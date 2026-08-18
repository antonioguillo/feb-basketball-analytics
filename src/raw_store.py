"""Capa RAW: sube los datos scrapeados a MinIO (data lake) en formato JSON.
Cada partido se guarda en raw/competicion=<name>/anio=<year>/partido=<id>.json
para permitir reprocesamientos y auditoría."""
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scraper import Game


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
                "scraped_at": datetime.utcnow().isoformat(),
                "source": "feb.es",
            },
            "players_home": [vars(s) for s in game.home_stats],
            "players_away": [vars(s) for s in game.away_stats],
            "play_by_play": game.play_by_play,
            "shots": game.shots,
            "team_stats": game.team_stats,
        }

    def upload_game(self, game: Game, competition: str = "partido_suelto", year: str = "2026",
                    group: str = "ungrouped") -> str:
        data = self._game_to_dict(game)
        data["meta"]["group"] = group
        key = f"competition={competition}/year={year}/group={group}/game_id={game.id}.json"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return f"s3://{self.bucket}/{key}"

    def list_games(self, competition: Optional[str] = None, year: Optional[str] = None) -> list:
        prefix = ""
        if competition:
            prefix += f"competition={competition}/"
        if year:
            prefix += f"year={year}/"
        result = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [o["Key"] for o in result.get("Contents", [])]