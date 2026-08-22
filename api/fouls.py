"""Disciplina de faltas: por tipo, por jugador y por equipo.

Un jugador queda eliminado por faltas a las 5 personales (reglas FIBA).
"""
from typing import Annotated, Dict, Optional

from fastapi import Query

from . import clickhouse
from .app import app
from .context import _contexto
from .stats import LEADERS_LIMIT, LEADERS_MAX, _num, _standings
from src.naming import display_name, player_slug, team_slug

FOUL_OUT_THRESHOLD = 5
MIN_FOUL_GAMES = 3


def _bucket() -> Dict[str, int]:
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
    where_p, params_p = clickhouse._filtro(competition, season, group, alias="p")

    # Partidos jugados y equipo, tal y como los cuenta el acta de caja: la
    # única fuente fiable de "partidos jugados" (el play-by-play solo sabe de
    # partidos en los que hubo alguna falta).
    filas_base = await clickhouse.ch_query(
        f"""
        SELECT player_name, argMax(team, game_date) AS team,
               argMax(`group`, game_date) AS grupo, count() AS games
        FROM feb.jugadores WHERE {where}
        GROUP BY player_name
        """,
        params,
    )
    base = {f["player_name"]: f for f in filas_base}

    filas_pbp = await clickhouse.ch_query(
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

        bucket = por_jugador.setdefault(name, _bucket())
        bucket["personal"] += personal
        bucket["tecnica"] += tecnica
        bucket["descalificante"] += descalificante
        bucket["gamesWithFoul"] += 1
        if personal >= FOUL_OUT_THRESHOLD:
            bucket["fouledOutGames"] += 1

        info = base.get(name)
        if info:
            equipo = por_equipo.setdefault(info["team"], _bucket())
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
