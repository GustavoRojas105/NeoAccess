#!/usr/bin/env bash
# NeoAccess - instala o actualiza NeoAccess en stem.itsoeh.edu.mx (Ubuntu + Docker).
#
#   sudo bash ~/neoaccess/deploy/instalar_servidor.sh
#
# Se puede correr las veces que sea: la base (/opt/neoaccess/datos) y la configuración
# (/opt/neoaccess/neoaccess.env) se conservan; solo se reconstruye el programa.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }

FUENTE="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/neoaccess
PROXY_CONF=/opt/thingsboard-proxy/default.conf

FECHA=$(date +%Y%m%d_%H%M%S)

echo "== 1. Liberar memoria: apagar ThingsBoard y n8n si siguen ahí (para borrarlos: borrar_thingsboard_n8n.sh)"
for c in thingsboard n8n n8n-postgres; do
  docker update --restart=no "$c" >/dev/null 2>&1 && docker stop "$c" >/dev/null 2>&1 && echo "   apagado: $c"
done
true

echo "== 2. Carpeta de datos y configuración en $BASE"
mkdir -p "$BASE/datos" "$BASE/respaldos"
chown 10001 "$BASE/datos"
chmod 700 "$BASE/datos"
chown root:pandasesino "$BASE/respaldos" 2>/dev/null || true
chmod 750 "$BASE/respaldos"
if [ ! -f "$BASE/neoaccess.env" ]; then
  cat > "$BASE/neoaccess.env" <<'ENV'
# NeoAccess en el servidor. Después de editar:  sudo bash ~/neoaccess/deploy/instalar_servidor.sh
NEOACCESS_PUBLIC_URL=https://stem.itsoeh.edu.mx
# Correo de verificación (contraseña de APLICACIÓN de la cuenta)
NEOACCESS_SMTP_HOST=smtp.gmail.com
NEOACCESS_SMTP_PORT=587
NEOACCESS_SMTP_USER=
NEOACCESS_SMTP_PASSWORD=
NEOACCESS_SMTP_FROM=
# Iniciar sesión con Google (opcional)
NEOACCESS_GOOGLE_CLIENT_ID=
ENV
fi
chmod 600 "$BASE/neoaccess.env"

if [ -f "$BASE/datos/neoaccess.db" ]; then
  echo "== Respaldo de la base antes de actualizar"
  docker exec neoaccess python -c "import sqlite3; s=sqlite3.connect('/datos/neoaccess.db'); d=sqlite3.connect('/datos/respaldo.tmp'); s.backup(d); d.close()" \
    && mv "$BASE/datos/respaldo.tmp" "$BASE/respaldos/neoaccess_$FECHA.db" || echo "   (no se pudo respaldar en caliente; sigue)"
  ls -1t "$BASE"/respaldos/neoaccess_*.db 2>/dev/null | tail -n +15 | xargs -r rm -f   # guarda los 14 más recientes
fi

echo "== 3. Construir la imagen de NeoAccess"
docker build -t neoaccess:latest "$FUENTE"

echo "== 4. Arrancar el contenedor (solo escucha en 127.0.0.1:8000; lo publica nginx)"
docker rm -f neoaccess >/dev/null 2>&1 || true
docker run -d --name neoaccess --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v "$BASE/datos:/datos" \
  --env-file "$BASE/neoaccess.env" \
  --memory 600m \
  neoaccess:latest

for i in $(seq 1 30); do
  curl -fs -o /dev/null http://127.0.0.1:8000/login && break
  sleep 2
done
curl -fs -o /dev/null http://127.0.0.1:8000/login || { echo "NeoAccess no respondió:"; docker logs --tail 40 neoaccess; exit 1; }

echo "== 5. nginx: stem.itsoeh.edu.mx -> NeoAccess"
if ! cmp -s "$FUENTE/deploy/nginx_stem.conf" "$PROXY_CONF"; then
  cp "$PROXY_CONF" "$PROXY_CONF.antes_neoaccess_$FECHA"
  cp "$FUENTE/deploy/nginx_stem.conf" "$PROXY_CONF"
  if ! docker exec thingsboard-proxy nginx -t; then
    echo "Configuración inválida, regreso la anterior."
    cp "$PROXY_CONF.antes_neoaccess_$FECHA" "$PROXY_CONF"
    exit 1
  fi
  docker exec thingsboard-proxy nginx -s reload
fi

echo "== 6. Prueba"
curl -fsS -o /dev/null -w "https://stem.itsoeh.edu.mx/login -> %{http_code}\n" https://stem.itsoeh.edu.mx/login \
  --resolve stem.itsoeh.edu.mx:443:127.0.0.1
docker exec neoaccess python -c "import sqlite3; print('Administradores:', sqlite3.connect('/datos/neoaccess.db').execute('select count(*) from administradores').fetchone()[0])"
echo
echo "Listo. Si no hay administradores, crea el primero con:"
echo "   sudo docker exec -it neoaccess python tools/crear_admin.py"
