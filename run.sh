#!/bin/bash
# Lanzador para Linux y macOS
set -e

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

python3 scraper.py "$@"
