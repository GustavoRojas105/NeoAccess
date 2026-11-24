"""
Actualiza las contraseñas de los usuarios en neoaccess.db para permitir inicio de sesión por rol.
"""

import sqlite3
import os
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "neoaccess.db")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.auth import hash_password as hash_pw

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("PRAGMA table_info(usuarios);")
cols = [col[1] for col in c.fetchall()]
if "password_hash" not in cols:
    c.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT;")

pw_docente = hash_pw("docente123")
pw_alumno = hash_pw("alumno123")
pw_limpieza = hash_pw("limpieza123")

c.execute("UPDATE usuarios SET password_hash = ? WHERE tipo = 'docente';", (pw_docente,))
c.execute("UPDATE usuarios SET password_hash = ? WHERE tipo = 'alumno';", (pw_alumno,))
c.execute("UPDATE usuarios SET password_hash = ? WHERE tipo = 'personal_limpieza';", (pw_limpieza,))

conn.commit()

c.execute("SELECT id, nombre_completo, tipo, matricula_clave FROM usuarios LIMIT 5;")
for r in c.fetchall():
    print(f"Usuario: {r[0]} | Nombre: {r[1]} | Tipo: {r[2]} | Clave: {r[3]}")

conn.close()
print("¡Contraseñas asignadas exitosamente!")
