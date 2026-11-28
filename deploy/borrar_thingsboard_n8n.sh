#!/usr/bin/env bash
# Borra por completo ThingsBoard y n8n del servidor stem (contenedores, imágenes, datos,
# red iot-network y el certificado de stem8n). NO toca nginx (thingsboard-proxy) ni NeoAccess.
#
#   sudo bash ~/neoaccess/deploy/borrar_thingsboard_n8n.sh
set -uo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }
IOT=/home/pandasesino/iot-server

echo "Se va a BORRAR PARA SIEMPRE (no hay respaldo):"
echo "  - contenedores: thingsboard, n8n, n8n-postgres"
echo "  - imágenes:     thingsboard/tb-postgres, n8nio/n8n, postgres:15-alpine"
echo "  - carpeta:      $IOT  ($(du -sh "$IOT" 2>/dev/null | cut -f1)) con dispositivos, flujos, bases y .env"
echo "  - red docker:   iot-network"
echo "  - certificado:  stem8n.itsoeh.edu.mx"
read -r -p "Escribe BORRAR para continuar: " ok
[ "$ok" = "BORRAR" ] || { echo "Cancelado, no se borró nada."; exit 1; }

docker rm -f thingsboard n8n n8n-postgres
docker rmi thingsboard/tb-postgres:latest n8nio/n8n:latest postgres:15-alpine
docker network rm iot-network
rm -rf "$IOT"
certbot delete --cert-name stem8n.itsoeh.edu.mx --non-interactive
docker image prune -f >/dev/null
echo
echo "Hecho. Quedan corriendo:"
docker ps --format '  {{.Names}}  ({{.Image}})'
