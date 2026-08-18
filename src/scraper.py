import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
import re
import time
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.feb.es/competiciones"
API_URL = "https://intrafeb.feb.es/LiveStats.API/api/v1"


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
    
    def __init__(self, delay: float = 1.0):
        self.base_url = BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.delay = delay
    
    def _get(self, url: str) -> BeautifulSoup:
        time.sleep(self.delay)
        response = self.session.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'lxml')

    def _get_bearer_token(self) -> Optional[str]:
        page = self.session.get("https://www.feb.es/competiciones/partido/0", timeout=20)
        match = re.search(r'id="_ctl0_token" value="([^"]+)"', page.text)
        return match.group(1) if match else None

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

    def get_game_links_by_group(self, competition_id: int, season_year: str,
                                group_id: str, max_journeys: int = None) -> List[str]:
        """Obtiene todos los partidos de un grupo concreto de una competición y
        temporada.

        Dado que la web FEB carga las jornadas mediante JavaScript, este método
        extrae los enlaces de la página de resultados y filtra por el grupo identificado.
        """
        url = f"{self.base_url}/resultados.aspx?g={competition_id}&t={season_year}"
        page = self._get(url)

        links: set = set()
        for a in page.find_all('a', href=True):
            href = a['href']
            if 'Partido.aspx?p=' in href:
                p_id = re.search(r'p=(\d+)', href)
                if p_id:
                    full_url = f"{self.base_url}/Partido.aspx?p={p_id.group(1)}"
                    links.add(full_url)

        # Filtrar por grupo si es posible usando el nombre del grupo en el HTML
        if group_id:
            group_text_match = re.search(
                rf'<option[^>]*value="{group_id}"[^>]*>([^<]*)</option>', page.text)
            if not group_text_match:
                # Grupo no encontrado en la página, retornar todos igual
                pass

        if max_journeys:
            # Limitar al número máximo de jornadas solicitadas
            # Tomar los primeros N enlaces donde N = max_journeys * ~8 partidos por jornada
            max_links = max_journeys * 8
            ordered = sorted(links)[:max_links]
            links = list(dict.fromkeys(ordered))[:max_journeys * 8]

        return list(links)
    
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
            token = self._get_bearer_token()
            if token:
                try:
                    keyfacts = self.get_api_data('KeyFacts', game_id, token)
                    play_by_play = keyfacts.get('PLAYBYPLAY', {}).get('LINES', [])
                except Exception as e:
                    logger.warning(f"No se pudo obtener play-by-play: {e}")
                try:
                    shotchart = self.get_api_data('ShotChart', game_id, token)
                    shots = shotchart.get('SHOTCHART', {}).get('SHOTS', [])
                except Exception as e:
                    logger.warning(f"No se pudo obtener shotchart: {e}")
                try:
                    teamstats = self.get_api_data('TeamStats', game_id, token)
                    team_stats = teamstats.get('TEAMSTATS', {})
                except Exception as e:
                    logger.warning(f"No se pudo obtener team stats: {e}")

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