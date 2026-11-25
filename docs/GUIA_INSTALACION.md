# Guía de Instalación y Uso de NeoAccess

NeoAccess es la plataforma IoT desarrollada para el control de acceso con reconocimiento facial en los laboratorios del **Edificio 6** y los laboratorios **STEM** del Instituto Tecnológico Superior del Occidente del Estado de Hidalgo (ITSOEH).

---

## 1. Requisitos Previos

- Computadora personal o servidor local (Raspberry Pi 5B o PC con Windows / Linux).
- Python 3.10 o superior (detectado Python 3.14).
- Conexión a red local Wi-Fi / Ethernet institucional (RF-22).
- Raspberry Pi Zero W con cámara y relevador para cada laboratorio.

---

## 2. Puesta en Marcha Rápida en Windows (1 Clic)

Todo el proyecto ya está guardado en tu Escritorio dentro de la carpeta `NeoAccess`:

### Paso 1: Iniciar el Servidor Central
1. Entra a la carpeta `NeoAccess` en tu Escritorio.
2. Haz doble clic en el archivo **`run_server.bat`**.
3. El script automáticamente:
   - Instalará o verificará las dependencias necesarias de Python.
   - Creará e inicializará la base de datos SQLite con los laboratorios del ITSOEH, horarios, usuarios y dispositivos.
   - Iniciará el servidor web en el puerto `8000`.
   - Abrirá automáticamente tu navegador en `http://localhost:8000`.

### Paso 2: Credenciales de Inicio de Sesión (RF-18)
- **Usuario:** `admin`
- **Contraseña:** `admin123`

---

## 3. Pruebas sin Hardware Físico (Simulador de puerta)

Para probar accesos, horarios y el modo sin internet antes de conectar la Raspberry Pi física:

1. Deja corriendo el servidor (`run_server.bat`).
2. Haz doble clic en **`run_simulator.bat`**. Se abre una página que se ve como la puerta.
3. Elige el laboratorio y quién llega ("Pasar frente a la cámara"). Puedes usar la hora real o simular un día y hora.
   La puerta decide con la misma lógica de la Raspberry y todo aparece en la plataforma:
   - la puerta `SIM-<LAB>` sale **en línea** en Dispositivos;
   - los accesos permitidos/denegados y la bitácora de limpieza;
   - "Desconectar Wi-Fi" guarda los accesos en cola y "Reconectar" los envía (RF-08, RF-09);
   - la apertura remota (🔑) desde el panel abre la puerta del simulador.

Todo lo simulado queda ligado a las puertas `SIM-*`. Para borrarlo:
```
python toolsorrar_simulacion.py        (muestra qué se borraría)
python toolsorrar_simulacion.py --si   (lo borra, con respaldo previo)
```

---

## 4. Estructura de Secciones de la Plataforma Web (Sección 9)

1. **Métricas:** Panel con tarjetas KPI, gráficos de barras de afluencia por laboratorio, gráficos de líneas por día y tabla de últimos intentos con filtros por salón, carrera y fecha.
2. **Dispositivos:** Tarjetas por puerta con indicador de estado (Verde = En línea, Amarillo = Intermitente, Rojo = Fuera de línea) y botones para ver detalle, probar apertura remota o desactivar.
3. **Horarios y Grupos:** Administración de horarios de clase que determinan los permisos automáticos de apertura para cada grupo y docente.
4. **Alumnos:** Directorio de alumnos con buscador, estatus de registro facial y modal para ver su historial completo de accesos.
5. **Maestros y Personal:** Control de docentes (asistencia a clases impartidas) y personal de limpieza (registro de horas de entrada y salida).
6. **Reportes:** Generación visual y descarga en formato CSV de evidencias de acceso para auditorías.
