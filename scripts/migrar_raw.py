#!/usr/bin/env python3
"""Limpia la capa raw y unifica la taxonomía de competiciones.

Hace dos cosas:

1. Retira los objetos sueltos que no encajan en el particionado:
   ficheros que no son partidos, fichas de encuentros que aún no se han jugado
   (el scraper antiguo las subía vacías, y quedaban marcadas como descargadas
   para siempre) y partidos guardados bajo claves ad-hoc como `partido_suelto`
   o `group=ungrouped`.

2. Traslada `competition=tercerafeb_e` a `competition=tercerafeb`, conservando
   temporada y grupo. La clave `_e` venía de un comando antiguo que solo bajaba
   el grupo E; hoy `historico` y `actualizar` usan la clave de la propia web,
   y tener las dos convivía mal.

Por defecto solo enseña el plan. Para ejecutarlo hay que pasar `--apply`.
Todo lo que se borra teniendo datos se guarda antes en disco.

Uso:
    python scripts/migrar_raw.py                 # plan, sin tocar nada
    python scripts/migrar_raw.py --apply
    python scripts/migrar_raw.py --apply --backup-dir data/backup_raw
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import boto3
from botocore.client import Config

CLAVE = re.compile(r"competition=([^/]+)/year=([^/]+)/group=([^/]+)/game_id=(\d+)\.json$")

# Competiciones que no son tales: las creaban comandos sueltos del scraper.
TAXONOMIA_INVALIDA = {"partido_suelto"}
GRUPO_INVALIDO = "ungrouped"

# Clave antigua -> clave de la web. El grupo y la temporada se conservan.
RENOMBRES = {"tercerafeb_e": "tercerafeb"}


def cliente(endpoint):
    return boto3.client(
        "s3", endpoint_url=f"http://{endpoint}",
        aws_access_key_id=os.environ.get("MINIO_ACCESS", "minioadmin"),
        aws_secret_access_key=os.environ.get("MINIO_SECRET", "minioadmin"),
        config=Config(signature_version="s3v4"), region_name="us-east-1")


def listar(s3, bucket):
    for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for objeto in pagina.get("Contents", []):
            yield objeto["Key"]


def tiene_estadisticas(s3, bucket, clave):
    cuerpo = s3.get_object(Bucket=bucket, Key=clave)["Body"].read()
    try:
        datos = json.loads(cuerpo)
    except ValueError:
        return False, None
    jugadores = len(datos.get("players_home") or []) + len(datos.get("players_away") or [])
    return jugadores > 0, cuerpo


def planificar(s3, bucket):
    """Devuelve (a_borrar, a_mover, indice_por_competicion)."""
    a_borrar, a_mover = [], []
    indice = defaultdict(set)

    for clave in listar(s3, bucket):
        coincidencia = CLAVE.match(clave)
        if not coincidencia:
            a_borrar.append((clave, "no es un partido particionado"))
            continue

        competicion, temporada, grupo, game_id = coincidencia.groups()
        indice[competicion].add(game_id)

        if competicion in TAXONOMIA_INVALIDA or grupo == GRUPO_INVALIDO:
            a_borrar.append((clave, f"taxonomía ad-hoc (competition={competicion}, group={grupo})"))
        elif competicion in RENOMBRES:
            destino = (f"competition={RENOMBRES[competicion]}/year={temporada}"
                       f"/group={grupo}/game_id={game_id}.json")
            a_mover.append((clave, destino))

    return a_borrar, a_mover, indice


def limpiar_marcadores(s3, aplicar, buckets=("bronze", "silver", "gold", "staging")):
    """Retira los objetos de cero bytes acabados en '/'.

    MinIO los crea para simular carpetas. Cuando VACUUM borra los parquet de una
    partición que ya no existe, el marcador se queda, y al listar el bucket
    parece que sigue habiendo datos de una competición retirada. No los lee
    nadie: Delta se guía por su log, no por el árbol de directorios.
    """
    total = 0
    for bucket in buckets:
        vacios = []
        try:
            paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket)
            for pagina in paginas:
                for objeto in pagina.get("Contents", []):
                    if objeto["Size"] == 0 and objeto["Key"].endswith("/"):
                        vacios.append(objeto["Key"])
        except s3.exceptions.NoSuchBucket:
            continue

        if not vacios:
            print(f"{bucket}: sin marcadores vacíos")
            continue
        print(f"{bucket}: {len(vacios)} marcadores vacíos")
        for clave in vacios[:4]:
            print(f"    {clave}")
        if len(vacios) > 4:
            print(f"    ... y {len(vacios) - 4} más")
        total += len(vacios)

        if aplicar:
            for clave in vacios:
                s3.delete_object(Bucket=bucket, Key=clave)

    if aplicar:
        print(f"\nRetirados {total} marcadores.")
    else:
        print(f"\n{total} marcadores a retirar (añade --apply para hacerlo)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="ejecuta los cambios")
    parser.add_argument("--endpoint", default=os.environ.get("MINIO_ENDPOINT", "localhost:9000"))
    parser.add_argument("--bucket", default="raw")
    parser.add_argument("--backup-dir", default="data/backup_raw",
                        help="dónde guardar lo que se borre teniendo datos")
    parser.add_argument("--limpiar-marcadores", action="store_true",
                        help="retira de bronze/silver/gold los marcadores de "
                             "directorio vacíos que deja MinIO tras un VACUUM")
    args = parser.parse_args()

    if args.limpiar_marcadores:
        limpiar_marcadores(cliente(args.endpoint), args.apply)
        return

    s3 = cliente(args.endpoint)
    a_borrar, a_mover, indice = planificar(s3, args.bucket)

    print(f"Contenido actual de {args.bucket}:")
    for competicion, ids in sorted(indice.items()):
        print(f"  {competicion:<18}{len(ids):>6} partidos")

    # Un traslado solo es seguro si el destino no tiene ya ese partido.
    colisiones = []
    for origen, destino in a_mover:
        competicion_destino = CLAVE.match(destino).group(1)
        game_id = CLAVE.match(destino).group(4)
        if game_id in indice.get(competicion_destino, set()):
            colisiones.append((origen, destino))
    if colisiones:
        print(f"\nABORTA: {len(colisiones)} partidos ya existen en el destino.")
        for origen, destino in colisiones[:5]:
            print(f"  {origen}\n    -> {destino}")
        sys.exit(1)

    print(f"\nA BORRAR ({len(a_borrar)}):")
    con_datos = []
    for clave, motivo in a_borrar:
        if clave.endswith(".json"):
            tiene, cuerpo = tiene_estadisticas(s3, args.bucket, clave)
            estado = "CON DATOS" if tiene else "sin datos "
            if tiene:
                con_datos.append((clave, cuerpo))
        else:
            estado = "no-json  "
        print(f"  [{estado}] {clave}\n              {motivo}")

    print(f"\nA TRASLADAR ({len(a_mover)}):")
    resumen = defaultdict(int)
    for origen, destino in a_mover:
        resumen[(CLAVE.match(origen).group(1), CLAVE.match(destino).group(1))] += 1
    for (origen, destino), cuantos in sorted(resumen.items()):
        print(f"  {origen} -> {destino}: {cuantos} partidos")

    if con_datos:
        print(f"\n{len(con_datos)} de los que se borran tienen estadísticas; "
              f"se guardarán en {args.backup_dir}/ antes de borrarlos.")
        print("Se pueden volver a descargar: ./run_pipeline.sh actualizar")

    if not args.apply:
        print("\n(plan; no se ha tocado nada — añade --apply para ejecutarlo)")
        return

    if con_datos:
        destino_backup = Path(args.backup_dir)
        destino_backup.mkdir(parents=True, exist_ok=True)
        for clave, cuerpo in con_datos:
            fichero = destino_backup / clave.replace("/", "__")
            fichero.write_bytes(cuerpo)
        print(f"\nGuardada copia de {len(con_datos)} partidos en {destino_backup}/")

    # Copiar antes de borrar: si algo falla, el original sigue ahí.
    for indice_actual, (origen, destino) in enumerate(a_mover, 1):
        s3.copy_object(Bucket=args.bucket, Key=destino,
                       CopySource={"Bucket": args.bucket, "Key": origen})
        if indice_actual % 200 == 0:
            print(f"  trasladados {indice_actual}/{len(a_mover)}")
    print(f"Copiados {len(a_mover)} partidos al destino.")

    for origen, _ in a_mover:
        s3.delete_object(Bucket=args.bucket, Key=origen)
    for clave, _ in a_borrar:
        s3.delete_object(Bucket=args.bucket, Key=clave)
    print(f"Retirados {len(a_mover)} originales y {len(a_borrar)} objetos sueltos.")

    _, pendientes, final = planificar(s3, args.bucket)
    print("\nContenido final:")
    for competicion, ids in sorted(final.items()):
        print(f"  {competicion:<18}{len(ids):>6} partidos")
    if pendientes:
        print(f"AVISO: quedan {len(pendientes)} traslados pendientes")


if __name__ == "__main__":
    main()
