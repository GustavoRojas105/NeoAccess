"""
PRUEBAS DE CAJA NEGRA
Solo se usa la API (entradas -> salidas), sin mirar la base de datos ni el código.
Técnicas: particiones de equivalencia, valores límite y matriz de permisos por rol.
"""
import io
import unittest
from datetime import datetime

import random as _random

_AZAR = _random.Random(2026)


def nombre_unico(prefijo="Persona"):
    """Nombre distinto en cada llamada (el sistema no deja dar de alta dos nombres iguales o parecidos)."""
    return f"{prefijo} " + "".join(_AZAR.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(9))


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
        cls.DO = entrar("100", CLAVE_PRUEBA)


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
            ("100", CLAVE_PRUEBA, 200, "docente"),
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
        d = {"id": "DOC-NEW", "nombre_completo": "Docente Nuevo", "matricula_clave": "300", "tipo": "docente", "carrera": ISC, "grupo_id": None, "estado": "activo"}
        self.assertEqual(C.post("/api/users", headers=self.J, json=d).status_code, 200)
        self.assertEqual(C.post("/api/users", headers=self.J, json={**d, "id": "DOC-N2", "matricula_clave": "301", "carrera": CIV}).status_code, 403)
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
        self.assertEqual(C.post("/api/users", headers=self.A, json={**lim, "id": "LIM-T2", "matricula_clave": "LIM-T2", "nombre_completo": "Rocío Sin Clave"}).status_code, 200)
        self.assertFalse(self.flag("LIM-T2", "personal_limpieza")["tiene_password"])

    def test_editar_datos_y_contrasena(self):
        al = {"id": "AL-CTA", "nombre_completo": "Alumno Cuenta", "matricula_clave": "22039999", "tipo": "alumno",
              "carrera": ISC, "grupo_id": "ISC-501", "estado": "activo", "password": "primera123"}
        self.assertEqual(C.post("/api/users", headers=self.A, json=al).status_code, 200)
        H = entrar("22039999", "primera123")
        self.assertTrue(H)
        # Editar sin contraseña: conserva la actual
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "nombre_completo": "Alumno Editado", "password": None}).status_code, 200)
        self.assertEqual(self.flag("AL-CTA", "alumno")["nombre_completo"], "ALUMNO EDITADO")   # se guarda en mayúsculas
        self.assertTrue(entrar("22039999", "primera123"))
        # Cambiar contraseña: la vieja ya no sirve y la sesión abierta se cierra
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "password": "segunda123"}).status_code, 200)
        self.assertEqual(C.get("/api/portal/student-data", headers=H).status_code, 401)
        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "22039999", "password": "primera123"}).status_code, 401)
        self.assertTrue(entrar("22039999", "segunda123"))
        self.assertEqual(C.put("/api/users/AL-CTA", headers=self.A, json={**al, "password": "corta"}).status_code, 400)

    def test_solo_admin_edita(self):
        d = {"id": "DOC-ISC", "nombre_completo": "Laura Pérez", "matricula_clave": "100", "tipo": "docente",
             "carrera": ISC, "grupo_id": None, "estado": "activo", "password": "hackeo1234"}
        self.assertEqual(C.put("/api/users/DOC-ISC", headers=self.J, json=d).status_code, 403)
        self.assertEqual(C.put("/api/users/DOC-ISC", headers=self.DO, json=d).status_code, 403)


class TestCodigosPorCorreo(Base):
    """Registro con código de 6 dígitos y recuperación de contraseña (correo simulado)."""

    def setUp(self):
        import re
        from unittest import mock
        import backend.app as appmod
        appmod._REGISTRO_INTENTOS.clear()
        appmod._RECUPERAR_INTENTOS.clear()
        self.enviados = []
        self.re = re

        def falso(para, asunto, texto, html=None):
            self.enviados.append((para, asunto, texto))
            return True
        p = mock.patch.object(appmod, "send_email", falso)
        p.start()
        self.addCleanup(p.stop)

    def ultimo_codigo(self, correo):
        para, asunto, texto = [e for e in self.enviados if e[0] == correo][-1]
        return self.re.search(r"\b(\d{6})\b", texto).group(1)

    def registrar(self, correo, matricula, tipo="alumno"):
        r = C.post("/api/auth/register", json={"tipo": tipo, "nombre_completo": nombre_unico(),
                                               "matricula_clave": matricula, "correo": correo,
                                               "carrera": ISC, "password": "ClaveNueva123"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_solo_correo_institucional(self):
        for correo in ("alguien@gmail.com", "x@itsoeh.edu.mx.evil.com", "x@sub.itsoeh.edu.mx"):
            r = C.post("/api/auth/register", json={"tipo": "alumno", "nombre_completo": "Fulano",
                                                   "matricula_clave": "99000001", "correo": correo,
                                                   "password": "ClaveNueva123"})
            self.assertEqual(r.status_code, 400, correo)
        self.assertEqual(self.enviados, [])

    def test_registro_con_codigo(self):
        correo = "alumno.codigo@itsoeh.edu.mx"
        d = self.registrar(correo, "99000010")
        self.assertTrue(d["correo_enviado"])
        self.assertEqual(d["minutos"], 15)
        codigo = self.ultimo_codigo(correo)
        self.assertNotIn("http", self.enviados[-1][2])            # ya no manda enlace
        malo = "000000" if codigo != "000000" else "111111"
        r = C.post("/api/auth/verify-code", json={"correo": correo, "codigo": malo})
        self.assertEqual(r.status_code, 400)
        self.assertIn("4 intento", r.json()["detail"])
        # antes de verificar no puede entrar
        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "99000010", "password": "ClaveNueva123"}).status_code, 401)
        r = C.post("/api/auth/verify-code", json={"correo": correo.upper(), "codigo": codigo})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["estado"], "ok")
        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "99000010", "password": "ClaveNueva123"}).status_code, 200)
        # el código ya no sirve una segunda vez
        self.assertEqual(C.post("/api/auth/verify-code", json={"correo": correo, "codigo": codigo}).status_code, 400)

    def test_docente_queda_pendiente_de_aprobacion(self):
        correo = "docente.codigo@itsoeh.edu.mx"
        self.registrar(correo, "9001", tipo="docente")
        r = C.post("/api/auth/verify-code", json={"correo": correo, "codigo": self.ultimo_codigo(correo)})
        self.assertEqual(r.json()["estado"], "pendiente")

    def test_cinco_intentos_invalidan_el_codigo_y_reenviar_da_otro(self):
        correo = "intentos@itsoeh.edu.mx"
        self.registrar(correo, "99000020")
        bueno = self.ultimo_codigo(correo)
        malo = "123456" if bueno != "123456" else "654321"
        for _ in range(5):
            C.post("/api/auth/verify-code", json={"correo": correo, "codigo": malo})
        r = C.post("/api/auth/verify-code", json={"correo": correo, "codigo": bueno})
        self.assertEqual(r.status_code, 400)                      # ni el bueno sirve ya
        self.assertEqual(C.post("/api/auth/resend-verification", json={"correo": correo}).status_code, 200)
        nuevo = self.ultimo_codigo(correo)
        r = C.post("/api/auth/verify-code", json={"correo": correo, "codigo": nuevo})
        self.assertEqual(r.status_code, 200, r.text)

    def test_codigo_vencido(self):
        from _entorno import bd
        correo = "vencido@itsoeh.edu.mx"
        self.registrar(correo, "99000030")
        c = bd()
        c.execute("UPDATE registros_pendientes SET expira = '2000-01-01 00:00:00' WHERE correo = ?", (correo,))
        c.commit()
        c.close()
        r = C.post("/api/auth/verify-code", json={"correo": correo, "codigo": self.ultimo_codigo(correo)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("venció", r.json()["detail"])

    def test_recuperar_contrasena(self):
        correo = "recupera@itsoeh.edu.mx"
        self.registrar(correo, "99000040")
        C.post("/api/auth/verify-code", json={"correo": correo, "codigo": self.ultimo_codigo(correo)})
        sesion_vieja = entrar("99000040", "ClaveNueva123")

        # correo sin cuenta: misma respuesta y no se manda nada
        n = len(self.enviados)
        r1 = C.post("/api/auth/forgot-password", json={"correo": "nadie@itsoeh.edu.mx"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(self.enviados), n)
        r2 = C.post("/api/auth/forgot-password", json={"correo": correo})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(self.enviados), n + 1)
        self.assertEqual(r1.json()["message"].replace("nadie@", "X@"), r2.json()["message"].replace("recupera@", "X@"))

        codigo = self.ultimo_codigo(correo)
        malo = "000000" if codigo != "000000" else "111111"
        r = C.post("/api/auth/reset-password", json={"correo": correo, "codigo": malo, "password": "OtraClave456"})
        self.assertEqual(r.status_code, 400)
        r = C.post("/api/auth/reset-password", json={"correo": correo, "codigo": codigo, "password": "corta"})
        self.assertEqual(r.status_code, 422)                      # mínimo 8 caracteres
        r = C.post("/api/auth/reset-password", json={"correo": correo, "codigo": codigo, "password": "OtraClave456"})
        self.assertEqual(r.status_code, 200, r.text)

        limpiar_intentos()
        self.assertEqual(C.post("/api/auth/login", json={"username": "99000040", "password": "ClaveNueva123"}).status_code, 401)
        self.assertEqual(C.post("/api/auth/login", json={"username": "99000040", "password": "OtraClave456"}).status_code, 200)
        self.assertEqual(C.get("/api/portal/student-data", headers=sesion_vieja).status_code, 401)  # sesión cerrada
        # el código se usa una sola vez
        r = C.post("/api/auth/reset-password", json={"correo": correo, "codigo": codigo, "password": "Tercera789"})
        self.assertEqual(r.status_code, 400)


class TestValidacionNombresMatriculas(Base):
    """Nombres en MAYÚSCULAS y solo letras; matrícula de alumno de 8 o 9 números; clave de docente."""

    def alta(self, **cambios):
        datos = {"id": "VAL-1", "nombre_completo": nombre_unico("Alumno"), "matricula_clave": "230110999",
                 "tipo": "alumno", "carrera": ISC, "grupo_id": None, "estado": "activo", **cambios}
        return C.post("/api/users", headers=self.A, json=datos)

    def test_nombre_se_guarda_en_mayusculas(self):
        r = self.alta(nombre_completo="  maría   josé  peña ")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("MARÍA JOSÉ PEÑA", r.json()["message"])
        usuarios = C.get("/api/users", headers=self.A).json()
        self.assertEqual([u["nombre_completo"] for u in usuarios if u["id"] == "VAL-1"], ["MARÍA JOSÉ PEÑA"])

    def test_nombres_invalidos(self):
        for nombre in ("Juan123", "Ana@Ruiz", "AB", "-Pedro"):
            r = self.alta(id="VAL-N", nombre_completo=nombre, matricula_clave="230110998")
            self.assertEqual(r.status_code, 400, nombre)
        self.assertEqual(self.alta(id="VAL-N2", nombre_completo="Ma. Guadalupe O'Neil-Ruiz", matricula_clave="230110997").status_code, 200)

    def test_matricula_de_alumno_limites(self):
        # 7 y 10 dígitos, con letras o espacios en medio: no; 8 y 9 dígitos: sí
        for i, mat in enumerate(("2301104", "2030110539", "23011A427", "ABC-123")):
            self.assertEqual(self.alta(id=f"VAL-M{i}", matricula_clave=mat).status_code, 400, mat)
        self.assertEqual(self.alta(id="VAL-M8", matricula_clave="19011044").status_code, 200)
        self.assertEqual(self.alta(id="VAL-M9", matricula_clave=" 250110668 ").status_code, 200)

    def test_numero_de_empleado_del_docente(self):
        base = {"tipo": "docente", "nombre_completo": "Docente Validado"}
        self.assertEqual(self.alta(id="VAL-D1", matricula_clave="004512", **base).status_code, 200)
        self.assertEqual(self.alta(id="VAL-D2", matricula_clave=" 12 34 ", **{**base, "nombre_completo": "Docente Segundo Validado"}).status_code, 200)   # espacios se quitan
        for i, mal in enumerate(("DOC-ISC-99", "12", "12345678901", "E-1234")):
            r = self.alta(id=f"VAL-D{i + 3}", matricula_clave=mal, **base)
            self.assertEqual(r.status_code, 400, mal)
            self.assertIn("número de empleado", r.json()["detail"])
        # el personal de limpieza sigue con clave de letras y números
        self.assertEqual(self.alta(id="VAL-L1", matricula_clave="lim-99", tipo="personal_limpieza",
                                   nombre_completo="Persona Limpieza").status_code, 200)

    def test_docente_antiguo_conserva_su_clave_al_editar(self):
        # un docente dado de alta antes con clave de letras se puede editar sin cambiarla,
        # pero si se cambia tiene que ser ya un número de empleado
        from _entorno import bd
        self.assertEqual(self.alta(id="VAL-ANT", tipo="docente", nombre_completo="Docente Antiguo",
                                   matricula_clave="7001").status_code, 200)
        c = bd()
        c.execute("UPDATE usuarios SET matricula_clave = 'DOC-ISC-77' WHERE id = 'VAL-ANT'")
        c.commit()
        c.close()
        datos = {"id": "VAL-ANT", "nombre_completo": "Docente Antiguo", "matricula_clave": "doc-isc-77",
                 "tipo": "docente", "carrera": ISC, "grupo_id": None, "estado": "activo"}
        self.assertEqual(C.put("/api/users/VAL-ANT", headers=self.A, json=datos).status_code, 200)
        self.assertEqual(C.put("/api/users/VAL-ANT", headers=self.A, json={**datos, "matricula_clave": "DOC-NUEVA"}).status_code, 400)
        self.assertEqual(C.put("/api/users/VAL-ANT", headers=self.A, json={**datos, "matricula_clave": "7002"}).status_code, 200)

    def test_registro_publico_valida_igual(self):
        import backend.app as appmod
        appmod._REGISTRO_INTENTOS.clear()
        r = C.post("/api/auth/register", json={"tipo": "alumno", "nombre_completo": "Juan 2", "matricula_clave": "230110111",
                                               "correo": "juan.val@itsoeh.edu.mx", "password": "ClaveNueva123"})
        self.assertEqual(r.status_code, 400)
        r = C.post("/api/auth/register", json={"tipo": "alumno", "nombre_completo": "Juan Val", "matricula_clave": "2301101112",
                                               "correo": "juan.val@itsoeh.edu.mx", "password": "ClaveNueva123"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("8 o 9 números", r.json()["detail"])


class TestEntrarConCorreoYEspacios(Base):
    """El alumno entra con su matrícula o su correo; la contraseña con espacios al final también sirve."""

    def test_formas_de_entrar(self):
        from _entorno import bd
        from backend.auth import hash_password
        from _entorno import poner_clave
        c = bd()
        c.execute("UPDATE usuarios SET correo = 'carlos.val@itsoeh.edu.mx', password_hash = ? WHERE id = 'AL-1'",
                  (hash_password("MiClave123 "),))
        c.commit()
        c.close()
        try:
            for usuario, clave in (("22030001", "MiClave123 "), (" 22030001 ", "MiClave123 "),
                                   ("Carlos.Val@itsoeh.edu.mx", "MiClave123 "), ("al-1", "MiClave123 ")):
                r = C.post("/api/auth/login", json={"username": usuario, "password": clave})
                self.assertEqual(r.status_code, 200, (usuario, clave, r.text))
            self.assertEqual(C.post("/api/auth/login", json={"username": "22030001", "password": "MiClave12"}).status_code, 401)
            # contraseña guardada sin espacios: si el celular agrega uno al final, igual entra
            poner_clave("AL-1", "OtraClave456")
            self.assertEqual(C.post("/api/auth/login", json={"username": "22030001", "password": "OtraClave456 "}).status_code, 200)
        finally:
            poner_clave("AL-1")


class TestJefeAsignaAlumnos(Base):
    """Issue #1: el jefe de carrera mete y saca alumnos de los grupos de su carrera, en bloque."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = {"tipo": "alumno", "estado": "activo", "grupo_id": None}
        for uid, mat, nombre, carrera in (("AG-1", "230118001", "Ana Grupo", ISC), ("AG-2", "230118002", "Beto Grupo", ISC),
                                          ("AG-CIV", "230118003", "Ciro Civil", CIV)):
            C.post("/api/users", headers=cls.A, json={**base, "id": uid, "matricula_clave": mat,
                                                      "nombre_completo": nombre, "carrera": carrera})
        C.post("/api/groups", headers=cls.A, json={"id": "ISC-AG", "nombre": "Grupo Asignación", "carrera": ISC, "semestre": 3})
        C.post("/api/groups", headers=cls.A, json={"id": "CIV-AG", "nombre": "Civil Asignación", "carrera": CIV, "semestre": 3})
        from _entorno import bd
        c = bd()
        c.execute("""INSERT OR IGNORE INTO grupos (id, nombre, carrera, semestre, periodo_id, clave)
                     VALUES ('ISC-VIEJO', 'Grupo cerrado', ?, 3, '2019-1', 'ISC-VIEJO')""", (ISC,))
        c.commit()
        c.close()

    def asignar(self, gid, H=None, **cuerpo):
        return C.put(f"/api/groups/{gid}/alumnos", headers=H or self.J, json=cuerpo)

    def test_jefe_asigna_en_bloque_y_queda_en_bitacora(self):
        r = self.asignar("ISC-AG", agregar=["AG-1", "AG-2"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["cambios"], r.json()["alumnos"]), (2, 2))
        g = C.get("/api/groups/ISC-AG/alumnos", headers=self.J).json()
        self.assertEqual(sorted(a["id"] for a in g["alumnos"]), ["AG-1", "AG-2"])
        r = self.asignar("ISC-AG", quitar=["AG-2"])
        self.assertEqual(r.json()["alumnos"], 1)
        bit = C.get("/api/asignaciones-grupo", headers=self.A, params={"grupo_id": "ISC-AG"}).json()
        self.assertEqual([(b["usuario_id"], b["grupo_nuevo"], b["actor_rol"]) for b in bit][:3],
                         [("AG-2", None, "jefe_carrera"), ("AG-2", "ISC-AG", "jefe_carrera"), ("AG-1", "ISC-AG", "jefe_carrera")])
        self.assertEqual(self.asignar("ISC-AG").status_code, 400)   # sin cambios

    def test_otra_carrera_o_periodo_cerrado(self):
        self.assertEqual(self.asignar("ISC-AG", agregar=["AG-CIV"]).status_code, 403)      # alumno de otra carrera
        self.assertEqual(self.asignar("CIV-AG", agregar=["AG-1"]).status_code, 403)        # grupo de otra carrera
        self.assertEqual(self.asignar("ISC-VIEJO", agregar=["AG-1"]).status_code, 400)     # periodo cerrado
        self.assertEqual(self.asignar("ISC-AG", agregar=["DOC-ISC"]).status_code, 404)     # no es alumno
        self.assertEqual(self.asignar("NO-EXISTE", agregar=["AG-1"]).status_code, 404)
        # el administrador tampoco mezcla carreras: el alumno de Civil no entra a un grupo de Sistemas
        self.assertEqual(self.asignar("ISC-AG", H=self.A, agregar=["AG-CIV"]).status_code, 400)
        self.assertEqual(self.asignar("CIV-AG", H=self.A, agregar=["AG-CIV"]).status_code, 200)
        self.assertEqual(self.asignar("ISC-AG", H=self.DO, agregar=["AG-1"]).status_code, 403)
        self.assertEqual(self.asignar("ISC-AG", H=self.AL, agregar=["AG-1"]).status_code, 403)

    def test_jefe_no_cambia_carrera_password_ni_estado(self):
        datos = {"id": "AG-1", "nombre_completo": "Ana Grupo", "matricula_clave": "230118001", "tipo": "alumno",
                 "carrera": CIV, "grupo_id": None, "estado": "activo", "password": "OtraClave2026"}
        self.assertEqual(C.put("/api/users/AG-1", headers=self.J, json=datos).status_code, 403)
        self.assertEqual(C.delete("/api/users/AG-1", headers=self.J).status_code, 403)
        self.assertEqual(C.post("/api/accounts/usuario/AG-1/reset-password", headers=self.J).status_code, 403)

    def test_lista_minima_sin_datos_privados(self):
        lista = C.get("/api/jefe/alumnos", headers=self.J).json()
        self.assertTrue(lista)
        self.assertTrue(all(a["carrera"] == ISC for a in lista))
        self.assertEqual(set(lista[0]), {"id", "matricula_clave", "nombre_completo", "carrera", "grupo_id", "grupo_clave"})
        self.assertNotIn("AG-CIV", [a["id"] for a in lista])
        self.assertEqual(C.get("/api/jefe/alumnos", headers=self.J, params={"carrera": CIV}).status_code, 403)
        sin = C.get("/api/jefe/alumnos", headers=self.J, params={"sin_grupo": 1}).json()
        self.assertTrue(all(a["grupo_id"] is None for a in sin))
        self.assertEqual(C.get("/api/jefe/alumnos", headers=self.AL).status_code, 403)

    def test_la_raspberry_ya_lo_ve_en_su_grupo(self):
        from _entorno import bd
        tok = sembrar()["token_rpi"]
        C.post("/api/schedules", headers=self.A, json={
            "grupo_id": "ISC-AG", "laboratorio_id": "LAB-RED", "docente_id": "DOC-ISC",
            "materia": "Programación Web", "dia_semana": "Lunes", "hora_inicio": "20:00", "hora_fin": "21:00"})
        c = bd()
        c.execute("INSERT OR REPLACE INTO metadatos_faciales (usuario_id, vector_encoding) VALUES ('AG-1', '[0.1, 0.2]')")
        c.commit()
        c.close()
        self.asignar("ISC-AG", agregar=["AG-1"])
        r = C.get("/api/iot/sync-offline-rules", headers={"X-Device-Token": tok}, params={"dispositivo_id": "RPI-RED"}).json()
        al = [u for u in r["usuarios"] if u["usuario_id"] == "AG-1"]
        self.assertEqual(al[0]["grupo_id"], "ISC-AG")
        self.assertTrue(any(h["grupo_id"] == "ISC-AG" for h in r["horarios"]))


class TestSinPersonasRepetidas(Base):
    """Nadie se puede dar de alta dos veces: ni la misma clave escrita distinto ni un nombre igual o casi igual."""

    def alta(self, uid, mat, nombre, tipo="docente", H=None):
        return C.post("/api/users", headers=H or self.A, json={
            "id": uid, "matricula_clave": mat, "nombre_completo": nombre, "tipo": tipo,
            "carrera": ISC, "grupo_id": None, "estado": "activo"})

    def test_nombre_y_clave_repetidos(self):
        r = self.alta("DUP-1", "77001", "Ramiro Ibáñez de la Torre")
        self.assertEqual(r.status_code, 200, r.text)
        for nombre in ("RAMIRO IBANEZ DE LA TORRE", "Ibáñez Torre Ramiro", "Ramiro  Ibañez Torre",
                       "RAMIRO IBÁÑEZ DE LA TORREZ", "Ramiro Alonso Ibáñez de la Torre"):
            r = self.alta("DUP-2", "77002", nombre)
            self.assertEqual(r.status_code, 400, nombre)
            self.assertIn("77001", r.json()["detail"])
        r = self.alta("DUP-3", "077001", "Persona Distinta Uno")       # misma clave con cero a la izquierda
        self.assertEqual(r.status_code, 400)
        self.assertIn("ya es de", r.json()["detail"])
        self.assertEqual(self.alta("DUP-4", "77004", "Ramira Ibarra Soto").status_code, 200)   # otra persona

    def test_editar_no_choca_consigo_mismo(self):
        self.assertEqual(self.alta("DUP-5", "77005", "Lucía Fernanda Ortega").status_code, 200)
        self.assertEqual(self.alta("DUP-6", "77006", "Mateo Quiroz Salas").status_code, 200)
        base = {"matricula_clave": "77005", "tipo": "docente", "carrera": ISC, "grupo_id": None, "estado": "activo"}
        r = C.put("/api/users/DUP-5", headers=self.A, json={**base, "id": "DUP-5", "nombre_completo": "Lucía Fernanda Ortega"})
        self.assertEqual(r.status_code, 200, r.text)
        r = C.put("/api/users/DUP-5", headers=self.A, json={**base, "id": "DUP-5", "nombre_completo": "Mateo Quiroz Salas"})
        self.assertEqual(r.status_code, 400)
        r = C.put("/api/users/DUP-5", headers=self.A, json={**base, "id": "DUP-5", "matricula_clave": "77006",
                                                             "nombre_completo": "Lucía Fernanda Ortega"})
        self.assertEqual(r.status_code, 400)


class TestRestablecerPassword(Base):
    """El administrador da una contraseña temporal; al entrar se obliga a cambiarla."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        C.post("/api/users", headers=cls.A, json={"id": "AL-RST", "nombre_completo": "Alumno Restablecer",
                                                  "matricula_clave": "230119999", "tipo": "alumno", "carrera": ISC,
                                                  "grupo_id": "ISC-501", "estado": "activo", "password": CLAVE_PRUEBA})
        C.post("/api/jefes", headers=cls.A, json={"username": "jefe.rst", "nombre": "Jefe Restablecer",
                                                  "password": CLAVE_PRUEBA, "carreras": [ISC]})

    def login(self, u, p):
        limpiar_intentos()
        return C.post("/api/auth/login", json={"username": u, "password": p})

    def reset(self, tipo, cid, H=None):
        return C.post(f"/api/accounts/{tipo}/{cid}/reset-password", headers=H or self.A)

    def test_alumno_cambia_la_temporal_al_entrar(self):
        viejo = {"Authorization": "Bearer " + self.login("230119999", CLAVE_PRUEBA).json()["token"]}
        r = self.reset("usuario", "AL-RST")
        self.assertEqual(r.status_code, 200, r.text)
        temporal = r.json()["temporal"]
        self.assertEqual(len(temporal), 10)
        self.assertEqual(C.get("/api/portal/student-data", headers=viejo).status_code, 401)   # sesión vieja cerrada
        self.assertEqual(self.login("230119999", CLAVE_PRUEBA).status_code, 401)              # la anterior ya no sirve
        e = self.login("230119999", temporal)
        self.assertEqual(e.status_code, 200, e.text)
        self.assertTrue(e.json()["admin"]["debe_cambiar_password"])
        H = {"Authorization": "Bearer " + e.json()["token"]}
        bloqueado = C.get("/api/portal/student-data", headers=H)
        self.assertEqual(bloqueado.status_code, 403)
        self.assertEqual(bloqueado.headers.get("X-NeoAccess-Cambiar-Password"), "1")
        self.assertEqual(C.post("/api/auth/required-password", headers=H, json={"nueva": temporal}).status_code, 400)
        self.assertEqual(C.post("/api/auth/required-password", headers=H, json={"nueva": "corta"}).status_code, 422)
        self.assertEqual(C.post("/api/auth/required-password", headers=H, json={"nueva": "MiNueva2026"}).status_code, 200)
        self.assertEqual(C.get("/api/portal/student-data", headers=H).status_code, 200)         # sigue con la misma sesión
        e2 = self.login("230119999", "MiNueva2026")
        self.assertEqual(e2.status_code, 200)
        self.assertFalse(e2.json()["admin"]["debe_cambiar_password"])

    def test_jefe_y_otro_admin(self):
        from _entorno import bd
        c = bd()
        jid = c.execute("SELECT id FROM jefes_carrera WHERE username = 'jefe.rst'").fetchone()[0]
        c.close()
        r = self.reset("jefe", jid)
        self.assertEqual(r.status_code, 200, r.text)
        e = self.login("jefe.rst", r.json()["temporal"])
        self.assertTrue(e.json()["admin"]["debe_cambiar_password"])
        H = {"Authorization": "Bearer " + e.json()["token"]}
        self.assertEqual(C.get("/api/groups", headers=H).status_code, 403)
        self.assertEqual(C.post("/api/auth/required-password", headers=H, json={"nueva": "JefeNueva2026"}).status_code, 200)
        self.assertEqual(C.get("/api/groups", headers=H).status_code, 200)
        # su propia cuenta no (usa «Cambiar mi contraseña»)
        yo = [a for a in C.get("/api/admins", headers=self.A).json() if a.get("es_yo")][0]
        self.assertEqual(self.reset("admin", yo["id"]).status_code, 400)

    def test_solo_el_administrador(self):
        self.assertEqual(self.reset("usuario", "AL-RST", H=self.J).status_code, 403)
        self.assertEqual(self.reset("usuario", "AL-RST", H=self.DO).status_code, 403)
        self.assertEqual(self.reset("otro", "AL-RST").status_code, 400)
        self.assertEqual(self.reset("usuario", "NO-EXISTE").status_code, 404)
        self.assertEqual(self.reset("jefe", "abc").status_code, 404)
        self.assertEqual(C.post("/api/auth/required-password", json={"nueva": "LoQueSea2026"}).status_code, 401)


class TestCargaYClasesExtra(Base):
    """Carga académica del SEIT y alumnos agregados por el docente a una clase de otro grupo."""
    FECHA = "2026-11-28"   # sábado

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        C.post("/api/groups", headers=cls.A, json={"id": "ISC-98A", "nombre": "98A Especialidad", "carrera": ISC, "semestre": 7})
        r = C.post("/api/schedules", headers=cls.A, json={
            "grupo_id": "ISC-98A", "laboratorio_id": "LAB-RED", "docente_id": "DOC-ISC",
            "materia": "Programación Web", "dia_semana": "Sábado", "hora_inicio": "09:00", "hora_fin": "11:00"})
        assert r.status_code == 200, r.text
        from _entorno import bd
        c = bd()
        cls.horario = c.execute("""SELECT id FROM horarios WHERE grupo_id = 'ISC-98A' AND dia_semana = 'Sábado'
                                   AND hora_inicio = '09:00'""").fetchone()[0]
        c.close()
        r = C.post("/api/schedules", headers=cls.A, json={
            "grupo_id": "ISC-98A", "laboratorio_id": "LAB-RED", "docente_id": "DOC-ISC",
            "materia": "Programación Web", "dia_semana": "Sábado", "hora_inicio": "19:00", "hora_fin": "20:00"})
        assert r.status_code == 200, r.text
        c = bd()
        cls.horario2 = c.execute("""SELECT id FROM horarios WHERE grupo_id = 'ISC-98A' AND hora_inicio = '19:00'""").fetchone()[0]
        c.close()

    def carga(self, control="22030001", docente="LAURA PEREZ"):
        return (f"N. Control : {control}\n"
                "98AB PROGRAMACION WEB 5 09:00-11:00 16:00-17:00\n"
                f"     {docente} Salón LAB-RED Salón 402\n"
                "T07B TUTORIA VII 0 15:00-16:00\n"
                "     OTRA PERSONA Salón 402\n")

    def subir(self, H, texto, ruta="/api/portal/student/carga"):
        return C.post(ruta, headers=H, json={"texto": texto})

    def test_alumno_sube_su_carga(self):
        r = self.subir(self.AL, self.carga())
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(([s["horario_id"] for s in d["ligadas"]], d["materias"]), ([self.horario], 2))
        self.assertEqual(len(d["en_salon"]), 2)
        h = [x for x in C.get("/api/portal/student-data", headers=self.AL).json()["horarios_autorizados"] if x["id"] == self.horario]
        self.assertTrue(h and h[0]["por_carga"])
        # sale en el pase de lista del docente aunque sea de otro grupo
        import openpyxl
        x = C.get("/api/portal/teacher/attendance-list", headers=self.DO,
                  params={"formato": "xlsx", "fecha": self.FECHA, "horario_id": self.horario})
        self.assertEqual(x.status_code, 200, x.text)
        filas = [[c.value for c in f] for f in openpyxl.load_workbook(io.BytesIO(x.content)).active.iter_rows()]
        self.assertTrue(any(f[1] == "22030001" for f in filas))
        # volver a subirla con otro docente quita la clase anterior
        self.assertEqual(self.subir(self.AL, self.carga(docente="NADIE")).json()["ligadas"], [])
        self.assertFalse([x for x in C.get("/api/portal/student-data", headers=self.AL).json()["horarios_autorizados"]
                          if x["id"] == self.horario])

    def test_carga_de_otra_matricula_o_vacia(self):
        r = self.subir(self.AL, self.carga(control="99999999"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("99999999", r.json()["detail"])
        self.assertEqual(self.subir(self.AL, "hola esto no es una carga académica").status_code, 400)
        self.assertEqual(self.subir(self.DO, self.carga()).status_code, 403)

    def test_admin_y_jefe_suben_la_carga_por_el_alumno(self):
        self.assertEqual(self.subir(self.A, self.carga(), "/api/users/AL-1/carga").status_code, 200)
        self.assertEqual(self.subir(self.J, self.carga(), "/api/users/AL-1/carga").status_code, 200)   # jefe de Sistemas
        self.assertEqual(self.subir(self.A, self.carga(), "/api/users/DOC-ISC/carga").status_code, 404)

    def test_docente_agrega_y_quita_alumnos(self):
        ruta = f"/api/portal/teacher/classes/{self.horario}/students"
        C.delete(f"{ruta}/AL-1", headers=self.DO)
        self.assertEqual(C.post(ruta, headers=self.DO, json={"matricula": "00000000"}).status_code, 404)
        r = C.post(ruta, headers=self.DO, json={"matricula": " 22030001 "})
        self.assertEqual(r.status_code, 200, r.text)
        lista = C.get(ruta, headers=self.DO).json()["alumnos"]
        self.assertEqual([(a["id"], a["como"], a["origen"]) for a in lista], [("AL-1", "inscrito", "docente")])
        # la otra sesión de esa materia (sábado 19:00) también lo tiene
        lista2 = C.get(f"/api/portal/teacher/classes/{self.horario2}/students", headers=self.DO).json()["alumnos"]
        self.assertEqual([x["id"] for x in lista2], ["AL-1"])
        # el docente ve cuántos alumnos tiene la clase
        clase = [c for c in C.get("/api/portal/teacher-data", headers=self.DO).json()["clases_asignadas"] if c["id"] == self.horario][0]
        self.assertEqual(clase["alumnos"], 1)
        self.assertEqual(C.delete(f"{ruta}/AL-1", headers=self.DO).status_code, 200)
        self.assertEqual(C.delete(f"{ruta}/AL-1", headers=self.DO).status_code, 400)
        # otro docente o un alumno no pueden tocar esta clase
        from _entorno import poner_clave
        poner_clave("DOC-CIV")
        otro = entrar("200", CLAVE_PRUEBA)
        self.assertEqual(C.get(ruta, headers=otro).status_code, 404)
        self.assertEqual(C.post(ruta, headers=self.AL, json={"matricula": "22030001"}).status_code, 403)


class TestPaseDeLista(Base):
    """El docente descarga el pase de lista del día en Excel o PDF."""
    FECHA = "2026-11-28"   # sábado

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from _entorno import bd
        r = C.post("/api/schedules", headers=cls.A, json={
            "grupo_id": "ISC-501", "laboratorio_id": "LAB-RED", "docente_id": "DOC-ISC",
            "materia": "Programación Web", "dia_semana": "Sábado", "hora_inicio": "16:00", "hora_fin": "18:00"})
        assert r.status_code == 200, r.text
        cls.horario = r.json().get("id")
        c = bd()
        if not cls.horario:
            cls.horario = c.execute("SELECT id FROM horarios WHERE docente_id = 'DOC-ISC' AND dia_semana = 'Sábado' AND hora_inicio = '16:00'").fetchone()[0]
        # entrada del alumno dentro de la tolerancia (15:52) y del docente a las 15:55
        for uid, hora in (("AL-1", "15:52:10"), ("DOC-ISC", "15:55:00")):
            c.execute("""INSERT INTO registros_acceso (usuario_id, laboratorio_id, dispositivo_id, fecha_hora, resultado, motivo)
                         VALUES (?, 'LAB-RED', 'RPI-RED', ?, 'permitido', 'prueba')""", (uid, f"{cls.FECHA} {hora}"))
        c.commit()
        c.close()

    def bajar(self, H, **params):
        return C.get("/api/portal/teacher/attendance-list", headers=H, params=params)

    def test_excel_con_asistencia(self):
        import openpyxl
        r = self.bajar(self.DO, formato="xlsx", fecha=self.FECHA, horario_id=self.horario)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("spreadsheetml", r.headers["content-type"])
        self.assertIn("pase_lista_2026-11-28_ISC-501.xlsx", r.headers["content-disposition"])
        ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
        filas = [[c.value for c in f] for f in ws.iter_rows()]
        alumno = [f for f in filas if f[1] == "22030001"][0]
        self.assertEqual((alumno[3], alumno[4]), ("15:52", "Presente"))
        datos = {f[0]: f[1] for f in filas if f[0] and f[1]}
        self.assertEqual(datos["Entrada del docente"], "15:55")
        self.assertTrue(datos["Asistencia"].startswith("1 de "))   # otras pruebas agregan alumnos al grupo

    def test_pdf_de_una_clase(self):
        r = self.bajar(self.DO, formato="pdf", fecha=self.FECHA, horario_id=self.horario)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertIn("ISC-501", r.headers["content-disposition"])

    def test_sin_clases_ese_dia_y_fecha_invalida(self):
        self.assertEqual(self.bajar(self.DO, formato="pdf", fecha="2026-11-29").status_code, 404)   # domingo
        self.assertEqual(self.bajar(self.DO, formato="pdf", fecha="29/11/2026").status_code, 400)
        self.assertEqual(self.bajar(self.DO, formato="doc", fecha=self.FECHA).status_code, 422)

    def test_solo_el_docente_y_solo_sus_clases(self):
        self.assertEqual(self.bajar(self.AL, formato="xlsx", fecha=self.FECHA).status_code, 403)
        self.assertEqual(self.bajar(self.A, formato="xlsx", fecha=self.FECHA).status_code, 403)
        # otra persona no puede bajar una clase ajena pidiendo su horario_id
        from _entorno import poner_clave
        poner_clave("DOC-CIV")
        otro = entrar("200", CLAVE_PRUEBA)
        self.assertEqual(self.bajar(otro, formato="xlsx", fecha=self.FECHA, horario_id=self.horario).status_code, 404)


class TestLoginGoogle(Base):
    """«Continuar con Google»: solo @itsoeh.edu.mx y solo cuentas que ya existen (Google simulado)."""
    CID = "cliente-prueba.apps.googleusercontent.com"

    def setUp(self):
        import os
        import time
        from unittest import mock
        import backend.app as appmod
        self.time = time
        os.environ["NEOACCESS_GOOGLE_CLIENT_ID"] = self.CID
        self.addCleanup(os.environ.pop, "NEOACCESS_GOOGLE_CLIENT_ID", None)
        self.info = {}
        p = mock.patch.object(appmod, "_verificar_token_google", lambda cred: dict(self.info))
        p.start()
        self.addCleanup(p.stop)
        from _entorno import bd
        c = bd()
        c.execute("UPDATE usuarios SET correo = 'carlos.mendoza@itsoeh.edu.mx' WHERE id = 'AL-1'")
        c.commit()
        c.close()

    def token(self, correo, **cambios):
        self.info = {"aud": self.CID, "iss": "https://accounts.google.com", "exp": str(int(self.time.time()) + 600),
                     "email": correo, "email_verified": "true", "hd": "itsoeh.edu.mx", **cambios}
        return C.post("/api/auth/google", json={"credential": "x" * 40})

    def test_config_y_entrada_con_cuenta_existente(self):
        cfg = C.get("/api/auth/google-config").json()
        self.assertEqual((cfg["habilitado"], cfg["client_id"]), (True, self.CID))
        r = self.token("Carlos.Mendoza@itsoeh.edu.mx")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["admin"]["matricula_clave"], "22030001")
        H = {"Authorization": "Bearer " + r.json()["token"]}
        self.assertEqual(C.get("/api/portal/student-data", headers=H).status_code, 200)

    def test_rechazos(self):
        self.assertEqual(self.token("alguien@gmail.com", hd=None).status_code, 403)
        self.assertEqual(self.token("carlos.mendoza@itsoeh.edu.mx", hd="otra.edu.mx").status_code, 403)
        self.assertEqual(self.token("carlos.mendoza@itsoeh.edu.mx", aud="otro-cliente").status_code, 401)
        self.assertEqual(self.token("carlos.mendoza@itsoeh.edu.mx", email_verified="false").status_code, 401)
        self.assertEqual(self.token("carlos.mendoza@itsoeh.edu.mx", exp="1").status_code, 401)
        r = self.token("sin.cuenta@itsoeh.edu.mx")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Crear cuenta", r.json()["detail"])

    def test_deshabilitado_sin_client_id(self):
        import os
        os.environ.pop("NEOACCESS_GOOGLE_CLIENT_ID", None)
        self.assertFalse(C.get("/api/auth/google-config").json()["habilitado"])
        self.assertEqual(self.token("carlos.mendoza@itsoeh.edu.mx").status_code, 404)


class TestMetricasPorPuerta(Base):
    def test_resumen_e_historial_por_puerta(self):
        tok_a = C.post("/api/devices", headers=self.A, json={"id": "PTA-A", "laboratorio_id": "LAB-RED", "nombre": "Puerta A"}).json()["token_api"]
        tok_b = C.post("/api/devices", headers=self.A, json={"id": "PTA-B", "laboratorio_id": "LAB-CIV", "nombre": "Puerta B"}).json()["token_api"]
        acc = lambda dev, tok, res, usuario="22030001": C.post("/api/iot/access-attempt", json={
            "dispositivo_id": dev, "token_api": tok, "usuario_id": usuario, "resultado": res, "motivo": "métricas"})
        for r in ("permitido", "permitido", "denegado"):
            acc("PTA-A", tok_a, r)
        acc("PTA-B", tok_b, "denegado", None)

        puertas = {p["id"]: p for p in C.get("/api/metrics/by-door", headers=self.A).json()}
        a, b = puertas["PTA-A"], puertas["PTA-B"]
        self.assertEqual((a["total"], a["permitidos"], a["denegados"], a["hoy"]), (3, 2, 1, 3))
        self.assertEqual((b["total"], b["denegados"], b["ultimo_acceso"]["usuario_nombre"]), (1, 1, None))
        self.assertEqual(a["tasa"], 66.7)
        self.assertEqual(a["ultimo_acceso"]["resultado"], "denegado")
        self.assertNotIn("token_api", a)                                               # nunca se expone el token

        s = C.get("/api/metrics/summary", headers=self.A, params={"dispositivo_id": "PTA-A"}).json()
        self.assertEqual((s["total_accesos"], s["accesos_permitidos"]), (3, 2))
        self.assertGreaterEqual(C.get("/api/metrics/summary", headers=self.A).json()["total_accesos"], 4)   # general = todas
        hist = C.get("/api/metrics/recent-accesses", headers=self.A, params={"dispositivo_id": "PTA-A", "limit": 2}).json()
        self.assertEqual(len(hist), 2)
        self.assertTrue(all(h["dispositivo_id"] == "PTA-A" for h in hist))
        mas = C.get("/api/metrics/recent-accesses", headers=self.A, params={"dispositivo_id": "PTA-A", "limit": 2, "offset": 2}).json()
        self.assertEqual(len(mas), 1)
        den = C.get("/api/metrics/recent-accesses", headers=self.A, params={"dispositivo_id": "PTA-A", "resultado": "denegado"}).json()
        self.assertEqual([h["resultado"] for h in den], ["denegado"])
        dias = C.get("/api/metrics/by-day", headers=self.A, params={"dispositivo_id": "PTA-B"}).json()
        self.assertEqual(sum(d["total"] for d in dias), 1)
        self.assertEqual(C.get("/api/metrics/recent-accesses", headers=self.A, params={"limit": 0}).status_code, 422)  # límite
        self.assertEqual(C.get("/api/metrics/by-door", headers=self.J).status_code, 403)   # solo admin


class TestTokenDispositivo(Base):
    def test_regenerar_token_invalida_el_anterior(self):
        viejo = C.post("/api/devices", headers=self.A, json={"id": "RPI-TOK", "laboratorio_id": "LAB-RED", "nombre": "Puerta Token"}).json()["token_api"]
        latido = lambda tok: C.post("/api/iot/heartbeat", json={"dispositivo_id": "RPI-TOK", "token_api": tok}).status_code
        self.assertEqual(latido(viejo), 200)
        self.assertEqual(C.post("/api/devices/RPI-TOK/regenerate-token", headers=self.J).status_code, 403)   # solo admin
        self.assertEqual(C.post("/api/devices/NO-EXISTE/regenerate-token", headers=self.A).status_code, 404)
        nuevo = C.post("/api/devices/RPI-TOK/regenerate-token", headers=self.A).json()["token_api"]
        self.assertNotEqual(nuevo, viejo)
        self.assertEqual(latido(viejo), 403)
        self.assertEqual(latido(nuevo), 200)
        self.assertIn(nuevo, C.get("/api/devices/RPI-TOK/config-file", headers=self.A).text)

    def test_paquete_zip_para_raspberry(self):
        import json, zipfile
        tok = sembrar()["token_rpi"]
        self.assertEqual(C.get("/api/devices/RPI-RED/rpi-package", headers=self.J).status_code, 403)
        self.assertEqual(C.get("/api/devices/NO-EXISTE/rpi-package", headers=self.A).status_code, 404)
        r = C.get("/api/devices/RPI-RED/rpi-package", headers=self.A)
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombres = z.namelist()
        for f in ("rpi_main.py", "face_engine.py", "setup_rpi.sh", "config.json"):
            self.assertIn(f"neoaccess/{f}", nombres)
        self.assertFalse(any("simulator" in n or "cache_offline" in n or "cola_" in n for n in nombres))
        cfg = json.loads(z.read("neoaccess/config.json"))
        self.assertEqual((cfg["dispositivo_id"], cfg["token_api"]), ("RPI-RED", tok))
        self.assertNotIn(b"\r\n", z.read("neoaccess/setup_rpi.sh"))              # bash en Linux
        self.assertTrue((z.getinfo("neoaccess/setup_rpi.sh").external_attr >> 16) & 0o111)  # ejecutable


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
        fila = "Lunes,7:00,8:00,LAB-RED,ISC-501,100,Programación Web\n"
        self.assertEqual(self.subir("h.csv", (enc + fila * 1001).encode()).status_code, 400)

    def test_revisar_no_guarda_y_confirmar_no_duplica(self):
        enc = "Día,Hora inicio,Hora fin,Laboratorio,Grupo,Docente,Materia\n"
        datos = (enc + "Martes,18:00,19:00,LAB-RED,ISC-501,100,Programación Web\n"
                       "Martes,18:30,19:30,LAB-RED,ISC-501,100,Programación Web\n").encode()
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
                                           ("200", "permitido", "2026-10-01 08:00:00")]:
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
