"""
NeoAccess - Borra TODO lo que generó el simulador de puerta.

Lo simulado siempre queda ligado a puertas cuyo ID empieza con "SIM-" (p. ej. SIM-LMU).
Al borrar esas puertas se borran también sus accesos, bitácora de limpieza, eventos y
órdenes remotas. Lo real (otras puertas, usuarios, horarios) no se toca.
Antes de borrar se guarda un respaldo en database/respaldos/.

Uso (desde la carpeta NeoAccess):
    python tools\\borrar_simulacion.py          -> muestra qué se borraría
    python tools\\borrar_simulacion.py --si     -> lo borra (con respaldo previo)
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(RAIZ, "database", "neoaccess.db")
DATOS_SIM = os.path.join(RAIZ, "tools", "simulador_datos")
TABLAS = [("registros_acceso", "accesos"), ("registros_limpieza", "registros de limpieza"),
          ("eventos_dispositivo", "eventos de dispositivo"), ("comandos_dispositivo", "órdenes remotas")]


def resumen(con, ids):
    marcas = ",".join("?" * len(ids))
    return {nombre: con.execute(f"SELECT COUNT(*) FROM {tabla} WHERE dispositivo_id IN ({marcas})", ids).fetchone()[0]
            for tabla, nombre in TABLAS}


def main(argv):
    db = DB
    if "--db" in argv:
        db = argv[argv.index("--db") + 1]
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    ids = [r[0] for r in con.execute("SELECT id FROM dispositivos WHERE id LIKE 'SIM-%' ORDER BY id")]
    if not ids:
        print("No hay nada simulado en la base de datos.")
        return 0
    print("Puertas simuladas:", ", ".join(ids))
    for nombre, n in resumen(con, ids).items():
        print(f"  {n:>5}  {nombre}")
    if "--si" not in argv:
        print("\nNo se borró nada. Para borrarlo: python tools\\borrar_simulacion.py --si")
        return 0

    con.close()
    carpeta = os.path.join(os.path.dirname(db), "respaldos")
    os.makedirs(carpeta, exist_ok=True)
    respaldo = os.path.join(carpeta, f"antes_borrar_simulacion_{datetime.now():%Y%m%d_%H%M%S}.db")
    origen = sqlite3.connect(db)
    destino = sqlite3.connect(respaldo)
    origen.backup(destino)
    destino.close()
    origen.close()
    print(f"\nRespaldo: {respaldo}")

    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys = ON")
    with con:
        marcas = ",".join("?" * len(ids))
        for tabla, _ in TABLAS:  # explícito, por si una tabla no tiene ON DELETE CASCADE
            con.execute(f"DELETE FROM {tabla} WHERE dispositivo_id IN ({marcas})", ids)
        con.execute(f"DELETE FROM dispositivos WHERE id IN ({marcas})", ids)
    quedan = con.execute("SELECT COUNT(*) FROM dispositivos WHERE id LIKE 'SIM-%'").fetchone()[0]
    con.close()
    if os.path.isdir(DATOS_SIM) and db == DB:
        shutil.rmtree(DATOS_SIM, ignore_errors=True)
    print("Listo: se borró todo lo simulado." if quedan == 0 else "Algo quedó sin borrar; revisa la base.")
    return 0 if quedan == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
