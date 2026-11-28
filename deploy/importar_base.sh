#!/usr/bin/env bash
# NeoAccess - reemplaza la base del servidor por una copia subida a ~/neoaccess_base.db
# (respaldando antes la que había).
#
#   sudo bash ~/neoaccess/deploy/importar_base.sh
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }
NUEVA=/home/pandasesino/neoaccess_base.db
DATOS=/opt/neoaccess/datos
FECHA=$(date +%Y%m%d_%H%M%S)

[ -f "$NUEVA" ] || { echo "No encuentro $NUEVA"; exit 1; }
python3 - "$NUEVA" <<'PY'
import sqlite3, sys
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
assert c.execute("pragma integrity_check").fetchone()[0] == "ok", "la copia está dañada"
print("Copia válida:", c.execute("select count(*) from usuarios").fetchone()[0], "usuarios,",
      c.execute("select count(*) from laboratorios").fetchone()[0], "laboratorios,",
      c.execute("select count(*) from horarios").fetchone()[0], "horarios")
PY

docker stop neoaccess >/dev/null
if [ -f "$DATOS/neoaccess.db" ]; then
  mkdir -p /opt/neoaccess/respaldos
  cp "$DATOS/neoaccess.db" "/opt/neoaccess/respaldos/antes_importar_$FECHA.db"
  echo "Respaldo de la base anterior: /opt/neoaccess/respaldos/antes_importar_$FECHA.db"
fi
rm -f "$DATOS"/neoaccess.db "$DATOS"/neoaccess.db-wal "$DATOS"/neoaccess.db-shm
install -o 10001 -m 600 "$NUEVA" "$DATOS/neoaccess.db"
rm -f "$NUEVA"
docker start neoaccess >/dev/null
for i in $(seq 1 20); do curl -fs -o /dev/null http://127.0.0.1:8000/login && break; sleep 1; done
echo "Base importada y NeoAccess arriba."
echo "Ahora vuelve a crear tu administrador:  sudo docker exec -it neoaccess python tools/crear_admin.py"
