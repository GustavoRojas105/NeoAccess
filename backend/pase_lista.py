"""
NeoAccess - Pase de lista del docente (Excel o PDF).

Para un día dado arma, por cada clase que el docente imparte ese día, la lista de
alumnos de su grupo con su hora de entrada al laboratorio (registrada por la puerta).
"""
import io
from datetime import date, datetime, timedelta

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(f: date) -> str:
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]} de {f.year}"


def clases_del_dia(cursor, docente_id: str, periodo_id: str, fecha: date, tolerancia_min: int,
                   horario_id=None, ahora: datetime = None) -> list:
    """Clases del docente ese día, cada una con su lista de alumnos y asistencia."""
    ahora = ahora or datetime.now()
    dia = DIAS[fecha.weekday()]
    sql = """
    SELECT h.id, h.materia, h.hora_inicio, h.hora_fin, h.grupo_id, h.laboratorio_id,
           l.nombre AS laboratorio_nombre, l.edificio,
           g.nombre AS grupo_nombre, COALESCE(g.clave, h.grupo_id) AS grupo_clave
    FROM horarios h
    JOIN laboratorios l ON h.laboratorio_id = l.id
    LEFT JOIN grupos g ON h.grupo_id = g.id
    WHERE h.docente_id = ? AND h.periodo_id = ? AND h.dia_semana = ?
    """
    params = [docente_id, periodo_id, dia]
    if horario_id is not None:
        sql += " AND h.id = ?"
        params.append(horario_id)
    sql += " ORDER BY h.hora_inicio"
    clases = [dict(r) for r in cursor.execute(sql, params).fetchall()]

    dia_txt = fecha.strftime("%Y-%m-%d")
    for c in clases:
        inicio = datetime.strptime(f"{dia_txt} {c['hora_inicio'][:5]}", "%Y-%m-%d %H:%M")
        fin = datetime.strptime(f"{dia_txt} {c['hora_fin'][:5]}", "%Y-%m-%d %H:%M")
        desde = (inicio - timedelta(minutes=tolerancia_min)).strftime("%Y-%m-%d %H:%M:%S")
        hasta = fin.strftime("%Y-%m-%d %H:%M:%S")

        entradas = {r["usuario_id"]: r["entrada"] for r in cursor.execute("""
            SELECT usuario_id, MIN(fecha_hora) AS entrada FROM registros_acceso
            WHERE resultado = 'permitido' AND laboratorio_id = ? AND fecha_hora BETWEEN ? AND ?
              AND usuario_id IS NOT NULL
            GROUP BY usuario_id
        """, (c["laboratorio_id"], desde, hasta)).fetchall()}

        alumnos = []
        if c["grupo_id"]:
            alumnos = [dict(r) for r in cursor.execute("""
                SELECT id, nombre_completo, matricula_clave FROM usuarios
                WHERE tipo = 'alumno' AND estado = 'activo' AND grupo_id = ?
                ORDER BY nombre_completo COLLATE NOCASE
            """, (c["grupo_id"],)).fetchall()]
        terminada = ahora >= fin
        for a in alumnos:
            entrada = entradas.get(a["id"])
            if entrada:
                a["entrada"] = entrada[11:16]
                a["asistencia"] = "Presente"
            else:
                a["entrada"] = ""
                a["asistencia"] = "Falta" if terminada else "Pendiente"
        c["alumnos"] = alumnos
        c["presentes"] = sum(1 for a in alumnos if a["asistencia"] == "Presente")
        c["docente_entrada"] = (entradas.get(docente_id) or "")[11:16]
        c["terminada"] = terminada
    return clases


# ───────────────────────── Excel ─────────────────────────
def _nombre_hoja(c: dict, usados: set) -> str:
    base = f"{c['hora_inicio'][:5].replace(':', '')} {c['grupo_clave'] or 'Clase'}"
    for ch in '[]:*?/\\':
        base = base.replace(ch, "-")
    base = base[:31]
    nombre, n = base, 2
    while nombre in usados:
        sufijo = f" ({n})"
        nombre = base[:31 - len(sufijo)] + sufijo
        n += 1
    usados.add(nombre)
    return nombre


def generar_excel(clases: list, docente: str, fecha: date, periodo: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    wb.remove(wb.active)
    negrita = Font(bold=True)
    titulo = Font(bold=True, size=14)
    encabezado = PatternFill("solid", fgColor="0F172A")
    blanco = Font(bold=True, color="FFFFFF")
    verde = PatternFill("solid", fgColor="DCFCE7")
    rojo = PatternFill("solid", fgColor="FEE2E2")
    fino = Side(style="thin", color="CBD5E1")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    usados = set()

    for c in clases:
        ws = wb.create_sheet(_nombre_hoja(c, usados))
        ws["A1"] = "Pase de lista — NeoAccess ITSOEH"
        ws["A1"].font = titulo
        datos = [
            ("Docente", docente),
            ("Materia", c["materia"]),
            ("Grupo", f"{c['grupo_clave'] or '—'}" + (f" · {c['grupo_nombre']}" if c.get("grupo_nombre") else "")),
            ("Laboratorio", f"{c['laboratorio_nombre']} ({c['edificio'] or ''})".replace(" ()", "")),
            ("Fecha", fecha_larga(fecha)),
            ("Horario", f"{c['hora_inicio'][:5]} – {c['hora_fin'][:5]}"),
            ("Periodo", periodo),
            ("Entrada del docente", c["docente_entrada"] or "Sin registro"),
            ("Asistencia", f"{c['presentes']} de {len(c['alumnos'])} alumnos"),
        ]
        for i, (k, v) in enumerate(datos, start=3):
            ws.cell(row=i, column=1, value=k).font = negrita
            ws.cell(row=i, column=2, value=v)
        fila = 3 + len(datos) + 1
        cab = ["#", "Matrícula", "Nombre del alumno", "Hora de entrada", "Asistencia", "Observaciones"]
        for j, texto in enumerate(cab, start=1):
            celda = ws.cell(row=fila, column=j, value=texto)
            celda.font, celda.fill, celda.border = blanco, encabezado, borde
            celda.alignment = Alignment(horizontal="center", vertical="center")
        if not c["alumnos"]:
            ws.cell(row=fila + 1, column=1, value="Este grupo no tiene alumnos registrados.")
        for n, a in enumerate(c["alumnos"], start=1):
            r = fila + n
            valores = [n, a["matricula_clave"], a["nombre_completo"], a["entrada"] or "—", a["asistencia"], ""]
            for j, v in enumerate(valores, start=1):
                celda = ws.cell(row=r, column=j, value=v)
                celda.border = borde
                if j in (1, 4, 5):
                    celda.alignment = Alignment(horizontal="center")
            ws.cell(row=r, column=5).fill = verde if a["asistencia"] == "Presente" else (
                rojo if a["asistencia"] == "Falta" else PatternFill())
        for col, ancho in zip("ABCDEF", (6, 14, 42, 16, 13, 30)):
            ws.column_dimensions[col].width = ancho
        ws.column_dimensions["B"].width = max(14, ws.column_dimensions["B"].width)
        ws.freeze_panes = ws.cell(row=fila + 1, column=1)
        ws.print_title_rows = f"{fila}:{fila}"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ───────────────────────── PDF ─────────────────────────
def _t(texto) -> str:
    """Las fuentes base del PDF usan Latin-1 (cubre acentos y ñ); lo demás se sustituye."""
    return str(texto if texto is not None else "").encode("latin-1", "replace").decode("latin-1")


def generar_pdf(clases: list, docente: str, fecha: date, periodo: str) -> bytes:
    from fpdf import FPDF

    generado = datetime.now().strftime("%d/%m/%Y %H:%M")

    class Hoja(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(120, 120, 120)
            self.cell(0, 5, _t(f"NeoAccess ITSOEH · generado el {generado} · página {self.page_no()}"), align="C")

    pdf = Hoja(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=16)
    anchos = (9, 26, 78, 24, 22, 37)
    cab = ("#", "Matrícula", "Nombre del alumno", "Entrada", "Asistencia", "Observaciones")

    def encabezado_tabla():
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(15, 23, 42)
        pdf.set_text_color(255, 255, 255)
        for w, txt in zip(anchos, cab):
            pdf.cell(w, 7, _t(txt), border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 8)

    for c in clases:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, _t("Pase de lista"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(0, 5, _t(f"NeoAccess ITSOEH · Periodo {periodo}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)
        grupo = f"{c['grupo_clave'] or '—'}" + (f" · {c['grupo_nombre']}" if c.get("grupo_nombre") else "")
        datos = [
            ("Docente", docente), ("Materia", c["materia"]), ("Grupo", grupo),
            ("Laboratorio", c["laboratorio_nombre"] + (f" ({c['edificio']})" if c.get("edificio") else "")),
            ("Fecha", fecha_larga(fecha)), ("Horario", f"{c['hora_inicio'][:5]} - {c['hora_fin'][:5]}"),
            ("Entrada del docente", c["docente_entrada"] or "Sin registro"),
            ("Asistencia", f"{c['presentes']} de {len(c['alumnos'])} alumnos"),
        ]
        for k, v in datos:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(38, 5.5, _t(k + ":"))
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(0, 5.5, _t(v), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        encabezado_tabla()
        if not c["alumnos"]:
            pdf.cell(sum(anchos), 8, _t("Este grupo no tiene alumnos registrados."), border=1, align="C")
            pdf.ln()
        for n, a in enumerate(c["alumnos"], start=1):
            if pdf.will_page_break(6.5):
                pdf.add_page()
                encabezado_tabla()
            presente = a["asistencia"] == "Presente"
            falta = a["asistencia"] == "Falta"
            valores = (str(n), a["matricula_clave"], a["nombre_completo"], a["entrada"] or "-", a["asistencia"], "")
            for i, (w, v) in enumerate(zip(anchos, valores)):
                relleno = False
                if i == 4 and (presente or falta):
                    pdf.set_fill_color(*((220, 252, 231) if presente else (254, 226, 226)))
                    relleno = True
                texto = _t(v)
                if i == 2:
                    while pdf.get_string_width(texto) > w - 2 and len(texto) > 3:
                        texto = texto[:-4] + "..."
                pdf.cell(w, 6.5, texto, border=1, align="L" if i == 2 else "C", fill=relleno)
            pdf.ln()
        pdf.ln(10)
        if pdf.will_page_break(14):
            pdf.add_page()
        pdf.cell(70, 5, "", border="B")
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(70, 4, _t(f"Firma del docente · {docente}"))

    return bytes(pdf.output())
