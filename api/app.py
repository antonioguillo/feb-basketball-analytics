"""API REST de la aplicación de scouting FEB.

Sirve lo que consume el frontend leyendo de ClickHouse:

    GET /api/competitions                          qué hay cargado
    GET /api/dashboard?competition=&season=&group=&limit=&offset=
    GET /api/games?competition=&season=&group=
    GET /api/players/{slug}?competition=&season=&group=
    GET /api/teams?competition=&season=&group=
    GET /api/teams/{slug}?competition=&season=&group=
    GET /api/clutch?competition=&season=&group=&limit=&offset=
    GET /api/assist-network?competition=&season=&group=&team=
    GET /api/fouls?competition=&season=&group=&limit=&offset=

Las tablas `feb.*` no tienen id de jugador (el acta solo publica el nombre), así
que el identificador se deriva del nombre con `src.naming.player_slug` y se
resuelve contra un índice cacheado (`api.slugs`).

Arrancar:  uvicorn api:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from typing import Annotated, Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query

from . import clickhouse
from .context import _contexto
from .slugs import _resolve_player, _resolve_team
from .stats import LEADERS_LIMIT, LEADERS_MAX, MIN_GAMES, MIN_MINUTES, _leader, _num, _possessions, _ratio, _standings
from src.models import COMPETITIONS
from src.naming import display_name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await clickhouse.cerrar_cliente()


app = FastAPI(
    title="FEB Basketball Scouting API",
    description="API de scouting sobre los datos FEB procesados en ClickHouse",
    version="1.0.0",
    lifespan=lifespan,
)


# --- endpoints ---------------------------------------------------------------

@app.get("/api/health", tags=["health"])
async def health():
    try:
        await clickhouse.ch_query("SELECT 1")
        return {"status": "ok", "clickhouse": "ok"}
    except HTTPException as error:
        return {"status": "degraded", "clickhouse": error.detail}


@app.get("/api/competitions", tags=["catalogo"])
async def competitions():
    """Qué hay cargado: competiciones, temporadas y grupos con datos."""
    filas = await clickhouse.ch_query(
        "SELECT competition, year, groupUniqArray(`group`) AS grupos, count() AS partidos "
        "FROM feb.partidos GROUP BY competition, year ORDER BY competition, year DESC")
    return {"competitions": [
        {
            "competitionKey": f["competition"],
            "competition": (COMPETITIONS[f["competition"]].name
                            if f["competition"] in COMPETITIONS else f["competition"]),
            "seasonKey": str(f["year"]),
            "season": f"{f['year']}/{int(f['year']) + 1}",
            "groups": sorted(f.get("grupos") or []),
            "games": _num(f["partidos"], int),
        }
        for f in filas
    ]}


@app.get("/api/dashboard", tags=["dashboard"])
async def dashboard(
    competition: Annotated[Optional[str], Query(description="Clave de competición, p. ej. tercerafeb")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada, p. ej. 2025")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo, p. ej. E-A")] = None,
    limit: Annotated[int, Query(ge=1, le=LEADERS_MAX)] = LEADERS_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Resumen de la competición, ranking de líderes y últimos resultados."""
    limit = max(1, min(int(limit), LEADERS_MAX))
    offset = max(0, int(offset))

    ctx = await _contexto(competition, season, group)
    where, params = ctx["where"], ctx["params"]
    umbrales = {**params, "min_games": MIN_GAMES, "min_minutes": MIN_MINUTES}

    resumen = await clickhouse.ch_one(
        f"""
        SELECT
            (SELECT count() FROM feb.partidos WHERE {where})                 AS games,
            (SELECT uniqExact(team) FROM feb.jugadores WHERE {where})        AS teams,
            (SELECT uniqExact(player_name) FROM feb.jugadores WHERE {where}) AS players,
            (SELECT count() FROM feb.tiros WHERE game_id IN
                (SELECT game_id FROM feb.partidos WHERE {where}))            AS shots
        """,
        params,
    )

    total_lideres = await clickhouse.ch_one(
        f"""
        SELECT count() AS n FROM (
            SELECT player_name FROM feb.jugadores WHERE {where}
            GROUP BY player_name
            HAVING count() >= {{min_games:UInt8}} AND avg(minutes) >= {{min_minutes:UInt8}})
        """,
        umbrales,
    )

    filas_lideres = await clickhouse.ch_query(
        f"""
        SELECT
            player_name,
            argMax(team, game_date)    AS team,
            argMax(`group`, game_date) AS grupo,
            count()          AS games,
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
        WHERE {where}
        GROUP BY player_name
        HAVING games >= {{min_games:UInt8}} AND avg_min >= {{min_minutes:UInt8}}
        ORDER BY avg_val DESC
        LIMIT {{limit:UInt16}} OFFSET {{offset:UInt32}}
        """,
        {**umbrales, "limit": limit, "offset": offset},
    )

    filas_partidos = await clickhouse.ch_query(
        f"""
        SELECT game_id, date, home_team, away_team, home_score, away_score
        FROM feb.partidos WHERE {where}
        ORDER BY game_date DESC, game_id DESC LIMIT 8
        """,
        params,
    )

    return {
        "meta": ctx["meta"],
        "summary": {k: _num(resumen.get(k), int)
                    for k in ("games", "teams", "players", "shots")},
        "leaders": [_leader(f) for f in filas_lideres],
        "leadersTotal": _num(total_lideres.get("n"), int),
        "leadersOffset": offset,
        "recentGames": [
            {
                "gameId": _num(f["game_id"], int),
                "date": f["date"],
                "home": f["home_team"],
                "away": f["away_team"],
                "homeScore": _num(f["home_score"], int),
                "awayScore": _num(f["away_score"], int),
            }
            for f in filas_partidos
        ],
    }


@app.get("/api/players/{slug}", tags=["jugadores"])
async def player(
    slug: str,
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
):
    """Ficha de scouting: totales, ritmos, tiro por zonas, partidos y tiros."""
    ctx = await _contexto(competition, season, group)
    competition, season, group = ctx["competition"], ctx["season"], ctx["group"]
    year = int(season)

    name = await _resolve_player(slug, competition, season, group)
    where, params = clickhouse._filtro(competition, season, group)
    # Las consultas con JOIN necesitan el filtro cualificado con el alias.
    where_j, _ = clickhouse._filtro(competition, season, group, alias="j")
    params = {**params, "name": name}

    totals = await clickhouse.ch_one(
        f"""
        SELECT
            argMax(team, game_date) AS team,
            argMax(`group`, game_date) AS grupo,
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
        WHERE {where} AND player_name = {{name:String}}
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

    log_rows = await clickhouse.ch_query(
        f"""
        SELECT j.game_id AS game_id, p.date AS date, j.is_home AS is_home,
               p.home_team AS home_team, p.away_team AS away_team,
               p.home_score AS home_score, p.away_score AS away_score,
               j.minutes AS minutes, j.points AS points, j.reb AS reb,
               j.ast AS ast, j.val AS val
        FROM feb.jugadores AS j
        INNER JOIN feb.partidos AS p ON p.game_id = j.game_id
        WHERE {where_j} AND j.player_name = {{name:String}}
        ORDER BY p.game_date
        """,
        params,
    )

    # Los tiros se enlazan por dorsal y lado: la tabla de tiros identifica al
    # jugador por su número, no por su nombre (0 = local, 1 = visitante).
    shot_rows = await clickhouse.ch_query(
        f"""
        SELECT t.x AS x, t.y AS y, t.made AS made,
               t.shot_distance_m AS dist, t.zone AS zone
        FROM feb.tiros AS t
        INNER JOIN feb.jugadores AS j
            ON j.game_id = t.game_id AND j.jersey = t.player
           AND t.team = if(j.is_home, 0, 1)
        WHERE {where_j} AND j.player_name = {{name:String}}
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
        "group": totals.get("grupo"),
        "jersey": _num(totals["jersey"], int),
        "games": games,
        "meta": ctx["meta"],
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


@app.get("/api/games", tags=["dashboard"])
async def games(
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
):
    """Todos los partidos del filtro, más recientes primero. Sin paginar: un
    grupo entero son ~200 partidos, cabe de sobra en una respuesta — el
    frontend los agrupa por fecha para navegar jornada a jornada."""
    ctx = await _contexto(competition, season, group)
    where, params = ctx["where"], ctx["params"]
    filas = await clickhouse.ch_query(
        f"""
        SELECT game_id, date, home_team, away_team, home_score, away_score
        FROM feb.partidos WHERE {where}
        ORDER BY game_date DESC, game_id DESC
        """,
        params,
    )
    return {
        "meta": ctx["meta"],
        "games": [
            {
                "gameId": _num(f["game_id"], int),
                "date": f["date"],
                "home": f["home_team"],
                "away": f["away_team"],
                "homeScore": _num(f["home_score"], int),
                "awayScore": _num(f["away_score"], int),
            }
            for f in filas
        ],
    }


@app.get("/api/teams", tags=["equipos"])
async def teams(
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
):
    """Clasificación: equipos del grupo con récord y diferencial de puntos."""
    ctx = await _contexto(competition, season, group)
    tabla = await _standings(ctx["where"], ctx["params"])
    return {"meta": ctx["meta"], "standings": tabla}


@app.get("/api/teams/{slug}", tags=["equipos"])
async def team(
    slug: str,
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
):
    """Ficha de equipo: clasificación, plantilla con tiro por zona, y ritmo/eficiencia por partido."""
    ctx = await _contexto(competition, season, group)
    competition, season, group = ctx["competition"], ctx["season"], ctx["group"]

    name = await _resolve_team(slug, competition, season, group)
    tabla = await _standings(ctx["where"], ctx["params"])
    standing = next((row for row in tabla if row["team"] == name), None)
    if standing is None:
        raise HTTPException(status_code=404, detail=f"Equipo '{slug}' sin partidos en {season}")

    where, params = clickhouse._filtro(competition, season, group)
    params_team = {**params, "team": name}
    where_j, _ = clickhouse._filtro(competition, season, group, alias="j")

    # Plantilla: mismas columnas que el ranking de líderes (se reutiliza
    # _leader para el reparto de tiro), pero sin el mínimo de partidos/minutos
    # — una plantilla tiene que enseñar también a quien juega poco.
    filas_roster = await clickhouse.ch_query(
        f"""
        SELECT
            player_name,
            argMax(jersey, game_date) AS jersey,
            argMax(`group`, game_date) AS grupo,
            count() AS games,
            avg(minutes) AS avg_min, avg(points) AS avg_pts, avg(reb) AS avg_reb,
            avg(ast) AS avg_ast, avg(stl) AS avg_stl, avg(blk) AS avg_blk,
            avg(to) AS avg_to, avg(val) AS avg_val, avg(plus_minus) AS avg_plus_minus,
            sum(t2m) AS sum_t2m, sum(t2a) AS sum_t2a,
            sum(t3m) AS sum_t3m, sum(t3a) AS sum_t3a,
            sum(ftm) AS sum_ftm, sum(fta) AS sum_fta,
            sum(points) AS total_points
        FROM feb.jugadores
        WHERE {where} AND team = {{team:String}}
        GROUP BY player_name
        ORDER BY avg_val DESC
        """,
        params_team,
    )

    # Tiro por zona y por jugador: los tiros se enlazan por dorsal y lado,
    # igual que en la ficha de jugador (la tabla de tiros no identifica al
    # jugador por nombre).
    filas_zonas = await clickhouse.ch_query(
        f"""
        SELECT j.player_name AS player_name, t.zone AS zone,
               countIf(t.made = 1) AS made, count() AS att
        FROM feb.tiros AS t
        INNER JOIN feb.jugadores AS j
            ON j.game_id = t.game_id AND j.jersey = t.player AND t.team = if(j.is_home, 0, 1)
        WHERE {where_j} AND j.team = {{team:String}}
        GROUP BY player_name, zone
        """,
        params_team,
    )
    zonas_por_jugador: Dict[str, Dict[str, Any]] = {}
    for row in filas_zonas:
        made, att = _num(row["made"], int), _num(row["att"], int)
        zonas_por_jugador.setdefault(row["player_name"], {})[row["zone"]] = {
            "made": made, "att": att, "pct": _ratio(made, att),
        }

    roster = []
    for row in filas_roster:
        row["team"] = name   # el filtro ya garantiza que todas las filas son del mismo equipo
        entry = _leader(row)
        entry["jersey"] = _num(row["jersey"], int)
        entry["zones"] = zonas_por_jugador.get(row["player_name"], {})
        roster.append(entry)

    # Mapa de tiro agregado del equipo: mismos tiros que arriba, sin agrupar.
    filas_shots = await clickhouse.ch_query(
        f"""
        SELECT t.x AS x, t.y AS y, t.made AS made,
               t.shot_distance_m AS dist, t.zone AS zone
        FROM feb.tiros AS t
        INNER JOIN feb.jugadores AS j
            ON j.game_id = t.game_id AND j.jersey = t.player AND t.team = if(j.is_home, 0, 1)
        WHERE {where_j} AND j.team = {{team:String}}
        """,
        params_team,
    )
    shots = [
        {"x": _num(row["x"], float, 2), "y": _num(row["y"], float, 2),
         "made": _num(row["made"], int), "dist": _num(row["dist"], float, 2), "zone": row["zone"]}
        for row in filas_shots
    ]

    # Ritmo y eficiencia: posesiones estimadas (FGA - RO + PER + 0.44·TL) de
    # cada partido, comparando el box score propio con el del rival en el
    # mismo game_id — así el rating defensivo se mide contra las posesiones
    # reales del rival, no una aproximación con las propias.
    # `equipos_partido` no lleva columna de grupo (solo competition/year), así
    # que competición/temporada/grupo se filtran por `partidos`, con quien de
    # todos modos hay que cruzar para la fecha.
    where_p, params_p = clickhouse._filtro(competition, season, group, alias="p")
    filas_pace = await clickhouse.ch_query(
        f"""
        SELECT e.game_id AS game_id, p.date AS date, opp.team_name AS opponent,
               e.points AS pf, opp.points AS pa,
               e.t2a AS t2a_for, e.t3a AS t3a_for, e.off_reb AS orb_for,
               e.to AS tov_for, e.fta AS fta_for,
               opp.t2a AS t2a_opp, opp.t3a AS t3a_opp, opp.off_reb AS orb_opp,
               opp.to AS tov_opp, opp.fta AS fta_opp
        FROM feb.equipos_partido AS e
        INNER JOIN feb.equipos_partido AS opp ON opp.game_id = e.game_id
        INNER JOIN feb.partidos AS p ON p.game_id = e.game_id
        WHERE {where_p} AND e.team_name = {{team:String}} AND opp.team_name != e.team_name
        ORDER BY p.game_date
        """,
        {**params_p, "team": name},
    )
    pace_log = []
    for row in filas_pace:
        fga_for = (_num(row["t2a_for"], float) or 0) + (_num(row["t3a_for"], float) or 0)
        fga_opp = (_num(row["t2a_opp"], float) or 0) + (_num(row["t3a_opp"], float) or 0)
        poss_for = _possessions(fga_for, row["orb_for"], row["tov_for"], row["fta_for"])
        poss_opp = _possessions(fga_opp, row["orb_opp"], row["tov_opp"], row["fta_opp"])
        pf, pa = _num(row["pf"], float), _num(row["pa"], float)
        pace_log.append({
            "gameId": _num(row["game_id"], int),
            "date": row["date"],
            "opponent": row["opponent"],
            "pointsFor": _num(pf, int),
            "pointsAgainst": _num(pa, int),
            "won": pf > pa if pf is not None and pa is not None else None,
            "possessions": round((poss_for + poss_opp) / 2, 1) if poss_for and poss_opp else None,
            "ortg": round(pf / poss_for * 100, 1) if poss_for else None,
            "drtg": round(pa / poss_opp * 100, 1) if poss_opp else None,
        })

    def _avg(key: str) -> Optional[float]:
        values = [g[key] for g in pace_log if g[key] is not None]
        return round(sum(values) / len(values), 1) if values else None

    avg_ortg, avg_drtg = _avg("ortg"), _avg("drtg")
    pace = {
        "avgPossessions": _avg("possessions"),
        "avgOrtg": avg_ortg,
        "avgDrtg": avg_drtg,
        "avgNetRtg": round(avg_ortg - avg_drtg, 1) if avg_ortg is not None and avg_drtg is not None else None,
    }

    return {
        "slug": slug,
        "team": name,
        "group": roster[0]["group"] if roster else group,
        "meta": ctx["meta"],
        "standing": standing,
        "pace": pace,
        "gameLog": pace_log,
        "roster": roster,
        "shots": shots,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
