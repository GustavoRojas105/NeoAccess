@echo off
title NeoAccess - Simulador de Puerta Raspberry Pi Zero W
color 0A
echo ======================================================================
echo    NeoAccess - Simulador de Puerta IoT (Raspberry Pi Zero W)
echo ======================================================================
echo.
cd /d "%~dp0raspberry_pi"
python simulator.py
pause
