#!/usr/bin/env python3
"""CLI del scraper FEB.

La lógica de scraping vive en `scraping.jobs`; este módulo solo interpreta los
argumentos de línea de comandos y despacha a la función correspondiente.

    python main.py partido <game_id> [--upload]
    python main.py liga <competition> [--upload] [--force] [--delay S] [--limit N]
    python main.py grupo-e [--upload] [--force] [--delay S] [--seasons X,Y] [--max-journeys N] [--limit N]
    python main.py historico <competition> [--upload] [--force] [--seasons X,Y] [--limit N] [--delay S] [--max-journeys N] [--all-groups] [--workers N]
    python main.py actualizar [--seasons X,Y] [--competitions X,Y] [--delay S] [--limit N] [--all-groups] [--workers N] [--categories X,Y]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import COMPETITIONS, Pipeline
from scraping import jobs
from scraping.jobs import actualizar, scrape_historico, _temporada_en_curso  # reexportados: usados por tests y por main()


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
        jobs.scrape_single_game(game_id, upload_raw='--upload' in sys.argv)
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'liga':
        competition_name = sys.argv[2] if len(sys.argv) > 2 else 'tercerafeb'
        jobs.scrape_league(
            competition_name,
            upload_raw='--upload' in sys.argv,
            force='--force' in sys.argv,
            limit=_flag_value(sys.argv, '--limit', int),
            delay=_flag_value(sys.argv, '--delay', float, 1.0),
        )
        return

    if len(sys.argv) > 1 and sys.argv[1] == 'grupo-e':
        seasons_arg = _flag_value(sys.argv, '--seasons')
        jobs.scrape_grupo_e(
            upload_raw='--upload' in sys.argv,
            force='--force' in sys.argv,
            limit=_flag_value(sys.argv, '--limit', int),
            delay=_flag_value(sys.argv, '--delay', float, 1.0),
            seasons=seasons_arg.split(',') if seasons_arg else [],
            max_journeys=_flag_value(sys.argv, '--max-journeys', int),
        )
        return

    # Sin subcomando: modo legado, pipeline local sobre `data/` sin pasar por MinIO.
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
