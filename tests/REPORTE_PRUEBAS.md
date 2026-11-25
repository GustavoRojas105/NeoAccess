# Reporte de Pruebas — NeoAccess

**Fecha:** 24 de noviembre de 2026
**Alcance:** jefes de carrera, periodos escolares (Ene–Jun / Ago–Dic) e histórico, horario semanal en los portales, tolerancia de 10 minutos en la puerta, importación de horarios y permisos por rol.

## Cómo ejecutarlas

```
python tests\ejecutar_pruebas.py
python tests\ejecutar_pruebas.py --cobertura      (requiere: pip install coverage)
```

Cada tipo corre en un proceso aparte con una **base de datos temporal nueva**. La base real `database/neoaccess.db` no se modifica; una prueba lo verifica comparando su huella SHA-256 antes y después.

## Resumen

| Tipo | Archivo | Pruebas | Resultado |
|---|---|---|---|
| Caja blanca | `test_caja_blanca.py` | 40 | ✅ 40 pasan |
| Caja negra (API) | `test_caja_negra.py` | 39 | ✅ 39 pasan |
| Caja gris | `test_caja_gris.py` | 19 | ✅ 19 pasan |
| Caja negra (interfaz) | navegador, manual asistida | 9 escenarios | ✅ todos correctos |
| **Total automatizadas** | | **98** | **✅ 98 pasan** |

Muchas pruebas usan `subTest` con tablas de casos. En total se revisan **más de 200 combinaciones** de entrada.

### Cobertura de código (caja blanca)

| Módulo | Cobertura |
|---|---|
| `backend/horarios_import.py` | 98 % |
| `backend/auth.py` | 97 % |
| `database/database.py` | 96 % |
| `backend/models.py` | 100 % |
| Funciones de `backend/app.py` que tocó este cambio | **93.6 %** |
| `backend/app.py` completo | 62 % |

El 62 % de `app.py` completo se debe a módulos que estas pruebas no abarcan: reconocimiento facial, registro por correo, comandos a la Raspberry y métricas.

## Técnicas aplicadas

### Caja blanca: se conoce el código
Se recorren las ramas de cada función interna:
- **`_hora`**: 25 casos, uno por rama:
  - `datetime` y `time` de Excel, y fracción de día;
  - números fuera de rango y texto con am/pm;
  - punto como separador ("7.30"), y horas y minutos inválidos.
- **`validar_horario`**: el camino correcto y **cada uno de los 16 mensajes de error**. Además:
  - choques de laboratorio, grupo y docente;
  - clases contiguas, que no chocan;
  - búsqueda por nombre sin acentos;
  - filtro por carreras del jefe y grupo de otro periodo.
- **`leer_archivo`**:
  - CSV con `;` y con `,`;
  - codificaciones UTF-8 con BOM y cp1252, y alias de encabezados;
  - Excel dañado, formato no soportado, columnas faltantes y filas vacías.
- **Periodos**:
  - límites de fecha: 1 ene, 30 jun, 1 jul (vacaciones), 1 ago y 31 dic;
  - periodo siguiente, `init_db` idempotente y migración de una BD antigua.
- **Seguridad**:
  - PBKDF2 con sal distinta y verificación de hashes válidos, inválidos y del formato heredado;
  - cuándo se debe volver a calcular el hash;
  - bloqueo tras exactamente 5 intentos fallidos;
  - sesiones y cierre de sesiones por persona.
- **Permisos**: `carreras_de`, `exigir_carrera`, `get_current_staff`, y el caso sin periodo activo.
- **Raspberry (`validate_schedule`)**:
  - límites 06:49 ❌, 06:50 ✅, 09:00 ✅ y 09:01 ❌;
  - tolerancia ausente, inválida o negativa, otro día, limpieza y administrador.
- **Portal (JavaScript, con Node)**: `hpEstadoClase` en sus límites y el texto de "faltan X min".

### Caja negra: solo entradas y salidas de la API
- **Particiones de equivalencia** en el inicio de sesión: los 4 roles, mayúsculas, contraseña incorrecta, usuario inexistente y campos vacíos.
- **Valores límite**:
  - clave de grupo de 1, 2, 20 y 21 caracteres;
  - semestre 0, 1, 12 y 13;
  - horas 05:59, 06:00, 22:00 y 22:01, e inicio igual al fin;
  - contraseña de 7 y de 8 caracteres;
  - archivo de 2 MB + 1 byte y 1001 filas;
  - fechas de reporte en el mismo día.
- **Matriz de permisos**: 15 rutas × 4 roles, más 6 acciones prohibidas al jefe.
- Importación: al revisar no se guarda nada, y al reimportar no se duplica.
- Reportes con caracteres especiales (`%`, `_`, `' OR 1=1 --`): sin inyección SQL.

### Caja gris: API + revisión interna de la base de datos
- Grupos, horarios y accesos guardan su `periodo_id`. Un acceso sin conexión de 2020 queda en el periodo de 2020.
- Al reenviar un lote de la Raspberry no se duplican registros. Un lote con un token ajeno se rechaza completo.
- La contraseña del jefe se guarda cifrada y nunca se envía al navegador.
- Al desactivar a un jefe, sus sesiones desaparecen de la memoria del servidor.
- **Atomicidad del cierre de periodo**: se simula una falla a la mitad y se comprueba que no queda nada a medias.
- **Estado tras cerrar el periodo**:
  - grupos archivados como `CLAVE@periodo`;
  - horarios ligados a su grupo archivado;
  - foto del alumno en `inscripciones` y alumno sin grupo;
  - no se pierde ningún acceso, y `PRAGMA foreign_key_check` queda vacío.
- El histórico es de solo lectura. La Raspberry deja de recibir los horarios viejos, y la clave del grupo puede reutilizarse en otro periodo.

### Caja negra de la interfaz, en el navegador
1. Inicio de sesión desde el formulario: con la contraseña incorrecta aparece el mensaje de error; con la correcta, entra al Dashboard del jefe.
2. El jefe solo ve Horarios, Docentes y Reportes. No ve mantenimiento ni el contador de puertas, y si se fuerza otra sección regresa a Horarios.
3. Formulario de grupo:
   - solo aparecen las carreras del jefe, ya preseleccionadas;
   - las claves "A" e "ISC 601" se rechazan;
   - "isc-601" se crea como ISC-601.
4. Tabla de grupos: el jefe puede editar pero no ve el botón de eliminar. La plantilla de Excel se descarga.
5. Docentes, vista del jefe: no ve la pestaña de limpieza, ni el registro de rostro, ni la eliminación definitiva.
6. Reportes: aparece el filtro de periodo y funciona la búsqueda por nombre.
7. Alta de jefe por el administrador:
   - sin carreras muestra un aviso;
   - si las contraseñas no coinciden muestra un aviso;
   - una contraseña corta la bloquea el navegador;
   - con datos correctos se crea.
8. Portales de alumno y docente: los estados "Terminada", "Acceso permitido ahora" y "Podrás entrar a las HH:MM" aparecen bien, y el cambio de estado es automático.
9. En celular (375 px) **ningún rol** tiene desbordamiento horizontal.

## Defectos encontrados y corregidos

| # | Encontrado por | Defecto | Corrección |
|---|---|---|---|
| 1 | Caja blanca | En la importación, un número de Excel mayor a 1 (p. ej. `1.5`) se leía como **15:00** porque se quitaba el punto. También se rechazaba "7.30", una forma común de escribir la hora. | Los números fuera de 0–1 se rechazan y el punto se toma como separador ("7.30" → 07:30). |
| 2 | Caja negra | Se podía crear un **administrador con el mismo usuario que un jefe de carrera**, lo que confunde el inicio de sesión. | Ahora se rechaza con "ya lo usa un jefe de carrera". |

## Fuera del alcance de estas pruebas
- Cámara y reconocimiento facial real (YuNet + SFace), relevador GPIO y una Raspberry física.
- Envío real de correos de verificación (SMTP).
- Pruebas de carga o estrés.
