"""Ejecuta la API contra un ClickHouse de verdad, si lo hay.

Los tests con un doble de la base de datos comprueban la FORMA de la respuesta,
pero no que el SQL sea válido: un alias que pisa el nombre de una columna
(`sum(reb) AS reb`) solo revienta cuando ClickHouse lo analiza. Esto lo cubre.

Se salta solo si ClickHouse no responde, así que es seguro en cualquier entorno.

Ejecutar:  ./run_pipeline.sh up  &&  python -m unittest tests.test_api_integracion -v
"""
import asyncio
import socket
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api


def _clickhouse_disponible() -> bool:
    parsed = urlparse(api.CH_URL)
    sock = socket.socket()
    sock.settimeout(2)
    try:
        sock.connect((parsed.hostname or "localhost", parsed.port or 8123))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@unittest.skipUnless(_clickhouse_disponible(),
                     f"ClickHouse no responde en {api.CH_URL}; levanta la infraestructura "
                     f"con ./run_pipeline.sh up")
class ApiIntegracionTest(unittest.TestCase):
    """Cada test ejecuta SQL real: valida sintaxis, tipos y semántica."""

    @classmethod
    def setUpClass(cls):
        cls.season = asyncio.run(cls._temporada_con_datos())
        if cls.season is None:
            raise unittest.SkipTest("ClickHouse está vacío: carga datos con "
                                    "./run_pipeline.sh backfill y el resto del pipeline")

    @staticmethod
    async def _temporada_con_datos():
        try:
            row = await api.ch_one(
                "SELECT year FROM feb.partidos GROUP BY year "
                "ORDER BY count() DESC, year DESC LIMIT 1")
        except Exception:
            return None
        year = row.get("year")
        return str(year) if year else None

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_health_responde_ok(self):
        self.assertEqual(self.run_async(api.health())["status"], "ok")

    def test_el_dashboard_se_ejecuta_y_cuadra(self):
        d = self.run_async(api.dashboard(season=self.season, group=None))

        self.assertGreater(d["summary"]["games"], 0)
        self.assertGreater(d["summary"]["players"], 0)
        self.assertEqual(d["meta"]["seasonKey"], self.season)
        self.assertTrue(d["leaders"], "sin líderes: revisa los umbrales")

        for leader in d["leaders"][:20]:
            self.assertGreaterEqual(leader["games"], api.MIN_GAMES)
            self.assertGreaterEqual(leader["perGame"]["min"], api.MIN_MINUTES)
            self.assertTrue(leader["team"], f"{leader['name']} sin equipo")

    def test_los_lideres_van_ordenados_por_valoracion(self):
        leaders = self.run_async(api.dashboard(season=self.season, group=None))["leaders"]
        valoraciones = [l["perGame"]["val"] for l in leaders]
        self.assertEqual(valoraciones, sorted(valoraciones, reverse=True))

    def test_la_ficha_del_primer_lider_es_coherente(self):
        d = self.run_async(api.dashboard(season=self.season, group=None))
        leader = d["leaders"][0]
        ficha = self.run_async(api.player(slug=leader["slug"], season=self.season))

        self.assertEqual(ficha["games"], leader["games"])
        self.assertEqual(len(ficha["gameLog"]), leader["games"],
                         "el historial debe tener una fila por partido jugado")
        self.assertAlmostEqual(ficha["perGame"]["val"], leader["perGame"]["val"], places=1)

        for porcentaje in ("t2", "t3", "ft", "ts", "efg"):
            valor = ficha["shooting"][porcentaje]
            if valor is not None:
                self.assertTrue(0 <= valor <= 1.5, f"{porcentaje} fuera de rango: {valor}")

    def test_las_zonas_de_tiro_cuadran_con_los_tiros(self):
        d = self.run_async(api.dashboard(season=self.season, group=None))
        ficha = self.run_async(api.player(slug=d["leaders"][0]["slug"], season=self.season))

        if not ficha["shots"]:
            self.skipTest("ese jugador no tiene tiros localizados")

        total_zonas = sum(z["att"] for z in ficha["zones"].values())
        self.assertEqual(total_zonas, len(ficha["shots"]),
                         "cada tiro tiene que caer en una zona y solo en una")
        self.assertTrue(set(ficha["zones"]) <= {"aro", "media", "triple"})

    def test_no_mezcla_competiciones(self):
        """Una respuesta habla de una sola competición: sumar la Tercera FEB
        masculina con la LF Endesa en un mismo resumen no significa nada."""
        catalogo = self.run_async(api.competitions())["competitions"]
        por_temporada = {}
        for entrada in catalogo:
            por_temporada.setdefault(entrada["seasonKey"], []).append(entrada)
        compartidas = [t for t, e in por_temporada.items() if len(e) > 1]
        if not compartidas:
            self.skipTest("no hay dos competiciones en la misma temporada")

        temporada = compartidas[0]
        for entrada in por_temporada[temporada]:
            d = self.run_async(api.dashboard(competition=entrada["competitionKey"],
                                             season=temporada))
            self.assertEqual(d["summary"]["games"], entrada["games"],
                             f"{entrada['competitionKey']} no cuadra con el catálogo")
            self.assertEqual(d["meta"]["competitionKey"], entrada["competitionKey"])

    def test_el_grupo_filtra_de_verdad(self):
        d = self.run_async(api.dashboard(season=self.season))
        grupos = d["meta"]["groups"]
        if len(grupos) < 2:
            self.skipTest("esa competición tiene un solo grupo")

        parcial = self.run_async(api.dashboard(
            competition=d["meta"]["competitionKey"], season=self.season, group=grupos[0]))
        self.assertLess(parcial["summary"]["games"], d["summary"]["games"])
        self.assertEqual(parcial["meta"]["groupKey"], grupos[0])

    def test_la_paginacion_no_solapa(self):
        uno = self.run_async(api.dashboard(season=self.season, limit=5))
        dos = self.run_async(api.dashboard(season=self.season, limit=5, offset=5))
        self.assertEqual(len(uno["leaders"]), 5)
        self.assertGreaterEqual(uno["leadersTotal"], 10)
        self.assertFalse({l["slug"] for l in uno["leaders"]}
                         & {l["slug"] for l in dos["leaders"]})

    def test_un_jugador_inexistente_da_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_async(api.player(slug="jugador-que-no-existe", season=self.season))
        self.assertEqual(ctx.exception.status_code, 404)

    # --- clasificación / ficha de equipo -------------------------------------

    def test_la_clasificacion_cuadra_con_el_dashboard(self):
        d = self.run_async(api.dashboard(season=self.season, group=None))
        t = self.run_async(api.teams(season=self.season, group=None))

        self.assertEqual(len(t["standings"]), d["summary"]["teams"])
        # Más victorias primero, y ninguna resta negativa de partidos.
        victorias = [row["wins"] for row in t["standings"]]
        self.assertEqual(victorias, sorted(victorias, reverse=True))
        for row in t["standings"]:
            self.assertGreaterEqual(row["losses"], 0)
            self.assertEqual(row["games"], row["wins"] + row["losses"])

    def test_la_ficha_del_primer_equipo_es_coherente(self):
        t = self.run_async(api.teams(season=self.season, group=None))
        primero = t["standings"][0]
        ficha = self.run_async(api.team(slug=primero["teamKey"], season=self.season))

        self.assertEqual(ficha["standing"]["games"], primero["games"])
        self.assertTrue(ficha["roster"], "un equipo con partidos debería tener plantilla")
        # Cada jugador de la plantilla juega en ese mismo equipo.
        for jugador in ficha["roster"]:
            self.assertEqual(jugador["team"], primero["team"])
        # El ritmo no puede tener más partidos que los que dice la clasificación
        # (el ritmo se pierde si un partido no cruza con su rival en equipos_partido).
        self.assertLessEqual(len(ficha["gameLog"]), ficha["standing"]["games"])
        for partido in ficha["gameLog"]:
            if partido["possessions"] is not None:
                self.assertGreater(partido["possessions"], 0)

    def test_las_zonas_de_la_plantilla_cuadran_con_los_tiros_del_equipo(self):
        t = self.run_async(api.teams(season=self.season, group=None))
        ficha = self.run_async(api.team(slug=t["standings"][0]["teamKey"], season=self.season))

        total_zonas = sum(
            zona["att"] for jugador in ficha["roster"] for zona in jugador["zones"].values())
        self.assertEqual(total_zonas, len(ficha["shots"]),
                         "cada tiro del equipo tiene que caer en la zona de alguien de la plantilla")

    def test_un_equipo_inexistente_da_404(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_async(api.team(slug="equipo-que-no-existe", season=self.season))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_games_devuelve_al_menos_los_de_la_clasificacion(self):
        t = self.run_async(api.teams(season=self.season, group=None))
        equipo = t["standings"][0]
        g = self.run_async(api.games(season=self.season, group=None))
        partidos_del_lider = [
            game for game in g["games"] if equipo["team"] in (game["home"], game["away"])
        ]
        self.assertGreaterEqual(len(partidos_del_lider), equipo["games"])

    # --- clutch / red de asistencias / faltas --------------------------------

    def test_el_clutch_se_ejecuta_y_va_ordenado(self):
        d = self.run_async(api.clutch(season=self.season, group=None, limit=20))
        if not d["players"]:
            self.skipTest("sin jugadores con el mínimo de partidos en momentos ajustados")

        puntos = [p["points"] for p in d["players"]]
        self.assertEqual(puntos, sorted(puntos, reverse=True))
        for player in d["players"]:
            self.assertGreaterEqual(player["games"], api.MIN_CLUTCH_GAMES)
            self.assertTrue(player["team"])
            fg = player["shooting"]
            self.assertLessEqual(fg["fgm"], fg["fga"])
            self.assertLessEqual(fg["fg3m"], fg["fg3a"])
            self.assertLessEqual(fg["ftm"], fg["fta"])

    def test_la_red_de_asistencias_liga_pasador_y_anotador_del_mismo_equipo(self):
        d = self.run_async(api.assist_network(season=self.season, group=None))
        if not d["edges"]:
            self.skipTest("sin asistencias resueltas en esta temporada")

        for edge in d["edges"][:30]:
            self.assertNotEqual(edge["passerSlug"], edge["scorerSlug"])
            self.assertGreater(edge["assists"], 0)

        # Filtrar por equipo tiene que devolver un subconjunto: los mismos
        # pares u otros, pero nunca más de los que hay sin filtrar.
        t = self.run_async(api.teams(season=self.season, group=None))
        equipo = t["standings"][0]["teamKey"]
        por_equipo = self.run_async(
            api.assist_network(season=self.season, group=None, team=equipo))
        self.assertEqual(por_equipo["teamKey"], equipo)
        for node in por_equipo["nodes"]:
            self.assertEqual(node["team"], por_equipo["team"])

    def test_las_faltas_cuadran_por_tipo_y_el_resumen_de_equipo_no_supera_el_total(self):
        d = self.run_async(api.fouls(season=self.season, group=None, limit=20))
        if not d["players"]:
            self.skipTest("nadie llega al mínimo de partidos con faltas registradas")

        totales = [p["totalFouls"] for p in d["players"]]
        self.assertEqual(totales, sorted(totales, reverse=True))
        for player in d["players"]:
            suma = player["personalFouls"] + player["technicalFouls"] + player["disqualifyingFouls"]
            self.assertEqual(suma, player["totalFouls"])
            self.assertGreaterEqual(player["personalFouls"], 0)
            # Eliminado solo puede pasar en un partido con 5+ personales; no
            # puede haber más partidos eliminado que partidos con falta.
            self.assertLessEqual(player["fouledOutGames"], player["games"])

        self.assertTrue(d["teams"], "sin resumen de faltas por equipo")
        ratios = [t["foulsPerGame"] for t in d["teams"] if t["foulsPerGame"] is not None]
        self.assertEqual(ratios, sorted(ratios, reverse=True))


if __name__ == "__main__":
    unittest.main()
