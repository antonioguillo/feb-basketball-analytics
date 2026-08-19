#!/usr/bin/env bash
# ============================================================
# Descarga del histórico de feb.es.
#
# Medido contra la web en agosto de 2026:
#
#   Play-by-play y carta de tiros existen SOLO desde la temporada 2020.
#   De 2019 hacia atrás la API interna no devuelve nada: queda el box score
#   (estadísticas por jugador), que sí llega hasta 1996.
#
#   Un partido con play-by-play ocupa ~375 KB en raw; uno sin él, ~10 KB.
#
#   Alcance          Temporadas   Partidos    Peso     Tiempo (6 hilos)
#   -----------------------------------------------------------------
#   moderno          2020-2025      ~20.000   ~7,2 GB     ~2 h
#   completo         1996-2025     ~100.000   ~8,0 GB    ~10 h
#
# Uso:
#   ./scripts/backfill_historico.sh moderno            # 2020-2025, absolutas
#   ./scripts/backfill_historico.sh completo           # todo, todas las categorías
#   ./scripts/backfill_historico.sh 2024,2025          # temporadas sueltas
#   ./scripts/backfill_historico.sh 2025 tercerafeb    # una competición
#
# Variables:
#   WORKERS=6   descargas en paralelo (por defecto 4)
#   DELAY=0.5   segundos de espera dentro de cada hilo (por defecto 1.0)
#
# El ritmo real contra feb.es es aproximadamente WORKERS/DELAY peticiones por
# segundo. Con los valores por defecto son 4 req/s; no conviene subir mucho más.
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

MODO="${1:-moderno}"
COMPETICIONES="${2:-}"
WORKERS="${WORKERS:-4}"
DELAY="${DELAY:-1.0}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

case "$MODO" in
    moderno)
        SEASONS="2020,2021,2022,2023,2024,2025"
        EXTRA=""
        log "Modo moderno: 2020-2025, competiciones absolutas, con play-by-play."
        ;;
    completo)
        SEASONS="$(seq -s, 1996 2025)"
        EXTRA="--all-groups --categories senior,copa,base"
        log "Modo completo: 1996-2025, todas las categorías y todos los grupos."
        log "AVISO: de 2019 hacia atrás no hay play-by-play ni carta de tiros."
        ;;
    *)
        SEASONS="$MODO"
        EXTRA=""
        log "Temporadas indicadas: $SEASONS"
        ;;
esac

if ! curl -sf -o /dev/null --max-time 3 "http://localhost:9000/minio/health/live"; then
    log "ERROR: MinIO no responde en localhost:9000. Ejecuta primero:  ./run_pipeline.sh up"
    exit 1
fi

# El venv del proyecto es de Linux; en Git Bash sobre Windows no se puede
# activar y basta con el Python del sistema, que ya tiene las dependencias.
if [ -f venv/bin/activate ] && [ -z "${OS:-}" ]; then
    source venv/bin/activate
fi
PY_BIN="${PY_BIN:-python}"

CMD=("$PY_BIN" main.py actualizar --seasons "$SEASONS" --workers "$WORKERS" --delay "$DELAY")
[ -n "$COMPETICIONES" ] && CMD+=(--competitions "$COMPETICIONES")
[ -n "$EXTRA" ] && CMD+=($EXTRA)

log "Ejecutando: ${CMD[*]}"
log "Se puede cortar y reanudar: lo ya descargado se omite."
"${CMD[@]}"

log "Descarga terminada. Construye las capas con:"
log "  ./run_pipeline.sh bronze && ./run_pipeline.sh silver && ./run_pipeline.sh gold"
log "  ./run_pipeline.sh export && ./run_pipeline.sh clickhouse"
