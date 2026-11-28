"""
NeoAccess - Módulo Exclusivo de Base de Datos SQLite
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\database\\database.py
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "neoaccess.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Administradores (RF-18)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS administradores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nombre TEXT NOT NULL,
        email TEXT,
        activo INTEGER DEFAULT 1,
        fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Laboratorios o salones (RF-17, Sec. 8)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS laboratorios (
        id TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        edificio TEXT NOT NULL,
        carrera TEXT NOT NULL,
        capacidad INTEGER DEFAULT 30,
        descripcion TEXT,
        activo INTEGER DEFAULT 1,
        fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3. Dispositivos de puerta (Raspberry Pi Zero W) (Sec. 6, 8, RF-10 al RF-13)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dispositivos (
        id TEXT PRIMARY KEY,
        laboratorio_id TEXT,
        nombre TEXT NOT NULL,
        token_api TEXT UNIQUE NOT NULL,
        ip_address TEXT,
        mac_address TEXT,
        intervalo_latido_seg INTEGER DEFAULT 300,
        ultima_senal TEXT,
        estado TEXT DEFAULT 'fuera_de_linea',
        activo INTEGER DEFAULT 1,
        fecha_alta TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (laboratorio_id) REFERENCES laboratorios (id) ON DELETE SET NULL
    );
    """)

    # 4. Grupos (Sec. 8)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grupos (
        id TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        carrera TEXT NOT NULL,
        semestre INTEGER NOT NULL
    );
    """)

    # 5. Usuarios: alumnos, docentes, personal de limpieza, administradores (Sec. 4, 8, RF-14)
    # Incluye password_hash para acceso a portales por rol (Docente, Alumno, Limpieza)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        nombre_completo TEXT NOT NULL,
        tipo TEXT NOT NULL, -- 'alumno', 'docente', 'personal_limpieza', 'administrador'
        matricula_clave TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        carrera TEXT,
        grupo_id TEXT,
        estado TEXT DEFAULT 'activo',
        fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE SET NULL
    );
    """)

    # Migración de columna password_hash si ya existía la tabla
    cursor.execute("PRAGMA table_info(usuarios);")
    columns = [col[1] for col in cursor.fetchall()]
    if "password_hash" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN password_hash TEXT;")
    # Autoregistro: correo institucional verificado y aprobación de cuentas de docente
    if "correo" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN correo TEXT;")
    if "cuenta_aprobada" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN cuenta_aprobada INTEGER DEFAULT 1;")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_correo ON usuarios (correo) WHERE correo IS NOT NULL;")
    if "debe_cambiar_password" not in columns:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN debe_cambiar_password INTEGER NOT NULL DEFAULT 0;")

    # Configuración global del sistema (p. ej. modo mantenimiento)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuracion_sistema (
        clave TEXT PRIMARY KEY,
        valor TEXT,
        actualizado TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Registros en espera de verificación por correo (@itsoeh.edu.mx).
    # La cuenta se crea solo cuando el usuario abre el enlace; aquí se guarda el hash del token, nunca el token.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registros_pendientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_hash TEXT UNIQUE NOT NULL,
        correo TEXT NOT NULL,
        matricula_clave TEXT NOT NULL,
        nombre_completo TEXT NOT NULL,
        tipo TEXT NOT NULL,
        carrera TEXT,
        password_hash TEXT NOT NULL,
        expira TEXT NOT NULL,
        fecha_solicitud TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Verificación por código de 6 dígitos: intentos fallidos del código vigente
    cursor.execute("PRAGMA table_info(registros_pendientes);")
    if "intentos" not in [col[1] for col in cursor.fetchall()]:
        cursor.execute("ALTER TABLE registros_pendientes ADD COLUMN intentos INTEGER DEFAULT 0;")

    # Recuperación de contraseña por código enviado al correo institucional.
    # Se guarda solo el hash del código; caduca en minutos y tiene intentos limitados.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recuperaciones_password (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        correo TEXT NOT NULL,
        cuenta_tipo TEXT NOT NULL,
        cuenta_id TEXT NOT NULL,
        codigo_hash TEXT NOT NULL,
        expira TEXT NOT NULL,
        intentos INTEGER DEFAULT 0,
        fecha_solicitud TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. Metadatos faciales (Sec. 2, 8, RF-07, RF-15)
    # IMPORTANTE: NO se guardan fotos, solo metadatos vectoriales (128 floats en JSON)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadatos_faciales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id TEXT UNIQUE NOT NULL,
        vector_encoding TEXT NOT NULL,
        dimension INTEGER DEFAULT 128,
        calidad_muestra REAL DEFAULT 1.0,
        fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
    );
    """)

    # 7. Horarios (Sec. 8, RF-02, RF-03, RF-17)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grupo_id TEXT,
        laboratorio_id TEXT NOT NULL,
        docente_id TEXT,                    -- NULL = actividad del laboratorio sin docente
        materia TEXT NOT NULL,
        dia_semana TEXT NOT NULL,
        hora_inicio TEXT NOT NULL,
        hora_fin TEXT NOT NULL,
        FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE CASCADE,
        FOREIGN KEY (laboratorio_id) REFERENCES laboratorios (id) ON DELETE CASCADE,
        FOREIGN KEY (docente_id) REFERENCES usuarios (id) ON DELETE CASCADE
    );
    """)

    # 8. Registros de acceso (Sec. 8, RF-05, RF-06)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registros_acceso (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id TEXT,
        dispositivo_id TEXT NOT NULL,
        laboratorio_id TEXT NOT NULL,
        fecha_hora TEXT NOT NULL,
        resultado TEXT NOT NULL,
        motivo TEXT NOT NULL,
        sincronizado_offline INTEGER DEFAULT 0,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL,
        FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id) ON DELETE CASCADE,
        FOREIGN KEY (laboratorio_id) REFERENCES laboratorios (id) ON DELETE CASCADE
    );
    """)

    # 9. Registros de limpieza (Sec. 5, 8, RF-04)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registros_limpieza (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id TEXT NOT NULL,
        dispositivo_id TEXT NOT NULL,
        laboratorio_id TEXT NOT NULL,
        hora_entrada TEXT NOT NULL,
        hora_salida TEXT,
        FOREIGN KEY (personal_id) REFERENCES usuarios (id) ON DELETE CASCADE,
        FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id) ON DELETE CASCADE,
        FOREIGN KEY (laboratorio_id) REFERENCES laboratorios (id) ON DELETE CASCADE
    );
    """)

    # 10. Eventos de dispositivo (Sec. 8, RF-21)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eventos_dispositivo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dispositivo_id TEXT NOT NULL,
        tipo_evento TEXT NOT NULL,
        descripcion TEXT,
        fecha_hora TEXT NOT NULL,
        FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id) ON DELETE CASCADE
    );
    """)

    # 11. Comandos remotos para dispositivos (apertura manual desde el Dashboard)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comandos_dispositivo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dispositivo_id TEXT NOT NULL,
        tipo TEXT NOT NULL,                 -- 'abrir_puerta'
        estado TEXT DEFAULT 'pendiente',    -- 'pendiente', 'entregado', 'ejecutado', 'fallido', 'expirado'
        solicitado_por TEXT,
        fecha_creacion TEXT NOT NULL,
        fecha_expira TEXT NOT NULL,
        fecha_ejecucion TEXT,
        detalle TEXT,
        FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comandos_pendientes ON comandos_dispositivo (dispositivo_id, estado);")

    # 12. Periodos escolares (Ene-Jun / Ago-Dic). Solo uno 'activo'; los 'cerrado' quedan como histórico.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS periodos (
        id TEXT PRIMARY KEY,                -- '2026-2' (1 = Ene-Jun, 2 = Ago-Dic)
        nombre TEXT NOT NULL,               -- 'Ago-Dic 2026'
        fecha_inicio TEXT NOT NULL,
        fecha_fin TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'activo',
        fecha_cierre TEXT,
        cerrado_por TEXT
    );
    """)

    # 13. Histórico de inscripciones (foto al cerrar cada periodo; sin FK para que nunca se pierda)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inscripciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        periodo_id TEXT NOT NULL,
        usuario_id TEXT NOT NULL,
        nombre_completo TEXT,
        matricula_clave TEXT,
        carrera TEXT,
        grupo_id TEXT,
        grupo_clave TEXT,
        grupo_nombre TEXT,
        semestre INTEGER
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inscripciones_usuario ON inscripciones (usuario_id);")

    # 13a. Contraseña temporal puesta por el administrador: se pide cambiarla al entrar
    for tabla in ("administradores", "jefes_carrera"):
        cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({tabla});").fetchall()]
        if cols and "debe_cambiar_password" not in cols:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN debe_cambiar_password INTEGER NOT NULL DEFAULT 0;")

    # 13c. Bitácora: quién metió o sacó a un alumno de un grupo (asignar un grupo da acceso físico)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asignaciones_grupo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT DEFAULT (datetime('now', 'localtime')),
        actor_rol TEXT NOT NULL,
        actor_id TEXT,
        actor_nombre TEXT,
        usuario_id TEXT NOT NULL,
        matricula TEXT,
        grupo_anterior TEXT,
        grupo_nuevo TEXT
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_asignaciones_grupo_usuario ON asignaciones_grupo (usuario_id);")

    # 13b. Alumnos inscritos a clases fuera de su grupo (carga académica del SEIT o agregados por el docente)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inscripciones_clase (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        horario_id INTEGER NOT NULL REFERENCES horarios(id) ON DELETE CASCADE,
        origen TEXT NOT NULL DEFAULT 'carga',
        codigo_seit TEXT,
        fecha TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (usuario_id, horario_id)
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inscripciones_clase_horario ON inscripciones_clase (horario_id);")

    # 14. Jefes de carrera (cuenta aparte, una o más carreras)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jefes_carrera (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nombre TEXT NOT NULL,
        email TEXT,
        activo INTEGER DEFAULT 1,
        fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jefe_carreras (
        jefe_id INTEGER NOT NULL,
        carrera TEXT NOT NULL,
        PRIMARY KEY (jefe_id, carrera),
        FOREIGN KEY (jefe_id) REFERENCES jefes_carrera (id) ON DELETE CASCADE
    );
    """)

    # Columnas de periodo (migración de bases existentes)
    def _columnas(tabla):
        return {r[1] for r in cursor.execute(f"PRAGMA table_info({tabla});").fetchall()}
    if "periodo_id" not in _columnas("grupos"):
        cursor.execute("ALTER TABLE grupos ADD COLUMN periodo_id TEXT;")
    if "clave" not in _columnas("grupos"):
        cursor.execute("ALTER TABLE grupos ADD COLUMN clave TEXT;")   # clave visible (el id se archiva al cerrar)
    if "periodo_id" not in _columnas("horarios"):
        cursor.execute("ALTER TABLE horarios ADD COLUMN periodo_id TEXT;")
    if "periodo_id" not in _columnas("registros_acceso"):
        cursor.execute("ALTER TABLE registros_acceso ADD COLUMN periodo_id TEXT;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accesos_periodo ON registros_acceso (periodo_id);")

    # horarios.docente_id pasa a ser opcional (actividades sin docente). SQLite no permite quitar
    # NOT NULL con ALTER: se reconstruye la tabla conservando ids y datos.
    docente_col = [r for r in cursor.execute("PRAGMA table_info(horarios);").fetchall() if r[1] == "docente_id"]
    if docente_col and docente_col[0][3]:  # notnull = 1
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF;")
        cursor.executescript("""
        BEGIN;
        CREATE TABLE horarios_nueva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id TEXT,
            laboratorio_id TEXT NOT NULL,
            docente_id TEXT,
            materia TEXT NOT NULL,
            dia_semana TEXT NOT NULL,
            hora_inicio TEXT NOT NULL,
            hora_fin TEXT NOT NULL,
            periodo_id TEXT,
            FOREIGN KEY (grupo_id) REFERENCES grupos (id) ON DELETE CASCADE,
            FOREIGN KEY (laboratorio_id) REFERENCES laboratorios (id) ON DELETE CASCADE,
            FOREIGN KEY (docente_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );
        INSERT INTO horarios_nueva (id, grupo_id, laboratorio_id, docente_id, materia, dia_semana, hora_inicio, hora_fin, periodo_id)
            SELECT id, grupo_id, laboratorio_id, docente_id, materia, dia_semana, hora_inicio, hora_fin, periodo_id FROM horarios;
        DROP TABLE horarios;
        ALTER TABLE horarios_nueva RENAME TO horarios;
        COMMIT;
        """)
        conn.execute("PRAGMA foreign_keys = ON;")

    # Periodo inicial según la fecha de hoy, y asignar lo existente al periodo activo
    if not cursor.execute("SELECT 1 FROM periodos WHERE estado = 'activo'").fetchone():
        p = periodo_para_fecha(datetime.now())
        cursor.execute("INSERT OR IGNORE INTO periodos (id, nombre, fecha_inicio, fecha_fin, estado) VALUES (?, ?, ?, ?, 'activo')",
                       (p["id"], p["nombre"], p["fecha_inicio"], p["fecha_fin"]))
        cursor.execute("UPDATE periodos SET estado = 'activo' WHERE id = ?", (p["id"],))
    activo = cursor.execute("SELECT id FROM periodos WHERE estado = 'activo'").fetchone()[0]
    cursor.execute("UPDATE grupos SET periodo_id = ? WHERE periodo_id IS NULL", (activo,))
    cursor.execute("UPDATE grupos SET clave = id WHERE clave IS NULL")
    cursor.execute("UPDATE horarios SET periodo_id = ? WHERE periodo_id IS NULL", (activo,))
    cursor.execute("UPDATE registros_acceso SET periodo_id = ? WHERE periodo_id IS NULL", (activo,))

    conn.commit()
    conn.close()


# ─────────────── Periodos escolares (Ene-Jun / Ago-Dic) ───────────────
def periodo_para_fecha(fecha) -> dict:
    """Ene-Jun = '{año}-1'; Jul-Dic = '{año}-2' (julio se cuenta como vacaciones previas a Ago-Dic)."""
    if fecha.month <= 6:
        return {"id": f"{fecha.year}-1", "nombre": f"Ene-Jun {fecha.year}",
                "fecha_inicio": f"{fecha.year}-01-01", "fecha_fin": f"{fecha.year}-06-30"}
    return {"id": f"{fecha.year}-2", "nombre": f"Ago-Dic {fecha.year}",
            "fecha_inicio": f"{fecha.year}-08-01", "fecha_fin": f"{fecha.year}-12-31"}


def periodo_siguiente(periodo_id: str) -> dict:
    anio, n = periodo_id.split("-")
    anio = int(anio)
    if n == "1":
        return {"id": f"{anio}-2", "nombre": f"Ago-Dic {anio}",
                "fecha_inicio": f"{anio}-08-01", "fecha_fin": f"{anio}-12-31"}
    return {"id": f"{anio + 1}-1", "nombre": f"Ene-Jun {anio + 1}",
            "fecha_inicio": f"{anio + 1}-01-01", "fecha_fin": f"{anio + 1}-06-30"}

if __name__ == "__main__":
    init_db()
    print("Base de datos de NeoAccess inicializada y actualizada en:", DB_PATH)
