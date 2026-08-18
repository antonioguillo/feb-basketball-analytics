-- Inicialización de ClickHouse: base de datos y tablas de consumo
CREATE DATABASE IF NOT EXISTS feb;

-- Tabla de jugadores (nivel partido)
CREATE TABLE IF NOT EXISTS feb.jugadores
(
    game_id       UInt32,
    year          UInt16,
    game_date     Date,
    jersey        UInt8,
    player_name   String,
    minutes       Float32,
    points        UInt16,
    t2m           UInt8,
    t2a           UInt8,
    t3m           UInt8,
    t3a           UInt8,
    ftm           UInt8,
    fta           UInt8,
    reb           UInt8,
    ast           UInt8,
    stl           UInt8,
    blk           UInt8,
    to            UInt8,
    pf            UInt8,
    plus_minus    Int16,
    val           Int16
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY (player_name, game_date);

-- Play-by-play
CREATE TABLE IF NOT EXISTS feb.playbyplay
(
    game_id   UInt32,
    year      UInt16,
    quarter   UInt8,
    time      String,
    text      String,
    team      Nullable(UInt8),
    action    String,
    scoreA    Nullable(UInt16),
    scoreB    Nullable(UInt16)
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY (game_id, quarter);

-- Tiros
CREATE TABLE IF NOT EXISTS feb.tiros
(
    game_id   UInt32,
    year      UInt16,
    quarter   UInt8,
    time      String,
    player    UInt8,
    team      UInt8,
    made      UInt8,
    x         Float64,
    y         Float64
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY (game_id, quarter);

-- Estadísticas de equipo por partido
CREATE TABLE IF NOT EXISTS feb.equipos_partido
(
    game_id   UInt32,
    year      UInt16,
    team_id   UInt32,
    team_name String,
    points    UInt16,
    t2m       UInt8,
    t2a       UInt8,
    t3m       UInt8,
    t3a       UInt8,
    ftm       UInt8,
    fta       UInt8,
    off_reb   UInt8,
    def_reb   UInt8,
    tot_reb   UInt8,
    ast       UInt8,
    stl       UInt8,
    to        UInt8,
    blk       UInt8,
    pf        UInt8
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY (game_id, team_id);

-- Hechos a nivel partido
CREATE TABLE IF NOT EXISTS feb.partidos
(
    game_id      UInt32,
    year         UInt16,
    date         String,
    home_score   UInt16,
    away_score   UInt16,
    total_points UInt16,
    winner       String
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY game_id;