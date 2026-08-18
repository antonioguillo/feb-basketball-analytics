#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from src import Pipeline, COMPETITIONS, FEBBasketballScraper

def test_models():
    print("Testing models...")
    assert len(COMPETITIONS) > 0
    print(f"  Found {len(COMPETITIONS)} competitions")

def test_scraper():
    print("Testing scraper instantiation...")
    scraper = FEBBasketballScraper(delay=0.5)
    print("  Scraper created successfully")

def test_pipeline():
    print("Testing pipeline...")
    competition = COMPETITIONS['tercerafeb']
    pipeline = Pipeline(competition, data_dir='data')
    print(f"  Pipeline created for: {competition.name}")

def test_sample_data():
    import pandas as pd
    print("Loading sample data...")
    try:
        df = pd.read_parquet('data/processed/sample_games.parquet')
        print(f"  Loaded {len(df)} rows")
        print(f"  Columns: {list(df.columns)}")
    except FileNotFoundError:
        print("  Sample data not found, creating it...")
        import subprocess
        subprocess.run([sys.executable, 'notebooks/sample_data.py'])

if __name__ == '__main__':
    test_models()
    test_scraper()
    test_pipeline()
    test_sample_data()
    print("\nAll tests passed!")