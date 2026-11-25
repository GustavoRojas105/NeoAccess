"""
NeoAccess - Validación, plantilla de Excel e importación masiva de horarios.

- generar_plantilla(cursor) -> bytes .xlsx con listas desplegables (laboratorios,
  grupos, docentes, días, horas y materias oficiales).
- leer_archivo(nombre, contenido) -> filas (dict por columna) desde .xlsx o .csv.
- validar_horario(datos, cursor, ocupados) -> (horario_normalizado, errores)
  La usan tanto el alta uno por uno como la importación.
"""
import csv
import io
import json
import os
import re
import unicodedata
from datetime import time as dtime, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOGO_MATERIAS = os.path.join(RAIZ, "frontend", "scripts", "materias_itsoeh.json")

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
HORA_MIN, HORA_MAX = "06:00", "22:00"
SEPARADOR = " — "  # en la plantilla: "CLAVE — Nombre"

COLUMNAS = [
    ("dia", "Día"),
    ("hora_inicio", "Hora inicio"),
    ("hora_fin", "Hora fin"),
    ("laboratorio", "Laboratorio"),
    ("grupo", "Grupo"),
    ("docente", "Docente"),
    ("materia", "Materia"),
]


def _norm(texto) -> str:
    """minúsculas, sin acentos ni espacios extra (para comparar)."""
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().split())


def cargar_materias() -> dict:
    """{carrera: [materias]} del catálogo oficial."""
    with open(CATALOGO_MATERIAS, encoding="utf-8") as f:
        data = json.load(f)["carreras"]
    return {c: [m for lista in por_sem.values() for m in lista] for c, por_sem in data.items()}


# ───────────────────────── Validación ─────────────────────────

def _hora(valor):
    """Acepta '7:00', '07:00', '7:00 am', time de Excel o fracción de día. Devuelve 'HH:MM' o None."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        valor = valor.time()
    if isinstance(valor, dtime):
        return f"{valor.hour:02d}:{valor.minute:02d}"
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if not 0 <= valor < 1:
            return None  # un número de Excel fuera de 0..1 no es una hora del día
        minutos = round(valor * 24 * 60)
        return f"{minutos // 60:02d}:{minutos % 60:02d}"
    # "7:30 p.m." -> "7:30pm"; "7.30" -> "7:30" (el punto como separador de hora)
    t = _norm(valor).replace(" ", "")
    for largo, corto in (("a.m.", "am"), ("p.m.", "pm"), ("a.m", "am"), ("p.m", "pm")):
        t = t.replace(largo, corto)
    t = t.replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::\d{2})?(am|pm)?", t)
    if not m:
        return None
    h, mi, sufijo = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if sufijo == "pm" and h < 12:
        h += 12
    if sufijo == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def _clave(valor) -> str:
    """'LAB-1 — Lab de Redes' -> 'LAB-1'."""
    v = str(valor or "").strip()
    return v.split(SEPARADOR)[0].split(" - ")[0].strip() if v else ""


def _buscar(cursor, sql_id, sql_nombre, valor, extra=()):
    """Busca por clave exacta; si no, por nombre completo (sin importar acentos/mayúsculas)."""
    clave = _clave(valor)
    if not clave:
        return None
    fila = cursor.execute(sql_id, (clave, clave, *extra)).fetchone()
    if fila:
        return fila
    texto = str(valor).split(SEPARADOR)[-1]
    for f in cursor.execute(sql_nombre, extra).fetchall():
        if _norm(f["nombre"]) == _norm(texto):
            return f
    return None


def _se_traslapan(a_ini, a_fin, b_ini, b_fin) -> bool:
    return a_ini < b_fin and b_ini < a_fin


def validar_horario(datos: dict, cursor, ocupados: list, materias: dict = None,
                    periodo_id: str = None, carreras: list = None):
    """
    datos: dia, hora_inicio, hora_fin, laboratorio, grupo, docente, materia (texto libre).
    ocupados: horarios ya aceptados en este lote [(lab, dia, ini, fin, grupo, docente)].
    periodo_id: periodo activo (grupos y choques solo de ese periodo).
    carreras: si se indica (jefe de carrera), el grupo debe ser de una de esas carreras.
    Devuelve (horario listo para insertar | None, [errores]).
    """
    materias = materias or cargar_materias()
    errores = []

    dia = next((d for d in DIAS if _norm(d) == _norm(datos.get("dia"))), None)
    if not dia:
        errores.append("Día inválido (use Lunes a Sábado).")

    ini, fin = _hora(datos.get("hora_inicio")), _hora(datos.get("hora_fin"))
    if not ini:
        errores.append("Hora de inicio inválida (formato HH:MM).")
    if not fin:
        errores.append("Hora de fin inválida (formato HH:MM).")
    if ini and fin:
        if ini >= fin:
            errores.append("La hora de fin debe ser después de la de inicio.")
        elif ini < HORA_MIN or fin > HORA_MAX:
            errores.append(f"El horario debe estar entre {HORA_MIN} y {HORA_MAX}.")

    lab = _buscar(cursor, "SELECT id, nombre, activo FROM laboratorios WHERE upper(id) = upper(?) OR ? = ''",
                  "SELECT id, nombre, activo FROM laboratorios", datos.get("laboratorio"))
    if not datos.get("laboratorio"):
        errores.append("Falta el laboratorio.")
    elif not lab:
        errores.append(f"El laboratorio '{_clave(datos.get('laboratorio'))}' no existe.")
    elif not lab["activo"]:
        errores.append(f"El laboratorio {lab['id']} está desactivado.")

    grupo = _buscar(cursor,
                    "SELECT id, nombre, carrera FROM grupos WHERE (upper(id) = upper(?) OR ? = '') AND periodo_id IS ?",
                    "SELECT id, nombre, carrera FROM grupos WHERE periodo_id IS ?",
                    datos.get("grupo"), extra=(periodo_id,))
    if not datos.get("grupo"):
        errores.append("Falta el grupo.")
    elif not grupo:
        errores.append(f"El grupo '{_clave(datos.get('grupo'))}' no existe en el periodo actual.")
    elif carreras is not None and grupo["carrera"] not in carreras:
        errores.append(f"El grupo {grupo['id']} es de {grupo['carrera']}, que no está a su cargo.")
        grupo = None

    docente = _buscar(
        cursor,
        "SELECT id, nombre_completo AS nombre, tipo, estado FROM usuarios WHERE upper(id) = upper(?) OR upper(matricula_clave) = upper(?)",
        "SELECT id, nombre_completo AS nombre, tipo, estado FROM usuarios WHERE tipo = 'docente'",
        datos.get("docente"))
    if not datos.get("docente"):
        errores.append("Falta el docente.")
    elif not docente:
        errores.append(f"El docente '{_clave(datos.get('docente'))}' no existe.")
    elif docente["tipo"] != "docente":
        errores.append(f"{docente['nombre']} no está registrado como docente.")
    elif docente["estado"] != "activo":
        errores.append(f"El docente {docente['nombre']} está dado de baja.")

    materia = None
    texto_materia = datos.get("materia")
    if not str(texto_materia or "").strip():
        errores.append("Falta la materia.")
    else:
        todas = {_norm(m): m for lista in materias.values() for m in lista}
        materia = todas.get(_norm(texto_materia))
        if not materia:
            errores.append(f"'{str(texto_materia).strip()}' no está en las materias oficiales del ITSOEH.")
        elif grupo and grupo["carrera"] in materias and materia not in materias[grupo["carrera"]]:
            errores.append(f"'{materia}' no pertenece a la carrera del grupo ({grupo['carrera']}).")

    # Choques de horario: mismo laboratorio, mismo grupo o mismo docente a la misma hora
    if not errores:
        existentes = cursor.execute(
            "SELECT laboratorio_id, dia_semana, hora_inicio, hora_fin, grupo_id, docente_id FROM horarios "
            "WHERE dia_semana = ? AND periodo_id IS ?", (dia, periodo_id)).fetchall()
        candidatos = [tuple(r) for r in existentes] + [o for o in ocupados if o[1] == dia]
        for (o_lab, _d, o_ini, o_fin, o_grupo, o_doc) in candidatos:
            if not _se_traslapan(ini, fin, o_ini, o_fin):
                continue
            if o_lab == lab["id"]:
                errores.append(f"El laboratorio {lab['id']} ya está ocupado el {dia} de {o_ini} a {o_fin}.")
            elif o_grupo == grupo["id"]:
                errores.append(f"El grupo {grupo['id']} ya tiene clase el {dia} de {o_ini} a {o_fin}.")
            elif o_doc == docente["id"]:
                errores.append(f"El docente ya da clase el {dia} de {o_ini} a {o_fin}.")
            if errores:
                break

    if errores:
        return None, errores
    return {
        "grupo_id": grupo["id"], "laboratorio_id": lab["id"], "docente_id": docente["id"], "periodo_id": periodo_id,
        "materia": materia, "dia_semana": dia, "hora_inicio": ini, "hora_fin": fin,
        # Para mostrar en la vista previa
        "laboratorio_nombre": lab["nombre"], "grupo_nombre": grupo["nombre"], "docente_nombre": docente["nombre"],
    }, []


# ───────────────────────── Lectura de archivos ─────────────────────────

_ALIAS = {
    "dia": ["dia", "dia de la semana", "dia semana"],
    "hora_inicio": ["hora inicio", "inicio", "hora de inicio", "entrada"],
    "hora_fin": ["hora fin", "fin", "hora de fin", "hora final", "salida"],
    "laboratorio": ["laboratorio", "lab", "laboratorio / salon", "salon", "laboratorio_id"],
    "grupo": ["grupo", "grupo_id"],
    "docente": ["docente", "docente titular", "clave docente", "maestro", "profesor", "docente_id"],
    "materia": ["materia", "asignatura"],
}


def _mapear_encabezados(encabezados):
    mapa = {}
    for i, h in enumerate(encabezados):
        n = _norm(h).rstrip(" *")
        for campo, alias in _ALIAS.items():
            if n in alias and campo not in mapa:
                mapa[campo] = i
    return mapa


def leer_archivo(nombre: str, contenido: bytes):
    """Devuelve (filas, error). Cada fila: {'fila': n, campo: valor}."""
    nombre = (nombre or "").lower()
    if nombre.endswith(".xlsx"):
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except Exception:
            return [], "No se pudo abrir el archivo de Excel. ¿Está dañado o protegido?"
        ws = wb["Horarios"] if "Horarios" in wb.sheetnames else wb.worksheets[0]
        tabla = [list(r) for r in ws.iter_rows(values_only=True)]
    elif nombre.endswith(".csv") or nombre.endswith(".txt"):
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("cp1252", errors="replace")  # CSV guardado por Excel en Windows
        primera = texto.splitlines()[0] if texto.strip() else ""
        delim = ";" if primera.count(";") > primera.count(",") else ","
        tabla = list(csv.reader(io.StringIO(texto), delimiter=delim))
    else:
        return [], "Formato no soportado. Use la plantilla de Excel (.xlsx) o un archivo .csv."

    # Buscar la fila de encabezados en las primeras 10
    for idx, fila in enumerate(tabla[:10]):
        mapa = _mapear_encabezados(fila)
        if len(mapa) >= 5:
            break
    else:
        return [], "No se encontraron los encabezados (Día, Hora inicio, Hora fin, Laboratorio, Grupo, Docente, Materia)."
    faltan = [titulo for campo, titulo in COLUMNAS if campo not in mapa]
    if faltan:
        return [], "Faltan columnas: " + ", ".join(faltan)

    filas = []
    for n, fila in enumerate(tabla[idx + 1:], start=idx + 2):
        valores = {c: (fila[i] if i < len(fila) else None) for c, i in mapa.items()}
        if all(v is None or str(v).strip() == "" for v in valores.values()):
            continue  # fila vacía
        valores = {c: (v.strip() if isinstance(v, str) else v) for c, v in valores.items()}
        filas.append({"fila": n, **valores})
    return filas, None


# ───────────────────────── Plantilla de Excel ─────────────────────────

def generar_plantilla(cursor, periodo_id: str = None, carreras: list = None, periodo_nombre: str = "") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter

    labs = [f"{r['id']}{SEPARADOR}{r['nombre']}" for r in cursor.execute(
        "SELECT id, nombre FROM laboratorios WHERE activo = 1 ORDER BY id")]
    grupos = [f"{r['id']}{SEPARADOR}{r['nombre']}" for r in cursor.execute(
        "SELECT id, nombre, carrera FROM grupos WHERE periodo_id IS ? ORDER BY carrera, semestre, id", (periodo_id,))
        if carreras is None or r["carrera"] in carreras]
    docentes = [f"{r['id']}{SEPARADOR}{r['nombre_completo']}" for r in cursor.execute(
        "SELECT id, nombre_completo FROM usuarios WHERE tipo = 'docente' AND estado = 'activo' ORDER BY nombre_completo")]
    catalogo = cargar_materias()
    materias = sorted({m for c, lista in catalogo.items() if carreras is None or c in carreras for m in lista}, key=_norm)
    horas = [f"{h:02d}:{m:02d}" for h in range(6, 23) for m in (0, 30) if f"{h:02d}:{m:02d}" <= HORA_MAX]

    wb = Workbook()
    ws = wb.active
    ws.title = "Horarios"
    titulo = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="0F172A")
    borde = Border(bottom=Side(style="thin", color="CBD5E1"))
    anchos = [12, 12, 12, 38, 34, 34, 44]
    for i, (_campo, texto) in enumerate(COLUMNAS, start=1):
        c = ws.cell(row=1, column=i, value=texto)
        c.font, c.fill = titulo, relleno
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = anchos[i - 1]
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"
    FILAS = 300
    for fila in range(2, FILAS + 2):
        for col in range(1, len(COLUMNAS) + 1):
            cel = ws.cell(row=fila, column=col)
            cel.number_format = "@"  # texto: Excel no convierte "07:00" en fecha
            cel.border = borde

    # Hoja con las listas para los desplegables
    listas = wb.create_sheet("Listas")
    columnas_listas = [("Días", DIAS), ("Horas", horas), ("Laboratorios", labs),
                       ("Grupos", grupos), ("Docentes", docentes), ("Materias oficiales", materias)]
    rangos = {}
    for i, (nombre, valores) in enumerate(columnas_listas, start=1):
        letra = get_column_letter(i)
        listas.cell(row=1, column=i, value=nombre).font = Font(bold=True)
        for j, v in enumerate(valores, start=2):
            listas.cell(row=j, column=i, value=v)
        listas.column_dimensions[letra].width = 40 if i > 2 else 12
        rangos[nombre] = f"Listas!${letra}$2:${letra}${max(2, len(valores) + 1)}" if valores else None
    listas.sheet_state = "hidden"

    def desplegable(col_letra, rango, nombre, estricto=True):
        if not rango:
            return
        dv = DataValidation(type="list", formula1=f"={rango}", allow_blank=True,
                            showErrorMessage=estricto, errorStyle="stop" if estricto else "warning",
                            errorTitle="Valor no válido",
                            error=f"Elija un valor de la lista de {nombre}.",
                            promptTitle=nombre, prompt=f"Elija de la lista de {nombre.lower()}.",
                            showInputMessage=True)
        ws.add_data_validation(dv)
        dv.add(f"{col_letra}2:{col_letra}{FILAS + 1}")

    desplegable("A", rangos["Días"], "Días")
    desplegable("B", rangos["Horas"], "Horas", estricto=False)   # se puede escribir otra hora (ej. 07:15)
    desplegable("C", rangos["Horas"], "Horas", estricto=False)
    desplegable("D", rangos["Laboratorios"], "Laboratorios")
    desplegable("E", rangos["Grupos"], "Grupos")
    desplegable("F", rangos["Docentes"], "Docentes")
    desplegable("G", rangos["Materias oficiales"], "Materias oficiales")

    # Instrucciones
    ins = wb.create_sheet("Instrucciones")
    ins.column_dimensions["A"].width = 110
    lineas = [
        ("Cómo llenar la plantilla de horarios (NeoAccess - ITSOEH)" + (f" — Periodo {periodo_nombre}" if periodo_nombre else ""), True),
        ("", False),
        ("1. Llene una fila por cada clase en la hoja «Horarios». Todas las columnas son obligatorias.", False),
        ("2. Use las listas desplegables: Día, Laboratorio, Grupo, Docente y Materia solo aceptan valores registrados en el sistema.", False),
        ("3. Horas en formato de 24 h (HH:MM), entre 06:00 y 22:00. Puede elegirlas de la lista o escribirlas (ej. 07:15).", False),
        ("4. La materia debe pertenecer a la carrera del grupo (materias oficiales del ITSOEH).", False),
        ("5. No se aceptan choques: el mismo laboratorio, grupo o docente no puede tener dos clases a la misma hora.", False),
        ("6. Guarde el archivo y súbalo en Horarios y Grupos → Importar horarios. Antes de guardar verá una revisión fila por fila.", False),
        ("", False),
        ("Si falta un laboratorio, grupo o docente en las listas, regístrelo primero en el Dashboard y descargue la plantilla de nuevo.", False),
        (f"Plantilla generada el {datetime.now().strftime('%d/%m/%Y %H:%M')} con {len(labs)} laboratorio(s), "
         f"{len(grupos)} grupo(s) y {len(docentes)} docente(s).", False),
    ]
    for i, (texto, negrita) in enumerate(lineas, start=1):
        c = ins.cell(row=i, column=1, value=texto)
        c.font = Font(bold=negrita, size=13 if negrita else 11)
        c.alignment = Alignment(wrap_text=True)
    wb.move_sheet("Instrucciones", offset=-1)  # queda antes de "Listas"
    wb.active = 0

    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()
