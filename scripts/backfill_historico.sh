#!/usr/bin/env bash
# ============================================================
# Descarga inicial del histórico de las competiciones absolutas.
#
# Recorre las seis categorías absolutas (Primera, Segunda y Tercera FEB,
# LF Endesa, L.F.-2 y LF Challenge) en las temporadas indicadas, bajando
# ficha, play-by-play, carta de tiros y estadísticas de equipo de cada partido.
#
# Volumen medido sobre la web en agosto de 2026, solo liga regular:
#     5 temporadas (2021-2025)  ~17.400 partidos  ~5,8 h  ~0,8 GB en raw
#
# Se puede cortar y reanudar: lo ya descargado se omite en la siguiente
# ejecución. Conviene lanzarlo por temporadas para ir viendo el avance.
#
# Uso:
#   ./scripts/backfill_historico.sh                       # 2021-2025
#   ./scripts/backfill_historico.sh 2024,2025             # temporadas sueltas
#   ./scripts/backfill_historico.sh 2025 tercerafeb       # una competición
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

SEASONS="${1:-2021,2022,2023,2024,2025}"
COMPETITIONS="${2:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

if ! curl -sf -o /dev/null --max-time 3 "http://localhost:9000/minio/health/live"; then
    log "ERROR: MinIO no responde en localhost:9000. Ejecuta primero:  ./run_pipeline.sh up"
    exit 1
fi

source venv/bin/activate

log "Histórico -> temporadas: $SEASONS"
if [ -n "$COMPETITIONS" ]; then
    log "Competiciones: $COMPETITIONS"
    python main.py actualizar --seasons "$SEASONS" --competitions "$COMPETITIONS"
else
    log "Competiciones: las seis absolutas"
    python main.py actualizar --seasons "$SEASONS"
fi

log "Descarga terminada. Construye las capas con:"
log "  ./run_pipeline.sh bronze && ./run_pipeline.sh silver && ./run_pipeline.sh gold"
log "  ./run_pipeline.sh export && ./run_pipeline.sh clickhouse"
