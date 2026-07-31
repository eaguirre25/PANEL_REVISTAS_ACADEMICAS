@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   Panel de revistas academicas
echo ==========================================
echo.

REM Busca un Python utilizable. Si tenes uno en otra ruta, defini la variable
REM de entorno PANEL_PYTHON apuntando al ejecutable y este script la respeta.
set "PY="
if defined PANEL_PYTHON if exist "%PANEL_PYTHON%" set "PY=%PANEL_PYTHON%"

if not defined PY (
    for %%P in (
        "D:\ANACONDA\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "C:\Python312\python.exe"
    ) do if not defined PY if exist %%P set "PY=%%~P"
)

if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
)

if not defined PY (
    echo No se encontro Python.
    echo Instalalo desde https://www.python.org/downloads/ o defini PANEL_PYTHON
    echo con la ruta a tu python.exe
    pause
    exit /b 1
)

echo Usando Python: %PY%
echo.

echo Verificando dependencias...
"%PY%" -c "import streamlit, bs4, pandas, truststore, schedule, openpyxl" 2>nul
if errorlevel 1 (
    echo Instalando dependencias faltantes...
    "%PY%" -m pip install -r requirements.txt
)

echo.
echo Abriendo en http://localhost:8501
echo Para cerrar: Ctrl+C en esta ventana.
echo.
REM --server.address=localhost: accesible solo desde esta PC, no desde la red.
"%PY%" -m streamlit run app.py --server.address=localhost --browser.gatherUsageStats=false

pause
