"""
NeoAccess - Módulo Exclusivo de Base de Datos SQLite
Ubicación: C:\\Users\\gr321\\Desktop\\NeoAccess\\database\\database.py
"""

import sqlite3
import os

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
        docente_id TEXT NOT NULL,
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

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Base de datos de NeoAccess inicializada y actualizada en:", DB_PATH)
