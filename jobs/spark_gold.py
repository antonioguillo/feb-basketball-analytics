"""Job Spark - Capa GOLD
Construye el modelo dimensional de consumo a partir de silver:

  - dim_jugadores             : perfil de jugador por temporada (totales + ratios)
  - dim_equipos               : equipos con totales agregados
  - fact_partidos             : un registro por partido con marcador y ganador
  - fact_equipo_estadisticas  : stats de equipo por partido con porcentajes
  - fact_tiros                : tiros individuales enriquecidos para mapas

Uso: spark-submit spark_gold.py [minio_endpoint] [access_key] [secret_key]
"""
import os
import sys
from pyspark.sql import SparkSession, functions as F

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

# Por defecto el data lake vive en MinIO y las tablas son Delta. Los tests
# redirigen ambas cosas a disco local con parquet para ejecutar el job sin
# Docker; ver tests/test_pipeline_local.py.
LAKE_ROOT = os.environ.get("FEB_LAKE_ROOT", "s3a://")
TABLE_FORMAT = os.environ.get("FEB_TABLE_FORMAT", "delta")

_builder = (SparkSession.builder.appName("FEB Gold")
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.sql.sources.partitionOverwriteMode",
                    "static" if os.environ.get("FEB_REBUILD") == "1" else "dynamic"))
if TABLE_FORMAT == "delta":
    _builder = (_builder
                .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
                .config("spark.sql.catalog.spark_catalog",
                        "org.apache.spark.sql.delta.catalog.DeltaCatalog"))
if LAKE_ROOT.startswith("s3a://"):
    _builder = (_builder
                .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
                .config("spark.hadoop.fs.s3a.access.key", ACCESS_KEY)
                .config("spark.hadoop.fs.s3a.secret.key", SECRET_KEY)
                .config("spark.hadoop.fs.s3a.path.style.access", "true")
                .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
                .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false"))
spark = _builder.getOrCreate()

SILVER = LAKE_ROOT + "silver/"
GOLD = LAKE_ROOT + "gold/"

# Alcance de la ejecución. Vacío = todo el lago; con valores, solo se reprocesan
# esas particiones. Con partitionOverwriteMode=dynamic la escritura toca
# únicamente las particiones presentes en los datos escritos, de modo que
# actualizar una temporada no reescribe el histórico entero.
SCOPE_COMPETITIONS = [c for c in os.environ.get("FEB_COMPETITIONS", "").split(",") if c]
SCOPE_SEASONS = [s for s in os.environ.get("FEB_SEASONS", "").split(",") if s]

PARTITIONS = ["competition", "year"]

# Un cambio de particionado o de tipos no se puede aplicar sobre una tabla
# existente: hay que reescribirla entera. FEB_REBUILD=1 hace justo eso.
REBUILD = os.environ.get("FEB_REBUILD", "") == "1"



def scoped(df):
    """Restringe un DataFrame al alcance pedido, podando particiones."""
    for column, values in (("competition", SCOPE_COMPETITIONS), ("year", SCOPE_SEASONS)):
        if values:
            df = df.filter(F.col(column).isin(values))
    return df

def _save(df, path):
    """Escribe una tabla particionada; en modo reconstrucción rehace el esquema."""
    writer = df.write.mode("overwrite").partitionBy(*PARTITIONS)
    if REBUILD:
        writer = writer.option("overwriteSchema", "true")
    writer.format(TABLE_FORMAT).save(path)




def _ratio(numerator: str, denominator: str):
    """Ratio sobre totales acumulados, null si no hay intentos.

    Se calcula sumando aciertos e intentos y dividiendo al final: promediar
    los porcentajes de cada partido daria mas peso a los partidos con pocos
    intentos y sesgaria el dato.
    """
    return F.when(F.col(denominator) > 0, F.col(numerator) / F.col(denominator))


def build_dim_players():
    """Perfil de jugador por temporada: totales, medias por partido y ratios."""
    df = scoped(spark.read.format(TABLE_FORMAT).load(SILVER + "players"))

    dim = df.groupBy("competition", "player_name", "year").agg(
        # Un jugador puede cambiar de equipo a mitad de temporada: se queda el
        # ultimo con el que aparece, que es el relevante para ojearlo hoy.
        F.max(F.struct("game_date", "team", "group")).alias("_last"),
        F.countDistinct("game_id").alias("games"),
        F.sum("minutes").alias("total_minutes"),
        F.sum("points").alias("total_points"),
        F.sum("reb").alias("total_rebounds"),
        F.sum("ast").alias("total_assists"),
        F.sum("stl").alias("total_steals"),
        F.sum("blk").alias("total_blocks"),
        F.sum("to").alias("total_turnovers"),
        F.sum("pf").alias("total_fouls"),
        F.sum("val").alias("total_val"),
        F.sum("t2m").alias("total_2pm"), F.sum("t2a").alias("total_2pa"),
        F.sum("t3m").alias("total_3pm"), F.sum("t3a").alias("total_3pa"),
        F.sum("ftm").alias("total_ftm"), F.sum("fta").alias("total_fta"),
        F.sum("fgm").alias("total_fgm"), F.sum("fga").alias("total_fga"),
        F.avg("points").alias("ppg"),
        F.avg("reb").alias("rpg"),
        F.avg("ast").alias("apg"),
        F.avg("minutes").alias("mpg"),
        F.avg("val").alias("avg_val"),
        F.avg("plus_minus").alias("avg_plus_minus"),
        F.avg("points_per_36").alias("avg_points_per_36"),
        F.sum(F.col("is_double_double").cast("int")).alias("double_doubles"),
        F.sum(F.col("is_triple_double").cast("int")).alias("triple_doubles"),
        F.max("points").alias("best_points"),
        F.max("val").alias("best_val"),
    )

    dim = (dim.withColumn("team", F.col("_last.team"))
          .withColumn("group", F.col("_last.group")).drop("_last"))

    dim = (dim.withColumn("two_point_pct", _ratio("total_2pm", "total_2pa"))
              .withColumn("three_point_pct", _ratio("total_3pm", "total_3pa"))
              .withColumn("free_throw_pct", _ratio("total_ftm", "total_fta"))
              .withColumn("field_goal_pct", _ratio("total_fgm", "total_fga"))
              .withColumn("effective_fg_pct", F.when(
                  F.col("total_fga") > 0,
                  (F.col("total_fgm") + 0.5 * F.col("total_3pm")) / F.col("total_fga")))
              .withColumn("true_shooting_pct", F.when(
                  (F.col("total_fga") + F.col("total_fta")) > 0,
                  F.col("total_points") / (2 * (F.col("total_fga") + 0.44 * F.col("total_fta")))))
              .withColumn("val_per_minute", F.when(
                  F.col("total_minutes") > 0, F.col("total_val") / F.col("total_minutes"))))

    _save(dim, GOLD + "dim_jugadores")
    print(f"gold_dim_jugadores: {dim.count()}")


def build_dim_teams():
    df = scoped(spark.read.format(TABLE_FORMAT).load(SILVER + "teamstats"))
    dim = df.groupBy("competition", "team_id", "team_name", "year").agg(
        F.countDistinct("game_id").alias("games"),
        F.sum("points").alias("total_points"),
        F.avg("points").alias("ppg"),
        F.sum("tot_reb").alias("total_rebounds"),
        F.sum("ast").alias("total_assists"),
        F.sum("t2m").alias("total_2pm"), F.sum("t2a").alias("total_2pa"),
        F.sum("t3m").alias("total_3pm"), F.sum("t3a").alias("total_3pa"),
        F.sum("ftm").alias("total_ftm"), F.sum("fta").alias("total_fta"),
    )
    dim = (dim.withColumn("two_point_pct", _ratio("total_2pm", "total_2pa"))
              .withColumn("three_point_pct", _ratio("total_3pm", "total_3pa"))
              .withColumn("free_throw_pct", _ratio("total_ftm", "total_fta")))
    _save(dim, GOLD + "dim_equipos")
    print(f"gold_dim_equipos: {dim.count()}")


def build_fact_partidos():
    """Un registro por partido. El marcador se reconstruye sumando los puntos
    de los jugadores de cada lado, que es lo unico que trae la ficha web."""
    players = scoped(spark.read.format(TABLE_FORMAT).load(SILVER + "players"))

    home = (players.filter(F.col("is_home"))
            .groupBy("game_id", "competition", "year", "group", "date", "game_date",
                     "home_team", "away_team")
            .agg(F.sum("points").alias("home_score")))
    away = (players.filter(~F.col("is_home"))
            .groupBy("game_id")
            .agg(F.sum("points").alias("away_score")))

    fact = (home.join(away, "game_id", "inner")
            .withColumn("total_points", F.col("home_score") + F.col("away_score"))
            .withColumn("winner", F.when(F.col("home_score") > F.col("away_score"), "local")
                        .when(F.col("home_score") < F.col("away_score"), "visitante")
                        .otherwise("empate"))
            .withColumn("margin", F.abs(F.col("home_score") - F.col("away_score"))))

    _save(fact, GOLD + "fact_partidos")
    print(f"gold_fact_partidos: {fact.count()}")


def build_fact_team_stats():
    df = scoped(spark.read.format(TABLE_FORMAT).load(SILVER + "teamstats"))
    df = (df.withColumn("fgm", F.col("t2m") + F.col("t3m"))
            .withColumn("fga", F.col("t2a") + F.col("t3a")))
    df = (df.withColumn("fg_pct", _ratio("fgm", "fga"))
            .withColumn("t2_pct", _ratio("t2m", "t2a"))
            .withColumn("t3_pct", _ratio("t3m", "t3a"))
            .withColumn("ft_pct", _ratio("ftm", "fta"))
            .withColumn("effective_fg_pct", F.when(
                F.col("fga") > 0, (F.col("fgm") + 0.5 * F.col("t3m")) / F.col("fga")))
            # Posesiones estimadas: FGA - ORB + TO + 0.44*FTA (formula estandar).
            .withColumn("possessions",
                        F.col("fga") - F.col("off_reb") + F.col("to") + 0.44 * F.col("fta")))
    df = df.withColumn("offensive_rating", F.when(
        F.col("possessions") > 0, F.col("points") / F.col("possessions") * 100))

    _save(df, GOLD + "fact_equipo_estadisticas")
    print(f"gold_fact_equipo_estadisticas: {df.count()}")


# Geometria de la cancha para clasificar los tiros.
# La API devuelve x/y como porcentaje (0-100) sobre la pista completa, con los
# dos aros en extremos opuestos del eje x. Convertimos a metros sobre una pista
# FIBA de 28x15 m. HOOP_X_PCT y THREE_POINT_M se calibraron contra los 3PA del
# box score de 6 partidos (836 tiros): 0.8% de discrepancia.
COURT_LENGTH_M, COURT_WIDTH_M = 28.0, 15.0
HOOP_X_PCT = 5.0
THREE_POINT_M = 6.6
RESTRICTED_AREA_M = 1.25


def build_fact_tiros():
    """Tiros con distancia en metros y zona, a partir de las coordenadas de la API."""
    df = scoped(spark.read.format(TABLE_FORMAT).load(SILVER + "shots"))

    # Cada tiro se mide contra el aro de su mitad de pista.
    hoop_x = F.when(F.col("x") < 50, F.lit(HOOP_X_PCT)).otherwise(F.lit(100 - HOOP_X_PCT))
    dx = (F.col("x") - hoop_x) * (COURT_LENGTH_M / 100)
    dy = (F.col("y") - 50) * (COURT_WIDTH_M / 100)
    distance = F.sqrt(dx * dx + dy * dy)

    df = (df.withColumn("shot_distance_m", distance)
            .withColumn("is_three", distance > THREE_POINT_M)
            .withColumn("zone", F.when(distance <= RESTRICTED_AREA_M, "aro")
                        .when(distance <= THREE_POINT_M, "media")
                        .otherwise("triple"))
            .withColumn("shot_points", F.when(F.col("made") == 1,
                                              F.when(distance > THREE_POINT_M, 3).otherwise(2))
                        .otherwise(0)))

    _save(df, GOLD + "fact_tiros")
    print(f"gold_fact_tiros: {df.count()}")


if __name__ == "__main__":
    build_dim_players()
    build_dim_teams()
    build_fact_partidos()
    build_fact_team_stats()
    build_fact_tiros()
    spark.stop()
