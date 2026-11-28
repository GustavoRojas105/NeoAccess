#!/usr/bin/env bash
# Servidor stem - instala las actualizaciones de Ubuntu, deja activas las de seguridad
# automáticas y reinicia. NeoAccess y nginx vuelven solos al arrancar (restart unless-stopped).
#
#   sudo bash ~/neoaccess/deploy/actualizar_sistema.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

echo "== Respaldo de la base antes de actualizar"
[ -x /etc/cron.daily/neoaccess-respaldo ] && /etc/cron.daily/neoaccess-respaldo || echo "   (sin respaldo diario instalado; sigue)"

echo "== Actualizaciones"
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade

echo "== Actualizaciones de seguridad automáticas"
apt-get -y -q install unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF

echo "== Que Docker arranque solo al prender"
systemctl enable docker containerd >/dev/null
docker ps --format '   {{.Names}} -> reinicio: {{.Status}}'
for c in neoaccess thingsboard-proxy; do
  echo "   $c: $(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$c")"
done

if [ -f /var/run/reboot-required ]; then
  echo
  echo "== El sistema necesita reiniciar. NeoAccess estará fuera ~1-2 minutos"
  echo "   (las puertas siguen funcionando con su copia local y mandan lo pendiente al volver)."
  read -r -p "¿Reiniciar ahora? (s/n): " r
  if [ "$r" = "s" ]; then
    echo "Reiniciando..."
    systemctl reboot
  else
    echo "No se reinició. Cuando puedas:  sudo reboot"
  fi
else
  echo "Listo. No hace falta reiniciar."
fi
