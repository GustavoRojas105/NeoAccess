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

Si no hay SMTP configurado (modo pruebas), el enlace se imprime en la consola
del servidor en lugar de enviarse.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage


def smtp_configured() -> bool:
    return bool(os.environ.get("NEOACCESS_SMTP_HOST") and os.environ.get("NEOACCESS_SMTP_USER"))


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
