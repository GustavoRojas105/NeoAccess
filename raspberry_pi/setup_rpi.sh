#!/bin/bash
# ====================================================================
# NeoAccess - Script de Configuración para Raspberry Pi Zero W
# Instituto Tecnológico Superior del Occidente del Estado de Hidalgo (ITSOEH)
# Maestría en Mecatrónica - Gustavo Antonio Rojas Morales
# ====================================================================

echo "=========================================================="
echo "    Instalación del Nodo de Puerta NeoAccess IoT         "
echo "=========================================================="

echo "[1/5] Actualizando repositorios de Raspberry Pi OS..."
sudo apt-get update -y

echo "[2/5] Instalando dependencias de Python, GPIO, cámara y visión (paquetes del sistema)..."
# Se usan paquetes apt (precompilados para ARMv6 de la Pi Zero W): sin compilar nada.
sudo apt-get install -y python3-requests python3-numpy python3-rpi.gpio python3-opencv
# Cámara CSI (Pi Camera). Si usa cámara USB no es necesario.
sudo apt-get install -y python3-picamera2 || echo "  (picamera2 no disponible: se usará cámara USB con OpenCV)"

echo "[3/5] Descargando modelos de reconocimiento facial (YuNet + SFace, ~37 MB)..."
python3 descargar_modelos.py || echo "  ¡AVISO! Descargue los modelos después con: python3 descargar_modelos.py"

if [ ! -f "config.json" ]; then
    echo "[4/5] Creando config.json desde plantilla..."
    cp config.json.template config.json
    echo "¡Recuerda editar 'config.json' con la IP de tu PC y el Token generado en el Dashboard!"
else
    echo "[4/5] Archivo config.json detectado."
fi

echo "[5/5] Creando servicio systemd para inicio automático..."
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

sudo bash -c "cat > /etc/systemd/system/neoaccess-door.service <<EOF
[Unit]
Description=NeoAccess IoT Door Controller Service
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=/usr/bin/python3 ${CURRENT_DIR}/rpi_main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable neoaccess-door.service

echo "=========================================================="
echo " ¡Instalación Completada!                                "
echo " 1. Prueba tu conexión ejecutando:                       "
echo "    python3 test_conexion.py                             "
echo " 2. Inicia el servicio con:                              "
echo "    sudo systemctl start neoaccess-door                  "
echo "=========================================================="
