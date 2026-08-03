@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   Publicar el panel en GitHub Pages
echo ==========================================
echo.
echo Regenera el sitio con los datos de ESTA maquina y lo sube. La base local
echo es la mas completa: tiene lo que el robot de GitHub no puede conseguir,
echo como las revistas leidas con el navegador asistido.
echo.

set "PY="
if defined PANEL_PYTHON if exist "%PANEL_PYTHON%" set "PY=%PANEL_PYTHON%"
if not defined PY (
    for %%P in (
        "D:\ANACONDA\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "C:\Python312\python.exe"
    ) do if not defined PY if exist %%P set "PY=%%~P"
)
if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
)
if not defined PY (
    echo No se encontro Python. Defini PANEL_PYTHON con la ruta a tu python.exe
    pause
    exit /b 1
)

echo Generando el sitio...
"%PY%" generar_sitio.py
if errorlevel 1 (
    echo.
    echo Fallo la generacion. No se sube nada.
    pause
    exit /b 1
)

echo.
echo Trayendo cambios del repositorio...
git pull --no-rebase --quiet origin main

echo Subiendo...
git add docs/
git diff --cached --quiet
if errorlevel 1 (
    git commit -q -m "Actualizar datos del panel desde la maquina local"
    git push -q origin main
    echo.
    echo Publicado. En un minuto se ve en:
    echo   https://eaguirre25.github.io/PANEL_REVISTAS_ACADEMICAS/
) else (
    echo.
    echo Sin cambios: el sitio publicado ya esta al dia.
)

echo.
pause
