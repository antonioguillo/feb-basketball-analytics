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

# Columnas enteras tal y como las produce bronze (ver jobs/spark_bronze.py).
INT_COLS = ["jersey", "points", "t2m", "t2a", "t3m", "t3a", "ftm", "fta", "reb",
            "ast", "stl", "blk", "to", "pf", "plus_minus", "val"]


def _to_int(df, cols):
    for c in cols:
        df = df.withColumn(c, F.col(c).cast("int"))
    return df


def _to_float(df, cols):
    for c in cols:
        df = df.withColumn(c, F.col(c).cast("double"))
    return df


def _per_minute(df, name, numerator, per=36):
    """Tasa proyectada a `per` minutos; null si el jugador no jugo."""
    return df.withColumn(name, F.when(
        F.col("minutes") > 0, F.col(numerator) / F.col("minutes") * per
    ).cast("double"))


def clean_players():
    df = spark.read.format("delta").load(BRONZE + "players")

    # bronze usa nombres heredados del scraper; silver fija el contrato que
    # consumen gold, el export a staging y el esquema de ClickHouse.
    df = (df.withColumnRenamed("minutes_played", "minutes")
            .withColumnRenamed("puntos", "points"))

    df = _to_int(df, INT_COLS)
    df = _to_float(df, ["minutes"])
    df = df.withColumn("game_date", F.to_date(F.col("date"), "dd/MM/yyyy"))

    # Tiros de campo = tiros de 2 + tiros de 3.
    df = (df.withColumn("fgm", F.col("t2m") + F.col("t3m"))
            .withColumn("fga", F.col("t2a") + F.col("t3a")))

    # Porcentajes de tiro (null si no hubo intentos, no 0: no es lo mismo).
    df = (df.withColumn("two_point_pct", F.when(F.col("t2a") > 0, F.col("t2m") / F.col("t2a")))
            .withColumn("three_point_pct", F.when(F.col("t3a") > 0, F.col("t3m") / F.col("t3a")))
            .withColumn("free_throw_pct", F.when(F.col("fta") > 0, F.col("ftm") / F.col("fta")))
            .withColumn("field_goal_pct", F.when(F.col("fga") > 0, F.col("fgm") / F.col("fga"))))

    # eFG% = (FGM + 0.5*3PM) / FGA  -- pondera que el triple vale mas.
    df = df.withColumn("effective_fg_pct", F.when(
        F.col("fga") > 0, (F.col("fgm") + 0.5 * F.col("t3m")) / F.col("fga")))

    # TS% = PTS / (2 * (FGA + 0.44*FTA))  -- incluye tiros libres.
    df = df.withColumn("true_shooting_pct", F.when(
        (F.col("fga") + F.col("fta")) > 0,
        F.col("points") / (2 * (F.col("fga") + 0.44 * F.col("fta")))))

    # Ritmos normalizados por minutos jugados.
    for name, source in [("points_per_36", "points"), ("rebounds_per_36", "reb"),
                         ("assists_per_36", "ast"), ("steals_per_36", "stl"),
                         ("blocks_per_36", "blk"), ("turnovers_per_36", "to"),
                         ("fouls_per_36", "pf")]:
        df = _per_minute(df, name, source)
    df = _per_minute(df, "val_per_36", "val")
    df = df.withColumn("val_per_minute", F.when(
        F.col("minutes") > 0, F.col("val") / F.col("minutes")).cast("double"))

    # Dobles-dobles / triples-dobles sobre las cinco categorias clasicas.
    categories = [F.col(c) >= 10 for c in ("points", "reb", "ast", "stl", "blk")]
    double_count = sum(c.cast("int") for c in categories)
    df = (df.withColumn("double_digit_categories", double_count)
            .withColumn("is_double_double", double_count >= 2)
            .withColumn("is_triple_double", double_count >= 3))

    df = df.filter(F.col("player_name").isNotNull()).dropDuplicates(
        ["game_id", "player_name", "jersey"])
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