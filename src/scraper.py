import requests
from bs4 import BeautifulSoup, FeatureNotFound
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
import html as html_lib
import re
import time
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.feb.es/competiciones"
API_URL = "https://intrafeb.feb.es/LiveStats.API/api/v1"

# Prefijo de los controles WebForms en resultados.aspx. Los <select> de
# temporada/grupo/jornada son postbacks de ASP.NET: hay que reenviar el
# __VIEWSTATE de la pagina para que el servidor devuelva otra seleccion.
CTL_PREFIX = "_ctl0:MainContentPlaceHolderMaster:"
FIELD_SEASON = CTL_PREFIX + "temporadasDropDownList"
FIELD_GROUP = CTL_PREFIX + "gruposDropDownList"
FIELD_JOURNEY = CTL_PREFIX + "jornadasDropDownList"
STATE_FIELDS = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")


@dataclass
class PlayerStats:
    jersey: int
    name: str
    player_id: str
    minutes: float
    points: int
    two_points_made: int
    two_points_attempted: int
    three_points_made: int
    three_points_attempted: int
    free_throws_made: int
    free_throws_attempted: int
    offensive_rebounds: int
    defensive_rebounds: int
    total_rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int
    fouls: int
    plus_minus: int
    efficiency: int


@dataclass
class Game:
    id: int
    date: str
    game_time: str
    venue: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    home_stats: List[PlayerStats] = field(default_factory=list)
    away_stats: List[PlayerStats] = field(default_factory=list)
    play_by_play: List[Dict[str, Any]] = field(default_factory=list)
    shots: List[Dict[str, Any]] = field(default_factory=list)
    team_stats: Dict[str, Any] = field(default_factory=dict)


class FEBBasketballScraper:
    
    def __init__(self, delay: float = 1.0, retries: int = 3):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        # Reintentos con backoff: al recorrer miles de partidos, un corte puntual
        # o un 5xx no debe abortar el escaneo completo.
        adapter = HTTPAdapter(max_retries=Retry(
            total=retries, backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"], raise_on_status=False))
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.delay = delay
        self._token: Optional[str] = None

    @staticmethod
    def _parse(markup: str) -> BeautifulSoup:
        """lxml si esta disponible; si no, el parser de la stdlib."""
        try:
            return BeautifulSoup(markup, 'lxml')
        except FeatureNotFound:
            return BeautifulSoup(markup, 'html.parser')

    def _get(self, url: str) -> BeautifulSoup:
        time.sleep(self.delay)
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return self._parse(response.text)

    def _get_bearer_token(self, refresh: bool = False) -> Optional[str]:
        """Token Bearer de la API interna, cacheado durante toda la sesion.

        Antes se pedia una vez por partido, lo que anadia una peticion HTTP
        extra a cada uno de los miles de partidos del historico.
        """
        if self._token and not refresh:
            return self._token
        page = self.session.get("https://www.feb.es/competiciones/partido/0", timeout=20)
        match = re.search(r'id="_ctl0_token" value="([^"]+)"', page.text)
        self._token = match.group(1) if match else None
        return self._token

    def get_api_data(self, endpoint: str, game_id: int, token: Optional[str] = None) -> Dict[str, Any]:
        if not token:
            token = self._get_bearer_token()
            if not token:
                raise RuntimeError("No se pudo obtener el token Bearer de la pagina")
        url = f"{API_URL}/{endpoint}/{game_id}"
        response = self.session.get(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Referer': f'{BASE_URL}/partido/{game_id}',
                'X-Requested-With': 'XMLHttpRequest'
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def _api_section(self, game_id: int, endpoint: str) -> Dict[str, Any]:
        """Pide un endpoint de la API interna tolerando fallos.

        Un 404 es normal (partido aun no jugado) y un 401 significa que el token
        cacheado ha caducado, en cuyo caso se renueva y se reintenta una vez.
        Devuelve {} si no hay datos: la ficha del partido se conserva igual.
        """
        for attempt in (1, 2):
            try:
                return self.get_api_data(endpoint, game_id, self._get_bearer_token())
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 401 and attempt == 1:
                    logger.debug(f"Token caducado en {endpoint}, renovando")
                    self._get_bearer_token(refresh=True)
                    continue
                logger.warning(f"{endpoint} partido {game_id}: HTTP {status}")
                return {}
            except Exception as e:
                logger.warning(f"{endpoint} partido {game_id}: {e}")
                return {}
        return {}

    def get_game_links(self, competition_id: int, season_year: str = '2026') -> List[str]:
        url = f"{self.base_url}/resultados.aspx?g={competition_id}&t={season_year}"
        soup = self._get(url)
        
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'Partido.aspx?p=' in href:
                p_id = re.search(r'p=(\d+)', href)
                if p_id:
                    links.add(f"{self.base_url}/Partido.aspx?p={p_id.group(1)}")
        
        return list(links)

    def _results_url(self, competition_id: int, season_year: str) -> str:
        return f"{self.base_url}/resultados.aspx?g={competition_id}&t={season_year}"

    def _get_html(self, url: str) -> str:
        time.sleep(self.delay)
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _form_state(page_html: str) -> Dict[str, str]:
        """Extrae los campos ocultos que ASP.NET exige reenviar en cada postback."""
        state = {}
        for name in STATE_FIELDS:
            match = (re.search(rf'name="{name}"[^>]*value="([^"]*)"', page_html)
                     or re.search(rf'id="{name}"[^>]*value="([^"]*)"', page_html))
            state[name] = match.group(1) if match else ''
        return state

    @staticmethod
    def _select_options(page_html: str, select_key: str) -> List[Tuple[str, str]]:
        """Devuelve [(value, texto)] del <select> cuyo name contiene select_key."""
        block = re.search(
            rf'<select[^>]*name="[^"]*{select_key}[^"]*"[^>]*>(.*?)</select>',
            page_html, re.S | re.I)
        if not block:
            return []
        options = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>',
                             block.group(1))
        return [(v, html_lib.unescape(t).strip()) for v, t in options if v]

    def _postback(self, url: str, page_html: str, target: str,
                  fields: Dict[str, str]) -> str:
        """Simula el cambio de un <select> con autopostback y devuelve el HTML."""
        data = self._form_state(page_html)
        data.update({"__EVENTTARGET": target, "__EVENTARGUMENT": "", "__LASTFOCUS": ""})
        data.update(fields)
        time.sleep(self.delay)
        response = self.session.post(url, data=data, timeout=30)
        response.raise_for_status()
        return response.text

    def _extract_game_ids(self, page_html: str) -> List[str]:
        """IDs de partido en orden de aparicion, sin duplicados."""
        return list(dict.fromkeys(re.findall(r'Partido\.aspx\?p=(\d+)', page_html)))

    def get_groups(self, competition_id: int, season_year: str) -> List[Tuple[str, str]]:
        """Lista los grupos disponibles de una competicion/temporada: [(id, nombre)].

        Permite descubrir los ids del selector sin tenerlos codificados a mano,
        de modo que sirve para cualquier competicion y cualquier temporada.
        """
        page_html = self._get_html(self._results_url(competition_id, season_year))
        return self._select_options(page_html, 'grupos')

    def get_seasons(self, competition_id: int) -> List[Tuple[str, str]]:
        """Lista las temporadas disponibles de una competicion: [(año, etiqueta)]."""
        page_html = self._get_html(self._results_url(competition_id, '2025'))
        return self._select_options(page_html, 'temporadas')

    def get_game_links_by_group(self, competition_id: int, season_year: str,
                                group_id: str, max_journeys: int = None) -> List[str]:
        """Obtiene TODOS los partidos de un grupo recorriendo sus jornadas.

        resultados.aspx es un WebForm: al cargarlo solo muestra la jornada activa
        del grupo por defecto (2 partidos), no el historico. Para recorrerlo hay
        que encadenar dos postbacks:
          1. __EVENTTARGET=gruposDropDownList  -> fija el grupo y devuelve sus jornadas
          2. __EVENTTARGET=jornadasDropDownList -> fija cada jornada y lista sus partidos

        Una liga regular tiene 26 jornadas x ~7 partidos = ~182 por grupo.
        """
        url = self._results_url(competition_id, season_year)
        base_html = self._get_html(url)

        group_html = self._postback(url, base_html, FIELD_GROUP, {
            FIELD_SEASON: season_year,
            FIELD_GROUP: group_id,
        })

        journeys = [value for value, _ in self._select_options(group_html, 'jornadas')]
        if not journeys:
            logger.warning(
                f"Grupo {group_id} ({season_year}): sin jornadas en el selector, "
                f"se usan los partidos de la pagina del grupo")
            return [f"{self.base_url}/Partido.aspx?p={gid}"
                    for gid in self._extract_game_ids(group_html)]

        if max_journeys:
            journeys = journeys[:max_journeys]

        game_ids: Dict[str, None] = {}
        for index, journey_id in enumerate(journeys, 1):
            try:
                journey_html = self._postback(url, group_html, FIELD_JOURNEY, {
                    FIELD_SEASON: season_year,
                    FIELD_GROUP: group_id,
                    FIELD_JOURNEY: journey_id,
                })
            except requests.RequestException as e:
                logger.warning(f"Jornada {index}/{len(journeys)} grupo {group_id}: {e}")
                continue
            found = self._extract_game_ids(journey_html)
            logger.debug(f"Jornada {index}/{len(journeys)}: {len(found)} partidos")
            for gid in found:
                game_ids[gid] = None

        logger.info(f"Grupo {group_id} ({season_year}): {len(journeys)} jornadas, "
                    f"{len(game_ids)} partidos unicos")
        return [f"{self.base_url}/Partido.aspx?p={gid}" for gid in game_ids]
    
    def _safe_int(self, text: str, default: int = 0) -> int:
        try:
            text = text.strip()
            if not text:
                return default
            return int(text)
        except:
            return default
    
    def _safe_float(self, text: str, default: float = 0.0) -> float:
        try:
            text = text.strip().replace(',', '.')
            if not text:
                return default
            if ':' in text:
                parts = text.split(':')
                minutes = int(parts[0])
                seconds = int(parts[1])
                return round(minutes + seconds / 60, 2)
            return float(text)
        except:
            return default
    
    def _safe_shot(self, text: str) -> Tuple[int, int]:
        try:
            match = re.search(r'(\d+)/(\d+)', text.strip())
            if match:
                return int(match.group(1)), int(match.group(2))
        except:
            pass
        return 0, 0

    @staticmethod
    def _cell_direct_text(cell) -> str:
        return ''.join(cell.find_all(string=True, recursive=False)).strip()
    
    def _safe_reb(self, text: str) -> Tuple[int, int]:
        try:
            parts = text.strip().split('+')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except:
            pass
        return 0, 0
    
    def _parse_player_row(self, cells: List) -> Optional[PlayerStats]:
        try:
            if len(cells) < 20:
                return None
            
            jersey_text = cells[1].get_text(strip=True)
            if not jersey_text or not jersey_text[0].isdigit():
                return None

            jersey = int(jersey_text)

            name_link = cells[2].find('a')
            name = name_link.get_text(strip=True) if name_link else cells[2].get_text(strip=True)

            player_id = ''
            if name_link and name_link.get('href'):
                player_match = re.search(r'i=(\d+)', str(name_link['href']))
                if player_match:
                    player_id = f"{self.base_url}/Jugador.aspx?{player_match.group(1)}"

            return PlayerStats(
                jersey=jersey,
                name=name,
                player_id=player_id,
                minutes=self._safe_float(cells[3].get_text(strip=True)),
                points=self._safe_int(cells[4].get_text(strip=True)),
                two_points_made=self._safe_shot(self._cell_direct_text(cells[5]))[0],
                two_points_attempted=self._safe_shot(self._cell_direct_text(cells[5]))[1],
                three_points_made=self._safe_shot(self._cell_direct_text(cells[6]))[0],
                three_points_attempted=self._safe_shot(self._cell_direct_text(cells[6]))[1],
                free_throws_made=self._safe_shot(self._cell_direct_text(cells[8]))[0],
                free_throws_attempted=self._safe_shot(self._cell_direct_text(cells[8]))[1],
                offensive_rebounds=self._safe_int(cells[9].get_text(strip=True)),
                defensive_rebounds=self._safe_int(cells[10].get_text(strip=True)),
                total_rebounds=self._safe_int(cells[11].get_text(strip=True)),
                assists=self._safe_int(cells[12].get_text(strip=True)),
                steals=self._safe_int(cells[13].get_text(strip=True)),
                blocks=self._safe_int(cells[15].get_text(strip=True)),
                turnovers=self._safe_int(cells[14].get_text(strip=True)),
                fouls=self._safe_int(cells[18].get_text(strip=True)),
                plus_minus=self._safe_int(cells[21].get_text(strip=True)),
                efficiency=self._safe_int(cells[20].get_text(strip=True))
            )
        except Exception as e:
            logger.debug(f"Error parsing row: {e}")
            return None
    
    def scrape_game(self, game_url: str, include_api: bool = True) -> Optional[Game]:
        soup = self._get(game_url)

        text = soup.get_text(' ', strip=True)

        date_match = re.search(r'Fecha\s+(\d{2}/\d{2}/\d{4})', text)
        date = date_match.group(1) if date_match else ''

        time_match = re.search(r'Fecha\s+\d{2}/\d{2}/\d{4}\s*-\s*(\d{2}:\d{2})', text)
        game_time = time_match.group(1) if time_match else ''

        venue_match = re.search(r'Pista\s+([^\s]+(?:\s+[^\s]+)*?)(?=\s*%)', text)
        venue = venue_match.group(1).strip() if venue_match else ''

        team_links = []
        for a in soup.find_all('a', href=True):
            if 'Equipo.aspx?i=' in a['href'] and a.get_text(strip=True):
                team_links.append(a.get_text(strip=True))

        home_team = team_links[0] if team_links else ''
        away_team = team_links[1] if len(team_links) > 1 else ''

        home_score = 0
        away_score = 0
        if home_team and away_team:
            score_match = re.search(
                re.escape(home_team) + r'\s+(\d+)\s+p\s+(\d+)\s+' + re.escape(away_team),
                text
            )
            if score_match:
                home_score = int(score_match.group(1))
                away_score = int(score_match.group(2))

        id_match = re.search(r'(?:partido/|p=)(\d+)', game_url)
        game_id = int(id_match.group(1)) if id_match else 0

        home_stats = []
        away_stats = []
        tables = soup.find_all('table')
        for idx, table in enumerate(tables):
            stats_list = []
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if cells:
                    stats = self._parse_player_row(cells)
                    if stats:
                        stats_list.append(stats)
            if idx == 0:
                home_stats = stats_list
            else:
                away_stats = stats_list

        play_by_play = []
        shots = []
        team_stats = {}
        if include_api:
            if self._get_bearer_token():
                keyfacts = self._api_section(game_id, 'KeyFacts')
                play_by_play = keyfacts.get('PLAYBYPLAY', {}).get('LINES', [])
                shots = self._api_section(game_id, 'ShotChart').get('SHOTCHART', {}).get('SHOTS', [])
                team_stats = self._api_section(game_id, 'TeamStats').get('TEAMSTATS', {})

        return Game(
            id=game_id,
            date=date,
            game_time=game_time,
            venue=venue,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            home_stats=home_stats,
            away_stats=away_stats,
            play_by_play=play_by_play,
            shots=shots,
            team_stats=team_stats
        )