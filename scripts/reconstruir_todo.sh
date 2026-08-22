#!/usr/bin/env bash
# ============================================================
# Reconstruye el data lake entero desde raw y lo carga en ClickHouse.
#
# Encadena las cinco etapas y se detiene en la primera que falle, para no
# cargar en ClickHouse un gold construido a medias.
#
# Uso:
#   ./scripts/reconstruir_todo.sh                 # todo, reescribiendo esquema
#   FEB_COMPETITIONS=tercerafeb ./scripts/reconstruir_todo.sh   # solo esa liga
#
# Variables: FEB_REBUILD (1 por defecto aquí), FEB_COMPETITIONS, FEB_SEASONS.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

export FEB_REBUILD="${FEB_REBUILD:-1}"
# Git Bash reescribe /opt/... a rutas Windows al invocar docker, así que hay que
# desactivarlo para que spark-submit reciba la ruta correcta.
# Cuidado: con esta variable puesta, `curl -o /dev/null` deja de resolver el
# destino y falla con un error de escritura que parece una caída del servicio.
# Por eso abajo la redirección la hace el shell.
export MSYS_NO_PATHCONV=1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Se reintenta antes de rendirse: MinIO puede tardar un instante en responder
# si está sirviendo otra lectura, y abortar por un parpadeo no compensa cuando
# lo que viene detrás son horas de proceso.
minio_listo=0
for intento in 1 2 3 4 5; do
    # La redirección la hace el shell, no curl: así no depende de MSYS_NO_PATHCONV.
    if curl -sf --max-time 10 "http://localhost:9000/minio/health/live" > /dev/null; then
        minio_listo=1
        break
    fi
    log "MinIO no responde (intento $intento/5); se reintenta en 5 s"
    sleep 5
done
if [ "$minio_listo" -eq 0 ]; then
    log "ERROR: MinIO sigue sin responder. Ejecuta primero:  ./run_pipeline.sh up"
    exit 1
fi

inicio=$(date +%s)
for etapa in bronze silver gold export clickhouse; do
    paso=$(date +%s)
    log "==> $etapa"
    if ! ./run_pipeline.sh "$etapa"; then
        log "FALLÓ en $etapa; no se continúa para no dejar ClickHouse a medias."
        exit 1
    fi
    log "    $etapa terminado en $((($(date +%s) - paso) / 60)) min"
done

log "RECONSTRUCCIÓN COMPLETA en $((($(date +%s) - inicio) / 60)) min"
