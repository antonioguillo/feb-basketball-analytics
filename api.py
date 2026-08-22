"""API REST de la aplicación de scouting FEB.

Sirve lo que consume el frontend leyendo de ClickHouse:

    GET /api/competitions                          qué hay cargado
    GET /api/dashboard?competition=&season=&group=&limit=&offset=
    GET /api/players/{slug}?competition=&season=&group=
    GET /api/teams?competition=&season=&group=
    GET /api/teams/{slug}?competition=&season=&group=
    GET /api/clutch?competition=&season=&group=&limit=&offset=
    GET /api/assist-network?competition=&season=&group=&team=
    GET /api/fouls?competition=&season=&group=&limit=&offset=

Toda respuesta habla de UNA competición: mezclar en un mismo ranking la Tercera
FEB masculina con la LF Endesa no significa nada. Si no se pide ninguna se elige
la que más partidos tiene y se dice cuál en `meta`.

Las tablas `feb.*` no tienen id de jugador (el acta solo publica el nombre), así
que el identificador se deriva del nombre con `src.naming.player_slug` y se
resuelve contra un índice cacheado.

Arrancar:  uvicorn api:app --reload --port 8000
"""
import asyncio
import os
from contextlib import asynccontextmanager
import time
from typing import Annotated, Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query

from src.models import COMPETITIONS
from src.naming import display_name, player_slug, team_slug

@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()


app = FastAPI(
    title="FEB Basketball Scouting API",
    description="API de scouting sobre los datos FEB procesados en ClickHouse",
    version="1.0.0",
    lifespan=lifespan,
)

CH_URL = os.getenv("CH_URL", "http://localhost:8123")
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "feb")
CH_TIMEOUT = float(os.getenv("CH_TIMEOUT", "30"))

# Umbrales del ranking de líderes: sin un mínimo, cualquiera con un buen
# partido suelto encabezaría la tabla.
MIN_GAMES = 6
MIN_MINUTES = 15

# Página de líderes por defecto. Sin tope, una liga entera devuelve cientos de
# jugadores en una sola respuesta.
LEADERS_LIMIT = 50
LEADERS_MAX = 500

# Cuánto se guarda el índice de slugs. Las tablas solo cambian cuando se
# recarga el pipeline, así que un cuarto de hora es conservador.
SLUG_CACHE_TTL = float(os.getenv("SLUG_CACHE_TTL", "900"))

# "Clutch": últimos 5 minutos del último cuarto (o cualquier prórroga) con el
# marcador a 5 puntos o menos en ese instante — la definición habitual de
# tiempo/marcador ajustado, no solo el resultado final del partido.
CLUTCH_SECONDS = 300
CLUTCH_MARGIN = 5
MIN_CLUTCH_GAMES = 2

# Un jugador queda eliminado por faltas a las 5 personales (reglas FIBA).
FOUL_OUT_THRESHOLD = 5
MIN_FOUL_GAMES = 3


def _filtro(competition: Optional[str], season: Optional[str], group: Optional[str],
            alias: str = "") -> tuple:
    """Construye el WHERE común y sus parámetros.

    Devuelve (sql, params). El alias permite usarlo en consultas con JOIN.
    """
    prefijo = f"{alias}." if alias else ""
    condiciones, params = [], {}
    if season:
        condiciones.append(f"{prefijo}year = {{year:UInt16}}")
        params["year"] = int(season)
    if competition:
        condiciones.append(f"{prefijo}competition = {{competition:String}}")
        params["competition"] = competition
    if group:
        condiciones.append(f"{prefijo}`group` = {{group:String}}")
        params["group"] = group
    return (" AND ".join(condiciones) or "1", params)


# Un único cliente para todo el proceso. Crear uno por consulta costaba 838 ms
# frente a 8 ms reutilizándolo: la ficha de un jugador lanza seis consultas, así
# que era la diferencia entre 5 segundos y medio segundo.
_http_client: Optional[httpx.AsyncClient] = None
_http_loop = None
_http_lock = asyncio.Lock()


def _hay_que_crear_cliente() -> bool:
    """El pool de conexiones queda atado al bucle de eventos que lo creó.

    Bajo uvicorn hay un único bucle y esto nunca se cumple, pero un script o un
    test que llame a `asyncio.run` varias veces abre un bucle nuevo cada vez y
    reutilizar el cliente daría "Event loop is closed".
    """
    if _http_client is None or _http_client.is_closed:
        return True
    return _http_loop is not asyncio.get_running_loop()


async def _cliente() -> httpx.AsyncClient:
    global _http_client, _http_loop
    if _hay_que_crear_cliente():
        async with _http_lock:
            if _hay_que_crear_cliente():
                if _http_client is not None and not _http_client.is_closed:
                    try:
                        await _http_client.aclose()
                    except RuntimeError:
                        pass       # su bucle ya no existe; no hay nada que cerrar
                _http_loop = asyncio.get_running_loop()
                # Sin contraseña, la imagen oficial de ClickHouse limita el
                # usuario default a conexiones desde dentro del contenedor y
                # responde con un "Authentication failed" que despista. Por eso
                # el compose fija una; aquí solo se manda si existe.
                _http_client = httpx.AsyncClient(
                    timeout=CH_TIMEOUT,
                    auth=(CH_USER, CH_PASSWORD) if CH_PASSWORD else None,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
    return _http_client


async def ch_query(sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Ejecuta SQL en ClickHouse y devuelve las filas como diccionarios.

    Los valores van como parámetros de ClickHouse (`{nombre:Tipo}`), nunca
    interpolados en el SQL.
    """
    query = {"query": sql + " FORMAT JSON", "default_format": "JSON"}
    for key, value in (params or {}).items():
        query[f"param_{key}"] = str(value)

    try:
        response = await (await _cliente()).post(CH_URL, params=query)
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



# --- índice de slugs -------------------------------------------------------
# El acta no publica id de jugador, así que el identificador se deriva del
# nombre. Resolverlo recorriendo todos los nombres en cada petición costaba
# cientos de milisegundos y crece con el histórico, de modo que el mapa
# slug -> nombre se construye una vez y se guarda.
_slug_cache: Dict[tuple, tuple] = {}
_slug_lock = asyncio.Lock()


async def _indice_slugs(competition: Optional[str], season: Optional[str],
                        group: Optional[str]) -> Dict[str, str]:
    clave = (competition, season, group)
    guardado = _slug_cache.get(clave)
    if guardado and (time.monotonic() - guardado[0]) < SLUG_CACHE_TTL:
        return guardado[1]

    async with _slug_lock:
        # Otra petición pudo construirlo mientras se esperaba el turno.
        guardado = _slug_cache.get(clave)
        if guardado and (time.monotonic() - guardado[0]) < SLUG_CACHE_TTL:
            return guardado[1]

        where, params = _filtro(competition, season, group)
        filas = await ch_query(
            f"SELECT DISTINCT player_name FROM feb.jugadores WHERE {where}", params)
        indice = {player_slug(f["player_name"]): f["player_name"] for f in filas}
        _slug_cache[clave] = (time.monotonic(), indice)
        return indice


def invalidar_indice_slugs():
    """Para los tests y para cuando se recarga el pipeline."""
    _slug_cache.clear()
    _team_slug_cache.clear()


# --- índice de equipos -------------------------------------------------------
# Mismo mecanismo que el índice de jugadores: el acta no trae id de equipo, así
# que el identificador se deriva del nombre y se cachea por competición/
# temporada/grupo.
_team_slug_cache: Dict[tuple, tuple] = {}
_team_slug_lock = asyncio.Lock()


async def _indice_equipos(competition: Optional[str], season: Optional[str],
                          group: Optional[str]) -> Dict[str, str]:
    clave = (competition, season, group)
    guardado = _team_slug_cache.get(clave)
    if guardado and (time.monotonic() - guardado[0]) < SLUG_CACHE_TTL:
        return guardado[1]

    async with _team_slug_lock:
        guardado = _team_slug_cache.get(clave)
        if guardado and (time.monotonic() - guardado[0]) < SLUG_CACHE_TTL:
            return guardado[1]

        where, params = _filtro(competition, season, group)
        filas = await ch_query(
            f"SELECT DISTINCT team FROM feb.jugadores WHERE {where}", params)
        indice = {team_slug(f["team"]): f["team"] for f in filas}
        _team_slug_cache[clave] = (time.monotonic(), indice)
        return indice


async def _resolve_team(slug: str, competition: Optional[str], season: Optional[str],
                        group: Optional[str]) -> str:
    indice = await _indice_equipos(competition, season, group)
    name = indice.get(slug)
    if name is None:
        raise HTTPException(status_code=404, detail=f"Equipo '{slug}' no encontrado")
    return name


async def _standings(where: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Clasificación: un equipo puede ser local o visitante, así que se cuenta
    desde ambos lados con una UNION y se suma por nombre de equipo."""
    filas = await ch_query(
        f"""
        SELECT team, count() AS games, sum(win) AS wins,
               sum(pf) AS points_for, sum(pa) AS points_against
        FROM (
            SELECT home_team AS team, home_score AS pf, away_score AS pa,
                   if(home_score > away_score, 1, 0) AS win
            FROM feb.partidos WHERE {where}
            UNION ALL
            SELECT away_team AS team, away_score AS pf, home_score AS pa,
                   if(away_score > home_score, 1, 0) AS win
            FROM feb.partidos WHERE {where}
        )
        GROUP BY team
        ORDER BY wins DESC, (points_for - points_against) DESC
        """,
        params,
    )
    tabla = []
    for index, row in enumerate(filas, 1):
        games = _num(row["games"], int)
        wins = _num(row["wins"], int)
        pf = _num(row["points_for"], int)
        pa = _num(row["points_against"], int)
        tabla.append({
            "rank": index,
            "teamKey": team_slug(row["team"]),
            "team": row["team"],
            "games": games,
            "wins": wins,
            "losses": games - wins,
            "pointsFor": pf,
            "pointsAgainst": pa,
            "diff": pf - pa,
        })
    return tabla


# --- endpoints ---------------------------------------------------------------

@app.get("/api/health", tags=["health"])
async def health():
    try:
        await ch_query("SELECT 1")
        return {"status": "ok", "clickhouse": "ok"}
    except HTTPException as error:
        return {"status": "degraded", "clickhouse": error.detail}


async def _contexto(competition: Optional[str], season: Optional[str],
                    group: Optional[str]) -> Dict[str, Any]:
    """Resuelve competición, temporada y grupo, y describe lo que se sirve.

    Una respuesta habla siempre de UNA competición: mezclar la Tercera FEB
    masculina con la LF Endesa en un mismo ranking no significa nada. Si no se
    pide ninguna se elige la que más partidos tiene y se dice cuál en `meta`.
    """
    if season is None:
        fila = await ch_one("SELECT year FROM feb.partidos GROUP BY year "
                            "ORDER BY count() DESC, year DESC LIMIT 1")
        season = str(fila.get("year") or "")
        if not season:
            raise HTTPException(status_code=404, detail="No hay partidos cargados")

    if competition is None:
        fila = await ch_one(
            "SELECT competition FROM feb.partidos WHERE year = {year:UInt16} "
            "GROUP BY competition ORDER BY count() DESC LIMIT 1",
            {"year": int(season)})
        competition = fila.get("competition")
        if not competition:
            raise HTTPException(status_code=404,
                                detail=f"No hay partidos en la temporada {season}")

    where, params = _filtro(competition, season, group)
    resumen = await ch_one(
        f"SELECT count() AS partidos, uniqExact(game_date) AS fechas, "
        f"       groupUniqArray(`group`) AS lista "
        f"FROM feb.partidos WHERE {where}", params)

    if not _num(resumen.get("partidos"), int):
        detalle = f"Sin datos para {competition} {season}"
        raise HTTPException(status_code=404,
                            detail=detalle + (f" grupo {group}" if group else ""))

    grupos = resumen.get("lista") or []
    nombre = COMPETITIONS[competition].name if competition in COMPETITIONS else competition

    return {
        "competition": competition,
        "season": season,
        "group": group,
        "where": where,
        "params": params,
        "meta": {
            "competition": nombre,
            "competitionKey": competition,
            "season": f"{season}/{int(season) + 1}",
            "seasonKey": season,
            # Sin grupo concreto se anuncia cuántos entran, para que la cabecera
            # no prometa un recorte que no se ha hecho.
            "group": group or (grupos[0] if len(grupos) == 1 else f"{len(grupos)} grupos"),
            "groupKey": group,
            "groups": sorted(grupos),
            # Fechas distintas con partidos, no jornadas: la jornada no viene en
            # el acta, y con varios grupos cada uno juega en días distintos.
            "matchDays": _num(resumen.get("fechas"), int),
            "groupTotalGames": _num(resumen.get("partidos"), int),
            "source": "feb.es",
        },
    }


@app.get("/api/competitions", tags=["catalogo"])
async def competitions():
    """Qué hay cargado: competiciones, temporadas y grupos con datos."""
    filas = await ch_query(
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

    resumen = await ch_one(
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

    total_lideres = await ch_one(
        f"""
        SELECT count() AS n FROM (
            SELECT player_name FROM feb.jugadores WHERE {where}
            GROUP BY player_name
            HAVING count() >= {{min_games:UInt8}} AND avg(minutes) >= {{min_minutes:UInt8}})
        """,
        umbrales,
    )

    filas_lideres = await ch_query(
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

    filas_partidos = await ch_query(
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


def _leader(row: Dict[str, Any]) -> Dict[str, Any]:
    fgm = _num(row["sum_t2m"], float) + _num(row["sum_t3m"], float)
    fga = _num(row["sum_t2a"], float) + _num(row["sum_t3a"], float)
    fta = _num(row["sum_fta"], float)
    return {
        "slug": player_slug(row["player_name"]),
        "name": display_name(row["player_name"]),
        "team": row["team"],
        "group": row.get("grupo"),
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


async def _resolve_player(slug: str, competition: Optional[str], season: Optional[str],
                          group: Optional[str]) -> str:
    """Nombre del acta que corresponde a un slug, vía el índice cacheado."""
    indice = await _indice_slugs(competition, season, group)
    nombre = indice.get(slug)
    if nombre is None:
        raise HTTPException(status_code=404, detail=f"Jugador '{slug}' no encontrado")
    return nombre


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
    where, params = _filtro(competition, season, group)
    # Las consultas con JOIN necesitan el filtro cualificado con el alias.
    where_j, _ = _filtro(competition, season, group, alias="j")
    params = {**params, "name": name}

    totals = await ch_one(
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

    log_rows = await ch_query(
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
    shot_rows = await ch_query(
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


def _possessions(fga, orb, tov, fta) -> Optional[float]:
    fga, orb, tov, fta = _num(fga, float), _num(orb, float), _num(tov, float), _num(fta, float)
    if fga is None:
        return None
    return fga - (orb or 0) + (tov or 0) + 0.44 * (fta or 0)


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

    where, params = _filtro(competition, season, group)
    params_team = {**params, "team": name}
    where_j, _ = _filtro(competition, season, group, alias="j")

    # Plantilla: mismas columnas que el ranking de líderes (se reutiliza
    # _leader para el reparto de tiro), pero sin el mínimo de partidos/minutos
    # — una plantilla tiene que enseñar también a quien juega poco.
    filas_roster = await ch_query(
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
    filas_zonas = await ch_query(
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
    filas_shots = await ch_query(
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
    where_p, params_p = _filtro(competition, season, group, alias="p")
    filas_pace = await ch_query(
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


# --- clutch --------------------------------------------------------------
# `feb.playbyplay` solo trae el marcador (scoreA/scoreB) en las jugadas que
# anotan; el resto lo deja a 0. Como el marcador nunca baja, el máximo
# acumulado hasta cada jugada (ventana ORDER BY tiempo real de partido) es el
# marcador vigente en ese instante — evita tener que rellenar a mano.
_CLUTCH_SCORED_CTE = """
    WITH scored AS (
        SELECT
            pbp.game_id AS game_id,
            pbp.quarter AS quarter,
            pbp.action AS action,
            pbp.made AS made,
            pbp.shot_value AS shot_value,
            pbp.player_name AS player_name,
            if(pbp.team = 1, p.home_team, p.away_team) AS team,
            (toUInt32OrZero(splitByChar(':', pbp.time)[1]) * 60
             + toUInt32OrZero(splitByChar(':', pbp.time)[2])) AS secs_left,
            max(pbp.scoreA) OVER (
                PARTITION BY pbp.game_id
                ORDER BY pbp.quarter,
                    600 - (toUInt32OrZero(splitByChar(':', pbp.time)[1]) * 60
                           + toUInt32OrZero(splitByChar(':', pbp.time)[2]))
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS score_home,
            max(pbp.scoreB) OVER (
                PARTITION BY pbp.game_id
                ORDER BY pbp.quarter,
                    600 - (toUInt32OrZero(splitByChar(':', pbp.time)[1]) * 60
                           + toUInt32OrZero(splitByChar(':', pbp.time)[2]))
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS score_away
        FROM feb.playbyplay AS pbp
        INNER JOIN feb.partidos AS p ON p.game_id = pbp.game_id
        WHERE {where_p}
    ),
    clutch AS (
        SELECT * FROM scored
        WHERE player_name IS NOT NULL
          AND (quarter > 4 OR (quarter = 4 AND secs_left <= {{secs:UInt16}}))
          AND abs(score_home - score_away) <= {{margin:UInt8}}
    )
"""

_CLUTCH_AGG = """
    SELECT
        player_name,
        argMax(team, game_id) AS team,
        uniqExact(game_id) AS games,
        countIf(action = 'shoot') AS fga,
        countIf(action = 'shoot' AND made = 1) AS fgm,
        countIf(action = 'shoot' AND shot_value = 3) AS fg3a,
        countIf(action = 'shoot' AND shot_value = 3 AND made = 1) AS fg3m,
        countIf(action = 'fthrow') AS fta,
        countIf(action = 'fthrow' AND made = 1) AS ftm,
        sum(if(action = 'shoot' AND made = 1, shot_value, 0))
            + countIf(action = 'fthrow' AND made = 1) AS points,
        countIf(action = 'assist') AS ast,
        countIf(action = 'lose') AS tov,
        countIf(action = 'recovery') AS stl,
        countIf(action = 'blockshot') AS blk,
        countIf(action = 'foul') AS fouls
    FROM clutch
    GROUP BY player_name
    HAVING games >= {min_games:UInt8}
"""


def _clutch_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    fgm, fga = _num(row["fgm"], int), _num(row["fga"], int)
    fg3m, fg3a = _num(row["fg3m"], int), _num(row["fg3a"], int)
    ftm, fta = _num(row["ftm"], int), _num(row["fta"], int)
    return {
        "slug": player_slug(row["player_name"]),
        "name": display_name(row["player_name"]),
        "team": row["team"],
        "games": _num(row["games"], int),
        "points": _num(row["points"], int),
        "ast": _num(row["ast"], int),
        "tov": _num(row["tov"], int),
        "stl": _num(row["stl"], int),
        "blk": _num(row["blk"], int),
        "fouls": _num(row["fouls"], int),
        "shooting": {
            "fgm": fgm, "fga": fga, "fg": _ratio(fgm, fga),
            "fg3m": fg3m, "fg3a": fg3a, "fg3": _ratio(fg3m, fg3a),
            "ftm": ftm, "fta": fta, "ft": _ratio(ftm, fta),
        },
    }


@app.get("/api/clutch", tags=["playbyplay"])
async def clutch(
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
    limit: Annotated[int, Query(ge=1, le=LEADERS_MAX)] = LEADERS_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Ranking en momentos ajustados: últimos 5' del último cuarto o prórroga
    con el marcador a 5 puntos o menos en ese instante del partido."""
    limit = max(1, min(int(limit), LEADERS_MAX))
    offset = max(0, int(offset))

    ctx = await _contexto(competition, season, group)
    where_p, params_p = _filtro(competition, season, group, alias="p")
    params = {**params_p, "secs": CLUTCH_SECONDS, "margin": CLUTCH_MARGIN,
              "min_games": MIN_CLUTCH_GAMES}

    cte = _CLUTCH_SCORED_CTE.format(where_p=where_p)

    total = await ch_one(
        f"SELECT count() AS n FROM ({cte} SELECT player_name FROM clutch "
        f"GROUP BY player_name HAVING uniqExact(game_id) >= {{min_games:UInt8}})",
        params,
    )
    filas = await ch_query(
        f"{cte} {_CLUTCH_AGG} ORDER BY points DESC LIMIT {{limit:UInt16}} OFFSET {{offset:UInt32}}",
        {**params, "limit": limit, "offset": offset},
    )

    return {
        "meta": ctx["meta"],
        "definition": {"lastSeconds": CLUTCH_SECONDS, "marginPoints": CLUTCH_MARGIN,
                       "minGames": MIN_CLUTCH_GAMES},
        "players": [_clutch_entry(f) for f in filas],
        "playersTotal": _num(total.get("n"), int),
        "playersOffset": offset,
    }


# --- red de asistencias ----------------------------------------------------

@app.get("/api/assist-network", tags=["playbyplay"])
async def assist_network(
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
    team: Annotated[Optional[str], Query(description="Slug de equipo; sin él, top de la competición")] = None,
):
    """Quién asiste a quién: pares (pasador, anotador) con nº de asistencias y
    puntos generados. Los tiros libres no llevan asistencia, así que solo
    cuentan los tiros de campo anotados."""
    ctx = await _contexto(competition, season, group)
    competition, season, group = ctx["competition"], ctx["season"], ctx["group"]

    name = None
    if team:
        name = await _resolve_team(team, competition, season, group)

    where_p, params_p = _filtro(competition, season, group, alias="p")
    condicion_equipo = ""
    params = {**params_p}
    if name:
        condicion_equipo = " AND if(pbp.team = 1, p.home_team, p.away_team) = {team:String}"
        params["team"] = name

    filas = await ch_query(
        f"""
        SELECT
            pbp.assisted_by_name AS passer,
            pbp.player_name AS scorer,
            if(pbp.team = 1, p.home_team, p.away_team) AS team,
            count() AS assists,
            sum(pbp.shot_value) AS points
        FROM feb.playbyplay AS pbp
        INNER JOIN feb.partidos AS p ON p.game_id = pbp.game_id
        WHERE {where_p} AND pbp.action = 'shoot' AND pbp.made = 1
              AND pbp.assisted_by_name IS NOT NULL AND pbp.player_name IS NOT NULL
              {condicion_equipo}
        GROUP BY passer, scorer, team
        ORDER BY assists DESC
        LIMIT 300
        """,
        params,
    )

    edges = []
    nodes: Dict[str, Dict[str, Any]] = {}

    def _node(raw_name: str, node_team: str) -> Dict[str, Any]:
        return nodes.setdefault(raw_name, {
            "slug": player_slug(raw_name), "name": display_name(raw_name),
            "team": node_team, "assistsGiven": 0, "assistsReceived": 0, "pointsCreated": 0,
        })

    for row in filas:
        assists = _num(row["assists"], int) or 0
        # `shot_value` no debería faltar en un tiro anotado, pero un acta rara
        # puede traerlo sin rellenar; mejor 0 puntos que tumbar la respuesta.
        points = _num(row["points"], int) or 0
        passer, scorer, row_team = row["passer"], row["scorer"], row["team"]
        edges.append({
            "passer": display_name(passer), "passerSlug": player_slug(passer),
            "scorer": display_name(scorer), "scorerSlug": player_slug(scorer),
            "team": row_team, "assists": assists, "points": points,
        })
        _node(passer, row_team)["assistsGiven"] += assists
        _node(scorer, row_team)["pointsCreated"] += points
        _node(scorer, row_team)["assistsReceived"] += assists

    nodes_out = sorted(nodes.values(), key=lambda n: n["assistsGiven"] + n["assistsReceived"], reverse=True)

    return {
        "meta": ctx["meta"],
        "team": name,
        "teamKey": team_slug(name) if name else None,
        "nodes": nodes_out,
        "edges": edges,
    }


# --- disciplina de faltas ----------------------------------------------------

def _foul_bucket() -> Dict[str, int]:
    return {"personal": 0, "tecnica": 0, "descalificante": 0, "gamesWithFoul": 0, "fouledOutGames": 0}


@app.get("/api/fouls", tags=["playbyplay"])
async def fouls(
    competition: Annotated[Optional[str], Query(description="Clave de competición")] = None,
    season: Annotated[Optional[str], Query(description="Año de inicio de temporada")] = None,
    group: Annotated[Optional[str], Query(description="Clave de grupo")] = None,
    limit: Annotated[int, Query(ge=1, le=LEADERS_MAX)] = LEADERS_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Disciplina: faltas por tipo (personal/técnica/descalificante), por
    jugador y por equipo, más partidos eliminado por 5 personales."""
    limit = max(1, min(int(limit), LEADERS_MAX))
    offset = max(0, int(offset))

    ctx = await _contexto(competition, season, group)
    where, params = ctx["where"], ctx["params"]
    where_p, params_p = _filtro(competition, season, group, alias="p")

    # Partidos jugados y equipo, tal y como los cuenta el acta de caja: la
    # única fuente fiable de "partidos jugados" (el play-by-play solo sabe de
    # partidos en los que hubo alguna falta).
    filas_base = await ch_query(
        f"""
        SELECT player_name, argMax(team, game_date) AS team,
               argMax(`group`, game_date) AS grupo, count() AS games
        FROM feb.jugadores WHERE {where}
        GROUP BY player_name
        """,
        params,
    )
    base = {f["player_name"]: f for f in filas_base}

    filas_pbp = await ch_query(
        f"""
        SELECT pbp.player_name AS player_name, pbp.game_id AS game_id,
               countIf(pbp.foul_type = 'personal') AS personal_g,
               countIf(pbp.foul_type = 'tecnica') AS tecnica_g,
               countIf(pbp.foul_type = 'descalificante') AS descalificante_g
        FROM feb.playbyplay AS pbp
        INNER JOIN feb.partidos AS p ON p.game_id = pbp.game_id
        WHERE {where_p} AND pbp.action = 'foul' AND pbp.player_name IS NOT NULL
        GROUP BY player_name, game_id
        """,
        params_p,
    )

    por_jugador: Dict[str, Dict[str, int]] = {}
    por_equipo: Dict[str, Dict[str, int]] = {}
    for row in filas_pbp:
        name = row["player_name"]
        personal = _num(row["personal_g"], int) or 0
        tecnica = _num(row["tecnica_g"], int) or 0
        descalificante = _num(row["descalificante_g"], int) or 0

        bucket = por_jugador.setdefault(name, _foul_bucket())
        bucket["personal"] += personal
        bucket["tecnica"] += tecnica
        bucket["descalificante"] += descalificante
        bucket["gamesWithFoul"] += 1
        if personal >= FOUL_OUT_THRESHOLD:
            bucket["fouledOutGames"] += 1

        info = base.get(name)
        if info:
            equipo = por_equipo.setdefault(info["team"], _foul_bucket())
            equipo["personal"] += personal
            equipo["tecnica"] += tecnica
            equipo["descalificante"] += descalificante

    players = []
    for name, stats in por_jugador.items():
        info = base.get(name)
        if info is None:
            continue    # falta en un partido fuera del filtro actual (no debería pasar)
        games = _num(info["games"], int)
        if games < MIN_FOUL_GAMES:
            continue
        total = stats["personal"] + stats["tecnica"] + stats["descalificante"]
        players.append({
            "slug": player_slug(name), "name": display_name(name),
            "team": info["team"], "group": info.get("grupo"),
            "games": games,
            "personalFouls": stats["personal"],
            "technicalFouls": stats["tecnica"],
            "disqualifyingFouls": stats["descalificante"],
            "totalFouls": total,
            "foulsPerGame": round(total / games, 2) if games else None,
            "fouledOutGames": stats["fouledOutGames"],
        })
    players.sort(key=lambda p: p["totalFouls"], reverse=True)
    players_total = len(players)
    players_page = players[offset:offset + limit]

    standings = await _standings(where, params)
    games_by_team = {row["team"]: row["games"] for row in standings}
    teams = []
    for team_name_raw, stats in por_equipo.items():
        games = games_by_team.get(team_name_raw)
        if not games or games < MIN_FOUL_GAMES:
            continue    # equipo con solo un par de partidos en el filtro (p.ej. fase final en curso)
        total = stats["personal"] + stats["tecnica"] + stats["descalificante"]
        teams.append({
            "team": team_name_raw, "teamKey": team_slug(team_name_raw), "games": games,
            "personalFouls": stats["personal"],
            "technicalFouls": stats["tecnica"],
            "disqualifyingFouls": stats["descalificante"],
            "totalFouls": total,
            "foulsPerGame": round(total / games, 2) if games else None,
        })
    teams.sort(key=lambda t: t["foulsPerGame"] or 0, reverse=True)

    return {
        "meta": ctx["meta"],
        "foulOutThreshold": FOUL_OUT_THRESHOLD,
        "players": players_page,
        "playersTotal": players_total,
        "playersOffset": offset,
        "teams": teams,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
