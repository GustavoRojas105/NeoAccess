# NeoAccess • Plataforma IoT de Control de Acceso

**Sistema de control de acceso con reconocimiento facial y registro digital para los laboratorios del Edificio 6 y los laboratorios STEM del ITSOEH**

- **Autor:** Gustavo Antonio Rojas Morales
- **Programa:** Maestría en Ingeniería Mecatrónica
- **Institución:** Instituto Tecnológico Superior del Occidente del Estado de Hidalgo (ITSOEH)
- **Fecha:** Diciembre de 2026

---

## 📁 Nueva Estructura Modular del Proyecto

El proyecto está organizado de manera limpia y modular por responsabilidades:

```
NeoAccess/
├── database/                  # Base de datos relacional y scripts SQL
│   ├── neoaccess.db           # Base de datos SQLite (10 tablas)
│   ├── database.py            # Esquema y conexión PRAGMA
│   └── seed_data.py           # Datos precargados del ITSOEH
│
├── backend/                   # Servidor central y API REST / IoT
│   ├── app.py                 # Endpoints FastAPI y controlador de red
│   ├── auth.py                # Autenticación PBKDF2-SHA256 (600k iteraciones) + límite de intentos
│   └── models.py              # Modelos Pydantic de validación
│
├── frontend/                  # Interfaz gráfica de usuario (SPA)
│   ├── html/
│   │   └── index.html         # Dashboard principal con diseño neutral
│   ├── styles/
│   │   └── style.css          # Estilos sobrios y reservas verde/amarillo/rojo
│   └── scripts/
│       ├── app.js             # Enrutador y control de sesión
│       ├── laboratories.js    # NUEVO: Gestión y alta de laboratorios reales
│       ├── devices.js         # Monitor de Raspberry Pi Zero W y puertas
│       ├── metrics.js         # KPIs y gráficos interactivos Chart.js
│       ├── schedules.js       # Asignación de horarios semanales
│       ├── users.js           # Alumnos, docentes y captura facial (128-d)
│       └── reports.js         # Reportes y descarga en formato CSV
│
├── raspberry_pi/              # PAQUETE COMPLETO PARA TU RASPBERRY PI ZERO W
│   ├── rpi_main.py            # Software de control de puerta (Cámara + Relé GPIO 17)
│   ├── test_conexion.py       # Diagnóstico en vivo de red y prueba de relevador
│   ├── config.json            # Configuración de IP, Token y Pines GPIO
│   ├── config.json.template   # Plantilla de configuración
│   ├── setup_rpi.sh           # Instalador automático en Raspberry Pi OS
│   ├── requirements.txt       # Librerías necesarias (RPi.GPIO, requests, etc.)
│   └── LEEME_RASPBERRY.md     # Guía detallada de conexión para la Raspberry Pi
│
├── docs/                      # Documentación del sistema
│   ├── CONECTAR_RPI_ZERO.md   # Diagrama de pines y protocolo de red
│   ├── GUIA_INSTALACION.md    # Manual paso a paso
│   └── ARQUITECTURA.md        # Arquitectura de hardware, datos y privacidad
│
├── run_server.bat             # Inicia el Servidor Central y abre el Dashboard
├── run_simulator.bat          # Simulador interactivo para pruebas en PC
└── README.md                  # Este documento
```

---

## 🚀 Inicio Rápido (Servidor Central)

1. En tu computadora, haz doble clic en **`run_server.bat`**.
2. Abrirá automáticamente el Dashboard en tu navegador: `http://localhost:8000`.
3. Inicia sesión con:
   - **Usuario:** `admin`
   - **Contraseña:** `admin123`

---

## 🏫 Cómo Agregar un Nuevo Laboratorio Real

1. En el Dashboard, dirígete a la nueva sección **"Laboratorios y Salones"** en el menú izquierdo.
2. Haz clic en el botón superior **"+ Agregar Laboratorio"**.
3. Ingresa los datos:
   - **Clave / ID:** Ejemplo: `LAB-STEM-04` o `LAB-ED6-03`.
   - **Nombre:** Ejemplo: `Laboratorio de Visión Artificial y Robótica`.
   - **Edificio:** Selecciona `Laboratorios STEM`, `Edificio 6`, etc.
   - **Carrera:** Ejemplo: `Ingeniería Mecatrónica`.
   - **Capacidad:** Ejemplo: `30` alumnos.
4. Haz clic en **Guardar Laboratorio**. El laboratorio quedará registrado de forma permanente en la base de datos y disponible al instante en filtros, horarios y puertas.

---

## 🔌 Cómo Poner a Funcionar tu Raspberry Pi Zero W Real

1. Copia toda la carpeta **`raspberry_pi/`** a tu Raspberry Pi Zero W.
2. Consulta la guía completa en [`raspberry_pi/LEEME_RASPBERRY.md`](file:///C:/Users/gr321/Desktop/NeoAccess/raspberry_pi/LEEME_RASPBERRY.md).
3. Conecta el relevador de la cerradura electromagnética al **Pin GPIO 17** y los indicadores a los pines correspondientes.
4. Ejecuta el diagnóstico de conexión en la Raspberry Pi:
   ```bash
   python3 test_conexion.py
   ```
   Verás las 4 pruebas automáticas y escucharás el "clic" mecánico del relevador.
5. Inicia el sistema con:
   ```bash
   python3 rpi_main.py
   ```

---

## 🔐 Seguridad (actualización)

- **Contraseñas:** PBKDF2-HMAC-SHA256 con 600 000 iteraciones. Los hashes antiguos (SHA-256 simple) se migran automáticamente la próxima vez que cada usuario inicia sesión.
- **Fuerza bruta:** después de 5 intentos fallidos con el mismo usuario (o 20 desde la misma IP) en 15 minutos, el login se bloquea 15 minutos (HTTP 429).
- **Dispositivos IoT:** cada Raspberry Pi solo puede reportar eventos con su propio `dispositivo_id`; el token viaja en el header `X-Device-Token` al sincronizar reglas.
- **CORS:** deshabilitado por defecto (el Dashboard se sirve desde el mismo servidor). Para permitir otro origen: `set NEOACCESS_CORS_ORIGINS=http://host:puerto`.
- **Modo desarrollo:** la recarga automática del servidor solo se activa con `set NEOACCESS_DEV=1`.
- **Cambia las contraseñas por defecto** (`admin123`, `docente123`, etc.) antes de usar el sistema con datos reales.

---

## 🧠 Reconocimiento facial real (YuNet + SFace)

El servidor y las puertas usan **el mismo motor** ([`raspberry_pi/face_engine.py`](raspberry_pi/face_engine.py)) basado en modelos ONNX de OpenCV, así los vectores registrados y los capturados en la puerta son comparables:

- **YuNet** detecta el rostro; **SFace** genera el vector de 128 dimensiones; se comparan por **similitud coseno** (umbral `umbral_similitud_coseno`, 0.363 por defecto; súbelo, p. ej. a 0.45, si hay falsos positivos).
- **Modelos:** `python raspberry_pi/descargar_modelos.py` (≈37 MB, una sola vez en la PC y en cada Pi). `run_server.bat` y `setup_rpi.sh` lo hacen automáticamente.
- **Registro (Dashboard → Usuarios → cámara):** el navegador toma 3 fotogramas, el servidor extrae el vector y **descarta las imágenes** (RF-07). La cámara del navegador solo funciona en `http://localhost` o con HTTPS.
- **Importante:** los vectores de prueba de `seed_data.py` y los capturados antes de esta versión eran aleatorios; hay que **volver a registrar el rostro** de cada persona para que la puerta la reconozca.

### Puerta (Raspberry Pi)
- `rpi_main.py` ahora corre 3 tareas: reconocimiento continuo con la cámara (Picamera2 o USB), latido/sincronización y **consulta de órdenes remotas cada 3 s**.
- **Apertura remota:** el botón de llave del Dashboard encola una orden; la Pi la ejecuta y la confirma; el Dashboard muestra si la puerta realmente abrió (o si no respondió en 30 s).
- **Limpieza (RF-04):** cada reconocimiento del personal de limpieza alterna *entrada/salida* en la bitácora (con cola offline si no hay red).
- Pi Zero W: espere ~1–2 s por reconocimiento; use buena iluminación frontal.
