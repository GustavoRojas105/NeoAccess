"""
NeoAccess - Semilla de Datos Iniciales (Seed Data)
Pobla la base de datos con laboratorios reales del ITSOEH (Edificio 6 y STEM),
dispositivos Raspberry Pi Zero W, docentes, alumnos, horarios y registros de prueba.
"""

import sqlite3
import json
import random
import secrets
import hashlib
from datetime import datetime, timedelta
import os
import sys
from database import get_connection, init_db

# Reutilizar el mismo algoritmo de hashing que el servidor (PBKDF2)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.auth import hash_password


def seed():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM administradores;")
    if cursor.fetchone()["total"] > 0:
        print("La base de datos ya contiene datos. Saltando semilla.")
        conn.close()
        return

    print("Poblando base de datos con datos de prueba del ITSOEH...")

    # 1. Administrador Inicial (RF-18)
    admin_hash = hash_password("admin123")
    cursor.execute("""
    INSERT INTO administradores (username, password_hash, nombre, email, activo)
    VALUES (?, ?, ?, ?, 1)
    """, ("admin", admin_hash, "Ing. Administrador General - ITSOEH", "admin.neoaccess@itsoeh.edu.mx"))

    # 2. Laboratorios (Edificio 6 y STEM)
    labs = [
        ("LAB-STEM-01", "Lab STEM de Robótica y Automatización", "Laboratorios STEM", "Ingeniería en Electromecánica", 25, "Equipado con brazos robóticos y celdas de manufactura"),
        ("LAB-STEM-02", "Lab STEM de IoT y Sistemas Embebidos", "Laboratorios STEM", "Ingeniería en Electromecánica", 25, "Especializado en microcontroladores, ESP32 y Raspberry Pi"),
        ("LAB-STEM-03", "Lab STEM de Prototipado y Fabricación Digital", "Laboratorios STEM", "Ingeniería en Electromecánica", 20, "Impresoras 3D, corte láser y estaciones CNC"),
        ("LAB-ED6-01", "Lab de Cómputo y Simulación 1", "Edificio 6", "Ingeniería en Electromecánica", 35, "Estaciones de trabajo para MATLAB, SolidWorks y LabVIEW"),
        ("LAB-ED6-02", "Lab de Redes y Cómputo Distribuido", "Edificio 6", "Ingeniería en Sistemas Computacionales", 30, "Racks de telecomunicaciones y switches administrables")
    ]
    cursor.executemany("""
    INSERT INTO laboratorios (id, nombre, edificio, carrera, capacidad, descripcion, activo)
    VALUES (?, ?, ?, ?, ?, ?, 1)
    """, labs)

    # 3. Dispositivos Raspberry Pi Zero W
    ahora = datetime.now()
    dispositivos = [
        ("DEV-PI-STEM01", "LAB-STEM-01", "RPi Zero W - Puerta Robótica", "neo_pi_robotica_stem_01", "192.168.1.111", "B8:27:EB:11:22:33", 300, ahora.strftime("%Y-%m-%d %H:%M:%S"), "en_linea", 1),
        ("DEV-PI-STEM02", "LAB-STEM-02", "RPi Zero W - Puerta IoT", "neo_pi_iot_stem_02", "192.168.1.112", "B8:27:EB:44:55:66", 300, (ahora - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"), "en_linea", 1),
        ("DEV-PI-STEM03", "LAB-STEM-03", "RPi Zero W - Puerta Fabricación", "neo_pi_fab_stem_03", "192.168.1.113", "B8:27:EB:77:88:99", 300, (ahora - timedelta(minutes=14)).strftime("%Y-%m-%d %H:%M:%S"), "intermitente", 1),
        ("DEV-PI-ED601", "LAB-ED6-01", "RPi Zero W - Puerta Cómputo 1", "neo_pi_comp1_ed6_01", "192.168.1.114", "B8:27:EB:AA:BB:CC", 300, (ahora - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), "fuera_de_linea", 1),
        ("DEV-PI-ED602", "LAB-ED6-02", "RPi Zero W - Puerta Redes", "neo_pi_redes_ed6_02", "192.168.1.115", "B8:27:EB:DD:EE:FF", 300, ahora.strftime("%Y-%m-%d %H:%M:%S"), "en_linea", 1)
    ]
    cursor.executemany("""
    INSERT INTO dispositivos (id, laboratorio_id, nombre, token_api, ip_address, mac_address, intervalo_latido_seg, ultima_senal, estado, activo)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, dispositivos)

    # 4. Grupos
    grupos = [
        ("MEC-801", "801 Electromecánica (Robótica)", "Ingeniería en Electromecánica", 8),
        ("MEC-601", "601 Electromecánica (Control)", "Ingeniería en Electromecánica", 6),
        ("MEC-401", "401 Electromecánica (Electrónica)", "Ingeniería en Electromecánica", 4),
        ("SIS-701", "701 Sistemas (IoT y Redes)", "Ingeniería en Sistemas Computacionales", 7)
    ]
    cursor.executemany("""
    INSERT INTO grupos (id, nombre, carrera, semestre)
    VALUES (?, ?, ?, ?)
    """, grupos)

    # 5. Usuarios
    usuarios = [
        ("DOC-001", "Dr. Martín Gómez Pérez", "docente", "DOC-ITSOEH-7489", "Ingeniería en Electromecánica", None, "activo"),
        ("DOC-002", "Mtra. Laura Elena Sánchez", "docente", "DOC-ITSOEH-8912", "Ingeniería en Electromecánica", None, "activo"),
        ("DOC-003", "Ing. Roberto Carlos Viveros", "docente", "DOC-ITSOEH-3301", "Ingeniería en Sistemas Computacionales", None, "activo"),
        ("ALU-001", "Carlos Alberto Mendoza Hernández", "alumno", "22030015", "Ingeniería en Electromecánica", "MEC-801", "activo"),
        ("ALU-002", "Ana Sofía Torres Morales", "alumno", "22030048", "Ingeniería en Electromecánica", "MEC-801", "activo"),
        ("ALU-003", "Gustavo Rojas Morales", "alumno", "22030088", "Ingeniería en Electromecánica", "MEC-801", "activo"),
        ("ALU-004", "Fernando Javier Ruiz Aguilar", "alumno", "22030105", "Ingeniería en Electromecánica", "MEC-601", "activo"),
        ("ALU-005", "Diego Ramírez Cruz", "alumno", "22030112", "Ingeniería en Sistemas Computacionales", "SIS-701", "activo"),
        ("ALU-006", "Valeria Ortiz Domínguez", "alumno", "22030095", "Ingeniería en Electromecánica", "MEC-601", "activo"),
        ("ALU-007", "Mariana Gómez Almaraz", "alumno", "22030154", "Ingeniería en Sistemas Computacionales", "SIS-701", "activo"),
        ("LIM-001", "Don Pedro Jiménez López", "personal_limpieza", "LIM-ITSOEH-104", "Servicios Generales", None, "activo"),
        ("LIM-002", "Sra. Carmen Bautista Cruz", "personal_limpieza", "LIM-ITSOEH-105", "Servicios Generales", None, "activo")
    ]
    cursor.executemany("""
    INSERT INTO usuarios (id, nombre_completo, tipo, matricula_clave, carrera, grupo_id, estado)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, usuarios)

    # 6. Metadatos Faciales (Vectores 128-d simulados - ¡Cero fotos almacenadas!)
    random.seed(42)
    for u in usuarios:
        uid = u[0]
        vector = [round(random.uniform(-0.15, 0.15), 6) for _ in range(128)]
        cursor.execute("""
        INSERT INTO metadatos_faciales (usuario_id, vector_encoding, dimension, calidad_muestra)
        VALUES (?, ?, 128, 0.98)
        """, (uid, json.dumps(vector)))

    # 7. Horarios Semanales
    horarios = [
        ("MEC-801", "LAB-STEM-01", "DOC-001", "Robótica Industrial", "Lunes", "07:00", "09:00"),
        ("MEC-801", "LAB-STEM-02", "DOC-002", "Internet de las Cosas", "Lunes", "09:00", "11:00"),
        ("SIS-701", "LAB-ED6-02", "DOC-003", "Redes Neuronales y Cómputo", "Lunes", "11:00", "13:00"),
        ("MEC-601", "LAB-STEM-01", "DOC-001", "Control de Procesos Industriales", "Martes", "08:00", "10:00"),
        ("MEC-801", "LAB-STEM-03", "DOC-002", "Manufactura Digital Avanzada", "Martes", "10:00", "12:00"),
        ("MEC-801", "LAB-STEM-01", "DOC-001", "Robótica Industrial", "Miércoles", "07:00", "09:00"),
        ("SIS-701", "LAB-ED6-02", "DOC-003", "Sistemas Distribuidos", "Miércoles", "09:00", "11:00"),
        ("MEC-601", "LAB-ED6-01", "DOC-002", "Simulación Mecatrónica", "Miércoles", "11:00", "13:00"),
        ("MEC-801", "LAB-STEM-02", "DOC-002", "Proyecto Integrador IoT", "Jueves", "13:00", "15:00"),
        ("MEC-401", "LAB-STEM-01", "DOC-001", "Circuitos Lógicos y PLC", "Jueves", "15:00", "17:00"),
        ("MEC-801", "LAB-STEM-03", "DOC-002", "Taller de Prototipos STEM", "Viernes", "08:00", "11:00"),
        ("SIS-701", "LAB-ED6-01", "DOC-003", "Laboratorio de Algoritmos", "Viernes", "11:00", "13:00")
    ]
    cursor.executemany("""
    INSERT INTO horarios (grupo_id, laboratorio_id, docente_id, materia, dia_semana, hora_inicio, hora_fin)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, horarios)

    # 8. Generación de Registros de Acceso Históricos para Métricas
    motivos_permitidos = [
        "Acceso autorizado por horario de clase asignado",
        "Docente en turno - Inicio de sesión de laboratorio confirmado",
        "Práctica programada en laboratorio STEM"
    ]
    motivos_denegados = [
        "Acceso denegado: Fuera del horario de clase asignado",
        "Acceso denegado: El grupo no tiene clase en este laboratorio",
        "Rostro no registrado en el sistema local",
        "Docente fuera de horario lectivo"
    ]

    fecha_base = ahora - timedelta(days=7)
    alumnos_ids = ["ALU-001", "ALU-002", "ALU-003", "ALU-004", "ALU-005", "ALU-006"]
    docentes_ids = ["DOC-001", "DOC-002", "DOC-003"]
    dev_map = {
        "LAB-STEM-01": "DEV-PI-STEM01",
        "LAB-STEM-02": "DEV-PI-STEM02",
        "LAB-STEM-03": "DEV-PI-STEM03",
        "LAB-ED6-01": "DEV-PI-ED601",
        "LAB-ED6-02": "DEV-PI-ED602"
    }

    registros = []
    for d in range(8):
        current_day = fecha_base + timedelta(days=d)
        if current_day.weekday() >= 5:
            continue

        num_accesos = random.randint(18, 30)
        for _ in range(num_accesos):
            lab_id = random.choice(list(dev_map.keys()))
            dev_id = dev_map[lab_id]
            hora_random = current_day.replace(
                hour=random.randint(7, 16),
                minute=random.randint(0, 59),
                second=random.randint(0, 59)
            ).strftime("%Y-%m-%d %H:%M:%S")

            es_exitoso = random.random() < 0.88
            if es_exitoso:
                u_id = random.choice(alumnos_ids if random.random() < 0.8 else docentes_ids)
                resultado = "permitido"
                motivo = random.choice(motivos_permitidos)
            else:
                u_id = random.choice(alumnos_ids) if random.random() < 0.7 else None
                resultado = "denegado"
                motivo = random.choice(motivos_denegados)

            registros.append((u_id, dev_id, lab_id, hora_random, resultado, motivo, 0))

    cursor.executemany("""
    INSERT INTO registros_acceso (usuario_id, dispositivo_id, laboratorio_id, fecha_hora, resultado, motivo, sincronizado_offline)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, registros)

    # 9. Registros de Limpieza (RF-04)
    limpiezas = [
        ("LIM-001", "DEV-PI-STEM01", "LAB-STEM-01", (ahora - timedelta(days=1, hours=4)).strftime("%Y-%m-%d 06:15:00"), (ahora - timedelta(days=1, hours=3)).strftime("%Y-%m-%d 06:55:00")),
        ("LIM-001", "DEV-PI-STEM02", "LAB-STEM-02", (ahora - timedelta(days=1, hours=3)).strftime("%Y-%m-%d 07:05:00"), (ahora - timedelta(days=1, hours=2)).strftime("%Y-%m-%d 07:45:00")),
        ("LIM-002", "DEV-PI-ED602", "LAB-ED6-02", ahora.strftime("%Y-%m-%d 06:30:00"), ahora.strftime("%Y-%m-%d 07:10:00")),
        ("LIM-001", "DEV-PI-STEM01", "LAB-STEM-01", ahora.strftime("%Y-%m-%d 14:10:00"), None)
    ]
    cursor.executemany("""
    INSERT INTO registros_limpieza (personal_id, dispositivo_id, laboratorio_id, hora_entrada, hora_salida)
    VALUES (?, ?, ?, ?, ?)
    """, limpiezas)

    # 10. Eventos de Dispositivos (RF-21)
    eventos = [
        ("DEV-PI-STEM01", "conexion", "Dispositivo conectado a red Wi-Fi institucional ITSOEH", (ahora - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")),
        ("DEV-PI-STEM01", "sincronizacion", "Lista de usuarios y horarios fuera de línea sincronizada", (ahora - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")),
        ("DEV-PI-STEM02", "conexion", "Dispositivo reportando latido normal", (ahora - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")),
        ("DEV-PI-STEM03", "intermitencia", "Retraso en latido periódico (>10 min) detectado", (ahora - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")),
        ("DEV-PI-ED601", "desconexion", "Dispositivo sin respuesta de latido", (ahora - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"))
    ]
    cursor.executemany("""
    INSERT INTO eventos_dispositivo (dispositivo_id, tipo_evento, descripcion, fecha_hora)
    VALUES (?, ?, ?, ?)
    """, eventos)

    conn.commit()
    conn.close()
    print("¡Base de datos sembrada con éxito en database/neoaccess.db!")

if __name__ == "__main__":
    seed()
