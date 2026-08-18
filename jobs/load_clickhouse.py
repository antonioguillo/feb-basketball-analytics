"""Carga datos desde el staging de MinIO (parquet plano limpio) hacia ClickHouse.

El job Spark jobs/export_clickhouse.py materializa el estado lógico de las capas
silver/gold Delta en s3a://staging/<tabla> (overwrite), y este loader lee esos
Parquet vía la función s3() de ClickHouse.

Uso: python jobs/load_clickhouse.py [tabla]
      tabla: jugadores | playbyplay | tiros | equipos_partido | partidos
"""
import subprocess
import sys

CLICKHOUSE_CONTAINER = "feb-clickhouse"
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
    cmd = ["docker", "exec", CLICKHOUSE_CONTAINER, "clickhouse-client", "--query", sql]
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
        cols = ("game_id, year, game_date, jersey, player_name, minutes, points, "
                "t2m, t2a, t3m, t3a, ftm, fta, reb, ast, stl, blk, to, pf, plus_minus, val")
        sel = (f"toUInt32(game_id), toUInt16(year), game_date, toUInt8(jersey), player_name, "
               f"toFloat32(minutes), toUInt16(points), toUInt8(t2m), toUInt8(t2a), "
               f"toUInt8(t3m), toUInt8(t3a), toUInt8(ftm), toUInt8(fta), toUInt8(reb), "
               f"toUInt8(ast), toUInt8(stl), toUInt8(blk), toUInt8(to), toUInt8(pf), "
               f"toInt16(plus_minus), toInt16(val)")
    elif table == "playbyplay":
        cols = ("game_id, year, quarter, time, text, team, action, scoreA, scoreB")
        sel = (f"toUInt32(game_id), toUInt16(year), toUInt8(quarter), time, text, "
               f"ifNull(toUInt8(team), 0), action, "
               f"ifNull(toUInt16(scoreA), 0), ifNull(toUInt16(scoreB), 0)")
    elif table == "tiros":
        cols = ("game_id, year, quarter, time, player, team, made, x, y")
        sel = (f"toUInt32(game_id), toUInt16(year), toUInt8(quarter), time, "
               f"toUInt8(player), toUInt8(team), toUInt8(made), toFloat64(x), toFloat64(y)")
    elif table == "equipos_partido":
        cols = ("game_id, year, team_id, team_name, points, t2m, t2a, t3m, t3a, ftm, fta, "
                "off_reb, def_reb, tot_reb, ast, stl, to, blk, pf")
        sel = (f"toUInt32(game_id), toUInt16(year), toUInt32(team_id), team_name, "
               f"toUInt16(points), toUInt8(t2m), toUInt8(t2a), toUInt8(t3m), toUInt8(t3a), "
               f"toUInt8(ftm), toUInt8(fta), toUInt8(off_reb), toUInt8(def_reb), "
               f"toUInt8(tot_reb), toUInt8(ast), toUInt8(stl), toUInt8(to), toUInt8(blk), "
               f"toUInt8(pf)")
    elif table == "partidos":
        cols = ("game_id, year, date, home_score, away_score, total_points, winner")
        sel = (f"toUInt32(game_id), toUInt16(year), date, toUInt16(home_score), "
               f"toUInt16(away_score), toUInt16(total_points), winner")
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