"""Job Spark - Capa BRONZE
Lee los JSON raw de MinIO y los escribe como tablas Delta (particionadas por year)
manteniendo los datos tal cual (sin limpieza), para poder reprocesar siempre.

Tablas de salida (en s3a://bronze/):
  - bronze_players   : stats por jugador
  - bronze_playbyplay: play-by-play
  - bronze_shots     : tiros con coordenadas
  - bronze_teamstats : stats de equipo
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

# Alcance de la ejecución. Vacío = todo el lago. Con valores, solo se reprocesan
# esas particiones: es lo que hace incremental el pipeline, porque con
# partitionOverwriteMode=dynamic la escritura solo toca las particiones que
# aparecen en los datos escritos.
SCOPE_COMPETITIONS = [c for c in os.environ.get("FEB_COMPETITIONS", "").split(",") if c]
SCOPE_SEASONS = [s for s in os.environ.get("FEB_SEASONS", "").split(",") if s]

PARTITIONS = ["competition", "year"]

# Un cambio de particionado o de tipos no se puede aplicar sobre una tabla
# existente: hay que reescribirla entera. FEB_REBUILD=1 hace justo eso.
REBUILD = os.environ.get("FEB_REBUILD", "") == "1"


_builder = (SparkSession.builder.appName("FEB Bronze")
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

RAW = LAKE_ROOT + "raw/"
BRONZE = LAKE_ROOT + "bronze/"


def save(df, name, partition_by=PARTITIONS):
    writer = df.write.mode("overwrite")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    if REBUILD:
        writer = writer.option("overwriteSchema", "true")
    writer.format(TABLE_FORMAT).save(BRONZE + name)


def read_raw() -> "DataFrame":
    """Lee raw aprovechando la partición del propio path.

    Las rutas son competition=<liga>/year=<temporada>/group=<grupo>/..., así que
    Spark expone esas tres claves como columnas. `year` es la TEMPORADA, no el
    año natural: la 2025/2026 se juega entre octubre de 2025 y mayo de 2026, y
    derivar el año de `meta.date` partía cada temporada en dos.
    """
    # Se leen solo las rutas bien particionadas, no el bucket entero: cualquier
    # objeto suelto (una prueba, un fichero de otro proceso) reventaría la
    # inferencia de esquema. `basePath` es lo que mantiene el descubrimiento de
    # particiones al usar un patrón.
    df = (spark.read
          .option("basePath", RAW)
          .json(RAW + "competition=*/year=*/group=*/*.json"))

    for column, values in (("competition", SCOPE_COMPETITIONS), ("year", SCOPE_SEASONS)):
        if values:
            df = df.filter(F.col(column).isin(values))

    # El año natural se conserva aparte: sirve para fechar, no para agrupar.
    return df.withColumn("calendar_year", F.substring(F.col("meta.date"), 7, 4))


def build_games(df):
    """Una fila por partido con los nombres de los equipos.

    Sin esto no se puede saber con que equipo jugo cada jugador: la ficha solo
    marca si es local o visitante, y los nombres viven en la cabecera del JSON.
    """
    games = df.select(
        F.col("meta.game_id").alias("game_id"),
        F.col("competition"),
        F.col("year"),
        F.col("group"),
        F.col("calendar_year"),
        F.col("meta.date").alias("date"),
        F.col("meta.time").alias("tipoff"),
        F.col("meta.venue").alias("venue"),
        F.col("meta.home_team").alias("home_team"),
        F.col("meta.away_team").alias("away_team"),
        F.col("meta.home_score").alias("home_score"),
        F.col("meta.away_score").alias("away_score"),
    ).dropDuplicates(["game_id"])
    save(games, "games")
    print(f"bronze_games: {games.count()} filas")


def build_players(df):
    def flat(rows_col, is_home):
        team_col = "meta.home_team" if is_home else "meta.away_team"
        return (df.select(
            F.col("meta.game_id").alias("game_id"),
            F.col("meta.date").alias("date"),
            F.col("competition"),
            F.col("year"),
            F.col("group"),
            F.lit(is_home).alias("is_home"),
            F.col(team_col).alias("team"),
            F.col("meta.home_team").alias("home_team"),
            F.col("meta.away_team").alias("away_team"),
            F.explode(rows_col).alias("p"),
        ).select(
            "game_id", "date", "competition", "year", "group", "is_home",
            "team", "home_team", "away_team",
            F.col("p.jersey").alias("jersey"),
            F.col("p.name").alias("player_name"),
            F.col("p.player_id").alias("player_id"),
            F.col("p.minutes").alias("minutes_played"),
            F.col("p.points").alias("puntos"),
            F.col("p.two_points_made").alias("t2m"),
            F.col("p.two_points_attempted").alias("t2a"),
            F.col("p.three_points_made").alias("t3m"),
            F.col("p.three_points_attempted").alias("t3a"),
            F.col("p.free_throws_made").alias("ftm"),
            F.col("p.free_throws_attempted").alias("fta"),
            F.col("p.total_rebounds").alias("reb"),
            F.col("p.assists").alias("ast"),
            F.col("p.steals").alias("stl"),
            F.col("p.blocks").alias("blk"),
            F.col("p.turnovers").alias("to"),
            F.col("p.fouls").alias("pf"),
            F.col("p.plus_minus").alias("plus_minus"),
            F.col("p.efficiency").alias("val"),
        ))

    home = flat("players_home", True)
    away = flat("players_away", False)
    players = home.unionByName(away)
    save(players, "players")
    print(f"bronze_players: {players.count()} filas")


def build_playbyplay(df):
    pbp = (df.select(
        F.col("meta.game_id").alias("game_id"),
        F.col("competition"),
        F.col("year"),
        F.explode("play_by_play").alias("line"),
    ).select(
        "game_id", "competition", "year",
        F.col("line.num").alias("num"),
        F.col("line.quarter").alias("quarter"),
        F.col("line.time").alias("time"),
        F.col("line.text").alias("text"),
        F.col("line.team").alias("team"),
        F.col("line.action").alias("action"),
        F.col("line.scoreA").alias("scoreA"),
        F.col("line.scoreB").alias("scoreB"),
        # Quién protagoniza la jugada. Sin esto el play-by-play solo sirve para
        # el marcador corriendo: no se puede saber qué jugador tiró, asistió,
        # entró a pista o cometió la falta. Van tipados a int ya en bronze
        # (a diferencia de num/quarter/team, que se dejan tal cual) porque son
        # ids numéricos sin formato que preservar.
        F.col("line.idPlayer").cast("int").alias("player_id"),
        F.col("line.idTeam").cast("int").alias("team_id"),
    ))
    save(pbp, "playbyplay")
    print(f"bronze_playbyplay: {pbp.count()} filas")


def build_shots(df):
    shots = (df.select(
        F.col("meta.game_id").alias("game_id"),
        F.col("competition"),
        F.col("year"),
        F.explode("shots").alias("s"),
    ).select(
        "game_id", "competition", "year",
        F.col("s.quarter").alias("quarter"),
        F.col("s.t").alias("time"),
        F.col("s.player").alias("player"),
        F.col("s.team").alias("team"),
        F.col("s.m").alias("made"),
        F.col("s.x").alias("x"),
        F.col("s.y").alias("y"),
    ))
    save(shots, "shots")
    print(f"bronze_shots: {shots.count()} filas")


def build_teamstats(df):
    def flat_teams(rows_col):
        return (df.select(
            F.col("meta.game_id").alias("game_id"),
            F.col("competition"),
            F.col("year"),
            F.explode(F.col(rows_col).getField("TEAM")).alias("t"),
        ).select(
            "game_id", "competition", "year",
            F.col("t.id").alias("team_id"),
            F.col("t.name").alias("team_name"),
            F.col("t.pts").alias("points"),
            F.col("t.p2m").alias("t2m"),
            F.col("t.p2a").alias("t2a"),
            F.col("t.p3m").alias("t3m"),
            F.col("t.p3a").alias("t3a"),
            F.col("t.p1m").alias("ftm"),
            F.col("t.p1a").alias("fta"),
            F.col("t.ro").alias("off_reb"),
            F.col("t.rd").alias("def_reb"),
            F.col("t.rt").alias("tot_reb"),
            F.col("t.assist").alias("ast"),
            F.col("t.st").alias("stl"),
            F.col("t.to").alias("to"),
            F.col("t.bs").alias("blk"),
            F.col("t.pf").alias("pf"),
        ))

    teams = flat_teams("team_stats")
    save(teams, "teamstats")
    print(f"bronze_teamstats: {teams.count()} filas")


if __name__ == "__main__":
    raw = read_raw()
    build_games(raw)
    build_players(raw)
    build_playbyplay(raw)
    build_shots(raw)
    build_teamstats(raw)
    spark.stop()
