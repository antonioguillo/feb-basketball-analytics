"""Tests del scraper que no tocan la red.

Cubren el fallo que hacia inservible el historico: resultados.aspx es un
WebForm y, si no se encadenan los postbacks de grupo y jornada, solo devuelve
los partidos de la jornada activa (2) en vez de los de todo el grupo (~175).

Ejecutar:  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import group_slug
from src.scraper import FEBBasketballScraper, FIELD_GROUP, FIELD_JOURNEY


LANDING_HTML = """
<input type="hidden" name="__VIEWSTATE" value="VS-LANDING" />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="GEN1" />
<input type="hidden" name="__EVENTVALIDATION" value="EV-LANDING" />
<select name="_ctl0:MainContentPlaceHolderMaster:temporadasDropDownList">
  <option value="2025">2025/2026</option>
  <option value="2024">2024/2025</option>
</select>
<select name="_ctl0:MainContentPlaceHolderMaster:gruposDropDownList">
  <option value="88891">Liga Regular &quot;E-A&quot;</option>
  <option value="88892">Liga Regular &quot;E-B&quot;</option>
</select>
<select name="_ctl0:MainContentPlaceHolderMaster:jornadasDropDownList">
  <option value="900">Jornada 30(01/06/2026)</option>
</select>
<a href="Partido.aspx?p=999001">ver</a>
"""

GROUP_HTML = """
<input type="hidden" name="__VIEWSTATE" value="VS-GROUP" />
<input type="hidden" name="__VIEWSTATEGENERATOR" value="GEN1" />
<input type="hidden" name="__EVENTVALIDATION" value="EV-GROUP" />
<select name="_ctl0:MainContentPlaceHolderMaster:jornadasDropDownList">
  <option value="662231">Jornada 1(05/10/2025)</option>
  <option value="662232">Jornada 2(12/10/2025)</option>
</select>
<a href="Partido.aspx?p=999001">ver</a>
"""


def journey_html(journey_id):
    """Cada jornada devuelve dos partidos distintos."""
    base = 1000 + int(journey_id) * 10
    return (f'<input name="__VIEWSTATE" value="VS-J" />'
            f'<a href="Partido.aspx?p={base}">a</a>'
            f'<a href="Partido.aspx?p={base + 1}">b</a>'
            f'<a href="Partido.aspx?p={base + 1}">duplicado</a>')


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    """Sustituye a requests.Session y registra los postbacks recibidos."""

    def __init__(self):
        self.headers = {}
        self.posts = []

    def mount(self, *_):
        pass

    def get(self, url, **kwargs):
        return FakeResponse(LANDING_HTML)

    def post(self, url, data=None, **kwargs):
        self.posts.append(data)
        target = data.get("__EVENTTARGET")
        if target == FIELD_GROUP:
            return FakeResponse(GROUP_HTML)
        return FakeResponse(journey_html(data[FIELD_JOURNEY]))


class GameLinksByGroupTest(unittest.TestCase):
    def setUp(self):
        self.scraper = FEBBasketballScraper(delay=0)
        self.session = FakeSession()
        self.scraper.session = self.session

    def test_recorre_todas_las_jornadas_del_grupo(self):
        links = self.scraper.get_game_links_by_group(3, '2025', '88891')

        # 2 jornadas x 2 partidos, sin el duplicado ni el de la pagina inicial.
        self.assertEqual(len(links), 4)
        self.assertTrue(all(link.startswith('https://www.feb.es/competiciones/Partido.aspx?p=')
                            for link in links))
        self.assertNotIn('999001', ' '.join(links),
                         "no debe devolver el partido de la jornada activa de la landing")

    def test_encadena_postback_de_grupo_y_de_jornada(self):
        self.scraper.get_game_links_by_group(3, '2025', '88891')

        targets = [post["__EVENTTARGET"] for post in self.session.posts]
        self.assertEqual(targets[0], FIELD_GROUP, "primero hay que fijar el grupo")
        self.assertEqual(targets[1:], [FIELD_JOURNEY] * 2, "luego una jornada por postback")

    def test_reenvia_el_viewstate_de_la_pagina_del_grupo(self):
        self.scraper.get_game_links_by_group(3, '2025', '88891')

        group_post, journey_post = self.session.posts[0], self.session.posts[1]
        self.assertEqual(group_post["__VIEWSTATE"], "VS-LANDING")
        self.assertEqual(journey_post["__VIEWSTATE"], "VS-GROUP",
                         "las jornadas se piden con el estado devuelto por el grupo")

    def test_max_journeys_limita_las_peticiones(self):
        self.scraper.get_game_links_by_group(3, '2025', '88891', max_journeys=1)

        journey_posts = [p for p in self.session.posts
                         if p["__EVENTTARGET"] == FIELD_JOURNEY]
        self.assertEqual(len(journey_posts), 1)


class SelectorParsingTest(unittest.TestCase):
    def setUp(self):
        self.scraper = FEBBasketballScraper(delay=0)

    def test_form_state(self):
        state = self.scraper._form_state(LANDING_HTML)
        self.assertEqual(state["__VIEWSTATE"], "VS-LANDING")
        self.assertEqual(state["__EVENTVALIDATION"], "EV-LANDING")

    def test_select_options_desescapa_entidades(self):
        options = self.scraper._select_options(LANDING_HTML, 'grupos')
        self.assertEqual(options, [('88891', 'Liga Regular "E-A"'),
                                   ('88892', 'Liga Regular "E-B"')])

    def test_extract_game_ids_sin_duplicados_y_en_orden(self):
        ids = self.scraper._extract_game_ids(journey_html('1'))
        self.assertEqual(ids, ['1010', '1011'])


class GroupSlugTest(unittest.TestCase):
    def test_entrecomillado(self):
        self.assertEqual(group_slug('Liga Regular "E-A"'), 'E-A')

    def test_sin_comillas_y_con_acento(self):
        self.assertEqual(group_slug('Liga Regular Único'), 'Unico')

    def test_nunca_vacio(self):
        self.assertEqual(group_slug('Liga Regular'), 'ungrouped')


if __name__ == '__main__':
    unittest.main()
