from fastapi import APIRouter

from app.core.db import (
    get_ch_client, get_partidos_temporada, get_jugador_partido_stats,
    get_lineup_ratings, get_leaderboard_estadisticas, check_db_health,
    MV_VIEWS, RAPID_ENDPOINTS
)

router = APIRouter(prefix="/v1", tags=["feb-basketball"])

"""API endpoints for FEB Basketball Scouting."""
