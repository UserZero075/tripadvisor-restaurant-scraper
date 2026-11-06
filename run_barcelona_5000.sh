#!/usr/bin/env bash
# Extraccion de 5000 restaurantes de Barcelona.
# Espera a que no haya otra instancia del scraper (para no abrir dos sesiones
# simultaneas contra DataDome desde la misma IP), cataloga y extrae.
set -uo pipefail
cd "$(dirname "$0")"

export LD_LIBRARY_PATH="$HOME/conda-gcc/lib:${LD_LIBRARY_PATH:-}"
PY=/home/cloud/tools/ipw/.venv/bin/python
DB=tripadvisor_barcelona_5000.db
CSV=restaurantes_barcelona_5000.csv
LOG=/home/cloud/.hermes/cache/scratch/barcelona_5000.log

echo "[$(date +%H:%M:%S)] esperando a que termine la extraccion en curso..." >> "$LOG"
while pgrep -f "scraper_ipw" >/dev/null 2>&1; do
  sleep 30
done

echo "[$(date +%H:%M:%S)] FASE 1: catalogo Barcelona (hasta 200 paginas)" >> "$LOG"
xvfb-run -a --server-args="-screen 0 1400x1000x24" "$PY" scraper_ipw.py \
  --city barcelona --mode catalog --max-pages 200 \
  --db "$DB" --output "$CSV" >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] FASE 2: extraccion de 5000 fichas" >> "$LOG"
xvfb-run -a --server-args="-screen 0 1400x1000x24" "$PY" scraper_ipw.py \
  --city barcelona --mode detail --limit 5000 --geo-filter g187497 \
  --delay-min 1.2 --delay-max 2.4 \
  --batch-size 40 --batch-cooldown-min 12 --batch-cooldown-max 22 \
  --db "$DB" --output "$CSV" >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] FINALIZADO" >> "$LOG"
