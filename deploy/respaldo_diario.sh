#!/bin/sh
# NeoAccess - respaldo diario de la base del servidor (lo corre cron: /etc/cron.daily/neoaccess-respaldo).
# Copia consistente con la API de respaldo de SQLite (sin detener el sistema) y guarda los últimos 30 días.
set -e
DATOS=/opt/neoaccess/datos
DESTINO=/opt/neoaccess/respaldos
DIA=$(date +%Y%m%d)

docker exec neoaccess python -c "import sqlite3; s=sqlite3.connect('/datos/neoaccess.db'); d=sqlite3.connect('/datos/respaldo_diario.tmp'); s.backup(d); d.close(); s.close()"
python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('pragma integrity_check').fetchone()[0]=='ok'" "$DATOS/respaldo_diario.tmp"
mv "$DATOS/respaldo_diario.tmp" "$DESTINO/diario_$DIA.db"
chown root:pandasesino "$DESTINO/diario_$DIA.db"
chmod 640 "$DESTINO/diario_$DIA.db"
ls -1t "$DESTINO"/diario_*.db 2>/dev/null | tail -n +31 | xargs -r rm -f
logger -t neoaccess "Respaldo diario listo: $DESTINO/diario_$DIA.db"
