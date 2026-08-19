-- Inicialización de ClickHouse: base de datos y tablas de consumo
CREATE DATABASE IF NOT EXISTS feb;

-- Tabla de jugadores (nivel partido)
CREATE TABLE IF NOT EXISTS feb.jugadores
(
    game_id       UInt32,
    competition   String,
    year          UInt16,
    game_date     Date,
    jersey        UInt8,
    player_name   String,
    team          String,
    is_home       UInt8,
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
    competition String,
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
    competition String,
    year      UInt16,
    quarter   UInt8,
    time      String,
    player    UInt8,
    team      UInt8,
    made      UInt8,
    x         Float64,
    y         Float64,
    shot_distance_m Float32,
    zone      String,
    is_three  UInt8,
    shot_points UInt8
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY (game_id, quarter);

-- Estadísticas de equipo por partido
CREATE TABLE IF NOT EXISTS feb.equipos_partido
(
    game_id   UInt32,
    competition String,
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
    competition  String,
    year         UInt16,
    date         String,
    game_date    Date,
    home_team    String,
    away_team    String,
    home_score   UInt16,
    away_score   UInt16,
    total_points UInt16,
    winner       String
) ENGINE = MergeTree()
PARTITION BY year
ORDER BY game_id;
-- Migracion de instalaciones anteriores: CREATE TABLE IF NOT EXISTS no anade
-- columnas nuevas a una tabla que ya existe.
ALTER TABLE feb.jugadores ADD COLUMN IF NOT EXISTS team String AFTER player_name;
ALTER TABLE feb.jugadores ADD COLUMN IF NOT EXISTS is_home UInt8 AFTER team;
ALTER TABLE feb.tiros     ADD COLUMN IF NOT EXISTS shot_distance_m Float32 AFTER y;
ALTER TABLE feb.tiros     ADD COLUMN IF NOT EXISTS zone String AFTER shot_distance_m;
ALTER TABLE feb.tiros     ADD COLUMN IF NOT EXISTS is_three UInt8 AFTER zone;
ALTER TABLE feb.tiros     ADD COLUMN IF NOT EXISTS shot_points UInt8 AFTER is_three;
ALTER TABLE feb.partidos  ADD COLUMN IF NOT EXISTS game_date Date AFTER date;
ALTER TABLE feb.partidos  ADD COLUMN IF NOT EXISTS home_team String AFTER game_date;
ALTER TABLE feb.partidos  ADD COLUMN IF NOT EXISTS away_team String AFTER home_team;

-- La competición se añade también por ALTER para instalaciones anteriores.
-- No entra en el ORDER BY: cambiarlo obligaría a recrear las tablas, y con la
-- partición por temporada el filtrado por competición ya es barato.
ALTER TABLE feb.jugadores       ADD COLUMN IF NOT EXISTS competition String AFTER game_id;
ALTER TABLE feb.playbyplay      ADD COLUMN IF NOT EXISTS competition String AFTER game_id;
ALTER TABLE feb.tiros           ADD COLUMN IF NOT EXISTS competition String AFTER game_id;
ALTER TABLE feb.equipos_partido ADD COLUMN IF NOT EXISTS competition String AFTER game_id;
ALTER TABLE feb.partidos        ADD COLUMN IF NOT EXISTS competition String AFTER game_id;
