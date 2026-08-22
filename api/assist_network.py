"""Red de asistencias: quién asiste a quién.

Pares (pasador, anotador) con nº de asistencias y puntos generados. Los
tiros libres no llevan asistencia, así que solo cuentan los tiros de campo
anotados.
"""
from typing import Annotated, Any, Dict, Optional

from fastapi import Query

from . import clickhouse
from .app import app
from .context import _contexto
from .slugs import _resolve_team
from .stats import _num
from src.naming import display_name, player_slug, team_slug


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

    where_p, params_p = clickhouse._filtro(competition, season, group, alias="p")
    condicion_equipo = ""
    params = {**params_p}
    if name:
        condicion_equipo = " AND if(pbp.team = 1, p.home_team, p.away_team) = {team:String}"
        params["team"] = name

    filas = await clickhouse.ch_query(
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
