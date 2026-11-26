@echo off
title NeoAccess - Servidor Central IoT ITSOEH
color 0B
echo ======================================================================
echo    NeoAccess - Sistema de Control de Acceso IoT con Reconocimiento Facial
echo    ITSOEH - Edificio 6 y Laboratorios STEM
echo ======================================================================
echo.
cd /d "%~dp0"

echo Verificando dependencias de Python...
python -c "import fastapi, uvicorn, cv2, numpy, openpyxl, fpdf" 2>nul
if %errorlevel% neq 0 (
    echo Instalando librerias requeridas...
    python -m pip install -r requirements.txt
)

if not exist "raspberry_pi\models\face_recognition_sface_2021dec.onnx" (
    echo Descargando modelos de reconocimiento facial ^(~37 MB, una sola vez^)...
    python raspberry_pi\descargar_modelos.py
)

echo Verificando base de datos SQLite en carpeta database/...
python database\seed_data.py

echo.
echo ======================================================================
echo  Iniciando Servidor Web en: http://localhost:8000/login
echo  Cuentas de prueba: ver ACCESOS_PRUEBA.txt
echo ======================================================================
if exist "config_servidor.env" (
    echo  Correo de verificacion: usando config_servidor.env
) else (
    echo  Correo de verificacion: SIN CONFIGURAR - los enlaces se muestran en esta consola.
    echo  Para enviar correos copie config_servidor.env.ejemplo como config_servidor.env
)
echo.
start http://localhost:8000/login
python backend\app.py
pause
