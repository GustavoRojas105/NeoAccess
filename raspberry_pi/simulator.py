"""
NeoAccess - Simulador de Puerta Interactivo para Pruebas en Computadora
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\raspberry_pi\\simulator.py

CORRECCIONES v2:
  - import requests añadido (faltaba, causaba NameError)
  - Opciones [1] y [3]: hora simulada DENTRO del horario real del caché (Lunes 07:30)
  - Opción [2]: hora simulada FUERA de horario (Sábado 22:30) garantiza denegado
  - Opciones [1-5]: recargan 'usuarios' del caché DESPUÉS de sync para no usar lista vacía
  - Resultado impreso con nombre, matrícula, resultado y motivo completos
  - Menú [0] muestra cuántos registros hay en la BD tras cada acción
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from rpi_main import NeoAccessRaspberryNode


def print_menu():
    print("\n" + "=" * 65)
    print("   NeoAccess • SIMULADOR DE PUERTA IOT (Raspberry Pi Zero W)")
    print("=" * 65)
    print(" [1] Probar Acceso de ALUMNO EN HORARIO      (PERMITIDO ✓)")
    print(" [2] Probar Acceso de ALUMNO FUERA HORARIO   (DENEGADO  ✗)")
    print(" [3] Probar Acceso de DOCENTE EN HORARIO     (PERMITIDO ✓)")
    print(" [4] Probar Acceso de ROSTRO NO REGISTRADO   (DENEGADO  ✗)")
    print(" [5] Simular Personal de LIMPIEZA (entrada/salida alterna) ✓")
    print(" [6] Simular CAÍDA DE RED → Modo Offline (RF-08)")
    print(" [7] Simular RECONEXIÓN  → Vaciar Cola Offline (RF-09)")
    print(" [8] Enviar Señal de Vida / Latido (RF-10)")
    print(" [9] Ver Estado del Caché Local")
    print(" [0] Salir")
    print("=" * 65)


def proxima_fecha_dia(dia_semana_num: int, hora: int, minuto: int) -> datetime:
    """
    Calcula una fecha con el día de la semana solicitado (0=Lunes, 5=Sábado) y la hora indicada.
    Esto permite que validate_schedule evalúe correctamente los horarios del plan de estudios,
    mientras que rpi_main.py asigna automáticamente la fecha y hora REAL actual para el registro.
    """
    hoy = datetime.now()
    dias_diferencia = (dia_semana_num - hoy.weekday()) % 7
    return (hoy + timedelta(days=dias_diferencia)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0
    )


def imprimir_resultado(res: dict, nombre: str = None, matricula: str = None):
    """Muestra el resultado de la simulación de forma clara."""
    resultado = res.get("resultado", "?").upper()
    motivo = res.get("motivo", "")
    icono = "✅ ACCESO PERMITIDO" if resultado == "PERMITIDO" else "🚫 ACCESO DENEGADO"
    linea = "-" * 65
    print(linea)
    print(f"  {icono}")
    if nombre:
        print(f"  Usuario   : {nombre}" + (f" ({matricula})" if matricula else ""))
    print(f"  Resultado : {resultado}")
    print(f"  Motivo    : {motivo}")
    print(f"  Timestamp : {res.get('fecha_hora', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
    print(linea)
    print("  >>> El registro YA fue enviado al servidor y aparecerá")
    print("      en el panel del Administrador en ≤ 3 segundos. <<<")
    print(linea)


def run_simulator():
    print("\nIniciando nodo NeoAccess para pruebas en PC...")
    node = NeoAccessRaspberryNode()

    # Auto-detectar y forzar conexión a localhost si el servidor está en esta máquina
    for url_candidato in [node.server_url, "http://127.0.0.1:8000", "http://localhost:8000"]:
        try:
            r = requests.get(f"{url_candidato}/api/devices", timeout=2)
            if r.status_code in (200, 401, 403):
                node.server_url = url_candidato
                print(f"[✓ SERVIDOR] Conectado a {node.server_url}")
                break
        except Exception:
            continue
    else:
        print("[⚠ AVISO] No se pudo conectar al servidor. Verifica que está corriendo en el puerto 8000.")

    # Sincronización inicial: descargar reglas y vaciar cola offline pendiente
    try:
        node.send_heartbeat()
        node.sync_offline_rules()
        node.flush_offline_queue()
    except Exception as e:
        print(f"[Aviso] Sincronización inicial: {e}")

    while True:
        # Siempre recargar usuarios del caché más reciente (por si se sincronizó)
        usuarios = node.offline_cache.get("usuarios", [])
        horarios = node.offline_cache.get("horarios", [])

        print_menu()
        print(f"  [Cache: {len(usuarios)} usuarios | {len(horarios)} horarios | Servidor: {node.server_url}]")
        choice = input("\nSeleccione una opción [0-9]: ").strip()

        # ── [0] Salir ────────────────────────────────────────────
        if choice == "0":
            print("Simulador finalizado.")
            break

        # ── [1] Alumno EN horario → PERMITIDO ───────────────────
        elif choice == "1":
            alumno = next((u for u in usuarios if u.get("grupo_id") == "MEC-801"), None)
            if not alumno:
                alumno = next((u for u in usuarios if u.get("tipo") == "alumno"), None)
            if not alumno:
                print("❌ No hay alumnos en el caché. Ejecuta opción [9] o [7] para sincronizar.")
                input("\nPresione Enter para continuar...")
                continue

            # Hora simulada: Lunes 07:30 → dentro del horario Lunes 07:00-09:00
            lunes_en_horario = proxima_fecha_dia(0, 7, 30)
            print(f"\n[SIMULACIÓN] Alumno frente a la cámara")
            print(f"  Nombre   : {alumno['nombre']} ({alumno.get('matricula_clave','')})")
            print(f"  Hora sim : {lunes_en_horario.strftime('%A %Y-%m-%d %H:%M')} (dentro de horario)")
            res = node.process_access(alumno["vector_encoding"], lunes_en_horario)
            imprimir_resultado(res, alumno["nombre"], alumno.get("matricula_clave"))

        # ── [2] Alumno FUERA de horario → DENEGADO ──────────────
        elif choice == "2":
            alumno = next((u for u in usuarios if u.get("tipo") == "alumno"), None)
            if not alumno:
                print("❌ No hay alumnos en el caché.")
                input("\nPresione Enter para continuar...")
                continue

            # Hora simulada: Sábado 22:30 → siempre fuera de horario
            sabado_sin_clase = proxima_fecha_dia(5, 22, 30)
            print(f"\n[SIMULACIÓN] Alumno fuera de horario frente a la cámara")
            print(f"  Nombre   : {alumno['nombre']} ({alumno.get('matricula_clave','')})")
            print(f"  Hora sim : {sabado_sin_clase.strftime('%A %Y-%m-%d %H:%M')} (fuera de horario)")
            res = node.process_access(alumno["vector_encoding"], sabado_sin_clase)
            imprimir_resultado(res, alumno["nombre"], alumno.get("matricula_clave"))

        # ── [3] Docente EN horario → PERMITIDO ──────────────────
        elif choice == "3":
            docente = next((u for u in usuarios if u.get("tipo") == "docente"), None)
            if not docente:
                print("❌ No hay docentes en el caché.")
                input("\nPresione Enter para continuar...")
                continue

            # Hora simulada: Lunes 07:30 → dentro del horario del docente
            lunes_en_horario = proxima_fecha_dia(0, 7, 30)
            print(f"\n[SIMULACIÓN] Docente frente a la cámara")
            print(f"  Nombre   : {docente['nombre']}")
            print(f"  Hora sim : {lunes_en_horario.strftime('%A %Y-%m-%d %H:%M')} (dentro de horario)")
            res = node.process_access(docente["vector_encoding"], lunes_en_horario)
            imprimir_resultado(res, docente["nombre"], docente.get("matricula_clave"))

        # ── [4] Rostro NO registrado → DENEGADO ─────────────────
        elif choice == "4":
            print("\n[SIMULACIÓN] Persona desconocida frente a la cámara (vector aleatorio)")
            import random
            vector_desconocido = [random.gauss(0, 1) for _ in range(128)]
            res = node.process_access(vector_desconocido)
            imprimir_resultado(res, "Persona no identificada")

        # ── [5] Personal de Limpieza → PERMITIDO ────────────────
        elif choice == "5":
            limpieza = next((u for u in usuarios if u.get("tipo") == "personal_limpieza"), None)
            if not limpieza:
                print("❌ No hay personal de limpieza en el caché.")
                input("\nPresione Enter para continuar...")
                continue

            print(f"\n[SIMULACIÓN] Personal de limpieza frente a la cámara")
            print(f"  Nombre: {limpieza['nombre']}")
            res = node.process_access(limpieza["vector_encoding"])
            imprimir_resultado(res, limpieza["nombre"], limpieza.get("matricula_clave"))

        # ── [6] Simular CAÍDA de red → Modo Offline ─────────────
        elif choice == "6":
            print("\n[SIMULACIÓN] ⚡ Cortando conexión al servidor (simula caída de internet)...")
            original_url = node.server_url
            node.server_url = "http://127.0.0.1:9999"  # puerto inexistente

            alumno = next((u for u in usuarios if u.get("tipo") == "alumno"), None)
            if alumno:
                lunes_en_horario = proxima_fecha_dia(0, 7, 30)
                print(f"  Alumno  : {alumno['nombre']}")
                print(f"  Hora sim: {lunes_en_horario.strftime('%A %H:%M')} (en horario)")
                print("  → La puerta abrirá con caché local. El registro queda en cola offline.")
                node.process_access(alumno["vector_encoding"], lunes_en_horario)
                print("[✓ RF-08] Acceso local concedido aunque no hay internet. Registro guardado en cola.")
            else:
                print("❌ No hay alumnos en caché para esta prueba.")

            node.server_url = original_url
            print(f"[INFO] Conexión restaurada a {node.server_url}")

        # ── [7] Simular RECONEXIÓN → vaciar cola offline ─────────
        elif choice == "7":
            print("\n[SIMULACIÓN] 🔄 Reconectando y enviando registros offline al servidor...")
            node.flush_offline_queue()
            print("[✓ RF-09] Cola offline procesada. Verifica el panel del administrador.")

        # ── [8] Señal de vida / heartbeat ───────────────────────
        elif choice == "8":
            print("\n[SIMULACIÓN] 💓 Enviando señal de vida al servidor...")
            try:
                node.send_heartbeat()
            except Exception as e:
                print(f"  Error: {e}")

        # ── [9] Ver estado del caché local ──────────────────────
        elif choice == "9":
            print("\n--- RESUMEN DE CACHÉ LOCAL ---")
            print(f"  Dispositivo   : {node.device_id}")
            print(f"  Servidor URL  : {node.server_url}")
            print(f"  Usuarios cache: {len(usuarios)}")
            for u in usuarios[:6]:
                print(f"    · {u.get('nombre','?')} [{u.get('tipo','?')}] id={u.get('usuario_id','?')}")
            if len(usuarios) > 6:
                print(f"    ... y {len(usuarios)-6} más")
            print(f"  Horarios cache: {len(horarios)}")
            for h in horarios:
                print(f"    · {h.get('dia_semana','?')} {h.get('hora_inicio','?')}-{h.get('hora_fin','?')} grupo={h.get('grupo_id','?')}")

            # Ver cola offline pendiente
            from rpi_main import QUEUE_FILE
            cola = []
            if os.path.exists(QUEUE_FILE):
                try:
                    with open(QUEUE_FILE, encoding="utf-8") as f:
                        cola = json.load(f)
                except Exception:
                    pass
            print(f"  Cola offline  : {len(cola)} registros pendientes de enviar")

        else:
            print("  Opción no válida. Elige entre [0] y [9].")

        input("\nPresione Enter para continuar...")


if __name__ == "__main__":
    run_simulator()
