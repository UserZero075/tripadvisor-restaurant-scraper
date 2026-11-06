#!/usr/bin/env bash
# run_barcelona_fast.sh - Ejecución ultra-rápida (~100 fichas/min) para 5000 restaurantes de Barcelona

set -euo pipefail
cd "$(dirname "$0")"

DB_FILE="tripadvisor_barcelona_5000.db"
CSV_FILE="/home/cloud/restaurantes_barcelona_5000.csv"
LOG_FILE="/home/cloud/.hermes/cache/scratch/barcelona_5000.log"
VENV="/home/cloud/tools/ipw/.venv"

export LD_LIBRARY_PATH="/home/cloud/conda-gcc/lib:${LD_LIBRARY_PATH:-}"

echo "[$(date)] Iniciando extracción ultra-rápida (100 fichas/min)..." >> "$LOG_FILE"

exec xvfb-run -a --server-args="-screen 0 1400x1000x24" \
    "$VENV/bin/python" scraper_fast.py \
        --city barcelona \
        --mode detail \
        --limit 5000 \
        --geo-filter g187497 \
        --delay 0.12 \
        --db "$DB_FILE" \
        --output "$CSV_FILE" >> "$LOG_FILE" 2>&1
