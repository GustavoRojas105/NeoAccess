"""
NeoAccess - Lector de la "Carga Académica del Alumno" del SEIT.

El alumno abre su carga en el SEIT, copia todo (Ctrl+A, Ctrl+C) y lo pega en NeoAccess.
Cada materia ocupa dos renglones:

    107B LENGUAJES Y AUTÓMATA   5                         15:00-16:00 12:00-14:00
         RICARDO MARTINEZ LOPEZ                            Salón 406   Salón 408

El día de cada hora se saca de su columna (encabezado Lunes ... Sábado). Si el texto
pegado perdió los espacios, se buscan las clases por docente y hora sin importar el día.

Una sesión se liga a una clase de NeoAccess (tabla horarios) cuando coinciden la hora
de inicio y fin, el docente (el SEIT recorta los nombres largos) y, si se conoce, el día.
"""
import re
import unicodedata

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_DIAS_RE = re.compile(r"\b(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo)\b", re.I)
_HORA_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_SALON_RE = re.compile(r"Sal[oó]n\s+(\S+)", re.I)
# código de la materia (107B, 98AB, S07B), nombre, créditos y lo demás (horas)
_MATERIA_RE = re.compile(r"^\s*((?=[0-9A-Z]*\d)[0-9A-Z]{3,5})\s+(\S.*?)\s+(\d{1,2})(?=\s+\d{1,2}:\d{2}|\s*$)")
_CONTROL_RE = re.compile(r"N\.?\s*(?:de\s*)?Control\s*:?\s*(\d{6,12})", re.I)
MAX_TEXTO = 20000


def normalizar(texto) -> str:
    """'José  Pérez' -> 'JOSE PEREZ' (sin acentos, mayúsculas, un espacio)."""
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.upper().split())


def _dia_normal(nombre: str) -> str:
    n = normalizar(nombre)
    for d in DIAS:
        if normalizar(d) == n:
            return d
    return nombre


def _centro(m) -> float:
    return (m.start() + m.end()) / 2


def leer_carga(texto: str) -> dict:
    """Devuelve {"control": "230110627" | None, "materias": [{codigo, materia, docente, sesiones:[...]}]}.
    Cada sesión: {"dia": "Martes" | None, "inicio": "13:00", "fin": "15:00", "salon": "LMU" | None}."""
    texto = (texto or "")[:MAX_TEXTO].replace("\r", "").expandtabs(8)
    lineas = texto.split("\n")
    control = _CONTROL_RE.search(texto)

    columnas = []   # [(centro, "Lunes"), ...] del encabezado
    materias = []
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        dias_linea = list(_DIAS_RE.finditer(linea))
        if len(dias_linea) >= 3 and not _HORA_RE.search(linea):
            columnas = [(_centro(m), _dia_normal(m.group(1))) for m in dias_linea]
            i += 1
            continue
        m = _MATERIA_RE.match(linea)
        if not m:
            i += 1
            continue
        horas = list(_HORA_RE.finditer(linea, m.end()))
        # renglón siguiente con el docente y los salones
        j = i + 1
        while j < len(lineas) and not lineas[j].strip():
            j += 1
        docente, salones = "", []
        if j < len(lineas) and not _MATERIA_RE.match(lineas[j]):
            sig = lineas[j]
            corte = _SALON_RE.search(sig)
            docente = (sig[:corte.start()] if corte else sig).strip()
            docente = re.split(r"\s{2,}", docente)[0].strip()
            salones = list(_SALON_RE.finditer(sig))
            i = j
        # si al pegar se perdieron los espacios, las columnas ya no dicen el día
        alineado = bool(horas) and len(linea[m.end():horas[0].start()]) >= 2
        sesiones = []
        for k, h in enumerate(horas):
            dia = None
            if columnas and alineado:
                dia = min(columnas, key=lambda c: abs(c[0] - _centro(h)))[1]
            salon = None
            if salones:
                if len(salones) == len(horas):
                    salon = salones[k].group(1)
                else:
                    salon = min(salones, key=lambda s: abs(_centro(s) - _centro(h))).group(1)
            sesiones.append({
                "dia": dia,
                "inicio": f"{int(h.group(1)):02d}:{h.group(2)}",
                "fin": f"{int(h.group(3)):02d}:{h.group(4)}",
                "salon": salon.upper() if salon else None,
            })
        materias.append({"codigo": m.group(1), "materia": " ".join(m.group(2).split()),
                         "docente": docente, "sesiones": sesiones})
        i += 1
    return {"control": control.group(1) if control else None, "materias": materias}


def ligar_con_horarios(carga: dict, horarios: list, laboratorios: set) -> dict:
    """Busca cada sesión en los horarios de NeoAccess (lista de dicts con id, dia_semana,
    hora_inicio, hora_fin, docente_nombre, laboratorio_id, materia, grupo_id).
    Devuelve {"ligadas": [...], "sin_clase": [...], "en_salon": [...]}."""
    labs = {normalizar(l) for l in laboratorios}
    ligadas, sin_clase, en_salon, vistos = [], [], [], set()
    for mat in carga["materias"]:
        doc = normalizar(mat["docente"])
        for s in mat["sesiones"]:
            fila = {"codigo": mat["codigo"], "materia": mat["materia"], "docente": mat["docente"], **s}
            candidatos = [
                h for h in horarios
                if h["hora_inicio"][:5] == s["inicio"] and h["hora_fin"][:5] == s["fin"]
                and (s["dia"] is None or h["dia_semana"] == s["dia"])
                and doc and normalizar(h.get("docente_nombre")).startswith(doc)
            ]
            if s["salon"] and len(candidatos) > 1:
                mismos = [h for h in candidatos if normalizar(h["laboratorio_id"]) == normalizar(s["salon"])]
                candidatos = mismos or candidatos
            if candidatos:
                for h in candidatos:
                    if h["id"] not in vistos:
                        vistos.add(h["id"])
                        ligadas.append({**fila, "horario_id": h["id"], "dia": h["dia_semana"],
                                        "laboratorio_id": h["laboratorio_id"], "materia_neoaccess": h["materia"]})
            elif s["salon"] and normalizar(s["salon"]) in labs:
                sin_clase.append(fila)       # es un laboratorio con puerta, pero no hay clase igual registrada
            else:
                en_salon.append(fila)        # salón normal: no tiene puerta de NeoAccess
    return {"ligadas": ligadas, "sin_clase": sin_clase, "en_salon": en_salon}
