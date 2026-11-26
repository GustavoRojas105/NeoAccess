"""
NeoAccess - Software de Control de Acceso para Raspberry Pi Zero W
Ubicación: raspberry_pi/rpi_main.py
Hardware: Raspberry Pi Zero W + Cámara Pi / USB + Cerradura Electromagnética (Relé GPIO 17)
Cumple con Requerimientos Funcionales RF-01 al RF-10 y RF-21 del documento NeoAccess ITSOEH.

Hilos en ejecución:
  1. Reconocimiento facial continuo (cámara -> YuNet -> SFace -> validación de horario)
  2. Latido + sincronización de reglas + vaciado de colas offline (cada intervalo_latido_seg)
  3. Consulta de comandos remotos del Dashboard, p. ej. apertura manual (cada intervalo_comandos_seg)
"""

import os
import sys
import json
import time
import threading
from datetime import datetime, timedelta
import requests

# Si la Raspberry tiene un idioma sin UTF-8 (p. ej. LANG=es_MX), print() con acentos o
# símbolos como • tumbaría el programa: forzar UTF-8 en la salida.
for _salida in (sys.stdout, sys.stderr):
    try:
        _salida.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from face_engine import (
    FaceEngine, FaceEngineUnavailable, VectorIndex,
    DEFAULT_COSINE_THRESHOLD, OPENCV_AVAILABLE
)

# 1. Detección de Hardware GPIO (Raspberry Pi)
try:
    import RPi.GPIO as GPIO
    HARDWARE_GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    HARDWARE_GPIO_AVAILABLE = False

# 2. Cámara: Picamera2 (cámara CSI en Raspberry Pi OS Bullseye/Bookworm) u OpenCV (USB)
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except Exception:
    PICAMERA2_AVAILABLE = False

if OPENCV_AVAILABLE:
    import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CACHE_FILE = os.path.join(BASE_DIR, "cache_offline.json")
QUEUE_FILE = os.path.join(BASE_DIR, "cola_offline.json")
CLEANING_QUEUE_FILE = os.path.join(BASE_DIR, "cola_limpieza.json")
CLEANING_STATE_FILE = os.path.join(BASE_DIR, "limpieza_estado.json")

# Otras ubicaciones donde se puede dejar el config.json descargado del panel.
# La partición "boot" de la tarjeta SD se ve desde Windows: basta con copiar ahí el archivo.
CONFIG_EXTRA = [
    "/boot/firmware/neoaccess_config.json", "/boot/neoaccess_config.json",
    "/boot/firmware/config.json.neoaccess", "/boot/config.json.neoaccess",
]
RETRY_OFFLINE_SEG = 15  # mientras no haya servidor, reintentar seguido


def _importar_config_externo():
    """Si hay un config en la partición boot (o uno distinto al local), copiarlo a config.json."""
    for ruta in CONFIG_EXTRA:
        try:
            if not os.path.isfile(ruta):
                continue
            nuevo = _read_json(ruta, None)
            if not isinstance(nuevo, dict) or not nuevo.get("token_api"):
                continue
            if _read_json(CONFIG_PATH, None) != nuevo:
                _write_json_atomic(CONFIG_PATH, nuevo)
                print(f"[CONFIG] Configuración importada desde {ruta}.")
            return
        except Exception as e:
            print(f"[CONFIG] No se pudo leer {ruta}: {e}")


def esperar_config(path: str = CONFIG_PATH) -> None:
    """Bloquea hasta que exista un config.json con token (copiado a mano o en la partición boot)."""
    avisado = False
    while True:
        _importar_config_externo()
        cfg = _read_json(path, None)
        if isinstance(cfg, dict) and cfg.get("token_api") and cfg.get("servidor_url"):
            return
        if not avisado:
            print("[CONFIG] Falta config.json. Descárgalo del panel (Dispositivos > Vincular) y")
            print(f"         cópialo a {path} o a la partición boot como neoaccess_config.json.")
            print("         Revisando cada 10 segundos...")
            avisado = True
        time.sleep(10)


def _read_json(path: str, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _write_json_atomic(path: str, data):
    """Escritura atómica: evita archivos corruptos si se va la luz a mitad de escritura."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class Camera:
    """Abstracción mínima de cámara: Picamera2 si existe, si no OpenCV VideoCapture."""

    def __init__(self, index: int = 0, width: int = 320, height: int = 240):
        self.picam = None
        self.cap = None
        if PICAMERA2_AVAILABLE:
            self.picam = Picamera2()
            cfg = self.picam.create_preview_configuration(main={"size": (width, height), "format": "RGB888"})
            self.picam.configure(cfg)
            self.picam.start()
            time.sleep(1.0)  # estabilizar exposición
            print(f"[CÁMARA] Picamera2 activa ({width}x{height}).")
        elif OPENCV_AVAILABLE:
            self.cap = cv2.VideoCapture(index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if not self.cap.isOpened():
                raise RuntimeError(f"No se pudo abrir la cámara USB índice {index}.")
            print(f"[CÁMARA] OpenCV VideoCapture({index}) activa.")
        else:
            raise RuntimeError("No hay librería de cámara disponible (instale OpenCV o Picamera2).")

    def read(self):
        """Devuelve un frame BGR o None. El llamador debe descartarlo tras usarlo (RF-07)."""
        if self.picam is not None:
            # Picamera2 'RGB888' entrega los bytes en orden BGR, el que espera OpenCV
            return self.picam.capture_array()
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self):
        try:
            if self.picam is not None:
                self.picam.stop()
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass


class NeoAccessRaspberryNode:
    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self._config_mtime = self._mtime(config_path)
        self.online = False
        self.server_url = self.config.get("servidor_url", "http://127.0.0.1:8000").rstrip("/")
        self.device_id = self.config.get("dispositivo_id", "DEV-PI-STEM01")
        self.token_api = self.config.get("token_api", "")
        self.heartbeat_interval = self.config.get("intervalo_latido_seg", 300)
        self.command_interval = self.config.get("intervalo_comandos_seg", 3)
        self.pin_cerradura = self.config.get("pin_cerradura_gpio", 17)
        self.pin_led_verde = self.config.get("pin_led_verde_gpio", 27)
        self.pin_led_rojo = self.config.get("pin_led_rojo_gpio", 22)
        self.pin_buzzer = self.config.get("pin_buzzer_gpio", 23)
        # Algunos módulos de buzzer suenan con LOW y se callan con HIGH ("activo en bajo")
        self.buzzer_activo_bajo = bool(self.config.get("buzzer_activo_en_bajo", False))
        self.open_seconds = self.config.get("segundos_puerta_abierta", 5)
        # Similitud coseno mínima para aceptar una identidad (SFace: 0.363 recomendado)
        self.threshold = self.config.get("umbral_similitud_coseno", DEFAULT_COSINE_THRESHOLD)
        # Evita registrar 20 accesos mientras la misma persona sigue frente a la cámara
        self.repeat_cooldown = self.config.get("segundos_espera_mismo_usuario", 10)
        self.camera_index = self.config.get("camara_indice", 0)
        self.frame_size = tuple(self.config.get("resolucion_camara", [320, 240]))
        # Botón físico: "boton" = se toma la foto N segundos después de presionarlo;
        # "continuo" = la cámara busca rostros todo el tiempo (modo anterior).
        self.capture_mode = str(self.config.get("modo_captura", "boton")).lower()
        self.pin_boton = self.config.get("pin_boton_gpio", 24)
        self.countdown_seconds = self.config.get("segundos_cuenta_regresiva", 5)
        self.boton_presionado = threading.Event()

        self.running = True
        self.door_lock = threading.Lock()   # una sola acción de puerta a la vez
        self.cache_lock = threading.Lock()
        self.offline_cache = {}
        self.vector_index = VectorIndex([])
        self._set_cache(self.load_offline_cache())
        self.last_decision = {}  # usuario_id/"desconocido" -> timestamp

        self.setup_gpio()

    def load_config(self, path: str) -> dict:
        if not os.path.exists(path):
            template_path = os.path.join(BASE_DIR, "config.json.template")
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {
                "dispositivo_id": "DEV-PI-STEM01",
                "token_api": "",
                "servidor_url": "http://127.0.0.1:8000",
                "intervalo_latido_seg": 300
            }
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _mtime(path: str):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def reload_config_if_changed(self):
        """Si se reemplazó el config.json (p. ej. token regenerado), aplicarlo sin reiniciar."""
        _importar_config_externo()
        mtime = self._mtime(self.config_path)
        if mtime is None or mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        cfg = _read_json(self.config_path, None)
        if not isinstance(cfg, dict) or not cfg.get("token_api"):
            return
        self.config = cfg
        self.server_url = cfg.get("servidor_url", self.server_url).rstrip("/")
        self.device_id = cfg.get("dispositivo_id", self.device_id)
        self.token_api = cfg.get("token_api", self.token_api)
        self.heartbeat_interval = cfg.get("intervalo_latido_seg", self.heartbeat_interval)
        self.online = False
        print(f"[CONFIG] config.json actualizado: {self.device_id} -> {self.server_url}")

    def _buzzer(self, sonar: bool):
        """Enciende o apaga el buzzer respetando si el módulo es activo en bajo."""
        if HARDWARE_GPIO_AVAILABLE:
            GPIO.output(self.pin_buzzer, GPIO.LOW if sonar == self.buzzer_activo_bajo else GPIO.HIGH)

    def setup_gpio(self):
        """Configuración física de pines GPIO de la Raspberry Pi Zero W."""
        if HARDWARE_GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.pin_cerradura, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.pin_led_verde, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.pin_led_rojo, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.pin_buzzer, GPIO.OUT,
                       initial=GPIO.HIGH if self.buzzer_activo_bajo else GPIO.LOW)
            print(f"[GPIO OK] Relevador de cerradura configurado en GPIO {self.pin_cerradura}.")
            if self.capture_mode == "boton":
                # Botón entre el GPIO y GND: resistencia pull-up interna, se lee LOW al presionar
                try:
                    GPIO.setup(self.pin_boton, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                except Exception as e:
                    print(f"[BOTÓN] No se pudo configurar GPIO {self.pin_boton}: {e}")
                    return
                try:
                    GPIO.add_event_detect(self.pin_boton, GPIO.FALLING,
                                          callback=lambda _canal: self.boton_presionado.set(),
                                          bouncetime=300)
                    print(f"[GPIO OK] Botón de verificación en GPIO {self.pin_boton}.")
                except Exception:
                    # Kernels nuevos (6.x) a veces no permiten la detección por interrupción:
                    # se lee el pin cada 20 ms, que funciona en cualquier versión.
                    threading.Thread(target=self._sondear_boton, daemon=True).start()
                    print(f"[GPIO OK] Botón de verificación en GPIO {self.pin_boton} (lectura continua).")
        else:
            print("[INFO] GPIO físico no disponible. Ejecutando en modo consola simulada.")

    # -------------------------------------------------------------
    # CACHÉ LOCAL DE REGLAS (RF-08)
    # -------------------------------------------------------------
    def load_offline_cache(self) -> dict:
        return _read_json(CACHE_FILE, {"usuarios": [], "horarios": [], "timestamp": None})

    def _set_cache(self, data: dict):
        with self.cache_lock:
            self.offline_cache = data
            self.vector_index = VectorIndex(data.get("usuarios", []))

    def save_offline_cache(self, data: dict):
        _write_json_atomic(CACHE_FILE, data)
        self._set_cache(data)

    def _auth_headers(self) -> dict:
        return {"X-Device-Token": self.token_api}

    # -------------------------------------------------------------
    # LATIDO PERIÓDICO (RF-10) Y SINCRONIZACIÓN DE REGLAS (RF-08, RF-09)
    # -------------------------------------------------------------
    def start_heartbeat_thread(self):
        threading.Thread(target=self._heartbeat_loop, daemon=True, name="latido").start()

    def _heartbeat_loop(self):
        print(f"[LATIDO] Servicio de señal periódica activo (cada {self.heartbeat_interval} seg)...")
        while self.running:
            self.reload_config_if_changed()
            try:
                if self.send_heartbeat():
                    self.sync_offline_rules()
                    self.flush_offline_queue()
                    self.flush_cleaning_queue()
            except Exception as e:
                if self.online:
                    print(f"[ALERTA RED] Se perdió la conexión con el servidor: {e}")
                else:
                    print(f"[BUSCANDO SERVIDOR] {self.server_url} no responde; reintento en {RETRY_OFFLINE_SEG} s.")
                self.online = False
            espera = self.heartbeat_interval if self.online else RETRY_OFFLINE_SEG
            # dormir en pasos cortos para notar pronto un config.json nuevo
            fin = time.time() + espera
            while self.running and time.time() < fin:
                time.sleep(1)
                if self._mtime(self.config_path) != self._config_mtime:
                    break

    def send_heartbeat(self):
        """Envía señal de 'sigo en línea' al servidor (RF-10)."""
        payload = {
            "dispositivo_id": self.device_id,
            "token_api": self.token_api,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        res = requests.post(f"{self.server_url}/api/iot/heartbeat", json=payload, timeout=5)
        if res.status_code == 200:
            if not self.online:
                print(f"[CONECTADO] Servidor {self.server_url} encontrado. Puerta en línea.")
            self.online = True
            print(f"[LATIDO OK] Señal de vida confirmada por servidor a las {datetime.now().strftime('%H:%M:%S')}")
            return True
        self.online = False
        if res.status_code in (401, 403):
            print("[TOKEN RECHAZADO] El servidor no reconoce este token (¿se regeneró o se desactivó la puerta?).")
            print("                  Descarga de nuevo el config.json del panel y reemplázalo.")
        else:
            print(f"[LATIDO] Respuesta inesperada del servidor: {res.status_code}")
        return False

    def sync_offline_rules(self):
        """Descarga listas de horarios y vectores faciales para operar sin internet (RF-08)."""
        # El token viaja en header (no en la URL) para que no quede en logs
        params = {"dispositivo_id": self.device_id}
        res = requests.get(f"{self.server_url}/api/iot/sync-offline-rules", params=params,
                           headers=self._auth_headers(), timeout=8)
        if res.status_code == 200:
            data = res.json()
            self.save_offline_cache(data)
            print(f"[SINCRONIZACIÓN] {len(data.get('usuarios', []))} usuarios y {len(data.get('horarios', []))} horarios actualizados en caché local.")

    def enqueue_offline_access(self, record: dict):
        """Almacena intentos cuando no hay conexión (RF-08)."""
        queue = _read_json(QUEUE_FILE, [])
        queue.append(record)
        _write_json_atomic(QUEUE_FILE, queue)
        print(f"[COLA LOCAL] Acceso guardado localmente ({len(queue)} pendientes de sincronizar).")

    def flush_offline_queue(self):
        """Envía registros acumulados al reconectarse sin duplicar (RF-09)."""
        queue = _read_json(QUEUE_FILE, [])
        if not queue:
            return
        try:
            for item in queue:
                item["token_api"] = self.token_api
                item["dispositivo_id"] = self.device_id
            res = requests.post(f"{self.server_url}/api/iot/access-attempts-batch", json=queue, timeout=10)
            if res.status_code == 200:
                print(f"[RECONEXIÓN OK] {len(queue)} registros offline sincronizados con éxito.")
                os.remove(QUEUE_FILE)
        except Exception as e:
            print(f"[COLA RETRY] Servidor no disponible para vaciar cola: {e}")

    # -------------------------------------------------------------
    # COMANDOS REMOTOS DEL DASHBOARD (apertura manual)
    # -------------------------------------------------------------
    def start_command_thread(self):
        threading.Thread(target=self._command_loop, daemon=True, name="comandos").start()

    def _command_loop(self):
        print(f"[COMANDOS] Escuchando órdenes remotas del Dashboard (cada {self.command_interval} seg)...")
        while self.running:
            try:
                self.poll_commands()
            except Exception:
                pass  # sin red: se reintenta en el siguiente ciclo
            time.sleep(self.command_interval)

    def poll_commands(self):
        res = requests.get(f"{self.server_url}/api/iot/commands", params={"dispositivo_id": self.device_id},
                           headers=self._auth_headers(), timeout=4)
        if res.status_code != 200:
            return
        for cmd in res.json().get("comandos", []):
            exito, detalle = True, "Ejecutado"
            if cmd.get("tipo") == "abrir_puerta":
                print(f"\n[COMANDO REMOTO] Apertura solicitada por {cmd.get('solicitado_por') or 'administrador'}.")
                self.unlock_door()
            else:
                exito, detalle = False, f"Comando no soportado: {cmd.get('tipo')}"
            try:
                requests.post(f"{self.server_url}/api/iot/commands/{cmd['id']}/ack",
                              json={"dispositivo_id": self.device_id, "exito": exito, "detalle": detalle},
                              headers=self._auth_headers(), timeout=4)
            except Exception as e:
                print(f"[COMANDOS] No se pudo confirmar el comando {cmd.get('id')}: {e}")

    # -------------------------------------------------------------
    # BITÁCORA DE LIMPIEZA (RF-04): entrada/salida alternadas por persona
    # -------------------------------------------------------------
    def register_cleaning(self, personal_id: str) -> str:
        """Alterna entrada/salida para el personal de limpieza y lo reporta. Retorna la acción."""
        estado = _read_json(CLEANING_STATE_FILE, {})
        accion = "salida" if estado.get(personal_id) == "dentro" else "entrada"
        estado[personal_id] = "dentro" if accion == "entrada" else "fuera"
        _write_json_atomic(CLEANING_STATE_FILE, estado)

        registro = {
            "dispositivo_id": self.device_id,
            "personal_id": personal_id,
            "accion": accion,
            "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if not self._send_cleaning(registro):
            cola = _read_json(CLEANING_QUEUE_FILE, [])
            cola.append(registro)
            _write_json_atomic(CLEANING_QUEUE_FILE, cola)
            print(f"[LIMPIEZA] Registro de {accion} guardado offline ({len(cola)} pendientes).")
        return accion

    def _send_cleaning(self, registro: dict) -> bool:
        try:
            res = requests.post(f"{self.server_url}/api/iot/cleaning-log",
                                json={**registro, "token_api": self.token_api}, timeout=4)
            return res.status_code in (200, 400)  # 400 = dato inválido: no reintentar
        except Exception:
            return False

    def flush_cleaning_queue(self):
        cola = _read_json(CLEANING_QUEUE_FILE, [])
        if not cola:
            return
        pendientes = []
        for i, reg in enumerate(cola):
            if not self._send_cleaning(reg):
                pendientes = cola[i:]  # conservar el orden entrada -> salida
                break
        if pendientes:
            _write_json_atomic(CLEANING_QUEUE_FILE, pendientes)
        else:
            os.remove(CLEANING_QUEUE_FILE)
            print(f"[LIMPIEZA] {len(cola)} registros de bitácora sincronizados.")

    # -------------------------------------------------------------
    # RECONOCIMIENTO FACIAL Y VALIDACIÓN DE HORARIOS (RF-01, RF-02, RF-03, RF-07)
    # -------------------------------------------------------------
    def identify_face_vector(self, face_vector: list) -> tuple:
        """Compara el vector con los usuarios de la caché local. Retorna (usuario|None, similitud)."""
        with self.cache_lock:
            index = self.vector_index
        user, sim = index.best_match(face_vector)
        if user and sim >= self.threshold:
            return user, sim
        return None, sim

    def validate_schedule(self, user: dict, now: datetime = None) -> tuple:
        """Valida permisos de acceso según tipo de usuario y horario de clase (RF-02, RF-03, RF-04)."""
        if not now:
            now = datetime.now()

        dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dia_actual = dias_es[now.weekday()]
        hora_actual = now.strftime("%H:%M")

        u_type = user.get("tipo")
        u_id = user.get("usuario_id")
        grupo_id = user.get("grupo_id")

        if u_type == "personal_limpieza":
            return True, "Acceso autorizado para personal de limpieza"
        if u_type == "administrador":
            return True, "Acceso administrativo"

        horarios = self.offline_cache.get("horarios", [])
        # La puerta abre unos minutos antes de la clase (lo define el servidor; 10 por defecto)
        try:
            tolerancia = max(0, int(self.offline_cache.get("tolerancia_min", 10)))
        except (TypeError, ValueError):
            tolerancia = 10
        hora_con_tolerancia = (now + timedelta(minutes=tolerancia)).strftime("%H:%M")

        def en_horario(h):
            return h["hora_inicio"] <= hora_con_tolerancia and hora_actual <= h["hora_fin"]

        if u_type == "alumno":
            for h in horarios:
                if h["dia_semana"] == dia_actual and h["grupo_id"] == grupo_id:
                    if en_horario(h):
                        return True, f"Acceso de alumno autorizado: Clase de {h['materia']} (Grupo {grupo_id})"
            return False, f"Acceso denegado: El grupo {grupo_id} no tiene clase en este salón a las {hora_actual} ({dia_actual})"

        if u_type == "docente":
            for h in horarios:
                if h["dia_semana"] == dia_actual and h["docente_id"] == u_id:
                    if en_horario(h):
                        return True, f"Docente en turno: Impartiendo {h['materia']}"
            return False, f"Acceso denegado: El docente no tiene clase asignada a las {hora_actual} ({dia_actual})"

        return False, "Tipo de usuario no autorizado para este laboratorio"

    # -------------------------------------------------------------
    # CONTROL DE CERRADURA ELECTROMAGNÉTICA (HARDWARE REAL)
    # -------------------------------------------------------------
    def unlock_door(self):
        """Activa el relevador para liberar la cerradura electromagnética por N segundos."""
        with self.door_lock:
            print(f"\n[CERRADURA] >> ACCESO PERMITIDO. Liberando puerta por {self.open_seconds} segundos...")
            if HARDWARE_GPIO_AVAILABLE:
                try:
                    GPIO.output(self.pin_cerradura, GPIO.HIGH)
                    GPIO.output(self.pin_led_verde, GPIO.HIGH)
                    self._buzzer(True)
                    time.sleep(0.3)
                    self._buzzer(False)
                    time.sleep(self.open_seconds)
                finally:
                    # Pase lo que pase, la cerradura vuelve a bloquearse
                    GPIO.output(self.pin_cerradura, GPIO.LOW)
                    GPIO.output(self.pin_led_verde, GPIO.LOW)
                print("[CERRADURA] >> Puerta bloqueada nuevamente.\n")
            else:
                time.sleep(1)

    def deny_door(self):
        """Mantiene la puerta bloqueada e indica rechazo con luz roja / sonido."""
        with self.door_lock:
            print("\n[CERRADURA] -- ACCESO DENEGADO. La puerta permanece BLOQUEADA.\n")
            if HARDWARE_GPIO_AVAILABLE:
                GPIO.output(self.pin_led_rojo, GPIO.HIGH)
                self._buzzer(True)
                time.sleep(0.8)
                GPIO.output(self.pin_led_rojo, GPIO.LOW)
                self._buzzer(False)

    # -------------------------------------------------------------
    # PROCESAMIENTO DE ACCESO CON PRIVACIDAD (RF-07)
    # -------------------------------------------------------------
    def process_access(self, face_vector: list, custom_now: datetime = None) -> dict:
        """
        CUMPLIMIENTO RF-07: aquí solo llega el vector numérico; la imagen ya fue descartada.
        """
        user, sim = self.identify_face_vector(face_vector)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not user:
            self.deny_door()
            record = {
                "dispositivo_id": self.device_id,
                "usuario_id": None,
                "resultado": "denegado",
                "motivo": "Rostro no registrado en la base de datos de usuarios autorizados",
                "fecha_hora": timestamp,
                "sincronizado_offline": False
            }
            self.report_access(record)
            return record

        permitido, motivo = self.validate_schedule(user, custom_now)

        if permitido and user.get("tipo") == "personal_limpieza":
            accion = self.register_cleaning(user["usuario_id"])
            motivo = f"Personal de limpieza: {accion} registrada en bitácora"

        if permitido:
            self.unlock_door()
            resultado_str = "permitido"
        else:
            self.deny_door()
            resultado_str = "denegado"

        record = {
            "dispositivo_id": self.device_id,
            "usuario_id": user["usuario_id"],
            "resultado": resultado_str,
            "motivo": motivo,
            "fecha_hora": timestamp,
            "sincronizado_offline": False
        }
        self.report_access(record)
        return record

    def report_access(self, record: dict):
        record["token_api"] = self.token_api
        try:
            res = requests.post(f"{self.server_url}/api/iot/access-attempt", json=record, timeout=4)
            if res.status_code == 200:
                print("[ACCESO REPORTADO] Sincronizado en tiempo real con servidor.")
                return
        except Exception:
            pass

        record_offline = dict(record)
        del record_offline["token_api"]
        record_offline["sincronizado_offline"] = True
        self.enqueue_offline_access(record_offline)

    # -------------------------------------------------------------
    # BUCLE DE RECONOCIMIENTO CONTINUO (cámara real)
    # -------------------------------------------------------------
    def _should_skip(self, key: str) -> bool:
        """True si ya se decidió sobre esta persona hace menos de repeat_cooldown segundos."""
        now = time.time()
        last = self.last_decision.get(key)
        if last and now - last < self.repeat_cooldown:
            return True
        self.last_decision[key] = now
        return False

    # -------------------------------------------------------------
    # MODO BOTÓN: presionar -> cuenta regresiva -> foto -> verificación
    # -------------------------------------------------------------
    def _sondear_boton(self):
        """Detecta la pulsación leyendo el pin (HIGH en reposo, LOW al presionar)."""
        anterior = 1
        while self.running:
            try:
                actual = GPIO.input(self.pin_boton)
            except Exception:
                return
            if anterior == 1 and actual == 0:
                self.boton_presionado.set()
                time.sleep(0.3)  # antirrebote
            anterior = actual
            time.sleep(0.02)

    def start_keyboard_button(self):
        """Sin GPIO (pruebas en PC): la tecla Enter hace de botón."""
        if HARDWARE_GPIO_AVAILABLE or not sys.stdin or not sys.stdin.isatty():
            return

        def leer():
            while self.running:
                try:
                    input()
                except (EOFError, OSError):
                    return
                self.boton_presionado.set()
        threading.Thread(target=leer, daemon=True).start()
        print("[INFO] Sin botón físico: presione Enter para simular el botón.")

    def _senal_cuenta(self, ultimo: bool):
        """Parpadeo del LED verde y pitido corto en cada segundo de la cuenta."""
        if not HARDWARE_GPIO_AVAILABLE:
            time.sleep(1)
            return
        pin = self.pin_led_verde
        GPIO.output(pin, GPIO.HIGH)
        self._buzzer(True)
        time.sleep(0.25 if ultimo else 0.08)
        self._buzzer(False)
        time.sleep(0.15)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.75 if not ultimo else 0.6)

    def cuenta_regresiva(self):
        n = max(0, int(self.countdown_seconds))
        print(f"[BOTÓN] Presionado. Mire a la cámara, foto en {n} s...")
        for i in range(n, 0, -1):
            print(f"[BOTÓN] {i}...")
            self._senal_cuenta(ultimo=(i == 1))

    def tomar_foto(self, camera, engine, intentos_seg: float = 2.0):
        """Toma la foto al terminar la cuenta y extrae el vector facial.
        Si en la primera imagen no se ve un rostro, sigue probando hasta intentos_seg."""
        for _ in range(4):           # descartar imágenes viejas del búfer de la cámara
            camera.read()
        limite = time.time() + intentos_seg
        while True:
            frame = camera.read()
            if frame is not None:
                vector, score = engine.extract_vector(frame)
                del frame            # RF-07: la imagen se descarta de RAM inmediatamente
                if vector is not None:
                    return vector, score
            if time.time() >= limite:
                return None, 0.0
            time.sleep(0.1)

    def verificar_con_boton(self, camera, engine):
        """Un ciclo completo del botón. Devuelve el registro de acceso o None si no hubo rostro."""
        self.cuenta_regresiva()
        print("[BOTÓN] Tomando foto...")
        vector, score = self.tomar_foto(camera, engine)
        if vector is None:
            print("[BOTÓN] No se detectó un rostro. Presione el botón de nuevo y mire a la cámara.")
            self.deny_door()
            return None
        user, sim = self.identify_face_vector(vector)
        nombre = user["nombre"] if user else "desconocido"
        print(f"[RECONOCIMIENTO] Rostro detectado (conf. {score:.2f}) -> {nombre} (similitud {sim:.3f})")
        registro = self.process_access(vector)
        del vector
        return registro

    def _ciclo_boton(self, camera, engine):
        self.start_keyboard_button()
        print(f"\n[RECONOCIMIENTO] Cámara lista. Presione el botón para verificar "
              f"(foto a los {self.countdown_seconds} s).")
        while self.running:
            if not self.boton_presionado.wait(timeout=0.5):
                continue
            self.boton_presionado.clear()
            try:
                self.verificar_con_boton(camera, engine)
            except Exception as e:
                print(f"[BOTÓN] Error durante la verificación: {e}")
            self.boton_presionado.clear()   # ignorar lo que se presionó mientras verificaba

    def run_recognition_loop(self):
        try:
            engine = FaceEngine(min_face_px=self.config.get("tamano_minimo_rostro_px", 60))
            camera = Camera(self.camera_index, *self.frame_size)
        except (FaceEngineUnavailable, RuntimeError) as e:
            print(f"[ERROR] Reconocimiento facial no disponible: {e}")
            print("        El nodo seguirá activo para latido y apertura remota.")
            while self.running:
                time.sleep(1)
            return

        if self.capture_mode == "boton":
            try:
                self._ciclo_boton(camera, engine)
            finally:
                camera.close()
            return

        print("\n[RECONOCIMIENTO] Cámara lista. Esperando rostros frente a la puerta...")
        fallos_camara = 0
        try:
            while self.running:
                frame = camera.read()
                if frame is None:
                    fallos_camara += 1
                    if fallos_camara % 50 == 1:
                        print("[CÁMARA] Sin imagen; reintentando...")
                    time.sleep(0.2)
                    continue
                fallos_camara = 0

                vector, score = engine.extract_vector(frame)
                del frame  # RF-07: la imagen se descarta de RAM inmediatamente
                if vector is None:
                    time.sleep(0.05)
                    continue

                user, sim = self.identify_face_vector(vector)
                key = user["usuario_id"] if user else "desconocido"
                if self._should_skip(key):
                    continue
                nombre = user["nombre"] if user else "desconocido"
                print(f"[RECONOCIMIENTO] Rostro detectado (conf. {score:.2f}) -> {nombre} (similitud {sim:.3f})")
                self.process_access(vector)
                del vector
        finally:
            camera.close()


if __name__ == "__main__":
    print("=" * 65)
    print(" NeoAccess • Nodo de Puerta Raspberry Pi Zero W (Modo Producción)")
    print("=" * 65)
    esperar_config()
    node = NeoAccessRaspberryNode()

    # El hilo de latido busca el servidor solo (cada 15 s mientras no responda)
    node.start_heartbeat_thread()
    node.start_command_thread()

    try:
        node.run_recognition_loop()
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        if HARDWARE_GPIO_AVAILABLE:
            GPIO.cleanup()
        print("\nNodo finalizado con seguridad.")
