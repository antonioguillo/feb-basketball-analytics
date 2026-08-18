"""Job Spark - Capa BRONZE
Lee los JSON raw de MinIO y los escribe como tablas Delta (particionadas por year)
manteniendo los datos tal cual (sin limpieza), para poder reprocesar siempre.

Tablas de salida (en s3a://bronze/):
  - bronze_players   : stats por jugador
  - bronze_playbyplay: play-by-play
  - bronze_shots     : tiros con coordenadas
  - bronze_teamstats : stats de equipo
"""
import sys
from pyspark.sql import SparkSession, functions as F

MINIO_ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://minio:9000"
ACCESS_KEY = sys.argv[2] if len(sys.argv) > 2 else "minioadmin"
SECRET_KEY = sys.argv[3] if len(sys.argv) > 3 else "minioadmin"

spark = SparkSession.builder \
    .appName("FEB Bronze") \
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

RAW = "s3a://raw/"
BRONZE = "s3a://bronze/"


def read_raw() -> "DataFrame":
    df = (spark.read.json(RAW)
          .withColumn("year", F.substring(F.col("meta.date"), 7, 4)))
    return df


def build_players(df):
    def flat(rows_col, is_home):
        return (df.select(
            F.col("meta.game_id").alias("game_id"),
            F.col("meta.date").alias("date"),
            F.col("year"),
            F.lit(is_home).alias("is_home"),
            F.explode(rows_col).alias("p"),
        ).select(
            "game_id", "date", "year", "is_home",
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
    players.write.mode("overwrite").partitionBy("year").format("delta").save(BRONZE + "players")
    print(f"bronze_players: {players.count()} filas")


def build_playbyplay(df):
    pbp = (df.select(
        F.col("meta.game_id").alias("game_id"),
        F.col("year"),
        F.explode("play_by_play").alias("line"),
    ).select(
        "game_id", "year",
        F.col("line.num").alias("num"),
        F.col("line.quarter").alias("quarter"),
        F.col("line.time").alias("time"),
        F.col("line.text").alias("text"),
        F.col("line.team").alias("team"),
        F.col("line.action").alias("action"),
        F.col("line.scoreA").alias("scoreA"),
        F.col("line.scoreB").alias("scoreB"),
    ))
    pbp.write.mode("overwrite").partitionBy("year").format("delta").save(BRONZE + "playbyplay")
    print(f"bronze_playbyplay: {pbp.count()} filas")


def build_shots(df):
    shots = (df.select(
        F.col("meta.game_id").alias("game_id"),
        F.col("year"),
        F.explode("shots").alias("s"),
    ).select(
        "game_id", "year",
        F.col("s.quarter").alias("quarter"),
        F.col("s.t").alias("time"),
        F.col("s.player").alias("player"),
        F.col("s.team").alias("team"),
        F.col("s.m").alias("made"),
        F.col("s.x").alias("x"),
        F.col("s.y").alias("y"),
    ))
    shots.write.mode("overwrite").partitionBy("year").format("delta").save(BRONZE + "shots")
    print(f"bronze_shots: {shots.count()} filas")


def build_teamstats(df):
    def flat_teams(rows_col):
        return (df.select(
            F.col("meta.game_id").alias("game_id"),
            F.col("year"),
            F.explode(F.col(rows_col).getField("TEAM")).alias("t"),
        ).select(
            "game_id", "year",
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
    teams.write.mode("overwrite").partitionBy("year").format("delta").save(BRONZE + "teamstats")
    print(f"bronze_teamstats: {teams.count()} filas")


if __name__ == "__main__":
    raw = read_raw()
    build_players(raw)
    build_playbyplay(raw)
    build_shots(raw)
    build_teamstats(raw)
    spark.stop()
