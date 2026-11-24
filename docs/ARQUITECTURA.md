# Arquitectura del Sistema NeoAccess

Este documento describe la arquitectura de software, base de datos y protocolos de comunicación de la plataforma IoT NeoAccess para el ITSOEH.

---

## 1. Arquitectura General y Topología de Red (RF-22)

```
[ Red Local Wi-Fi / LAN Escolar - Edificio 6 y Laboratorios STEM ]
                        │
       ┌────────────────┴────────────────┐
       ▼                                 ▼
┌────────────────────────┐      ┌────────────────────────┐
│  Raspberry Pi Zero W   │      │  Raspberry Pi Zero W   │
│  (Lab Robótica STEM)   │      │  (Lab IoT Embebidos)   │
│  • Cámara + Encodings  │      │  • Cámara + Encodings  │
│  • Caché Offline JSON  │      │  • Caché Offline JSON  │
│  • Relevador Cerradura │      │  • Relevador Cerradura │
└───────────┬────────────┘      └───────────┬────────────┘
            │                               │
            └───────────────┬───────────────┘
                            ▼
               ┌───────────────────────────┐
               │    Servidor Central       │
               │   (PC / RPi 5B ITSOEH)    │
               │  • FastAPI Backend        │
               │  • Base de Datos SQLite   │
               │  • Dashboard Web (Admin)  │
               └───────────────────────────┘
```

---

## 2. Estructura de Datos (Sección 8 del Documento de Requerimientos)

El sistema implementa 10 tablas relacionales optimizadas en SQLite:

1. **`laboratorios`**: Salones registrados en Edificio 6 y Laboratorios STEM.
2. **`dispositivos`**: Nodos Raspberry Pi Zero W asociados a cada puerta, con clave API, intervalo de latido y estado en tiempo real.
3. **`usuarios`**: Alumnos, docentes, personal de limpieza y administradores.
4. **`metadatos_faciales`**: Vectores numéricos de 128 flotantes (embeddings matemáticos). **Cumple con RF-07: ¡Cero almacenamiento de imágenes en disco ni base de datos!**
5. **`grupos`**: Carreras, semestres y nombres de grupo (ej. MEC-801, SIS-701).
6. **`horarios`**: Asignaciones semanales por grupo, materia, docente, laboratorio, día y rango horario.
7. **`registros_acceso`**: Bitácora de cada intento de acceso (permitido o denegado), motivo, fecha/hora y si fue sincronizado fuera de línea.
8. **`registros_limpieza`**: Bitácora específica para personal de limpieza con hora de entrada y hora de salida (RF-04).
9. **`eventos_dispositivo`**: Registro de conexiones, desconexiones, intermitencias y sincronizaciones (RF-21).
10. **`administradores`**: Cuentas con hash PBKDF2-HMAC-SHA256 (600 000 iteraciones, sal aleatoria; los hashes antiguos se migran solos al iniciar sesión) para acceso exclusivo a la plataforma web (RF-18).

---

## 3. Filosofía de Privacidad de Datos (RF-07)

El documento técnico establece una estricta política de protección de datos:
- Cuando la persona se posiciona frente a la cámara de la Raspberry Pi Zero W, el fotograma se procesa temporalmente en la memoria RAM volátil.
- Se extrae un vector numérico de 128 dimensiones (representación biométrica espacial).
- El fotograma de imagen se destruye inmediatamente de la memoria RAM con `del frame` o garbage collection.
- En la base de datos únicamente se almacena el vector numérico JSON en la tabla `metadatos_faciales`. Ninguna fotografía es guardada en disco ni enviada por red.

---

## 4. Tolerancia a Fallos y Operación Fuera de Línea (RF-08, RF-09)

1. **Descarga Anticipada:** La Raspberry Pi Zero W descarga cada día un caché completo de los horarios y vectores faciales de los usuarios autorizados.
2. **Autonomía Local:** Si la red Wi-Fi escolar se interrumpe, el cliente sigue validando los rostros y los horarios contra su archivo local `cache_offline.json`. La cerradura abre normalmente para las personas autorizadas.
3. **Cola de Encolamiento:** Los accesos permitidos o denegados ocurridos durante la desconexión se guardan en `cola_offline.json`.
4. **Reconexión Automática:** Cuando se detecta de nuevo conectividad con el servidor central, se despachan los registros en lote mediante el endpoint `/api/iot/access-attempts-batch` y se purga la cola local sin duplicar registros.
