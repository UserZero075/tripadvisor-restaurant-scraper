@echo off
chcp 65001 > nul
echo ============================================================
echo Instalando dependencias de TripAdvisor Barcelona Scraper...
echo ============================================================

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no está instalado o no está en el PATH de Windows.
    echo Por favor instala Python 3.10+ desde python.org marcando "Add Python to PATH".
    pause
    exit /b 1
)

REM Crear entorno virtual
if not exist "venv\" (
    echo [1/3] Creando entorno virtual Python (venv)...
    python -m venv venv
) else (
    echo [1/3] Entorno virtual existente detectado.
)

REM Activar entorno
call venv\Scripts\activate.bat

REM Instalar dependencias
echo [2/3] Instalando dependencias de requirements.txt...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM Descargar binario de Camoufox
echo [3/3] Descargando navegador Camoufox Anti-Detect...
python -m camoufox fetch

REM Comprobar instalación
echo.
python scraper.py --check-install

echo.
echo ============================================================
echo Instalación completada con éxito.
echo Para iniciar el scraper haz doble clic en run.bat o ejecuta:
echo   run.bat
echo ============================================================
pause
