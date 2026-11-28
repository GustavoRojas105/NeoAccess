# NeoAccess - imagen del servidor central (para el servidor Linux con Docker).
# La base de datos y la configuración (correo, dominio) NO van dentro de la imagen:
#   - base:   volumen en /datos  (NEOACCESS_DB_PATH=/datos/neoaccess.db)
#   - config: --env-file /opt/neoaccess/neoaccess.env
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEOACCESS_DB_PATH=/datos/neoaccess.db \
    TZ=America/Mexico_City

# Zona horaria real: los horarios de acceso se deciden con la hora de México
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY database/database.py database/
COPY frontend frontend
# Programa de la Raspberry: el panel lo empaqueta en el zip de cada puerta
COPY raspberry_pi/rpi_main.py raspberry_pi/face_engine.py raspberry_pi/descargar_modelos.py \
     raspberry_pi/test_conexion.py raspberry_pi/setup_rpi.sh raspberry_pi/requirements.txt \
     raspberry_pi/LEEME_RASPBERRY.md raspberry_pi/
COPY tools/crear_admin.py tools/asignar_contrasena.py tools/
# Modelos de reconocimiento facial (registro desde el panel)
RUN python raspberry_pi/descargar_modelos.py

RUN useradd --system --uid 10001 neoaccess && mkdir -p /datos && chown neoaccess /datos
USER neoaccess
VOLUME /datos
EXPOSE 8000

# Un solo proceso: las sesiones viven en memoria. Las cabeceras X-Forwarded-* vienen de nginx
# (el puerto solo se publica en 127.0.0.1, así que nadie de fuera las puede falsificar).
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
