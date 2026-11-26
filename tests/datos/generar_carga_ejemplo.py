"""Genera carga_seit_ejemplo.txt: la «Carga Académica del Alumno» del SEIT de una captura real,
con las columnas medidas en pantalla (1 carácter ≈ 9.5 px). Uso: python tests/datos/generar_carga_ejemplo.py"""
import os

COL = {"Lu": 31, "Ma": 43, "Mi": 55, "Ju": 67, "Vi": 79, "Sa": 91}
SEP = "- " * 49


def fila(izq, celdas):
    t = list(izq.ljust(105))
    for col, txt in celdas:
        t[col:col + len(txt)] = list(txt)
    return "".join(t).rstrip()


L = [SEP,
     "           SEP   INSTITUTO TECNOLÓGICO SUPERIOR DEL OCCIDENTE DEL ESTADO DE HIDALGO   SEIT",
     "                                Carga Académica del Alumno              Fecha      : 16/08/26",
     SEP,
     "N. Control : 230110627             Periodo    : AGO-DIC-2026                  Hora       : 10:26:",
     "Nombre     : SANTILLAN HERNANDEZ RAFAEL",
     "Semestre   : 7                     Créditos   : 38",
     SEP,
     "                            Cr    Lunes      Martes     Miércoles    Jueves      Viernes     Sábado",
     SEP]


def mat(code, nombre, cr, horas, docente, salones):
    L.append(fila(f"{code} {nombre}".ljust(28) + cr, [(COL[d], h) for d, h in horas]))
    L.append(fila(f"     {docente}", [(COL[d] + 1, s) for d, s in salones]))


mat("107B", "LENGUAJES Y AUTÓMATA", "5", [("Mi", "15:00-16:00"), ("Ju", "12:00-14:00"), ("Vi", "13:00-15:00")],
    "RICARDO MARTINEZ LOPEZ", [("Mi", "Salón 406"), ("Ju", "Salón 408"), ("Vi", "Salón M1")])
mat("207B", "CONMUTACIÓN Y ENRUTA", "5", [("Lu", "17:00-20:00"), ("Ju", "17:00-19:00")],
    "GERMAN REBOLLEDO AVALOS", [("Lu", "Salón LPB"), ("Ju", "Salón 408")])
mat("307B", "INTELIGENCIA ARTIFIC", "4", [("Ma", "18:00-20:00"), ("Mi", "18:00-20:00")],
    "JORGE ARMANDO GARCIA BAUT", [("Ma", "Salón 402"), ("Mi", "Salón 406")])
mat("507B", "SISTEMAS PROGRAMABLE", "4", [("Ma", "13:00-15:00"), ("Ju", "15:00-17:00")],
    "JOSUE EMANUEL RODRIGUEZ A", [("Ma", "Salón LMU"), ("Ju", "Salón 408")])
mat("98AB", "TÓPICOS DEL FRONT-EN", "5", [("Lu", "13:00-15:00"), ("Ma", "11:00-13:00"), ("Mi", "17:00-18:00")],
    "SERGIO CRUZ PEREZ", [("Lu", "Salón 401"), ("Ma", "Salón LRE"), ("Mi", "Salón 406")])
mat("98BB", "TÓPICOS DE BASE DE D", "5", [("Ma", "16:00-18:00"), ("Ju", "14:00-15:00"), ("Vi", "17:00-19:00")],
    "JAVIER PEREZ ESCAMILLA", [("Ma", "Salón 402"), ("Ju", "Salón 408"), ("Vi", "Salón 406")])
mat("S07B", "SERVICIO SOCIAL", "10", [("Sa", "11:30-12:00")], "CARMEN ROJO MONROY", [("Sa", "Salón SS")])
mat("T07B", "TUTORÍA VII", "0", [("Ma", "15:00-16:00")], "LORENA MENDOZA GUZMAN", [("Ma", "Salón 402")])
mat("X07B", "INGLÉS VII", "0", [("Lu", "15:00-17:00"), ("Mi", "16:00-17:00"), ("Vi", "15:00-17:00")],
    "IRIS CRISTAL PEREZ RESEND", [("Lu", "Salón 406"), ("Mi", "Salón 406"), ("Vi", "Salón 406")])
L += ["", "Nota Importante: Desde esta pagina puedes descargar el temario de las materias que estas cursando."]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "carga_seit_ejemplo.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
