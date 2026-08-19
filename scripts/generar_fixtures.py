#!/usr/bin/env python3
"""Regenera los datos de ejemplo del frontend desde la API real.

`frontend/src/api/fixtures.json` es lo que la interfaz muestra cuando la API no
responde, y también la referencia contra la que los tests comprueban el
contrato. Escribirlo a mano lo condena a desfasarse: si el backend añade una
clave, el modo de ejemplo enseña una forma distinta justo cuando menos conviene
una sorpresa.

Este script llama a los endpoints en proceso —sin levantar uvicorn— y guarda la
respuesta tal cual, de modo que la fixture es por construcción idéntica a lo que
sirve la API.

Requiere ClickHouse levantado con datos:  ./run_pipeline.sh up

Uso:
    python scripts/generar_fixtures.py
    python scripts/generar_fixtures.py --competition lfendesa --season 2024
    python scripts/generar_fixtures.py --players 40
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import api

DESTINO = ROOT / "frontend" / "src" / "api" / "fixtures.json"


async def construir(competition, season, group, cuantos_jugadores):
    catalogo = await api.competitions()

    tablero = await api.dashboard(competition=competition, season=season, group=group,
                                  limit=api.LEADERS_MAX)
    meta = tablero["meta"]
    print(f"Dashboard: {meta['competition']} {meta['season']} · "
          f"{tablero['summary']['games']} partidos · {tablero['leadersTotal']} elegibles")

    contexto = dict(competition=meta["competitionKey"], season=meta["seasonKey"],
                    group=meta["groupKey"])

    fichas = {}
    for indice, lider in enumerate(tablero["leaders"][:cuantos_jugadores], 1):
        fichas[lider["slug"]] = await api.player(slug=lider["slug"], **contexto)
        if indice % 20 == 0:
            print(f"  fichas: {indice}/{min(cuantos_jugadores, len(tablero['leaders']))}")

    # Las claves de primer nivel replican la respuesta del dashboard para que la
    # capa de datos del frontend pueda usarla sin transformar nada.
    return {
        "meta": meta,
        "summary": tablero["summary"],
        "leaders": tablero["leaders"],
        "leadersTotal": tablero["leadersTotal"],
        "recentGames": tablero["recentGames"],
        "competitions": catalogo["competitions"],
        "players": fichas,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--competition", default=None)
    parser.add_argument("--season", default=None)
    parser.add_argument("--group", default=None)
    parser.add_argument("--players", type=int, default=60,
                        help="cuántas fichas completas se guardan (con sus tiros)")
    parser.add_argument("--out", default=str(DESTINO))
    args = parser.parse_args()

    datos = asyncio.run(construir(args.competition, args.season, args.group, args.players))

    destino = Path(args.out)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")

    tamano = destino.stat().st_size / 1024
    tiros = sum(len(f["shots"]) for f in datos["players"].values())
    print(f"\n{destino.relative_to(ROOT)}: {tamano:.0f} KB · "
          f"{len(datos['players'])} fichas · {tiros} tiros · "
          f"{len(datos['competitions'])} entradas de catálogo")


if __name__ == "__main__":
    main()
