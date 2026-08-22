"""Resolución del contexto de una petición: competición, temporada y grupo.

Toda respuesta habla de UNA competición: mezclar en un mismo ranking la
Tercera FEB masculina con la LF Endesa no significa nada. Si no se pide
ninguna se elige la que más partidos tiene y se dice cuál en `meta`.
"""
from typing import Any, Dict, Optional

from fastapi import HTTPException

from . import clickhouse
from .stats import _num
from src.models import COMPETITIONS


async def _contexto(competition: Optional[str], season: Optional[str],
                    group: Optional[str]) -> Dict[str, Any]:
    if season is None:
        fila = await clickhouse.ch_one("SELECT year FROM feb.partidos GROUP BY year "
                            "ORDER BY count() DESC, year DESC LIMIT 1")
        season = str(fila.get("year") or "")
        if not season:
            raise HTTPException(status_code=404, detail="No hay partidos cargados")

    if competition is None:
        fila = await clickhouse.ch_one(
            "SELECT competition FROM feb.partidos WHERE year = {year:UInt16} "
            "GROUP BY competition ORDER BY count() DESC LIMIT 1",
            {"year": int(season)})
        competition = fila.get("competition")
        if not competition:
            raise HTTPException(status_code=404,
                                detail=f"No hay partidos en la temporada {season}")

    where, params = clickhouse._filtro(competition, season, group)
    resumen = await clickhouse.ch_one(
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
