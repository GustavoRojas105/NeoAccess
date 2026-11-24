"""
NeoAccess - Prueba de Acceso (programa independiente)
Ubicación: prueba_acceso/prueba_acceso.py

Simula intentos de acceso a los laboratorios y muestra métricas.
Permite decidir el resultado de cada intento: automático (reglas del sistema),
forzar ACEPTADO o forzar DENEGADO.

- Lee usuarios y laboratorios de database/neoaccess.db en SOLO LECTURA.
- Guarda sus propios registros en prueba_acceso/prueba_acceso.db, así las
  pruebas NO se mezclan con las métricas reales del Dashboard.
- No forma parte de la página principal del proyecto.

Ejecutar:  python prueba_acceso\\prueba_acceso.py   (o doble clic en prueba_acceso.bat)
"""

import csv
import os
import random
import sqlite3
from datetime import datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
DB_PRINCIPAL = os.path.join(AQUI, "..", "database", "neoaccess.db")
DB_PRUEBAS = os.path.join(AQUI, "prueba_acceso.db")

DESCONOCIDO_ID = "__DESCONOCIDO__"
UMBRAL = 0.363  # mismo umbral de similitud coseno que usan las puertas

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
def cargar_catalogos(db_path: str = DB_PRINCIPAL):
    """Usuarios y laboratorios desde la base principal (solo lectura)."""
    if not os.path.exists(db_path):
        return USUARIOS_DEMO, LABS_DEMO, False
    uri = "file:" + os.path.abspath(db_path).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
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


class RegistroPruebas:
    """Base de datos propia de las simulaciones."""

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
        conn = self._conn()
        conn.execute("""
        INSERT INTO intentos (fecha_hora, usuario_id, usuario_nombre, tipo, laboratorio_id,
                              laboratorio_nombre, resultado, modo, similitud, motivo)
        VALUES (:fecha_hora, :usuario_id, :usuario_nombre, :tipo, :laboratorio_id,
                :laboratorio_nombre, :resultado, :modo, :similitud, :motivo)""", intento)
        conn.commit()
        conn.close()

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
        campos = ["fecha_hora", "usuario_id", "usuario_nombre", "tipo", "laboratorio_id",
                  "laboratorio_nombre", "resultado", "modo", "similitud", "motivo"]
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        return len(filas)


# =============================================================
# SIMULACIÓN
# =============================================================
def simular_intento(usuario: dict, lab: dict, modo: str, motivo_manual: str = "",
                    fecha: datetime = None, rng: random.Random = random) -> dict:
    """
    modo: 'auto'     -> decide con las reglas del sistema
          'aceptar'  -> fuerza ACEPTADO
          'denegar'  -> fuerza DENEGADO
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

    return {
        "fecha_hora": (fecha or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "usuario_id": None if desconocido else usuario["id"],
        "usuario_nombre": usuario["nombre"],
        "tipo": usuario.get("tipo"),
        "laboratorio_id": lab["id"],
        "laboratorio_nombre": lab["nombre"],
        "resultado": resultado,
        "modo": modo,
        "similitud": round(sim, 3),
        "motivo": motivo,
    }


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
# INTERFAZ (tkinter)
# =============================================================
VERDE, ROJO, OSCURO, GRIS, FONDO, BLANCO = "#059669", "#dc2626", "#0f172a", "#64748b", "#f1f5f9", "#ffffff"


def ejecutar_app():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    usuarios, labs, con_bd = cargar_catalogos()
    usuarios_ui = usuarios + [{"id": DESCONOCIDO_ID, "nombre": "— Persona desconocida —", "matricula": "",
                               "tipo": "desconocido", "estado": "activo", "rostro": False}]
    registro = RegistroPruebas()

    root = tk.Tk()
    root.title("NeoAccess • Prueba de Acceso (simulador independiente)")
    root.geometry("1280x800")
    root.minsize(1100, 700)
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
    style.configure("Treeview", font=("Segoe UI", 9), rowheight=22)
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    # ---------- Encabezado ----------
    header = tk.Frame(root, bg=OSCURO)
    header.pack(fill="x")
    tk.Label(header, text="NeoAccess • Prueba de Acceso", bg=OSCURO, fg="white",
             font=("Segoe UI", 15, "bold")).pack(side="left", padx=16, pady=10)
    origen = "usuarios y laboratorios de database/neoaccess.db (solo lectura)" if con_bd else "datos de demostración (no se encontró la base principal)"
    tk.Label(header, text=f"Simulador independiente • {origen} • las pruebas se guardan en prueba_acceso.db",
             bg=OSCURO, fg="#94a3b8", font=("Segoe UI", 9)).pack(side="left", padx=6)

    cuerpo = ttk.Frame(root)
    cuerpo.pack(fill="both", expand=True, padx=12, pady=12)
    cuerpo.columnconfigure(1, weight=1)
    cuerpo.rowconfigure(0, weight=1)

    # ---------- Panel izquierdo: simulación ----------
    izq = ttk.Frame(cuerpo, style="Card.TFrame", padding=14)
    izq.grid(row=0, column=0, sticky="ns", padx=(0, 12))

    ttk.Label(izq, text="Simular un acceso", style="H.TLabel").pack(anchor="w")
    ttk.Label(izq, text="Usuario frente a la puerta", style="Muted.TLabel").pack(anchor="w", pady=(10, 2))
    etiquetas_usuario = [
        f"{u['nombre']}" if u["id"] == DESCONOCIDO_ID else
        f"{u['matricula']} — {u['nombre']} ({u['tipo'].replace('personal_', '')}{'' if u['rostro'] else ', sin rostro'})"
        for u in usuarios_ui]
    cb_usuario = ttk.Combobox(izq, values=etiquetas_usuario, state="readonly", width=46)
    cb_usuario.current(0)
    cb_usuario.pack(anchor="w")

    ttk.Label(izq, text="Laboratorio / puerta", style="Muted.TLabel").pack(anchor="w", pady=(10, 2))
    cb_lab = ttk.Combobox(izq, values=[f"{l['id']} — {l['nombre']}" for l in labs], state="readonly", width=46)
    cb_lab.current(0)
    cb_lab.pack(anchor="w")

    ttk.Label(izq, text="Resultado del acceso", style="Muted.TLabel").pack(anchor="w", pady=(12, 2))
    modo_var = tk.StringVar(value="auto")
    for valor, texto in (("auto", "Automático (reglas del sistema)"),
                         ("aceptar", "Forzar ACEPTADO"),
                         ("denegar", "Forzar DENEGADO")):
        ttk.Radiobutton(izq, text=texto, value=valor, variable=modo_var).pack(anchor="w")

    ttk.Label(izq, text="Motivo (opcional)", style="Muted.TLabel").pack(anchor="w", pady=(10, 2))
    motivo_var = tk.StringVar()
    ttk.Entry(izq, textvariable=motivo_var, width=49).pack(anchor="w")

    ttk.Button(izq, text="▶  Simular acceso", style="Big.TButton",
               command=lambda: simular_uno()).pack(fill="x", pady=(14, 8))

    resultado_lbl = tk.Label(izq, text="Esperando prueba…", bg="#e2e8f0", fg=OSCURO,
                             font=("Segoe UI", 14, "bold"), height=2)
    resultado_lbl.pack(fill="x")
    detalle_lbl = tk.Label(izq, text="", bg=BLANCO, fg=GRIS, font=("Segoe UI", 9), wraplength=360, justify="left")
    detalle_lbl.pack(anchor="w", pady=(4, 0))

    ttk.Separator(izq).pack(fill="x", pady=12)
    ttk.Label(izq, text="Simulación masiva", style="H.TLabel").pack(anchor="w")
    fila = ttk.Frame(izq, style="Card.TFrame")
    fila.pack(anchor="w", pady=(8, 0), fill="x")
    ttk.Label(fila, text="Cantidad:", style="Card.TLabel").pack(side="left")
    cant_var = tk.IntVar(value=50)
    ttk.Spinbox(fila, from_=1, to=5000, textvariable=cant_var, width=7).pack(side="left", padx=(6, 0))
    pct_var = tk.IntVar(value=80)
    pct_lbl = ttk.Label(izq, text="Aceptados: 80 %", style="Card.TLabel")
    pct_lbl.pack(anchor="w", pady=(8, 0))
    escala = ttk.Scale(izq, from_=0, to=100, orient="horizontal", length=350,
                       command=lambda v: (pct_var.set(int(float(v))),
                                          pct_lbl.config(text=f"Aceptados: {int(float(v))} %")))
    escala.set(80)
    escala.pack(anchor="w")
    ttk.Label(izq, text="Se reparten en los últimos 7 días, de 7:00 a 21:00.", style="Muted.TLabel").pack(anchor="w")
    ttk.Button(izq, text="Generar accesos", command=lambda: simular_masivo()).pack(fill="x", pady=(8, 0))

    ttk.Separator(izq).pack(fill="x", pady=12)
    botones = ttk.Frame(izq, style="Card.TFrame")
    botones.pack(fill="x")
    ttk.Button(botones, text="Exportar CSV", command=lambda: exportar()).pack(side="left", expand=True, fill="x")
    ttk.Button(botones, text="Borrar pruebas", command=lambda: borrar()).pack(side="left", expand=True, fill="x", padx=(8, 0))

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
    canvas_lab = tk.Canvas(card_lab, bg=BLANCO, height=220, highlightthickness=0)
    canvas_lab.pack(fill="both", expand=True)

    card_hora = ttk.Frame(der, style="Card.TFrame", padding=10)
    card_hora.grid(row=1, column=1, sticky="nsew", pady=10, padx=(5, 0))
    ttk.Label(card_hora, text="Intentos por hora del día", style="H.TLabel").pack(anchor="w")
    canvas_hora = tk.Canvas(card_hora, bg=BLANCO, height=220, highlightthickness=0)
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

    # ---------- Dibujo de gráficas ----------
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
        dibujar_labs(m)
        dibujar_horas(m)
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

    # ---------- Acciones ----------
    def simular_uno():
        usuario = usuarios_ui[cb_usuario.current()]
        lab = labs[cb_lab.current()]
        intento = simular_intento(usuario, lab, modo_var.get(), motivo_var.get())
        registro.guardar(intento)
        ok = intento["resultado"] == "aceptado"
        resultado_lbl.config(text="✔  ACCESO ACEPTADO — puerta abierta" if ok else "✖  ACCESO DENEGADO",
                             bg=VERDE if ok else ROJO, fg="white")
        detalle_lbl.config(text=f"{intento['usuario_nombre']} → {lab['nombre']}\n"
                                f"Similitud: {intento['similitud']:.3f} (umbral {UMBRAL}) • {intento['motivo']}")
        refrescar()

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
            resultado_lbl.config(text="Esperando prueba…", bg="#e2e8f0", fg=OSCURO)
            detalle_lbl.config(text="")
            refrescar()

    canvas_lab.bind("<Configure>", redibujar)
    canvas_hora.bind("<Configure>", redibujar)
    root.after(100, refrescar)
    root.mainloop()


if __name__ == "__main__":
    ejecutar_app()
