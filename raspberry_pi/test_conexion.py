"""
NeoAccess - Herramienta de Diagnóstico y Prueba de Conexión Real
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\raspberry_pi\\test_conexion.py
Ejecutar en la Raspberry Pi Zero W: python3 test_conexion.py
"""

import os
import sys
import json
import time
import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def run_diagnostics():
    print_header("NeoAccess IoT • Diagnóstico de Conexión Real Raspberry Pi")

    # 1. Leer Configuración
    if not os.path.exists(CONFIG_PATH):
        print("[ERROR] No se encontró el archivo 'config.json'.")
        print("Copia 'config.json.template' a 'config.json' y coloca la IP de tu computadora.")
        return

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    server_url = cfg.get("servidor_url", "http://127.0.0.1:8000").rstrip("/")
    dev_id = cfg.get("dispositivo_id", "DEV-PI-STEM01")
    token = cfg.get("token_api", "")

    print(f"• Dispositivo ID: {dev_id}")
    print(f"• Servidor URL:  {server_url}")
    print(f"• Token API:     {token[:10]}...")

    # 2. Prueba de Alcance de Red (Ping HTTP)
    print_header("Paso 1: Verificando Conexión de Red Local Wi-Fi")
    try:
        t0 = time.time()
        res = requests.get(f"{server_url}/", timeout=4)
        latency = round((time.time() - t0) * 1000, 1)
        if res.status_code == 200:
            print(f"[✓ ÉXITO] Servidor central alcanzado en {latency} ms (Código HTTP 200).")
        else:
            print(f"[!] Servidor respondió con código: {res.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[✗ FALLO] No se pudo conectar a '{server_url}'.")
        print("Revisa:")
        print(" 1. Que tu computadora y la Raspberry Pi estén en la misma red Wi-Fi.")
        print(" 2. Que el servidor central esté corriendo en tu computadora ('run_server.bat').")
        print(" 3. Que el Firewall de Windows no esté bloqueando el puerto 8000.")
        return
    except Exception as e:
        print(f"[✗ ERROR] Error inesperado de red: {e}")
        return

    # 3. Prueba de Autenticación de Token y Señal de Vida (Heartbeat)
    print_header("Paso 2: Verificando Token de Seguridad y Estado 'En línea'")
    try:
        payload = {
            "dispositivo_id": dev_id,
            "token_api": token
        }
        res = requests.post(f"{server_url}/api/iot/heartbeat", json=payload, timeout=4)
        if res.status_code == 200:
            data = res.json()
            print(f"[✓ ÉXITO] ¡Token aceptado! El servidor registró la señal a las: {data.get('ack_time')}")
            print(">>> Revisa tu Dashboard: ¡La puerta ahora debe mostrarse en color VERDE ('En línea')!")
        elif res.status_code == 403:
            print("[✗ ERROR DE SEGURIDAD] Token no reconocido o el dispositivo fue desactivado.")
            print("Verifica en el Dashboard web que el Token API coincida con el generado.")
            return
        else:
            print(f"[!] Respuesta inesperada: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[✗ ERROR] {e}")
        return

    # 4. Prueba de Sincronización Fuera de Línea (RF-08)
    print_header("Paso 3: Descarga de Lista de Acceso Fuera de Línea (RF-08)")
    try:
        params = {"dispositivo_id": dev_id}
        res = requests.get(f"{server_url}/api/iot/sync-offline-rules", params=params,
                           headers={"X-Device-Token": token}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            num_users = len(data.get("usuarios", []))
            num_horarios = len(data.get("horarios", []))
            print(f"[✓ ÉXITO] Reglas descargadas correctamente:")
            print(f" • Usuarios con vector facial en memoria: {num_users}")
            print(f" • Clases y horarios programados en este salón: {num_horarios}")
        else:
            print(f"[!] No se pudieron obtener reglas: {res.status_code}")
    except Exception as e:
        print(f"[✗ ERROR] {e}")

    # 5. Prueba de Hardware Físico (GPIO Relé de Cerradura)
    print_header("Paso 4: Prueba Física de Pines GPIO y Relevador de Puerta")
    try:
        import RPi.GPIO as GPIO
        pin_cerradura = cfg.get("pin_cerradura_gpio", 17)
        pin_led_verde = cfg.get("pin_led_verde_gpio", 27)
        pin_led_rojo = cfg.get("pin_led_rojo_gpio", 22)
        pin_buzzer = cfg.get("pin_buzzer_gpio", 23)

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin_cerradura, GPIO.OUT)
        GPIO.setup(pin_led_verde, GPIO.OUT)
        GPIO.setup(pin_led_rojo, GPIO.OUT)
        # Buzzer callado durante la prueba (algunos módulos suenan con LOW)
        GPIO.setup(pin_buzzer, GPIO.OUT,
                   initial=GPIO.HIGH if cfg.get("buzzer_activo_en_bajo", True) else GPIO.LOW)

        print(f"Activando relevador en GPIO {pin_cerradura} durante 3 segundos...")
        print("(Deberías escuchar el 'clic' del relevador y ver encender el LED verde)")
        GPIO.output(pin_cerradura, GPIO.HIGH)
        GPIO.output(pin_led_verde, GPIO.HIGH)
        time.sleep(3)
        GPIO.output(pin_cerradura, GPIO.LOW)
        GPIO.output(pin_led_verde, GPIO.LOW)

        GPIO.cleanup()
        print("[✓ ÉXITO] Prueba de hardware físico completada.")
    except ImportError:
        print("[INFO] Librería 'RPi.GPIO' no encontrada (estás ejecutando en una PC/laptop de prueba).")
        print("Cuando ejecutes este script en la Raspberry Pi física con Raspberry Pi OS, accionará el relé.")

    print_header("Diagnóstico Completado con Éxito")
    print("Todo está listo para ejecutar el cliente en tu Raspberry Pi Zero W:")
    print("   python3 rpi_main.py\n")

if __name__ == "__main__":
    run_diagnostics()
