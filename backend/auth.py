"""
NeoAccess - Módulo de Autenticación y Seguridad Multi-Rol
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\backend\\auth.py
Manejo de sesiones para Administradores, Docentes, Alumnos y Personal de Limpieza.
"""

import hashlib
import secrets
import threading
from datetime import datetime, timedelta

ACTIVE_SESSIONS = {}
SESSION_DURATION_HOURS = 12

# -------------------------------------------------------------
# HASHING DE CONTRASEÑAS (PBKDF2-HMAC-SHA256, solo librería estándar)
# Formato: pbkdf2_sha256$<iteraciones>$<sal_hex>$<hash_hex>
# Se aceptan hashes antiguos "sal:sha256" y se migran al iniciar sesión.
# -------------------------------------------------------------
PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000  # Recomendación OWASP 2023+ para PBKDF2-HMAC-SHA256

def hash_password(password: str, salt: str = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Genera un hash lento (PBKDF2) con sal aleatoria para almacenar contraseñas."""
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"{PBKDF2_ALGORITHM}${iterations}${salt}${dk.hex()}"

def _is_legacy_hash(stored_hash: str) -> bool:
    return bool(stored_hash) and not stored_hash.startswith(PBKDF2_ALGORITHM + "$") and ":" in stored_hash

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifica si la contraseña coincide con el hash almacenado (PBKDF2 o formato heredado)."""
    try:
        if not stored_hash:
            return False
        if stored_hash.startswith(PBKDF2_ALGORITHM + "$"):
            _, iterations, salt, expected = stored_hash.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
            return secrets.compare_digest(dk.hex(), expected)
        if _is_legacy_hash(stored_hash):
            salt, expected = stored_hash.split(":")
            computed = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed, expected)
        return False
    except Exception:
        return False

def needs_rehash(stored_hash: str) -> bool:
    """Indica si el hash debe regenerarse (formato antiguo o menos iteraciones de las actuales)."""
    if not stored_hash or _is_legacy_hash(stored_hash):
        return True
    try:
        return int(stored_hash.split("$")[1]) < PBKDF2_ITERATIONS
    except Exception:
        return True

# -------------------------------------------------------------
# LÍMITE DE INTENTOS DE LOGIN (anti fuerza bruta)
# Bloquea temporalmente una combinación IP+usuario y también la IP completa.
# -------------------------------------------------------------
MAX_FAILED_PER_USER = 5          # intentos fallidos por (IP, usuario)
MAX_FAILED_PER_IP = 20           # intentos fallidos por IP (cualquier usuario)
FAILED_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)

_FAILED_ATTEMPTS: dict = {}      # clave -> lista de datetimes de fallos
_LOCKED_UNTIL: dict = {}         # clave -> datetime
_ATTEMPTS_LOCK = threading.Lock()

def _attempt_keys(ip: str, username: str):
    return (f"ip:{ip}", f"user:{ip}:{(username or '').strip().lower()}")

def login_locked_seconds(ip: str, username: str) -> int:
    """Segundos restantes de bloqueo para esta IP/usuario (0 si no está bloqueado)."""
    now = datetime.now()
    with _ATTEMPTS_LOCK:
        remaining = 0
        for key in _attempt_keys(ip, username):
            until = _LOCKED_UNTIL.get(key)
            if until:
                if until > now:
                    remaining = max(remaining, int((until - now).total_seconds()) + 1)
                else:
                    del _LOCKED_UNTIL[key]
        return remaining

def register_failed_login(ip: str, username: str):
    now = datetime.now()
    ip_key, user_key = _attempt_keys(ip, username)
    with _ATTEMPTS_LOCK:
        for key, limit in ((ip_key, MAX_FAILED_PER_IP), (user_key, MAX_FAILED_PER_USER)):
            recent = [t for t in _FAILED_ATTEMPTS.get(key, []) if now - t < FAILED_WINDOW]
            recent.append(now)
            _FAILED_ATTEMPTS[key] = recent
            if len(recent) >= limit:
                _LOCKED_UNTIL[key] = now + LOCKOUT_DURATION
                _FAILED_ATTEMPTS[key] = []

def reset_failed_logins(ip: str, username: str):
    _, user_key = _attempt_keys(ip, username)
    with _ATTEMPTS_LOCK:
        _FAILED_ATTEMPTS.pop(user_key, None)
        _LOCKED_UNTIL.pop(user_key, None)

def create_session(username: str, user_id: any, nombre: str, rol: str = "administrador", extra_data: dict = None) -> str:
    """Genera un token de sesión seguro con su rol institucional correspondiente."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)
    session_data = {
        "username": username,
        "user_id": user_id,
        "nombre": nombre,
        "rol": rol,
        "expires_at": expires_at
    }
    if extra_data:
        session_data.update(extra_data)
    ACTIVE_SESSIONS[token] = session_data
    return token

def validate_session(token: str) -> dict | None:
    """Verifica si un token de sesión es válido y no ha expirado."""
    if not token or token not in ACTIVE_SESSIONS:
        return None
    session = ACTIVE_SESSIONS[token]
    if datetime.now() > session["expires_at"]:
        del ACTIVE_SESSIONS[token]
        return None
    return session

def destroy_session(token: str) -> bool:
    """Cierra la sesión activa."""
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
        return True
    return False

def destroy_sessions_for(rol: str, user_id, except_token: str = None) -> int:
    """Cierra todas las sesiones de una cuenta (p. ej. al desactivar un administrador)."""
    tokens = [t for t, s in ACTIVE_SESSIONS.items()
              if s.get("rol") == rol and s.get("user_id") == user_id and t != except_token]
    for t in tokens:
        del ACTIVE_SESSIONS[t]
    return len(tokens)

def generate_device_token() -> str:
    """Genera una clave de API única para cada Raspberry Pi Zero W."""
    return f"neo_pi_{secrets.token_hex(16)}"
