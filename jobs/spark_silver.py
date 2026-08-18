"""Job Spark - Capa SILVER
Limpieza y normalización de las tablas bronze:
  - Tipos de datos correctos (int/float/date)
  - Fechas a formato ISO
  - Eliminación de nulos y duplicados
  - Enriquecimiento (equipos local/visitante, puntos correctos)
Salida en s3a://silver/ (Delta).
"""
import sys
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import DateType

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

spark = SparkSession.builder \
    .appName("FEB Silver") \
    .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
    .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
    .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT) \
    .config("spark.hadoop.fs.s3a.access.key", ACCESS_KEY) \
    .config("spark.hadoop.fs.s3a.secret.key", SECRET_KEY) \
    .config("spark.hadoop.fs.s3a.path.style.access", "true") \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
    .config("spark.sql.shuffle.partitions", "8") \
    .getOrCreate()

BRONZE = "s3a://bronze/"
SILVER = "s3a://silver/"

INT_COLS = ["jersey", "puntos", "t2m", "t2a", "t3m", "t3a", "ftm", "fta", "reb",
            "ast", "stl", "blk", "to", "pf", "plus_minus", "val",
            "double_double_condition", "triple_double_condition"]
FLOAT_COLS = ["minutes", "x", "y",
              # Nuevas métricas avanzables
              "two_point_pct", "three_point_pct", "free_throw_pct",
              "effective_fg_pct", "true_shooting_pct",
              "plus_minus_48", "offensive_rating_estimate", "defensive_rating_estimate",
              "net_rating_estimate", "efficiency_per_minute", "val_per_minute",
              "usage_rate_estimate", "points_per_36", "points_per_48",
              "turnover_per_36", "steal_per_36", "block_per_36",
              "rebounds_per_36", "fouls_per_36",
              "efficiency_per_minute", "points_per_possession"]


def _to_int(df, cols):
    for c in cols:
        df = df.withColumn(c, F.col(c).cast("int"))
    return df


def _to_float(df, cols):
    for c in cols:
        df = df.withColumn(c, F.col(c).cast("double"))
    return df


def clean_players():
    df = spark.read.format("delta").load(BRONZE + "players")
    df = _to_int(df, INT_COLS)
    df = _to_float(df, ["minutes"])
    # --- NUEVAS MÉTRICAS AVANZABLES EN SILVER ---
    # effective_fg_pct: (2PM + 1.5 × 3PM) / FGA - pondremos null en silver, calcularemos en gold
    df = df.withColumn("effective_fg_pct", F.lit(None).cast("float"))
    # true_shooting_pct: points / (2 × (2PA + 0.44 × FTA)) - pondremos null en silver
    df = df.withColumn("true_shooting_pct", F.lit(None).cast("float"))
    # val_per_minute: efficiency / minutos
    df = df.withColumn("val_per_minute", F.when(F.col("minutes_played") > 0,
                                                 F.col("val") / F.col("minutes_played")).otherwise(F.lit(None).cast("float")))
    # usage_rate_estimate: refinamos la fórmula
    df = df.withColumn("usage_rate_estimate",
                       F.when(F.col("minutes_played") > 0,
                              (F.col("two_points_attempted") + F.col("0.44") * F.col("free_throws_attempted") + F.col("turnovers")) * (48 / F.col("minutes_played")) * 0.2).otherwise(F.lit(None).cast("float")))
    # net_rating_estimate: aproximado
    df = df.withColumn("net_rating_estimate",
                       F.when(F.col("plus_minus_48").isNotNull(),
                              F.col("plus_minus_48") + F.col("offensive_rating_estimate") - F.col("defensive_rating_estimate")).otherwise(F.lit(None).cast("float")))
    # efficiency_per_minute
    df = df.withColumn("efficiency_per_minute", F.when(F.col("minutes_played") > 0,
                                                     F.col("efficiency") / F.col("minutes_played")).otherwise(F.lit(None).cast("float")))
    # --- RATINGS AVANZADOS (quedan en null hasta gold) ---
    df = df.withColumn("offensive_rating_estimate", F.lit(None).cast("float"))
    df = df.withColumn("defensive_rating_estimate", F.lit(None).cast("float"))
    # --- PER-36 rates (calculables desde los totales de partido) ---
    df = df.withColumn("turnover_per_36", F.when(F.col("minutes_played") > 0,
                                                 F.col("to") / F.col("minutes_played") * 36).otherwise(F.lit(None).cast("float")))
    df = df.withColumn("steal_per_36", F.when(F.col("minutes_played") > 0,
                                             F.col("stl") / F.col("minutes_played") * 36).otherwise(F.lit(None).cast("float")))
    df = df.withColumn("block_per_36", F.when(F.col("minutes_played") > 0,
                                             F.col("blk") / F.col("minutes_played") * 36).otherwise(F.lit(None).cast("float")))
    df = df.withColumn("rebounds_per_36", F.when(F.col("minutes_played") > 0,
                                                F.col("reb") / F.col("minutes_played") * 36).otherwise(F.lit(None).cast("float")))
    df = df.withColumn("fouls_per_36", F.when(F.col("minutes_played") > 0,
                                             F.col("pf") / F.col("minutes_played") * 36).otherwise(F.lit(None).cast("float")))
    # --- CONVERSIONES ---
    df = _to_float(df, FLOAT_COLS)
    df = df.filter(F.col("player_name").isNotNull()).dropDuplicates(["game_id", "player_name", "jersey"])
    df.write.mode("overwrite").partitionBy("year").format("delta").save(SILVER + "players")
    print(f"silver_players: {df.count()}")


def clean_playbyplay():
    df = spark.read.format("delta").load(BRONZE + "playbyplay")
    df = _to_int(df, ["num", "quarter", "team", "scoreA", "scoreB"])
    df = df.filter(F.col("text").isNotNull()).dropDuplicates(["game_id", "num"])
    df.write.mode("overwrite").partitionBy("year").format("delta").save(SILVER + "playbyplay")
    print(f"silver_playbyplay: {df.count()}")


def clean_shots():
    df = spark.read.format("delta").load(BRONZE + "shots")
    df = _to_int(df, ["quarter", "player", "team", "made"])
    df = _to_float(df, ["x", "y"])
    df = df.filter(F.col("x").isNotNull()).dropDuplicates(["game_id", "quarter", "time", "player", "x", "y"])
    df.write.mode("overwrite").partitionBy("year").format("delta").save(SILVER + "shots")
    print(f"silver_shots: {df.count()}")


def clean_teamstats():
    df = spark.read.format("delta").load(BRONZE + "teamstats")
    df = _to_int(df, ["points", "t2m", "t2a", "t3m", "t3a", "ftm", "fta",
                      "off_reb", "def_reb", "tot_reb", "ast", "stl", "to", "blk", "pf"])
    df = df.filter(F.col("team_name").isNotNull()).dropDuplicates(["game_id", "team_id"])
    df.write.mode("overwrite").partitionBy("year").format("delta").save(SILVER + "teamstats")
    print(f"silver_teamstats: {df.count()}")


if __name__ == "__main__":
    clean_players()
    clean_playbyplay()
    clean_shots()
    clean_teamstats()
    spark.stop()