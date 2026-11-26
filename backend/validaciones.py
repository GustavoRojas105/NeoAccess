"""
NeoAccess - Reglas comunes para nombres de personas y matrículas/claves.

- Los nombres se guardan en MAYÚSCULAS, sin espacios dobles (evita duplicados por
  "Juan Pérez" vs "JUAN PÉREZ" y que las listas se vean disparejas).
- Matrícula de alumno: solo números, 8 dígitos (generación anterior, p. ej. 19011044)
  o 9 dígitos (generaciones nuevas, p. ej. 230110427).
- Clave de docente / personal: letras, números y guiones (p. ej. DOC-ISC-01).
"""
import re

from fastapi import HTTPException

NOMBRE_MIN, NOMBRE_MAX = 3, 120
MATRICULA_MIN, MATRICULA_MAX = 8, 9
CLAVE_MIN, CLAVE_MAX = 3, 20

_NOMBRE_RE = re.compile(r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ .'-]*$")
_MATRICULA_RE = re.compile(rf"^\d{{{MATRICULA_MIN},{MATRICULA_MAX}}}$")
_CLAVE_RE = re.compile(rf"^[A-Z0-9-]{{{CLAVE_MIN},{CLAVE_MAX}}}$")


def normalizar_nombre(nombre, que: str = "El nombre") -> str:
    """'  juan  pérez ' -> 'JUAN PÉREZ'. Lanza 400 si tiene números o símbolos."""
    limpio = " ".join(str(nombre or "").split()).upper()
    if not NOMBRE_MIN <= len(limpio) <= NOMBRE_MAX:
        raise HTTPException(status_code=400, detail=f"{que} debe tener de {NOMBRE_MIN} a {NOMBRE_MAX} caracteres.")
    if not _NOMBRE_RE.match(limpio):
        raise HTTPException(status_code=400,
                            detail=f"{que} solo puede tener letras y espacios (también acentos, ñ, punto, guion y apóstrofo).")
    return limpio


def normalizar_matricula(valor, tipo: str) -> str:
    """Alumno: 8 o 9 números. Docente / personal: 3 a 20 letras, números o guiones (en mayúsculas)."""
    v = "".join(str(valor or "").split()).upper()
    if tipo == "alumno":
        if not _MATRICULA_RE.match(v):
            raise HTTPException(status_code=400,
                                detail=f"La matrícula del alumno debe tener {MATRICULA_MIN} o {MATRICULA_MAX} números, "
                                       "sin letras ni espacios (p. ej. 19011044 o 230110427).")
    elif not _CLAVE_RE.match(v):
        raise HTTPException(status_code=400,
                            detail=f"La clave debe tener de {CLAVE_MIN} a {CLAVE_MAX} letras, números o guiones (p. ej. DOC-ISC-01).")
    return v
