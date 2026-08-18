import pandas as pd
import numpy as np
from pathlib import Path

def load_data(file_path: str) -> pd.DataFrame:
    return pd.read_parquet(file_path)

def calculate_team_stats(df: pd.DataFrame) -> pd.DataFrame:
    agg_funcs = {
        'points': 'sum',
        'two_points_made': 'sum',
        'two_points_attempted': 'sum',
        'three_points_made': 'sum',
        'three_points_attempted': 'sum',
        'free_throws_made': 'sum',
        'free_throws_attempted': 'sum',
        'total_rebounds': 'sum',
        'assists': 'sum',
        'steals': 'sum',
        'blocks': 'sum',
        'turnovers': 'sum',
        'minutes': 'sum'
    }
    
    team_stats = df.groupby(['team', 'date']).agg(agg_funcs).reset_index()
    team_stats['fg_made'] = team_stats['two_points_made'] + team_stats['three_points_made']
    team_stats['fg_attempted'] = team_stats['two_points_attempted'] + team_stats['three_points_attempted']
    team_stats['fg_percentage'] = np.where(
        team_stats['fg_attempted'] > 0,
        team_stats['fg_made'] / team_stats['fg_attempted'],
        0
    )
    team_stats['three_p_percentage'] = np.where(
        team_stats['three_points_attempted'] > 0,
        team_stats['three_points_made'] / team_stats['three_points_attempted'],
        0
    )
    team_stats['ft_percentage'] = np.where(
        team_stats['free_throws_attempted'] > 0,
        team_stats['free_throws_made'] / team_stats['free_throws_attempted'],
        0
    )
    team_stats['pace'] = team_stats['minutes'] / 40
    team_stats['efficiency'] = team_stats['points'] / team_stats['pace'].replace(0, 1)
    
    return team_stats

def calculate_player_career_stats(df: pd.DataFrame) -> pd.DataFrame:
    career_stats = df.groupby('player_name').agg({
        'points': 'sum',
        'two_points_made': 'sum',
        'two_points_attempted': 'sum',
        'three_points_made': 'sum',
        'three_points_attempted': 'sum',
        'free_throws_made': 'sum',
        'free_throws_attempted': 'sum',
        'total_rebounds': 'sum',
        'assists': 'sum',
        'steals': 'sum',
        'blocks': 'sum',
        'turnovers': 'sum',
        'minutes': 'sum',
        'efficiency': 'mean',
        'game_id': 'count'
    }).reset_index()
    
    career_stats.rename(columns={'game_id': 'games'}, inplace=True)
    
    career_stats['fg_made'] = career_stats['two_points_made'] + career_stats['three_points_made']
    career_stats['fg_attempted'] = career_stats['two_points_attempted'] + career_stats['three_points_attempted']
    career_stats['fg_percentage'] = np.where(
        career_stats['fg_attempted'] > 0,
        career_stats['fg_made'] / career_stats['fg_attempted'],
        0
    )
    career_stats['three_p_percentage'] = np.where(
        career_stats['three_points_attempted'] > 0,
        career_stats['three_points_made'] / career_stats['three_points_attempted'],
        0
    )
    career_stats['ft_percentage'] = np.where(
        career_stats['free_throws_attempted'] > 0,
        career_stats['free_throws_made'] / career_stats['free_throws_attempted'],
        0
    )
    career_stats['ppg'] = career_stats['points'] / career_stats['games']
    career_stats['rpg'] = career_stats['total_rebounds'] / career_stats['games']
    career_stats['apg'] = career_stats['assists'] / career_stats['games']
    career_stats['bpg'] = career_stats['blocks'] / career_stats['games']
    career_stats['spg'] = career_stats['steals'] / career_stats['games']
    
    return career_stats

def top_scorers(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    career_stats = calculate_player_career_stats(df)
    return career_stats.nlargest(n, 'points')[['player_name', 'games', 'points', 'ppg', 'fg_percentage', 'three_p_percentage', 'ft_percentage']]

def team_rankings(df: pd.DataFrame) -> pd.DataFrame:
    career_stats = calculate_player_career_stats(df)
    return career_stats.groupby('player_name')['games'].sum().count()