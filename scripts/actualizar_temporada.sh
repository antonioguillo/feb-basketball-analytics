#!/usr/bin/env bash
# ============================================================
# Actualización incremental de la temporada en curso.
#
# Baja de feb.es los partidos que aún no están en raw, y vuelve a construir
# las capas del data lake hasta ClickHouse. Está pensado para ejecutarse de
# forma recurrente (cron, tarea programada) mientras dura la liga.
#
# Es seguro repetirlo: los partidos ya descargados se omiten y los que todavía
# no se han jugado no se guardan, así que se recogen solos en cuanto la FEB
# publique el acta.
#
# Uso:
#   ./scripts/actualizar_temporada.sh                    # temporada en curso
#   ./scripts/actualizar_temporada.sh --seasons 2026     # una concreta
#   ./scripts/actualizar_temporada.sh --competitions lfendesa,primerafeb
#   ./scripts/actualizar_temporada.sh --solo-scraping    # sin reconstruir capas
#
# En cron, un día por semana a las 4:00:
#   0 4 * * 1 cd /ruta/al/proyecto && ./scripts/actualizar_temporada.sh >> logs/actualizar.log 2>&1
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
log() { echo "$LOG_PREFIX $*"; }

SOLO_SCRAPING=0
ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--solo-scraping" ]; then SOLO_SCRAPING=1; else ARGS+=("$arg"); fi
done

# La capa raw vive en MinIO: sin la infraestructura levantada no hay dónde
# guardar, así que se aborta antes de gastar horas de scraping.
if ! curl -sf --max-time 10 "http://localhost:9000/minio/health/live" > /dev/null; then
    log "ERROR: MinIO no responde en localhost:9000."
    log "Levanta la infraestructura primero:  ./run_pipeline.sh up"
    exit 1
fi

if [ ! -d venv ]; then
    log "ERROR: falta el entorno virtual. Créalo con:  python3 -m venv venv && pip install -r requirements.txt"
    exit 1
fi
# El venv del proyecto es de Linux; en Git Bash sobre Windows no se puede
# activar y basta con el Python del sistema, que ya tiene las dependencias.
if [ -f venv/bin/activate ] && [ -z "${OS:-}" ]; then
    source venv/bin/activate
fi
PY_BIN="${PY_BIN:-python}"

log "Descargando partidos nuevos de feb.es..."
"$PY_BIN" main.py actualizar ${ARGS[@]+"${ARGS[@]}"}

if [ "$SOLO_SCRAPING" -eq 1 ]; then
    log "Solo scraping: no se reconstruyen las capas."
    exit 0
fi

log "Reconstruyendo el data lake..."
for etapa in bronze silver gold export clickhouse; do
    log "  -> $etapa"
    ./run_pipeline.sh "$etapa"
done

log "Actualización completada."
