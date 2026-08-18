def build_dim_players():
    df = spark.read.format("delta").load(SILVER + "players")
    dim = (df.groupBy("player_name").agg(
        F.countDistinct("game_id").alias("games"),
        F.sum("points").alias("total_points"),
        F.sum("reb").alias("total_rebounds"),
        F.sum("ast").alias("total_assists"),
        F.sum("stl").alias("total_steals"),
        F.sum("blk").alias("total_blocks"),
        F.sum("t3m").alias("total_3pm"),
        F.sum("t2m").alias("total_2pm"),
        F.sum("ftm").alias("total_ftm"),
        F.avg("val").alias("avg_efficiency"),
        F.sum("minutes").alias("total_minutes"),
        F.avg("points_per_36").alias("avg_points_per_36"),
        F.avg("points_per_48").alias("avg_points_per_48"),
        F.avg("offensive_rating_estimate").alias("avg_off_rating"),
        F.avg("defensive_rating_estimate").alias("avg_def_rating"),
        F.avg("net_rating_estimate").alias("avg_net_rating"),
        F.avg("usage_rate_estimate").alias("avg_usage_rate"),
        F.avg("efficiency_per_minute").alias("avg_eff_per_min"),
        F.avg("val_per_minute").alias("avg_val_per_min"),
        F.count(F.when("double_double_condition", True)).alias("double_double_count"),
        F.count(F.when("triple_double_condition", True)).alias("triple_double_count"),
    ))
    dim.write.mode("overwrite").format("delta").save(GOLD + "dim_jugadores")
    print(f"gold_dim_jugadores: {dim.count()}")
def build_dim_teams():
    df = spark.read.format("delta").load(SILVER + "teamstats")
    dim = (df.groupBy("team_id", "team_name").agg(
        F.countDistinct("game_id").alias("games"),
        F.sum("points").alias("total_points"),
    ))
    dim.write.mode("overwrite").format("delta").save(GOLD + "dim_equipos")
    print(f"gold_dim_equipos: {dim.count()}")
def build_fact_partidos():
    players = spark.read.format("delta").load(SILVER + "players")
    home = (players.filter(F.col("is_home") == True).groupBy("game_id", "year", "date")
            .agg(F.sum("points").alias("home_score")))
    away = (players.filter(F.col("is_home") == False).groupBy("game_id")
            .agg(F.sum("points").alias("away_score")))
    fact = home.join(away, "game_id", "inner")         .withColumn("total_points", F.col("home_score") + F.col("away_score"))         .withColumn("winner", F.when(F.col("home_score") > F.col("away_score"), "local").otherwise("visitante"))
    fact.write.mode("overwrite").partitionBy("year").format("delta").save(GOLD + "fact_partidos")
    print(f"gold_fact_partidos: {fact.count()}")
def build_fact_team_stats():
    df = spark.read.format("delta").load(SILVER + "teamstats")
    df = (df.withColumn("fgm", F.col("t2m") + F.col("t3m"))
             .withColumn("fga", F.col("t2a") + F.col("t3a"))
             .withColumn("fg_pct", F.when(F.col("fga") > 0, F.col("fgm") / F.col("fga")))
             .withColumn("t3_pct", F.when(F.col("t3a") > 0, F.col("t3m") / F.col("t3a")))
             .withColumn("ft_pct", F.when(F.col("fta") > 0, F.col("ftm") / F.col("fta"))))
    df.write.mode("overwrite").partitionBy("year").format("delta").save(GOLD + "fact_equipo_estadisticas")
    print(f"gold_fact_equipo_estadisticas: {df.count()}")
def build_fact_tiros():
    df = spark.read.format("delta").load(SILVER + "shots")
    df = df.withColumn("is_three", F.when(F.col("y") > 220, True).otherwise(False))
    df.write.mode("overwrite").partitionBy("year").format("delta").save(GOLD + "fact_tiros")
    print(f"gold_fact_tiros: {df.count()}")
