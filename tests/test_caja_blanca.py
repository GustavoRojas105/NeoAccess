"""
PRUEBAS DE CAJA BLANCA
Se conoce el código: se prueba cada función interna recorriendo sus ramas
(if/else, ciclos, excepciones) y los valores límite de sus condiciones.
"""
import ast
import io
import json
import os
import shutil
import sqlite3
import subprocess
import types
import unittest
from datetime import date, datetime, time as dtime, timedelta

from _entorno import RAIZ, ISC, CIV, bd, sembrar, periodo_activo_id
import database.database as dbm
import backend.auth as auth
import backend.horarios_import as hi
import backend.app as appmod
from fastapi import HTTPException


# ───────────────────────── database.database ─────────────────────────
class TestPeriodos(unittest.TestCase):
    def test_periodo_para_fecha_limites_de_mes(self):
        casos = {
            date(2026, 1, 1): "2026-1",     # primer día del año
            date(2026, 6, 30): "2026-1",    # último día de Ene-Jun
            date(2026, 7, 1): "2026-2",     # julio: vacaciones, cuenta para Ago-Dic
            date(2026, 8, 1): "2026-2",
            date(2026, 12, 31): "2026-2",
        }
        for fecha, esperado in casos.items():
            with self.subTest(fecha=fecha):
                self.assertEqual(dbm.periodo_para_fecha(fecha)["id"], esperado)

    def test_periodo_para_fecha_campos(self):
        p = dbm.periodo_para_fecha(date(2027, 3, 15))
        self.assertEqual(p, {"id": "2027-1", "nombre": "Ene-Jun 2027", "fecha_inicio": "2027-01-01", "fecha_fin": "2027-06-30"})

    def test_periodo_siguiente_ambas_ramas(self):
        self.assertEqual(dbm.periodo_siguiente("2026-1")["id"], "2026-2")
        self.assertEqual(dbm.periodo_siguiente("2026-2")["id"], "2027-1")
        self.assertEqual(dbm.periodo_siguiente("2026-2")["fecha_inicio"], "2027-01-01")

    def test_init_db_idempotente_y_un_solo_activo(self):
        dbm.init_db()
        dbm.init_db()
        c = bd()
        activos = c.execute("SELECT COUNT(*) FROM periodos WHERE estado = 'activo'").fetchone()[0]
        tablas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        c.close()
        self.assertEqual(activos, 1)
        self.assertTrue({"periodos", "inscripciones", "jefes_carrera", "jefe_carreras"} <= tablas)

    def test_migracion_desde_bd_antigua(self):
        """Rama de migración: una BD sin columnas periodo_id recibe columnas y relleno."""
        import tempfile
        ruta = os.path.join(tempfile.mkdtemp(), "vieja.db")
        con = sqlite3.connect(ruta)
        con.executescript("""
            CREATE TABLE grupos (id TEXT PRIMARY KEY, nombre TEXT, carrera TEXT, semestre INTEGER);
            INSERT INTO grupos VALUES ('G-1', 'Grupo 1', 'Ingeniería Civil', 1);
        """)
        con.commit(); con.close()
        original = dbm.DB_PATH
        try:
            dbm.DB_PATH = ruta
            dbm.init_db()
            c = dbm.get_connection()
            g = c.execute("SELECT periodo_id, clave FROM grupos WHERE id = 'G-1'").fetchone()
            activo = c.execute("SELECT id FROM periodos WHERE estado = 'activo'").fetchone()[0]
            c.close()
        finally:
            dbm.DB_PATH = original
        self.assertEqual(g["periodo_id"], activo)
        self.assertEqual(g["clave"], "G-1")


# ───────────────────────── backend.auth ─────────────────────────
class TestAuth(unittest.TestCase):
    def test_hash_formato_y_sal_distinta(self):
        a, b = auth.hash_password("x" * 8), auth.hash_password("x" * 8)
        self.assertTrue(a.startswith("pbkdf2_sha256$600000$"))
        self.assertNotEqual(a, b)  # sal aleatoria

    def test_verify_ramas(self):
        h = auth.hash_password("correcta", iterations=1000)
        self.assertTrue(auth.verify_password("correcta", h))
        self.assertFalse(auth.verify_password("incorrecta", h))
        self.assertFalse(auth.verify_password("x", ""))               # hash vacío
        self.assertFalse(auth.verify_password("x", "basura"))         # formato desconocido
        self.assertFalse(auth.verify_password("x", "pbkdf2_sha256$no$es$valido"))  # excepción controlada
        import hashlib
        legado = "abc:" + hashlib.sha256(("abc" + "vieja").encode()).hexdigest()
        self.assertTrue(auth.verify_password("vieja", legado))      # formato heredado

    def test_needs_rehash_ramas(self):
        self.assertTrue(auth.needs_rehash(""))
        self.assertTrue(auth.needs_rehash("sal:abc"))
        self.assertTrue(auth.needs_rehash(auth.hash_password("x", iterations=1000)))
        self.assertFalse(auth.needs_rehash(auth.hash_password("x")))
        self.assertTrue(auth.needs_rehash("pbkdf2_sha256$NaN$a$b"))

    def test_bloqueo_por_intentos_limite_5(self):
        auth._FAILED_ATTEMPTS.clear(); auth._LOCKED_UNTIL.clear()
        for _ in range(4):
            auth.register_failed_login("1.1.1.1", "pepe")
        self.assertEqual(auth.login_locked_seconds("1.1.1.1", "pepe"), 0)   # 4 fallos: aún no
        auth.register_failed_login("1.1.1.1", "pepe")
        self.assertGreater(auth.login_locked_seconds("1.1.1.1", "pepe"), 0)  # 5.º fallo: bloqueado
        auth.reset_failed_logins("1.1.1.1", "pepe")
        auth._LOCKED_UNTIL.clear()

    def test_sesiones_crear_validar_destruir(self):
        t1 = auth.create_session("j", 99, "J", rol="jefe_carrera", extra_data={"carreras": [ISC]})
        t2 = auth.create_session("j", 99, "J", rol="jefe_carrera")
        self.assertEqual(auth.validate_session(t1)["carreras"], [ISC])
        self.assertEqual(auth.destroy_sessions_for("jefe_carrera", 99, except_token=t2), 1)
        self.assertIsNone(auth.validate_session(t1))
        self.assertIsNotNone(auth.validate_session(t2))
        self.assertTrue(auth.destroy_session(t2))
        self.assertFalse(auth.destroy_session("no-existe"))


# ───────────────────────── backend.app (helpers de permisos) ─────────────────────────
class TestPermisos(unittest.TestCase):
    def test_carreras_de(self):
        self.assertIsNone(appmod.carreras_de({"rol": "administrador"}))
        self.assertEqual(appmod.carreras_de({"rol": "jefe_carrera", "carreras": [ISC]}), [ISC])
        self.assertEqual(appmod.carreras_de({"rol": "jefe_carrera"}), [])   # sin carreras: nada

    def test_exigir_carrera(self):
        appmod.exigir_carrera({"rol": "administrador"}, CIV)                        # admin: todo
        appmod.exigir_carrera({"rol": "jefe_carrera", "carreras": [ISC]}, ISC)      # propia
        with self.assertRaises(HTTPException) as e:
            appmod.exigir_carrera({"rol": "jefe_carrera", "carreras": [ISC]}, CIV)  # ajena
        self.assertEqual(e.exception.status_code, 403)

    def test_get_current_staff_ramas(self):
        tok_a = auth.create_session("a", 1, "A", rol="administrador")
        tok_j = auth.create_session("j", 2, "J", rol="jefe_carrera", extra_data={"carreras": [ISC]})
        tok_d = auth.create_session("d", "D", "D", rol="docente")
        self.assertIsNone(appmod.get_current_staff(f"Bearer {tok_a}")["carreras"])
        self.assertEqual(appmod.get_current_staff(f"Bearer {tok_j}")["carreras"], [ISC])
        with self.assertRaises(HTTPException):
            appmod.get_current_staff(f"Bearer {tok_d}")

    def test_periodo_activo_sin_periodo(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE periodos (id TEXT, estado TEXT)")
        with self.assertRaises(HTTPException) as e:
            appmod.periodo_activo(con.cursor())
        self.assertEqual(e.exception.status_code, 500)


# ───────────────────────── backend.horarios_import ─────────────────────────
class TestHoras(unittest.TestCase):
    def test_hora_todas_las_ramas(self):
        casos = [
            (None, None), ("", None),
            (datetime(2026, 1, 1, 7, 5), "07:05"),   # datetime de Excel
            (dtime(13, 0), "13:00"),                 # time de Excel
            (0.5, "12:00"), (0.0, "00:00"),           # fracción de día
            (1.5, None), (-0.1, None), (7, None),     # números fuera de 0..1 (antes 1.5 daba 15:00)
            ("7.30", "07:30"), ("7.30 pm", "19:30"),  # punto como separador de hora
            ("7", "07:00"), ("7:00", "07:00"), ("07:00:00", "07:00"),
            ("7 pm", "19:00"), ("7:30 p.m.", "19:30"), ("12 am", "00:00"), ("12 pm", "12:00"),
            ("24:00", None), ("7:60", None), ("siete", None), ("7:5", None),
        ]
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(hi._hora(valor), esperado)

    def test_norm_y_clave(self):
        self.assertEqual(hi._norm("  Programación   WEB "), "programacion web")
        self.assertEqual(hi._clave("LAB-1 — Lab de Redes"), "LAB-1")
        self.assertEqual(hi._clave("LAB-1 - Lab"), "LAB-1")
        self.assertEqual(hi._clave(None), "")

    def test_traslape_limites(self):
        self.assertTrue(hi._se_traslapan("07:00", "09:00", "08:00", "10:00"))
        self.assertFalse(hi._se_traslapan("07:00", "09:00", "09:00", "11:00"))  # se tocan: no chocan
        self.assertTrue(hi._se_traslapan("07:00", "11:00", "08:00", "09:00"))   # contenido


class TestValidarHorario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sembrar()
        cls.periodo = periodo_activo_id()

    def setUp(self):
        self.con = bd()
        self.cur = self.con.cursor()

    def tearDown(self):
        self.con.close()

    def base(self, **cambios):
        d = {"dia": "Lunes", "hora_inicio": "07:00", "hora_fin": "09:00", "laboratorio": "LAB-RED",
             "grupo": "ISC-501", "docente": "D-100", "materia": "Programación Web"}
        d.update(cambios)
        return d

    def validar(self, datos, ocupados=None, carreras=None):
        return hi.validar_horario(datos, self.cur, ocupados or [], periodo_id=self.periodo, carreras=carreras)

    def test_camino_feliz(self):
        h, err = self.validar(self.base())
        self.assertEqual(err, [])
        self.assertEqual((h["grupo_id"], h["docente_id"], h["periodo_id"]), ("ISC-501", "DOC-ISC", self.periodo))

    def test_cada_rama_de_error(self):
        casos = [
            ({"dia": "Domingo"}, "Día inválido"),
            ({"hora_inicio": "xx"}, "Hora de inicio inválida"),
            ({"hora_fin": ""}, "Hora de fin inválida"),
            ({"hora_inicio": "09:00", "hora_fin": "09:00"}, "después de la de inicio"),
            ({"hora_inicio": "05:59", "hora_fin": "07:00"}, "entre 06:00 y 22:00"),
            ({"hora_inicio": "21:00", "hora_fin": "22:01"}, "entre 06:00 y 22:00"),
            ({"laboratorio": ""}, "Falta el laboratorio"),
            ({"laboratorio": "LAB-X"}, "no existe"),
            ({"grupo": ""}, "Falta el grupo"),
            ({"grupo": "NO-EXISTE"}, "no existe en el periodo actual"),
            ({"docente": ""}, "Falta el docente"),
            ({"docente": "D-999"}, "no existe"),
            ({"docente": "22030001"}, "no está registrado como docente"),
            ({"materia": "  "}, "Falta la materia"),
            ({"materia": "Robótica Espacial"}, "no está en las materias oficiales"),
            ({"materia": "Topografía"}, "no pertenece a la carrera del grupo"),
        ]
        for cambio, texto in casos:
            with self.subTest(cambio=cambio):
                h, err = self.validar(self.base(**cambio))
                self.assertIsNone(h)
                self.assertTrue(any(texto in e for e in err), err)

    def test_limites_validos_06_y_22(self):
        h, err = self.validar(self.base(hora_inicio="06:00", hora_fin="22:00", dia="Sábado"))
        self.assertEqual(err, [])

    def test_busqueda_por_nombre_sin_acentos(self):
        h, err = self.validar(self.base(laboratorio="lab de redes", docente="laura perez", dia="miercoles"))
        self.assertEqual(err, [], err)
        self.assertEqual((h["laboratorio_id"], h["dia_semana"]), ("LAB-RED", "Miércoles"))

    def test_choques_del_lote(self):
        # (lab, dia, ini, fin, grupo, docente)
        casos = [
            (("LAB-RED", "Lunes", "08:00", "10:00", "OTRO", "OTRO"), "laboratorio LAB-RED ya está ocupado"),
            (("LAB-CIV", "Lunes", "08:00", "10:00", "ISC-501", "OTRO"), "grupo ISC-501 ya tiene clase"),
            (("LAB-CIV", "Lunes", "08:00", "10:00", "OTRO", "DOC-ISC"), "docente ya da clase"),
        ]
        for ocupado, texto in casos:
            with self.subTest(ocupado=ocupado):
                h, err = self.validar(self.base(), ocupados=[ocupado])
                self.assertTrue(any(texto in e for e in err), err)
        h, err = self.validar(self.base(), ocupados=[("LAB-RED", "Martes", "07:00", "09:00", "X", "Y")])
        self.assertEqual(err, [])  # otro día: no choca

    def test_rama_carreras_del_jefe(self):
        h, err = self.validar(self.base(grupo="CIV-301", materia="Topografía", docente="D-200", laboratorio="LAB-CIV"), carreras=[ISC])
        self.assertTrue(any("no está a su cargo" in e for e in err))
        h, err = self.validar(self.base(), carreras=[ISC])
        self.assertEqual(err, [])

    def test_actividad_sin_docente_ni_grupo(self):
        h, err = self.validar(self.base(docente="SIN-DOCENTE", grupo="", materia="  Práctica   de Redes "))
        self.assertEqual(err, [], err)
        self.assertEqual((h["docente_id"], h["grupo_id"], h["materia"]), (None, None, "Práctica de Redes"))
        # Alias aceptados y la opción de la plantilla "SIN-DOCENTE — ..."
        for alias in ("sin docente", "Actividad", f"SIN-DOCENTE{hi.SEPARADOR}{hi.SIN_DOCENTE_TEXTO}"):
            with self.subTest(alias=alias):
                self.assertEqual(self.validar(self.base(docente=alias, grupo="", materia="Club IoT"))[1], [])
        h, err = self.validar(self.base(docente="SIN-DOCENTE", grupo="", materia=""))
        self.assertTrue(any("Falta el nombre de la actividad" in e for e in err))

    def test_actividad_sin_docente_aparta_el_laboratorio(self):
        h, err = self.validar(self.base(), ocupados=[("LAB-RED", "Lunes", "08:00", "09:00", None, None, "Club IoT")])
        self.assertTrue(any("LAB-RED ya está ocupado" in e for e in err), err)
        # Dos actividades sin docente ni grupo en labs distintos no chocan entre sí
        h, err = self.validar(self.base(docente="SIN-DOCENTE", grupo="", materia="Club IoT", laboratorio="LAB-CIV"),
                              ocupados=[("LAB-RED", "Lunes", "07:00", "09:00", None, None, "Club IoT")])
        self.assertEqual(err, [], err)

    def test_actividad_sin_grupo_respeta_carreras_del_jefe(self):
        h, err = self.validar(self.base(docente="SIN-DOCENTE", grupo="", materia="Práctica", laboratorio="LAB-CIV"), carreras=[ISC])
        self.assertTrue(any("no está a su cargo" in e for e in err), err)
        self.assertEqual(self.validar(self.base(docente="SIN-DOCENTE", grupo="", materia="Práctica"), carreras=[ISC])[1], [])

    def test_clase_compartida_varios_grupos(self):
        # Inglés para 7A y 7B juntos: misma materia, mismas horas, mismo lab, otro grupo -> se permite
        ocupado = ("LAB-RED", "Lunes", "07:00", "09:00", "OTRO-GRUPO", None, "Inglés VII")
        h, err = self.validar(self.base(docente="SIN-DOCENTE", materia="Inglés VII"), ocupados=[ocupado])
        self.assertEqual(err, [], err)
        # Si cambia la materia o las horas, sí es choque
        h, err = self.validar(self.base(docente="SIN-DOCENTE", materia="Club IoT"), ocupados=[ocupado])
        self.assertTrue(any("ya está ocupado" in e for e in err), err)
        h, err = self.validar(self.base(docente="SIN-DOCENTE", materia="Inglés VII", hora_fin="08:00"), ocupados=[ocupado])
        self.assertTrue(any("ya está ocupado" in e for e in err), err)

    def test_grupo_de_otro_periodo_no_se_encuentra(self):
        h, err = hi.validar_horario(self.base(), self.cur, [], periodo_id="1999-1")
        self.assertTrue(any("no existe en el periodo actual" in e for e in err))


class TestArchivos(unittest.TestCase):
    def test_csv_punto_y_coma_cp1252(self):
        texto = "Día;Hora inicio;Hora fin;Laboratorio;Grupo;Docente;Materia\nLunes;7:00;9:00;LAB-RED;ISC-501;D-100;Programación Web\n"
        filas, error = hi.leer_archivo("h.csv", texto.encode("cp1252"))
        self.assertIsNone(error)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["materia"], "Programación Web")

    def test_csv_coma_utf8_bom_y_alias(self):
        texto = "﻿dia,entrada,salida,salon,grupo,maestro,asignatura\nMartes,7,9,LAB-RED,ISC-501,D-100,Programación Web\n"
        filas, error = hi.leer_archivo("h.csv", texto.encode("utf-8"))
        self.assertEqual((filas[0]["dia"], filas[0]["docente"]), ("Martes", "D-100"))

    def test_ramas_de_error(self):
        casos = [
            ("h.pdf", b"%PDF", "Formato no soportado"),
            ("h.xlsx", b"no es excel", "No se pudo abrir"),
            ("h.csv", b"", "No se encontraron los encabezados"),
            ("h.csv", "Día,Hora inicio,Hora fin,Laboratorio,Grupo,Docente\n".encode(), "Faltan columnas: Materia"),
        ]
        for nombre, contenido, texto in casos:
            with self.subTest(nombre=nombre, texto=texto):
                filas, error = hi.leer_archivo(nombre, contenido)
                self.assertEqual(filas, [])
                self.assertIn(texto, error or "")

    def test_filas_vacias_se_omiten_y_numeran(self):
        texto = "Día,Hora inicio,Hora fin,Laboratorio,Grupo,Docente,Materia\n,,,,,,\nLunes,7,9,L,G,D,M\n"
        filas, _ = hi.leer_archivo("h.csv", texto.encode())
        self.assertEqual([f["fila"] for f in filas], [3])

    def test_plantilla_filtra_por_carreras_y_periodo(self):
        sembrar()
        from openpyxl import load_workbook
        c = bd()
        try:
            contenido = hi.generar_plantilla(c.cursor(), periodo_activo_id(), [ISC], "Ago-Dic 2026")
        finally:
            c.close()
        L = load_workbook(io.BytesIO(contenido))["Listas"]
        valores = [str(L.cell(i, j).value or "") for i in range(1, 400) for j in range(1, 10)]
        self.assertTrue(any("ISC-501" in v for v in valores))
        self.assertFalse(any("CIV-301" in v for v in valores))
        self.assertFalse(any(v == "Topografía" for v in valores))


# ───────────────────────── Raspberry Pi: validate_schedule ─────────────────────────
def _cargar_validate_schedule():
    """Se extrae solo el método (rpi_main importa cámara/GPIO que no existen en la PC)."""
    src = io.open(os.path.join(RAIZ, "raspberry_pi", "rpi_main.py"), encoding="utf-8").read()
    arbol = ast.parse(src)
    fn = [n for c in arbol.body if isinstance(c, ast.ClassDef) for n in c.body
          if isinstance(n, ast.FunctionDef) and n.name == "validate_schedule"][0]
    ns = {"datetime": datetime, "timedelta": timedelta}
    exec(compile(ast.Module([fn], []), "rpi_main.validate_schedule", "exec"), ns)
    return ns["validate_schedule"]


class TestRaspberry(unittest.TestCase):
    validar = staticmethod(_cargar_validate_schedule())

    def puerta(self, tolerancia=10):
        cache = {"horarios": [{"dia_semana": "Martes", "grupo_id": "G1", "docente_id": "D1",
                               "hora_inicio": "07:00", "hora_fin": "09:00", "materia": "M"}]}
        if tolerancia is not None:
            cache["tolerancia_min"] = tolerancia
        return types.SimpleNamespace(offline_cache=cache)

    def hora(self, hhmm):
        h, m = map(int, hhmm.split(":"))
        return datetime(2026, 11, 24, h, m)  # martes

    def test_limites_alumno_con_tolerancia_10(self):
        al = {"tipo": "alumno", "grupo_id": "G1", "usuario_id": "A"}
        for hhmm, esperado in [("06:49", False), ("06:50", True), ("07:00", True), ("09:00", True), ("09:01", False)]:
            with self.subTest(hora=hhmm):
                self.assertEqual(self.validar(self.puerta(), al, self.hora(hhmm))[0], esperado)

    def test_docente_y_otro_grupo(self):
        self.assertTrue(self.validar(self.puerta(), {"tipo": "docente", "usuario_id": "D1"}, self.hora("06:55"))[0])
        self.assertFalse(self.validar(self.puerta(), {"tipo": "alumno", "grupo_id": "G2"}, self.hora("07:30"))[0])

    def test_limpieza_y_admin_siempre(self):
        self.assertTrue(self.validar(self.puerta(), {"tipo": "personal_limpieza"}, self.hora("23:00"))[0])
        self.assertTrue(self.validar(self.puerta(), {"tipo": "administrador"}, self.hora("23:00"))[0])

    def test_tolerancia_ausente_invalida_o_negativa(self):
        al = {"tipo": "alumno", "grupo_id": "G1"}
        self.assertTrue(self.validar(self.puerta(None), al, self.hora("06:50"))[0])     # cache viejo: 10 por defecto
        self.assertTrue(self.validar(self.puerta("abc"), al, self.hora("06:50"))[0])    # valor basura: 10
        self.assertFalse(self.validar(self.puerta(-5), al, self.hora("06:59"))[0])      # negativo: se toma 0
        self.assertTrue(self.validar(self.puerta(0), al, self.hora("07:00"))[0])

    def test_otro_dia(self):
        al = {"tipo": "alumno", "grupo_id": "G1"}
        self.assertFalse(self.validar(self.puerta(), al, datetime(2026, 11, 25, 7, 30))[0])  # miércoles


# ───────────────────────── Portal (JavaScript): hpEstadoClase ─────────────────────────
@unittest.skipUnless(shutil.which("node"), "Node.js no está instalado")
def _cargar_recarga_config():
    """Extrae reload_config_if_changed y _mtime de rpi_main (sin importar cámara/GPIO)."""
    src = io.open(os.path.join(RAIZ, "raspberry_pi", "rpi_main.py"), encoding="utf-8").read()
    arbol = ast.parse(src)
    fns = [n for c in arbol.body if isinstance(c, ast.ClassDef) for n in c.body
           if isinstance(n, ast.FunctionDef) and n.name in ("reload_config_if_changed", "_mtime")]
    for f in fns:
        f.decorator_list = []
    leer = lambda ruta, defecto: json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else defecto
    ns = {"os": os, "_read_json": leer, "_importar_config_externo": lambda: None}
    exec(compile(ast.Module(fns, []), "rpi_main.recarga", "exec"), ns)
    return ns


class TestRaspberryConfig(unittest.TestCase):
    def test_recarga_config_sin_reiniciar(self):
        import tempfile
        ns = _cargar_recarga_config()
        carpeta = tempfile.mkdtemp()
        ruta = os.path.join(carpeta, "config.json")
        cfg = {"dispositivo_id": "D1", "token_api": "viejo", "servidor_url": "http://1.1.1.1:8000/"}
        json.dump(cfg, open(ruta, "w", encoding="utf-8"))
        nodo = types.SimpleNamespace(config_path=ruta, server_url="http://1.1.1.1:8000", device_id="D1",
                                     token_api="viejo", heartbeat_interval=300, online=True, config={})
        nodo._mtime = lambda p: ns["_mtime"](p)
        nodo._config_mtime = nodo._mtime(ruta)
        recargar = lambda: ns["reload_config_if_changed"](nodo)
        recargar()                                              # sin cambios: no toca nada
        self.assertEqual(nodo.token_api, "viejo")
        self.assertTrue(nodo.online)
        json.dump({**cfg, "token_api": "nuevo", "servidor_url": "http://2.2.2.2:8000/"}, open(ruta, "w", encoding="utf-8"))
        os.utime(ruta, (nodo._config_mtime + 5, nodo._config_mtime + 5))
        recargar()                                              # archivo nuevo: aplica token e IP
        self.assertEqual((nodo.token_api, nodo.server_url, nodo.online), ("nuevo", "http://2.2.2.2:8000", False))
        json.dump({"token_api": ""}, open(ruta, "w", encoding="utf-8"))
        os.utime(ruta, (nodo._config_mtime + 10, nodo._config_mtime + 10))
        recargar()                                              # archivo sin token: se ignora
        self.assertEqual(nodo.token_api, "nuevo")
        shutil.rmtree(carpeta)


class TestPortalJS(unittest.TestCase):
    def test_estado_de_la_clase_limites(self):
        ruta = os.path.join(RAIZ, "frontend", "scripts", "horario_portal.js").replace("\\", "/")
        js = f"""
        const fs = require('fs'); const vm = require('vm');
        const ctx = {{ esc: x => String(x), setInterval: () => 0, document: {{}}, window: {{}}, console }};
        vm.createContext(ctx);
        vm.runInContext(fs.readFileSync('{ruta}', 'utf8') + '; this.hpEstadoClase = hpEstadoClase; this.hpHHMM = hpHHMM; this.hpEnMinutos = hpEnMinutos;', ctx);
        const c = {{ hora_inicio: '07:00', hora_fin: '09:00' }};
        const m = s => {{ const [h, mi] = s.split(':').map(Number); return h * 60 + mi; }};
        const r = ['06:49', '06:50', '09:00', '09:01'].map(h => ctx.hpEstadoClase(c, m(h), 10).tipo);
        console.log(JSON.stringify({{ r, abre: ctx.hpHHMM(ctx.hpEstadoClase(c, m('06:00'), 10).abre),
          falta: ctx.hpEstadoClase(c, m('06:00'), 10).faltan, txt: [ctx.hpEnMinutos(5), ctx.hpEnMinutos(60), ctx.hpEnMinutos(125)] }}));
        """
        salida = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
        self.assertEqual(salida.returncode, 0, salida.stderr)
        d = json.loads(salida.stdout)
        self.assertEqual(d["r"], ["espera", "permitido", "permitido", "terminada"])
        self.assertEqual((d["abre"], d["falta"]), ("06:50", 50))
        self.assertEqual(d["txt"], ["5 min", "1 h", "2 h 5 min"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
