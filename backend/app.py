"""
NeoAccess - Servidor Central IoT y Plataforma Web de Control de Acceso
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\backend\\app.py
Diseñado para ITSOEH - Edificio 6 y Laboratorios STEM
Cumple con todos los Requerimientos Funcionales RF-01 al RF-22 del documento NeoAccess.
"""

import os
import sys
import json
import sqlite3
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List

# Asegurar importaciones relativas limpias desde la raíz del proyecto
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Header, Depends, Query, Response, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database.database import get_connection, init_db, periodo_siguiente
from backend.mailer import send_email
from backend.horarios_import import validar_horario, leer_archivo, generar_plantilla, cargar_materias
from backend.auth import (
    hash_password, verify_password, needs_rehash, create_session,
    validate_session, destroy_session, destroy_sessions_for, generate_device_token,
    login_locked_seconds, register_failed_login, reset_failed_logins
)
from backend.models import (
    LoginRequest, RegisterRequest, AdminCreate, PasswordChange, JefeCreate, JefeCarreras, GroupUpdate, ResendVerificationRequest, MaintenancePayload, LabCreate, LabUpdate, DeviceCreate, GroupCreate,
    UserCreate, FacialMetadataCreate, FacialCapturePayload, ScheduleCreate,
    HeartbeatPayload, AccessAttemptPayload, CleaningPayload, CommandAckPayload
)

# Inicializar Base de Datos si no existe
init_db()

app = FastAPI(
    title="NeoAccess IoT Server",
    description="Servidor Local de Control de Acceso por Reconocimiento Facial para Laboratorios ITSOEH",
    version="1.1.0"
)

# CORS (RF-22): el Dashboard se sirve desde este mismo servidor, por lo que no
# necesita CORS. Solo si otro origen debe consumir la API, listarlo en la variable
# de entorno NEOACCESS_CORS_ORIGINS separada por comas
# (ej. "http://192.168.1.50:3000"). Las Raspberry Pi no usan CORS.
_cors_origins = [o.strip() for o in os.environ.get("NEOACCESS_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,  # La API usa header Authorization, no cookies
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Device-Token"],
    )

# Middleware global para evitar caché en navegadores durante desarrollo y pruebas
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Directorios de Frontend
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
HTML_DIR = os.path.join(FRONTEND_DIR, "html")
STYLES_DIR = os.path.join(FRONTEND_DIR, "styles")
SCRIPTS_DIR = os.path.join(FRONTEND_DIR, "scripts")

# -------------------------------------------------------------
# DEPENDENCIAS Y AUTENTICACIÓN
# -------------------------------------------------------------
# -------------------------------------------------------------
# MODO MANTENIMIENTO GLOBAL
# Mientras está activo solo el administrador puede usar la plataforma web.
# Las puertas (API IoT con token de dispositivo) siguen funcionando.
# -------------------------------------------------------------
MANTENIMIENTO_MENSAJE_DEFECTO = "El sistema está en mantenimiento. Intente más tarde."

def get_maintenance_state() -> dict:
    conn = get_connection()
    rows = {r["clave"]: r["valor"] for r in conn.execute(
        "SELECT clave, valor FROM configuracion_sistema WHERE clave LIKE 'mantenimiento%'").fetchall()}
    conn.close()
    return {
        "activo": rows.get("mantenimiento") == "1",
        "mensaje": rows.get("mantenimiento_mensaje") or MANTENIMIENTO_MENSAJE_DEFECTO,
        "desde": rows.get("mantenimiento_desde"),
        "por": rows.get("mantenimiento_por"),
    }

def maintenance_exception(state: dict) -> HTTPException:
    return HTTPException(status_code=503, detail=state["mensaje"],
                         headers={"X-NeoAccess-Mantenimiento": "1", "Retry-After": "600"})

def get_current_user(authorization: Optional[str] = Header(None)):
    """Verifica que la petición provenga de un usuario autenticado (cualquier rol)."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado. Inicie sesión en la plataforma.")
    token = authorization.replace("Bearer ", "").strip()
    session = validate_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido.")
    if session.get("rol") != "administrador":
        state = get_maintenance_state()
        if state["activo"]:
            raise maintenance_exception(state)
    return session

def require_role(*roles: str):
    """Dependencia que exige que la sesión tenga uno de los roles indicados."""
    def _dep(authorization: Optional[str] = Header(None)):
        session = get_current_user(authorization)
        if session.get("rol") not in roles:
            raise HTTPException(status_code=403, detail="Acceso denegado para su rol.")
        return session
    return _dep

def get_current_admin(authorization: Optional[str] = Header(None)):
    """Verifica que la petición provenga de un administrador autenticado (RF-18)."""
    session = get_current_user(authorization)
    if session.get("rol") != "administrador":
        raise HTTPException(status_code=403, detail="Acceso denegado: se requieren privilegios de Administrador.")
    return session

def get_current_staff(authorization: Optional[str] = Header(None)):
    """Administrador o jefe de carrera. session['carreras'] = None (admin: todas) o lista de carreras."""
    session = get_current_user(authorization)
    if session.get("rol") == "administrador":
        session.setdefault("carreras", None)
        return session
    if session.get("rol") == "jefe_carrera":
        return session
    raise HTTPException(status_code=403, detail="Acceso denegado para su rol.")

def carreras_de(session: dict):
    """None = sin restricción (administrador)."""
    return None if session.get("rol") == "administrador" else list(session.get("carreras") or [])

def exigir_carrera(session: dict, carrera: Optional[str], que: str = "este registro"):
    permitidas = carreras_de(session)
    if permitidas is not None and carrera not in permitidas:
        raise HTTPException(status_code=403, detail=f"No puede modificar {que}: pertenece a una carrera que no está a su cargo.")

# Minutos antes del inicio de la clase en que la puerta ya permite entrar
TOLERANCIA_ENTRADA_MIN = 10

def periodo_activo(cursor) -> dict:
    row = cursor.execute("SELECT * FROM periodos WHERE estado = 'activo' ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="No hay un periodo escolar activo.")
    return dict(row)

def verify_device_token(token_api: Optional[str], db_cursor, dispositivo_id: Optional[str] = None) -> dict:
    """
    Verifica la autenticidad de un dispositivo Raspberry Pi Zero W mediante su token.
    Si se indica dispositivo_id, debe coincidir con el dueño del token: un dispositivo
    no puede reportar eventos a nombre de otro (anti-suplantación).
    """
    if not token_api:
        raise HTTPException(status_code=401, detail="Token de dispositivo requerido.")
    db_cursor.execute("SELECT * FROM dispositivos WHERE token_api = ? AND activo = 1", (token_api,))
    dev = db_cursor.fetchone()
    if not dev:
        raise HTTPException(status_code=403, detail="Dispositivo no reconocido o desactivado.")
    if dispositivo_id is not None and dispositivo_id != dev["id"]:
        raise HTTPException(status_code=403, detail="El token no corresponde al dispositivo indicado.")
    return dict(dev)

# -------------------------------------------------------------
# RUTAS DE AUTENTICACIÓN MULTI-ROL (RF-18 + Portales por Rol)
# -------------------------------------------------------------
@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "desconocido"

    # Anti fuerza bruta: rechazar mientras la IP/usuario esté bloqueado
    bloqueo = login_locked_seconds(client_ip, payload.username)
    if bloqueo:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Intente de nuevo en {max(1, bloqueo // 60)} minuto(s).",
            headers={"Retry-After": str(bloqueo)}
        )

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Intentar como Administrador
    cursor.execute("SELECT * FROM administradores WHERE lower(username) = lower(?) AND activo = 1", (payload.username.strip(),))
    admin = cursor.fetchone()
    if admin and verify_password(payload.password, admin["password_hash"]):
        if needs_rehash(admin["password_hash"]):
            # Migración transparente del hash antiguo (SHA-256) a PBKDF2
            cursor.execute("UPDATE administradores SET password_hash = ? WHERE id = ?",
                           (hash_password(payload.password), admin["id"]))
            conn.commit()
        reset_failed_logins(client_ip, payload.username)
        token = create_session(admin["username"], admin["id"], admin["nombre"], rol="administrador", extra_data={"email": admin["email"]})
        conn.close()
        return {
            "success": True,
            "token": token,
            "admin": {
                "id": admin["id"],
                "username": admin["username"],
                "nombre": admin["nombre"],
                "email": admin["email"],
                "rol": "administrador"
            }
        }

    # 2. Intentar como Jefe de Carrera
    cursor.execute("SELECT * FROM jefes_carrera WHERE lower(username) = lower(?) AND activo = 1", (payload.username.strip(),))
    jefe = cursor.fetchone()
    if jefe and verify_password(payload.password, jefe["password_hash"]):
        state = get_maintenance_state()
        if state["activo"]:
            conn.close()
            raise maintenance_exception(state)
        carreras = [r["carrera"] for r in cursor.execute(
            "SELECT carrera FROM jefe_carreras WHERE jefe_id = ? ORDER BY carrera", (jefe["id"],))]
        if needs_rehash(jefe["password_hash"]):
            cursor.execute("UPDATE jefes_carrera SET password_hash = ? WHERE id = ?",
                           (hash_password(payload.password), jefe["id"]))
            conn.commit()
        conn.close()
        reset_failed_logins(client_ip, payload.username)
        token = create_session(jefe["username"], jefe["id"], jefe["nombre"], rol="jefe_carrera",
                               extra_data={"email": jefe["email"], "carreras": carreras})
        return {"success": True, "token": token, "admin": {
            "id": jefe["id"], "username": jefe["username"], "nombre": jefe["nombre"],
            "email": jefe["email"], "rol": "jefe_carrera", "carreras": carreras}}

    # 3. Intentar como Usuario Institucional (Docente, Alumno o Limpieza)
    cursor.execute("""
    SELECT u.*, g.nombre as grupo_nombre 
    FROM usuarios u 
    LEFT JOIN grupos g ON u.grupo_id = g.id 
    WHERE (u.matricula_clave = ? OR u.id = ?) AND u.estado = 'activo';
    """, (payload.username, payload.username))
    user = cursor.fetchone()

    if user and user["password_hash"] and verify_password(payload.password, user["password_hash"]):
        state = get_maintenance_state()
        if state["activo"]:
            conn.close()
            raise maintenance_exception(state)
        if "cuenta_aprobada" in user.keys() and user["cuenta_aprobada"] == 0:
            conn.close()
            raise HTTPException(
                status_code=403,
                detail="Tu correo ya está verificado, pero la cuenta de docente espera la aprobación del administrador."
            )
        if needs_rehash(user["password_hash"]):
            cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?",
                           (hash_password(payload.password), user["id"]))
            conn.commit()
        conn.close()
        reset_failed_logins(client_ip, payload.username)
        token = create_session(
            username=user["matricula_clave"],
            user_id=user["id"],
            nombre=user["nombre_completo"],
            rol=user["tipo"],
            extra_data={
                "matricula_clave": user["matricula_clave"],
                "carrera": user["carrera"],
                "grupo_id": user["grupo_id"],
                "grupo_nombre": user["grupo_nombre"]
            }
        )
        return {
            "success": True,
            "token": token,
            "admin": {
                "id": user["id"],
                "username": user["matricula_clave"],
                "nombre": user["nombre_completo"],
                "matricula_clave": user["matricula_clave"],
                "carrera": user["carrera"],
                "grupo_id": user["grupo_id"],
                "grupo_nombre": user["grupo_nombre"],
                "rol": user["tipo"]
            }
        }

    conn.close()
    register_failed_login(client_ip, payload.username)
    raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        destroy_session(token)
    return {"success": True, "message": "Sesión finalizada."}

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"success": True, "user": user}

@app.get("/api/system/status")
def system_status():
    """Público: lo consulta la página de login para mostrar el aviso de mantenimiento."""
    state = get_maintenance_state()
    return {"mantenimiento": state["activo"], "mensaje": state["mensaje"] if state["activo"] else None}

@app.get("/api/system/maintenance")
def get_maintenance(admin: dict = Depends(get_current_admin)):
    return get_maintenance_state()

@app.post("/api/system/maintenance")
def set_maintenance(payload: MaintenancePayload, admin: dict = Depends(get_current_admin)):
    """Activa o desactiva el modo mantenimiento global (solo administrador)."""
    mensaje = " ".join((payload.mensaje or "").split()) or MANTENIMIENTO_MENSAJE_DEFECTO
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valores = {
        "mantenimiento": "1" if payload.activo else "0",
        "mantenimiento_mensaje": mensaje,
        "mantenimiento_desde": ahora if payload.activo else None,
        "mantenimiento_por": admin.get("nombre") if payload.activo else None,
    }
    conn = get_connection()
    for clave, valor in valores.items():
        conn.execute("""
        INSERT INTO configuracion_sistema (clave, valor, actualizado) VALUES (?, ?, ?)
        ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, actualizado = excluded.actualizado;
        """, (clave, valor, ahora))
    conn.commit()
    conn.close()
    estado = "ACTIVADO" if payload.activo else "desactivado"
    print(f"[MANTENIMIENTO] {estado} por {admin.get('nombre')} ({ahora})", flush=True)
    return {"success": True, **get_maintenance_state()}

# -------------------------------------------------------------
# AUTORREGISTRO CON CORREO INSTITUCIONAL (@itsoeh.edu.mx)
# La cuenta solo se crea cuando el usuario abre el enlace enviado a su correo.
# -------------------------------------------------------------
import re
import hashlib
import html as _html
import ipaddress
import secrets
import socket
import time
from fastapi.responses import RedirectResponse

DOMINIO_INSTITUCIONAL = "itsoeh.edu.mx"
_CORREO_RE = re.compile(r"^[a-z0-9._%+-]+@itsoeh\.edu\.mx$")
_MATRICULA_RE = re.compile(r"^[A-Za-z0-9-]{3,40}$")
VERIFICACION_HORAS = 24
_REGISTRO_INTENTOS = {}  # ip -> [timestamps]
_REGISTRO_MAX_POR_HORA = 5


def _registro_rate_limit(ip: str):
    ahora = time.time()
    intentos = [t for t in _REGISTRO_INTENTOS.get(ip, []) if ahora - t < 3600]
    if len(intentos) >= _REGISTRO_MAX_POR_HORA:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes de registro. Intente de nuevo en una hora.")
    intentos.append(ahora)
    _REGISTRO_INTENTOS[ip] = intentos


def _normalizar_correo(correo: str) -> str:
    correo = (correo or "").strip().lower()
    if not _CORREO_RE.match(correo):
        raise HTTPException(status_code=400, detail=f"Solo se permiten correos institucionales @{DOMINIO_INSTITUCIONAL}.")
    return correo


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _public_base_url(request: Request) -> str:
    """
    URL base de los enlaces del correo. Usa NEOACCESS_PUBLIC_URL si existe; si no,
    solo confía en el Host cuando es una IP de la red (un Host falso no puede hacer
    que el enlace con el token apunte a otro sitio).
    """
    env_url = os.environ.get("NEOACCESS_PUBLIC_URL")
    if env_url:
        return env_url.rstrip("/")
    port = request.url.port or 8000
    host = request.url.hostname or ""
    try:
        if not ipaddress.ip_address(host).is_loopback:
            return f"{request.url.scheme}://{host}:{port}"
    except ValueError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no envía paquetes; solo elige la interfaz
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:{port}"
    except Exception:
        return f"http://127.0.0.1:{port}"


def _enviar_verificacion(request: Request, correo: str, nombre: str, token: str) -> bool:
    enlace = f"{_public_base_url(request)}/verificar?token={token}"
    texto = (
        f"Hola {nombre}:\n\n"
        f"Para activar tu cuenta de NeoAccess ITSOEH abre este enlace (válido {VERIFICACION_HORAS} h):\n\n"
        f"{enlace}\n\n"
        "Si tú no solicitaste esta cuenta, ignora este correo."
    )
    html = (
        f"<p>Hola {_html.escape(nombre)}:</p>"
        f"<p>Para activar tu cuenta de <b>NeoAccess ITSOEH</b> haz clic aquí (válido {VERIFICACION_HORAS} h):</p>"
        f'<p><a href="{enlace}" style="background:#0f172a;color:#fff;padding:10px 18px;'
        f'border-radius:8px;text-decoration:none">Verificar mi correo</a></p>'
        f"<p style='font-size:12px;color:#64748b'>O copia este enlace: {enlace}</p>"
        "<p style='font-size:12px;color:#64748b'>Si tú no solicitaste esta cuenta, ignora este correo.</p>"
    )
    return send_email(correo, "Verifica tu cuenta de NeoAccess ITSOEH", texto, html)


@app.post("/api/auth/register")
def register_account(payload: RegisterRequest, request: Request):
    """
    Autorregistro de alumnos y docentes. Solo correos @itsoeh.edu.mx.
    Envía un enlace de verificación; la cuenta no existe hasta que se abre.
    Las cuentas de docente requieren además aprobación del administrador.
    """
    state = get_maintenance_state()
    if state["activo"]:
        raise maintenance_exception(state)
    _registro_rate_limit(request.client.host if request.client else "desconocido")
    correo = _normalizar_correo(payload.correo)
    matricula = payload.matricula_clave.strip().upper()
    if not _MATRICULA_RE.match(matricula):
        raise HTTPException(status_code=400, detail="La matrícula o clave solo puede tener letras, números y guiones.")
    nombre = " ".join(payload.nombre_completo.split())

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM usuarios WHERE correo = ?", (correo,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="Este correo ya tiene una cuenta. Inicie sesión.")
        cursor.execute("SELECT password_hash, correo FROM usuarios WHERE matricula_clave = ?", (matricula,))
        existente = cursor.fetchone()
        if existente and (existente["password_hash"] or existente["correo"]):
            raise HTTPException(status_code=409, detail="Esta matrícula o clave ya tiene una cuenta. Inicie sesión o contacte al administrador.")

        # Una sola solicitud vigente por correo y por matrícula
        cursor.execute("DELETE FROM registros_pendientes WHERE correo = ? OR matricula_clave = ? OR expira < ?",
                       (correo, matricula, _ahora_str()))
        token = secrets.token_urlsafe(32)
        expira = (datetime.now() + timedelta(hours=VERIFICACION_HORAS)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
        INSERT INTO registros_pendientes (token_hash, correo, matricula_clave, nombre_completo, tipo, carrera, password_hash, expira)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (_hash_token(token), correo, matricula, nombre, payload.tipo,
              (payload.carrera or "").strip() or None, hash_password(payload.password), expira))
        conn.commit()

        try:
            enviado = _enviar_verificacion(request, correo, nombre, token)
        except Exception as e:
            cursor.execute("DELETE FROM registros_pendientes WHERE token_hash = ?", (_hash_token(token),))
            conn.commit()
            print(f"[CORREO] Error SMTP: {e}", flush=True)
            raise HTTPException(status_code=502, detail="No se pudo enviar el correo de verificación. Intente más tarde.")
    finally:
        conn.close()

    return {
        "success": True,
        "correo_enviado": enviado,
        "message": (f"Te enviamos un enlace de verificación a {correo}. Ábrelo para activar tu cuenta."
                    if enviado else
                    "SMTP no configurado (modo pruebas): el enlace de verificación se mostró en la consola del servidor.")
    }


@app.post("/api/auth/resend-verification")
def resend_verification(payload: ResendVerificationRequest, request: Request):
    """Reenvía el enlace (genera uno nuevo). Respuesta genérica para no revelar qué correos existen."""
    state = get_maintenance_state()
    if state["activo"]:
        raise maintenance_exception(state)
    _registro_rate_limit(request.client.host if request.client else "desconocido")
    correo = _normalizar_correo(payload.correo)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registros_pendientes WHERE correo = ? AND expira >= ?", (correo, _ahora_str()))
    pend = cursor.fetchone()
    if pend:
        token = secrets.token_urlsafe(32)
        expira = (datetime.now() + timedelta(hours=VERIFICACION_HORAS)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE registros_pendientes SET token_hash = ?, expira = ? WHERE id = ?",
                       (_hash_token(token), expira, pend["id"]))
        conn.commit()
        try:
            _enviar_verificacion(request, correo, pend["nombre_completo"], token)
        except Exception as e:
            print(f"[CORREO] Error SMTP: {e}", flush=True)
    conn.close()
    return {"success": True, "message": "Si hay un registro pendiente con ese correo, se envió un nuevo enlace."}


@app.get("/verificar")
def verify_email(token: str = ""):
    """Enlace del correo: crea (o vincula) la cuenta y regresa al login con el resultado."""
    if not token or len(token) > 200:
        return RedirectResponse("/login?verificado=error", status_code=303)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM registros_pendientes WHERE token_hash = ?", (_hash_token(token),))
        pend = cursor.fetchone()
        if not pend:
            return RedirectResponse("/login?verificado=error", status_code=303)
        if pend["expira"] < _ahora_str():
            cursor.execute("DELETE FROM registros_pendientes WHERE id = ?", (pend["id"],))
            conn.commit()
            return RedirectResponse("/login?verificado=expirado", status_code=303)

        cursor.execute("SELECT id FROM usuarios WHERE correo = ?", (pend["correo"],))
        correo_usado = cursor.fetchone()
        cursor.execute("SELECT * FROM usuarios WHERE matricula_clave = ?", (pend["matricula_clave"],))
        existente = cursor.fetchone()
        if correo_usado or (existente and (existente["password_hash"] or existente["correo"])):
            cursor.execute("DELETE FROM registros_pendientes WHERE id = ?", (pend["id"],))
            conn.commit()
            return RedirectResponse("/login?verificado=existe", status_code=303)

        if existente:
            # Alumno/docente dado de alta antes por el administrador: se vincula su cuenta.
            # Conserva su tipo; si no es alumno, requiere aprobación del administrador.
            aprobada = 1 if existente["tipo"] == "alumno" else 0
            cursor.execute("UPDATE usuarios SET password_hash = ?, correo = ?, cuenta_aprobada = ? WHERE id = ?;",
                           (pend["password_hash"], pend["correo"], aprobada, existente["id"]))
        else:
            aprobada = 1 if pend["tipo"] == "alumno" else 0
            nuevo_id = f"{'ALU' if pend['tipo'] == 'alumno' else 'DOC'}-{pend['matricula_clave']}"
            cursor.execute("SELECT 1 FROM usuarios WHERE id = ?", (nuevo_id,))
            if cursor.fetchone():
                nuevo_id = f"{nuevo_id}-{secrets.token_hex(2).upper()}"
            cursor.execute("""
            INSERT INTO usuarios (id, nombre_completo, tipo, matricula_clave, password_hash, carrera, estado, correo, cuenta_aprobada)
            VALUES (?, ?, ?, ?, ?, ?, 'activo', ?, ?);
            """, (nuevo_id, pend["nombre_completo"], pend["tipo"], pend["matricula_clave"],
                  pend["password_hash"], pend["carrera"], pend["correo"], aprobada))
        cursor.execute("DELETE FROM registros_pendientes WHERE id = ?", (pend["id"],))
        conn.commit()
        return RedirectResponse("/login?verificado=" + ("ok" if aprobada else "pendiente"), status_code=303)
    finally:
        conn.close()


@app.post("/api/users/{user_id}/approve-account")
def approve_account(user_id: str, admin: dict = Depends(get_current_staff)):
    """El administrador (o el jefe de su carrera) aprueba una cuenta de docente autorregistrada."""
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT carrera FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    if row:
        try:
            exigir_carrera(admin, row["carrera"], "esta cuenta")
        except HTTPException:
            conn.close()
            raise
    cursor.execute("UPDATE usuarios SET cuenta_aprobada = 1 WHERE id = ?", (user_id,))
    conn.commit()
    ok = cursor.rowcount
    conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return {"success": True, "message": "Cuenta aprobada. El docente ya puede iniciar sesión."}

# -------------------------------------------------------------
# PORTALES EXCLUSIVOS POR ROL (Docente, Alumno, Limpieza)
# -------------------------------------------------------------
@app.get("/api/portal/student-data")
def get_student_portal(user: dict = Depends(require_role("alumno"))):
    """Datos para el Portal de Alumnos: materias autorizadas e historial de asistencias."""
    conn = get_connection()
    cursor = conn.cursor()
    user_id = user["user_id"]
    actual = cursor.execute("""
        SELECT u.grupo_id, u.carrera, g.nombre AS grupo_nombre, g.clave AS grupo_clave, g.semestre
        FROM usuarios u LEFT JOIN grupos g ON g.id = u.grupo_id WHERE u.id = ?""", (user_id,)).fetchone()
    grupo_id = actual["grupo_id"] if actual else None
    periodo = periodo_activo(cursor)

    # Horarios autorizados de su grupo
    cursor.execute("""
    SELECT 
        h.*,
        l.nombre as laboratorio_nombre,
        l.edificio,
        u.nombre_completo as docente_nombre
    FROM horarios h
    JOIN laboratorios l ON h.laboratorio_id = l.id
    LEFT JOIN usuarios u ON h.docente_id = u.id
    WHERE h.grupo_id = ? AND h.periodo_id = ?
    ORDER BY CASE h.dia_semana WHEN 'Lunes' THEN 1 WHEN 'Martes' THEN 2 WHEN 'Miércoles' THEN 3 WHEN 'Jueves' THEN 4 WHEN 'Viernes' THEN 5 ELSE 6 END, h.hora_inicio ASC;
    """, (grupo_id, periodo["id"]))
    horarios = [dict(r) for r in cursor.fetchall()]

    # Historial de accesos / pase de lista (RF-06)
    cursor.execute("""
    SELECT 
        ra.*,
        l.nombre as laboratorio_nombre,
        l.edificio
    FROM registros_acceso ra
    JOIN laboratorios l ON ra.laboratorio_id = l.id
    WHERE ra.usuario_id = ?
    ORDER BY ra.fecha_hora DESC
    LIMIT 50;
    """, (user_id,))
    asistencias = [dict(r) for r in cursor.fetchall()]

    # Estado del vector facial
    cursor.execute("SELECT id, fecha_registro, dimension FROM metadatos_faciales WHERE usuario_id = ?", (user_id,))
    rostro = cursor.fetchone()

    conn.close()
    perfil = {**user, **({k: actual[k] for k in actual.keys()} if actual else {})}
    return {
        "perfil": perfil,
        "periodo": {"id": periodo["id"], "nombre": periodo["nombre"]},
        "ahora": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tolerancia_min": TOLERANCIA_ENTRADA_MIN,
        "tiene_rostro_registrado": bool(rostro),
        "fecha_rostro": rostro["fecha_registro"] if rostro else None,
        "horarios_autorizados": horarios,
        "historial_asistencias": asistencias
    }

@app.get("/api/portal/teacher-data")
def get_teacher_portal(user: dict = Depends(require_role("docente"))):
    """Datos para el Portal de Docentes: clases impartidas y pase de lista de alumnos (RF-03, RF-06)."""
    conn = get_connection()
    cursor = conn.cursor()
    teacher_id = user["user_id"]
    periodo = periodo_activo(cursor)

    # Clases asignadas
    cursor.execute("""
    SELECT 
        h.*,
        l.nombre as laboratorio_nombre,
        l.edificio,
        g.nombre as grupo_nombre,
        g.clave as grupo_clave
    FROM horarios h
    JOIN laboratorios l ON h.laboratorio_id = l.id
    LEFT JOIN grupos g ON h.grupo_id = g.id
    WHERE h.docente_id = ? AND h.periodo_id = ?
    ORDER BY CASE h.dia_semana WHEN 'Lunes' THEN 1 WHEN 'Martes' THEN 2 WHEN 'Miércoles' THEN 3 WHEN 'Jueves' THEN 4 WHEN 'Viernes' THEN 5 ELSE 6 END, h.hora_inicio ASC;
    """, (teacher_id, periodo["id"]))
    clases = [dict(r) for r in cursor.fetchall()]

    # Confirmaciones de clase del docente (RF-03)
    cursor.execute("""
    SELECT 
        ra.*,
        l.nombre as laboratorio_nombre
    FROM registros_acceso ra
    JOIN laboratorios l ON ra.laboratorio_id = l.id
    WHERE ra.usuario_id = ? AND ra.resultado = 'permitido'
    ORDER BY ra.fecha_hora DESC
    LIMIT 30;
    """, (teacher_id,))
    confirmaciones = [dict(r) for r in cursor.fetchall()]

    # Alumnos que han entrado a los laboratorios asignados a este maestro (Pase de lista RF-06)
    cursor.execute("""
    SELECT 
        ra.id,
        ra.fecha_hora,
        ra.resultado,
        ra.motivo,
        u.nombre_completo as alumno_nombre,
        u.matricula_clave,
        g.nombre as grupo_nombre,
        l.nombre as laboratorio_nombre
    FROM registros_acceso ra
    JOIN usuarios u ON ra.usuario_id = u.id AND u.tipo = 'alumno'
    LEFT JOIN grupos g ON u.grupo_id = g.id
    JOIN laboratorios l ON ra.laboratorio_id = l.id
    WHERE ra.laboratorio_id IN (SELECT DISTINCT laboratorio_id FROM horarios WHERE docente_id = ?)
    ORDER BY ra.fecha_hora DESC
    LIMIT 60;
    """, (teacher_id,))
    alumnos_asistencias = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT fecha_registro FROM metadatos_faciales WHERE usuario_id = ?", (teacher_id,))
    rostro = cursor.fetchone()

    conn.close()
    return {
        "perfil": user,
        "periodo": {"id": periodo["id"], "nombre": periodo["nombre"]},
        "ahora": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tolerancia_min": TOLERANCIA_ENTRADA_MIN,
        "tiene_rostro_registrado": bool(rostro),
        "clases_asignadas": clases,
        "confirmaciones_docente": confirmaciones,
        "pase_de_lista_alumnos": alumnos_asistencias
    }

@app.get("/api/portal/cleaning-data")
def get_cleaning_portal(user: dict = Depends(require_role("personal_limpieza"))):
    """Datos para el Portal de Limpieza: historial de salones atendidos (RF-04)."""
    conn = get_connection()
    cursor = conn.cursor()
    personal_id = user["user_id"]

    cursor.execute("""
    SELECT 
        rl.*,
        l.nombre as laboratorio_nombre,
        l.edificio
    FROM registros_limpieza rl
    JOIN laboratorios l ON rl.laboratorio_id = l.id
    WHERE rl.personal_id = ?
    ORDER BY rl.hora_entrada DESC
    LIMIT 40;
    """, (personal_id,))
    bitacora = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "perfil": user,
        "bitacora": bitacora
    }

# -------------------------------------------------------------
# GESTIÓN COMPLETA DE LABORATORIOS (Nuevo / Edición / Consulta)
# -------------------------------------------------------------
@app.get("/api/labs")
def get_labs(todos: bool = False, admin: dict = Depends(get_current_staff)):
    """Obtiene la lista de laboratorios registrados."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        l.*,
        COUNT(d.id) as total_dispositivos,
        SUM(CASE WHEN d.estado = 'en_linea' AND d.activo = 1 THEN 1 ELSE 0 END) as dispositivos_en_linea
    FROM laboratorios l
    LEFT JOIN dispositivos d ON l.id = d.laboratorio_id
    """
    if not todos:
        query += " WHERE l.activo = 1"
    query += " GROUP BY l.id ORDER BY l.edificio, l.nombre;"
    
    cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/labs")
def create_lab(payload: LabCreate, admin: dict = Depends(get_current_admin)):
    """Da de alta un nuevo laboratorio en la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()

    # Verificar si el ID ya existe
    cursor.execute("SELECT id FROM laboratorios WHERE id = ?", (payload.id.strip(),))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"El ID de laboratorio '{payload.id}' ya existe.")

    cursor.execute("""
    INSERT INTO laboratorios (id, nombre, edificio, carrera, capacidad, descripcion, activo)
    VALUES (?, ?, ?, ?, ?, ?, 1);
    """, (payload.id.strip(), payload.nombre.strip(), payload.edificio.strip(), payload.carrera.strip(), payload.capacidad or 30, payload.descripcion))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Laboratorio '{payload.nombre}' registrado con éxito.", "lab_id": payload.id}

@app.put("/api/labs/{lab_id}")
def update_lab(lab_id: str, payload: LabUpdate, admin: dict = Depends(get_current_admin)):
    """Actualiza la información de un laboratorio existente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM laboratorios WHERE id = ?", (lab_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Laboratorio no encontrado.")

    cursor.execute("""
    UPDATE laboratorios
    SET nombre = ?, edificio = ?, carrera = ?, capacidad = ?, descripcion = ?, activo = ?
    WHERE id = ?;
    """, (payload.nombre.strip(), payload.edificio.strip(), payload.carrera.strip(), payload.capacidad or 30, payload.descripcion, payload.activo, lab_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Laboratorio actualizado correctamente."}

@app.delete("/api/labs/{lab_id}")
def delete_lab(lab_id: str, admin: dict = Depends(get_current_admin)):
    """Da de baja un laboratorio (marcado como inactivo para preservar registros históricos)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE laboratorios SET activo = 0 WHERE id = ?", (lab_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Laboratorio desactivado correctamente."}

# -------------------------------------------------------------
# RUTAS DE MÉTRICAS (Sección 5, 9, RF-19)
# -------------------------------------------------------------
@app.get("/api/metrics/summary")
def get_metrics_summary(
    laboratorio_id: Optional[str] = None,
    carrera: Optional[str] = None,
    dispositivo_id: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    admin: dict = Depends(get_current_admin)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        COUNT(*) as total_intentos,
        SUM(CASE WHEN ra.resultado = 'permitido' THEN 1 ELSE 0 END) as total_permitidos,
        SUM(CASE WHEN ra.resultado = 'denegado' THEN 1 ELSE 0 END) as total_denegados,
        COUNT(DISTINCT ra.usuario_id) as usuarios_unicos
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    WHERE 1=1
    """
    params = []
    if laboratorio_id and laboratorio_id != "todos":
        query += " AND ra.laboratorio_id = ?"
        params.append(laboratorio_id)
    if dispositivo_id and dispositivo_id != "todas":
        query += " AND ra.dispositivo_id = ?"
        params.append(dispositivo_id)
    if carrera and carrera != "todas":
        query += " AND (l.carrera = ? OR u.carrera = ?)"
        params.extend([carrera, carrera])
    if fecha_inicio:
        query += " AND DATE(ra.fecha_hora) >= DATE(?)"
        params.append(fecha_inicio)
    if fecha_fin:
        query += " AND DATE(ra.fecha_hora) <= DATE(?)"
        params.append(fecha_fin)

    cursor.execute(query, params)
    stats = dict(cursor.fetchone() or {})

    # Dispositivos activos y estados
    # Estado calculado en tiempo real con la última señal (el campo guardado puede estar desfasado)
    cursor.execute("SELECT ultima_senal, intervalo_latido_seg, activo FROM dispositivos;")
    estados = [calculate_device_status(r["ultima_senal"], r["intervalo_latido_seg"] or 300, r["activo"])
               for r in cursor.fetchall()]
    dev_stats = {
        "total_dispositivos": len(estados),
        "en_linea": estados.count("en_linea"),
        "intermitentes": estados.count("intermitente"),
        "fuera_linea": estados.count("fuera_de_linea"),
        "desactivados": estados.count("desactivado"),
    }

    total = stats.get("total_intentos") or 0
    permitidos = stats.get("total_permitidos") or 0
    denegados = stats.get("total_denegados") or 0
    tasa_exito = round((permitidos / total * 100), 1) if total > 0 else 0.0

    conn.close()
    return {
        "total_accesos": total,
        "usuarios_distintos": stats.get("usuarios_unicos") or 0,
        "accesos_permitidos": permitidos,
        "accesos_denegados": denegados,
        "tasa_efectividad_porcentaje": tasa_exito,
        "dispositivos": dev_stats
    }

@app.get("/api/metrics/by-lab")
def get_metrics_by_lab(
    carrera: Optional[str] = None,
    dispositivo_id: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    admin: dict = Depends(get_current_admin)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        l.id as lab_id,
        l.nombre as lab_nombre,
        l.edificio,
        COUNT(ra.id) as total_accesos,
        SUM(CASE WHEN ra.resultado = 'permitido' THEN 1 ELSE 0 END) as accesos_validos
    FROM laboratorios l
    LEFT JOIN registros_acceso ra ON l.id = ra.laboratorio_id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    WHERE l.activo = 1
    """
    params = []
    if dispositivo_id and dispositivo_id != "todas":
        query += " AND (ra.id IS NULL OR ra.dispositivo_id = ?)"
        params.append(dispositivo_id)
    if carrera and carrera != "todas":
        query += " AND (l.carrera = ? OR u.carrera = ?)"
        params.extend([carrera, carrera])
    if fecha_inicio:
        query += " AND (ra.fecha_hora IS NULL OR DATE(ra.fecha_hora) >= DATE(?))"
        params.append(fecha_inicio)
    if fecha_fin:
        query += " AND (ra.fecha_hora IS NULL OR DATE(ra.fecha_hora) <= DATE(?))"
        params.append(fecha_fin)

    query += " GROUP BY l.id, l.nombre, l.edificio ORDER BY total_accesos DESC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/metrics/by-day")
def get_metrics_by_day(
    laboratorio_id: Optional[str] = None,
    carrera: Optional[str] = None,
    dispositivo_id: Optional[str] = None,
    dias: int = 7,
    admin: dict = Depends(get_current_admin)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        DATE(ra.fecha_hora) as dia,
        COUNT(*) as total,
        SUM(CASE WHEN ra.resultado = 'permitido' THEN 1 ELSE 0 END) as permitidos,
        SUM(CASE WHEN ra.resultado = 'denegado' THEN 1 ELSE 0 END) as denegados
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    WHERE ra.fecha_hora >= DATE('now', '-' || ? || ' days')
    """
    params = [str(dias)]
    if laboratorio_id and laboratorio_id != "todos":
        query += " AND ra.laboratorio_id = ?"
        params.append(laboratorio_id)
    if dispositivo_id and dispositivo_id != "todas":
        query += " AND ra.dispositivo_id = ?"
        params.append(dispositivo_id)
    if carrera and carrera != "todas":
        query += " AND (l.carrera = ? OR u.carrera = ?)"
        params.extend([carrera, carrera])

    query += " GROUP BY DATE(ra.fecha_hora) ORDER BY DATE(ra.fecha_hora) ASC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/metrics/recent-accesses")
def get_recent_accesses(
    limit: int = Query(10, ge=1, le=500),
    offset: int = Query(0, ge=0),
    dispositivo_id: Optional[str] = None,
    resultado: Optional[str] = None,
    admin: dict = Depends(get_current_admin)
):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT
        ra.id,
        ra.fecha_hora,
        ra.resultado,
        ra.motivo,
        ra.sincronizado_offline,
        ra.dispositivo_id,
        l.nombre as laboratorio_nombre,
        l.edificio,
        u.nombre_completo as usuario_nombre,
        u.tipo as usuario_tipo,
        u.matricula_clave,
        d.nombre as dispositivo_nombre
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    LEFT JOIN dispositivos d ON ra.dispositivo_id = d.id
    WHERE 1=1
    """
    params = []
    if dispositivo_id and dispositivo_id != "todas":
        query += " AND ra.dispositivo_id = ?"
        params.append(dispositivo_id)
    if resultado in ("permitido", "denegado"):
        query += " AND ra.resultado = ?"
        params.append(resultado)
    query += " ORDER BY ra.id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/metrics/by-door")
def get_metrics_by_door(
    carrera: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    admin: dict = Depends(get_current_admin)
):
    """Resumen modular por puerta: estado, totales del periodo, hoy y último acceso."""
    conn = get_connection()
    cursor = conn.cursor()
    filtro, params = "", []
    if carrera and carrera != "todas":
        filtro += " AND (l2.carrera = ? OR u.carrera = ?)"
        params.extend([carrera, carrera])
    if fecha_inicio:
        filtro += " AND DATE(ra.fecha_hora) >= DATE(?)"
        params.append(fecha_inicio)
    if fecha_fin:
        filtro += " AND DATE(ra.fecha_hora) <= DATE(?)"
        params.append(fecha_fin)
    cursor.execute(f"""
    SELECT ra.dispositivo_id,
           COUNT(*) AS total,
           SUM(CASE WHEN ra.resultado = 'permitido' THEN 1 ELSE 0 END) AS permitidos,
           SUM(CASE WHEN ra.resultado = 'denegado' THEN 1 ELSE 0 END) AS denegados,
           SUM(CASE WHEN DATE(ra.fecha_hora) = DATE('now', 'localtime') THEN 1 ELSE 0 END) AS hoy,
           COUNT(DISTINCT ra.usuario_id) AS usuarios_unicos
    FROM registros_acceso ra
    LEFT JOIN laboratorios l2 ON ra.laboratorio_id = l2.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    WHERE 1=1 {filtro}
    GROUP BY ra.dispositivo_id
    """, params)
    totales = {r["dispositivo_id"]: dict(r) for r in cursor.fetchall()}

    cursor.execute("""
    SELECT d.id, d.nombre, d.laboratorio_id, d.ultima_senal, d.intervalo_latido_seg, d.activo,
           l.nombre AS laboratorio_nombre, l.edificio
    FROM dispositivos d LEFT JOIN laboratorios l ON d.laboratorio_id = l.id
    ORDER BY l.nombre, d.nombre
    """)
    puertas = [dict(d) for d in cursor.fetchall()]
    for item in puertas:
        item["estado"] = calculate_device_status(item["ultima_senal"], item["intervalo_latido_seg"] or 300, item["activo"])
        t = totales.get(item["id"], {})
        for k in ("total", "permitidos", "denegados", "hoy", "usuarios_unicos"):
            item[k] = t.get(k) or 0
        item["tasa"] = round(item["permitidos"] / item["total"] * 100, 1) if item["total"] else 0.0
        ultimo = cursor.execute("""
            SELECT ra.fecha_hora, ra.resultado, u.nombre_completo AS usuario_nombre
            FROM registros_acceso ra LEFT JOIN usuarios u ON ra.usuario_id = u.id
            WHERE ra.dispositivo_id = ? ORDER BY ra.id DESC LIMIT 1
        """, (item["id"],)).fetchone()
        item["ultimo_acceso"] = dict(ultimo) if ultimo else None
        for k in ("ultima_senal", "intervalo_latido_seg", "activo"):
            item.pop(k, None)
    conn.close()
    return puertas

# -------------------------------------------------------------
# RUTAS DE DISPOSITIVOS Y PUERTAS (Sección 5, 9, RF-10 al RF-13)
# -------------------------------------------------------------
def calculate_device_status(ultima_senal_str: Optional[str], intervalo_seg: int, activo: int) -> str:
    """Calcula el estado en tiempo real de acuerdo a la llegada de señales (RF-11)."""
    if not activo:
        return "desactivado"
    if not ultima_senal_str:
        return "fuera_de_linea"
    try:
        ultima = datetime.strptime(ultima_senal_str, "%Y-%m-%d %H:%M:%S")
        diferencia_seg = (datetime.now() - ultima).total_seconds()
        if diferencia_seg <= intervalo_seg * 1.8:
            return "en_linea"
        elif diferencia_seg <= intervalo_seg * 3.5:
            return "intermitente"
        else:
            return "fuera_de_linea"
    except Exception:
        return "fuera_de_linea"

@app.get("/api/devices")
def get_devices(admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        d.*,
        l.nombre as laboratorio_nombre,
        l.edificio as laboratorio_edificio,
        l.carrera as laboratorio_carrera
    FROM dispositivos d
    LEFT JOIN laboratorios l ON d.laboratorio_id = l.id
    ORDER BY d.fecha_alta DESC;
    """)
    rows = []
    for r in cursor.fetchall():
        item = dict(r)
        nuevo_estado = calculate_device_status(item["ultima_senal"], item["intervalo_latido_seg"] or 300, item["activo"])
        item["estado"] = nuevo_estado
        rows.append(item)
    conn.close()
    return rows

@app.post("/api/devices")
def create_device(payload: DeviceCreate, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM dispositivos WHERE id = ?", (payload.id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="El ID del dispositivo ya está en uso.")

    token = generate_device_token()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO dispositivos (id, laboratorio_id, nombre, token_api, ip_address, mac_address, intervalo_latido_seg, ultima_senal, estado, activo)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'en_linea', 1);
    """, (payload.id, payload.laboratorio_id, payload.nombre, token, payload.ip_address, payload.mac_address, payload.intervalo_latido_seg, ahora))

    cursor.execute("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, 'conexion', 'Nuevo dispositivo Raspberry Pi Zero W registrado y asignado a puerta', ?);
    """, (payload.id, ahora))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Dispositivo '{payload.nombre}' dado de alta exitosamente.",
        "dispositivo_id": payload.id,
        "token_api": token
    }

@app.post("/api/devices/{device_id}/toggle")
def toggle_device(device_id: str, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT activo, nombre FROM dispositivos WHERE id = ?", (device_id,))
    dev = cursor.fetchone()
    if not dev:
        conn.close()
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    nuevo_estado = 0 if dev["activo"] == 1 else 1
    cursor.execute("UPDATE dispositivos SET activo = ? WHERE id = ?", (nuevo_estado, device_id))
    
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    desc = "Dispositivo activado por administrador" if nuevo_estado == 1 else "Dispositivo desactivado por administrador"
    cursor.execute("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, ?, ?, ?);
    """, (device_id, 'conexion' if nuevo_estado == 1 else 'desconexion', desc, ahora))

    conn.commit()
    conn.close()
    return {"success": True, "activo": nuevo_estado, "mensaje": desc}

@app.post("/api/devices/{device_id}/regenerate-token")
def regenerate_device_token(device_id: str, admin: dict = Depends(get_current_admin)):
    """Genera un Token API nuevo; el anterior deja de funcionar de inmediato."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM dispositivos WHERE id = ?", (device_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

    token = generate_device_token()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE dispositivos SET token_api = ? WHERE id = ?", (token, device_id))
    cursor.execute("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, 'configuracion', 'Token API regenerado por administrador (el anterior quedó invalidado)', ?);
    """, (device_id, ahora))
    conn.commit()
    conn.close()
    return {"success": True, "token_api": token,
            "message": "Token regenerado. Descarga de nuevo el config.json y cópialo a la Raspberry Pi."}

COMMAND_TTL_SECONDS = 30  # una apertura remota no ejecutada en 30 s se descarta

@app.post("/api/devices/{device_id}/manual-unlock")
def manual_unlock(device_id: str, admin: dict = Depends(get_current_admin)):
    """
    Encola un comando de apertura. La Raspberry Pi lo recoge en su siguiente consulta
    (cada ~3 s), abre la puerta y lo confirma; el registro de acceso se guarda al confirmar.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dispositivos WHERE id = ?", (device_id,))
    dev = cursor.fetchone()
    if not dev:
        conn.close()
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    if not dev["activo"]:
        conn.close()
        raise HTTPException(status_code=409, detail="El dispositivo está desactivado.")

    ahora = datetime.now()
    cursor.execute("""
    INSERT INTO comandos_dispositivo (dispositivo_id, tipo, estado, solicitado_por, fecha_creacion, fecha_expira)
    VALUES (?, 'abrir_puerta', 'pendiente', ?, ?, ?);
    """, (device_id, admin.get("username"), ahora.strftime("%Y-%m-%d %H:%M:%S"),
          (ahora + timedelta(seconds=COMMAND_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")))
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {
        "success": True,
        "comando_id": cmd_id,
        "message": f"Orden de apertura enviada a {dev['nombre']}. La puerta se abrirá en cuanto el dispositivo la reciba."
    }

@app.get("/api/devices/{device_id}/commands/{command_id}")
def get_command_status(device_id: str, command_id: int, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    _expire_commands(cursor)
    conn.commit()
    cursor.execute("SELECT * FROM comandos_dispositivo WHERE id = ? AND dispositivo_id = ?", (command_id, device_id))
    cmd = cursor.fetchone()
    conn.close()
    if not cmd:
        raise HTTPException(status_code=404, detail="Comando no encontrado.")
    return dict(cmd)

def _expire_commands(cursor):
    cursor.execute("""
    UPDATE comandos_dispositivo SET estado = 'expirado'
    WHERE estado IN ('pendiente', 'entregado') AND fecha_expira < ?;
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

def _server_url_for_devices(request: Request) -> str:
    """URL con la que las Raspberry Pi deben llegar a este servidor."""
    env_url = os.environ.get("NEOACCESS_PUBLIC_URL")
    if env_url:
        return env_url.rstrip("/")
    host = request.url.hostname or ""
    port = request.url.port or 8000
    if host not in ("localhost", "127.0.0.1", "::1", ""):
        return f"{request.url.scheme}://{host}:{port}"
    # El admin entró por localhost: detectar la IP de esta PC en la red local
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no envía paquetes; solo elige la interfaz
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:{port}"
    except Exception:
        return f"http://127.0.0.1:{port}"

def _device_config(device_id: str, request: Request) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dispositivos WHERE id = ?", (device_id,))
    dev = cursor.fetchone()
    conn.close()
    if not dev:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
    return {
        "dispositivo_id": dev["id"],
        "nombre": dev["nombre"],
        "token_api": dev["token_api"],
        "servidor_url": _server_url_for_devices(request),
        "laboratorio_id": dev["laboratorio_id"],
        "intervalo_latido_seg": dev["intervalo_latido_seg"] or 300,
        "pin_cerradura_gpio": 17,
        "pin_led_verde_gpio": 27,
        "pin_led_rojo_gpio": 22,
        "pin_buzzer_gpio": 23,
        "buzzer_activo_en_bajo": False,
        "modo_captura": "boton",
        "pin_boton_gpio": 24,
        "segundos_cuenta_regresiva": 5,
        "segundos_puerta_abierta": 5,
        "umbral_similitud_coseno": 0.363,
        "segundos_espera_mismo_usuario": 10,
        "intervalo_comandos_seg": 3,
        "camara_indice": 0,
        "resolucion_camara": [320, 240],
        "tamano_minimo_rostro_px": 60
    }

@app.get("/api/devices/{device_id}/config-file")
def download_device_config(device_id: str, request: Request, admin: dict = Depends(get_current_admin)):
    content = json.dumps(_device_config(device_id, request), indent=4, ensure_ascii=False)
    return Response(content=content, media_type="application/json", headers={
        "Content-Disposition": f"attachment; filename=config_{device_id}.json"
    })

# Archivos que necesita la Raspberry (sin simulador, cachés ni datos locales)
RPI_DIR = os.path.join(BASE_DIR, "raspberry_pi")
RPI_ARCHIVOS = ["rpi_main.py", "face_engine.py", "descargar_modelos.py", "test_conexion.py",
                "setup_rpi.sh", "requirements.txt", "LEEME_RASPBERRY.md"]

@app.get("/api/devices/{device_id}/rpi-package")
def download_device_package(device_id: str, request: Request, admin: dict = Depends(get_current_admin)):
    """Zip listo para la Raspberry: programa + config.json de esta puerta + modelos (si están en la PC)."""
    import zipfile
    cfg = _device_config(device_id, request)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def agregar(nombre: str, datos: bytes, ejecutable: bool = False):
            info = zipfile.ZipInfo(f"neoaccess/{nombre}", date_time=datetime.now().timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = ((0o755 if ejecutable else 0o644) | 0o100000) << 16
            z.writestr(info, datos)
        for nombre in RPI_ARCHIVOS:
            ruta = os.path.join(RPI_DIR, nombre)
            if os.path.isfile(ruta):
                with open(ruta, "rb") as f:
                    datos = f.read().replace(b"\r\n", b"\n")  # finales de línea de Linux
                agregar(nombre, datos, nombre.endswith(".sh"))
        agregar("config.json", json.dumps(cfg, indent=4, ensure_ascii=False).encode("utf-8"))
        modelos = os.path.join(RPI_DIR, "models")
        if os.path.isdir(modelos):
            for nombre in sorted(os.listdir(modelos)):
                if nombre.endswith(".onnx"):
                    with open(os.path.join(modelos, nombre), "rb") as f:
                        agregar(f"models/{nombre}", f.read())
    return Response(content=buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename=neoaccess_{device_id}.zip"
    })

# -------------------------------------------------------------
# RUTAS DE COMUNICACIÓN IOT PARA RASPBERRY PI ZERO W (RF-01, RF-08 al RF-10)
# -------------------------------------------------------------
@app.post("/api/iot/heartbeat")
def receive_heartbeat(payload: HeartbeatPayload):
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(payload.token_api, cursor, payload.dispositivo_id)

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    UPDATE dispositivos
    SET ultima_senal = ?, estado = 'en_linea', ip_address = COALESCE(?, ip_address)
    WHERE id = ?;
    """, (ahora, payload.ip_address, dev["id"]))

    conn.commit()
    conn.close()
    return {"status": "ok", "ack_time": ahora}

@app.get("/api/iot/sync-offline-rules")
def get_sync_offline_rules(
    dispositivo_id: Optional[str] = None,
    token_api: Optional[str] = None,
    x_device_token: Optional[str] = Header(None)
):
    # Preferir el token en el header X-Device-Token (no queda en logs de URL).
    # El parámetro de query se mantiene solo por compatibilidad con nodos antiguos.
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(x_device_token or token_api, cursor, dispositivo_id)
    dispositivo_id = dev["id"]

    lab_id = dev["laboratorio_id"]

    cursor.execute("""
    SELECT 
        u.id,
        u.nombre_completo,
        u.tipo,
        u.matricula_clave,
        u.grupo_id,
        u.carrera,
        mf.vector_encoding
    FROM usuarios u
    JOIN metadatos_faciales mf ON u.id = mf.usuario_id
    WHERE u.estado = 'activo';
    """)
    usuarios_cache = []
    for r in cursor.fetchall():
        usuarios_cache.append({
            "usuario_id": r["id"],
            "nombre": r["nombre_completo"],
            "tipo": r["tipo"],
            "matricula_clave": r["matricula_clave"],
            "grupo_id": r["grupo_id"],
            "carrera": r["carrera"],
            "vector_encoding": json.loads(r["vector_encoding"])
        })

    cursor.execute("""
    SELECT 
        h.id,
        h.grupo_id,
        h.docente_id,
        h.materia,
        h.dia_semana,
        h.hora_inicio,
        h.hora_fin
    FROM horarios h
    WHERE h.laboratorio_id = ? AND h.periodo_id = (SELECT id FROM periodos WHERE estado = 'activo' LIMIT 1);
    """, (lab_id,))
    horarios_cache = [dict(r) for r in cursor.fetchall()]

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, 'sincronizacion', 'Sincronización exitosa de reglas fuera de línea', ?);
    """, (dispositivo_id, ahora))

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "timestamp": ahora,
        "dispositivo_id": dispositivo_id,
        "laboratorio_id": lab_id,
        "usuarios": usuarios_cache,
        "horarios": horarios_cache,
        "tolerancia_min": TOLERANCIA_ENTRADA_MIN
    }

@app.post("/api/iot/access-attempt")
def log_access_attempt(payload: AccessAttemptPayload):
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(payload.token_api, cursor, payload.dispositivo_id)

    fecha_hora = payload.fecha_hora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Resolver usuario_id válido para respetar integridad referencial FK
    valid_user_id = None
    if payload.usuario_id:
        cursor.execute("SELECT id FROM usuarios WHERE id = ? OR matricula_clave = ?", (payload.usuario_id, payload.usuario_id))
        user_row = cursor.fetchone()
        if user_row:
            valid_user_id = user_row["id"]

    cursor.execute("""
    INSERT INTO registros_acceso (usuario_id, dispositivo_id, laboratorio_id, fecha_hora, resultado, motivo, sincronizado_offline, periodo_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT id FROM periodos WHERE estado = 'activo' LIMIT 1));
    """, (
        valid_user_id,
        dev["id"],
        dev["laboratorio_id"],
        fecha_hora,
        payload.resultado,
        payload.motivo,
        1 if payload.sincronizado_offline else 0
    ))

    conn.commit()
    conn.close()
    return {"status": "success", "message": "Acceso registrado en servidor central."}

@app.post("/api/iot/access-attempts-batch")
def log_access_attempts_batch(payload: List[AccessAttemptPayload]):
    if not payload:
        return {"status": "ok", "inserted": 0}

    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(payload[0].token_api, cursor, payload[0].dispositivo_id)

    # Todos los registros del lote deben pertenecer al mismo dispositivo autenticado
    for p in payload:
        if p.token_api != dev["token_api"] or p.dispositivo_id != dev["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="El lote contiene registros de otro dispositivo.")

    count = 0
    for p in payload:
        # Resolver usuario_id válido
        valid_user_id = None
        if p.usuario_id:
            cursor.execute("SELECT id FROM usuarios WHERE id = ? OR matricula_clave = ?", (p.usuario_id, p.usuario_id))
            user_row = cursor.fetchone()
            if user_row:
                valid_user_id = user_row["id"]

        cursor.execute("""
        SELECT id FROM registros_acceso 
        WHERE (usuario_id = ? OR (usuario_id IS NULL AND ? IS NULL)) 
          AND dispositivo_id = ? AND fecha_hora = ?
        """, (valid_user_id, valid_user_id, dev["id"], p.fecha_hora))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO registros_acceso (usuario_id, dispositivo_id, laboratorio_id, fecha_hora, resultado, motivo, sincronizado_offline, periodo_id)
            VALUES (?, ?, ?, ?, ?, ?, 1, COALESCE(
                (SELECT id FROM periodos WHERE DATE(?) BETWEEN fecha_inicio AND fecha_fin LIMIT 1),
                (SELECT id FROM periodos WHERE estado = 'activo' LIMIT 1)));
            """, (valid_user_id, dev["id"], dev["laboratorio_id"], p.fecha_hora, p.resultado, p.motivo, p.fecha_hora))
            count += 1

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, 'sincronizacion', ?, ?);
    """, (dev["id"], f"Sincronizados {count} registros fuera de línea", ahora))

    conn.commit()
    conn.close()
    return {"status": "ok", "inserted": count}

@app.get("/api/iot/commands")
def get_pending_commands(dispositivo_id: Optional[str] = None, x_device_token: Optional[str] = Header(None)):
    """La Raspberry Pi consulta aquí sus órdenes pendientes (y de paso cuenta como señal de vida)."""
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(x_device_token, cursor, dispositivo_id)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _expire_commands(cursor)
    cursor.execute("""
    SELECT id, tipo, solicitado_por, fecha_creacion FROM comandos_dispositivo
    WHERE dispositivo_id = ? AND estado = 'pendiente' ORDER BY id ASC;
    """, (dev["id"],))
    comandos = [dict(r) for r in cursor.fetchall()]
    if comandos:
        cursor.executemany("UPDATE comandos_dispositivo SET estado = 'entregado' WHERE id = ?",
                           [(c["id"],) for c in comandos])
    cursor.execute("UPDATE dispositivos SET ultima_senal = ?, estado = 'en_linea' WHERE id = ?", (ahora, dev["id"]))
    conn.commit()
    conn.close()
    return {"comandos": comandos}

@app.post("/api/iot/commands/{command_id}/ack")
def ack_command(command_id: int, payload: CommandAckPayload, x_device_token: Optional[str] = Header(None)):
    """La Raspberry Pi confirma que ejecutó (o no) la orden."""
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(x_device_token, cursor, payload.dispositivo_id)
    cursor.execute("SELECT * FROM comandos_dispositivo WHERE id = ? AND dispositivo_id = ?", (command_id, dev["id"]))
    cmd = cursor.fetchone()
    if not cmd:
        conn.close()
        raise HTTPException(status_code=404, detail="Comando no encontrado.")
    if cmd["estado"] != "entregado":
        conn.close()
        return {"status": "ignorado", "estado": cmd["estado"]}

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    estado = "ejecutado" if payload.exito else "fallido"
    cursor.execute("UPDATE comandos_dispositivo SET estado = ?, fecha_ejecucion = ?, detalle = ? WHERE id = ?",
                   (estado, ahora, payload.detalle, command_id))
    if payload.exito and cmd["tipo"] == "abrir_puerta":
        cursor.execute("""
        INSERT INTO registros_acceso (usuario_id, dispositivo_id, laboratorio_id, fecha_hora, resultado, motivo, sincronizado_offline, periodo_id)
        VALUES (NULL, ?, ?, ?, 'permitido', ?, 0, (SELECT id FROM periodos WHERE estado = 'activo' LIMIT 1));
        """, (dev["id"], dev["laboratorio_id"], ahora,
              f"Apertura remota autorizada por {cmd['solicitado_por'] or 'Administrador'} desde Dashboard"))
    conn.commit()
    conn.close()
    return {"status": "ok", "estado": estado}

@app.post("/api/iot/cleaning-log")
def log_cleaning(payload: CleaningPayload):
    conn = get_connection()
    cursor = conn.cursor()
    dev = verify_device_token(payload.token_api, cursor, payload.dispositivo_id)

    cursor.execute(
        "SELECT id FROM usuarios WHERE id = ? AND tipo = 'personal_limpieza' AND estado = 'activo'",
        (payload.personal_id,)
    )
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="El usuario no es personal de limpieza activo.")

    ahora = payload.fecha_hora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if payload.accion == "entrada":
        cursor.execute("""
        INSERT INTO registros_limpieza (personal_id, dispositivo_id, laboratorio_id, hora_entrada)
        VALUES (?, ?, ?, ?);
        """, (payload.personal_id, dev["id"], dev["laboratorio_id"], ahora))
    else:
        cursor.execute("""
        UPDATE registros_limpieza 
        SET hora_salida = ?
        WHERE id = (
            SELECT id FROM registros_limpieza 
            WHERE personal_id = ? AND dispositivo_id = ? AND hora_salida IS NULL
            ORDER BY id DESC LIMIT 1
        );
        """, (ahora, payload.personal_id, dev["id"]))

    conn.commit()
    conn.close()
    return {"status": "ok", "accion": payload.accion}

# -------------------------------------------------------------
# RUTAS DE HORARIOS Y GRUPOS (RF-17)
# -------------------------------------------------------------
@app.get("/api/schedules")
def get_schedules(
    laboratorio_id: Optional[str] = None,
    carrera: Optional[str] = None,
    periodo_id: Optional[str] = None,
    admin: dict = Depends(get_current_staff)
):
    conn = get_connection()
    cursor = conn.cursor()
    periodo_id = periodo_id or periodo_activo(cursor)["id"]

    query = """
    SELECT 
        h.*,
        l.nombre as laboratorio_nombre,
        l.edificio,
        l.carrera as laboratorio_carrera,
        g.nombre as grupo_nombre,
        u.nombre_completo as docente_nombre,
        g.clave as grupo_clave,
        g.carrera as grupo_carrera
    FROM horarios h
    JOIN laboratorios l ON h.laboratorio_id = l.id
    LEFT JOIN grupos g ON h.grupo_id = g.id
    LEFT JOIN usuarios u ON h.docente_id = u.id
    WHERE h.periodo_id = ?
    """
    params = [periodo_id]
    permitidas = carreras_de(admin)
    if permitidas is not None:
        query += f" AND COALESCE(g.carrera, l.carrera) IN ({','.join('?' * len(permitidas)) or 'NULL'})"
        params.extend(permitidas)
    if laboratorio_id and laboratorio_id != "todos":
        query += " AND h.laboratorio_id = ?"
        params.append(laboratorio_id)
    if carrera and carrera != "todas":
        query += " AND (l.carrera = ? OR g.carrera = ?)"
        params.extend([carrera, carrera])

    query += " ORDER BY CASE h.dia_semana WHEN 'Lunes' THEN 1 WHEN 'Martes' THEN 2 WHEN 'Miércoles' THEN 3 WHEN 'Jueves' THEN 4 WHEN 'Viernes' THEN 5 ELSE 6 END, h.hora_inicio ASC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

_SQL_INSERT_HORARIO = """
INSERT INTO horarios (grupo_id, laboratorio_id, docente_id, materia, dia_semana, hora_inicio, hora_fin, periodo_id)
VALUES (:grupo_id, :laboratorio_id, :docente_id, :materia, :dia_semana, :hora_inicio, :hora_fin, :periodo_id);
"""

@app.post("/api/schedules")
def create_schedule(payload: ScheduleCreate, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        horario, errores = validar_horario({
            "dia": payload.dia_semana, "hora_inicio": payload.hora_inicio, "hora_fin": payload.hora_fin,
            "laboratorio": payload.laboratorio_id, "grupo": payload.grupo_id,
            "docente": payload.docente_id, "materia": payload.materia,
        }, cursor, [], periodo_id=periodo_activo(cursor)["id"], carreras=carreras_de(admin))
        if errores:
            raise HTTPException(status_code=400, detail=" ".join(errores))
        cursor.execute(_SQL_INSERT_HORARIO, horario)
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "Horario registrado correctamente."}

@app.get("/api/schedules/template")
def schedules_template(admin: dict = Depends(get_current_staff)):
    """Plantilla de Excel con listas desplegables de los datos reales del sistema."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        periodo = periodo_activo(cursor)
        contenido = generar_plantilla(cursor, periodo["id"], carreras_de(admin), periodo["nombre"])
    finally:
        conn.close()
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plantilla_horarios_neoaccess.xlsx"'},
    )

MAX_IMPORT_BYTES = 2 * 1024 * 1024

@app.post("/api/schedules/import")
async def import_schedules(
    archivo: UploadFile = File(...),
    confirmar: bool = Query(False),
    admin: dict = Depends(get_current_staff),
):
    """
    confirmar=false: solo revisa y devuelve el resultado fila por fila.
    confirmar=true:  guarda las filas válidas (las que tienen error se omiten).
    """
    contenido = await archivo.read(MAX_IMPORT_BYTES + 1)
    if len(contenido) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="El archivo es demasiado grande (máximo 2 MB).")
    filas, error = leer_archivo(archivo.filename, contenido)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not filas:
        raise HTTPException(status_code=400, detail="El archivo no tiene horarios: llene al menos una fila debajo de los encabezados.")
    if len(filas) > 1000:
        raise HTTPException(status_code=400, detail="Máximo 1000 horarios por archivo.")

    materias = cargar_materias()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        periodo_id = periodo_activo(cursor)["id"]
        carreras = carreras_de(admin)
        resultado, ocupados, validos = [], [], []
        for f in filas:
            horario, errores = validar_horario(f, cursor, ocupados, materias, periodo_id=periodo_id, carreras=carreras)
            if horario:
                ocupados.append((horario["laboratorio_id"], horario["dia_semana"], horario["hora_inicio"],
                                 horario["hora_fin"], horario["grupo_id"], horario["docente_id"]))
                validos.append(horario)
            resultado.append({
                "fila": f["fila"],
                "datos": {k: ("" if v is None else str(v)) for k, v in f.items() if k != "fila"},
                "horario": horario,
                "errores": errores,
            })
        guardados = 0
        if confirmar and validos:
            cursor.executemany(_SQL_INSERT_HORARIO, validos)
            conn.commit()
            guardados = len(validos)
    finally:
        conn.close()
    return {
        "total": len(resultado),
        "validas": len(validos),
        "con_error": len(resultado) - len(validos),
        "guardados": guardados,
        "filas": resultado,
    }

@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("""SELECT h.periodo_id, COALESCE(g.carrera, l.carrera) AS carrera FROM horarios h
                            LEFT JOIN grupos g ON g.id = h.grupo_id LEFT JOIN laboratorios l ON l.id = h.laboratorio_id
                            WHERE h.id = ?""", (schedule_id,)).fetchone()
    try:
        if not row:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        if row["periodo_id"] != periodo_activo(cursor)["id"]:
            raise HTTPException(status_code=400, detail="Los horarios de periodos cerrados son histórico y no se modifican.")
        exigir_carrera(admin, row["carrera"], "este horario")
    except HTTPException:
        conn.close()
        raise
    cursor.execute("DELETE FROM horarios WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Horario eliminado."}

@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error_handler(request: Request, exc: sqlite3.IntegrityError):
    """Datos duplicados o referencias inexistentes: mensaje claro en lugar de un error 500."""
    msg = str(exc)
    if "UNIQUE" in msg:
        detalle = "Ya existe un registro con ese ID o clave."
    elif "FOREIGN KEY" in msg:
        detalle = "Uno de los datos hace referencia a un registro que no existe (grupo, laboratorio, etc.)."
    else:
        detalle = f"Datos inválidos: {msg}"
    return JSONResponse(status_code=400, content={"detail": detalle})

# -------------------------------------------------------------
# ADMINISTRADORES (alta, activar/desactivar, cambio de contraseña)
# -------------------------------------------------------------
@app.get("/api/admins")
def list_admins(admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        rows = conn.execute("""
        SELECT id, username, nombre, email, activo, fecha_creacion
        FROM administradores ORDER BY activo DESC, nombre;
        """).fetchall()
    finally:
        conn.close()
    return [{**dict(r), "es_yo": r["id"] == admin.get("user_id")} for r in rows]

@app.post("/api/admins")
def create_admin(payload: AdminCreate, admin: dict = Depends(get_current_admin)):
    username = payload.username.strip().lower()
    nombre = " ".join(payload.nombre.split())
    email = (payload.email or "").strip().lower() or None
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="El correo no tiene un formato válido.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM administradores WHERE lower(username) = ?", (username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Ya existe un administrador con el usuario '{username}'.")
        cur.execute("SELECT 1 FROM jefes_carrera WHERE lower(username) = ?", (username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"El usuario '{username}' ya lo usa un jefe de carrera.")
        # Evita que el usuario choque con la matrícula/clave de un alumno o docente al iniciar sesión
        cur.execute("SELECT 1 FROM usuarios WHERE lower(matricula_clave) = ? OR lower(id) = ?", (username, username))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ese usuario coincide con la matrícula o clave de un alumno/docente. Elija otro.")
        cur.execute("""
        INSERT INTO administradores (username, password_hash, nombre, email, activo, fecha_creacion)
        VALUES (?, ?, ?, ?, 1, ?);
        """, (username, hash_password(payload.password), nombre, email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Administrador '{username}' creado. Ya puede iniciar sesión."}

@app.post("/api/admins/{admin_id}/toggle")
def toggle_admin(admin_id: int, admin: dict = Depends(get_current_admin)):
    if admin_id == admin.get("user_id"):
        raise HTTPException(status_code=400, detail="No puede desactivar su propia cuenta.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, activo FROM administradores WHERE id = ?", (admin_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Administrador no encontrado.")
        nuevo = 0 if row["activo"] else 1
        if nuevo == 0:
            cur.execute("SELECT COUNT(*) FROM administradores WHERE activo = 1 AND id != ?", (admin_id,))
            if cur.fetchone()[0] == 0:
                raise HTTPException(status_code=400, detail="Debe quedar al menos un administrador activo.")
        cur.execute("UPDATE administradores SET activo = ? WHERE id = ?", (nuevo, admin_id))
        conn.commit()
    finally:
        conn.close()
    if nuevo == 0:
        destroy_sessions_for("administrador", admin_id)  # lo saca del sistema de inmediato
    return {"success": True, "activo": nuevo,
            "message": f"Administrador '{row['username']}' {'reactivado' if nuevo else 'desactivado'}."}

@app.post("/api/admins/me/password")
def change_own_password(payload: PasswordChange, authorization: Optional[str] = Header(None),
                        admin: dict = Depends(get_current_staff)):
    tabla = "administradores" if admin.get("rol") == "administrador" else "jefes_carrera"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT password_hash FROM {tabla} WHERE id = ?", (admin.get("user_id"),))
        row = cur.fetchone()
        if not row or not verify_password(payload.actual, row["password_hash"]):
            raise HTTPException(status_code=400, detail="La contraseña actual no es correcta.")
        if payload.actual == payload.nueva:
            raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta a la actual.")
        cur.execute(f"UPDATE {tabla} SET password_hash = ? WHERE id = ?",
                    (hash_password(payload.nueva), admin.get("user_id")))
        conn.commit()
    finally:
        conn.close()
    token = (authorization or "").replace("Bearer ", "").strip()
    destroy_sessions_for(admin.get("rol"), admin.get("user_id"), except_token=token)  # cierra otras sesiones
    return {"success": True, "message": "Contraseña actualizada. Se cerraron sus otras sesiones abiertas."}

@app.get("/api/groups")
def get_groups(periodo_id: Optional[str] = None, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    cursor = conn.cursor()
    periodo_id = periodo_id or periodo_activo(cursor)["id"]
    cursor.execute("""
        SELECT g.*, (SELECT COUNT(*) FROM usuarios u WHERE u.grupo_id = g.id AND u.estado = 'activo')
                  + (SELECT COUNT(*) FROM inscripciones i WHERE i.grupo_id = g.id) AS alumnos
        FROM grupos g WHERE g.periodo_id = ? ORDER BY g.carrera, g.semestre, g.nombre;""", (periodo_id,))
    permitidas = carreras_de(admin)
    rows = [dict(r) for r in cursor.fetchall() if permitidas is None or r["carrera"] in permitidas]
    conn.close()
    return rows

@app.post("/api/groups")
def create_group(payload: GroupCreate, admin: dict = Depends(get_current_staff)):
    gid = (payload.id or "").strip().upper()
    nombre = " ".join((payload.nombre or "").split())
    carrera = (payload.carrera or "").strip()
    if not re.fullmatch(r"[A-Z0-9-]{2,20}", gid):
        raise HTTPException(status_code=400, detail="La clave del grupo solo puede tener letras, números y guiones (2 a 20).")
    if len(nombre) < 2 or not carrera:
        raise HTTPException(status_code=400, detail="Indique el nombre y la carrera del grupo.")
    if not 1 <= int(payload.semestre) <= 12:
        raise HTTPException(status_code=400, detail="El semestre debe estar entre 1 y 12.")
    exigir_carrera(admin, carrera, "grupos de esa carrera")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM grupos WHERE id = ?", (gid,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Ya existe el grupo {gid}.")
        cursor.execute("""
        INSERT INTO grupos (id, nombre, carrera, semestre, periodo_id, clave)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (gid, nombre, carrera, int(payload.semestre), periodo_activo(cursor)["id"], gid))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Grupo {gid} registrado."}

@app.put("/api/groups/{group_id}")
def update_group(group_id: str, payload: GroupUpdate, admin: dict = Depends(get_current_staff)):
    nombre = " ".join((payload.nombre or "").split())
    carrera = (payload.carrera or "").strip()
    if len(nombre) < 2 or not carrera or not 1 <= int(payload.semestre) <= 12:
        raise HTTPException(status_code=400, detail="Revise nombre, carrera y semestre (1 a 12).")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT carrera, periodo_id FROM grupos WHERE id = ?", (group_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Grupo no encontrado.")
        if row["periodo_id"] != periodo_activo(cursor)["id"]:
            raise HTTPException(status_code=400, detail="Los grupos de periodos cerrados son histórico y no se modifican.")
        exigir_carrera(admin, row["carrera"], "este grupo")
        exigir_carrera(admin, carrera, "grupos de esa carrera")
        cursor.execute("UPDATE grupos SET nombre = ?, carrera = ?, semestre = ? WHERE id = ?",
                       (nombre, carrera, int(payload.semestre), group_id))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Grupo {group_id} actualizado."}

# -------------------------------------------------------------
# PERIODOS ESCOLARES (Ene-Jun / Ago-Dic) Y JEFES DE CARRERA
# -------------------------------------------------------------
@app.get("/api/periodos")
def list_periodos(admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    try:
        rows = conn.execute("""
        SELECT p.*,
          (SELECT COUNT(*) FROM grupos g WHERE g.periodo_id = p.id) AS grupos,
          (SELECT COUNT(*) FROM horarios h WHERE h.periodo_id = p.id) AS horarios,
          (SELECT COUNT(*) FROM registros_acceso r WHERE r.periodo_id = p.id) AS accesos,
          (SELECT COUNT(*) FROM inscripciones i WHERE i.periodo_id = p.id) AS inscripciones
        FROM periodos p ORDER BY p.id DESC;""").fetchall()
        activo = [dict(r) for r in rows if r["estado"] == "activo"]
        siguiente = periodo_siguiente(activo[0]["id"]) if activo else None
    finally:
        conn.close()
    return {"periodos": [dict(r) for r in rows], "siguiente": siguiente}

@app.post("/api/periodos/cerrar")
def cerrar_periodo(admin: dict = Depends(get_current_admin)):
    """
    Cierra el periodo activo y abre el siguiente. No se borra nada:
    - Se guarda la foto de qué alumno estaba en qué grupo (inscripciones).
    - Los grupos se archivan con id 'CLAVE@periodo' para poder reutilizar la clave.
    - Horarios y accesos quedan ligados al periodo cerrado (histórico de solo lectura).
    - Los alumnos quedan sin grupo hasta que se les asigne uno del nuevo periodo.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        actual = periodo_activo(cur)
        nuevo = periodo_siguiente(actual["id"])
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("PRAGMA foreign_keys = OFF;")
        cur.execute("""
        INSERT INTO inscripciones (periodo_id, usuario_id, nombre_completo, matricula_clave, carrera,
                                   grupo_id, grupo_clave, grupo_nombre, semestre)
        SELECT ?, u.id, u.nombre_completo, u.matricula_clave, COALESCE(g.carrera, u.carrera),
               g.id || '@' || ?, g.clave, g.nombre, g.semestre
        FROM usuarios u JOIN grupos g ON g.id = u.grupo_id
        WHERE u.tipo = 'alumno' AND g.periodo_id = ?;""", (actual["id"], actual["id"], actual["id"]))
        inscritos = cur.rowcount
        grupos = [r["id"] for r in cur.execute("SELECT id FROM grupos WHERE periodo_id = ?", (actual["id"],))]
        for gid in grupos:
            archivado = f"{gid}@{actual['id']}"
            cur.execute("UPDATE horarios SET grupo_id = ? WHERE grupo_id = ?", (archivado, gid))
            cur.execute("UPDATE usuarios SET grupo_id = NULL WHERE grupo_id = ?", (gid,))
            cur.execute("UPDATE grupos SET id = ? WHERE id = ?", (archivado, gid))
        cur.execute("UPDATE periodos SET estado = 'cerrado', fecha_cierre = ?, cerrado_por = ? WHERE id = ?",
                    (ahora, admin.get("username"), actual["id"]))
        cur.execute("INSERT OR IGNORE INTO periodos (id, nombre, fecha_inicio, fecha_fin, estado) VALUES (?, ?, ?, ?, 'activo')",
                    (nuevo["id"], nuevo["nombre"], nuevo["fecha_inicio"], nuevo["fecha_fin"]))
        cur.execute("UPDATE periodos SET estado = 'activo', fecha_cierre = NULL WHERE id = ?", (nuevo["id"],))
        conn.commit()
        cur.execute("PRAGMA foreign_keys = ON;")
        problemas = cur.execute("PRAGMA foreign_key_check;").fetchall()
        if problemas:
            print("[PERIODOS] Aviso de integridad tras el cierre:", problemas[:5])
    finally:
        conn.close()
    return {"success": True, "message": f"Periodo {actual['nombre']} cerrado. Periodo activo: {nuevo['nombre']}.",
            "cerrado": actual["id"], "activo": nuevo["id"], "grupos_archivados": len(grupos), "inscripciones": inscritos}

def _jefe_dict(cursor, row) -> dict:
    d = {k: row[k] for k in row.keys() if k != "password_hash"}
    d["carreras"] = [r["carrera"] for r in cursor.execute(
        "SELECT carrera FROM jefe_carreras WHERE jefe_id = ? ORDER BY carrera", (row["id"],))]
    return d

def _validar_carreras(carreras: list) -> list:
    oficiales = set(cargar_materias().keys())
    limpias = sorted({c.strip() for c in carreras if c and c.strip()})
    if not limpias:
        raise HTTPException(status_code=400, detail="Asigne al menos una carrera.")
    malas = [c for c in limpias if c not in oficiales]
    if malas:
        raise HTTPException(status_code=400, detail=f"Carrera no válida: {', '.join(malas)}.")
    return limpias

@app.get("/api/jefes")
def list_jefes(admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        return [_jefe_dict(cur, r) for r in cur.execute("SELECT * FROM jefes_carrera ORDER BY activo DESC, nombre").fetchall()]
    finally:
        conn.close()

@app.post("/api/jefes")
def create_jefe(payload: JefeCreate, admin: dict = Depends(get_current_admin)):
    username = payload.username.strip().lower()
    nombre = " ".join(payload.nombre.split())
    email = (payload.email or "").strip().lower() or None
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="El correo no tiene un formato válido.")
    carreras = _validar_carreras(payload.carreras)
    conn = get_connection()
    try:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM jefes_carrera WHERE lower(username) = ? UNION SELECT 1 FROM administradores WHERE lower(username) = ?",
                       (username, username)).fetchone():
            raise HTTPException(status_code=400, detail=f"El usuario '{username}' ya está en uso.")
        if cur.execute("SELECT 1 FROM usuarios WHERE lower(matricula_clave) = ? OR lower(id) = ?", (username, username)).fetchone():
            raise HTTPException(status_code=400, detail="Ese usuario coincide con la matrícula o clave de un alumno/docente. Elija otro.")
        cur.execute("INSERT INTO jefes_carrera (username, password_hash, nombre, email, activo, fecha_creacion) VALUES (?, ?, ?, ?, 1, ?)",
                    (username, hash_password(payload.password), nombre, email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        jefe_id = cur.lastrowid
        cur.executemany("INSERT INTO jefe_carreras (jefe_id, carrera) VALUES (?, ?)", [(jefe_id, c) for c in carreras])
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Jefe de carrera '{username}' creado. Ya puede iniciar sesión."}

@app.put("/api/jefes/{jefe_id}/carreras")
def update_jefe_carreras(jefe_id: int, payload: JefeCarreras, admin: dict = Depends(get_current_admin)):
    carreras = _validar_carreras(payload.carreras)
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not cur.execute("SELECT 1 FROM jefes_carrera WHERE id = ?", (jefe_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Jefe de carrera no encontrado.")
        cur.execute("DELETE FROM jefe_carreras WHERE jefe_id = ?", (jefe_id,))
        cur.executemany("INSERT INTO jefe_carreras (jefe_id, carrera) VALUES (?, ?)", [(jefe_id, c) for c in carreras])
        conn.commit()
    finally:
        conn.close()
    destroy_sessions_for("jefe_carrera", jefe_id)  # vuelve a entrar con sus nuevas carreras
    return {"success": True, "message": "Carreras actualizadas. Si tenía la sesión abierta, deberá entrar de nuevo."}

@app.post("/api/jefes/{jefe_id}/toggle")
def toggle_jefe(jefe_id: int, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT username, activo FROM jefes_carrera WHERE id = ?", (jefe_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Jefe de carrera no encontrado.")
        nuevo = 0 if row["activo"] else 1
        cur.execute("UPDATE jefes_carrera SET activo = ? WHERE id = ?", (nuevo, jefe_id))
        conn.commit()
    finally:
        conn.close()
    if not nuevo:
        destroy_sessions_for("jefe_carrera", jefe_id)
    return {"success": True, "activo": nuevo,
            "message": f"Jefe de carrera '{row['username']}' {'reactivado' if nuevo else 'desactivado'}."}

# -------------------------------------------------------------
# ELIMINACIÓN DEFINITIVA (con vista previa de lo que se borra)
# -------------------------------------------------------------
# Cuántos registros relacionados se pierden al eliminar cada cosa.
# Las cascadas las hace SQLite (PRAGMA foreign_keys = ON en get_connection).
_IMPACTO_ELIMINAR = {
    "usuario": {
        "tabla": "usuarios",
        "conteos": {
            "rostro": "SELECT COUNT(*) FROM metadatos_faciales WHERE usuario_id = ?",
            "horarios": "SELECT COUNT(*) FROM horarios WHERE docente_id = ?",
            "bitacoras_limpieza": "SELECT COUNT(*) FROM registros_limpieza WHERE personal_id = ?",
            "accesos_conservados": "SELECT COUNT(*) FROM registros_acceso WHERE usuario_id = ?",
        },
    },
    "laboratorio": {
        "tabla": "laboratorios",
        "conteos": {
            "dispositivos_sin_lab": "SELECT COUNT(*) FROM dispositivos WHERE laboratorio_id = ?",
            "horarios": "SELECT COUNT(*) FROM horarios WHERE laboratorio_id = ?",
            "accesos": "SELECT COUNT(*) FROM registros_acceso WHERE laboratorio_id = ?",
            "bitacoras_limpieza": "SELECT COUNT(*) FROM registros_limpieza WHERE laboratorio_id = ?",
        },
    },
    "dispositivo": {
        "tabla": "dispositivos",
        "conteos": {
            "accesos": "SELECT COUNT(*) FROM registros_acceso WHERE dispositivo_id = ?",
            "bitacoras_limpieza": "SELECT COUNT(*) FROM registros_limpieza WHERE dispositivo_id = ?",
            "eventos": "SELECT COUNT(*) FROM eventos_dispositivo WHERE dispositivo_id = ?",
        },
    },
    "grupo": {
        "tabla": "grupos",
        "conteos": {
            "alumnos_sin_grupo": "SELECT COUNT(*) FROM usuarios WHERE grupo_id = ?",
            "horarios": "SELECT COUNT(*) FROM horarios WHERE grupo_id = ?",
        },
    },
}

def _impacto(cursor, tipo: str, item_id: str) -> dict:
    cfg = _IMPACTO_ELIMINAR.get(tipo)
    if not cfg:
        raise HTTPException(status_code=404, detail="Tipo no válido.")
    cursor.execute(f"SELECT 1 FROM {cfg['tabla']} WHERE id = ?", (item_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="El registro ya no existe.")
    return {k: cursor.execute(q, (item_id,)).fetchone()[0] for k, q in cfg["conteos"].items()}

@app.get("/api/delete-preview/{tipo}/{item_id}")
def delete_preview(tipo: str, item_id: str, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        return _impacto(conn.cursor(), tipo, item_id)
    finally:
        conn.close()

def _eliminar(tipo: str, item_id: str) -> dict:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        impacto = _impacto(cursor, tipo, item_id)
        cursor.execute(f"DELETE FROM {_IMPACTO_ELIMINAR[tipo]['tabla']} WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    return impacto

@app.delete("/api/users/{user_id}/permanent")
def delete_user_permanent(user_id: str, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT nombre_completo, tipo FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    impacto = _eliminar("usuario", user_id)
    if row:
        destroy_sessions_for(row["tipo"], user_id)  # si tenía sesión abierta, se cierra
    return {"success": True, "impacto": impacto,
            "message": f"{row['nombre_completo'] if row else user_id} eliminado definitivamente."}

@app.delete("/api/labs/{lab_id}/permanent")
def delete_lab_permanent(lab_id: str, admin: dict = Depends(get_current_admin)):
    impacto = _eliminar("laboratorio", lab_id)
    return {"success": True, "impacto": impacto, "message": f"Laboratorio {lab_id} eliminado definitivamente."}

@app.delete("/api/devices/{device_id}/permanent")
def delete_device_permanent(device_id: str, admin: dict = Depends(get_current_admin)):
    impacto = _eliminar("dispositivo", device_id)
    return {"success": True, "impacto": impacto, "message": f"Dispositivo {device_id} eliminado definitivamente."}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: str, admin: dict = Depends(get_current_admin)):
    impacto = _eliminar("grupo", group_id)
    return {"success": True, "impacto": impacto, "message": f"Grupo {group_id} eliminado."}

# -------------------------------------------------------------
# RUTAS DE USUARIOS: ALUMNOS, MAESTROS, LIMPIEZA (RF-14, RF-15, RF-16)
# -------------------------------------------------------------
@app.get("/api/users")
def get_users(
    tipo: Optional[str] = None,
    q: Optional[str] = None,
    admin: dict = Depends(get_current_staff)
):
    if admin.get("rol") == "jefe_carrera":
        tipo = "docente"   # el jefe de carrera solo consulta docentes
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        u.*,
        g.nombre as grupo_nombre,
        CASE WHEN mf.id IS NOT NULL THEN 1 ELSE 0 END as tiene_rostro,
        mf.fecha_registro as fecha_registro_rostro
    FROM usuarios u
    LEFT JOIN grupos g ON u.grupo_id = g.id
    LEFT JOIN metadatos_faciales mf ON u.id = mf.usuario_id
    WHERE 1=1
    """
    params = []
    if tipo:
        query += " AND u.tipo = ?"
        params.append(tipo)
    if q:
        query += " AND (u.nombre_completo LIKE ? OR u.matricula_clave LIKE ?)"
        term = f"%{q}%"
        params.extend([term, term])

    query += " ORDER BY u.fecha_registro DESC;"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        r["tiene_password"] = bool(r.pop("password_hash", None))  # nunca exponer hashes de contraseña
    return rows

TIPOS_USUARIO = ("alumno", "docente", "personal_limpieza")

def _validar_usuario(payload: UserCreate, cursor) -> dict:
    """Normaliza y valida los datos de un usuario; lanza 400 con un mensaje claro."""
    datos = {
        "id": (payload.id or "").strip().upper(),
        "nombre_completo": " ".join((payload.nombre_completo or "").split()),
        "tipo": (payload.tipo or "").strip(),
        "matricula_clave": (payload.matricula_clave or "").strip(),
        "carrera": (payload.carrera or "").strip() or None,
        "grupo_id": (payload.grupo_id or "").strip().upper() or None,
        "estado": (payload.estado or "activo").strip() or "activo",
        "password": payload.password or None,
    }
    if datos["password"] is not None and not 8 <= len(datos["password"]) <= 128:
        raise HTTPException(status_code=400, detail="La contraseña debe tener de 8 a 128 caracteres.")
    if not datos["id"] or not datos["nombre_completo"] or not datos["matricula_clave"]:
        raise HTTPException(status_code=400, detail="El ID, el nombre y la matrícula/clave son obligatorios.")
    if datos["tipo"] not in TIPOS_USUARIO:
        raise HTTPException(status_code=400, detail="Tipo de usuario inválido.")
    if datos["estado"] not in ("activo", "inactivo"):
        raise HTTPException(status_code=400, detail="Estado inválido.")
    if datos["grupo_id"]:
        cursor.execute("SELECT 1 FROM grupos WHERE id = ?", (datos["grupo_id"],))
        if not cursor.fetchone():
            cursor.execute("SELECT id FROM grupos ORDER BY id")
            existentes = ", ".join(r["id"] for r in cursor.fetchall()) or "ninguno"
            raise HTTPException(
                status_code=400,
                detail=f"El grupo '{datos['grupo_id']}' no existe. Grupos registrados: {existentes}."
            )
    return datos

def _exigir_docente_propio(admin: dict, cursor, user_id: str):
    """El jefe de carrera solo administra docentes de sus carreras."""
    if admin.get("rol") != "jefe_carrera":
        return
    row = cursor.execute("SELECT tipo, carrera FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if row["tipo"] != "docente":
        raise HTTPException(status_code=403, detail="Solo puede administrar docentes.")
    exigir_carrera(admin, row["carrera"], "este docente")

@app.post("/api/users")
def create_user(payload: UserCreate, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        d = _validar_usuario(payload, cursor)
        if admin.get("rol") == "jefe_carrera":
            if d["tipo"] != "docente":
                raise HTTPException(status_code=403, detail="El jefe de carrera solo puede registrar docentes.")
            exigir_carrera(admin, d["carrera"], "docentes de esa carrera")
        cursor.execute("SELECT id FROM usuarios WHERE id = ? OR matricula_clave = ?", (d["id"], d["matricula_clave"]))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="El ID o la matrícula/clave ya existen.")
        try:
            cursor.execute("""
            INSERT INTO usuarios (id, nombre_completo, tipo, matricula_clave, carrera, grupo_id, estado, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (d["id"], d["nombre_completo"], d["tipo"], d["matricula_clave"], d["carrera"], d["grupo_id"], d["estado"],
                  hash_password(d["password"]) if d["password"] else None))
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"No se pudo registrar el usuario: {e}")
        return {"success": True, "message": f"Usuario '{d['nombre_completo']}' registrado exitosamente.", "id": d["id"]}
    finally:
        conn.close()

@app.put("/api/users/{user_id}")
def update_user(user_id: str, payload: UserCreate, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        actual = cursor.execute("SELECT tipo, estado FROM usuarios WHERE id = ?", (user_id,)).fetchone()
        if not actual:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        d = _validar_usuario(payload, cursor)
        cursor.execute("SELECT 1 FROM usuarios WHERE matricula_clave = ? AND id <> ?", (d["matricula_clave"], user_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Esa matrícula/clave ya pertenece a otro usuario.")
        try:
            cursor.execute("""
            UPDATE usuarios
            SET nombre_completo = ?, tipo = ?, matricula_clave = ?, carrera = ?, grupo_id = ?, estado = ?
            WHERE id = ?;
            """, (d["nombre_completo"], d["tipo"], d["matricula_clave"], d["carrera"], d["grupo_id"], d["estado"], user_id))
            if d["password"]:
                cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (hash_password(d["password"]), user_id))
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"No se pudo actualizar el usuario: {e}")
        # Nueva contraseña, baja o cambio de tipo: se cierran sus sesiones abiertas
        if d["password"] or d["estado"] != actual["estado"] or d["tipo"] != actual["tipo"]:
            destroy_sessions_for(actual["tipo"], user_id)
        return {"success": True, "message": "Usuario actualizado." + (" Contraseña cambiada." if d["password"] else "")}
    finally:
        conn.close()

@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _exigir_docente_propio(admin, cursor, user_id)
    except HTTPException:
        conn.close()
        raise
    cursor.execute("UPDATE usuarios SET estado = 'inactivo' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Usuario dado de baja (marcado inactivo)."}

@app.post("/api/users/{user_id}/reactivate")
def reactivate_user(user_id: str, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        _exigir_docente_propio(admin, cur, user_id)
        cur.execute("UPDATE usuarios SET estado = 'activo' WHERE id = ?", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "Usuario reactivado."}

@app.get("/api/users/{user_id}/details")
def get_user_details(user_id: str, admin: dict = Depends(get_current_staff)):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _exigir_docente_propio(admin, cursor, user_id)
    except HTTPException:
        conn.close()
        raise

    cursor.execute("""
    SELECT u.*, g.nombre as grupo_nombre, mf.dimension, mf.calidad_muestra, mf.fecha_registro as fecha_rostro
    FROM usuarios u
    LEFT JOIN grupos g ON u.grupo_id = g.id
    LEFT JOIN metadatos_faciales mf ON u.id = mf.usuario_id
    WHERE u.id = ?;
    """, (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    cursor.execute("""
    SELECT 
        ra.*,
        l.nombre as laboratorio_nombre,
        d.nombre as dispositivo_nombre
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN dispositivos d ON ra.dispositivo_id = d.id
    WHERE ra.usuario_id = ?
    ORDER BY ra.fecha_hora DESC
    LIMIT 50;
    """, (user_id,))
    history = [dict(r) for r in cursor.fetchall()]

    inscripciones = [dict(r) for r in cursor.execute("""
        SELECT i.periodo_id, p.nombre AS periodo_nombre, i.grupo_clave, i.grupo_nombre, i.carrera, i.semestre
        FROM inscripciones i LEFT JOIN periodos p ON p.id = i.periodo_id
        WHERE i.usuario_id = ? ORDER BY i.periodo_id DESC;""", (user_id,))]

    conn.close()
    usuario = dict(user)
    usuario.pop("password_hash", None)  # nunca exponer hashes de contraseña
    return {
        "usuario": usuario,
        "historial": history,
        "inscripciones": inscripciones
    }

@app.post("/api/users/{user_id}/facial-metadata")
def save_facial_metadata(user_id: str, payload: FacialMetadataCreate, admin: dict = Depends(get_current_admin)):
    if len(payload.vector_encoding) != 128:
        raise HTTPException(status_code=400, detail="El vector facial debe tener exactamente 128 dimensiones.")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM usuarios WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    vector_json = json.dumps(payload.vector_encoding)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO metadatos_faciales (usuario_id, vector_encoding, dimension, calidad_muestra, fecha_registro)
    VALUES (?, ?, 128, ?, ?)
    ON CONFLICT(usuario_id) DO UPDATE SET
        vector_encoding = excluded.vector_encoding,
        calidad_muestra = excluded.calidad_muestra,
        fecha_registro = excluded.fecha_registro;
    """, (user_id, vector_json, payload.calidad_muestra or 1.0, ahora))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Metadatos faciales registrados exitosamente (sin foto guardada)."}

# -------------------------------------------------------------
# REGISTRO FACIAL REAL (YuNet + SFace) DESDE EL DASHBOARD (RF-07, RF-15)
# -------------------------------------------------------------
import base64
import threading
from raspberry_pi.face_engine import FaceEngine, FaceEngineUnavailable, engine_status

_FACE_ENGINE = None
_FACE_ENGINE_LOCK = threading.Lock()
MAX_CAPTURE_IMAGES = 5
MAX_IMAGE_BYTES = 2 * 1024 * 1024  # 2 MB por fotograma

def get_face_engine() -> FaceEngine:
    global _FACE_ENGINE
    with _FACE_ENGINE_LOCK:
        if _FACE_ENGINE is None:
            _FACE_ENGINE = FaceEngine()
        return _FACE_ENGINE

@app.get("/api/face-engine/status")
def face_engine_status(admin: dict = Depends(get_current_admin)):
    st = engine_status()
    st["listo"] = bool(st["opencv"] and st["modelo_deteccion"] and st["modelo_reconocimiento"])
    return st

@app.post("/api/users/{user_id}/facial-capture")
def facial_capture(user_id: str, payload: FacialCapturePayload, admin: dict = Depends(get_current_admin)):
    """
    Recibe 1-5 fotogramas (JPEG en base64) de la webcam del Dashboard, extrae el
    vector de 128-d con el mismo motor que usan las puertas y guarda SOLO el vector.
    RF-07: las imágenes se decodifican en RAM y se descartan; nunca tocan el disco.
    """
    if not payload.imagenes or len(payload.imagenes) > MAX_CAPTURE_IMAGES:
        raise HTTPException(status_code=400, detail=f"Envíe entre 1 y {MAX_CAPTURE_IMAGES} fotogramas.")
    try:
        engine = get_face_engine()
    except FaceEngineUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    vectores, scores = [], []
    for img_b64 in payload.imagenes:
        if "," in img_b64[:100]:
            img_b64 = img_b64.split(",", 1)[1]  # quitar prefijo data:image/jpeg;base64,
        try:
            raw = base64.b64decode(img_b64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Fotograma con base64 inválido.")
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Fotograma demasiado grande (máx. 2 MB).")
        try:
            vec, score = engine.extract_vector_from_bytes(raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            del raw  # RF-07
        if vec:
            vectores.append(vec)
            scores.append(score)

    if not vectores:
        raise HTTPException(status_code=422, detail="No se detectó ningún rostro. Mire de frente a la cámara con buena iluminación.")

    # Promedio de los vectores normalizados: más robusto que un solo fotograma
    import numpy as np
    m = np.array(vectores, dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    vector_final = m.mean(axis=0)
    vector_final = (vector_final / np.linalg.norm(vector_final)).astype(float).tolist()
    calidad = round(float(sum(scores) / len(scores)), 3)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO metadatos_faciales (usuario_id, vector_encoding, dimension, calidad_muestra, fecha_registro)
    VALUES (?, ?, 128, ?, ?)
    ON CONFLICT(usuario_id) DO UPDATE SET
        vector_encoding = excluded.vector_encoding,
        calidad_muestra = excluded.calidad_muestra,
        fecha_registro = excluded.fecha_registro;
    """, (user_id, json.dumps(vector_final), calidad, ahora))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": f"Vector facial registrado con {len(vectores)} de {len(payload.imagenes)} fotogramas válidos (sin fotos guardadas).",
        "fotogramas_validos": len(vectores),
        "calidad_muestra": calidad
    }

# -------------------------------------------------------------
# RUTAS DE REPORTES (Sección 5, 9, RF-20)
# -------------------------------------------------------------
def _filtros_reporte(query: str, params: list, admin: dict, laboratorio_id, fecha_inicio, fecha_fin,
                     resultado, periodo_id, q) -> str:
    if laboratorio_id and laboratorio_id != "todos":
        query += " AND ra.laboratorio_id = ?"
        params.append(laboratorio_id)
    if resultado and resultado != "todos":
        query += " AND ra.resultado = ?"
        params.append(resultado)
    if fecha_inicio:
        query += " AND DATE(ra.fecha_hora) >= DATE(?)"
        params.append(fecha_inicio)
    if fecha_fin:
        query += " AND DATE(ra.fecha_hora) <= DATE(?)"
        params.append(fecha_fin)
    if periodo_id and periodo_id != "todos":
        query += " AND ra.periodo_id = ?"
        params.append(periodo_id)
    if q and q.strip():
        query += " AND (u.nombre_completo LIKE ? OR u.matricula_clave LIKE ? OR ra.motivo LIKE ?)"
        term = f"%{q.strip()}%"
        params.extend([term, term, term])
    permitidas = carreras_de(admin)
    if permitidas is not None:
        marcas = ",".join("?" * len(permitidas)) or "NULL"
        query += f" AND (u.carrera IN ({marcas}) OR l.carrera IN ({marcas}))"
        params.extend(permitidas + permitidas)
    return query + " ORDER BY ra.fecha_hora DESC;"

@app.get("/api/reports/data")
def get_report_data(
    laboratorio_id: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    resultado: Optional[str] = None,
    periodo_id: Optional[str] = None,
    q: Optional[str] = None,
    admin: dict = Depends(get_current_staff)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        ra.id,
        ra.fecha_hora,
        ra.resultado,
        ra.motivo,
        ra.sincronizado_offline,
        l.nombre as laboratorio,
        l.edificio,
        u.nombre_completo as usuario,
        u.tipo as tipo_usuario,
        u.matricula_clave,
        g.nombre as grupo,
        d.nombre as dispositivo,
        ra.periodo_id
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    LEFT JOIN grupos g ON u.grupo_id = g.id
    LEFT JOIN dispositivos d ON ra.dispositivo_id = d.id
    WHERE 1=1
    """
    params = []
    query = _filtros_reporte(query, params, admin, laboratorio_id, fecha_inicio, fecha_fin, resultado, periodo_id, q)
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/reports/export-csv")
def export_report_csv(
    laboratorio_id: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    resultado: Optional[str] = None,
    periodo_id: Optional[str] = None,
    q: Optional[str] = None,
    admin: dict = Depends(get_current_staff)
):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        ra.id,
        ra.fecha_hora,
        l.nombre as laboratorio,
        l.edificio,
        COALESCE(u.nombre_completo, 'Desconocido / No Registrado') as persona,
        COALESCE(u.tipo, 'N/A') as tipo,
        COALESCE(u.matricula_clave, 'N/A') as matricula_o_clave,
        ra.resultado,
        ra.motivo,
        CASE WHEN ra.sincronizado_offline = 1 THEN 'Sí' ELSE 'No' END as fue_offline,
        COALESCE(ra.periodo_id, '') as periodo
    FROM registros_acceso ra
    LEFT JOIN laboratorios l ON ra.laboratorio_id = l.id
    LEFT JOIN usuarios u ON ra.usuario_id = u.id
    WHERE 1=1
    """
    params = []
    query = _filtros_reporte(query, params, admin, laboratorio_id, fecha_inicio, fecha_fin, resultado, periodo_id, q)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(["ID", "Fecha y Hora", "Laboratorio", "Edificio", "Persona", "Tipo", "Matrícula/Clave", "Resultado", "Motivo", "Sincronizado Offline", "Periodo"])
    for r in rows:
        writer.writerow(list(r))

    output.seek(0)
    filename = f"reporte_neoaccess_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/reports/cleaning")
def get_cleaning_reports(admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        rl.*,
        u.nombre_completo as personal_nombre,
        u.matricula_clave as personal_clave,
        l.nombre as laboratorio_nombre,
        l.edificio
    FROM registros_limpieza rl
    JOIN usuarios u ON rl.personal_id = u.id
    JOIN laboratorios l ON rl.laboratorio_id = l.id
    ORDER BY rl.hora_entrada DESC;
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# -------------------------------------------------------------
# ARCHIVOS ESTÁTICOS Y PÁGINA PRINCIPAL MODULAR
# -------------------------------------------------------------
app.mount("/styles", StaticFiles(directory=STYLES_DIR), name="styles")
app.mount("/scripts", StaticFiles(directory=SCRIPTS_DIR), name="scripts")

@app.get("/login")
@app.get("/login.html")
def serve_login():
    login_file = os.path.join(HTML_DIR, "login.html")
    if os.path.exists(login_file):
        return FileResponse(login_file, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        })
    return HTMLResponse("<h3>NeoAccess - Página de login no encontrada.</h3>")

@app.get("/")
def serve_index():
    index_file = os.path.join(HTML_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        })
    return HTMLResponse("<h3>NeoAccess - El frontend se está cargando...</h3>")

if __name__ == "__main__":
    import uvicorn
    print("Iniciando NeoAccess IoT Server en http://0.0.0.0:8000 ...")
    # Recarga automática solo en desarrollo: set NEOACCESS_DEV=1
    dev_mode = os.environ.get("NEOACCESS_DEV") == "1"
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=dev_mode)
