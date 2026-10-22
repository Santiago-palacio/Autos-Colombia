@echo off
title Autos Colombia - Servidor de Parqueadero
echo ===================================================
echo     Iniciando Servidor Web Autos Colombia...
echo ===================================================
echo.
echo Abriendo navegador en http://127.0.0.1:5000 ...
start http://127.0.0.1:5000
echo.
python app.py
pause
