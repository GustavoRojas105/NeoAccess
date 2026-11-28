"""
NeoAccess - Simulador de puerta contra el SERVIDOR EN LÍNEA (https://stem.itsoeh.edu.mx).

Es la versión "de internet" de tools/simulador_puerta.py (que sigue igual, para el servidor local):
  - No toca ninguna base de datos: se comporta exactamente como una Raspberry real, solo con
    el config.json (ID + token) que se descarga del panel del servidor.
  - "Escanear rostro" usa la cámara de esta computadora y el mismo motor que la puerta
    (YuNet + SFace). La imagen solo vive en memoria; al servidor solo llega el resultado.
  - También se puede elegir a una persona de la lista (sin cámara) para demostraciones.

Preparación (una vez, en el panel del servidor):
  Dispositivos -> Agregar -> ID p. ej. SIM-LCS (con SIM- se distingue de las puertas reales)
  -> Vincular -> Descargar config.json. Al abrir el simulador se pega o se elige ese archivo.

Uso:
    python tools\\simulador_servidor.py            (o doble clic en run_simulador_servidor.bat)
Opciones: --config RUTA  --puerto 8030  --camara 0  --sin-navegador
"""
import argparse
import base64
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "raspberry_pi"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import rpi_main as rm  # noqa: E402
from simulador_puerta import PuertaSimulada, momento_simulado, DIAS, INTERVALO_LATIDO  # noqa: E402
from face_engine import FaceEngine, FaceEngineUnavailable  # noqa: E402

CARPETA = os.path.join(RAIZ, "tools", "simulador_servidor_datos")
CONFIG_DEFECTO = os.path.join(CARPETA, "config.json")
PAGINA = os.path.join(RAIZ, "tools", "simulador_servidor.html")
SERVIDOR_DEFECTO = "https://stem.itsoeh.edu.mx"
MAX_IMAGEN = 3 * 1024 * 1024


def validar_config(datos) -> dict:
    if not isinstance(datos, dict):
        raise ValueError("Eso no es un config.json de NeoAccess.")
    faltan = [k for k in ("dispositivo_id", "token_api", "servidor_url") if not datos.get(k)]
    if faltan:
        raise ValueError("Al config.json le falta: " + ", ".join(faltan) +
                         ". Descárgalo del panel: Dispositivos → Vincular.")
    if not str(datos["servidor_url"]).startswith(("http://", "https://")):
        raise ValueError("servidor_url debe empezar con https://")
    return datos


class SimuladorServidor:
    def __init__(self, config_path):
        self.config_path = config_path
        self.nodo = None
        self.motor = None
        self.error_motor = None
        self.lock = threading.Lock()
        os.makedirs(CARPETA, exist_ok=True)
        # Cachés y colas propias (no se mezclan con el simulador local ni con una Raspberry)
        rm.CACHE_FILE = os.path.join(CARPETA, "cache_offline.json")
        rm.QUEUE_FILE = os.path.join(CARPETA, "cola_offline.json")
        rm.CLEANING_QUEUE_FILE = os.path.join(CARPETA, "cola_limpieza.json")
        rm.CLEANING_STATE_FILE = os.path.join(CARPETA, "limpieza_estado.json")
        rm.CONFIG_EXTRA = []
        if os.path.isfile(config_path):
            try:
                self.encender(validar_config(rm._read_json(config_path, None)))
            except ValueError as e:
                print(f"[SIMULADOR] {e}")

    def encender(self, cfg: dict):
        with self.lock:
            if self.nodo:
                self.nodo.running = False
            mismo = (rm._read_json(self.config_path, {}) or {}).get("dispositivo_id") == cfg["dispositivo_id"]
            if not mismo:  # otra puerta: la copia local anterior no le sirve
                for f in (rm.CACHE_FILE, rm.QUEUE_FILE, rm.CLEANING_QUEUE_FILE, rm.CLEANING_STATE_FILE):
                    if os.path.exists(f):
                        os.remove(f)
            cfg = {**cfg, "intervalo_latido_seg": INTERVALO_LATIDO, "intervalo_comandos_seg": 2,
                   "segundos_puerta_abierta": cfg.get("segundos_puerta_abierta", 5),
                   "segundos_espera_mismo_usuario": 0}
            rm._write_json_atomic(self.config_path, cfg)
            nodo = PuertaSimulada(self.config_path)
            nodo.anotar("🔌 Puerta encendida", f"{nodo.device_id} → {nodo.server_url}")
            if nodo.sincronizar():
                nodo.anotar("🟢 Conectada al servidor", f"{len(nodo.offline_cache.get('usuarios', []))} rostros descargados")
            else:
                nodo.anotar("🔎 Buscando servidor…", "No responde o rechazó el token; reintenta cada 15 s", "aviso")
            nodo.start_heartbeat_thread()
            nodo.start_command_thread()
            self.nodo = nodo

    def preparar_motor(self):
        if self.motor or self.error_motor:
            return
        try:
            self.motor = FaceEngine()
        except FaceEngineUnavailable as e:
            self.error_motor = str(e)

    def personas(self):
        if not self.nodo:
            return []
        return [{"id": u["usuario_id"], "nombre_completo": u.get("nombre") or u["usuario_id"], "tipo": u.get("tipo"),
                 "matricula_clave": u.get("matricula_clave"), "grupo_id": u.get("grupo_id"), "con_rostro": True}
                for u in self.nodo.offline_cache.get("usuarios", [])]

    def escanear(self, datos):
        """Una imagen de la cámara -> vector -> misma decisión que la puerta."""
        self.preparar_motor()
        if not self.motor:
            raise RuntimeError(self.error_motor)
        imagen = str(datos.get("imagen") or "")
        if "," in imagen:
            imagen = imagen.split(",", 1)[1]
        crudo = base64.b64decode(imagen)
        if not crudo or len(crudo) > MAX_IMAGEN:
            raise ValueError("Imagen vacía o demasiado grande.")
        vector, score = self.motor.extract_vector_from_bytes(crudo)
        del crudo  # RF-07: la foto no se guarda
        if vector is None:
            return {"rostro": False}
        nodo = self.nodo
        usuario, similitud = nodo.identify_face_vector(vector)
        en_cola = len(rm._read_json(rm.QUEUE_FILE, []))
        momento = momento_simulado(datos)
        rec = nodo.process_access(vector, momento)
        rec.pop("token_api", None)
        nombre = usuario.get("nombre") if usuario else "Rostro no reconocido"
        esperado = datos.get("esperado")
        esperado_nombre = next((p["nombre_completo"] for p in self.personas() if p["id"] == esperado), None) if esperado else None
        nodo.anotar(("✅ " if rec["resultado"] == "permitido" else "⛔ ") + f"{nombre} (cámara)",
                    f"{rec['motivo']} · similitud {similitud:.2f}", rec["resultado"])
        return {**rec, "rostro": True, "nombre": nombre, "similitud": round(similitud, 3),
                "esperado_nombre": esperado_nombre,
                "coincide": (usuario or {}).get("usuario_id") == esperado if esperado else None,
                "umbral": nodo.threshold, "enviado": len(rm._read_json(rm.QUEUE_FILE, [])) == en_cola,
                "momento": f"{DIAS[(momento or __import__('datetime').datetime.now()).weekday()]} "
                           f"{(momento or __import__('datetime').datetime.now()):%H:%M}"}

    def estado(self):
        n = self.nodo
        if not n:
            return {"configurado": False, "servidor_sugerido": SERVIDOR_DEFECTO}
        import time
        ahora = time.time()
        horarios = sorted(n.offline_cache.get("horarios", []),
                          key=lambda h: (DIAS.index(h["dia_semana"]) if h["dia_semana"] in DIAS else 9, h["hora_inicio"]))
        return {
            "configurado": True, "dispositivo_id": n.device_id,
            "laboratorio": n.offline_cache.get("laboratorio_id") or n.config.get("laboratorio_id") or "—",
            "servidor": n.url_real, "en_linea": bool(n.online and not n.sin_red), "sin_red": n.sin_red,
            "abierta": n.puerta["abierta_hasta"] > ahora,
            "led": n.puerta["led"] if n.puerta["led_hasta"] > ahora else None,
            "pendientes": len(rm._read_json(rm.QUEUE_FILE, [])) + len(rm._read_json(rm.CLEANING_QUEUE_FILE, [])),
            "rostros_en_cache": len(n.offline_cache.get("usuarios", [])),
            "horarios": horarios, "bitacora": n.bitacora,
            "ultima_sincronizacion": n.offline_cache.get("timestamp"),
            "motor": "listo" if self.motor else (self.error_motor or "sin cargar"),
        }


def crear_handler(sim: SimuladorServidor):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, datos, codigo=200):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _leer(self):
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > MAX_IMAGEN * 2:
                raise ValueError("Petición demasiado grande.")
            return json.loads(self.rfile.read(largo) or b"{}")

        def _local(self):
            # Solo la página de esta misma computadora (nada de otras pestañas o sitios)
            origen = self.headers.get("Origin")
            puerto = self.server.server_address[1]
            return origen is None or origen in (f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                cuerpo = open(PAGINA, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
            elif self.path == "/api/estado":
                self._json(sim.estado())
            elif self.path == "/api/personas":
                self._json({"personas": sim.personas(), "dias": DIAS})
            else:
                self._json({"error": "no encontrado"}, 404)

        def do_POST(self):
            if not self._local():
                return self._json({"error": "origen no permitido"}, 403)
            try:
                datos = self._leer()
                if self.path == "/api/config":
                    texto = datos.get("texto") or ""
                    try:
                        cfg = json.loads(texto)
                    except json.JSONDecodeError:
                        raise ValueError("El texto pegado no es un JSON válido.")
                    sim.encender(validar_config(cfg))
                    return self._json({"ok": True})
                if not sim.nodo:
                    return self._json({"error": "Primero carga el config.json de la puerta."}, 400)
                if self.path == "/api/escanear":
                    self._json(sim.escanear(datos))
                elif self.path == "/api/presentar":
                    persona = None
                    if datos.get("usuario_id"):
                        persona = next((p for p in sim.personas() if p["id"] == datos["usuario_id"]), None)
                        if not persona:
                            return self._json({"error": "Esa persona ya no está en la copia local."}, 400)
                    self._json(sim.nodo.presentar(persona, momento_simulado(datos)))
                elif self.path == "/api/red":
                    sim.nodo.cortar_red(bool(datos.get("cortar")))
                    self._json({"ok": True})
                elif self.path == "/api/sincronizar":
                    ok = sim.nodo.sincronizar()
                    sim.nodo.anotar("🔄 Sincronización" + (" correcta" if ok else " fallida"),
                                    "Reglas, rostros y horarios descargados" if ok else "El servidor no respondió",
                                    "info" if ok else "aviso")
                    self._json({"ok": ok})
                else:
                    self._json({"error": "no encontrado"}, 404)
            except (ValueError, RuntimeError) as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
    return Handler


def main():
    ap = argparse.ArgumentParser(description="Simulador de puerta NeoAccess contra el servidor en línea")
    ap.add_argument("--config", default=CONFIG_DEFECTO, help="config.json descargado del panel del servidor")
    ap.add_argument("--puerto", type=int, default=8030)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args()

    sim = SimuladorServidor(os.path.abspath(args.config))
    threading.Thread(target=sim.preparar_motor, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.puerto), crear_handler(sim))
    url = f"http://127.0.0.1:{args.puerto}"
    print("=" * 65)
    print(f"  Simulador (servidor en línea) listo en {url}")
    print(f"  Puerta: {sim.nodo.device_id + ' -> ' + sim.nodo.server_url if sim.nodo else 'sin configurar (pega el config.json en la página)'}")
    print("  Cierra esta ventana para apagar la puerta.")
    print("=" * 65)
    if not args.sin_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
