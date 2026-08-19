"""API REST de la aplicación de scouting FEB.

Sirve los dos endpoints que consume el frontend leyendo de ClickHouse:

    GET /api/dashboard?season=&group=   resumen del grupo, líderes y resultados
    GET /api/players/{slug}             ficha completa de un jugador

La forma de las respuestas es la que documenta `frontend/src/api/client.js`.
Las tablas `feb.*` no tienen id de jugador (el acta solo publica el nombre),
así que el identificador se deriva del nombre con `src.naming.player_slug`.

Arrancar:  uvicorn api:app --reload --port 8000
"""
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query

from src.naming import display_name, player_slug

app = FastAPI(
    title="FEB Basketball Scouting API",
    description="API de scouting sobre los datos FEB procesados en ClickHouse",
    version="1.0.0",
)

CH_URL = os.getenv("CH_URL", "http://localhost:8123")
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "feb")
CH_TIMEOUT = float(os.getenv("CH_TIMEOUT", "30"))

# Contexto de la competición que se está sirviendo. Hoy el pipeline carga un
# grupo cada vez; cuando cargue varios saldrá de la propia tabla.
COMPETITION = {
    "competition": "Tercera FEB",
    "competitionKey": "tercerafeb",
    "group": "Liga Regular E-A",
    "groupKey": "E-A",
}

# Umbrales del ranking de líderes: sin un mínimo, cualquiera con un buen
# partido suelto encabezaría la tabla.
MIN_GAMES = 6
MIN_MINUTES = 15


async def ch_query(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Ejecuta SQL en ClickHouse y devuelve las filas como diccionarios.

    Los valores van como parámetros de ClickHouse (`{nombre:Tipo}`), nunca
    interpolados en el SQL.
    """
    query = {"query": sql + " FORMAT JSON", "default_format": "JSON"}
    for key, value in (params or {}).items():
        query[f"param_{key}"] = str(value)

    # Sin contraseña, la imagen oficial de ClickHouse limita el usuario default
    # a conexiones desde dentro del contenedor y responde a cualquier petición
    # del host con un "Authentication failed" que despista. Por eso el compose
    # fija una contraseña; aquí solo se manda la cabecera si existe.
    auth = (CH_USER, CH_PASSWORD) if CH_PASSWORD else None
    try:
        async with httpx.AsyncClient(timeout=CH_TIMEOUT) as client:
            response = await client.post(CH_URL, params=query, auth=auth)
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail=f"ClickHouse inaccesible: {error}") from error

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ClickHouse: {response.text[:500]}")
    return response.json().get("data", [])


async def ch_one(sql: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rows = await ch_query(sql, params)
    return rows[0] if rows else {}


def _num(value, cast=float, digits: Optional[int] = None):
    """ClickHouse devuelve los enteros de 64 bits como texto en JSON."""
    if value is None:
        return None
    try:
        result = cast(value)
    except (TypeError, ValueError):
        return None
    return round(result, digits) if digits is not None and isinstance(result, float) else result


def _ratio(made, attempted, digits: int = 4):
    """None si no hubo intentos: un 0/0 no es un 0 %."""
    made, attempted = _num(made, float), _num(attempted, float)
    if not attempted:
        return None
    return round(made / attempted, digits)


# --- endpoints ---------------------------------------------------------------

@app.get("/api/health", tags=["health"])
async def health():
    try:
        await ch_query("SELECT 1")
        return {"status": "ok", "clickhouse": "ok"}
    except HTTPException as error:
        return {"status": "degraded", "clickhouse": error.detail}


@app.get("/api/dashboard", tags=["dashboard"])
async def dashboard(
    season: Optional[str] = Query(None, description="Año de inicio de temporada, p. ej. 2025"),
    group: Optional[str] = Query(None, description="Clave de grupo, p. ej. E-A"),
):
    """Resumen del grupo, ranking de líderes y últimos resultados."""
    if season is None:
        # La temporada con más partidos, no la más reciente: el lago puede tener
        # unos pocos encuentros sueltos de una temporada que aún no ha empezado,
        # y abrir el dashboard ahí daría un ranking vacío.
        latest = await ch_one(
            "SELECT year FROM feb.partidos GROUP BY year "
            "ORDER BY count() DESC, year DESC LIMIT 1")
        season = str(latest.get("year") or "")
        if not season:
            raise HTTPException(status_code=404, detail="No hay partidos cargados")
    params = {"year": int(season)}

    summary = await ch_one(
        """
        SELECT
            (SELECT count() FROM feb.partidos WHERE year = {year:UInt16})   AS games,
            (SELECT uniqExact(team) FROM feb.jugadores WHERE year = {year:UInt16}) AS teams,
            (SELECT uniqExact(player_name) FROM feb.jugadores WHERE year = {year:UInt16}) AS players,
            (SELECT count() FROM feb.tiros WHERE year = {year:UInt16})      AS shots
        """,
        params,
    )

    journeys = await ch_one(
        "SELECT uniqExact(game_date) AS journeys FROM feb.partidos WHERE year = {year:UInt16}",
        params,
    )

    leader_rows = await ch_query(
        """
        SELECT
            player_name,
            argMax(team, game_date)              AS team,
            count()                              AS games,
            avg(minutes)     AS avg_min,
            avg(points)      AS avg_pts,
            avg(reb)         AS avg_reb,
            avg(ast)         AS avg_ast,
            avg(stl)         AS avg_stl,
            avg(blk)         AS avg_blk,
            avg(to)          AS avg_to,
            avg(val)         AS avg_val,
            avg(plus_minus)  AS avg_plus_minus,
            sum(t2m) AS sum_t2m, sum(t2a) AS sum_t2a,
            sum(t3m) AS sum_t3m, sum(t3a) AS sum_t3a,
            sum(ftm) AS sum_ftm, sum(fta) AS sum_fta,
            sum(points) AS total_points
        FROM feb.jugadores
        WHERE year = {year:UInt16}
        GROUP BY player_name
        HAVING games >= {min_games:UInt8} AND avg_min >= {min_minutes:UInt8}
        ORDER BY avg_val DESC
        """,
        {**params, "min_games": MIN_GAMES, "min_minutes": MIN_MINUTES},
    )

    recent_rows = await ch_query(
        """
        SELECT game_id, date, home_team, away_team, home_score, away_score
        FROM feb.partidos
        WHERE year = {year:UInt16}
        ORDER BY game_date DESC, game_id DESC
        LIMIT 8
        """,
        params,
    )

    total_games = await ch_one(
        "SELECT count() AS n FROM feb.partidos WHERE year = {year:UInt16}", params)

    return {
        "meta": {
            **COMPETITION,
            "season": f"{season}/{int(season) + 1}",
            "seasonKey": season,
            "group": group or COMPETITION["group"],
            "journeys": _num(journeys.get("journeys"), int),
            "groupTotalGames": _num(total_games.get("n"), int),
            "source": "feb.es",
        },
        "summary": {key: _num(summary.get(key), int) for key in ("games", "teams", "players", "shots")},
        "leaders": [_leader(row) for row in leader_rows],
        "recentGames": [
            {
                "gameId": _num(row["game_id"], int),
                "date": row["date"],
                "home": row["home_team"],
                "away": row["away_team"],
                "homeScore": _num(row["home_score"], int),
                "awayScore": _num(row["away_score"], int),
            }
            for row in recent_rows
        ],
    }


def _leader(row: Dict[str, Any]) -> Dict[str, Any]:
    fgm = _num(row["sum_t2m"], float) + _num(row["sum_t3m"], float)
    fga = _num(row["sum_t2a"], float) + _num(row["sum_t3a"], float)
    fta = _num(row["sum_fta"], float)
    return {
        "slug": player_slug(row["player_name"]),
        "name": display_name(row["player_name"]),
        "team": row["team"],
        "games": _num(row["games"], int),
        "perGame": {
            "min": _num(row["avg_min"], float, 1),
            "pts": _num(row["avg_pts"], float, 1),
            "reb": _num(row["avg_reb"], float, 1),
            "ast": _num(row["avg_ast"], float, 1),
            "stl": _num(row["avg_stl"], float, 1),
            "blk": _num(row["avg_blk"], float, 1),
            "to": _num(row["avg_to"], float, 1),
            "val": _num(row["avg_val"], float, 1),
            "plusMinus": _num(row["avg_plus_minus"], float, 1),
        },
        "shooting": {
            "t2": _ratio(row["sum_t2m"], row["sum_t2a"]),
            "t3": _ratio(row["sum_t3m"], row["sum_t3a"]),
            "ft": _ratio(row["sum_ftm"], row["sum_fta"]),
            "fg": _ratio(fgm, fga),
            "efg": round((fgm + 0.5 * _num(row["sum_t3m"], float)) / fga, 4) if fga else None,
            "ts": (round(_num(row["total_points"], float) / (2 * (fga + 0.44 * fta)), 4)
                   if (fga + fta) else None),
        },
    }


async def _resolve_player(slug: str, year: Optional[int]) -> str:
    """Devuelve el nombre del acta que corresponde a un slug.

    El slug se deriva del nombre, así que hay que recorrer los nombres del
    grupo; son unos cientos y ClickHouse los resuelve en una sola consulta.
    """
    where = "WHERE year = {year:UInt16}" if year else ""
    rows = await ch_query(
        f"SELECT DISTINCT player_name FROM feb.jugadores {where}",
        {"year": year} if year else None,
    )
    for row in rows:
        if player_slug(row["player_name"]) == slug:
            return row["player_name"]
    raise HTTPException(status_code=404, detail=f"Jugador '{slug}' no encontrado")


@app.get("/api/players/{slug}", tags=["jugadores"])
async def player(slug: str, season: Optional[str] = Query(None)):
    """Ficha de scouting: totales, ritmos, tiro por zonas, partidos y tiros."""
    year = int(season) if season else None
    if year is None:
        latest = await ch_one("SELECT max(year) AS year FROM feb.jugadores")
        year = _num(latest.get("year"), int)
        if year is None:
            raise HTTPException(status_code=404, detail="No hay jugadores cargados")

    name = await _resolve_player(slug, year)
    params = {"year": year, "name": name}

    totals = await ch_one(
        """
        SELECT
            argMax(team, game_date) AS team,
            argMax(jersey, game_date) AS jersey,
            count() AS games,
            sum(minutes) AS sum_min, sum(points) AS sum_pts, sum(reb) AS sum_reb,
            sum(ast) AS sum_ast, sum(stl) AS sum_stl, sum(blk) AS sum_blk,
            sum(to) AS sum_to, sum(pf) AS sum_pf, sum(val) AS sum_val,
            sum(t2m) AS sum_t2m, sum(t2a) AS sum_t2a,
            sum(t3m) AS sum_t3m, sum(t3a) AS sum_t3a,
            sum(ftm) AS sum_ftm, sum(fta) AS sum_fta,
            avg(plus_minus) AS avg_plus_minus,
            max(points) AS best_pts, max(reb) AS best_reb,
            max(ast) AS best_ast, max(val) AS best_val
        FROM feb.jugadores
        WHERE year = {year:UInt16} AND player_name = {name:String}
        """,
        params,
    )
    if not totals or not _num(totals.get("games"), int):
        raise HTTPException(status_code=404, detail=f"Jugador '{slug}' sin partidos en {year}")

    games = _num(totals["games"], int)
    minutes = _num(totals["sum_min"], float) or 0.0
    fgm = _num(totals["sum_t2m"], float) + _num(totals["sum_t3m"], float)
    fga = _num(totals["sum_t2a"], float) + _num(totals["sum_t3a"], float)
    fta = _num(totals["sum_fta"], float)
    points = _num(totals["sum_pts"], float)

    log_rows = await ch_query(
        """
        SELECT j.game_id AS game_id, p.date AS date, j.is_home AS is_home,
               p.home_team AS home_team, p.away_team AS away_team,
               p.home_score AS home_score, p.away_score AS away_score,
               j.minutes AS minutes, j.points AS points, j.reb AS reb,
               j.ast AS ast, j.val AS val
        FROM feb.jugadores AS j
        INNER JOIN feb.partidos AS p ON p.game_id = j.game_id
        WHERE j.year = {year:UInt16} AND j.player_name = {name:String}
        ORDER BY p.game_date
        """,
        params,
    )

    # Los tiros se enlazan por dorsal y lado: la tabla de tiros identifica al
    # jugador por su número, no por su nombre (0 = local, 1 = visitante).
    shot_rows = await ch_query(
        """
        SELECT t.x AS x, t.y AS y, t.made AS made,
               t.shot_distance_m AS dist, t.zone AS zone
        FROM feb.tiros AS t
        INNER JOIN feb.jugadores AS j
            ON j.game_id = t.game_id AND j.jersey = t.player
           AND t.team = if(j.is_home, 0, 1)
        WHERE j.year = {year:UInt16} AND j.player_name = {name:String}
        """,
        params,
    )

    zones: Dict[str, Dict[str, Any]] = {}
    for row in shot_rows:
        bucket = zones.setdefault(row["zone"], {"made": 0, "att": 0})
        bucket["att"] += 1
        bucket["made"] += _num(row["made"], int) or 0
    for bucket in zones.values():
        bucket["pct"] = _ratio(bucket["made"], bucket["att"])

    def per36(total):
        value = _num(total, float)
        return round(value / minutes * 36, 1) if minutes else None

    return {
        "slug": slug,
        "name": display_name(name),
        "rawName": name,
        "team": totals["team"],
        "jersey": _num(totals["jersey"], int),
        "games": games,
        "meta": {**COMPETITION, "season": f"{year}/{year + 1}", "seasonKey": str(year)},
        "totals": {key: _num(totals["sum_" + key], float, 1) for key in
                   ("min", "pts", "reb", "ast", "stl", "blk", "to", "pf", "val",
                    "t2m", "t2a", "t3m", "t3a", "ftm", "fta")},
        "perGame": {
            "min": round(minutes / games, 1),
            "pts": round(points / games, 1),
            "reb": round(_num(totals["sum_reb"], float) / games, 1),
            "ast": round(_num(totals["sum_ast"], float) / games, 1),
            "stl": round(_num(totals["sum_stl"], float) / games, 1),
            "blk": round(_num(totals["sum_blk"], float) / games, 1),
            "to": round(_num(totals["sum_to"], float) / games, 1),
            "val": round(_num(totals["sum_val"], float) / games, 1),
            "plusMinus": _num(totals["avg_plus_minus"], float, 1),
        },
        "shooting": {
            "t2": _ratio(totals["sum_t2m"], totals["sum_t2a"]),
            "t3": _ratio(totals["sum_t3m"], totals["sum_t3a"]),
            "ft": _ratio(totals["sum_ftm"], totals["sum_fta"]),
            "fg": _ratio(fgm, fga),
            "efg": round((fgm + 0.5 * _num(totals["sum_t3m"], float)) / fga, 4) if fga else None,
            "ts": round(points / (2 * (fga + 0.44 * fta)), 4) if (fga + fta) else None,
        },
        "per36": {"pts": per36(totals["sum_pts"]), "reb": per36(totals["sum_reb"]),
                  "ast": per36(totals["sum_ast"])},
        "zones": zones,
        "bests": {key: _num(totals[f"best_{key}"], int) for key in ("pts", "reb", "ast", "val")},
        "gameLog": [
            {
                "gameId": _num(row["game_id"], int),
                "date": row["date"],
                "home": bool(_num(row["is_home"], int)),
                "opponent": row["away_team"] if _num(row["is_home"], int) else row["home_team"],
                "score": f"{_num(row['home_score'], int)}-{_num(row['away_score'], int)}",
                "won": (_num(row["home_score"], int) > _num(row["away_score"], int))
                       if _num(row["is_home"], int)
                       else (_num(row["away_score"], int) > _num(row["home_score"], int)),
                "min": _num(row["minutes"], float, 0),
                "pts": _num(row["points"], int),
                "reb": _num(row["reb"], int),
                "ast": _num(row["ast"], int),
                "val": _num(row["val"], int),
            }
            for row in log_rows
        ],
        "shots": [
            {
                "x": _num(row["x"], float, 2),
                "y": _num(row["y"], float, 2),
                "made": _num(row["made"], int),
                "dist": _num(row["dist"], float, 2),
                "zone": row["zone"],
            }
            for row in shot_rows
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
