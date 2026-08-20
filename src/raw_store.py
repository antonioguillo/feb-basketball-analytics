"""Capa RAW: sube los datos scrapeados a MinIO (data lake) en formato JSON.
Cada partido se guarda en raw/competicion=<name>/anio=<year>/partido=<id>.json
para permitir reprocesamientos y auditoría."""
import io
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .scraper import Game

logger = logging.getLogger(__name__)


class RawStore:
    def __init__(self, endpoint="localhost:9000", access_key="minioadmin", secret_key="minioadmin", bucket="raw", secure=False):
        try:
            import boto3
            from botocore.client import Config
        except ImportError:
            raise RuntimeError("Instala boto3: pip install boto3")

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if secure else 'http'}://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def _game_to_dict(self, game: Game) -> dict:
        return {
            "meta": {
                "game_id": game.id,
                "date": game.date,
                "time": game.game_time,
                "venue": game.venue,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "source": "feb.es",
            },
            "players_home": [vars(s) for s in game.home_stats],
            "players_away": [vars(s) for s in game.away_stats],
            "play_by_play": game.play_by_play,
            "shots": game.shots,
            "team_stats": game.team_stats,
        }

    def upload_game(self, game: Game, competition: str = "partido_suelto", year: str = "2026",
                    group: str = "ungrouped", intentos: int = 4) -> str:
        """Sube un partido a raw, reintentando los fallos pasajeros.

        Una descarga del histórico dura horas, y en ese tiempo el reloj del
        contenedor de MinIO se desincroniza del anfitrión cada vez que el equipo
        suspende. La firma de S3 rechaza entonces la petición con
        `RequestTimeTooSkewed` y, sin reintento, una sola de esas tira abajo un
        trabajo de veinte horas. El desfase se corrige solo en cuanto Docker
        vuelve a sincronizar, así que basta con esperar y repetir.
        """
        data = self._game_to_dict(game)
        data["meta"]["group"] = group
        key = f"competition={competition}/year={year}/group={group}/game_id={game.id}.json"
        cuerpo = json.dumps(data, ensure_ascii=False).encode("utf-8")

        for intento in range(1, intentos + 1):
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=cuerpo,
                    ContentType="application/json",
                )
                return f"s3://{self.bucket}/{key}"
            except Exception as error:
                if intento == intentos:
                    raise
                espera = 5 * 2 ** (intento - 1)      # 5 s, 10 s, 20 s
                logger.warning("Fallo al subir %s (%s). Reintento %d/%d en %ds",
                               key, type(error).__name__, intento, intentos - 1, espera)
                time.sleep(espera)

    def list_games(self, competition: Optional[str] = None, year: Optional[str] = None) -> list:
        """Lista las claves de raw bajo el prefijo dado.

        Usa paginacion: list_objects_v2 devuelve como mucho 1000 claves por
        llamada, y una sola temporada ya supera esa cifra. Sin paginar, la
        comprobacion de idempotencia daria por ausentes partidos ya subidos y
        los volveria a scrapear.
        """
        prefix = ""
        if competition:
            prefix += f"competition={competition}/"
        if year:
            prefix += f"year={year}/"

        keys = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return keys

    def existing_game_ids(self, competition: Optional[str] = None,
                          year: Optional[str] = None) -> set:
        """IDs de partido ya presentes en raw, para saltarlos al re-escanear."""
        ids = set()
        for key in self.list_games(competition=competition, year=year):
            match = re.search(r"game_id=(\d+)\.json$", key)
            if match:
                ids.add(match.group(1))
        return ids