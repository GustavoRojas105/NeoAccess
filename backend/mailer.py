"""
NeoAccess - Envío de correos (verificación de cuentas @itsoeh.edu.mx)
Ubicación: backend/mailer.py

Se configura con variables de entorno (nunca en el código ni en Git):

    NEOACCESS_SMTP_HOST      p. ej. smtp.gmail.com  (Google Workspace)
                                   smtp.office365.com (Microsoft 365)
    NEOACCESS_SMTP_PORT      587 (STARTTLS, por defecto) o 465 (SSL)
    NEOACCESS_SMTP_USER      cuenta que envía, p. ej. neoaccess@itsoeh.edu.mx
    NEOACCESS_SMTP_PASSWORD  contraseña de aplicación de esa cuenta
    NEOACCESS_SMTP_FROM      remitente visible (opcional; por defecto SMTP_USER)

En lugar de definirlas a mano, se pueden escribir en el archivo local
`config_servidor.env` (raíz del proyecto; está en .gitignore). Copie
`config_servidor.env.ejemplo` y rellénelo.

Si no hay SMTP configurado (modo pruebas), el enlace se imprime en la consola
del servidor en lugar de enviarse.

Probar el envío:   python backend/mailer.py su.correo@itsoeh.edu.mx
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config_servidor.env")


def load_local_config(path: str = CONFIG_FILE) -> bool:
    """
    Carga variables NEOACCESS_* desde config_servidor.env (formato CLAVE=valor).
    Las variables ya definidas en el sistema tienen prioridad.
    """
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
            if clave.startswith("NEOACCESS_") and valor and clave not in os.environ:
                os.environ[clave] = valor
    return True


load_local_config()


def smtp_configured() -> bool:
    return all(os.environ.get(k) for k in ("NEOACCESS_SMTP_HOST", "NEOACCESS_SMTP_USER", "NEOACCESS_SMTP_PASSWORD"))


def send_email(to: str, subject: str, text: str, html: str = None) -> bool:
    """
    Envía un correo. Retorna True si se envió por SMTP y False si se usó el modo
    consola (SMTP sin configurar). Lanza excepción si el SMTP configurado falla.
    """
    if not smtp_configured():
        print("\n" + "=" * 70)
        print("[CORREO - MODO PRUEBA] SMTP no configurado; el correo NO se envió.")
        print(f"Para: {to}\nAsunto: {subject}\n\n{text}")
        print("=" * 70 + "\n", flush=True)
        return False

    host = os.environ["NEOACCESS_SMTP_HOST"]
    port = int(os.environ.get("NEOACCESS_SMTP_PORT", "587"))
    user = os.environ["NEOACCESS_SMTP_USER"]
    password = os.environ.get("NEOACCESS_SMTP_PASSWORD", "")
    sender = os.environ.get("NEOACCESS_SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=context)
            s.login(user, password)
            s.send_message(msg)
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python backend/mailer.py destino@itsoeh.edu.mx")
        sys.exit(1)
    if not smtp_configured():
        print("SMTP no configurado. Copie config_servidor.env.ejemplo a config_servidor.env y rellénelo.")
        sys.exit(1)
    print(f"Enviando correo de prueba a {sys.argv[1]} con {os.environ['NEOACCESS_SMTP_HOST']}...")
    try:
        send_email(sys.argv[1], "Prueba de NeoAccess ITSOEH",
                   "Si recibes este correo, el envío de verificaciones de NeoAccess funciona.")
        print("[OK] Correo enviado. Revise la bandeja de entrada (y la carpeta de spam).")
    except smtplib.SMTPAuthenticationError:
        print("[ERROR] Usuario o contraseña rechazados. Use una CONTRASEÑA DE APLICACIÓN, no la normal.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        sys.exit(1)
