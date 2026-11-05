@echo off
chcp 65001 > nul

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python scraper.py %*
if %errorlevel% neq 0 (
    echo.
    echo Ocurrió un error durante la ejecución.
    pause
)
