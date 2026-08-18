"""Comprueba que la API devuelve exactamente la forma que consume el frontend.

No hace falta ClickHouse: se sustituye `api.ch_query` por filas equivalentes a
las que devolvería, y se compara la respuesta con `frontend/src/api/fixtures.json`,
que es la referencia del contrato. Así un cambio en el SQL que rompa una clave
del frontend falla aquí y no en el navegador.

Ejecutar:  python -m unittest tests.test_api_contract -v
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api
from src.naming import display_name, player_slug

FIXTURES = json.loads(
    (ROOT / "frontend" / "src" / "api" / "fixtures.json").read_text(encoding="utf-8")
)

# Un jugador real con tiros y varios partidos, tal y como sale del scraper.
RAW_NAME = "ORTEGA IBAÑEZ, ALEJANDRO"
TEAM = "THE FITZGERALD EL PILAR"


def _rows_for(sql: str, params):
    """Devuelve filas plausibles según la consulta que se esté haciendo.

    ClickHouse serializa los enteros de 64 bits como texto en JSON; aquí se
    reproduce a propósito para que el test cubra la conversión.
    """
    if "SELECT 1" in sql:
        return [{"1": 1}]
    if "max(year)" in sql:
        return [{"year": "2025"}]
    if "uniqExact(game_date)" in sql:
        return [{"journeys": "9"}]
    if "AS games," in sql and "AS teams," in sql:
        return [{"games": "63", "teams": "14", "players": "203", "shots": "8800"}]
    if "count() AS n" in sql:
        return [{"n": "175"}]
    if "GROUP BY player_name" in sql:
        return [{
            "player_name": RAW_NAME, "team": TEAM, "games": "9",
            "min": 30.0, "pts": 13.8, "reb": 8.3, "ast": 3.7, "val": 23.6,
            "stl": 2.1, "blk": 0.1, "to": 2.3, "plus_minus": 6.9,
            "t2m": "25", "t2a": "39", "t3m": "13", "t3a": "28",
            "ftm": "35", "fta": "46", "total_points": "124",
        }]
    if "ORDER BY game_date DESC" in sql:
        return [{
            "game_id": "2484526", "date": "04/10/2025",
            "home_team": "SOCAGE JOVENS L'ELIANA", "away_team": TEAM,
            "home_score": "77", "away_score": "78",
        }]
    if "DISTINCT player_name" in sql:
        return [{"player_name": RAW_NAME}, {"player_name": "OTRO JUGADOR, PEPE"}]
    if "best_val" in sql:
        return [{
            "team": TEAM, "jersey": "3", "games": "9",
            "min": 270.0, "pts": "124", "reb": "75", "ast": "33",
            "stl": "19", "blk": "1", "to": "21", "pf": "22", "val": "212",
            "t2m": "25", "t2a": "39", "t3m": "13", "t3a": "28",
            "ftm": "35", "fta": "46", "plus_minus": 6.9,
            "best_pts": "23", "best_reb": "17", "best_ast": "8", "best_val": "34",
        }]
    if "FROM feb.jugadores AS j" in sql and "INNER JOIN feb.partidos" in sql:
        return [{
            "game_id": "2484526", "date": "04/10/2025", "is_home": "0",
            "home_team": "SOCAGE JOVENS L'ELIANA", "away_team": TEAM,
            "home_score": "77", "away_score": "78",
            "minutes": 26.0, "points": "10", "reb": "3", "ast": "4", "val": "17",
        }]
    if "FROM feb.tiros" in sql:
        return [
            {"x": 12.5, "y": 50.0, "made": "1", "dist": 0.9, "zone": "aro"},
            {"x": 30.0, "y": 40.0, "made": "0", "dist": 5.2, "zone": "media"},
            {"x": 30.0, "y": 20.0, "made": "1", "dist": 7.4, "zone": "triple"},
        ]
    raise AssertionError(f"consulta no prevista en el test:\n{sql}")


class FakeClickHouse:
    def __init__(self):
        self.queries = []

    async def __call__(self, sql, params=None):
        self.queries.append((sql, params))
        return _rows_for(sql, params)


class ApiContractTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClickHouse()
        self._real = api.ch_query
        api.ch_query = self.fake

    def tearDown(self):
        api.ch_query = self._real

    def run_async(self, coro):
        return asyncio.run(coro)

    # --- dashboard ----------------------------------------------------------

    def test_dashboard_tiene_las_claves_del_frontend(self):
        result = self.run_async(api.dashboard(season="2025", group=None))

        self.assertEqual(set(result), {"meta", "summary", "leaders", "recentGames"})
        self.assertEqual(set(result["summary"]), set(FIXTURES["summary"]))
        for key in ("competition", "season", "seasonKey", "group", "groupKey",
                    "journeys", "groupTotalGames"):
            self.assertIn(key, result["meta"], f"falta meta.{key}")
        self.assertEqual(result["meta"]["season"], "2025/2026")

    def test_leaders_coinciden_con_el_contrato(self):
        leader = self.run_async(api.dashboard(season="2025", group=None))["leaders"][0]
        reference = FIXTURES["leaders"][0]

        self.assertEqual(set(leader), set(reference))
        self.assertEqual(set(leader["perGame"]) & set(reference["perGame"]),
                         set(reference["perGame"]))
        self.assertEqual(set(leader["shooting"]), set(reference["shooting"]))

    def test_leader_calcula_bien_el_tiro(self):
        leader = self.run_async(api.dashboard(season="2025", group=None))["leaders"][0]
        self.assertAlmostEqual(leader["shooting"]["t2"], 25 / 39, places=4)
        self.assertAlmostEqual(leader["shooting"]["t3"], 13 / 28, places=4)
        # eFG% = (FGM + 0.5*3PM) / FGA
        self.assertAlmostEqual(leader["shooting"]["efg"], (38 + 6.5) / 67, places=4)
        # TS% = PTS / (2*(FGA + 0.44*FTA))
        self.assertAlmostEqual(leader["shooting"]["ts"], 124 / (2 * (67 + 0.44 * 46)), places=4)

    def test_el_slug_del_leader_resuelve_su_ficha(self):
        leader = self.run_async(api.dashboard(season="2025", group=None))["leaders"][0]
        self.assertEqual(leader["slug"], player_slug(RAW_NAME))
        self.assertEqual(leader["name"], display_name(RAW_NAME))
        # El mismo slug tiene que servir para pedir la ficha
        ficha = self.run_async(api.player(slug=leader["slug"], season="2025"))
        self.assertEqual(ficha["slug"], leader["slug"])

    def test_recent_games_usan_los_nombres_de_equipo(self):
        game = self.run_async(api.dashboard(season="2025", group=None))["recentGames"][0]
        self.assertEqual(set(game), set(FIXTURES["recentGames"][0]))
        self.assertIsInstance(game["homeScore"], int)
        self.assertTrue(game["home"] and game["away"])

    # --- ficha de jugador ---------------------------------------------------

    def test_ficha_tiene_las_claves_del_frontend(self):
        result = self.run_async(api.player(slug=player_slug(RAW_NAME), season="2025"))
        reference = FIXTURES["players"][player_slug(RAW_NAME)]

        for key in reference:
            self.assertIn(key, result, f"falta {key} en la ficha")
        for group in ("perGame", "shooting", "per36", "bests"):
            self.assertEqual(set(reference[group]) - set(result[group]), set(),
                             f"faltan claves en {group}")
        self.assertEqual(set(reference["gameLog"][0]) - set(result["gameLog"][0]), set())
        self.assertEqual(set(reference["shots"][0]) - set(result["shots"][0]), set())

    def test_las_zonas_usan_las_claves_de_gold(self):
        result = self.run_async(api.player(slug=player_slug(RAW_NAME), season="2025"))
        self.assertEqual(set(result["zones"]), {"aro", "media", "triple"})
        self.assertEqual(result["zones"]["aro"], {"made": 1, "att": 1, "pct": 1.0})
        self.assertEqual(result["zones"]["media"]["pct"], 0.0)

    def test_el_game_log_identifica_al_rival_y_el_resultado(self):
        log = self.run_async(api.player(slug=player_slug(RAW_NAME), season="2025"))["gameLog"][0]
        # El jugador era visitante y su equipo ganó 78-77
        self.assertFalse(log["home"])
        self.assertEqual(log["opponent"], "SOCAGE JOVENS L'ELIANA")
        self.assertTrue(log["won"])
        self.assertEqual(log["score"], "77-78")

    def test_jugador_desconocido_da_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_async(api.player(slug="no-existe", season="2025"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_el_sql_nunca_interpola_valores(self):
        self.run_async(api.player(slug=player_slug(RAW_NAME), season="2025"))
        for sql, params in self.fake.queries:
            self.assertNotIn(RAW_NAME, sql,
                             "el nombre debe viajar como parámetro, no dentro del SQL")
            if "player_name = " in sql:
                self.assertIn("{name:String}", sql)


if __name__ == "__main__":
    unittest.main()
