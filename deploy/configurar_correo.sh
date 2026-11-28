#!/usr/bin/env bash
# NeoAccess - configura el correo (SMTP) del servidor y manda un correo de prueba.
#
#   sudo bash ~/neoaccess/deploy/configurar_correo.sh correo.de.prueba@itsoeh.edu.mx
#
# Si existe ~/neoaccess_correo.env (líneas NEOACCESS_SMTP_*=..., subido desde la PC), toma los
# datos de ahí y lo borra; si no, los pregunta (la contraseña no se ve al escribir).
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Córrelo con sudo."; exit 1; }
FUENTE="$(cd "$(dirname "$0")/.." && pwd)"
ENV=/opt/neoaccess/neoaccess.env
SUBIDO=/home/pandasesino/neoaccess_correo.env
PRUEBA="${1:-}"

[ -f "$ENV" ] || { echo "Falta $ENV: corre primero instalar_servidor.sh"; exit 1; }

poner() {  # poner CLAVE VALOR  (reemplaza o agrega la línea, sin mostrar el valor)
  python3 - "$ENV" "$1" "$2" <<'PY'
import sys
ruta, clave, valor = sys.argv[1:4]
lineas = open(ruta, encoding="utf-8").read().splitlines()
nuevas, puesto = [], False
for l in lineas:
    if l.split("=", 1)[0].strip() == clave:
        nuevas.append(f"{clave}={valor}")
        puesto = True
    else:
        nuevas.append(l)
if not puesto:
    nuevas.append(f"{clave}={valor}")
open(ruta, "w", encoding="utf-8").write("\n".join(nuevas) + "\n")
PY
}

if [ -f "$SUBIDO" ]; then
  echo "== Tomando los datos del correo de $SUBIDO"
  while IFS='=' read -r clave valor; do
    case "$clave" in
      NEOACCESS_SMTP_HOST|NEOACCESS_SMTP_PORT|NEOACCESS_SMTP_USER|NEOACCESS_SMTP_PASSWORD|NEOACCESS_SMTP_FROM)
        poner "$clave" "$valor" ;;
    esac
  done < <(tr -d '\r' < "$SUBIDO")
  shred -u "$SUBIDO" 2>/dev/null || rm -f "$SUBIDO"
else
  read -r -p "Servidor SMTP [smtp.gmail.com]: " host;  poner NEOACCESS_SMTP_HOST "${host:-smtp.gmail.com}"
  read -r -p "Puerto [587]: " puerto;                  poner NEOACCESS_SMTP_PORT "${puerto:-587}"
  read -r -p "Cuenta que envía (p. ej. neoaccess@itsoeh.edu.mx): " usuario; poner NEOACCESS_SMTP_USER "$usuario"
  read -r -s -p "Contraseña de APLICACIÓN de esa cuenta (no se ve): " clave; echo; poner NEOACCESS_SMTP_PASSWORD "$clave"
  poner NEOACCESS_SMTP_FROM "NeoAccess ITSOEH <$usuario>"
fi
chmod 600 "$ENV"
echo "   Cuenta: $(grep '^NEOACCESS_SMTP_USER=' "$ENV" | cut -d= -f2-)"

echo "== Reiniciando NeoAccess con la configuración nueva"
bash "$FUENTE/deploy/instalar_servidor.sh" >/tmp/neoaccess_instalar.log 2>&1 || { tail -30 /tmp/neoaccess_instalar.log; exit 1; }
echo "   NeoAccess arriba."

if [ -n "$PRUEBA" ]; then
  echo "== Correo de prueba a $PRUEBA"
  docker exec neoaccess python backend/mailer.py "$PRUEBA"
fi
