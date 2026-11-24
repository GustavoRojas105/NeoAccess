@echo off
title NeoAccess - Prueba de Acceso
cd /d "%~dp0"
python prueba_acceso.py
if %errorlevel% neq 0 pause
