"""
NeoAccess - Reglas comunes para nombres de personas y matrículas/claves.

- Los nombres se guardan en MAYÚSCULAS, sin espacios dobles (evita duplicados por
  "Juan Pérez" vs "JUAN PÉREZ" y que las listas se vean disparejas).
- Matrícula de alumno: solo números, 8 dígitos (generación anterior, p. ej. 19011044)
  o 9 dígitos (generaciones nuevas, p. ej. 230110427).
- Docente: número de empleado que asigna RH, solo números (3 a 10 dígitos).
  Los docentes dados de alta antes con claves tipo DOC-ISC-01 la conservan mientras no la cambien.
- Personal de limpieza / mantenimiento: clave de letras, números y guiones (p. ej. LIM-01).
"""
import difflib
import re
import unicodedata

from fastapi import HTTPException

NOMBRE_MIN, NOMBRE_MAX = 3, 120
MATRICULA_MIN, MATRICULA_MAX = 8, 9
CLAVE_MIN, CLAVE_MAX = 3, 20
EMPLEADO_MIN, EMPLEADO_MAX = 3, 10

_NOMBRE_RE = re.compile(r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ .'-]*$")
_MATRICULA_RE = re.compile(rf"^\d{{{MATRICULA_MIN},{MATRICULA_MAX}}}$")
_CLAVE_RE = re.compile(rf"^[A-Z0-9-]{{{CLAVE_MIN},{CLAVE_MAX}}}$")
_EMPLEADO_RE = re.compile(rf"^\d{{{EMPLEADO_MIN},{EMPLEADO_MAX}}}$")


_PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "Y"}


def palabras_nombre(nombre) -> list:
    """'José de la Peña' -> ['JOSE', 'PENA']: sin acentos, sin partículas, para comparar nombres."""
    s = unicodedata.normalize("NFD", str(nombre or "").upper())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z ]", " ", s)
    return [w for w in s.split() if w not in _PARTICULAS]


def nombres_parecidos(a, b) -> bool:
    """Mismo nombre aunque cambie el orden, los acentos, falte un nombre o tenga un error de dedo."""
    pa, pb = palabras_nombre(a), palabras_nombre(b)
    if not pa or not pb:
        return False
    sa, sb = set(pa), set(pb)
    if sa == sb:
        return True
    menor, mayor = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if len(menor) >= 3 and menor <= mayor:          # p. ej. le falta el segundo nombre
        return True
    return difflib.SequenceMatcher(None, " ".join(sorted(pa)), " ".join(sorted(pb))).ratio() >= 0.95


def clave_comparable(valor) -> str:
    """'00123' == '123' y 'lim-01' == 'LIM01': así no se repite la misma clave escrita distinto."""
    s = re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())
    return (s.lstrip("0") or "0") if s.isdigit() else s


def normalizar_nombre(nombre, que: str = "El nombre") -> str:
    """'  juan  pérez ' -> 'JUAN PÉREZ'. Lanza 400 si tiene números o símbolos."""
    limpio = " ".join(str(nombre or "").split()).upper()
    if not NOMBRE_MIN <= len(limpio) <= NOMBRE_MAX:
        raise HTTPException(status_code=400, detail=f"{que} debe tener de {NOMBRE_MIN} a {NOMBRE_MAX} caracteres.")
    if not _NOMBRE_RE.match(limpio):
        raise HTTPException(status_code=400,
                            detail=f"{que} solo puede tener letras y espacios (también acentos, ñ, punto, guion y apóstrofo).")
    return limpio


def normalizar_matricula(valor, tipo: str, actual: str | None = None) -> str:
    """Alumno: 8 o 9 números. Docente: número de empleado (3 a 10 números).
    Personal: 3 a 20 letras, números o guiones. `actual` = la que ya tenía (se respeta si no cambia)."""
    v = "".join(str(valor or "").split()).upper()
    if actual is not None and v == str(actual).upper():
        return v
    if tipo == "docente":
        if not _EMPLEADO_RE.match(v):
            raise HTTPException(status_code=400,
                                detail=f"El número de empleado debe tener de {EMPLEADO_MIN} a {EMPLEADO_MAX} números, "
                                       "sin letras ni espacios (es el que asigna Recursos Humanos).")
    elif tipo == "alumno":
        if not _MATRICULA_RE.match(v):
            raise HTTPException(status_code=400,
                                detail=f"La matrícula del alumno debe tener {MATRICULA_MIN} o {MATRICULA_MAX} números, "
                                       "sin letras ni espacios (p. ej. 19011044 o 230110427).")
    elif not _CLAVE_RE.match(v):
        raise HTTPException(status_code=400,
                            detail=f"La clave debe tener de {CLAVE_MIN} a {CLAVE_MAX} letras, números o guiones (p. ej. LIM-01).")
    return v
