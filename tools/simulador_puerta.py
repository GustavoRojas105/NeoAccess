"""
NeoAccess - Simulador de la puerta (Raspberry Pi) en la computadora.

Abre una página que se ve como la puerta de un laboratorio: eliges quién llega,
la puerta decide con la MISMA lógica de la Raspberry real (rpi_main.py) y todo
se refleja en la plataforma: puerta "en línea", accesos, bitácora de limpieza y
apertura remota desde el panel.

Todo lo que genera queda ligado a una puerta llamada SIM-<LAB> (p. ej. SIM-LMU),
así se distingue de lo real. Para borrarlo:  python tools\\borrar_simulacion.py

Uso (desde la carpeta NeoAccess, con el servidor corriendo):
    python tools\\simulador_puerta.py                 -> laboratorio por defecto
    python tools\\simulador_puerta.py --lab LPB
Opciones: --servidor http://127.0.0.1:8000  --db database\\neoaccess.db  --puerto 8020  --sin-navegador
"""
import argparse
import json
import os
import random
import sqlite3
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "raspberry_pi"))

import rpi_main as rm  # noqa: E402
from backend.auth import generate_device_token  # noqa: E402

PREFIJO = "SIM-"
CARPETA_ESTADO = os.path.join(RAIZ, "tools", "simulador_datos")
PAGINA = os.path.join(RAIZ, "tools", "simulador_puerta.html")
INTERVALO_LATIDO = 60  # la tarjeta del panel se pone en verde rápido y se apaga ~2 min después de cerrar
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
URL_SIN_RED = "http://127.0.0.1:9"  # puerto cerrado: simula que se cayó el Wi-Fi


# ───────────────────────── Base de datos (solo lo que haría el admin en el panel) ─────────────────────────
class BD:
    def __init__(self, ruta):
        self.ruta = ruta

    def _con(self, solo_lectura=True):
        if solo_lectura:
            c = sqlite3.connect(f"file:{self.ruta}?mode=ro", uri=True, timeout=10)
        else:
            c = sqlite3.connect(self.ruta, timeout=10)
            c.execute("PRAGMA foreign_keys = ON")
        c.row_factory = sqlite3.Row
        return c

    def laboratorios(self):
        with self._con() as c:
            return [dict(r) for r in c.execute("SELECT id, nombre, carrera FROM laboratorios ORDER BY id")]

    def asegurar_puerta(self, lab_id):
        """Crea (una vez) la puerta simulada SIM-<LAB> igual que si se diera de alta en el panel."""
        dev_id = f"{PREFIJO}{lab_id}"
        with self._con(False) as c:
            lab = c.execute("SELECT nombre FROM laboratorios WHERE id = ?", (lab_id,)).fetchone()
            if not lab:
                raise ValueError(f"No existe el laboratorio {lab_id}.")
            dev = c.execute("SELECT * FROM dispositivos WHERE id = ?", (dev_id,)).fetchone()
            if not dev:
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""INSERT INTO dispositivos (id, laboratorio_id, nombre, token_api, ip_address, mac_address,
                             intervalo_latido_seg, ultima_senal, estado, activo)
                             VALUES (?, ?, ?, ?, '127.0.0.1', NULL, ?, NULL, 'fuera_de_linea', 1)""",
                          (dev_id, lab_id, f"Simulador de puerta - {lab['nombre']}", generate_device_token(), INTERVALO_LATIDO))
                c.execute("""INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
                             VALUES (?, 'conexion', 'Puerta simulada creada por el simulador', ?)""", (dev_id, ahora))
                print(f"[SIMULADOR] Puerta simulada {dev_id} creada.")
                dev = c.execute("SELECT * FROM dispositivos WHERE id = ?", (dev_id,)).fetchone()
            elif not dev["activo"]:
                print(f"[SIMULADOR] Aviso: la puerta {dev_id} está desactivada en el panel.")
            return dict(dev), lab["nombre"]

    def personas(self):
        """Personas activas (con o sin rostro registrado) para elegir quién llega a la puerta."""
        with self._con() as c:
            filas = c.execute("""
                SELECT u.id, u.nombre_completo, u.tipo, u.matricula_clave, u.grupo_id, u.carrera,
                       EXISTS(SELECT 1 FROM metadatos_faciales mf WHERE mf.usuario_id = u.id) AS con_rostro
                FROM usuarios u WHERE u.estado = 'activo'
                ORDER BY con_rostro DESC, CASE u.tipo WHEN 'docente' THEN 1 WHEN 'alumno' THEN 2 ELSE 3 END, u.nombre_completo""")
            return [dict(r) for r in filas]


# ───────────────────────── La puerta: rpi_main con la cerradura dibujada en pantalla ─────────────────────────
class PuertaSimulada(rm.NeoAccessRaspberryNode):
    def __init__(self, config_path):
        self.puerta = {"abierta_hasta": 0.0, "led": None, "led_hasta": 0.0}
        self.bitacora = []          # lo que se muestra en la pantalla del simulador
        self.sin_red = False
        self.url_real = None
        super().__init__(config_path)
        self.url_real = self.server_url

    # La cerradura real usa GPIO y se queda dormida N segundos; aquí solo se dibuja.
    def unlock_door(self):
        t = time.time()
        self.puerta.update(abierta_hasta=t + self.open_seconds, led="verde", led_hasta=t + self.open_seconds)
        self.anotar("🔓 Cerradura liberada", f"{self.open_seconds} s")

    def deny_door(self):
        self.puerta.update(led="rojo", led_hasta=time.time() + 2)

    def anotar(self, titulo, detalle="", tipo="info"):
        self.bitacora.insert(0, {"hora": datetime.now().strftime("%H:%M:%S"), "titulo": titulo,
                                 "detalle": detalle, "tipo": tipo})
        del self.bitacora[40:]

    def poll_commands(self):
        antes = self.puerta["abierta_hasta"]
        super().poll_commands()
        if self.puerta["abierta_hasta"] != antes:
            self.anotar("📡 Apertura remota desde el panel", "La orden llegó y se confirmó al servidor", "remoto")

    def cortar_red(self, cortar: bool):
        self.sin_red = cortar
        if cortar:
            self.server_url = URL_SIN_RED
            self.online = False
            self.anotar("📴 Wi-Fi desconectado", "La puerta sigue decidiendo con su copia local", "aviso")
        else:
            self.server_url = self.url_real
            self.anotar("📶 Wi-Fi reconectado", "Enviando lo pendiente…", "info")
            threading.Thread(target=self.sincronizar, daemon=True).start()

    def reload_config_if_changed(self):
        if not self.sin_red:  # con la red "cortada" no se cambia la URL
            super().reload_config_if_changed()

    def sincronizar(self):
        try:
            if self.send_heartbeat():
                self.sync_offline_rules()
                self.flush_offline_queue()
                self.flush_cleaning_queue()
                return True
        except Exception:
            self.online = False
        return False

    def presentar(self, persona, momento):
        """Alguien se para frente a la cámara. persona=None -> rostro desconocido."""
        en_cola = len(rm._read_json(rm.QUEUE_FILE, []))
        if persona is None:
            vector = [random.gauss(0, 1) for _ in range(128)]
            rec = self.process_access(vector, momento)
            nombre = "Persona no registrada"
        else:
            cache = {u["usuario_id"]: u for u in self.offline_cache.get("usuarios", [])}
            usuario = cache.get(persona["id"])
            if usuario and usuario.get("vector_encoding"):
                # Tiene rostro registrado: se usa su vector real, igual que la cámara
                rec = self.process_access(usuario["vector_encoding"], momento)
            else:
                rec = self._decidir_sin_vector(persona, momento)
            nombre = persona["nombre_completo"]
        enviado = len(rm._read_json(rm.QUEUE_FILE, [])) == en_cola  # no se quedó en la cola offline
        rec.pop("token_api", None)
        self.anotar(("✅ " if rec["resultado"] == "permitido" else "⛔ ") + nombre, rec["motivo"],
                    rec["resultado"])
        return {**rec, "nombre": nombre, "enviado": enviado,
                "momento": f"{DIAS[(momento or datetime.now()).weekday()]} {(momento or datetime.now()):%H:%M}"}

    def _decidir_sin_vector(self, persona, momento):
        """Mismo flujo que process_access, saltando solo la comparación del rostro."""
        user = {"usuario_id": persona["id"], "tipo": persona["tipo"], "grupo_id": persona["grupo_id"],
                "nombre": persona["nombre_completo"]}
        permitido, motivo = self.validate_schedule(user, momento)
        if permitido and user["tipo"] == "personal_limpieza":
            accion = self.register_cleaning(user["usuario_id"])
            motivo = f"Personal de limpieza: {accion} registrada en bitácora"
        (self.unlock_door if permitido else self.deny_door)()
        rec = {"dispositivo_id": self.device_id, "usuario_id": user["usuario_id"],
               "resultado": "permitido" if permitido else "denegado", "motivo": motivo,
               "fecha_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "sincronizado_offline": False}
        self.report_access(rec)
        return rec


# ───────────────────────── Simulador (estado + servidor web local) ─────────────────────────
class Simulador:
    def __init__(self, bd, servidor):
        self.bd = bd
        self.servidor = servidor.rstrip("/")
        self.nodo = None
        self.lab = None
        self.lab_nombre = ""
        self.lock = threading.Lock()

    def usar_laboratorio(self, lab_id):
        with self.lock:
            if self.nodo:
                self.nodo.running = False
            dev, self.lab_nombre = self.bd.asegurar_puerta(lab_id)
            self.lab = lab_id
            carpeta = os.path.join(CARPETA_ESTADO, dev["id"])
            os.makedirs(carpeta, exist_ok=True)
            # Archivos propios de esta puerta simulada (no se mezclan con los de una Raspberry real)
            rm.CACHE_FILE = os.path.join(carpeta, "cache_offline.json")
            rm.QUEUE_FILE = os.path.join(carpeta, "cola_offline.json")
            rm.CLEANING_QUEUE_FILE = os.path.join(carpeta, "cola_limpieza.json")
            rm.CLEANING_STATE_FILE = os.path.join(carpeta, "limpieza_estado.json")
            rm.CONFIG_EXTRA = []
            config = os.path.join(carpeta, "config.json")
            rm._write_json_atomic(config, {
                "dispositivo_id": dev["id"], "nombre": dev["nombre"], "token_api": dev["token_api"],
                "servidor_url": self.servidor, "laboratorio_id": lab_id,
                "intervalo_latido_seg": INTERVALO_LATIDO, "segundos_puerta_abierta": 5,
                "intervalo_comandos_seg": 2})
            nodo = PuertaSimulada(config)
            nodo.anotar("🔌 Puerta encendida", f"{dev['id']} · {self.lab_nombre}")
            if nodo.sincronizar():
                nodo.anotar("🟢 Conectada al servidor", self.servidor)
            else:
                nodo.anotar("🔎 Buscando servidor…", f"{self.servidor} no responde; reintenta cada 15 s", "aviso")
            nodo.start_heartbeat_thread()
            nodo.start_command_thread()
            self.nodo = nodo

    def estado(self):
        n = self.nodo
        ahora = time.time()
        horarios = sorted(n.offline_cache.get("horarios", []),
                          key=lambda h: (DIAS.index(h["dia_semana"]) if h["dia_semana"] in DIAS else 9, h["hora_inicio"]))
        return {
            "dispositivo_id": n.device_id, "laboratorio": self.lab, "laboratorio_nombre": self.lab_nombre,
            "servidor": n.url_real, "en_linea": bool(n.online and not n.sin_red), "sin_red": n.sin_red,
            "abierta": n.puerta["abierta_hasta"] > ahora,
            "led": n.puerta["led"] if n.puerta["led_hasta"] > ahora else None,
            "pendientes": len(rm._read_json(rm.QUEUE_FILE, [])) + len(rm._read_json(rm.CLEANING_QUEUE_FILE, [])),
            "rostros_en_cache": len(n.offline_cache.get("usuarios", [])),
            "horarios": horarios, "bitacora": n.bitacora,
            "ultima_sincronizacion": n.offline_cache.get("timestamp"),
        }


def momento_simulado(datos):
    if datos.get("modo") != "personalizado":
        return None
    dia = DIAS.index(datos["dia"])
    hh, mm = (int(x) for x in datos["hora"].split(":"))
    hoy = datetime.now()
    fecha = hoy + timedelta(days=(dia - hoy.weekday()) % 7)
    return fecha.replace(hour=hh, minute=mm, second=0, microsecond=0)


def crear_handler(sim: Simulador):
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
            return json.loads(self.rfile.read(largo) or b"{}")

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
                self._json({"personas": sim.bd.personas(), "laboratorios": sim.bd.laboratorios(), "dias": DIAS})
            else:
                self._json({"error": "no encontrado"}, 404)

        def do_POST(self):
            try:
                datos = self._leer()
                if self.path == "/api/presentar":
                    persona = None
                    if datos.get("usuario_id"):
                        persona = next((p for p in sim.bd.personas() if p["id"] == datos["usuario_id"]), None)
                        if not persona:
                            return self._json({"error": "Esa persona no existe o está dada de baja."}, 400)
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
                elif self.path == "/api/laboratorio":
                    sim.usar_laboratorio(datos["laboratorio"])
                    self._json({"ok": True})
                else:
                    self._json({"error": "no encontrado"}, 404)
            except Exception as e:
                self._json({"error": str(e)}, 500)
    return Handler


def main():
    ap = argparse.ArgumentParser(description="Simulador de la puerta NeoAccess")
    ap.add_argument("--lab", help="ID del laboratorio (por defecto el primero)")
    ap.add_argument("--servidor", default="http://127.0.0.1:8000")
    ap.add_argument("--db", default=os.path.join(RAIZ, "database", "neoaccess.db"))
    ap.add_argument("--puerto", type=int, default=8020)
    ap.add_argument("--sin-navegador", action="store_true")
    args = ap.parse_args()

    bd = BD(args.db)
    labs = bd.laboratorios()
    if not labs:
        print("No hay laboratorios dados de alta. Crea uno en el panel primero.")
        return 1
    lab = args.lab or labs[0]["id"]
    sim = Simulador(bd, args.servidor)
    sim.usar_laboratorio(lab)

    srv = ThreadingHTTPServer(("127.0.0.1", args.puerto), crear_handler(sim))
    url = f"http://127.0.0.1:{args.puerto}"
    print("=" * 65)
    print(f"  Simulador de puerta listo en {url}")
    print(f"  Puerta simulada: {sim.nodo.device_id}  ->  servidor {args.servidor}")
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
