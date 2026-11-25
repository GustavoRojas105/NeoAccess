"""
Ejecuta todas las pruebas de NeoAccess (caja blanca, negra y gris).

    python tests\\ejecutar_pruebas.py              -> corre todo
    python tests\\ejecutar_pruebas.py --cobertura  -> además mide la cobertura (requiere: pip install coverage)

Cada tipo de prueba corre en su propio proceso con una base de datos temporal nueva;
la base real database/neoaccess.db nunca se modifica.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SUITES = [("Caja blanca", "test_caja_blanca"), ("Caja negra", "test_caja_negra"), ("Caja gris", "test_caja_gris")]


def main():
    cobertura = "--cobertura" in sys.argv
    if cobertura:
        try:
            import coverage  # noqa: F401
        except ImportError:
            print("Instale coverage primero:  pip install coverage")
            return 2
        subprocess.run([sys.executable, "-m", "coverage", "erase"], cwd=AQUI)

    resultados = []
    for nombre, modulo in SUITES:
        print(f"\n{'=' * 70}\n {nombre}\n{'=' * 70}", flush=True)
        if cobertura:
            cmd = [sys.executable, "-m", "coverage", "run", "-p", f"--source={RAIZ}/backend,{RAIZ}/database",
                   "-m", "unittest", "-v", modulo]
        else:
            cmd = [sys.executable, "-m", "unittest", "-v", modulo]
        r = subprocess.run(cmd, cwd=AQUI)
        resultados.append((nombre, r.returncode == 0))

    if cobertura:
        subprocess.run([sys.executable, "-m", "coverage", "combine"], cwd=AQUI, capture_output=True)
        print(f"\n{'=' * 70}\n Cobertura de código\n{'=' * 70}")
        subprocess.run([sys.executable, "-m", "coverage", "report", "--omit=*seed_data*,*update_passwords*,*mailer*"], cwd=AQUI)

    print(f"\n{'=' * 70}\n Resumen\n{'=' * 70}")
    for nombre, ok in resultados:
        print(f"  {'OK   ' if ok else 'FALLA'}  {nombre}")
    return 0 if all(ok for _, ok in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
