"""
NeoAccess - Asignar o cambiar la contraseña de portal de UN usuario (limpieza, docente o alumno).

Útil sobre todo para el personal de limpieza, que no tiene autorregistro por correo.
La contraseña se escribe oculta en la terminal (no queda en el historial ni en archivos).

Uso (desde la carpeta NeoAccess):
    python tools\\asignar_contrasena.py LIM-01
"""
import getpass
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from backend.auth import hash_password  # noqa: E402
from database.database import get_connection  # noqa: E402

MIN_LARGO = 8
TIPOS = {"alumno": "Alumno", "docente": "Docente", "personal_limpieza": "Personal de limpieza"}


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    clave = argv[1].strip()
    conn = get_connection()
    try:
        u = conn.execute(
            "SELECT id, nombre_completo, tipo, matricula_clave, estado, password_hash FROM usuarios "
            "WHERE upper(id) = upper(?) OR upper(matricula_clave) = upper(?)", (clave, clave)).fetchone()
        if not u:
            print(f"No existe ningún usuario con ID o clave '{clave}'.")
            return 1
        if u["tipo"] not in TIPOS:
            print(f"{u['nombre_completo']} es de tipo '{u['tipo']}': esta herramienta no aplica.")
            return 1
        print(f"{TIPOS[u['tipo']]}: {u['nombre_completo']}  (inicia sesión con: {u['matricula_clave']})")
        if u["estado"] != "activo":
            print("Aviso: el usuario está dado de baja; no podrá entrar hasta que lo reactive.")
        if u["password_hash"]:
            print("Ya tiene contraseña: se reemplazará por la nueva.")

        nueva = getpass.getpass(f"Nueva contraseña (mínimo {MIN_LARGO} caracteres): ")
        if len(nueva) < MIN_LARGO:
            print(f"Muy corta: use al menos {MIN_LARGO} caracteres. No se cambió nada.")
            return 1
        if getpass.getpass("Repítala: ") != nueva:
            print("No coinciden. No se cambió nada.")
            return 1
        conn.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (hash_password(nueva), u["id"]))
        conn.commit()
        print("Contraseña asignada. Ya puede entrar en el login con su clave y esa contraseña.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
