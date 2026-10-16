@echo off
setlocal
cd /d "%~dp0"
py -3.13 -B app_movil\main.py
if errorlevel 1 (
    echo.
    echo No se pudo iniciar Grupo JE Movil. Verifica que Python 3.13 y Pillow esten instalados.
    pause
)
