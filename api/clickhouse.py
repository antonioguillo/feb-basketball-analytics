"""Acceso a ClickHouse: cliente HTTP compartido y helpers de consulta.

Un único cliente para todo el proceso. Crear uno por consulta costaba 838 ms
frente a 8 ms reutilizándolo: la ficha de un jugador lanza seis consultas, así
que era la diferencia entre 5 segundos y medio segundo.
"""
import asyncio
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

CH_URL = os.getenv("CH_URL", "http://localhost:8123")
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "feb")
CH_TIMEOUT = float(os.getenv("CH_TIMEOUT", "30"))

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


async def cerrar_cliente():
    """Para el lifespan de FastAPI: libera el pool de conexiones al apagar."""
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()


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
