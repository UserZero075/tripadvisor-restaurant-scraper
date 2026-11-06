#!/usr/bin/env bash
# Lanzador del motor alternativo basado en invisible_playwright.
# Requiere: uv, Xvfb (xvfb-run) y las dependencias de requirements-ipw.txt
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv-ipw/bin/python"
if [ ! -x "$PY" ]; then
  echo "[!] Falta el entorno. Ejecuta primero:"
  echo "    uv venv --python 3.11 .venv-ipw"
  echo "    VIRTUAL_ENV=.venv-ipw uv pip install -r requirements-ipw.txt"
  echo "    .venv-ipw/bin/invisible-playwright fetch"
  exit 1
fi

# El motor necesita libstdc++ reciente en distribuciones antiguas
if [ -d "$HOME/conda-gcc/lib" ]; then
  export LD_LIBRARY_PATH="$HOME/conda-gcc/lib:${LD_LIBRARY_PATH:-}"
fi

export DISPLAY_ARGS="-screen 0 1400x1000x24"
exec xvfb-run -a --server-args="$DISPLAY_ARGS" "$PY" scraper_ipw.py "$@"
