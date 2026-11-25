"""
PRUEBAS DE CAJA GRIS
Se actúa por la API (como un usuario) y se revisa el estado interno conociendo el esquema
de la base de datos: qué se guardó, en qué periodo, integridad referencial, atomicidad,
sesiones en memoria y que la BD real del sistema no se toque.
"""
import sqlite3
import unittest

from _entorno import (cliente as C, admin, entrar, sembrar, bd, periodo_activo_id, bd_real_intacta,
                      ISC, CIV, CLAVE_PRUEBA)
import backend.auth as auth
import database.database as dbm


def uno(sql, *params):
    c = bd()
    try:
        return c.execute(sql, params).fetchone()
    finally:
        c.close()


def todos(sql, *params):
    c = bd()
    try:
        return [dict(r) for r in c.execute(sql, params).fetchall()]
    finally:
        c.close()


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datos = sembrar()
        cls.A = admin()
        cls.periodo = periodo_activo_id()


class TestA_Registro(Base):
    def test_grupo_guarda_periodo_y_clave(self):
        C.post("/api/groups", headers=self.A, json={"id": "gg-1", "nombre": "Grupo G", "carrera": ISC, "semestre": 2})
        g = uno("SELECT id, clave, periodo_id FROM grupos WHERE id = 'GG-1'")
        self.assertEqual(tuple(g), ("GG-1", "GG-1", self.periodo))

    def test_horario_guarda_periodo(self):
        r = C.post("/api/schedules", headers=self.A, json={"grupo_id": "ISC-501", "laboratorio_id": "LAB-RED", "docente_id": "DOC-ISC",
                   "materia": "Programación Web", "dia_semana": "Lunes", "hora_inicio": "07:00", "hora_fin": "09:00"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(uno("SELECT periodo_id FROM horarios WHERE grupo_id = 'ISC-501' AND dia_semana = 'Lunes'")[0], self.periodo)

    def test_jefe_contrasena_cifrada_y_no_expuesta(self):
        fila = uno("SELECT password_hash FROM jefes_carrera WHERE username = 'jefe.isc'")
        self.assertTrue(fila[0].startswith("pbkdf2_sha256$"))
        self.assertNotIn(CLAVE_PRUEBA, fila[0])
        self.assertNotIn("password_hash", C.get("/api/jefes", headers=self.A).text)

    def test_carreras_del_jefe_en_tabla_relacion(self):
        jid = uno("SELECT id FROM jefes_carrera WHERE username = 'jefe.isc'")[0]
        self.assertEqual([r["carrera"] for r in todos("SELECT carrera FROM jefe_carreras WHERE jefe_id = ?", jid)], [ISC])

    def test_baja_de_docente_no_borra_fila(self):
        J = entrar("jefe.isc", CLAVE_PRUEBA)
        C.post("/api/users", headers=J, json={"id": "DOC-BAJA", "nombre_completo": "Docente Baja", "matricula_clave": "D-777",
                                              "tipo": "docente", "carrera": ISC, "grupo_id": None, "estado": "activo"})
        C.delete("/api/users/DOC-BAJA", headers=J)
        self.assertEqual(uno("SELECT estado FROM usuarios WHERE id = 'DOC-BAJA'")[0], "inactivo")


class TestB_Accesos(Base):
    def test_acceso_en_linea_guarda_periodo_activo(self):
        tok = self.datos["token_rpi"]
        r = C.post("/api/iot/access-attempt", json={"dispositivo_id": "RPI-RED", "token_api": tok, "usuario_id": "22030001",
                                                    "resultado": "permitido", "motivo": "Prueba gris"})
        self.assertEqual(r.status_code, 200, r.text)
        fila = uno("SELECT usuario_id, periodo_id FROM registros_acceso WHERE motivo = 'Prueba gris'")
        self.assertEqual(tuple(fila), ("AL-1", self.periodo))   # la matrícula se resuelve al id interno

    def test_lote_offline_usa_periodo_de_la_fecha(self):
        c = bd()
        c.execute("INSERT OR IGNORE INTO periodos (id, nombre, fecha_inicio, fecha_fin, estado) VALUES ('2020-1', 'Ene-Jun 2020', '2020-01-01', '2020-06-30', 'cerrado')")
        c.commit(); c.close()
        tok = self.datos["token_rpi"]
        lote = [
            {"dispositivo_id": "RPI-RED", "token_api": tok, "usuario_id": "AL-1", "resultado": "permitido", "motivo": "offline-2020", "fecha_hora": "2020-03-10 08:00:00", "sincronizado_offline": True},
            {"dispositivo_id": "RPI-RED", "token_api": tok, "usuario_id": "AL-1", "resultado": "denegado", "motivo": "offline-sin-periodo", "fecha_hora": "2019-07-10 08:00:00", "sincronizado_offline": True},
        ]
        self.assertEqual(C.post("/api/iot/access-attempts-batch", json=lote).json()["inserted"], 2)
        self.assertEqual(C.post("/api/iot/access-attempts-batch", json=lote).json()["inserted"], 0)   # reenviar no duplica
        self.assertEqual(uno("SELECT periodo_id FROM registros_acceso WHERE motivo = 'offline-2020'")[0], "2020-1")
        self.assertEqual(uno("SELECT periodo_id FROM registros_acceso WHERE motivo = 'offline-sin-periodo'")[0], self.periodo)

    def test_lote_con_token_ajeno_rechazado(self):
        tok = self.datos["token_rpi"]
        lote = [{"dispositivo_id": "RPI-RED", "token_api": tok, "resultado": "permitido", "motivo": "a"},
                {"dispositivo_id": "OTRA", "token_api": "falso", "resultado": "permitido", "motivo": "b"}]
        self.assertEqual(C.post("/api/iot/access-attempts-batch", json=lote).status_code, 403)
        self.assertIsNone(uno("SELECT 1 FROM registros_acceso WHERE motivo = 'a'"))

    def test_sincronizacion_raspberry(self):
        r = C.get("/api/iot/sync-offline-rules", headers={"X-Device-Token": self.datos["token_rpi"]}, params={"dispositivo_id": "RPI-RED"}).json()
        self.assertEqual(r["tolerancia_min"], 10)
        en_bd = uno("SELECT COUNT(*) FROM horarios WHERE laboratorio_id = 'LAB-RED' AND periodo_id = ?", self.periodo)[0]
        self.assertEqual(len(r["horarios"]), en_bd)


class TestC_Sesiones(Base):
    def test_desactivar_jefe_borra_sus_sesiones_en_memoria(self):
        C.post("/api/jefes", headers=self.A, json={"username": "jefe.ses", "nombre": "Jefe Sesiones", "password": "12345678", "carreras": [CIV]})
        jid = uno("SELECT id FROM jefes_carrera WHERE username = 'jefe.ses'")[0]
        entrar("jefe.ses", "12345678"); entrar("jefe.ses", "12345678")
        contar = lambda: sum(1 for s in auth.ACTIVE_SESSIONS.values() if s.get("rol") == "jefe_carrera" and s.get("user_id") == jid)
        self.assertEqual(contar(), 2)
        C.post(f"/api/jefes/{jid}/toggle", headers=self.A)
        self.assertEqual(contar(), 0)
        self.assertEqual(uno("SELECT activo FROM jefes_carrera WHERE id = ?", jid)[0], 0)


class TestD_AprobacionYDetalle(Base):
    def pendiente(self, uid, clave, carrera):
        C.post("/api/users", headers=self.A, json={"id": uid, "nombre_completo": f"Docente {uid}", "matricula_clave": clave,
                                                   "tipo": "docente", "carrera": carrera, "grupo_id": None, "estado": "activo"})
        c = bd(); c.execute("UPDATE usuarios SET cuenta_aprobada = 0 WHERE id = ?", (uid,)); c.commit(); c.close()

    def test_jefe_aprueba_solo_docentes_de_su_carrera(self):
        J = entrar("jefe.isc", CLAVE_PRUEBA)
        self.pendiente("DOC-P1", "D-501", ISC)
        self.pendiente("DOC-P2", "D-502", CIV)
        self.assertEqual(C.post("/api/users/DOC-P2/approve-account", headers=J).status_code, 403)
        self.assertEqual(uno("SELECT cuenta_aprobada FROM usuarios WHERE id = 'DOC-P2'")[0], 0)   # no cambió
        self.assertEqual(C.post("/api/users/DOC-P1/approve-account", headers=J).status_code, 200)
        self.assertEqual(uno("SELECT cuenta_aprobada FROM usuarios WHERE id = 'DOC-P1'")[0], 1)
        self.assertEqual(C.post("/api/users/DOC-P2/approve-account", headers=self.A).status_code, 200)

    def test_detalle_de_usuario_por_rol(self):
        J = entrar("jefe.isc", CLAVE_PRUEBA)
        d = C.get("/api/users/DOC-ISC/details", headers=J).json()
        self.assertNotIn("password_hash", d["usuario"])
        self.assertEqual(d["inscripciones"], [])
        self.assertEqual(C.get("/api/users/DOC-CIV/details", headers=J).status_code, 403)
        self.assertEqual(C.get("/api/users/AL-1/details", headers=J).status_code, 403)       # no es docente
        self.assertEqual(C.get("/api/users/AL-1/details", headers=self.A).status_code, 200)


class _RedDePrueba:
    """Sustituye a 'requests' del nodo: manda las peticiones al TestClient; la URL sin red falla."""
    def __init__(self, base):
        self.base = base

    def _ir(self, metodo, url, **kw):
        if not url.startswith(self.base):
            raise ConnectionError("sin red")
        kw.pop("timeout", None)
        return getattr(C, metodo)(url[len(self.base):], **kw)

    def get(self, url, **kw):
        return self._ir("get", url, **kw)

    def post(self, url, **kw):
        return self._ir("post", url, **kw)


class TestE_SimuladorDePuerta(Base):
    """El simulador escribe por la API como una Raspberry y todo queda ligado a SIM-<LAB>."""

    def test_simulador_registra_y_se_borra_sin_tocar_lo_real(self):
        import os, sys, tempfile
        from _entorno import RAIZ
        sys.path.insert(0, os.path.join(RAIZ, "tools"))
        import simulador_puerta as sp
        import rpi_main as rm
        import borrar_simulacion
        base = "http://servidor-prueba"
        red_original = rm.requests
        rm.requests = _RedDePrueba(base)
        sp.CARPETA_ESTADO = tempfile.mkdtemp()
        sp.PuertaSimulada.start_heartbeat_thread = lambda self: None   # sin hilos en la prueba
        sp.PuertaSimulada.start_command_thread = lambda self: None
        try:
            # Un acceso real de otra puerta, que NO debe borrarse
            tok = sembrar()["token_rpi"]
            C.post("/api/iot/access-attempt", json={"dispositivo_id": "RPI-RED", "token_api": tok, "usuario_id": "AL-1",
                                                    "resultado": "permitido", "motivo": "real"})
            reales = uno("SELECT COUNT(*) FROM registros_acceso WHERE dispositivo_id = 'RPI-RED'")[0]

            sim = sp.Simulador(sp.BD(dbm.DB_PATH), base)
            sim.usar_laboratorio("LAB-RED")
            self.assertEqual(sim.nodo.device_id, "SIM-LAB-RED")
            self.assertTrue(sim.estado()["en_linea"])
            self.assertIsNotNone(uno("SELECT ultima_senal FROM dispositivos WHERE id = 'SIM-LAB-RED'")[0])  # latido llegó

            alumno = [p for p in sim.bd.personas() if p["id"] == "AL-1"][0]
            r = sim.nodo.presentar(alumno, None)
            self.assertTrue(r["enviado"])
            self.assertEqual(sim.nodo.presentar(None, None)["resultado"], "denegado")        # rostro desconocido
            # Sin Wi-Fi: decide igual, guarda en cola y lo envía al reconectar
            sim.nodo.cortar_red(True)
            import time
            time.sleep(1.1)   # el servidor descarta como duplicado misma persona+puerta en el mismo segundo
            self.assertFalse(sim.nodo.presentar(alumno, None)["enviado"])
            self.assertEqual(sim.estado()["pendientes"], 1)
            sim.nodo.cortar_red(False)
            sim.nodo.sincronizar()
            self.assertEqual(sim.estado()["pendientes"], 0)
            filas = todos("SELECT usuario_id, resultado, sincronizado_offline FROM registros_acceso WHERE dispositivo_id = 'SIM-LAB-RED' ORDER BY id")
            self.assertEqual([f["sincronizado_offline"] for f in filas], [0, 0, 1])
            self.assertEqual([f["usuario_id"] for f in filas], ["AL-1", None, "AL-1"])

            # Borrar lo simulado: desaparece SIM-*, lo real se queda
            self.assertEqual(borrar_simulacion.main(["--db", dbm.DB_PATH, "--si"]), 0)
            self.assertEqual(uno("SELECT COUNT(*) FROM dispositivos WHERE id LIKE 'SIM-%'")[0], 0)
            self.assertEqual(uno("SELECT COUNT(*) FROM registros_acceso WHERE dispositivo_id = 'SIM-LAB-RED'")[0], 0)
            self.assertEqual(uno("SELECT COUNT(*) FROM registros_acceso WHERE dispositivo_id = 'RPI-RED'")[0], reales)
            self.assertIsNotNone(uno("SELECT id FROM dispositivos WHERE id = 'RPI-RED'"))
        finally:
            rm.requests = red_original


class TestZ_CierreDePeriodo(Base):
    """Al final: cambia el periodo activo."""

    def test_1_cierre_es_atomico_si_falla(self):
        grupos_antes = todos("SELECT id FROM grupos ORDER BY id")
        c = bd()
        c.execute("CREATE TRIGGER falla_cierre BEFORE UPDATE OF estado ON periodos BEGIN SELECT RAISE(ABORT, 'falla simulada'); END;")
        c.commit(); c.close()
        try:
            try:
                codigo = C.post("/api/periodos/cerrar", headers=self.A).status_code
            except Exception:
                codigo = 500
            self.assertGreaterEqual(codigo, 400)   # la API reporta el error (no dice "cerrado")
        finally:
            c = bd(); c.execute("DROP TRIGGER falla_cierre"); c.commit(); c.close()
        self.assertEqual(todos("SELECT id FROM grupos ORDER BY id"), grupos_antes)      # nada a medias
        self.assertEqual(uno("SELECT COUNT(*) FROM inscripciones")[0], 0)
        self.assertEqual(periodo_activo_id(), self.periodo)

    def test_2_cierre_estado_interno(self):
        p = self.periodo
        accesos_antes = uno("SELECT COUNT(*) FROM registros_acceso")[0]
        horarios_antes = uno("SELECT COUNT(*) FROM horarios WHERE periodo_id = ?", p)[0]
        r = C.post("/api/periodos/cerrar", headers=self.A)
        self.assertEqual(r.status_code, 200, r.text)
        nuevo = dbm.periodo_siguiente(p)["id"]
        self.assertEqual(periodo_activo_id(), nuevo)
        self.assertEqual(uno("SELECT estado FROM periodos WHERE id = ?", p)[0], "cerrado")
        # grupos archivados con id CLAVE@periodo y clave intacta
        g = uno("SELECT id, clave FROM grupos WHERE clave = 'ISC-501' AND periodo_id = ?", p)
        self.assertEqual(tuple(g), (f"ISC-501@{p}", "ISC-501"))
        # horarios siguen ligados a su grupo archivado
        self.assertEqual(uno("SELECT COUNT(*) FROM horarios WHERE grupo_id = ?", f"ISC-501@{p}")[0], horarios_antes - uno(
            "SELECT COUNT(*) FROM horarios WHERE periodo_id = ? AND grupo_id NOT LIKE 'ISC-501@%'", p)[0])
        # foto del alumno en su grupo
        i = uno("SELECT grupo_clave, grupo_id, periodo_id FROM inscripciones WHERE usuario_id = 'AL-1'")
        self.assertEqual(tuple(i), ("ISC-501", f"ISC-501@{p}", p))
        self.assertIsNone(uno("SELECT grupo_id FROM usuarios WHERE id = 'AL-1'")[0])
        hist = C.get("/api/users/AL-1/details", headers=self.A).json()["inscripciones"]
        self.assertEqual([(x["periodo_id"], x["grupo_clave"]) for x in hist], [(p, "ISC-501")])   # lo ve el admin
        # nada de accesos se pierde y la integridad queda bien
        self.assertEqual(uno("SELECT COUNT(*) FROM registros_acceso")[0], accesos_antes)
        c = bd()
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)     # conexiones nuevas con FK activas
        c.close()

    def test_3_historico_solo_lectura(self):
        hid = uno("SELECT id FROM horarios WHERE periodo_id = ?", self.periodo)[0]
        self.assertEqual(C.delete(f"/api/schedules/{hid}", headers=self.A).status_code, 400)
        self.assertIsNotNone(uno("SELECT 1 FROM horarios WHERE id = ?", hid))
        gid = f"ISC-501@{self.periodo}"
        self.assertEqual(C.put(f"/api/groups/{gid}", headers=self.A, json={"nombre": "Cambio", "carrera": ISC, "semestre": 5}).status_code, 400)

    def test_4_raspberry_deja_de_usar_horarios_viejos(self):
        r = C.get("/api/iot/sync-offline-rules", headers={"X-Device-Token": self.datos["token_rpi"]}, params={"dispositivo_id": "RPI-RED"}).json()
        self.assertEqual(r["horarios"], [])

    def test_5_clave_se_puede_reusar_y_segundo_cierre(self):
        self.assertEqual(C.post("/api/groups", headers=self.A, json={"id": "ISC-501", "nombre": "501 Sistemas", "carrera": ISC, "semestre": 5}).status_code, 200)
        self.assertEqual(C.post("/api/periodos/cerrar", headers=self.A).status_code, 200)
        claves = todos("SELECT id FROM grupos WHERE clave = 'ISC-501' ORDER BY id")
        self.assertEqual(len(claves), 2)   # uno por cada periodo cerrado, sin chocar

    def test_9_bd_real_intacta(self):
        self.assertTrue(bd_real_intacta())


if __name__ == "__main__":
    unittest.main(verbosity=2)
