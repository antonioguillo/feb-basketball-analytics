"""Índices slug -> nombre para jugadores y equipos.

El acta no publica id de jugador ni de equipo, así que el identificador se
deriva del nombre. Resolverlo recorriendo todos los nombres en cada petición
costaba cientos de milisegundos y crece con el histórico, de modo que el mapa
slug -> nombre se construye una vez por (competición, temporada, grupo) y se
guarda con TTL.
"""
import asyncio
import os
import time
from typing import Dict, Optional

from fastapi import HTTPException

from . import clickhouse
from src.naming import player_slug, team_slug

# Cuánto se guarda el índice de slugs. Las tablas solo cambian cuando se
# recarga el pipeline, así que un cuarto de hora es conservador.
SLUG_CACHE_TTL = float(os.getenv("SLUG_CACHE_TTL", "900"))

_slug_cache: Dict[tuple, tuple] = {}
_slug_lock = asyncio.Lock()

_team_slug_cache: Dict[tuple, tuple] = {}
_team_slug_lock = asyncio.Lock()


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

        where, params = clickhouse._filtro(competition, season, group)
        filas = await clickhouse.ch_query(
            f"SELECT DISTINCT player_name FROM feb.jugadores WHERE {where}", params)
        indice = {player_slug(f["player_name"]): f["player_name"] for f in filas}
        _slug_cache[clave] = (time.monotonic(), indice)
        return indice


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

        where, params = clickhouse._filtro(competition, season, group)
        filas = await clickhouse.ch_query(
            f"SELECT DISTINCT team FROM feb.jugadores WHERE {where}", params)
        indice = {team_slug(f["team"]): f["team"] for f in filas}
        _team_slug_cache[clave] = (time.monotonic(), indice)
        return indice


async def _resolve_player(slug: str, competition: Optional[str], season: Optional[str],
                          group: Optional[str]) -> str:
    """Nombre del acta que corresponde a un slug, vía el índice cacheado."""
    indice = await _indice_slugs(competition, season, group)
    nombre = indice.get(slug)
    if nombre is None:
        raise HTTPException(status_code=404, detail=f"Jugador '{slug}' no encontrado")
    return nombre


async def _resolve_team(slug: str, competition: Optional[str], season: Optional[str],
                        group: Optional[str]) -> str:
    indice = await _indice_equipos(competition, season, group)
    name = indice.get(slug)
    if name is None:
        raise HTTPException(status_code=404, detail=f"Equipo '{slug}' no encontrado")
    return name


def invalidar_indice_slugs():
    """Para los tests y para cuando se recarga el pipeline."""
    _slug_cache.clear()
    _team_slug_cache.clear()
