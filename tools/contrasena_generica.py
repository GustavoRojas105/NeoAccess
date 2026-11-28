"""
NeoAccess - Contraseña genérica para quienes todavía no tienen cuenta (por defecto, alumnos).

A cada alumno activo SIN contraseña se le pone la misma contraseña genérica y queda marcado
para que, al entrar por primera vez, el sistema le pida cambiarla antes de hacer cualquier cosa.
Los que ya tienen su propia contraseña no se tocan (salvo con --todos).
Antes de cambiar nada se guarda un respaldo en database/respaldos/.

Uso (desde la carpeta NeoAccess):
    python tools/contrasena_generica.py                  -> pide la contraseña (oculta)
    python tools/contrasena_generica.py --tipo docente
    python tools/contrasena_generica.py --todos          -> también a quienes ya tenían contraseña
    python tools/contrasena_generica.py --db otra.db
En el servidor:  sudo docker exec -it neoaccess python tools/contrasena_generica.py
"""
import argparse
import getpass
import os
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from backend.auth import hash_password  # noqa: E402

MIN_LARGO = 8
TIPOS = ("alumno", "docente", "personal_limpieza")


def respaldar(db_path: str) -> str:
    carpeta = os.path.join(os.path.dirname(os.path.abspath(db_path)), "respaldos")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"antes_contrasena_generica_{datetime.now():%Y%m%d_%H%M%S}.db")
    origen = sqlite3.connect(db_path)
    copia = sqlite3.connect(destino)
    origen.backup(copia)
    copia.close()
    origen.close()
    return destino


def aplicar(db_path: str, clave: str, tipo: str = "alumno", todos: bool = False) -> list:
    """Pone `clave` (con cambio obligatorio al entrar) y devuelve [(matrícula, nombre), ...]."""
    if len(clave) < MIN_LARGO:
        raise ValueError(f"La contraseña genérica debe tener al menos {MIN_LARGO} caracteres.")
    conn = sqlite3.connect(db_path)
    try:
        filtro = "" if todos else " AND password_hash IS NULL"
        filas = conn.execute(f"""SELECT id, matricula_clave, nombre_completo FROM usuarios
                                 WHERE tipo = ? AND estado = 'activo'{filtro} ORDER BY nombre_completo""",
                             (tipo,)).fetchall()
        for uid, _, _ in filas:
            # cada uno con su propia sal: el hash es distinto aunque la contraseña sea la misma
            conn.execute("UPDATE usuarios SET password_hash = ?, debe_cambiar_password = 1, cuenta_aprobada = 1 WHERE id = ?",
                         (hash_password(clave), uid))
        conn.commit()
        return [(m, n) for _, m, n in filas]
    finally:
        conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Contraseña genérica con cambio obligatorio al entrar")
    ap.add_argument("--tipo", choices=TIPOS, default="alumno")
    ap.add_argument("--todos", action="store_true", help="también a quienes ya tenían contraseña")
    ap.add_argument("--db", default=os.environ.get("NEOACCESS_DB_PATH") or os.path.join(RAIZ, "database", "neoaccess.db"))
    args = ap.parse_args(argv)

    clave = getpass.getpass(f"Contraseña genérica (mínimo {MIN_LARGO} caracteres, no se ve al escribir): ")
    if getpass.getpass("Repítela: ") != clave:
        print("No coinciden. No se cambió nada.")
        return 1
    try:
        print("Respaldo:", respaldar(args.db))
        cambiados = aplicar(args.db, clave, args.tipo, args.todos)
    except ValueError as e:
        print(e)
        return 1
    for mat, nombre in cambiados:
        print(f"  {mat:<12} {nombre}")
    print(f"{len(cambiados)} cuenta(s) con la contraseña genérica. Al entrar se les pedirá cambiarla.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
