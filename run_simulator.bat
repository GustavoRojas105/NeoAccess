@echo off
title NeoAccess - Simulador de puerta
color 0A
echo ======================================================================
echo    NeoAccess - Simulador de puerta (se refleja en la plataforma)
echo    Deja abierto run_server.bat. Cierra esta ventana para apagar la puerta.
echo ======================================================================
echo.
cd /d "%~dp0"
python tools\simulador_puerta.py %*
pause
