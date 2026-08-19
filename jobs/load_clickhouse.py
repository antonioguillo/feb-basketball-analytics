"""Carga datos desde el staging de MinIO (parquet plano limpio) hacia ClickHouse.

El job Spark jobs/export_clickhouse.py materializa el estado lógico de las capas
silver/gold Delta en s3a://staging/<tabla> (overwrite), y este loader lee esos
Parquet vía la función s3() de ClickHouse.

Uso: python jobs/load_clickhouse.py [tabla]
      tabla: jugadores | playbyplay | tiros | equipos_partido | partidos
"""
import os
import subprocess
import sys

CLICKHOUSE_CONTAINER = "feb-clickhouse"
CH_USER = os.environ.get("CH_USER", "default")
CH_PASSWORD = os.environ.get("CH_PASSWORD", "feb")
MINIO_ENDPOINT = "http://minio:9000"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"

# name: (tabla CH, tabla staging MinIO)
TABLES = {
    "jugadores": ("feb.jugadores", "staging/jugadores"),
    "playbyplay": ("feb.playbyplay", "staging/playbyplay"),
    "tiros": ("feb.tiros", "staging/tiros"),
    "equipos_partido": ("feb.equipos_partido", "staging/equipos_partido"),
    "partidos": ("feb.partidos", "staging/partidos"),
}


def _query(sql: str):
    cmd = ["docker", "exec", CLICKHOUSE_CONTAINER, "clickhouse-client",
           "--user", CH_USER, "--password", CH_PASSWORD, "--query", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"ERROR: {proc.stderr.strip()}")
        sys.exit(1)
    return proc.stdout


def load(table):
    ch_table, staging = TABLES[table]
    url = f"{MINIO_ENDPOINT}/{staging}/*.parquet"
    auth = f"'{ACCESS_KEY}', '{SECRET_KEY}'"
    src = f"s3('{url}', {auth}, 'Parquet')"

    total = _query(f"SELECT count() FROM {src}").strip()

    if table == "jugadores":
        cols = ("game_id, competition, `group`, year, game_date, jersey, player_name, team, is_home, "
                "minutes, points, "
                "t2m, t2a, t3m, t3a, ftm, fta, reb, ast, stl, blk, to, pf, plus_minus, val")
        sel = (f"toUInt32(game_id), competition, `group`, toUInt16(year), game_date, toUInt8(jersey), player_name, "
               f"team, toUInt8(is_home), "
               f"toFloat32(minutes), toUInt16(points), toUInt8(t2m), toUInt8(t2a), "
               f"toUInt8(t3m), toUInt8(t3a), toUInt8(ftm), toUInt8(fta), toUInt8(reb), "
               f"toUInt8(ast), toUInt8(stl), toUInt8(blk), toUInt8(to), toUInt8(pf), "
               f"toInt16(plus_minus), toInt16(val)")
    elif table == "playbyplay":
        cols = ("game_id, competition, year, quarter, time, text, team, action, scoreA, scoreB")
        sel = (f"toUInt32(game_id), competition, toUInt16(year), toUInt8(quarter), time, text, "
               f"ifNull(toUInt8(team), 0), action, "
               f"ifNull(toUInt16(scoreA), 0), ifNull(toUInt16(scoreB), 0)")
    elif table == "tiros":
        cols = ("game_id, competition, year, quarter, time, player, team, made, x, y, "
                "shot_distance_m, zone, is_three, shot_points")
        sel = (f"toUInt32(game_id), competition, toUInt16(year), toUInt8(quarter), time, "
               f"toUInt8(player), toUInt8(team), toUInt8(made), toFloat64(x), toFloat64(y), "
               f"toFloat32(shot_distance_m), zone, toUInt8(is_three), toUInt8(shot_points)")
    elif table == "equipos_partido":
        cols = ("game_id, competition, year, team_id, team_name, points, t2m, t2a, t3m, t3a, ftm, fta, "
                "off_reb, def_reb, tot_reb, ast, stl, to, blk, pf")
        sel = (f"toUInt32(game_id), competition, toUInt16(year), toUInt32(team_id), team_name, "
               f"toUInt16(points), toUInt8(t2m), toUInt8(t2a), toUInt8(t3m), toUInt8(t3a), "
               f"toUInt8(ftm), toUInt8(fta), toUInt8(off_reb), toUInt8(def_reb), "
               f"toUInt8(tot_reb), toUInt8(ast), toUInt8(stl), toUInt8(to), toUInt8(blk), "
               f"toUInt8(pf)")
    elif table == "partidos":
        cols = ("game_id, competition, `group`, year, date, game_date, home_team, away_team, home_score, "
                "away_score, total_points, winner")
        sel = (f"toUInt32(game_id), competition, `group`, toUInt16(year), date, game_date, home_team, away_team, "
               f"toUInt16(home_score), toUInt16(away_score), toUInt16(total_points), winner")
    else:
        raise ValueError(f"Tabla desconocida: {table}")

    print(f"Cargando {table} ...")
    _query(f"TRUNCATE TABLE {ch_table}")
    _query(f"INSERT INTO {ch_table} ({cols}) SELECT {sel} FROM {src}")
    print(f"  {table}: {total} filas cargadas")


def main():
    table = sys.argv[1] if len(sys.argv) > 1 else None
    targets = [table] if table else list(TABLES)
    for t in targets:
        if t not in TABLES:
            print(f"Tabla desconocida: {t}. Válidas: {', '.join(TABLES)}")
            sys.exit(1)
        load(t)


if __name__ == "__main__":
    main()