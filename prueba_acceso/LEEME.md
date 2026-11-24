# Prueba de Acceso (simulador independiente)

Programa aparte para **simular accesos a los laboratorios con escaneo de rostro y ver métricas**. No forma parte del Dashboard.

## Abrir

Doble clic en **`prueba_acceso.bat`**, o:

```powershell
python prueba_acceso\prueba_acceso.py
```

## Pestaña "Escanear rostro"

1. Elige el **laboratorio**.
2. Elige cómo se decide el **resultado**:
   - **Automático:** decide el reconocimiento facial.
     - Si el rostro coincide con uno registrado (similitud ≥ 0.363, el mismo umbral de las puertas) y el usuario está activo → aceptado.
     - Si no coincide → "Rostro no reconocido".
     - Si el usuario está dado de baja → denegado.
   - **Forzar ACEPTADO** o **Forzar DENEGADO:** se escanea igual y se registra quién era, pero el resultado lo eliges tú.
   - **Motivo opcional:** puedes escribir el motivo que quieres que quede registrado.
3. Pulsa **Escanear rostro** y mira a la cámara.
   - Se usa el mismo motor que las puertas (YuNet + SFace).
   - Cuando tu rostro está estable se toman 3 muestras y se comparan con los rostros registrados en el sistema.
   - Tienes 20 segundos; puedes cancelar.

Para que te reconozca, primero registra tu rostro en el Dashboard: **Alumnos → Registrar rostro**. Los vectores de los datos de prueba son aleatorios y no coinciden con ninguna persona real.

Si no hay cámara o faltan los modelos, aparece la opción **Simular sin cámara**, donde eliges a la persona de una lista.

## Pestaña "Simulación masiva"

- Genera N accesos (sin cámara) con el **% de aceptados** que elijas, repartidos en los últimos 7 días.
- Aquí también están **Exportar CSV** y **Borrar pruebas**.

## Métricas

- Totales, aceptados, denegados, efectividad y similitud promedio.
- Gráficas por laboratorio y por hora del día.
- Últimos intentos, motivos de rechazo y usuarios con más intentos.

## Datos y privacidad

- Usuarios, laboratorios y vectores faciales se leen de `database/neoaccess.db` en **solo lectura**.
- Las simulaciones se guardan en **`prueba_acceso/prueba_acceso.db`**. No se mezclan con los accesos reales ni con las métricas del Dashboard, y no se suben a Git.
- Las imágenes de la cámara **solo viven en memoria** y se descartan después de extraer el vector (RF-07).
