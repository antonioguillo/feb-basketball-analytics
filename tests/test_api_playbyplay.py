"""Comprueba la forma de los endpoints que salen del play-by-play enriquecido:
clutch, red de asistencias y disciplina de faltas.

Mismo mecanismo que test_api_contract.py (sustituir api.ch_query por filas de
mentira), pero en un archivo propio: las consultas nuevas no tienen nada que
ver con las de jugadores/equipos y mezclar los `_rows_for` de ambos habría
hecho frágil a los dos por el juego de coincidencias de subcadena.

Ejecutar:  python -m unittest tests.test_api_playbyplay -v
"""
import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api
from src.naming import display_name, player_slug, team_slug

COMPETITION = "tercerafeb"
TEAM = "THE FITZGERALD EL PILAR"
PASSER = "ROY CARNICER, DANIEL"
SCORER = "ALMIRALL CANALS, XAVIER"


def _rows_for(sql: str, params):
    if "SELECT 1" in sql:
        return [{"1": 1}]
    if "GROUP BY year" in sql:
        return [{"year": "2025"}]
    if "GROUP BY competition ORDER BY" in sql:
        return [{"competition": COMPETITION}]
    if "groupUniqArray(`group`) AS lista" in sql:
        return [{"partidos": "175", "fechas": "9", "lista": ["E-A"]}]

    # --- clutch --------------------------------------------------------
    if "SELECT player_name FROM clutch" in sql:
        return [{"n": "1"}]
    if "HAVING games >= {min_games:UInt8}" in sql:
        return [{
            "player_name": PASSER, "team": TEAM, "games": "4",
            "fga": "10", "fgm": "6", "fg3a": "4", "fg3m": "2",
            "fta": "5", "ftm": "4", "points": "18",
            "ast": "3", "tov": "2", "stl": "1", "blk": "0", "fouls": "2",
        }]

    # --- red de asistencias ---------------------------------------------
    if "pbp.assisted_by_name AS passer" in sql:
        return [{"passer": PASSER, "scorer": SCORER, "team": TEAM,
                 "assists": "12", "points": "26"}]
    if "SELECT DISTINCT team FROM" in sql:
        return [{"team": TEAM}, {"team": "RIVAL EQUIPO"}]

    # --- faltas ----------------------------------------------------------
    if "SELECT player_name, argMax(team, game_date) AS team," in sql:
        return [{"player_name": PASSER, "team": TEAM, "grupo": "E-A", "games": "20"}]
    if "SELECT pbp.player_name AS player_name, pbp.game_id AS game_id," in sql:
        return [
            {"player_name": PASSER, "game_id": "1", "personal_g": "3", "tecnica_g": "0", "descalificante_g": "0"},
            {"player_name": PASSER, "game_id": "2", "personal_g": "5", "tecnica_g": "1", "descalificante_g": "0"},
        ]
    if "UNION ALL" in sql:
        return [{"team": TEAM, "games": "20", "wins": "15",
                 "points_for": "1600", "points_against": "1400"}]

    raise AssertionError(f"consulta no prevista en el test:\n{sql}")


class FakeClickHouse:
    def __init__(self):
        self.queries = []

    async def __call__(self, sql, params=None):
        self.queries.append((sql, params))
        return _rows_for(sql, params)


class PlayByPlayContractTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeClickHouse()
        self._real = api.ch_query
        api.ch_query = self.fake
        api.invalidar_indice_slugs()

    def tearDown(self):
        api.ch_query = self._real

    def run_async(self, coro):
        return asyncio.run(coro)

    # --- clutch ----------------------------------------------------------

    def test_clutch_tiene_las_claves_del_frontend(self):
        result = self.run_async(api.clutch(season="2025", group=None))

        self.assertLessEqual({"meta", "definition", "players", "playersTotal", "playersOffset"}, set(result))
        for key in ("lastSeconds", "marginPoints", "minGames"):
            self.assertIn(key, result["definition"])

        player = result["players"][0]
        self.assertEqual(player["slug"], player_slug(PASSER))
        self.assertEqual(player["name"], display_name(PASSER))
        for key in ("shooting",):
            self.assertIn(key, player)
        self.assertEqual(player["shooting"]["fgm"], 6)
        self.assertEqual(player["shooting"]["fga"], 10)
        self.assertAlmostEqual(player["shooting"]["fg"], 0.6, places=4)

    def test_clutch_no_interpola_los_umbrales(self):
        self.run_async(api.clutch(season="2025", group=None))
        for sql, params in self.fake.queries:
            if "clutch" in sql:
                self.assertIn("{secs:UInt16}", sql)
                self.assertIn("{margin:UInt8}", sql)

    # --- red de asistencias ------------------------------------------------

    def test_assist_network_tiene_las_claves_del_frontend(self):
        result = self.run_async(api.assist_network(season="2025", group=None))

        self.assertLessEqual({"meta", "team", "teamKey", "nodes", "edges"}, set(result))
        self.assertIsNone(result["team"])
        edge = result["edges"][0]
        self.assertEqual(edge["passerSlug"], player_slug(PASSER))
        self.assertEqual(edge["scorerSlug"], player_slug(SCORER))
        self.assertEqual(edge["assists"], 12)
        self.assertEqual(edge["points"], 26)

        nombres = {n["slug"]: n for n in result["nodes"]}
        self.assertEqual(nombres[player_slug(PASSER)]["assistsGiven"], 12)
        self.assertEqual(nombres[player_slug(SCORER)]["assistsReceived"], 12)
        self.assertEqual(nombres[player_slug(SCORER)]["pointsCreated"], 26)

    def test_assist_network_filtra_por_equipo(self):
        result = self.run_async(
            api.assist_network(season="2025", group=None, team=team_slug(TEAM)))
        self.assertEqual(result["team"], TEAM)
        self.assertEqual(result["teamKey"], team_slug(TEAM))
        # El equipo tiene que viajar como parámetro, nunca interpolado.
        for sql, params in self.fake.queries:
            if "pbp.assisted_by_name AS passer" in sql:
                self.assertIn("{team:String}", sql)
                self.assertEqual(params.get("team"), TEAM)

    def test_assist_network_equipo_desconocido_da_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_async(api.assist_network(season="2025", group=None, team="no-existe"))
        self.assertEqual(ctx.exception.status_code, 404)

    # --- faltas ------------------------------------------------------------

    def test_fouls_tiene_las_claves_del_frontend(self):
        result = self.run_async(api.fouls(season="2025", group=None))

        self.assertLessEqual({"meta", "foulOutThreshold", "players", "playersTotal",
                              "playersOffset", "teams"}, set(result))
        player = result["players"][0]
        self.assertEqual(player["slug"], player_slug(PASSER))
        # 2 partidos con falta: 3+5 personales, 0+1 técnicas
        self.assertEqual(player["personalFouls"], 8)
        self.assertEqual(player["technicalFouls"], 1)
        self.assertEqual(player["totalFouls"], 9)
        # El segundo partido llega a 5 personales: un partido eliminado.
        self.assertEqual(player["fouledOutGames"], 1)
        self.assertEqual(player["games"], 20)
        self.assertAlmostEqual(player["foulsPerGame"], 9 / 20, places=4)

        # El resumen por equipo se agrega en Python a partir de las mismas
        # filas por jugador/partido, no de una consulta aparte.
        team_row = result["teams"][0]
        self.assertEqual(team_row["team"], TEAM)
        self.assertEqual(team_row["teamKey"], team_slug(TEAM))
        self.assertEqual(team_row["totalFouls"], 9)
        self.assertEqual(team_row["games"], 20)

    def test_fouls_respeta_el_minimo_de_partidos(self):
        # Un jugador con menos partidos que el mínimo no debe aparecer, aunque
        # tenga faltas registradas en el play-by-play.
        def _con_pocos_partidos(sql, params):
            if "SELECT player_name, argMax(team, game_date) AS team," in sql:
                return [{"player_name": PASSER, "team": TEAM, "grupo": "E-A", "games": "1"}]
            return _rows_for(sql, params)

        async def _fake_ch_query(sql, params=None):
            return _con_pocos_partidos(sql, params)

        api.ch_query = _fake_ch_query
        result = self.run_async(api.fouls(season="2025", group=None))
        self.assertEqual(result["players"], [])


if __name__ == "__main__":
    unittest.main()
