#!/bin/bash
# Script de instalación para Linux y macOS
set -e

echo "============================================================"
echo "Instalando dependencias de TripAdvisor Barcelona Scraper..."
echo "============================================================"

# Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 no está instalado o no está en el PATH."
    exit 1
fi

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "[1/3] Creando entorno virtual Python (venv)..."
    python3 -m venv venv
else
    echo "[1/3] Entorno virtual existente detectado."
fi

# Activar entorno
source venv/bin/activate

# Instalar dependencias de Python
echo "[2/3] Instalando paquetes de requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# Descargar binario de Camoufox
echo "[3/3] Descargando navegador Camoufox Anti-Detect..."
python3 -m camoufox fetch

# Verificar instalación
echo ""
python3 scraper.py --check-install

echo ""
echo "============================================================"
echo "Instalación completada. Para ejecutar el scraper usa:"
echo "  ./run.sh"
echo "o ejecuta directamente:"
echo "  source venv/bin/activate && python scraper.py --mode all"
echo "============================================================"
