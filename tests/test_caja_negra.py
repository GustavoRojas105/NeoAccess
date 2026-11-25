"""
PRUEBAS DE CAJA NEGRA
Solo se usa la API (entradas -> salidas), sin mirar la base de datos ni el código.
Técnicas: particiones de equivalencia, valores límite y matriz de permisos por rol.
"""
import io
import unittest
from datetime import datetime

from _entorno import cliente as C, admin, entrar, sembrar, limpiar_intentos, ISC, CIV, CLAVE_ADMIN, CLAVE_PRUEBA


def ids(lista):
    return [x["id"] for x in lista]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sembrar()
        cls.A = admin()
        cls.J = entrar("jefe.isc", CLAVE_PRUEBA)
        cls.AL = entrar("22030001", CLAVE_PRUEBA)
        cls.DO = entrar("D-100", CLAVE_PRUEBA)


# ───────────────────────── Inicio de sesión ─────────────────────────
class TestLogin(Base):
    def login(self, u, p):
        limpiar_intentos()
        return C.post("/api/auth/login", json={"username": u, "password": p})

    def test_particiones(self):
        casos = [
            ("admin.pruebas", CLAVE_ADMIN, 200, "administrador"),
            ("ADMIN.PRUEBAS", CLAVE_ADMIN, 200, "administrador"),   # sin distinguir mayúsculas
            ("jefe.isc", CLAVE_PRUEBA, 200, "jefe_carrera"),
            ("22030001", CLAVE_PRUEBA, 200, "alumno"),
            ("D-100", CLAVE_PRUEBA, 200, "docente"),
            ("admin.pruebas", "incorrecta", 401, None),
            ("no.existe", "loquesea123", 401, None),
            ("", "", 401, None),
        ]
        for u, p, codigo, rol in casos:
            with self.subTest(usuario=u):
                r = self.login(u, p)
                self.assertEqual(r.status_code, codigo, r.text)
                if rol:
                    self.assertEqual(r.json()["admin"]["rol"], rol)

    def test_jefe_recibe_sus_carreras(self):
        self.assertEqual(self.login("jefe.isc", CLAVE_PRUEBA).json()["admin"]["carreras"], [ISC])

    def test_bloqueo_tras_5_fallos(self):
        limpiar_intentos()
        codigos = [C.post("/api/auth/login", json={"username": "jefe.isc", "password": "mal"}).status_code for _ in range(6)]
        self.assertEqual(codigos[:5], [401] * 5)
        self.assertEqual(codigos[5], 429)
        limpiar_intentos()

    def test_sin_token_y_token_falso(self):
        self.assertEqual(C.get("/api/groups").status_code, 401)
        self.assertEqual(C.get("/api/groups", headers={"Authorization": "Bearer falso"}).status_code, 401)


# ───────────────────────── Matriz de permisos ─────────────────────────
class TestMatrizPermisos(Base):
    """Cada fila: (método, ruta, admin, jefe, docente, alumno). True = debe permitirse (2xx)."""
    MATRIZ = [
        ("GET", "/api/labs", True, True, False, False),
        ("GET", "/api/groups", True, True, False, False),
        ("GET", "/api/schedules", True, True, False, False),
        ("GET", "/api/schedules/template", True, True, False, False),
        ("GET", "/api/users?tipo=docente", True, True, False, False),
        ("GET", "/api/reports/data", True, True, False, False),
        ("GET", "/api/reports/export-csv", True, True, False, False),
        ("GET", "/api/periodos", True, True, False, False),
        ("GET", "/api/jefes", True, False, False, False),
        ("GET", "/api/admins", True, False, False, False),
        ("GET", "/api/devices", True, False, False, False),
        ("GET", "/api/metrics/summary", True, False, False, False),
        ("GET", "/api/reports/cleaning", True, False, False, False),
        ("GET", "/api/portal/student-data", False, False, False, True),
        ("GET", "/api/portal/teacher-data", False, False, True, False),
    ]

    def test_matriz(self):
        roles = {"admin": self.A, "jefe": self.J, "docente": self.DO, "alumno": self.AL}
        for metodo, ruta, *permitidos in self.MATRIZ:
            for (rol, H), permitido in zip(roles.items(), permitidos):
                with self.subTest(ruta=ruta, rol=rol):
                    r = C.request(metodo, ruta, headers=H)
                    if permitido:
                        self.assertLess(r.status_code, 300, r.text[:150])
                    else:
                        self.assertIn(r.status_code, (401, 403), r.text[:150])

    def test_acciones_prohibidas_al_jefe(self):
        prohibidas = [
            ("POST", "/api/periodos/cerrar", None),
            ("POST", "/api/labs", {"id": "LAB-Z", "nombre": "Z", "edificio": "Edificio 2", "carrera": ISC, "capacidad": 3, "descripcion": ""}),
            ("POST", "/api/jefes", {"username": "otro.jefe", "nombre": "Otro Jefe", "password": "12345678", "carreras": [ISC]}),
            ("DELETE", "/api/users/DOC-ISC/permanent", None),
            ("DELETE", "/api/groups/ISC-501", None),
            ("POST", "/api/system/maintenance", {"activo": True, "mensaje": "x"}),
        ]
        for metodo, ruta, cuerpo in prohibidas:
            with self.subTest(ruta=ruta):
                self.assertEqual(C.request(metodo, ruta, headers=self.J, json=cuerpo).status_code, 403)


# ───────────────────────── Grupos: particiones y límites ─────────────────────────
class TestGrupos(Base):
    def crear(self, gid, semestre=1, carrera=ISC, H=None):
        return C.post("/api/groups", headers=H or self.A, json={"id": gid, "nombre": "Grupo prueba", "carrera": carrera, "semestre": semestre})

    def test_clave_limites_de_longitud(self):
        self.assertEqual(self.crear("A").status_code, 400)          # 1 carácter
        self.assertEqual(self.crear("AB").status_code, 200)         # 2 (mínimo)
        self.assertEqual(self.crear("X" * 20).status_code, 200)     # 20 (máximo)
        self.assertEqual(self.crear("Y" * 21).status_code, 400)     # 21

    def test_clave_caracteres(self):
        self.assertEqual(self.crear("ISC 999").status_code, 400)
        self.assertEqual(self.crear("ISC_999").status_code, 400)
        self.assertEqual(self.crear("isc-998").status_code, 200)    # se acepta y se pasa a mayúsculas
        self.assertIn("ISC-998", ids(C.get("/api/groups", headers=self.A).json()))
        self.assertEqual(self.crear("ISC-998").status_code, 400)    # duplicado

    def test_semestre_limites(self):
        for sem, codigo in [(0, 400), (1, 200), (12, 200), (13, 400)]:
            with self.subTest(semestre=sem):
                self.assertEqual(self.crear(f"SEM-{sem}", semestre=sem).status_code, codigo)

    def test_editar(self):
        self.crear("ED-1")
        r = C.put("/api/groups/ED-1", headers=self.A, json={"nombre": "Grupo editado", "carrera": CIV, "semestre": 4})
        self.assertEqual(r.status_code, 200)
        g = [x for x in C.get("/api/groups", headers=self.A).json() if x["id"] == "ED-1"][0]
        self.assertEqual((g["nombre"], g["carrera"], g["semestre"]), ("Grupo editado", CIV, 4))
        self.assertEqual(C.put("/api/groups/NO-EXISTE", headers=self.A, json={"nombre": "Xx", "carrera": ISC, "semestre": 1}).status_code, 404)
        self.assertEqual(C.put("/api/groups/ED-1", headers=self.A, json={"nombre": "X", "carrera": ISC, "semestre": 1}).status_code, 400)

    def test_jefe_solo_sus_carreras(self):
        self.assertEqual(self.crear("JF-ISC", H=self.J).status_code, 200)
        self.assertEqual(self.crear("JF-CIV", carrera=CIV, H=self.J).status_code, 403)
        self.assertTrue(all(g["carrera"] == ISC for g in C.get("/api/groups", headers=self.J).json()))


# ───────────────────────── Jefes y administradores ─────────────────────────
class TestCuentas(Base):
    def jefe(self, **cambios):
        d = {"username": "jefe.nuevo", "nombre": "Jefe Nuevo", "password": "12345678", "carreras": [CIV]}
        d.update(cambios)
        return C.post("/api/jefes", headers=self.A, json=d)

    def test_validaciones_de_entrada(self):
        casos = [
            ({"password": "1234567"}, 422),           # 7 caracteres
            ({"username": "ab"}, 422),                # usuario de 2
            ({"username": "con espacio"}, 422),
            ({"carreras": []}, 422),
            ({"carreras": ["Medicina"]}, 400),
            ({"email": "no-es-correo"}, 400),
            ({"username": "admin.pruebas"}, 400),     # ya es administrador
            ({"username": "JEFE.ISC"}, 400),          # ya es jefe (sin importar mayúsculas)
            ({"username": "22030001"}, 400),          # coincide con matrícula de alumno
        ]
        for cambio, codigo in casos:
            with self.subTest(cambio=cambio):
                self.assertEqual(self.jefe(**cambio).status_code, codigo)

    def test_limites_validos(self):
        self.assertEqual(self.jefe(username="j3x", password="8" * 8, email="j@itsoeh.edu.mx").status_code, 200)

    def test_admin_no_puede_repetir_usuario_de_jefe(self):
        r = C.post("/api/admins", headers=self.A, json={"username": "jefe.isc", "nombre": "Choque de usuario", "password": "12345678"})
        self.assertEqual(r.status_code, 400, "Un administrador con el mismo usuario que un jefe impediría que el jefe entre")

    def test_cambio_de_carreras_y_desactivar(self):
        self.jefe(username="jefe.temp")
        jid = [j for j in C.get("/api/jefes", headers=self.A).json() if j["username"] == "jefe.temp"][0]["id"]
        H = entrar("jefe.temp", "12345678")
        self.assertEqual(C.put(f"/api/jefes/{jid}/carreras", headers=self.A, json={"carreras": [ISC, CIV]}).status_code, 200)
        self.assertEqual(C.get("/api/groups", headers=H).status_code, 401)   # sesión cerrada
        self.assertEqual(entrar("jefe.temp", "12345678") is not None, True)
        self.assertEqual(C.post(f"/api/jefes/{jid}/toggle", headers=self.A).json()["activo"], 0)
        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "jefe.temp", "password": "12345678"}).status_code, 401)
        self.assertEqual(C.post("/api/jefes/99999/toggle", headers=self.A).status_code, 404)

    def test_cambio_de_contrasena_del_jefe(self):
        self.jefe(username="jefe.pw")
        H = entrar("jefe.pw", "12345678")
        self.assertEqual(C.post("/api/admins/me/password", headers=H, json={"actual": "mala", "nueva": "nueva12345"}).status_code, 400)
        self.assertEqual(C.post("/api/admins/me/password", headers=H, json={"actual": "12345678", "nueva": "corta"}).status_code, 422)
        self.assertEqual(C.post("/api/admins/me/password", headers=H, json={"actual": "12345678", "nueva": "nueva12345"}).status_code, 200)
        self.assertTrue(entrar("jefe.pw", "nueva12345"))


# ───────────────────────── Docentes (jefe) ─────────────────────────
class TestDocentesJefe(Base):
    def test_alta_baja_reactivar(self):
        d = {"id": "DOC-NEW", "nombre_completo": "Docente Nuevo", "matricula_clave": "D-300", "tipo": "docente", "carrera": ISC, "grupo_id": None, "estado": "activo"}
        self.assertEqual(C.post("/api/users", headers=self.J, json=d).status_code, 200)
        self.assertEqual(C.post("/api/users", headers=self.J, json={**d, "id": "DOC-N2", "matricula_clave": "D-301", "carrera": CIV}).status_code, 403)
        self.assertEqual(C.post("/api/users", headers=self.J, json={**d, "id": "AL-N", "matricula_clave": "22035555", "tipo": "alumno", "grupo_id": "ISC-501"}).status_code, 403)
        self.assertEqual(C.delete("/api/users/DOC-NEW", headers=self.J).status_code, 200)
        u = [x for x in C.get("/api/users?tipo=docente", headers=self.J).json() if x["id"] == "DOC-NEW"][0]
        self.assertEqual(u["estado"], "inactivo")                                    # queda en el histórico
        self.assertEqual(C.post("/api/users/DOC-NEW/reactivate", headers=self.J).status_code, 200)
        self.assertEqual(C.delete("/api/users/DOC-CIV", headers=self.J).status_code, 403)
        self.assertEqual(C.delete("/api/users/AL-1", headers=self.J).status_code, 403)
        self.assertEqual(C.delete("/api/users/NO-EXISTE", headers=self.J).status_code, 404)

    def test_jefe_solo_lista_docentes(self):
        tipos = {u["tipo"] for u in C.get("/api/users?tipo=alumno", headers=self.J).json()}
        self.assertEqual(tipos, {"docente"})


# ──────────────── Cuentas de portal (apartados de Administradores) ────────────────
class TestCuentasPortal(Base):
    def flag(self, uid, tipo):
        return [x for x in C.get(f"/api/users?tipo={tipo}", headers=self.A).json() if x["id"] == uid][0]

    def test_alta_con_contrasena_y_login(self):
        lim = {"id": "LIM-T1", "nombre_completo": "Magda Prueba", "matricula_clave": "LIM-T1",
               "tipo": "personal_limpieza", "carrera": None, "grupo_id": None, "estado": "activo"}
        self.assertEqual(C.post("/api/users", headers=self.A, json={**lim, "password": "corta"}).status_code, 400)  # límite: 7 < 8
        self.assertEqual(C.post("/api/users", headers=self.A, json={**lim, "password": "limpia2026"}).status_code, 200)
        u = self.flag("LIM-T1", "personal_limpieza")
        self.assertTrue(u["tiene_password"])
        self.assertNotIn("password_hash", u)                                              # nunca se expone el hash
        self.assertTrue(entrar("LIM-T1", "limpia2026"))
        # Sin contraseña: se crea, pero no puede entrar
        self.assertEqual(C.post("/api/users", headers=self.A, json={**lim, "id": "LIM-T2", "matricula_clave": "LIM-T2"}).status_code, 200)
        self.assertFalse(self.flag("LIM-T2", "personal_limpieza")["tiene_password"])

    def test_editar_datos_y_contrasena(self):
        al = {"id": "AL-CTA", "nombre_completo": "Alumno Cuenta", "matricula_clave": "22039999", "tipo": "alumno",
              "carrera": ISC, "grupo_id": "ISC-501", "estado": "activo", "password": "primera123"}
        self.assertEqual(C.post("/api/users", headers=self.A, json=al).status_code, 200)
        H = entrar("22039999", "primera123")
        self.assertTrue(H)
        # Editar sin contraseña: conserva la actual
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "nombre_completo": "Alumno Editado", "password": None}).status_code, 200)
        self.assertEqual(self.flag("AL-CTA", "alumno")["nombre_completo"], "Alumno Editado")
        self.assertTrue(entrar("22039999", "primera123"))
        # Cambiar contraseña: la vieja ya no sirve y la sesión abierta se cierra
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "password": "segunda123"}).status_code, 200)
        self.assertEqual(C.get("/api/portal/student-data", headers=H).status_code, 401)
        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "22039999", "password": "primera123"}).status_code, 401)
        self.assertTrue(entrar("22039999", "segunda123"))
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "password": "corta"}).status_code, 400)

    def test_solo_admin_edita(self):
        d = {"id": "DOC-ISC", "nombre_completo": "Laura Pérez", "matricula_clave": "D-100", "tipo": "docente",
             "carrera": ISC, "grupo_id": None, "estado": "activo", "password": "hackeo1234"}
        self.assertEqual(C.put("/api/users/DOC-ISC", headers=self.J, json=d).status_code, 403)
        self.assertEqual(C.put("/api/users/DOC-ISC", headers=self.DO, json=d).status_code, 403)


# ───────────────────────── Horarios: límites ─────────────────────────
class TestHorarios(Base):
    def horario(self, ini, fin, dia="Viernes", lab="LAB-RED", H=None, **extra):
        d = {"grupo_id": "ISC-501", "laboratorio_id": lab, "docente_id": "DOC-ISC", "materia": "Programación Web",
             "dia_semana": dia, "hora_inicio": ini, "hora_fin": fin}
        d.update(extra)
        return C.post("/api/schedules", headers=H or self.A, json=d)

    def test_limites_de_hora(self):
        casos = [("05:59", "07:00", 400), ("06:00", "07:00", 200), ("21:00", "22:00", 200),
                 ("21:30", "22:01", 400), ("10:00", "10:00", 400), ("11:00", "10:00", 400)]
        for ini, fin, codigo in casos:
            with self.subTest(ini=ini, fin=fin):
                self.assertEqual(self.horario(ini, fin).status_code, codigo)

    def test_choque_y_contiguo(self):
        self.assertEqual(self.horario("12:00", "14:00", dia="Sábado").status_code, 200)
        self.assertEqual(self.horario("13:00", "15:00", dia="Sábado").status_code, 400)   # se traslapa
        self.assertEqual(self.horario("14:00", "16:00", dia="Sábado").status_code, 200)   # contiguo: válido

    def test_jefe_y_grupo_ajeno(self):
        r = self.horario("08:00", "09:00", dia="Jueves", lab="LAB-CIV", H=self.J, grupo_id="CIV-301", docente_id="DOC-CIV", materia="Topografía")
        self.assertEqual(r.status_code, 400)
        self.assertIn("no está a su cargo", r.text)

    def test_borrar_inexistente(self):
        self.assertEqual(C.delete("/api/schedules/999999", headers=self.A).status_code, 404)


class TestImportacion(Base):
    def subir(self, nombre, contenido, confirmar=False):
        return C.post(f"/api/schedules/import?confirmar={str(confirmar).lower()}", headers=self.A,
                      files={"archivo": (nombre, contenido, "application/octet-stream")})

    def test_formatos_y_tamanos(self):
        self.assertEqual(self.subir("h.pdf", b"%PDF-1.4").status_code, 400)
        self.assertEqual(self.subir("h.csv", b"").status_code, 400)
        self.assertIn(self.subir("h.csv", b"a" * (2 * 1024 * 1024 + 1)).status_code, (400, 413))

    def test_mas_de_1000_filas(self):
        enc = "Día,Hora inicio,Hora fin,Laboratorio,Grupo,Docente,Materia\n"
        fila = "Lunes,7:00,8:00,LAB-RED,ISC-501,D-100,Programación Web\n"
        self.assertEqual(self.subir("h.csv", (enc + fila * 1001).encode()).status_code, 400)

    def test_revisar_no_guarda_y_confirmar_no_duplica(self):
        enc = "Día,Hora inicio,Hora fin,Laboratorio,Grupo,Docente,Materia\n"
        datos = (enc + "Martes,18:00,19:00,LAB-RED,ISC-501,D-100,Programación Web\n"
                       "Martes,18:30,19:30,LAB-RED,ISC-501,D-100,Programación Web\n").encode()
        antes = len(C.get("/api/schedules", headers=self.A).json())
        r = self.subir("h.csv", datos).json()
        self.assertEqual((r["total"], r["validas"], r["con_error"]), (2, 1, 1))     # la 2.ª choca con la 1.ª
        self.assertEqual(len(C.get("/api/schedules", headers=self.A).json()), antes)  # revisar no guarda
        self.assertEqual(self.subir("h.csv", datos, True).json()["guardados"], 1)
        self.assertEqual(self.subir("h.csv", datos, True).json()["guardados"], 0)     # reimportar no duplica


# ───────────────────────── Portales ─────────────────────────
class TestPortales(Base):
    def test_alumno(self):
        d = C.get("/api/portal/student-data", headers=self.AL).json()
        self.assertEqual(d["tolerancia_min"], 10)
        datetime.strptime(d["ahora"], "%Y-%m-%dT%H:%M:%S")
        self.assertIn("nombre", d["periodo"])
        self.assertEqual(d["perfil"]["grupo_clave"], "ISC-501")
        self.assertFalse(d["tiene_rostro_registrado"])
        self.assertTrue(all(h["grupo_id"] == "ISC-501" for h in d["horarios_autorizados"]))

    def test_docente(self):
        d = C.get("/api/portal/teacher-data", headers=self.DO).json()
        self.assertEqual(d["tolerancia_min"], 10)
        self.assertTrue(all(h["docente_id"] == "DOC-ISC" for h in d["clases_asignadas"]))


# ───────────────────────── Reportes ─────────────────────────
class TestReportes(Base):
    def test_busqueda_particiones(self):
        for q in ["Carlos", "22030001", "zzz-no-existe", "%", "' OR 1=1 --", "_"]:
            with self.subTest(q=q):
                r = C.get("/api/reports/data", headers=self.A, params={"q": q})
                self.assertEqual(r.status_code, 200)
        self.assertEqual(C.get("/api/reports/data", headers=self.A, params={"q": "' OR 1=1 --"}).json(), [])

    def test_periodo_inexistente_vacio(self):
        self.assertEqual(C.get("/api/reports/data", headers=self.A, params={"periodo_id": "1999-1"}).json(), [])

    def test_csv_incluye_columna_periodo(self):
        r = C.get("/api/reports/export-csv", headers=self.J)
        self.assertIn("Periodo", r.content.decode("utf-8-sig").splitlines()[0])


class TestFiltros(Base):
    """Particiones de los filtros de horarios y reportes (con accesos registrados por la puerta)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        H = cls.A
        base = {"docente_id": "DOC-ISC", "dia_semana": "Miércoles", "hora_inicio": "16:00", "hora_fin": "17:00"}
        C.post("/api/schedules", headers=H, json={**base, "grupo_id": "ISC-501", "laboratorio_id": "LAB-RED", "materia": "Programación Web"})
        C.post("/api/schedules", headers=H, json={**base, "grupo_id": "CIV-301", "laboratorio_id": "LAB-CIV", "docente_id": "DOC-CIV", "materia": "Topografía"})
        tok = sembrar()["token_rpi"]
        for usuario, resultado, fecha in [("22030001", "permitido", "2026-09-01 08:00:00"), ("22030001", "denegado", "2026-09-15 08:00:00"),
                                           ("D-200", "permitido", "2026-10-01 08:00:00")]:
            C.post("/api/iot/access-attempt", json={"dispositivo_id": "RPI-RED", "token_api": tok, "usuario_id": usuario,
                                                    "resultado": resultado, "motivo": "filtro", "fecha_hora": fecha})

    def test_horarios_por_laboratorio_y_carrera(self):
        g = lambda **p: C.get("/api/schedules", headers=self.A, params=p).json()
        self.assertTrue(all(h["laboratorio_id"] == "LAB-CIV" for h in g(laboratorio_id="LAB-CIV")))
        self.assertTrue(all(h["grupo_carrera"] == CIV for h in g(carrera=CIV)))
        self.assertEqual(len(g(laboratorio_id="todos")), len(g()))
        self.assertEqual(g(periodo_id="1999-1"), [])

    def test_jefe_borra_horario_propio_no_ajeno(self):
        todos = C.get("/api/schedules", headers=self.A).json()
        propio = [h for h in todos if h["grupo_id"] == "ISC-501" and h["dia_semana"] == "Miércoles"][0]["id"]
        ajeno = [h for h in todos if h["grupo_id"] == "CIV-301"][0]["id"]
        self.assertEqual(C.delete(f"/api/schedules/{ajeno}", headers=self.J).status_code, 403)
        self.assertEqual(C.delete(f"/api/schedules/{propio}", headers=self.J).status_code, 200)
        self.assertNotIn(propio, [h["id"] for h in C.get("/api/schedules", headers=self.A).json()])

    def test_reportes_por_resultado_fechas_y_laboratorio(self):
        g = lambda H=None, **p: C.get("/api/reports/data", headers=H or self.A, params={"q": "", **p}).json()
        self.assertTrue(all(r["resultado"] == "denegado" for r in g(resultado="denegado")))
        self.assertEqual(len(g(fecha_inicio="2026-09-01", fecha_fin="2026-09-01")), 1)        # límite: el mismo día
        self.assertEqual(len(g(fecha_inicio="2026-09-02", fecha_fin="2026-09-14")), 0)        # entre dos accesos
        self.assertEqual(g(laboratorio_id="LAB-CIV"), [])
        self.assertEqual(len(g(q="22030001")), 2)
        # el jefe de Sistemas ve los de su carrera (alumno ISC o laboratorio ISC); el docente de Civil entró a un lab ISC
        self.assertEqual(len(g(H=self.J, fecha_inicio="2026-09-01", fecha_fin="2026-10-31")), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
