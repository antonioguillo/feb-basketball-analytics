#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import Pipeline, COMPETITIONS, FEBBasketballScraper
from src.models import EBA_GROUP_E


def scrape_single_game(game_id: str, upload_raw: bool = False, competition: str = "partido_suelto"):
    url = f"https://www.feb.es/competiciones/partido/{game_id}"
    scraper = FEBBasketballScraper(delay=1.0)
    game = scraper.scrape_game(url)

    if not game:
        print(f"No se pudo scrappear el partido {game_id}")
        sys.exit(1)

    print(f"Partido {game.id} | {game.date} {game.game_time}")
    print(f"{game.home_team} {game.home_score} - {game.away_score} {game.away_team}")
    print(f"Pista: {game.venue}")
    print(f"\nJugadores locales ({len(game.home_stats)}):")
    for p in game.home_stats:
        print(f"  #{p.jersey} {p.name} | PT {p.points} | T2 {p.two_points_made}/{p.two_points_attempted} | T3 {p.three_points_made}/{p.three_points_attempted} | TL {p.free_throws_made}/{p.free_throws_attempted} | RT {p.total_rebounds} | AS {p.assists} | VA {p.efficiency}")
    print(f"\nJugadores visitantes ({len(game.away_stats)}):")
    for p in game.away_stats:
        print(f"  #{p.jersey} {p.name} | PT {p.points} | T2 {p.two_points_made}/{p.two_points_attempted} | T3 {p.three_points_made}/{p.three_points_attempted} | TL {p.free_throws_made}/{p.free_throws_attempted} | RT {p.total_rebounds} | AS {p.assists} | VA {p.efficiency}")

    pipeline = Pipeline(None, data_dir='data')
    filepath = pipeline.save_single_game(game)
    print(f"\nDatos guardados en: {filepath}")

    if upload_raw:
        from src.raw_store import RawStore
        year = game.date[-4:] if len(game.date) == 10 else "2026"
        store = RawStore(endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"))
        key = store.upload_game(game, competition=competition, year=year)
        print(f"Capa RAW actualizada: {key}")


def scrape_league(competition_name: str, upload_raw: bool = False, limit: int = None,
                  force: bool = False, delay: float = 1.0):
    """Escanea una competición completa: obtiene los partidos, los scrapea
    (con play-by-play, tiros y stats) y los sube a la capa raw de MinIO.

    Idempotente por defecto: omite partidos ya presentes en raw a menos que --force.
    """
    competition = COMPETITIONS.get(competition_name)
    if not competition:
        print(f"Competición no encontrada. Opciones: {list(COMPETITIONS.keys())}")
        sys.exit(1)

    print(f"Escaneando competición: {competition.name}")
    scraper = FEBBasketballScraper(delay=delay)
    game_links = scraper.get_game_links(competition.id, competition.year)
    print(f"Partidos encontrados: {len(game_links)}")

    if limit:
        game_links = game_links[:limit]
        print(f"Aplicando límite: {limit} partidos")

    store = None
    if upload_raw:
        from src.raw_store import RawStore
        store = RawStore(endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"))

    scraped = skipped = failed = 0
    existing = set()
    if store and not force:
        existing = {key.rsplit("/", 1)[-1].replace("game_id=", "").replace(".json", "")
                    for key in store.list_games(competition=competition_name)}
    for i, url in enumerate(game_links, 1):
        game_id = re.search(r'(?:partido/|p=)(\d+)', url).group(1)

        if store and not force:
            if game_id in existing:
                print(f"[{i}/{len(game_links)}] Partido {game_id} ya en raw, omitido")
                skipped += 1
                continue

        try:
            game = scraper.scrape_game(url)
            if not game:
                print(f"[{i}/{len(game_links)}] Partido {game_id}: scrape fallido")
                failed += 1
                continue

            if upload_raw:
                year = game.date[-4:] if len(game.date) == 10 else competition.year
                key = store.upload_game(game, competition=competition_name, year=year)
                print(f"[{i}/{len(game_links)}] Partido {game_id}: {game.home_team} {game.home_score}-{game.away_score} {game.away_team} -> raw ({key})")
            else:
                print(f"[{i}/{len(game_links)}] Partido {game_id}: {game.home_team} {game.home_score}-{game.away_score} {game.away_team}")
            scraped += 1
        except Exception as e:
            print(f"[{i}/{len(game_links)}] Partido {game_id}: ERROR {str(e)[:120]}")
            failed += 1

    print(f"\nResumen: {scraped} scrapeados, {skipped} omitidos (ya en raw), {failed} fallidos")


def scrape_grupo_e(upload_raw: bool = False, limit: int = None,
                   force: bool = False, delay: float = 1.0,
                   seasons: list = None, max_journeys: int = None):
    """Escanea el grupo E de la Tercera FEB / Liga EBA en las últimas temporadas.

    Por cada temporada y subgrupo (E-A, E-B) obtiene los partidos iterando por
    todas las jornadas, los scrapea (ficha + API interna) y los sube a raw con:
        competition=tercerafeb_e/year=<season>/group=<E-A|E-B>/game_id=<id>.json

    Los partidos se guardan incluso si la API interna falla (solo se conserva
    la ficha del partido).
    """
    seasons = seasons or sorted(EBA_GROUP_E.keys())
    print(f"Escaneando Grupo E - Tercera FEB/Liga EBA: temporadas {seasons}")

    scraper = FEBBasketballScraper(delay=delay)
    store = None
    if upload_raw:
        from src.raw_store import RawStore
        store = RawStore(endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"))

    # cache de parts ya sublaidos (idempotencia)
    existing = {}
    if store and not force:
        existing = {k.rsplit("/", 1)[-1].replace("game_id=", "").replace(".json", "")
                    for k in store.list_games(competition="tercerafeb_e")}

    total_scraped = total_skipped = total_failed = 0
    global_done = 0
    for season in seasons:
        season_cfg = EBA_GROUP_E[season]
        for group_name, group_id in season_cfg.groups.items():
            print(f"\n--- Temporada {season}/{int(season)+1} | Grupo {group_name} (id {group_id}) ---")
            game_links = scraper.get_game_links_by_group(3, season, group_id, max_journeys=max_journeys)
            print(f"Partidos encontrados: {len(game_links)}")

            if limit is not None:
                remaining = limit - global_done
                if remaining <= 0:
                    print("Límite alcanzado, termina escaneo.")
                    break
                game_links = game_links[:remaining]

            for url in game_links:
                game_id = re.search(r'(?:partido/|p=)(\d+)', url).group(1)

                if store and not force and game_id in existing:
                    print(f"Partido {game_id}: ya en raw, omitido")
                    total_skipped += 1
                    continue

                try:
                    game = scraper.scrape_game(url)
                    if not game or not (game.home_stats or game.away_stats):
                        print(f"Partido {game_id}: scrape fallido (ficha sin stats)")
                        total_failed += 1
                        global_done += 1
                        continue

                    total_scraped += 1
                    global_done += 1
                    if upload_raw:
                        key = store.upload_game(
                            game, competition="tercerafeb_e", year=season, group=group_name)
                        print(f"Partido {game_id}: {game.home_team} {game.home_score}-{game.away_score} {game.away_team} -> raw ({key})")
                    else:
                        print(f"Partido {game_id}: {game.home_team} {game.home_score}-{game.away_score} {game.away_team}")
                except Exception as e:
                    print(f"Partido {game_id}: ERROR {str(e)[:120]}")
                    total_failed += 1
                    global_done += 1

            if limit is not None and global_done >= limit:
                break
        if limit is not None and global_done >= limit:
            break

    print(f"\nResumen Grupo E: {total_scraped} scrapeados, {total_skipped} omitidos, {total_failed} fallidos")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'partido':
        game_id = sys.argv[2]
        upload = '--upload' in sys.argv
        scrape_single_game(game_id, upload_raw=upload)
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'liga':
        competition_name = sys.argv[2] if len(sys.argv) > 2 else 'tercerafeb'
        upload = '--upload' in sys.argv
        force = '--force' in sys.argv

        limit = None
        if '--limit' in sys.argv:
            idx = sys.argv.index('--limit')
            limit = int(sys.argv[idx + 1])

        delay = 1.0
        if '--delay' in sys.argv:
            idx = sys.argv.index('--delay')
            delay = float(sys.argv[idx + 1])

        scrape_league(competition_name, upload_raw=upload, limit=limit, force=force, delay=delay)
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'grupo-e':
        upload = '--upload' in sys.argv
        force = '--force' in sys.argv
        limit = None
        if '--limit' in sys.argv:
            idx = sys.argv.index('--limit')
            limit = int(sys.argv[idx + 1])
        delay = 1.0
        if '--delay' in sys.argv:
            idx = sys.argv.index('--delay')
            delay = float(sys.argv[idx + 1])
        seasons = []
        if '--seasons' in sys.argv:
            idx = sys.argv.index('--seasons')
            seasons = sys.argv[idx + 1].split(',')
        max_journeys = None
        if '--max-journeys' in sys.argv:
            idx = sys.argv.index('--max-journeys')
            max_journeys = int(sys.argv[idx + 1])
        scrape_grupo_e(upload_raw=upload, limit=limit, force=force, delay=delay,
                       seasons=seasons, max_journeys=max_journeys)
        return

    competition_name = sys.argv[1] if len(sys.argv) > 1 else 'tercerafeb'
    season = sys.argv[2] if len(sys.argv) > 2 else '2025'

    competition = COMPETITIONS.get(competition_name)
    if not competition:
        print(f"Competicion no encontrada. Opciones: {list(COMPETITIONS.keys())}")
        sys.exit(1)

    pipeline = Pipeline(competition, data_dir='data')
    filepath = pipeline.run()
    print(f"Datos guardados en: {filepath}")


if __name__ == '__main__':
    main()