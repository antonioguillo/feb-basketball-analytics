"""Fórmulas de estadísticas y ranking: números, porcentajes de tiro, clasificación."""
from typing import Any, Dict, List, Optional

from . import clickhouse
from src.naming import display_name, player_slug, team_slug

# Umbrales del ranking de líderes: sin un mínimo, cualquiera con un buen
# partido suelto encabezaría la tabla.
MIN_GAMES = 6
MIN_MINUTES = 15

# Página de líderes por defecto. Sin tope, una liga entera devuelve cientos de
# jugadores en una sola respuesta.
LEADERS_LIMIT = 50
LEADERS_MAX = 500


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


def _possessions(fga, orb, tov, fta) -> Optional[float]:
    fga, orb, tov, fta = _num(fga, float), _num(orb, float), _num(tov, float), _num(fta, float)
    if fga is None:
        return None
    return fga - (orb or 0) + (tov or 0) + 0.44 * (fta or 0)


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


async def _standings(where: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Clasificación: un equipo puede ser local o visitante, así que se cuenta
    desde ambos lados con una UNION y se suma por nombre de equipo."""
    filas = await clickhouse.ch_query(
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
