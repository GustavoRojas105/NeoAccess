# Guía: Cómo Alimentar tu Archivo `.pkl` y Registrar Usuarios por Lotes

Esta guía responde a tus dudas:
1. **¿Cómo alimento mi `.pkl`?**
2. **¿De dónde saco esa parte / las fotos?**
3. **¿Cómo puedo registrar usuarios por bloques o por tandas a ese `.pkl`?**

---

## 1. ¿Qué es el archivo `.pkl` y para qué sirve?

El archivo con extensión `.pkl` es un archivo binario serializado de Python (**Pickle**).
En proyectos de visión artificial y reconocimiento facial (como con la librería `face_recognition` de dlib o OpenCV), el `.pkl` almacena en disco los **vectores espaciales de 128 números flotantes** de cada alumno o docente junto con su nombre y matrícula.

Estructura interna del `.pkl`:
```python
{
    "encodings": [
        [-0.045, 0.123, 0.089, ... 128 flotantes del Alumno 1],
        [-0.012, 0.088, 0.041, ... 128 flotantes del Alumno 2]
    ],
    "matriculas": ["22030015", "22030048"],
    "nombres": ["Carlos Mendoza", "Ana Torres"],
    "grupos": ["MEC-801", "MEC-801"]
}
```

---

## 2. ¿De dónde saco las fotos para alimentar el sistema?

Tienes 3 fuentes principales y muy sencillas en una escuela como el ITSOEH:

1. **Fotos de Credencial Escolar / Servicios Escolares:**
   - Servicios escolares suele tener las fotografías digitales del proceso de inscripción en una carpeta.
   - Solo necesitas que el nombre del archivo sea la matrícula del alumno (ejemplo: `22030015.jpg`).
2. **Cámara Web desde el Dashboard de NeoAccess:**
   - En el Dashboard web, en la sección **Alumnos**, cada fila tiene el botón del rostro.
   - Enciende la cámara web de la computadora, toma la captura y el sistema genera automáticamente el vector de 128 flotantes sin guardar la foto en disco (**RF-07**).
3. **Fotografía tomada con el celular o la Raspberry Pi:**
   - Tomas una foto frontal con buena luz y la guardas con su matrícula.

---

## 3. ¿Cómo registrar usuarios por bloques o tandas en el `.pkl`?

Creamos una herramienta automática lista para usar: [`tools/entrenar_pkl_lote.py`](entrenar_pkl_lote.py).

### Pasos para procesar un grupo o generación completa:

#### Paso 1: Colocar las fotos en la carpeta
Copia las fotos de los alumnos dentro de la carpeta:
📁 `C:\Users\gr321\Desktop\NeoAccess\tools\fotos_credenciales`

*(Ejemplo: `22030015.jpg`, `22030048.jpg`, etc.)*

#### Paso 2: Llenar la plantilla CSV
Abre con Excel o bloc de notas el archivo:
📄 [`tools/plantilla_alumnos.ejemplo.csv`](plantilla_alumnos.ejemplo.csv) (cópiala como `plantilla_alumnos.csv`)

Pega la lista del grupo con estas columnas:
```csv
matricula,nombre_completo,carrera,grupo,archivo_foto
22030015,Carlos Alberto Mendoza Hernandez,Ingenieria Mecatronica,MEC-801,22030015.jpg
22030048,Ana Sofia Torres Morales,Ingenieria Mecatronica,MEC-801,22030048.jpg
22030088,Gustavo Antonio Rojas Morales,Ingenieria Mecatronica,MEC-801,22030088.jpg
```

#### Paso 3: Ejecutar el alimentador automático
Abre una terminal en tu computadora y ejecuta:
```bash
cd C:\Users\gr321\Desktop\NeoAccess\tools
python entrenar_pkl_lote.py
```

### ¿Qué hace este script automáticamente?
1. **Extrae el vector de 128 dimensiones** de cada foto.
2. **Destruye de inmediato la foto de la memoria RAM (RF-07)** para garantizar privacidad y cumplimiento ético.
3. **Genera tu archivo `encodings.pkl`** con todos los alumnos del lote.
4. **Copia el archivo a la Raspberry Pi Zero W** en `raspberry_pi/encodings.pkl`.
5. **Actualiza la base de datos SQLite** (`neoaccess.db`) para que los alumnos aparezcan activos en el Dashboard.
6. **Actualiza la memoria local `cache_offline.json`** de la Raspberry Pi para que la puerta los reconozca al instante aunque se caiga el Wi-Fi escolar (RF-08).
