@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   Actualizacion automatica semanal
echo ==========================================
echo.
echo Crea una tarea de Windows que cada lunes a las 10:00 actualiza el catalogo,
echo busca convocatorias y arma el boletin. No abre ninguna ventana.
echo.

REM Misma deteccion de Python que iniciar.bat
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
    echo No se encontro Python. Defini PANEL_PYTHON con la ruta a tu python.exe
    pause
    exit /b 1
)

set "CARPETA=%~dp0"

> "%CARPETA%ejecutar-actualizacion.bat" (
    echo @echo off
    echo chcp 65001 ^>nul
    echo cd /d "%CARPETA%"
    echo "%PY%" actualizar.py
)

schtasks /create /tn "Revistas - actualizacion semanal" ^
    /tr "%CARPETA%ejecutar-actualizacion.bat" ^
    /sc WEEKLY /d MON /st 10:00 /f

if %errorlevel% equ 0 (
    echo.
    echo Listo. Se actualizara cada lunes a las 10:00.
    echo.
    echo Si usas notebook, conviene permitir que corra con bateria:
    echo   abri "Programador de tareas" ^> "Revistas - actualizacion semanal"
    echo   ^> Condiciones ^> desmarca "Iniciar solo si el equipo esta con CA"
) else (
    echo.
    echo No se pudo crear la tarea. Proba ejecutando este archivo como
    echo administrador ^(clic derecho ^> Ejecutar como administrador^).
)

echo.
pause
