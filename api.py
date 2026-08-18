"""API REST para la aplicación de scouting de baloncesto FEB.
Exponen datos de ClickHouse vía HTTP para el frontend.
"""

import os
import re
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import httpx

app = FastAPI(
    title="FEB Basketball Scouting API",
    description="API para aplicación de scouting de baloncesto Tercera FEB",
    version="0.1.0",
)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS = os.getenv("MINIO_ACCESS", "minioadmin")
MINIO_SECRET = os.getenv("MINIO_SECRET", "minioadmin")
CH_HOST = os.getenv("CH_HOST", "http://localhost:8123")


async def query_clickhouse(sql: str, database: str = "feb") -> List[Dict[str, Any]]:
    """Ejecuta una query a ClickHouse y devuelve resultados como lista de diccionarios."""
    url = f"{CH_HOST}/?sql={httpx.URL(sql).encode()}".replace(" ", "%20")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"ClickHouse error: {resp.text}")
        # ClickHouse devuelve CSV con nombres de columna en la primera fila
        lines = resp.text.strip().split("\n")
        if not lines or lines[0].startswith("Exception"):
            raise HTTPException(status_code=500, detail=f"ClickHouse error: {resp.text}")
        # Parse simple CSV
        headers = [h.strip() for h in lines[0].split("\t")]
        rows = []
        for line in lines[1:]:
            values = [v.strip() for v in line.split("\t")]
            row = dict(zip(headers, values))
            rows.append(row)
        return rows


@app.get("/api/health", tags=["health"])
async def health():
    """Health check."""
    return {"status": "ok", "service": "feb-scouting-api"}


@app.get("/api/partidos", tags=["partidos"], summary="Listado de partidos")
async def list_partidos(
    skip: int = 0,
    limit: int = 100,
    year: Optional[int] = None,
    winner: Optional[str] = None,
):
    """Lista de partidos con filtros opcionales."""
    base_sql = "SELECT game_id, year, date, home_score, away_score, total_points, winner FROM feb.partidos"
    conditions = []
    params = {}
    if year:
        conditions.append(f"year = {year}")
    if winner:
        conditions.append(f"winner = '{winner}'")
    
    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)
    
    sql = f"{base_sql}{where_clause} LIMIT {limit} OFFSET {skip}"
    rows = await query_clickhouse(sql)
    return {"total": len(rows), "partidos": rows}


@app.get("/api/partidos/{game_id}", tags=["partidos"], summary="Detalle de un partido")
async def get_partido(game_id: int):
    """Obtiene los detalles de un partido específico."""
    sql = f"SELECT game_id, year, date, home_score, away_score, total_points, winner FROM feb.partidos WHERE game_id = {game_id}"
    rows = await query_clickhouse(sql)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Partido {game_id} no encontrado")
    return rows[0]


@app.get("/api/equipos", tags=["equipos"], summary="Lista de equipos")
async def list_equipos():
    """Obtiene la lista de equipos participantes."""
    sql = "SELECT DISTINCT team_id, team_name FROM feb.equipos_partido ORDER BY team_name"
    rows = await query_clickhouse(sql)
    return {"equipos": rows}


@app.get("/api/jugadores", tags=["jugadores"], summary="Lista de jugadores")
async def list_jugadores(
    skip: int = 0,
    limit: int = 100,
    team_id: Optional[int] = None,
):
    """Lista de jugadores con filtro por equipo opcional."""
    base_sql = "SELECT player_id, player_name, jersey, year, minutos_played, puntos, equipo_id FROM feb.jugadores"
    conditions = []
    if team_id:
        conditions.append(f"equipo_id = {team_id}")
    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)
    sql = f"{base_sql}{where_clause} LIMIT {limit} OFFSET {skip}"
    rows = await query_clickhouse(sql)
    return {"total": len(rows), "jugadores": rows}


@app.get("/api/scouting/player/{player_id}", tags=["scouting"], summary="Estadísticas de scouting de un jugador")
async def get_scouting_player(player_id: int):
    """Obtiene todas las estadísticas de scouting de un jugador en todas las jornadas."""
    sql = f"""
    SELECT game_id, year, date, jersey, player_name, minutes_played, puntos,
           t2m, t2a, t3m, t3a, ftm, fta, reb, ast, stl, blk, to, pf, plus_minus, val
    FROM feb.jugadores WHERE player_id = {player_id}
    ORDER BY year, date
    """
    rows = await query_clickhouse(sql)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Jugador {player_id} no encontrado")
    
    # Formatear datos para el frontend
    return {
        "player_id": player_id,
        "player_name": rows[0].get("player_name", ""),
        "total_games": len(rows),
        "career_averages": {
            "points": sum(int(r.get("puntos", 0) or 0) for r in rows) / len(rows),
            "minutes": sum(float(r.get("minutes_played", 0) or 0) for r in rows) / len(rows),
            "rebounds": sum(int(r.get("reb", 0) or 0) for r in rows) / len(rows),
            "assists": sum(int(r.get("ast", 0) or 0) for r in rows) / len(rows),
        },
        "games": rows,
    }


@app.get("/api/scouting/team/{team_id}", tags=["scouting"], summary="Estadísticas de un equipo")
async def get_scouting_team(team_id: int):
    """Estadísticas de un equipo incluyendo tiros y play-by-play."""
    # Estadísticas básicas del equipo
    sql_team = f"""
    SELECT * FROM feb.equipos_partido WHERE team_id = {team_id} LIMIT 1
    """
    team_rows = await query_clickhouse(sql_team)
    
    # Tiros del equipo
    sql_shots = f"""
    SELECT * FROM feb.tiros WHERE team_id = {team_id} LIMIT 20
    """
    shot_rows = await query_clickhouse(sql_shots)
    
    return {
        "team_id": team_id,
        "team_info": team_rows[0] if team_rows else {},
        "shots": shot_rows,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)