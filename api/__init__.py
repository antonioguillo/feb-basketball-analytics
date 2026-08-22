"""Paquete de la API REST. Ver `api.app` para los endpoints.

Reexporta lo que usan `uvicorn api:app`, los scripts de operación
(`scripts/generar_fixtures.py`) y los tests (`tests/test_api_*.py`), de modo
que el paquete se comporta como el antiguo módulo `api.py` de cara a quien lo
importa.
"""
from . import clickhouse
from .app import app, competitions, dashboard, health, player, team, teams
from .clickhouse import CH_PASSWORD, CH_TIMEOUT, CH_URL, CH_USER, ch_one, ch_query
from .slugs import invalidar_indice_slugs
from .stats import LEADERS_LIMIT, LEADERS_MAX, MIN_GAMES, MIN_MINUTES

__all__ = [
    "app", "clickhouse", "ch_query", "ch_one",
    "CH_URL", "CH_USER", "CH_PASSWORD", "CH_TIMEOUT",
    "health", "competitions", "dashboard", "player", "team", "teams",
    "invalidar_indice_slugs",
    "MIN_GAMES", "MIN_MINUTES", "LEADERS_LIMIT", "LEADERS_MAX",
]
