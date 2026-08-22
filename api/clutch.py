"""Ranking en momentos ajustados ("clutch").

`feb.playbyplay` solo trae el marcador (scoreA/scoreB) en las jugadas que
anotan; el resto lo deja a 0. Como el marcador nunca baja, el máximo
acumulado hasta cada jugada (ventana ORDER BY tiempo real de partido) es el
marcador vigente en ese instante — evita tener que rellenar a mano.

"Clutch": últimos 5 minutos del último cuarto (o cualquier prórroga) con el
marcador a 5 puntos o menos en ese instante — la definición habitual de
tiempo/marcador ajustado, no solo el resultado final del partido.
"""
from typing import Annotated, Any, Dict, Optional

from fastapi import Query

from . import clickhouse
from .app import app
from .context import _contexto
from .stats import LEADERS_LIMIT, LEADERS_MAX, _num, _ratio
from src.naming import display_name, player_slug

CLUTCH_SECONDS = 300
CLUTCH_MARGIN = 5
MIN_CLUTCH_GAMES = 2

_SCORED_CTE = """
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

_AGG = """
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


def _entry(row: Dict[str, Any]) -> Dict[str, Any]:
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
    where_p, params_p = clickhouse._filtro(competition, season, group, alias="p")
    params = {**params_p, "secs": CLUTCH_SECONDS, "margin": CLUTCH_MARGIN,
              "min_games": MIN_CLUTCH_GAMES}

    cte = _SCORED_CTE.format(where_p=where_p)

    total = await clickhouse.ch_one(
        f"SELECT count() AS n FROM ({cte} SELECT player_name FROM clutch "
        f"GROUP BY player_name HAVING uniqExact(game_id) >= {{min_games:UInt8}})",
        params,
    )
    filas = await clickhouse.ch_query(
        f"{cte} {_AGG} ORDER BY points DESC LIMIT {{limit:UInt16}} OFFSET {{offset:UInt32}}",
        {**params, "limit": limit, "offset": offset},
    )

    return {
        "meta": ctx["meta"],
        "definition": {"lastSeconds": CLUTCH_SECONDS, "marginPoints": CLUTCH_MARGIN,
                       "minGames": MIN_CLUTCH_GAMES},
        "players": [_entry(f) for f in filas],
        "playersTotal": _num(total.get("n"), int),
        "playersOffset": offset,
    }
