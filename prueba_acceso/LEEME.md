# Prueba de Acceso (simulador independiente)

Programa aparte para **simular accesos a los laboratorios y ver métricas**. No forma parte del Dashboard.

## Abrir

Doble clic en **`prueba_acceso.bat`**, o:

```powershell
python prueba_acceso\prueba_acceso.py
```

## Qué hace

- **Simular un acceso:** eliges el usuario frente a la puerta (o "Persona desconocida") y el laboratorio. Después eliges cómo se decide el resultado:
  - **Automático:** usa las reglas del sistema.
    - Sin rostro registrado → denegado.
    - Dado de baja → denegado.
    - Persona desconocida → denegada.
    - Con rostro: se genera una similitud y se compara con el umbral 0.363 de las puertas.
  - **Forzar ACEPTADO** o **Forzar DENEGADO**.
  - **Motivo opcional:** puedes escribir el motivo que quieres que quede registrado.
- **Simulación masiva:** genera N accesos con el **% de aceptados** que elijas, repartidos en los últimos 7 días, de 7:00 a 21:00.
- **Métricas:**
  - Totales, aceptados, denegados, efectividad y similitud promedio.
  - Gráficas por laboratorio y por hora del día.
  - Últimos intentos, motivos de rechazo y usuarios con más intentos.
- **Exportar CSV** y **Borrar pruebas**.

## Datos

- Lee los usuarios y laboratorios de `database/neoaccess.db` en **solo lectura**. Si esa base no existe, usa datos de demostración.
- Las simulaciones se guardan en **`prueba_acceso/prueba_acceso.db`**. No se mezclan con los accesos reales ni con las métricas del Dashboard, y no se suben a Git.
