"""
NeoAccess - Prueba de Acceso (programa independiente)
Ubicación: prueba_acceso/prueba_acceso.py

Simula intentos de acceso a los laboratorios y muestra métricas.
Cada acceso individual PIDE EL ESCANEO DEL ROSTRO con la cámara: se usa el
mismo motor que las puertas (YuNet + SFace) y se compara con los rostros
registrados en el sistema. Después se decide el resultado:
automático (reglas del sistema), forzar ACEPTADO o forzar DENEGADO.

- Lee usuarios, laboratorios y vectores faciales de database/neoaccess.db en
  SOLO LECTURA.
- Guarda sus propios registros en prueba_acceso/prueba_acceso.db, así las
  pruebas NO se mezclan con las métricas reales del Dashboard.
- RF-07: los fotogramas de la cámara solo viven en memoria; nunca se guardan.
- No forma parte de la página principal del proyecto.

Ejecutar:  python prueba_acceso/prueba_acceso.py   (o doble clic en prueba_acceso.bat)
"""

import base64
import csv
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.abspath(os.path.join(AQUI, ".."))
DB_PRINCIPAL = os.path.join(RAIZ, "database", "neoaccess.db")
DB_PRUEBAS = os.path.join(AQUI, "prueba_acceso.db")

if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
try:
    from raspberry_pi.face_engine import (FaceEngine, FaceEngineUnavailable, VectorIndex,
                                          DEFAULT_COSINE_THRESHOLD)
    UMBRAL = DEFAULT_COSINE_THRESHOLD
except Exception:  # sin numpy/OpenCV el simulador sigue funcionando sin cámara
    FaceEngine = VectorIndex = None
    FaceEngineUnavailable = RuntimeError
    UMBRAL = 0.363  # mismo umbral de similitud coseno que usan las puertas

DESCONOCIDO_ID = "__DESCONOCIDO__"
DESCONOCIDO = {"id": DESCONOCIDO_ID, "nombre": "— Persona desconocida —", "matricula": "",
               "tipo": "desconocido", "estado": "activo", "rostro": False}

# Datos de respaldo si no existe la base principal
USUARIOS_DEMO = [
    {"id": "ALU-001", "nombre": "Alumno Demo Uno", "matricula": "22030001", "tipo": "alumno", "estado": "activo", "rostro": True},
    {"id": "ALU-002", "nombre": "Alumno Demo Dos", "matricula": "22030002", "tipo": "alumno", "estado": "activo", "rostro": False},
    {"id": "DOC-001", "nombre": "Docente Demo", "matricula": "DOC-001", "tipo": "docente", "estado": "activo", "rostro": True},
    {"id": "LIM-001", "nombre": "Limpieza Demo", "matricula": "LIM-001", "tipo": "personal_limpieza", "estado": "activo", "rostro": True},
]
LABS_DEMO = [
    {"id": "LAB-STEM-01", "nombre": "Lab STEM 01"},
    {"id": "LAB-ED6-01", "nombre": "Lab Edificio 6 - 01"},
]


# =============================================================
# DATOS
# =============================================================
def _conectar_solo_lectura(db_path: str):
    uri = "file:" + os.path.abspath(db_path).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def cargar_catalogos(db_path: str = DB_PRINCIPAL):
    """Usuarios y laboratorios desde la base principal (solo lectura)."""
    if not os.path.exists(db_path):
        return USUARIOS_DEMO, LABS_DEMO, False
    conn = _conectar_solo_lectura(db_path)
    try:
        usuarios = [{
            "id": r["id"], "nombre": r["nombre_completo"], "matricula": r["matricula_clave"],
            "tipo": r["tipo"], "estado": r["estado"], "rostro": bool(r["tiene_rostro"]),
        } for r in conn.execute("""
            SELECT u.id, u.nombre_completo, u.matricula_clave, u.tipo, u.estado,
                   CASE WHEN mf.id IS NULL THEN 0 ELSE 1 END AS tiene_rostro
            FROM usuarios u LEFT JOIN metadatos_faciales mf ON mf.usuario_id = u.id
            ORDER BY u.tipo, u.nombre_completo""")]
        labs = [{"id": r["id"], "nombre": r["nombre"]}
                for r in conn.execute("SELECT id, nombre FROM laboratorios WHERE activo = 1 ORDER BY id")]
    finally:
        conn.close()
    return (usuarios or USUARIOS_DEMO), (labs or LABS_DEMO), True


def cargar_vectores(db_path: str = DB_PRINCIPAL) -> list:
    """Usuarios con su vector facial registrado (para comparar el escaneo)."""
    if not os.path.exists(db_path):
        return []
    conn = _conectar_solo_lectura(db_path)
    try:
        filas = conn.execute("""
            SELECT u.id, u.nombre_completo, u.matricula_clave, u.tipo, u.estado, mf.vector_encoding
            FROM usuarios u JOIN metadatos_faciales mf ON mf.usuario_id = u.id""").fetchall()
    finally:
        conn.close()
    usuarios = []
    for r in filas:
        try:
            vec = json.loads(r["vector_encoding"])
        except (TypeError, ValueError):
            continue
        usuarios.append({"id": r["id"], "nombre": r["nombre_completo"], "matricula": r["matricula_clave"],
                         "tipo": r["tipo"], "estado": r["estado"], "rostro": True, "vector_encoding": vec})
    return usuarios


class RegistroPruebas:
    """Base de datos propia de las simulaciones."""

    CAMPOS = ["fecha_hora", "usuario_id", "usuario_nombre", "tipo", "laboratorio_id",
              "laboratorio_nombre", "resultado", "modo", "similitud", "motivo"]

    def __init__(self, path: str = DB_PRUEBAS):
        self.path = path
        conn = self._conn()
        conn.execute("""
        CREATE TABLE IF NOT EXISTS intentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT NOT NULL,
            usuario_id TEXT,
            usuario_nombre TEXT,
            tipo TEXT,
            laboratorio_id TEXT,
            laboratorio_nombre TEXT,
            resultado TEXT NOT NULL CHECK (resultado IN ('aceptado', 'denegado')),
            modo TEXT NOT NULL,
            similitud REAL,
            motivo TEXT
        );""")
        conn.commit()
        conn.close()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def guardar(self, intento: dict):
        self.guardar_varios([intento])

    def guardar_varios(self, intentos: list):
        conn = self._conn()
        conn.executemany("""
        INSERT INTO intentos (fecha_hora, usuario_id, usuario_nombre, tipo, laboratorio_id,
                              laboratorio_nombre, resultado, modo, similitud, motivo)
        VALUES (:fecha_hora, :usuario_id, :usuario_nombre, :tipo, :laboratorio_id,
                :laboratorio_nombre, :resultado, :modo, :similitud, :motivo)""", intentos)
        conn.commit()
        conn.close()

    def borrar_todo(self):
        conn = self._conn()
        conn.execute("DELETE FROM intentos")
        conn.commit()
        conn.close()

    def todos(self):
        conn = self._conn()
        filas = [dict(r) for r in conn.execute("SELECT * FROM intentos ORDER BY fecha_hora DESC, id DESC")]
        conn.close()
        return filas

    def exportar_csv(self, destino: str) -> int:
        filas = self.todos()
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self.CAMPOS, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        return len(filas)


# =============================================================
# SIMULACIÓN
# =============================================================
def _intento(usuario: dict, lab: dict, resultado: str, modo: str, similitud, motivo: str, fecha=None) -> dict:
    desconocido = usuario["id"] == DESCONOCIDO_ID
    return {
        "fecha_hora": (fecha or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "usuario_id": None if desconocido else usuario["id"],
        "usuario_nombre": usuario["nombre"],
        "tipo": usuario.get("tipo"),
        "laboratorio_id": lab["id"],
        "laboratorio_nombre": lab["nombre"],
        "resultado": resultado,
        "modo": modo,
        "similitud": None if similitud is None else round(float(similitud), 3),
        "motivo": motivo,
    }


def resolver_escaneo(coincidencia, similitud: float, lab: dict, modo: str, motivo_manual: str = "") -> dict:
    """
    Decide un acceso a partir de un escaneo REAL de rostro.
    coincidencia: usuario registrado más parecido (o None); similitud: coseno con ese usuario.
    modo: 'auto' (reglas de la puerta), 'aceptar' o 'denegar' (forzado).
    """
    if modo not in ("auto", "aceptar", "denegar"):
        raise ValueError("Modo inválido")
    similitud = round(float(similitud), 3)
    reconocido = coincidencia is not None and similitud >= UMBRAL
    persona = coincidencia if reconocido else DESCONOCIDO

    if modo == "auto":
        if not reconocido:
            resultado, motivo = "denegado", "Rostro no reconocido"
        elif persona.get("estado") != "activo":
            resultado, motivo = "denegado", "Usuario dado de baja"
        else:
            resultado, motivo = "aceptado", "Rostro reconocido"
    elif modo == "aceptar":
        resultado, motivo = "aceptado", "Aceptado manualmente (prueba)"
    else:
        resultado, motivo = "denegado", "Denegado manualmente (prueba)"

    if motivo_manual.strip():
        motivo = motivo_manual.strip()
    return _intento(persona, lab, resultado, f"escaneo-{modo}", similitud, motivo)


def simular_intento(usuario: dict, lab: dict, modo: str, motivo_manual: str = "",
                    fecha: datetime = None, rng: random.Random = random) -> dict:
    """
    Intento SIN cámara (se usa en la simulación masiva).
    modo: 'auto' -> reglas del sistema; 'aceptar' / 'denegar' -> forzado.
    """
    if modo not in ("auto", "aceptar", "denegar"):
        raise ValueError("Modo inválido")
    desconocido = usuario["id"] == DESCONOCIDO_ID

    if modo == "auto":
        if desconocido:
            resultado, sim, motivo = "denegado", rng.uniform(0.02, 0.30), "Rostro no reconocido"
        elif usuario.get("estado") != "activo":
            resultado, sim, motivo = "denegado", rng.uniform(0.50, 0.90), "Usuario dado de baja"
        elif not usuario.get("rostro"):
            resultado, sim, motivo = "denegado", rng.uniform(0.02, 0.30), "Rostro no registrado en el sistema"
        else:
            sim = round(rng.uniform(0.25, 0.92), 3)  # se decide con el mismo valor que se muestra
            if sim >= UMBRAL:
                resultado, motivo = "aceptado", "Rostro reconocido"
            else:
                resultado, motivo = "denegado", "Similitud por debajo del umbral (mala iluminación o ángulo)"
    elif modo == "aceptar":
        resultado, sim, motivo = "aceptado", rng.uniform(0.45, 0.92), "Aceptado manualmente (prueba)"
    else:
        resultado, sim, motivo = "denegado", rng.uniform(0.02, 0.33), "Denegado manualmente (prueba)"

    if motivo_manual.strip():
        motivo = motivo_manual.strip()
    return _intento(usuario, lab, resultado, modo, sim, motivo, fecha)


def simular_rafaga(usuarios: list, labs: list, cantidad: int, porcentaje_aceptados: float,
                   dias: int = 7, rng: random.Random = random) -> list:
    """Genera N intentos repartidos en los últimos días (7:00 a 21:00), con el % de aceptados indicado."""
    cantidad = max(0, int(cantidad))
    n_aceptados = round(cantidad * max(0.0, min(100.0, porcentaje_aceptados)) / 100)
    resultados = ["aceptar"] * n_aceptados + ["denegar"] * (cantidad - n_aceptados)
    rng.shuffle(resultados)
    ahora = datetime.now()
    motivos_rechazo = ["Rostro no reconocido", "Fuera de horario autorizado",
                       "Similitud por debajo del umbral", "Rostro no registrado en el sistema"]
    intentos = []
    for modo in resultados:
        fecha = (ahora - timedelta(days=rng.randint(0, max(0, dias - 1)))).replace(
            hour=rng.randint(7, 20), minute=rng.randint(0, 59), second=rng.randint(0, 59))
        if fecha > ahora:
            fecha -= timedelta(days=1)
        motivo = "Rostro reconocido" if modo == "aceptar" else rng.choice(motivos_rechazo)
        intentos.append(simular_intento(rng.choice(usuarios), rng.choice(labs), modo, motivo, fecha, rng))
    return intentos


def calcular_metricas(intentos: list) -> dict:
    total = len(intentos)
    aceptados = sum(1 for i in intentos if i["resultado"] == "aceptado")
    por_lab, por_hora, motivos, por_usuario = {}, [0] * 24, {}, {}
    for i in intentos:
        lab = por_lab.setdefault(i["laboratorio_nombre"] or i["laboratorio_id"], {"aceptado": 0, "denegado": 0})
        lab[i["resultado"]] += 1
        try:
            por_hora[int(i["fecha_hora"][11:13])] += 1
        except (ValueError, TypeError, IndexError):
            pass
        if i["resultado"] == "denegado":
            motivos[i["motivo"] or "Sin motivo"] = motivos.get(i["motivo"] or "Sin motivo", 0) + 1
        u = por_usuario.setdefault(i["usuario_nombre"], {"aceptado": 0, "denegado": 0})
        u[i["resultado"]] += 1
    sims = [i["similitud"] for i in intentos if i.get("similitud") is not None and i["resultado"] == "aceptado"]
    return {
        "total": total,
        "aceptados": aceptados,
        "denegados": total - aceptados,
        "efectividad": round(100 * aceptados / total, 1) if total else 0.0,
        "similitud_promedio": round(sum(sims) / len(sims), 3) if sims else None,
        "por_lab": dict(sorted(por_lab.items(), key=lambda kv: -(kv[1]["aceptado"] + kv[1]["denegado"]))),
        "por_hora": por_hora,
        "motivos": dict(sorted(motivos.items(), key=lambda kv: -kv[1])),
        "por_usuario": dict(sorted(por_usuario.items(), key=lambda kv: -(kv[1]["aceptado"] + kv[1]["denegado"]))),
    }


# =============================================================
# ESCÁNER DE ROSTRO (cámara + YuNet/SFace)
# =============================================================
class EscanerRostro:
    """
    Muestra la cámara en un Label de tkinter, espera a que haya un rostro estable,
    extrae 3 vectores, los promedia y busca el usuario registrado más parecido.
    Los fotogramas solo viven en memoria (RF-07).
    """
    FOTOGRAMAS_ESTABLES = 4   # detecciones seguidas antes de capturar
    MUESTRAS = 3              # vectores que se promedian
    TIEMPO_LIMITE_S = 20
    ANCHO_VISTA = 400

    def __init__(self, root, vista, al_estado, al_terminar, indice_camara=0):
        self.root, self.vista = root, vista
        self.al_estado, self.al_terminar = al_estado, al_terminar
        self.indice = indice_camara
        self.motor = None
        self.cap = None
        self.activo = False
        self._foto = None

    def preparar_motor(self):
        if FaceEngine is None:
            raise FaceEngineUnavailable("Falta OpenCV/numpy. Ejecute: python -m pip install -r requirements.txt")
        if self.motor is None:
            self.motor = FaceEngine()
        return self.motor

    def iniciar(self):
        import cv2
        self.preparar_motor()
        self.cap = cv2.VideoCapture(self.indice, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(self.indice)
        if not self.cap or not self.cap.isOpened():
            self.cap = None
            raise RuntimeError("No se pudo abrir la cámara. ¿Está conectada o la usa otro programa?")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.activo = True
        self.estables = 0
        self.vectores, self.puntajes = [], []
        self.n = 0
        self.limite = datetime.now() + timedelta(seconds=self.TIEMPO_LIMITE_S)
        self.al_estado("Mire de frente a la cámara…")
        self.root.after(10, self._tick)

    def cancelar(self, motivo="Escaneo cancelado."):
        if self.activo:
            self._cerrar()
            self.al_terminar(None, motivo)

    def _cerrar(self):
        self.activo = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.vectores, self.puntajes = [], []

    def _mostrar(self, frame, caja, color):
        import cv2
        vista = cv2.flip(frame, 1)  # espejo, más natural para quien se ve
        h, w = vista.shape[:2]
        if caja is not None:
            x, y, bw, bh = [int(v) for v in caja[:4]]
            x = w - x - bw
            cv2.rectangle(vista, (x, y), (x + bw, y + bh), color, 3)
        escala = self.ANCHO_VISTA / w
        vista = cv2.resize(vista, (self.ANCHO_VISTA, int(h * escala)))
        ok, png = cv2.imencode(".png", vista)
        del vista
        if ok:
            import tkinter as tk
            self._foto = tk.PhotoImage(data=base64.b64encode(png.tobytes()))
            self.vista.config(image=self._foto, text="")

    def _tick(self):
        if not self.activo:
            return
        if datetime.now() > self.limite:
            self._cerrar()
            self.al_terminar(None, "No se detectó un rostro a tiempo. Acérquese y mire de frente a la cámara.")
            return
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self.root.after(30, self._tick)
            return
        self.n += 1
        caja = None
        if self.n % 2 == 0:  # detectar cada 2 fotogramas
            caja = self.motor.detect_largest_face(frame)
            if caja is None:
                self.estables = 0
                self.vectores, self.puntajes = [], []
                self.al_estado("Buscando rostro… mire de frente a la cámara.")
            else:
                self.estables += 1
                if self.estables >= self.FOTOGRAMAS_ESTABLES:
                    vec, score = self.motor.extract_vector(frame)
                    if vec:
                        self.vectores.append(vec)
                        self.puntajes.append(score)
                    self.al_estado(f"Rostro detectado… analizando ({len(self.vectores)}/{self.MUESTRAS})")
                else:
                    self.al_estado("Rostro detectado… quédese quieto.")
        self._mostrar(frame, caja, (5, 150, 105) if caja is not None else (148, 163, 184))
        del frame  # RF-07
        if len(self.vectores) >= self.MUESTRAS:
            self._finalizar()
            return
        self.root.after(30, self._tick)

    def _finalizar(self):
        import numpy as np
        m = np.array(self.vectores, dtype=np.float32)
        m /= np.linalg.norm(m, axis=1, keepdims=True)
        vector = m.mean(axis=0)
        vector = (vector / np.linalg.norm(vector)).astype(float).tolist()
        calidad = sum(self.puntajes) / len(self.puntajes)
        self._cerrar()
        registrados = cargar_vectores()
        usuario, similitud = VectorIndex(registrados).best_match(vector)
        del vector  # RF-07
        self.al_terminar({"usuario": usuario, "similitud": similitud, "calidad": calidad,
                          "registrados": len(registrados)}, None)


# =============================================================
# INTERFAZ (tkinter)
# =============================================================
VERDE, ROJO, OSCURO, GRIS, FONDO, BLANCO = "#059669", "#dc2626", "#0f172a", "#64748b", "#f1f5f9", "#ffffff"


def ejecutar_app():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    usuarios, labs, con_bd = cargar_catalogos()
    registro = RegistroPruebas()

    root = tk.Tk()
    root.title("NeoAccess • Prueba de Acceso (simulador independiente)")
    root.geometry("1320x860")
    root.minsize(1150, 760)
    root.configure(bg=FONDO)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background=FONDO)
    style.configure("Card.TFrame", background=BLANCO)
    style.configure("TLabel", background=FONDO, foreground=OSCURO, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=BLANCO, foreground=OSCURO, font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=BLANCO, foreground=GRIS, font=("Segoe UI", 9))
    style.configure("H.TLabel", background=BLANCO, foreground=OSCURO, font=("Segoe UI", 11, "bold"))
    style.configure("TRadiobutton", background=BLANCO, font=("Segoe UI", 10))
    style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=8)
    style.configure("TNotebook", background=BLANCO)
    style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(12, 5))
    style.configure("Treeview", font=("Segoe UI", 9), rowheight=22)
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # ---------- Encabezado ----------
    header = tk.Frame(root, bg=OSCURO)
    header.pack(fill="x")
    tk.Label(header, text="NeoAccess • Prueba de Acceso", bg=OSCURO, fg="white",
             font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)
    origen = "datos de database/neoaccess.db (solo lectura)" if con_bd else "datos de demostración (no se encontró la base principal)"
    tk.Label(header, text=f"Simulador independiente • {origen} • las pruebas se guardan en prueba_acceso.db",
             bg=OSCURO, fg="#94a3b8", font=("Segoe UI", 9)).pack(side="left", padx=6)

    cuerpo = ttk.Frame(root)
    cuerpo.pack(fill="both", expand=True, padx=12, pady=12)
    cuerpo.columnconfigure(1, weight=1)
    cuerpo.rowconfigure(0, weight=1)

    # ---------- Panel izquierdo (pestañas) ----------
    izq = ttk.Frame(cuerpo, style="Card.TFrame", padding=10)
    izq.grid(row=0, column=0, sticky="ns", padx=(0, 12))
    pestanas = ttk.Notebook(izq)
    pestanas.pack(fill="both", expand=True)
    tab_esc = ttk.Frame(pestanas, style="Card.TFrame", padding=10)
    tab_mas = ttk.Frame(pestanas, style="Card.TFrame", padding=10)
    pestanas.add(tab_esc, text="Escanear rostro")
    pestanas.add(tab_mas, text="Simulación masiva")

    # ===== Pestaña 1: acceso con escaneo de rostro =====
    ttk.Label(tab_esc, text="Laboratorio / puerta", style="Muted.TLabel").pack(anchor="w")
    cb_lab = ttk.Combobox(tab_esc, values=[f"{l['id']} — {l['nombre']}" for l in labs], state="readonly", width=50)
    cb_lab.current(0)
    cb_lab.pack(anchor="w")

    ttk.Label(tab_esc, text="Resultado del acceso", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
    modo_var = tk.StringVar(value="auto")
    for valor, texto in (("auto", "Automático (decide el reconocimiento facial)"),
                         ("aceptar", "Forzar ACEPTADO"),
                         ("denegar", "Forzar DENEGADO")):
        ttk.Radiobutton(tab_esc, text=texto, value=valor, variable=modo_var).pack(anchor="w")

    ttk.Label(tab_esc, text="Motivo (opcional)", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
    motivo_var = tk.StringVar()
    ttk.Entry(tab_esc, textvariable=motivo_var, width=53).pack(anchor="w")

    vista = tk.Label(tab_esc, bg="#0f172a", fg="#94a3b8", width=400, height=300, image="",
                     text="📷\n\nPulse «Escanear rostro» y mire a la cámara",
                     font=("Segoe UI", 10), compound="center")
    # width/height en píxeles al usar una imagen vacía:
    vacia = tk.PhotoImage(width=400, height=300)
    vista.config(image=vacia)
    vista.image_vacia = vacia
    vista.pack(pady=(10, 6))

    estado_lbl = tk.Label(tab_esc, text="", bg=BLANCO, fg=GRIS, font=("Segoe UI", 9))
    estado_lbl.pack(anchor="w")

    fila_btn = ttk.Frame(tab_esc, style="Card.TFrame")
    fila_btn.pack(fill="x", pady=(4, 6))
    btn_escanear = ttk.Button(fila_btn, text="📷  Escanear rostro", style="Big.TButton")
    btn_escanear.pack(side="left", expand=True, fill="x")
    btn_cancelar = ttk.Button(fila_btn, text="Cancelar", state="disabled")
    btn_cancelar.pack(side="left", padx=(8, 0))

    resultado_lbl = tk.Label(tab_esc, text="Esperando escaneo…", bg="#e2e8f0", fg=OSCURO,
                             font=("Segoe UI", 13, "bold"), height=2)
    resultado_lbl.pack(fill="x")
    detalle_lbl = tk.Label(tab_esc, text="", bg=BLANCO, fg=GRIS, font=("Segoe UI", 9), wraplength=400, justify="left")
    detalle_lbl.pack(anchor="w", pady=(4, 0))

    # Respaldo sin cámara: elegir la persona a mano
    sin_cam = ttk.Frame(tab_esc, style="Card.TFrame")
    ttk.Label(sin_cam, text="Sin cámara: elija quién está en la puerta", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
    usuarios_ui = usuarios + [DESCONOCIDO]
    cb_usuario = ttk.Combobox(sin_cam, state="readonly", width=50, values=[
        u["nombre"] if u["id"] == DESCONOCIDO_ID else
        f"{u['matricula']} — {u['nombre']} ({u['tipo'].replace('personal_', '')}{'' if u['rostro'] else ', sin rostro'})"
        for u in usuarios_ui])
    cb_usuario.current(0)
    cb_usuario.pack(anchor="w")
    ttk.Button(sin_cam, text="Simular sin cámara", command=lambda: simular_sin_camara()).pack(fill="x", pady=(6, 0))

    # ===== Pestaña 2: simulación masiva =====
    ttk.Label(tab_mas, text="Genera muchos accesos de golpe (sin cámara)", style="H.TLabel").pack(anchor="w")
    fila = ttk.Frame(tab_mas, style="Card.TFrame")
    fila.pack(anchor="w", pady=(10, 0), fill="x")
    ttk.Label(fila, text="Cantidad:", style="Card.TLabel").pack(side="left")
    cant_var = tk.IntVar(value=50)
    ttk.Spinbox(fila, from_=1, to=5000, textvariable=cant_var, width=7).pack(side="left", padx=(6, 0))
    pct_var = tk.IntVar(value=80)
    pct_lbl = ttk.Label(tab_mas, text="Aceptados: 80 %", style="Card.TLabel")
    pct_lbl.pack(anchor="w", pady=(10, 0))
    escala = ttk.Scale(tab_mas, from_=0, to=100, orient="horizontal", length=380,
                       command=lambda v: (pct_var.set(int(float(v))),
                                          pct_lbl.config(text=f"Aceptados: {int(float(v))} %")))
    escala.set(80)
    escala.pack(anchor="w")
    ttk.Label(tab_mas, text="Se reparten en los últimos 7 días, de 7:00 a 21:00.", style="Muted.TLabel").pack(anchor="w")
    ttk.Button(tab_mas, text="Generar accesos", command=lambda: simular_masivo()).pack(fill="x", pady=(10, 0))
    ttk.Separator(tab_mas).pack(fill="x", pady=14)
    ttk.Button(tab_mas, text="Exportar CSV", command=lambda: exportar()).pack(fill="x")
    ttk.Button(tab_mas, text="Borrar pruebas", command=lambda: borrar()).pack(fill="x", pady=(8, 0))

    # ---------- Panel derecho: métricas ----------
    der = ttk.Frame(cuerpo)
    der.grid(row=0, column=1, sticky="nsew")
    der.columnconfigure((0, 1), weight=1)
    der.rowconfigure(2, weight=1)

    kpis = ttk.Frame(der)
    kpis.grid(row=0, column=0, columnspan=2, sticky="ew")
    kpi_vals = {}
    for i, (clave, titulo, color) in enumerate((("total", "Total de intentos", OSCURO),
                                                ("aceptados", "Aceptados", VERDE),
                                                ("denegados", "Denegados", ROJO),
                                                ("efectividad", "Efectividad", OSCURO),
                                                ("similitud", "Similitud prom. (aceptados)", OSCURO))):
        kpis.columnconfigure(i, weight=1)
        card = ttk.Frame(kpis, style="Card.TFrame", padding=(12, 8))
        card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
        ttk.Label(card, text=titulo.upper(), style="Muted.TLabel").pack(anchor="w")
        lbl = tk.Label(card, text="0", bg=BLANCO, fg=color, font=("Segoe UI", 20, "bold"))
        lbl.pack(anchor="w")
        kpi_vals[clave] = lbl

    card_lab = ttk.Frame(der, style="Card.TFrame", padding=10)
    card_lab.grid(row=1, column=0, sticky="nsew", pady=10, padx=(0, 5))
    ttk.Label(card_lab, text="Accesos por laboratorio", style="H.TLabel").pack(anchor="w")
    canvas_lab = tk.Canvas(card_lab, bg=BLANCO, height=230, highlightthickness=0)
    canvas_lab.pack(fill="both", expand=True)

    card_hora = ttk.Frame(der, style="Card.TFrame", padding=10)
    card_hora.grid(row=1, column=1, sticky="nsew", pady=10, padx=(5, 0))
    ttk.Label(card_hora, text="Intentos por hora del día", style="H.TLabel").pack(anchor="w")
    canvas_hora = tk.Canvas(card_hora, bg=BLANCO, height=230, highlightthickness=0)
    canvas_hora.pack(fill="both", expand=True)

    card_tabla = ttk.Frame(der, style="Card.TFrame", padding=10)
    card_tabla.grid(row=2, column=0, sticky="nsew", padx=(0, 5))
    ttk.Label(card_tabla, text="Últimos intentos", style="H.TLabel").pack(anchor="w")
    cols = ("fecha", "usuario", "lab", "resultado", "motivo")
    tabla = ttk.Treeview(card_tabla, columns=cols, show="headings", height=8)
    for c, t, w in zip(cols, ("Fecha y hora", "Usuario", "Laboratorio", "Resultado", "Motivo"), (130, 170, 110, 80, 200)):
        tabla.heading(c, text=t)
        tabla.column(c, width=w, anchor="w")
    tabla.tag_configure("aceptado", foreground=VERDE)
    tabla.tag_configure("denegado", foreground=ROJO)
    tabla.pack(fill="both", expand=True)

    card_mot = ttk.Frame(der, style="Card.TFrame", padding=10)
    card_mot.grid(row=2, column=1, sticky="nsew", padx=(5, 0))
    ttk.Label(card_mot, text="Motivos de rechazo y usuarios", style="H.TLabel").pack(anchor="w")
    texto_mot = tk.Text(card_mot, height=8, bg=BLANCO, relief="flat", font=("Segoe UI", 9), wrap="word")
    texto_mot.pack(fill="both", expand=True)
    texto_mot.tag_configure("titulo", font=("Segoe UI", 9, "bold"), foreground=OSCURO)
    texto_mot.tag_configure("rojo", foreground=ROJO)

    # ---------- Gráficas ----------
    def dibujar_labs(m):
        canvas_lab.delete("all")
        w = max(canvas_lab.winfo_width(), 300)
        datos = list(m["por_lab"].items())[:7]
        if not datos:
            canvas_lab.create_text(w / 2, 100, text="Sin datos todavía", fill=GRIS, font=("Segoe UI", 10))
            return
        maximo = max(v["aceptado"] + v["denegado"] for _, v in datos)
        izq_txt, ancho = 170, w - 220
        for i, (nombre, v) in enumerate(datos):
            y = 12 + i * 29
            nombre_corto = nombre if len(nombre) <= 26 else nombre[:25] + "…"
            canvas_lab.create_text(izq_txt - 8, y + 9, text=nombre_corto, anchor="e", fill=OSCURO, font=("Segoe UI", 8))
            wa = ancho * v["aceptado"] / maximo
            wd = ancho * v["denegado"] / maximo
            canvas_lab.create_rectangle(izq_txt, y, izq_txt + wa, y + 18, fill=VERDE, width=0)
            canvas_lab.create_rectangle(izq_txt + wa, y, izq_txt + wa + wd, y + 18, fill=ROJO, width=0)
            canvas_lab.create_text(izq_txt + wa + wd + 6, y + 9, anchor="w", fill=GRIS, font=("Segoe UI", 8),
                                   text=f"{v['aceptado']} / {v['denegado']}")
        y = 12 + len(datos) * 29 + 4
        canvas_lab.create_rectangle(izq_txt, y, izq_txt + 10, y + 10, fill=VERDE, width=0)
        canvas_lab.create_text(izq_txt + 14, y + 5, anchor="w", text="Aceptados", fill=GRIS, font=("Segoe UI", 8))
        canvas_lab.create_rectangle(izq_txt + 90, y, izq_txt + 100, y + 10, fill=ROJO, width=0)
        canvas_lab.create_text(izq_txt + 104, y + 5, anchor="w", text="Denegados", fill=GRIS, font=("Segoe UI", 8))

    def dibujar_horas(m):
        canvas_hora.delete("all")
        w = max(canvas_hora.winfo_width(), 300)
        h = max(canvas_hora.winfo_height(), 200)
        datos = m["por_hora"]
        if not any(datos):
            canvas_hora.create_text(w / 2, 100, text="Sin datos todavía", fill=GRIS, font=("Segoe UI", 10))
            return
        maximo = max(datos)
        base, alto = h - 22, h - 40
        paso = (w - 20) / 24
        for hora, n in enumerate(datos):
            x = 10 + hora * paso
            bh = alto * n / maximo if maximo else 0
            canvas_hora.create_rectangle(x + 2, base - bh, x + paso - 2, base, fill=OSCURO if n else "#e2e8f0", width=0)
            if n == maximo:
                canvas_hora.create_text(x + paso / 2, base - bh - 8, text=str(n), fill=OSCURO, font=("Segoe UI", 8, "bold"))
            if hora % 3 == 0:
                canvas_hora.create_text(x + paso / 2, base + 10, text=f"{hora}h", fill=GRIS, font=("Segoe UI", 8))

    ultimas = {"m": calcular_metricas([])}

    def redibujar(_evento=None):
        dibujar_labs(ultimas["m"])
        dibujar_horas(ultimas["m"])

    def refrescar():
        intentos = registro.todos()
        m = calcular_metricas(intentos)
        ultimas["m"] = m
        kpi_vals["total"].config(text=str(m["total"]))
        kpi_vals["aceptados"].config(text=str(m["aceptados"]))
        kpi_vals["denegados"].config(text=str(m["denegados"]))
        kpi_vals["efectividad"].config(text=f"{m['efectividad']} %")
        kpi_vals["similitud"].config(text="—" if m["similitud_promedio"] is None else f"{m['similitud_promedio']:.3f}")
        redibujar()
        tabla.delete(*tabla.get_children())
        for i in intentos[:200]:
            tabla.insert("", "end", tags=(i["resultado"],), values=(
                i["fecha_hora"], i["usuario_nombre"], i["laboratorio_id"],
                "ACEPTADO" if i["resultado"] == "aceptado" else "DENEGADO", i["motivo"]))
        texto_mot.config(state="normal")
        texto_mot.delete("1.0", "end")
        texto_mot.insert("end", "Motivos de rechazo\n", "titulo")
        if not m["motivos"]:
            texto_mot.insert("end", "  (ninguno)\n")
        for motivo, n in list(m["motivos"].items())[:6]:
            texto_mot.insert("end", f"  {n:>4}  ", "rojo")
            texto_mot.insert("end", f"{motivo}\n")
        texto_mot.insert("end", "\nUsuarios con más intentos (aceptados / denegados)\n", "titulo")
        for nombre, v in list(m["por_usuario"].items())[:6]:
            texto_mot.insert("end", f"  {v['aceptado']:>3} / {v['denegado']:<3} {nombre}\n")
        texto_mot.config(state="disabled")

    def mostrar_resultado(intento, lab, extra=""):
        registro.guardar(intento)
        ok = intento["resultado"] == "aceptado"
        resultado_lbl.config(text="✔  ACCESO ACEPTADO — puerta abierta" if ok else "✖  ACCESO DENEGADO",
                             bg=VERDE if ok else ROJO, fg="white")
        sim = "—" if intento["similitud"] is None else f"{intento['similitud']:.3f}"
        detalle_lbl.config(text=f"{intento['usuario_nombre']} → {lab['nombre']}\n"
                                f"Similitud: {sim} (umbral {UMBRAL}) • {intento['motivo']}{extra}")
        refrescar()

    # ---------- Escaneo ----------
    def al_estado(texto):
        estado_lbl.config(text=texto)

    def al_terminar(res, error):
        btn_escanear.config(state="normal")
        btn_cancelar.config(state="disabled")
        cb_lab.config(state="readonly")
        vista.config(image=vista.image_vacia, text="📷\n\nPulse «Escanear rostro» y mire a la cámara")
        if error:
            estado_lbl.config(text=error)
            resultado_lbl.config(text="Escaneo sin resultado", bg="#e2e8f0", fg=OSCURO)
            detalle_lbl.config(text="")
            return
        lab = labs[cb_lab.current()]
        intento = resolver_escaneo(res["usuario"], res["similitud"], lab, modo_var.get(), motivo_var.get())
        if res["usuario"] is not None and res["similitud"] < UMBRAL:
            parecido = f"\nMás parecido: {res['usuario']['nombre']} ({res['similitud']:.3f}), no alcanza el umbral."
        else:
            parecido = ""
        if res["registrados"] == 0:
            parecido += "\nNo hay rostros registrados: registre uno en el Dashboard (Alumnos → Registrar rostro)."
        estado_lbl.config(text=f"Escaneo listo (calidad de detección {res['calidad']:.2f}). La imagen no se guardó.")
        mostrar_resultado(intento, lab, parecido)

    escaner = EscanerRostro(root, vista, al_estado, al_terminar)

    def escanear():
        try:
            escaner.iniciar()
        except Exception as e:
            estado_lbl.config(text=str(e))
            if not sin_cam.winfo_ismapped():
                sin_cam.pack(fill="x")
            messagebox.showwarning("Escaneo de rostro",
                                   f"{e}\n\nPuede simular sin cámara eligiendo a la persona en la lista de abajo.")
            return
        btn_escanear.config(state="disabled")
        btn_cancelar.config(state="normal")
        cb_lab.config(state="disabled")
        resultado_lbl.config(text="Escaneando rostro…", bg="#e2e8f0", fg=OSCURO)
        detalle_lbl.config(text="")

    btn_escanear.config(command=escanear)
    btn_cancelar.config(command=lambda: escaner.cancelar())

    def simular_sin_camara():
        lab = labs[cb_lab.current()]
        intento = simular_intento(usuarios_ui[cb_usuario.current()], lab, modo_var.get(), motivo_var.get())
        intento["modo"] = "sin-camara-" + intento["modo"]
        mostrar_resultado(intento, lab, "\n(Simulado sin cámara)")

    # ---------- Otras acciones ----------
    def simular_masivo():
        try:
            n = int(cant_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Prueba de acceso", "Escriba una cantidad válida.")
            return
        if not 1 <= n <= 5000:
            messagebox.showerror("Prueba de acceso", "La cantidad debe estar entre 1 y 5000.")
            return
        registro.guardar_varios(simular_rafaga(usuarios, labs, n, pct_var.get()))
        refrescar()

    def exportar():
        destino = filedialog.asksaveasfilename(title="Exportar pruebas", defaultextension=".csv",
                                               initialfile="prueba_acceso.csv", filetypes=[("CSV", "*.csv")])
        if destino:
            n = registro.exportar_csv(destino)
            messagebox.showinfo("Prueba de acceso", f"Se exportaron {n} intentos a:\n{destino}")

    def borrar():
        if messagebox.askyesno("Prueba de acceso", "¿Borrar todos los intentos simulados?\n(No afecta la base de datos principal.)"):
            registro.borrar_todo()
            resultado_lbl.config(text="Esperando escaneo…", bg="#e2e8f0", fg=OSCURO)
            detalle_lbl.config(text="")
            refrescar()

    def al_cerrar():
        escaner.activo = False
        if escaner.cap is not None:
            escaner.cap.release()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", al_cerrar)
    canvas_lab.bind("<Configure>", redibujar)
    canvas_hora.bind("<Configure>", redibujar)
    root.after(100, refrescar)
    root.mainloop()


if __name__ == "__main__":
    ejecutar_app()
