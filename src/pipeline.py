import pandas as pd
from pathlib import Path
from typing import List, Optional
from src.scraper import FEBBasketballScraper, Game
from src.models import Competition
from datetime import datetime


class Pipeline:
    
    def __init__(self, competition: Competition, data_dir: str = "data"):
        self.scraper = FEBBasketballScraper(delay=1.0)
        self.competition = competition
        self.data_dir = Path(data_dir)
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def find_games_to_scrap(self) -> List[str]:
        game_links = self.scraper.get_game_links(
            self.competition.id,
            self.competition.year
        )
        return game_links
    
    def scrap_all_games(self) -> List[Game]:
        game_urls = self.find_games_to_scrap()
        games = []
        
        for url in game_urls:
            try:
                game = self.scraper.scrape_game(url)
                if game:
                    games.append(game)
            except Exception as e:
                print(f"Error scraping {url}: {e}")
        
        return games
    
    def save_games_to_parquet(self, games: List[Game]) -> str:
        rows = []
        for game in games:
            base_row = {
                'game_id': game.id,
                'date': game.date,
                'time': game.game_time,
                'venue': game.venue,
                'home_team': game.home_team,
                'away_team': game.away_team,
                'home_score': game.home_score,
                'away_score': game.away_score,
                'competition': self.competition.name
            }
            
            for stat in game.home_stats:
                row = {
                    **base_row,
                    'team': game.home_team,
                    'is_home': True,
                    'player_jersey': stat.jersey,
                    'player_name': stat.name,
                    'minutes': stat.minutes,
                    'points': stat.points,
                    'two_points_made': stat.two_points_made,
                    'two_points_attempted': stat.two_points_attempted,
                    'three_points_made': stat.three_points_made,
                    'three_points_attempted': stat.three_points_attempted,
                    'free_throws_made': stat.free_throws_made,
                    'free_throws_attempted': stat.free_throws_attempted,
                    'total_rebounds': stat.total_rebounds,
                    'assists': stat.assists,
                    'steals': stat.steals,
                    'blocks': stat.blocks,
                    'turnovers': stat.turnovers,
                    'efficiency': stat.efficiency,
                    'plus_minus': stat.plus_minus
                }
                rows.append(row)
            
            for stat in game.away_stats:
                row = {
                    **base_row,
                    'team': game.away_team,
                    'is_home': False,
                    'player_jersey': stat.jersey,
                    'player_name': stat.name,
                    'minutes': stat.minutes,
                    'points': stat.points,
                    'two_points_made': stat.two_points_made,
                    'two_points_attempted': stat.two_points_attempted,
                    'three_points_made': stat.three_points_made,
                    'three_points_attempted': stat.three_points_attempted,
                    'free_throws_made': stat.free_throws_made,
                    'free_throws_attempted': stat.free_throws_attempted,
                    'total_rebounds': stat.total_rebounds,
                    'assists': stat.assists,
                    'steals': stat.steals,
                    'blocks': stat.blocks,
                    'turnovers': stat.turnovers,
                    'efficiency': stat.efficiency,
                    'plus_minus': stat.plus_minus
                }
                rows.append(row)
        
        df = pd.DataFrame(rows)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        import re
        safe_name = re.sub(r'[^a-z0-9_]+', '_', self.competition.name.lower())
        filename = f"games_{safe_name}_{timestamp}.parquet"
        filepath = self.processed_dir / filename
        df.to_parquet(filepath, index=False)
        
        return str(filepath)

    def save_single_game(self, game: Game) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_row = {
            'game_id': game.id,
            'date': game.date,
            'time': game.game_time,
            'venue': game.venue,
            'home_team': game.home_team,
            'away_team': game.away_team,
            'home_score': game.home_score,
            'away_score': game.away_score,
            'competition': 'partido_suelto'
        }

        rows = []
        for stat in game.home_stats:
            row = {**base_row, 'team': game.home_team, 'is_home': True, **self._stat_row(stat)}
            rows.append(row)
        for stat in game.away_stats:
            row = {**base_row, 'team': game.away_team, 'is_home': False, **self._stat_row(stat)}
            rows.append(row)

        df = pd.DataFrame(rows)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')

        filepath = self.processed_dir / f"game_{game.id}_{timestamp}.parquet"
        df.to_parquet(filepath, index=False)

        if game.play_by_play:
            pbp_df = self._play_by_play_to_df(game.play_by_play, base_row)
            pbp_df.to_parquet(self.processed_dir / f"game_{game.id}_playbyplay_{timestamp}.parquet", index=False)

        if game.shots:
            shots_df = self._shots_to_df(game.shots, base_row)
            shots_df.to_parquet(self.processed_dir / f"game_{game.id}_shots_{timestamp}.parquet", index=False)

        if game.team_stats:
            ts_df = self._team_stats_to_df(game.team_stats, base_row)
            ts_df.to_parquet(self.processed_dir / f"game_{game.id}_teamstats_{timestamp}.parquet", index=False)

        return str(filepath)

    def _play_by_play_to_df(self, lines: List[dict], base_row: dict) -> pd.DataFrame:
        rows = []
        for line in lines:
            row = {**base_row, **line}
            rows.append(row)
        return pd.DataFrame(rows)

    def _shots_to_df(self, shots: List[dict], base_row: dict) -> pd.DataFrame:
        rows = []
        for shot in shots:
            row = {**base_row, **shot}
            rows.append(row)
        return pd.DataFrame(rows)

    def _team_stats_to_df(self, team_stats: dict, base_row: dict) -> pd.DataFrame:
        rows = []
        for team in team_stats.get('TEAM', []):
            row = {**base_row, **team}
            rows.append(row)
        return pd.DataFrame(rows)

    @staticmethod
    def _stat_row(stat) -> dict:
        return {
            'player_jersey': stat.jersey,
            'player_name': stat.name,
            'minutes': stat.minutes,
            'points': stat.points,
            'two_points_made': stat.two_points_made,
            'two_points_attempted': stat.two_points_attempted,
            'three_points_made': stat.three_points_made,
            'three_points_attempted': stat.three_points_attempted,
            'free_throws_made': stat.free_throws_made,
            'free_throws_attempted': stat.free_throws_attempted,
            'total_rebounds': stat.total_rebounds,
            'assists': stat.assists,
            'steals': stat.steals,
            'blocks': stat.blocks,
            'turnovers': stat.turnovers,
            'efficiency': stat.efficiency,
            'plus_minus': stat.plus_minus
        }
    
    def run(self) -> str:
        games = self.scrap_all_games()
        return self.save_games_to_parquet(games)