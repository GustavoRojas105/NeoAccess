@echo off
title NeoAccess - Simulador (servidor en linea)
color 0B
echo ======================================================================
echo    NeoAccess - Simulador de puerta contra https://stem.itsoeh.edu.mx
echo    Escanea tu rostro con la camara de esta PC. Cierra para apagar.
echo ======================================================================
echo.
cd /d "%~dp0"
python tools\simulador_servidor.py %*
pause
