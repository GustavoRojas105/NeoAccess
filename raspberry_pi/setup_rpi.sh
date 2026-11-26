#!/bin/bash
# ====================================================================
# NeoAccess - Script de Configuración para Raspberry Pi Zero W
# Instituto Tecnológico Superior del Occidente del Estado de Hidalgo (ITSOEH)
# Maestría en Mecatrónica - Gustavo Antonio Rojas Morales
# ====================================================================

echo "=========================================================="
echo "    Instalación del Nodo de Puerta NeoAccess IoT         "
echo "=========================================================="

# Ejecutar desde la carpeta del script, aunque se llame desde otro lado
cd "$(dirname "$(readlink -f "$0")")"

echo "[1/5] Actualizando repositorios de Raspberry Pi OS..."
sudo apt-get update -y

echo "[2/5] Instalando dependencias de Python, GPIO, cámara y visión (paquetes del sistema)..."
# Se usan paquetes apt (precompilados para ARMv6 de la Pi Zero W): sin compilar nada.
sudo apt-get install -y python3-requests python3-numpy python3-rpi.gpio python3-opencv
# Cámara CSI (Pi Camera). Si usa cámara USB no es necesario.
sudo apt-get install -y python3-picamera2 || echo "  (picamera2 no disponible: se usará cámara USB con OpenCV)"

echo "[3/5] Descargando modelos de reconocimiento facial (YuNet + SFace, ~37 MB)..."
python3 descargar_modelos.py || echo "  ¡AVISO! Descargue los modelos después con: python3 descargar_modelos.py"

if [ -f "config.json" ]; then
    echo "[4/5] Archivo config.json detectado."
else
    echo "[4/5] AVISO: aún no hay config.json. La puerta esperará a que lo copies"
    echo "      (a esta carpeta o a la partición boot como neoaccess_config.json)."
fi

echo "[5/5] Creando servicio systemd para inicio automático..."
CURRENT_DIR=$(pwd)
CURRENT_USER=${SUDO_USER:-$(whoami)}
# Permisos para GPIO y cámara sin ser root
sudo usermod -aG gpio,video "${CURRENT_USER}" 2>/dev/null || true

sudo bash -c "cat > /etc/systemd/system/neoaccess-door.service <<EOF
[Unit]
Description=NeoAccess IoT Door Controller Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
ExecStart=/usr/bin/python3 ${CURRENT_DIR}/rpi_main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable neoaccess-door.service
sudo systemctl restart neoaccess-door.service

echo "=========================================================="
echo " ¡Instalación completada! La puerta ya está corriendo y"
echo " arrancará sola cada vez que se encienda la Raspberry."
echo " Buscará el servidor cada 15 s hasta encontrarlo."
echo ""
echo " Ver lo que está haciendo:  journalctl -u neoaccess-door -f"
echo " Probar la conexión:        python3 test_conexion.py"
echo "=========================================================="
