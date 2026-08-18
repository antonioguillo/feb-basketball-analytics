import pandas as pd

sample_data = [
    {'game_id': 1, 'date': '2026-04-18', 'time': '19:00', 'venue': 'PAL DEP ILLA BENIDORM',
     'home_team': 'SERVIGROUP BENIDORM', 'away_team': 'RIGALLI-ALGINET',
     'home_score': 88, 'away_score': 76, 'competition': 'Tercera FEB 2025/2026',
     'team': 'SERVIGROUP BENIDORM', 'is_home': True,
     'player_jersey': 2, 'player_name': 'DESPLACE, THIBAULT PIERRE ROBERT', 
     'minutes': 32.46, 'points': 16, 'two_points_made': 5, 'two_points_attempted': 10,
     'three_points_made': 0, 'three_points_attempted': 4,
     'free_throws_made': 6, 'free_throws_attempted': 9,
     'total_rebounds': 4, 'assists': 4, 'steals': 1, 'blocks': 2, 'turnovers': 0,
     'efficiency': 17, 'plus_minus': -11},
    {'game_id': 1, 'date': '2026-04-18', 'time': '19:00', 'venue': 'PAL DEP ILLA BENIDORM',
     'home_team': 'SERVIGROUP BENIDORM', 'away_team': 'RIGALLI-ALGINET',
     'home_score': 88, 'away_score': 76, 'competition': 'Tercera FEB 2025/2026',
     'team': 'RIGALLI-ALGINET', 'is_home': False,
     'player_jersey': 5, 'player_name': 'CHOJNACKI, MAKSYMILIAN MARCIN',
     'minutes': 2.83, 'points': 6, 'two_points_made': 0, 'two_points_attempted': 0,
     'three_points_made': 2, 'three_points_attempted': 3,
     'free_throws_made': 0, 'free_throws_attempted': 0,
     'total_rebounds': 0, 'assists': 0, 'steals': 1, 'blocks': 0, 'turnovers': 0,
     'efficiency': 5, 'plus_minus': 1},
]

df = pd.DataFrame(sample_data)
df.to_parquet('data/processed/sample_games.parquet', index=False)

print("Sample data saved to data/processed/sample_games.parquet")
print(df.head())