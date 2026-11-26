@echo off
title NeoAccess - Borrar datos del simulador
chcp 65001 >nul
echo ======================================================================
echo    NeoAccess - Borrar lo generado por el simulador (puertas SIM-*)
echo    Las puertas reales, usuarios y horarios no se tocan.
echo ======================================================================
echo.
cd /d "%~dp0"
python tools\borrar_simulacion.py %*
echo.
pause
