# NeoAccess • Plataforma IoT de Control de Acceso

**Sistema de control de acceso con reconocimiento facial y registro digital para los laboratorios del Edificio 6 y los laboratorios STEM del ITSOEH**

- **Autor:** Gustavo Antonio Rojas Morales
- **Programa:** Maestría en Ingeniería Mecatrónica
- **Institución:** Instituto Tecnológico Superior del Occidente del Estado de Hidalgo (ITSOEH)
- **Fecha:** Diciembre de 2026

---

## 📁 Estructura del Proyecto

```
NeoAccess/
├── backend/                       # Servidor central y API REST / IoT (FastAPI)
│   ├── app.py                     # Endpoints del Dashboard, IoT, registro facial y comandos remotos
│   ├── auth.py                    # PBKDF2-SHA256 (600k iteraciones), sesiones y límite de intentos
│   ├── mailer.py                  # Envío de correos de verificación (SMTP); prueba: python backend\mailer.py
│   └── models.py                  # Modelos Pydantic de validación
│
├── database/                      # Base de datos SQLite
│   ├── database.py                # Esquema (13 tablas) y conexión
│   ├── seed_data.py               # Datos de prueba del ITSOEH (crea neoaccess.db)
│   ├── update_passwords.py        # Asigna contraseñas de prueba por rol
│   └── neoaccess.db               # (se genera solo; no está en Git)
│
├── frontend/                      # Dashboard web (SPA)
│   ├── html/                      # index.html (Dashboard) y login.html
│   ├── styles/style.css
│   └── scripts/                   # app.js, laboratories.js, devices.js, metrics.js,
│                                  # schedules.js, users.js (captura facial), reports.js
│
├── raspberry_pi/                  # Paquete para la Raspberry Pi Zero W de cada puerta
│   ├── rpi_main.py                # Nodo de puerta: cámara + reconocimiento + relé GPIO 17
│   ├── face_engine.py             # Motor facial YuNet + SFace (compartido con el servidor)
│   ├── descargar_modelos.py       # Descarga los modelos ONNX a models/
│   ├── simulator.py               # Simulador interactivo de la puerta en PC
│   ├── test_conexion.py           # Diagnóstico de red, token y relevador
│   ├── setup_rpi.sh               # Instalador automático en Raspberry Pi OS
│   ├── config.json.template       # Plantilla de configuración (copiar a config.json)
│   ├── requirements.txt
│   ├── LEEME_RASPBERRY.md         # Guía de conexión de la Raspberry Pi
│   └── models/                    # (se descargan solos; no están en Git)
│
├── tools/                         # Registro masivo de rostros desde fotos + CSV
│   ├── entrenar_pkl_lote.py
│   ├── plantilla_alumnos.ejemplo.csv   # Copiar a plantilla_alumnos.csv
│   ├── fotos_credenciales/        # Fotos de entrada (no se suben a Git)
│   └── README_PKL.md
│
├── docs/                          # ARQUITECTURA.md, GUIA_INSTALACION.md, CONECTAR_RPI_ZERO.md
├── requirements.txt               # Dependencias del servidor
├── run_server.bat                 # Instala dependencias, prepara la BD y abre el Dashboard
└── run_simulator.bat              # Abre el simulador de puerta
```

---

## ⬇️ Clonar e Instalar desde GitHub

**Requisitos:** Windows 10/11 con [Python 3.10+](https://www.python.org/downloads/) y [Git](https://git-scm.com/).

```powershell
git clone https://github.com/GustavoRojas105/NeoAccess.git
cd NeoAccess
.\run_server.bat
```

La primera vez, `run_server.bat` hace todo automáticamente:

1. Instala las dependencias de `requirements.txt` (FastAPI, Uvicorn, OpenCV, NumPy…).
2. Descarga los modelos de reconocimiento facial (~37 MB) en `raspberry_pi/models/`.
3. Crea la base de datos `database/neoaccess.db` con datos de prueba.
4. Abre el Dashboard en `http://localhost:8000/login`.

> **No se incluyen en el repositorio** (por privacidad y seguridad): la base de datos, los vectores faciales (`*.pkl`, `cache_offline.json`), el `config.json` con el token de cada puerta, los modelos ONNX ni las listas o fotos reales de alumnos. Todo se genera localmente.

Instalación manual (equivalente):

```powershell
python -m pip install -r requirements.txt
python raspberry_pi\descargar_modelos.py
python database\seed_data.py
python backend\app.py
```

---

## 🚀 Inicio Rápido (Servidor Central)

1. En tu computadora, haz doble clic en **`run_server.bat`**.
2. Abrirá automáticamente el Dashboard en tu navegador: `http://localhost:8000/login`.
3. Inicia sesión como administrador (`admin` / `admin123`). Las cuentas de prueba de cada rol están en `ACCESOS_PRUEBA.txt`, un archivo local que no se sube a Git; la página de login ya no las muestra.
4. **Cambia estas contraseñas** antes de usar datos reales.

---

## ✉️ Registro de Cuentas con Correo Institucional

Alumnos y docentes crean su cuenta en la pestaña **Crear cuenta** del login:

- Solo se aceptan correos **`@itsoeh.edu.mx`**.
- Se envía un enlace de verificación (válido 24 h). La cuenta no existe hasta que se abre el enlace.
- **Alumnos:** pueden entrar en cuanto verifican el correo.
- **Docentes:** después de verificar, el administrador aprueba la cuenta en **Maestros y Personal → Aprobar**.
- Si el administrador ya había dado de alta la matrícula (sin contraseña), el registro se vincula a ese mismo alumno en lugar de duplicarlo.
- Se aceptan como máximo 5 solicitudes por hora desde la misma IP.

**Configurar el envío de correos:**

1. Copia `config_servidor.env.ejemplo` como **`config_servidor.env`**. Es un archivo local y no se sube a Git.
2. Rellena la cuenta que enviará los correos y su **contraseña de aplicación**:
   - **Google Workspace:** `smtp.gmail.com`. La cuenta necesita verificación en 2 pasos; la contraseña se crea en *Cuenta de Google → Seguridad → Contraseñas de aplicaciones*.
   - **Microsoft 365:** `smtp.office365.com`. El administrador de TI debe tener habilitado *SMTP AUTH* para esa cuenta.
3. En `NEOACCESS_PUBLIC_URL` pon la IP fija de la PC servidor. Es la dirección que aparecerá en el enlace del correo.
4. Prueba el envío:
   ```powershell
   python backend\mailer.py tu.correo@itsoeh.edu.mx
   ```
5. Reinicia `run_server.bat`. Al arrancar indica si está usando `config_servidor.env`.

- **Sin SMTP configurado (modo pruebas)**, el enlace se imprime en la consola del servidor en lugar de enviarse.

---

## 🔧 Modo Mantenimiento

Desde el Dashboard → menú lateral → **Modo mantenimiento** (el indicador muestra ON/OFF):

- Solo los **administradores** pueden iniciar sesión y usar el Dashboard.
- Alumnos, docentes y personal de limpieza ven el aviso con tu mensaje: en el login y, si ya tenían sesión abierta, en una pantalla de mantenimiento. Sus sesiones solo quedan en pausa y vuelven a funcionar al desactivarlo.
- El registro de cuentas nuevas se pausa.
- Las **puertas siguen funcionando**: reconocimiento, sincronización y apertura remota.
- Mientras está activo, el Dashboard muestra una barra naranja con un botón para desactivarlo.

---

## 🏫 Cómo Agregar un Nuevo Laboratorio Real

1. En el Dashboard, dirígete a la sección **"Laboratorios y Salones"** en el menú izquierdo.
2. Haz clic en el botón superior **"+ Agregar Laboratorio"**.
3. Ingresa los datos:
   - **Clave / ID:** Ejemplo: `LAB-STEM-04` o `LAB-ED6-03`.
   - **Nombre:** Ejemplo: `Laboratorio de Visión Artificial y Robótica`.
   - **Edificio:** Selecciona `Laboratorios STEM`, `Edificio 6`, etc.
   - **Carrera:** Ejemplo: `Ingeniería en Electromecánica`.
   - **Capacidad:** Ejemplo: `30` alumnos.
4. Haz clic en **Guardar Laboratorio**. El laboratorio quedará registrado de forma permanente en la base de datos y disponible al instante en filtros, horarios y puertas.

---

## 🔌 Cómo Poner a Funcionar tu Raspberry Pi Zero W Real

1. En el Dashboard, sección **Dispositivos**, da de alta la puerta y descarga su **`config.json`** (ya trae el token y la IP de tu PC).
2. Copia la carpeta **`raspberry_pi/`** a la Raspberry Pi y coloca ahí el `config.json` descargado.
3. Ejecuta el instalador (instala OpenCV, la cámara y los modelos, y crea el servicio de arranque automático):
   ```bash
   cd raspberry_pi
   bash setup_rpi.sh
   ```
4. Conecta el relevador de la cerradura al **GPIO 17**, el LED verde al **GPIO 27**, el rojo al **GPIO 22** y el buzzer al **GPIO 23**. Detalles en [`raspberry_pi/LEEME_RASPBERRY.md`](raspberry_pi/LEEME_RASPBERRY.md) y [`docs/CONECTAR_RPI_ZERO.md`](docs/CONECTAR_RPI_ZERO.md).
5. Comprueba la conexión (escucharás el "clic" del relevador):
   ```bash
   python3 test_conexion.py
   ```
6. Inicia el servicio:
   ```bash
   sudo systemctl start neoaccess-door
   ```

---

## 🔐 Seguridad

- **Contraseñas:** PBKDF2-HMAC-SHA256 con 600 000 iteraciones. Los hashes antiguos (SHA-256 simple) se migran automáticamente la próxima vez que cada usuario inicia sesión.
- **Fuerza bruta:** después de 5 intentos fallidos con el mismo usuario (o 20 desde la misma IP) en 15 minutos, el login se bloquea 15 minutos (HTTP 429).
- **Dispositivos IoT:** cada Raspberry Pi solo puede reportar eventos con su propio `dispositivo_id`; el token viaja en el header `X-Device-Token`.
- **Portales por rol:** cada portal (alumno, docente, limpieza) solo responde a su rol; la API de administración exige rol de administrador.
- **CORS:** deshabilitado por defecto (el Dashboard se sirve desde el mismo servidor). Para permitir otro origen: `set NEOACCESS_CORS_ORIGINS=http://host:puerto`.
- **Modo desarrollo:** la recarga automática del servidor solo se activa con `set NEOACCESS_DEV=1`.
- **Tokens de ejemplo:** los dispositivos de `seed_data.py` usan tokens públicos de demostración; para puertas reales, dalas de alta desde el Dashboard (genera tokens aleatorios).

---

## 🧠 Reconocimiento Facial Real (YuNet + SFace)

El servidor y las puertas usan **el mismo motor** ([`raspberry_pi/face_engine.py`](raspberry_pi/face_engine.py)) basado en modelos ONNX de OpenCV, así los vectores registrados y los capturados en la puerta son comparables:

- **YuNet** detecta el rostro; **SFace** genera el vector de 128 dimensiones; se comparan por **similitud coseno** (umbral `umbral_similitud_coseno`, 0.363 por defecto; súbelo, p. ej. a 0.45, si hay falsos positivos).
- **Modelos:** `python raspberry_pi/descargar_modelos.py` (≈37 MB, una sola vez en la PC y en cada Pi). `run_server.bat` y `setup_rpi.sh` lo hacen automáticamente.
- **Registro (Dashboard → Usuarios → cámara):** el navegador toma 3 fotogramas, el servidor extrae el vector y **descarta las imágenes** (RF-07). La cámara en vivo del navegador solo funciona en `http://localhost` o con HTTPS.
- **Registro desde el celular:** abre `http://IP-DE-TU-PC:8000` en el teléfono (misma red Wi-Fi), entra como administrador → **Alumnos** → **Registrar rostro** → **Tomar foto con el celular** (1 a 3 fotos). Usa la cámara nativa del teléfono, así que funciona aunque la conexión sea `http`. Las fotos se reducen a 1280 px en el teléfono, solo viven en memoria y el servidor las descarta tras extraer el vector. Al dar de alta un alumno, el Dashboard ofrece registrar su rostro de inmediato.
- **Importante:** los vectores de prueba de `seed_data.py` son aleatorios; hay que **registrar el rostro** de cada persona para que la puerta la reconozca.

### Puerta (Raspberry Pi)
- `rpi_main.py` corre 3 tareas: reconocimiento continuo con la cámara (Picamera2 o USB), latido/sincronización y **consulta de órdenes remotas cada 3 s**.
- **Apertura remota:** el botón de llave del Dashboard encola una orden; la Pi la ejecuta y la confirma; el Dashboard muestra si la puerta realmente abrió (o si no respondió en 30 s).
- **Limpieza (RF-04):** cada reconocimiento del personal de limpieza alterna *entrada/salida* en la bitácora (con cola offline si no hay red).
- **Modo offline (RF-08/09):** sin red, la puerta sigue decidiendo con su caché local y sincroniza los registros al reconectarse.
- Pi Zero W: espere ~1–2 s por reconocimiento; use buena iluminación frontal.
