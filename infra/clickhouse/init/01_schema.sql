-- Inicialización de ClickHouse: base de datos y tablas de consumo
CREATE DATABASE IF NOT EXISTS feb;

-- Tabla de jugadores (nivel partido)
CREATE TABLE IF NOT EXISTS feb.jugadores
(
    game_id       UInt32,
    competition   String,
    `group`       String,
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
    scoreB    Nullable(UInt16),
    -- Quién protagoniza la jugada: sin esto solo sirve para el marcador
    -- corriendo. `made`/`shot_value`/`foul_type`/`sub_direction` se derivan
    -- del texto del acta en silver (jobs/spark_silver.py:clean_playbyplay),
    -- no de los logParamN crudos, cuyo significado cambia según la jugada.
    player_id Nullable(UInt32),
    team_id   Nullable(UInt32),
    made      Nullable(UInt8),
    shot_value Nullable(UInt8),
    foul_type  Nullable(String),
    sub_direction Nullable(String),
    -- El evento "assist" no trae un campo que lo enlace con la canasta que
    -- reparte; se resuelve en silver por adyacencia (mismo equipo, mismo
    -- instante de juego, jugada inmediatamente siguiente).
    assisted_by_player_id Nullable(UInt32),
    -- Nombre resuelto por partido+equipo+inicial/apellidos (ver ALTER más
    -- abajo): el player_id del acta de caja no sirve para enlazar aquí.
    player_name Nullable(String),
    assisted_by_name Nullable(String)
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
    `group`      String,
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

-- El grupo permite filtrar una liga por su subgrupo (E-A, ESTE, Unico...).
ALTER TABLE feb.jugadores ADD COLUMN IF NOT EXISTS `group` String AFTER competition;
ALTER TABLE feb.partidos  ADD COLUMN IF NOT EXISTS `group` String AFTER competition;

-- Jugador/equipo protagonista y campos derivados del play-by-play, para
-- instalaciones anteriores a que el pipeline empezara a traer idPlayer/idTeam.
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS player_id Nullable(UInt32) AFTER action;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS team_id Nullable(UInt32) AFTER player_id;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS made Nullable(UInt8) AFTER scoreB;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS shot_value Nullable(UInt8) AFTER made;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS foul_type Nullable(String) AFTER shot_value;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS sub_direction Nullable(String) AFTER foul_type;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS assisted_by_player_id Nullable(UInt32) AFTER sub_direction;

-- Nombre del jugador resuelto en silver por partido+equipo+inicial/apellidos
-- (jobs/spark_silver.py:clean_playbyplay): el player_id que trae el acta de
-- caja (bronze_players) no sirve para enlazar aquí, es la URL del equipo,
-- repetida en todos sus jugadores, no un id por jugador.
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS player_name Nullable(String) AFTER assisted_by_player_id;
ALTER TABLE feb.playbyplay ADD COLUMN IF NOT EXISTS assisted_by_name Nullable(String) AFTER player_name;
