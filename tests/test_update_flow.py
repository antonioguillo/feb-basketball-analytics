"""Comportamiento del flujo de actualización de una temporada en curso.

El punto delicado: un partido que todavía no se ha jugado NO debe guardarse en
raw. Si se guardara, la comprobación de idempotencia lo daría por hecho y no
volvería a bajarse nunca cuando se dispute, dejando un agujero permanente en el
histórico.

Ejecutar:  python -m unittest tests.test_update_flow -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main
import src.raw_store
from src.scraper import Game, PlayerStats


def _player(jersey=4, points=10):
    return PlayerStats(
        jersey=jersey, name=f"JUGADOR {jersey}", player_id="", minutes=20.0,
        points=points, two_points_made=3, two_points_attempted=6,
        three_points_made=1, three_points_attempted=3,
        free_throws_made=1, free_throws_attempted=2,
        offensive_rebounds=1, defensive_rebounds=3, total_rebounds=4,
        assists=2, steals=1, blocks=0, turnovers=2, fouls=3,
        plus_minus=5, efficiency=12,
    )


def played(game_id):
    return Game(id=game_id, date="04/10/2025", game_time="18:00", venue="Pabellón",
                home_team="EQUIPO A", away_team="EQUIPO B", home_score=80, away_score=70,
                home_stats=[_player()], away_stats=[_player(7, 8)],
                play_by_play=[{"num": 1}], shots=[{"x": "50", "y": "50"}],
                team_stats={"TEAM": [{}, {}]})


def not_played(game_id):
    """Ficha publicada pero sin acta: el partido aún no se ha disputado."""
    return Game(id=game_id, date="30/05/2026", game_time="18:00", venue="Pabellón",
                home_team="EQUIPO A", away_team="EQUIPO B", home_score=0, away_score=0,
                home_stats=[], away_stats=[], play_by_play=[], shots=[], team_stats={})


class FakeScraper:
    """Un grupo con dos partidos: uno jugado y otro por jugar."""

    def __init__(self, *args, **kwargs):
        self.scraped = []

    def get_seasons(self, competition_id):
        return [("2025", "2025/2026")]

    def get_groups(self, competition_id, season):
        return [("111", 'Liga Regular Único')]

    def get_game_links_by_group(self, competition_id, season, group_id, max_journeys=None):
        return ["https://www.feb.es/competiciones/Partido.aspx?p=1001",
                "https://www.feb.es/competiciones/Partido.aspx?p=1002"]

    def scrape_game(self, url):
        game_id = int(url.rsplit("=", 1)[-1])
        self.scraped.append(game_id)
        return played(game_id) if game_id == 1001 else not_played(game_id)


class FakeStore:
    """RawStore en memoria, con la misma interfaz que usa scraping/jobs.py."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.uploaded = {}
        FakeStore.instances.append(self)

    def existing_game_ids(self, competition=None, year=None):
        return set(self.uploaded)

    def upload_game(self, game, competition="", year="", group=""):
        key = f"competition={competition}/year={year}/group={group}/game_id={game.id}.json"
        self.uploaded[str(game.id)] = key
        return key


class UpdateFlowTest(unittest.TestCase):
    def setUp(self):
        FakeStore.instances = []
        self._scraper, self._store = main.jobs.FEBBasketballScraper, src.raw_store.RawStore
        main.jobs.FEBBasketballScraper = FakeScraper
        src.raw_store.RawStore = FakeStore

    def tearDown(self):
        main.jobs.FEBBasketballScraper = self._scraper
        src.raw_store.RawStore = self._store

    def test_no_guarda_partidos_sin_jugar(self):
        result = main.scrape_historico("tercerafeb", seasons=["2025"], upload_raw=True, delay=0)

        self.assertEqual(result["scraped"], 1)
        self.assertEqual(result["pending"], 1, "el partido sin jugar debe contarse como pendiente")
        store = FakeStore.instances[-1]
        self.assertEqual(set(store.uploaded), {"1001"},
                         "solo debe subirse el partido con acta")

    def test_la_siguiente_ejecucion_reintenta_el_pendiente(self):
        """Segunda pasada: el ya guardado se omite y el pendiente se vuelve a mirar."""
        main.scrape_historico("tercerafeb", seasons=["2025"], upload_raw=True, delay=0)
        first_store = FakeStore.instances[-1]

        # La segunda ejecución arranca con lo que ya hay en raw
        class SeededStore(FakeStore):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.uploaded = dict(first_store.uploaded)

        src.raw_store.RawStore = SeededStore
        result = main.scrape_historico("tercerafeb", seasons=["2025"], upload_raw=True, delay=0)

        self.assertEqual(result["skipped"], 1, "el partido ya descargado no se repite")
        self.assertEqual(result["pending"], 1, "el que falta se vuelve a intentar")
        self.assertEqual(result["scraped"], 0)

    def test_la_ruta_de_raw_separa_liga_y_grupo(self):
        main.scrape_historico("tercerafeb", seasons=["2025"], upload_raw=True, delay=0)
        key = FakeStore.instances[-1].uploaded["1001"]

        self.assertEqual(key,
                         "competition=tercerafeb/year=2025/group=Unico/game_id=1001.json")

    def test_actualizar_recorre_las_competiciones_absolutas(self):
        from src.models import SENIOR_COMPETITIONS

        totales = main.actualizar(seasons=["2025"], delay=0)

        # Un partido nuevo y otro pendiente por cada competición absoluta
        self.assertEqual(totales["scraped"], len(SENIOR_COMPETITIONS))
        self.assertEqual(totales["pending"], len(SENIOR_COMPETITIONS))
        self.assertEqual(totales["failed"], 0)

    def test_actualizar_admite_una_competicion_concreta(self):
        totales = main.actualizar(seasons=["2025"], competitions=["lfendesa"], delay=0)
        self.assertEqual(totales["scraped"], 1)

    def test_la_temporada_en_curso_cambia_en_septiembre(self):
        import datetime

        real_date = datetime.date

        class FakeDate(real_date):
            fixed = None

            @classmethod
            def today(cls):
                return cls.fixed

        datetime.date = FakeDate
        try:
            FakeDate.fixed = real_date(2026, 8, 19)   # agosto: sigue la 2025/2026
            self.assertEqual(main._temporada_en_curso(), "2025")
            FakeDate.fixed = real_date(2026, 9, 1)    # septiembre: arranca la 2026/2027
            self.assertEqual(main._temporada_en_curso(), "2026")
        finally:
            datetime.date = real_date


if __name__ == "__main__":
    unittest.main()
