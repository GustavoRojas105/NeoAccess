"""
Entorno común de pruebas de NeoAccess.

- Crea una base de datos NUEVA en una carpeta temporal (nunca toca database/neoaccess.db).
- Crea un administrador de prueba y datos base (laboratorios, grupos, docentes, alumno, jefe).
- Expone un TestClient de FastAPI para llamar a la API sin levantar el servidor.
"""
import os
import sys
import tempfile
import hashlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import database.database as dbm  # noqa: E402

BD_REAL = os.path.join(RAIZ, "database", "neoaccess.db")
# Lo que una puerta real conectada cambia sola mientras corren las pruebas (latido cada
# minuto): no cuenta como "las pruebas tocaron la BD real".
_CAMBIOS_EN_VIVO = {"dispositivos": ("ultima_senal", "ip_address", "estado"),
                    "eventos_dispositivo": None}


def _huella(ruta):
    """Huella del contenido de la BD real, sin lo que cambian las puertas en vivo."""
    import sqlite3
    h = hashlib.sha256()
    c = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        tablas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tablas:
            if t in _CAMBIOS_EN_VIVO and _CAMBIOS_EN_VIVO[t] is None:
                continue
            cols = [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')
                    if r[1] not in (_CAMBIOS_EN_VIVO.get(t) or ())]
            lista = ", ".join(f'"{x}"' for x in cols)
            h.update(t.encode())
            for fila in c.execute(f'SELECT {lista} FROM "{t}" ORDER BY rowid'):
                h.update(repr(fila).encode())
    finally:
        c.close()
    return h.hexdigest()


HUELLA_BD_REAL = _huella(BD_REAL) if os.path.exists(BD_REAL) else None

# Sin SMTP en pruebas: config_servidor.env no sobreescribe variables ya definidas
for _k in ("NEOACCESS_SMTP_HOST", "NEOACCESS_SMTP_USER", "NEOACCESS_SMTP_PASSWORD"):
    os.environ[_k] = ""

_CARPETA = tempfile.mkdtemp(prefix="neoaccess_pruebas_")
dbm.DB_PATH = os.path.join(_CARPETA, "pruebas.db")
dbm.init_db()

from backend.auth import hash_password  # noqa: E402
import backend.auth as auth  # noqa: E402

# Contraseñas solo de esta BD temporal de pruebas
CLAVE_ADMIN = "AdminPrueba123"
CLAVE_PRUEBA = "Prueba12345"

_c = dbm.get_connection()
_c.execute("INSERT INTO administradores (username, password_hash, nombre, email, activo) VALUES (?, ?, ?, ?, 1)",
           ("admin.pruebas", hash_password(CLAVE_ADMIN), "Administrador de Pruebas", None))
_c.commit()
_c.close()

import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402
import backend.app as appmod  # noqa: E402

cliente = TestClient(appmod.app)

ISC = "Ingeniería en Sistemas Computacionales"
CIV = "Ingeniería Civil"


def limpiar_intentos():
    """Evita que el bloqueo anti fuerza bruta afecte a otras pruebas."""
    auth._FAILED_ATTEMPTS.clear()
    auth._LOCKED_UNTIL.clear()


def entrar(usuario, clave):
    limpiar_intentos()
    r = cliente.post("/api/auth/login", json={"username": usuario, "password": clave})
    assert r.status_code == 200, (usuario, r.status_code, r.text)
    return {"Authorization": "Bearer " + r.json()["token"]}


def admin():
    return entrar("admin.pruebas", CLAVE_ADMIN)


def bd():
    return dbm.get_connection()


def poner_clave(user_id, clave=CLAVE_PRUEBA):
    c = bd()
    c.execute("UPDATE usuarios SET password_hash = ?, cuenta_aprobada = 1 WHERE id = ?", (hash_password(clave), user_id))
    c.commit()
    c.close()


_SEMBRADO = {}


def sembrar():
    """Datos base (idempotente): 2 labs, 2 grupos, 2 docentes, 1 alumno, 1 jefe de Sistemas y 1 Raspberry."""
    if _SEMBRADO:
        return _SEMBRADO
    H = admin()
    p = cliente.post
    p("/api/labs", headers=H, json={"id": "LAB-RED", "nombre": "Lab de Redes", "edificio": "Edificio 6", "carrera": ISC, "capacidad": 30, "descripcion": ""})
    p("/api/labs", headers=H, json={"id": "LAB-CIV", "nombre": "Lab Civil", "edificio": "Edificio 2", "carrera": CIV, "capacidad": 30, "descripcion": ""})
    p("/api/groups", headers=H, json={"id": "ISC-501", "nombre": "501 Sistemas", "carrera": ISC, "semestre": 5})
    p("/api/groups", headers=H, json={"id": "CIV-301", "nombre": "301 Civil", "carrera": CIV, "semestre": 3})
    base = {"grupo_id": None, "estado": "activo"}
    p("/api/users", headers=H, json={**base, "id": "DOC-ISC", "nombre_completo": "Laura Pérez", "matricula_clave": "100", "tipo": "docente", "carrera": ISC})
    p("/api/users", headers=H, json={**base, "id": "DOC-CIV", "nombre_completo": "Ana Ruiz", "matricula_clave": "200", "tipo": "docente", "carrera": CIV})
    p("/api/users", headers=H, json={"id": "AL-1", "nombre_completo": "Carlos Mendoza", "matricula_clave": "22030001", "tipo": "alumno", "carrera": ISC, "grupo_id": "ISC-501", "estado": "activo"})
    p("/api/jefes", headers=H, json={"username": "jefe.isc", "nombre": "Jefa de Sistemas", "password": CLAVE_PRUEBA, "carreras": [ISC]})
    dev = p("/api/devices", headers=H, json={"id": "RPI-RED", "laboratorio_id": "LAB-RED", "nombre": "Puerta Redes"}).json()
    poner_clave("AL-1")
    poner_clave("DOC-ISC")
    _SEMBRADO.update({"token_rpi": dev["token_api"]})
    return _SEMBRADO


def periodo_activo_id():
    c = bd()
    pid = c.execute("SELECT id FROM periodos WHERE estado = 'activo'").fetchone()[0]
    c.close()
    return pid


def bd_real_intacta():
    if HUELLA_BD_REAL is None:
        return True
    return _huella(BD_REAL) == HUELLA_BD_REAL
