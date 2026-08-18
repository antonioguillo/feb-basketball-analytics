"""Database connection and ClickHouse client for the FEB Scouting API."""
import os
import json
import subprocess
from typing import Optional, Dict, Any, List
import httpx

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS = os.getenv("MINIO_ACCESS", "minioadmin")
MINIO_SECRET = os.getenv("MINIO_SECRET", "minioadmin")

CLICKHOUSE_HTTP_URL = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"

class ClickHouseClient:
    def __init__(self, host: str = CLICKHOUSE_HOST, port: int = CLICKHOUSE_PORT,
                 user: str = CLICKHOUSE_USER, password: str = CLICKHOUSE_PASSWORD):
        self.base_url = f"http://{host}:{port}"
        self.user = user
        self.password = password
        self._session: Optional[httpx.AsyncClient] = None
    
    async def _get_session(self) -> httpx.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={"Accept": "application/json"}
            )
        return self._session
    
    async def query(self, sql: str, **kwargs) -> List[Dict[str, Any]]:
        session = await self._get_session()
        auth = (self.user, self.password) if self.user else None
        try:
            response = await session.post(
                "/",
                content=sql,
                headers={"Content-Type": "application/sql"},
                auth=auth,
                timeout=120.0
            )
            response.raise_for_status()
            return [{"raw_response": response.text}]
        except httpx.HTTPError as e:
            return await self._docker_query(sql)
    
    async def _docker_query(self, sql: str) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(
                ["docker", "exec", "feb-clickhouse", "clickhouse-client", "--query", sql],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if not lines:
                    return []
                headers = lines[0].split("\t") if "\t" in lines[0] else [f"col_{i}" for i in range(len(lines[0].split()))]
                results = []
                for line in lines[1:]:
                    values = line.split("\t")
                    row = {}
                    for i, header in enumerate(headers):
                        if i < len(values):
                            row[header] = values[i]
                        else:
                            row[header] = None
                    results.append(row)
                return results
            return []
        except Exception:
            return []
    
    async def close(self):
        if self._session and not self._session.is_closed:
            await self._session.aclose()
            self._session = None

ch_client = ClickHouseClient()
def get_ch_client() -> ClickHouseClient:
    return ch_client

async def execute_sql(sql: str, fallback_to_docker: bool = True) -> List[Dict[str, Any]]:
    result = await ch_client.query(sql)
    if not result and fallback_to_docker:
        result = await ch_client._docker_query(sql)
    return result

async def get_partidos_temporada(any_temporada: str) -> List[Dict[str, Any]]:
    sql = f"SELECT partido_id, any, fecha, equipo_local_id, equipo_visitante_id, score_local, score_visitante, ganador, grupo FROM feb.fact_partidos WHERE any_temporada = '{any_temporada}' ORDER BY fecha"
    return await execute_sql(sql)

async def get_jugador_partido_stats(jugador_id: int, any_temporada: str) -> List[Dict[str, Any]]:
    sql = f"SELECT game_id, player_id, player_name, minutes_played, puntos, two_point_pct, three_point_pct, free_throw_pct, effective_fg_pct, true_shooting_pct, plus_minus_48, offensive_rating_estimate, defensive_rating_estimate, net_rating_estimate, points_per_36, points_per_48, turnover_per_36, steal_per_36, block_per_36, rebounds_per_36, fouls_per_36, double_double_condition, triple_double_condition, efficiency_per_minute, val_per_minute, usage_rate_estimate, es_local, grupo FROM feb.fact_jugador_partido WHERE player_id = {jugador_id} AND any_temporada = '{any_temporada}' ORDER BY game_id"
    return await execute_sql(sql)

async def get_lineup_ratings(any_temporada: str) -> List[Dict[str, Any]]:
    sql = f"SELECT jugadores[1] AS jugador1, jugadores[2] AS jugador2, jugadores[3] AS jugador3, jugadores[4] AS jugador4, jugadores[5] AS jugador5, any_temporada, offensive_rating, defensive_rating, net_rating, partidos_jugados, win_percentage, minutos_promedio FROM gold.mv_lineup_ratings WHERE any_temporada = '{any_temporada}' ORDER BY net_rating DESC"
    return await execute_sql(sql)

async def get_leaderboard_estadisticas(any_temporada: str) -> List[Dict[str, Any]]:
    sql = f"SELECT any_temporada, argMax(player_id, puntos) AS max_puntos_jugador_id, MAX(puntos) AS max_puntos, argMax(player_id, two_point_pct) AS mejor_tiro_2p_jugador_id, MAX(two_point_pct) AS max_two_point_pct, argMax(player_id, three_point_pct) AS mejor_tiro_3p_jugador_id, MAX(three_point_pct) AS max_three_point_pct, argMax(player_id, free_throw_pct) AS mejor_tiro_livre_jugador_id, MAX(free_throw_pct) AS max_free_throw_pct, argMax(player_id, true_shooting_pct) AS mejor_ts_jugador_id, MAX(true_shooting_pct) AS max_ts, argMax(player_id, points_per_36) AS mas_activo_jugador_id, MAX(points_per_36) AS max_points_per_36 FROM feb.fact_jugador_partido WHERE any_temporada = '{any_temporada}' GROUP BY any_temporada"
    return await execute_sql(sql)

async def check_db_health() -> bool:
    try:
        result = await execute_sql("SELECT 1")
        return len(result) > 0
    except Exception:
        return False

MV_VIEWS = ["mv_lineup_ratings", "mv_mejores_quintetos", "mv_onoff_player", "mv_quinteto_zones", "mv_quinteto_assists", "mv_double_triple_doubles", "mv_estadisticas_lideres", "mv_players_by_position", "mv_minutes_leaderboard"]

RAPID_ENDPOINTS = {
    "lineup_ratings": "mv_lineup_ratings",
    "mejores_quintetos": "mv_mejores_quintetos",
    "onoff_player": "mv_onoff_player",
    "zones_tiro": "mv_quinteto_zones",
    "asistencias": "mv_quinteto_assists",
    "doubles_triples": "mv_double_triple_doubles",
    "lideres": "mv_estadisticas_lideres",
    "jugadores_posicion": "mv_players_by_position",
    "minutos_leaderboard": "mv_minutes_leaderboard"
}
