#!/usr/bin/env bash
# NeoAccess - activa el respaldo diario de la base (cron.daily) y hace uno ahora para probarlo.
#
#   sudo bash ~/neoaccess/deploy/instalar_respaldos.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }
FUENTE="$(cd "$(dirname "$0")/.." && pwd)"

install -m 755 "$FUENTE/deploy/respaldo_diario.sh" /etc/cron.daily/neoaccess-respaldo
# La carpeta de respaldos se puede leer (no escribir) desde la cuenta pandasesino,
# para bajar copias a otra computadora con scp.
mkdir -p /opt/neoaccess/respaldos
chown root:pandasesino /opt/neoaccess/respaldos
chmod 750 /opt/neoaccess/respaldos
find /opt/neoaccess/respaldos -name '*.db' -exec chown root:pandasesino {} + -exec chmod 640 {} +

/etc/cron.daily/neoaccess-respaldo
echo "Respaldo diario activado (cada mañana, guarda 30 días). Respaldos:"
ls -lh /opt/neoaccess/respaldos
