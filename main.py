#!/usr/bin/env python3
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import Pipeline, COMPETITIONS, FEBBasketballScraper
from src.models import EBA_GROUP_E, group_slug


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

    SUPERADO por `historico` y `actualizar`, que descubren los grupos en la
    propia web en vez de depender de la tabla EBA_GROUP_E. Se mantiene porque
    fue lo que descargó el histórico inicial del grupo E.

    Sube a la misma taxonomía que el resto:
        competition=tercerafeb/year=<season>/group=<E-A|E-B>/game_id=<id>.json
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
                    for k in store.list_games(competition="tercerafeb")}

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
                            game, competition="tercerafeb", year=season, group=group_name)
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


_thread_local = threading.local()


def _scraper_del_hilo(delay: float) -> FEBBasketballScraper:
    """Un scraper por hilo: cada uno con su sesión HTTP y su token cacheado."""
    scraper = getattr(_thread_local, "scraper", None)
    if scraper is None:
        scraper = FEBBasketballScraper(delay=delay)
        _thread_local.scraper = scraper
    return scraper


def _descargar_partido(url: str, delay: float):
    """Devuelve (game_id, game). `game` es None si el partido no se ha jugado."""
    game_id = re.search(r'(?:partido/|p=)(\d+)', url).group(1)
    game = _scraper_del_hilo(delay).scrape_game(url)
    if not game or not (game.home_stats or game.away_stats):
        return game_id, None
    return game_id, game


def _descargar_lote(urls, delay: float, workers: int):
    """Descarga un lote de partidos, en paralelo si workers > 1.

    Con varios hilos el `delay` sigue aplicándose dentro de cada uno, así que
    el ritmo total contra feb.es es aproximadamente `workers / delay` peticiones
    por segundo. Conviene no pasarse: 8 hilos con delay 1 s ya son 8 req/s.
    """
    if workers <= 1:
        for url in urls:
            yield _descargar_partido(url, delay)
        return

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_descargar_partido, url, delay): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                yield future.result()
            except Exception as error:
                game_id = re.search(r'(?:partido/|p=)(\d+)', url).group(1)
                raise RuntimeError(f"partido {game_id}: {error}") from error


def scrape_historico(competition_name: str, seasons: list = None, upload_raw: bool = False,
                     limit: int = None, force: bool = False, delay: float = 1.0,
                     max_journeys: int = None, only_regular: bool = True,
                     workers: int = 1):
    """Descarga el historico completo de una competicion.

    Descubre los grupos de cada temporada en el propio selector de la web (en vez
    de depender de ids codificados a mano) y recorre todas las jornadas de cada
    grupo. Sube cada partido a raw en:
        competition=<comp>/year=<temporada>/group=<slug>/game_id=<id>.json

    Es idempotente: consulta los ids ya presentes en raw y los omite salvo --force.
    """
    competition = COMPETITIONS.get(competition_name)
    if not competition:
        print(f"Competición no encontrada. Opciones: {list(COMPETITIONS.keys())}")
        sys.exit(1)

    scraper = FEBBasketballScraper(delay=delay)

    if not seasons:
        seasons = [year for year, _ in scraper.get_seasons(competition.id)]
        print(f"Temporadas detectadas en la web: {len(seasons)} ({seasons[0]}..{seasons[-1]})")

    store = None
    existing = set()
    if upload_raw:
        from src.raw_store import RawStore
        store = RawStore(endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"))
        if not force:
            existing = store.existing_game_ids(competition=competition_name)
            print(f"Partidos ya en raw para {competition_name}: {len(existing)}")

    scraped = skipped = failed = pending = 0
    for season in seasons:
        try:
            groups = scraper.get_groups(competition.id, season)
        except Exception as e:
            print(f"Temporada {season}: no se pudieron listar los grupos ({str(e)[:80]})")
            continue

        if only_regular:
            groups = [(gid, name) for gid, name in groups if 'Liga Regular' in name]
        if not groups:
            print(f"Temporada {season}: sin grupos que scrapear")
            continue

        print(f"\n=== Temporada {season} | {len(groups)} grupos ===")
        for group_id, group_name in groups:
            slug = group_slug(group_name)
            try:
                links = scraper.get_game_links_by_group(
                    competition.id, season, group_id, max_journeys=max_journeys)
            except Exception as e:
                print(f"  [{slug}] error listando partidos: {str(e)[:80]}")
                continue
            print(f"  [{slug}] {len(links)} partidos")

            pendientes = [u for u in links
                          if re.search(r'(?:partido/|p=)(\d+)', u).group(1) not in existing]
            skipped += len(links) - len(pendientes)
            if limit is not None:
                pendientes = pendientes[:max(0, limit - scraped)]

            try:
                for game_id, game in _descargar_lote(pendientes, delay, workers):
                    # Un partido sin estadísticas de jugador todavía no se ha
                    # jugado (o la FEB aún no ha publicado el acta). No se sube:
                    # si se subiera, quedaría en raw como "ya hecho" y no se
                    # volvería a bajar nunca cuando se dispute.
                    if game is None:
                        pending += 1
                        continue
                    if store:
                        store.upload_game(game, competition=competition_name,
                                          year=season, group=slug)
                        existing.add(game_id)
                    scraped += 1
                    if scraped % 50 == 0:
                        print(f"    ... {scraped} descargados")
            except RuntimeError as error:
                print(f"    ERROR {str(error)[:120]}")
                failed += 1

            if limit is not None and scraped >= limit:
                print(f"\nLímite de {limit} partidos alcanzado.")
                return _resumen(competition_name, scraped, skipped, pending, failed)

    return _resumen(competition_name, scraped, skipped, pending, failed)


def _resumen(competition_name, scraped, skipped, pending, failed):
    print(f"\nResumen {competition_name}: {scraped} nuevos, {skipped} ya en raw, "
          f"{pending} sin jugar todavía, {failed} fallidos")
    return {"scraped": scraped, "skipped": skipped, "pending": pending, "failed": failed}


def actualizar(seasons: list = None, competitions: list = None, delay: float = 1.0,
               limit: int = None, include_playoffs: bool = False, workers: int = 1,
               categories: list = None):
    """Descarga lo que falte de una temporada, para ejecutar de forma recurrente.

    Pensado para la temporada en curso: recorre las competiciones absolutas,
    omite lo que ya está en raw y baja únicamente los partidos nuevos. Los que
    todavía no se han jugado no se guardan, así que la siguiente ejecución los
    recoge en cuanto la FEB publique el acta.

    Es seguro repetirlo: no reescribe nada de lo ya descargado.
    """
    from src.models import SENIOR_COMPETITIONS, competitions_by_category

    if not competitions:
        if categories:
            competitions = [c for cat in categories for c in competitions_by_category(cat)]
        else:
            competitions = SENIOR_COMPETITIONS
    seasons = seasons or [_temporada_en_curso()]
    print(f"Actualizando temporadas {seasons} · competiciones: {', '.join(competitions)}")

    totales = {"scraped": 0, "skipped": 0, "pending": 0, "failed": 0}
    for name in competitions:
        if name not in COMPETITIONS:
            print(f"  competición desconocida, se omite: {name}")
            continue
        print(f"\n=== {COMPETITIONS[name].name} ===")
        resultado = scrape_historico(
            name, seasons=seasons, upload_raw=True, delay=delay, limit=limit,
            only_regular=not include_playoffs, workers=workers)
        for key in totales:
            totales[key] += (resultado or {}).get(key, 0)

    print(f"\n{'=' * 52}")
    print(f"TOTAL: {totales['scraped']} partidos nuevos, {totales['skipped']} ya estaban, "
          f"{totales['pending']} sin jugar, {totales['failed']} fallidos")
    if totales["pending"]:
        print("Los partidos sin jugar se descargarán solos en la próxima ejecución.")
    return totales


def _temporada_en_curso() -> str:
    """Año de inicio de la temporada actual.

    La liga va de septiembre a mayo, así que de enero a agosto la temporada en
    curso empezó el año anterior.
    """
    from datetime import date
    today = date.today()
    return str(today.year if today.month >= 9 else today.year - 1)


def _flag_value(argv, flag, cast=str, default=None):
    """Lee '--flag valor' de argv sin depender del orden."""
    if flag not in argv:
        return default
    index = argv.index(flag) + 1
    return cast(argv[index]) if index < len(argv) else default


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'actualizar':
        seasons_arg = _flag_value(sys.argv, '--seasons')
        comps_arg = _flag_value(sys.argv, '--competitions')
        actualizar(
            seasons=seasons_arg.split(',') if seasons_arg else None,
            competitions=comps_arg.split(',') if comps_arg else None,
            delay=_flag_value(sys.argv, '--delay', float, 1.0),
            limit=_flag_value(sys.argv, '--limit', int),
            include_playoffs='--all-groups' in sys.argv,
            workers=_flag_value(sys.argv, '--workers', int, 1),
            categories=(_flag_value(sys.argv, '--categories') or '').split(',') or None
                       if '--categories' in sys.argv else None,
        )
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'historico':
        competition_name = sys.argv[2] if len(sys.argv) > 2 else 'tercerafeb'
        seasons_arg = _flag_value(sys.argv, '--seasons')
        scrape_historico(
            competition_name,
            seasons=seasons_arg.split(',') if seasons_arg else None,
            upload_raw='--upload' in sys.argv,
            force='--force' in sys.argv,
            limit=_flag_value(sys.argv, '--limit', int),
            delay=_flag_value(sys.argv, '--delay', float, 1.0),
            max_journeys=_flag_value(sys.argv, '--max-journeys', int),
            only_regular='--all-groups' not in sys.argv,
            workers=_flag_value(sys.argv, '--workers', int, 1),
        )
        return

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