"""Job Spark - Capa SILVER
Limpieza y normalización de las tablas bronze:
  - Tipos de datos correctos (int/float/date)
  - Fechas a formato ISO
  - Eliminación de nulos y duplicados
  - Enriquecimiento (equipos local/visitante, puntos correctos)
Salida en s3a://silver/ (Delta).
"""
import os
import sys
from pyspark.sql import SparkSession, Window, functions as F

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

# Por defecto el data lake vive en MinIO y las tablas son Delta. Los tests
# redirigen ambas cosas a disco local con parquet para ejecutar el job sin
# Docker; ver tests/test_pipeline_local.py.
LAKE_ROOT = os.environ.get("FEB_LAKE_ROOT", "s3a://")
TABLE_FORMAT = os.environ.get("FEB_TABLE_FORMAT", "delta")

_builder = (SparkSession.builder.appName("FEB Silver")
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

BRONZE = LAKE_ROOT + "bronze/"
SILVER = LAKE_ROOT + "silver/"

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
    df = scoped(spark.read.format(TABLE_FORMAT).load(BRONZE + "players"))

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

    for col in ("team", "home_team", "away_team"):
        df = df.withColumn(col, F.trim(F.col(col)))

    df = df.filter(F.col("player_name").isNotNull()).dropDuplicates(
        ["game_id", "player_name", "jersey"])
    _save(df, SILVER + "players")
    print(f"silver_players: {df.count()}")


def clean_games():
    """Cabecera del partido: fecha tipada y nombres de equipo normalizados."""
    df = scoped(spark.read.format(TABLE_FORMAT).load(BRONZE + "games"))
    df = _to_int(df, ["home_score", "away_score"])
    df = df.withColumn("game_date", F.to_date(F.col("date"), "dd/MM/yyyy"))
    for col in ("home_team", "away_team", "venue"):
        df = df.withColumn(col, F.trim(F.col(col)))
    df = df.filter(F.col("home_team").isNotNull() & F.col("away_team").isNotNull())
    df = df.dropDuplicates(["game_id"])
    _save(df, SILVER + "games")
    print(f"silver_games: {df.count()}")


def clean_playbyplay():
    df = scoped(spark.read.format(TABLE_FORMAT).load(BRONZE + "playbyplay"))
    df = _to_int(df, ["num", "quarter", "team", "scoreA", "scoreB", "player_id", "team_id"])
    df = df.filter(F.col("text").isNotNull()).dropDuplicates(["game_id", "num"])

    # made/shot_value/foul_type/sub_direction se derivan del texto del acta, no
    # de los logParamN crudos: su posición cambia de significado según el tipo
    # de jugada (logParam4 es "encestado" en un tiro pero "a quién le pitan la
    # falta" en una falta), mientras que el texto sigue una plantilla fija.
    df = df.withColumn(
        "made",
        F.when(~F.col("action").isin("shoot", "fthrow"), F.lit(None))
         .when(F.col("text").contains("ANOTADO"), F.lit(1))
         .when(F.col("text").contains("FALLADO"), F.lit(0))
         .otherwise(F.lit(None)).cast("int"))
    df = df.withColumn(
        "shot_value",
        F.when(F.col("action").isin("shoot", "fthrow"),
               F.regexp_extract(F.col("text"), r"TIRO DE (\d)", 1))
         .otherwise(F.lit(None)).cast("int"))
    df = df.withColumn(
        "foul_type",
        F.when(F.col("action") != "foul", F.lit(None))
         .when(F.col("text").contains("Descalificante"), F.lit("descalificante"))
         # Se compara por "cnica" en vez de "Técnica": evita depender de que la
         # tilde sobreviva intacta a cualquier codificación intermedia.
         .when(F.col("text").contains("cnica"), F.lit("tecnica"))
         .otherwise(F.lit("personal")))
    df = df.withColumn(
        "sub_direction",
        F.when(F.col("action") != "subst", F.lit(None))
         .when(F.col("text").contains("Entra"), F.lit("in"))
         .otherwise(F.lit("out")))

    # Asistencia: la FEB no enlaza el evento "assist" con la canasta que
    # reparte, pero le sigue siempre, en el mismo equipo y el mismo instante
    # de juego, a la jugada "shoot" que anota — no la precede: el acta apunta
    # primero el tiro y acredita la asistencia justo después. `num` es el
    # orden cronológico real (el JSON crudo lo lista del último suceso al
    # primero, así que num ascendente = avance del partido).
    orden = Window.partitionBy("game_id").orderBy(F.col("num"))
    next_cols = ["_next_action", "_next_player", "_next_team", "_next_time"]
    for col in next_cols:
        source = {"_next_action": "action", "_next_player": "player_id",
                  "_next_team": "team", "_next_time": "time"}[col]
        df = df.withColumn(col, F.lead(F.col(source)).over(orden))
    df = df.withColumn(
        "assisted_by_player_id",
        F.when(
            (F.col("action") == "shoot") & (F.col("made") == 1)
            & (F.col("_next_action") == "assist")
            & (F.col("_next_team") == F.col("team"))
            & (F.col("_next_time") == F.col("time")),
            F.col("_next_player"),
        ).otherwise(F.lit(None)).cast("int"))
    df = df.drop(*next_cols)

    # Nombre del jugador: el `player_id` del acta (bronze_players) no sirve
    # para enlazar — es la URL del EQUIPO, repetida en todos sus jugadores,
    # no un id por jugador (bug del origen, no de este pipeline). Sin un id
    # compartido, se cruza por partido: se saca "inicial. apellidos" del
    # texto de la jugada ("D. NGUBA ETAME") y se empareja con "apellidos,
    # nombre" del acta ("NGUBA ETAME, DAVID") dentro del mismo equipo. Si dos
    # compañeros comparten inicial y apellidos, se descarta el cruce para ese
    # jugador antes que arriesgarse a poner el nombre equivocado.
    etiqueta = F.regexp_extract(F.col("text"), r"\)\s*([^:]+):", 1)
    nombres_pbp = (
        df.filter((F.col("player_id").isNotNull()) & (etiqueta != ""))
          .select(
              "game_id", "player_id",
              (F.col("team") == 1).alias("is_home"),
              F.upper(F.substring(etiqueta, 1, 1)).alias("inicial"),
              F.upper(F.trim(F.regexp_replace(etiqueta, r"^\S+\.\s*", ""))).alias("apellidos"),
          )
          .dropDuplicates(["game_id", "player_id"])
    )

    acta = spark.read.format(TABLE_FORMAT).load(SILVER + "players").select(
        "game_id", "is_home", "player_name",
        F.upper(F.trim(F.element_at(F.split(F.col("player_name"), ","), 1))).alias("apellidos_acta"),
        F.upper(F.substring(F.trim(F.element_at(F.split(F.col("player_name"), ","), 2)), 1, 1)).alias("inicial_acta"),
    ).dropDuplicates(["game_id", "is_home", "player_name"])

    cruce = nombres_pbp.join(
        acta,
        (nombres_pbp.game_id == acta.game_id) & (nombres_pbp.is_home == acta.is_home)
        & (nombres_pbp.inicial == acta.inicial_acta) & (nombres_pbp.apellidos == acta.apellidos_acta),
        "inner",
    ).select(nombres_pbp.game_id, nombres_pbp.player_id, acta.player_name)

    resueltos = (cruce.groupBy("game_id", "player_id")
                 .agg(F.countDistinct("player_name").alias("n"), F.first("player_name").alias("player_name"))
                 .filter(F.col("n") == 1)
                 .select("game_id", "player_id", "player_name"))

    df = df.join(resueltos, ["game_id", "player_id"], "left")
    df = df.join(
        resueltos.select(
            F.col("game_id"),
            F.col("player_id").alias("assisted_by_player_id"),
            F.col("player_name").alias("assisted_by_name"),
        ),
        ["game_id", "assisted_by_player_id"], "left",
    )

    _save(df, SILVER + "playbyplay")
    print(f"silver_playbyplay: {df.count()}")


def clean_shots():
    df = scoped(spark.read.format(TABLE_FORMAT).load(BRONZE + "shots"))
    df = _to_int(df, ["quarter", "player", "team", "made"])
    df = _to_float(df, ["x", "y"])
    df = df.filter(F.col("x").isNotNull()).dropDuplicates(["game_id", "quarter", "time", "player", "x", "y"])
    _save(df, SILVER + "shots")
    print(f"silver_shots: {df.count()}")


def clean_teamstats():
    df = scoped(spark.read.format(TABLE_FORMAT).load(BRONZE + "teamstats"))
    df = _to_int(df, ["points", "t2m", "t2a", "t3m", "t3a", "ftm", "fta",
                      "off_reb", "def_reb", "tot_reb", "ast", "stl", "to", "blk", "pf"])
    df = df.filter(F.col("team_name").isNotNull()).dropDuplicates(["game_id", "team_id"])
    _save(df, SILVER + "teamstats")
    print(f"silver_teamstats: {df.count()}")


if __name__ == "__main__":
    clean_games()
    clean_players()
    clean_playbyplay()
    clean_shots()
    clean_teamstats()
    spark.stop()