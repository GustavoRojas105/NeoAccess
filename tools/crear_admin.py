"""
NeoAccess - Crear (o reactivar) una cuenta de administrador.

En el servidor la base empieza vacía (sin las cuentas de prueba de seed_data.py),
así que la primera cuenta de administrador se crea con esta herramienta.
La contraseña se escribe oculta en la terminal (no queda en el historial ni en archivos).

Uso:
    python tools/crear_admin.py
    (en el servidor:  sudo docker exec -it neoaccess python tools/crear_admin.py)
"""
import getpass
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from backend.auth import hash_password  # noqa: E402
from database.database import get_connection, init_db  # noqa: E402

MIN_LARGO = 10


def main() -> int:
    init_db()
    usuario = input("Usuario del administrador (para iniciar sesión): ").strip()
    if len(usuario) < 3:
        print("El usuario debe tener al menos 3 caracteres.")
        return 1
    nombre = input("Nombre completo: ").strip().upper() or usuario.upper()
    correo = input("Correo (opcional, sirve para entrar y recuperar la contraseña): ").strip().lower() or None
    while True:
        clave = getpass.getpass(f"Contraseña (mínimo {MIN_LARGO} caracteres, no se ve al escribir): ")
        if len(clave) < MIN_LARGO:
            print("Muy corta.")
            continue
        if getpass.getpass("Repite la contraseña: ") != clave:
            print("No coinciden, otra vez.")
            continue
        break
    conn = get_connection()
    try:
        existe = conn.execute("SELECT id FROM administradores WHERE username = ?", (usuario,)).fetchone()
        if existe:
            conn.execute("""UPDATE administradores SET password_hash = ?, nombre = ?, email = COALESCE(?, email),
                            activo = 1, debe_cambiar_password = 0 WHERE id = ?""",
                         (hash_password(clave), nombre, correo, existe["id"]))
            print(f"Administrador '{usuario}' actualizado y activo.")
        else:
            conn.execute("""INSERT INTO administradores (username, password_hash, nombre, email, activo)
                            VALUES (?, ?, ?, ?, 1)""", (usuario, hash_password(clave), nombre, correo))
            print(f"Administrador '{usuario}' creado. Ya puede iniciar sesión.")
        conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
