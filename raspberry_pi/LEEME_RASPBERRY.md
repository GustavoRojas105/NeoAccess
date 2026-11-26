# Guía para la Raspberry Pi Zero W: Código y Conexión Real

Esta guía responde exactamente a tu pregunta: **¿Qué código le tengo que poner a mi Raspberry Pi Zero W y cómo compruebo que la conexión real funcione?**

---

## Forma rápida (recomendada)

1. En el panel: **Dispositivos → Vincular → "Descargar paquete para Raspberry Pi (.zip)"**. El zip ya trae el programa, los modelos y el `config.json` de esa puerta.
2. Copia el zip a la Raspberry (USB, WinSCP o FileZilla) y ejecuta **una sola vez**:
   ```bash
   unzip neoaccess_<ID>.zip
   bash neoaccess/setup_rpi.sh
   ```
3. Listo. La puerta arranca sola cada vez que se enciende la Raspberry y busca el servidor cada 15 segundos hasta encontrarlo; en el panel la tarjeta se pone en verde.

**Si cambias el token o cambia la IP de la PC:** descarga solo el `config.json` y reemplaza `neoaccess/config.json`, o cópialo a la partición *boot* de la tarjeta SD (la que se ve en Windows) con el nombre `neoaccess_config.json`. La Raspberry lo detecta sola, sin reiniciar.

Ver lo que está haciendo la puerta: `journalctl -u neoaccess-door -f`

> Requisito: la Raspberry debe estar conectada al mismo Wi-Fi que la PC (se configura al grabar la SD con Raspberry Pi Imager).

El resto de esta guía explica el detalle (pines, diagnóstico, configuración manual).

---

## 1. ¿Qué archivos van en la Raspberry Pi Zero W?

Para que tu Raspberry Pi Zero W funcione como un nodo de acceso físico real, solo debes copiar la carpeta **`raspberry_pi/`** a tu Raspberry Pi (mediante una memoria USB, o por red con WinSCP o FileZilla).

La carpeta contiene:
- **`rpi_main.py`**: El programa principal que controla la cámara, compara los rostros en memoria RAM (RF-07), valida los horarios de clase en el caché local (RF-08), acciona el relevador de la cerradura electromagnética y envía la señal periódica ("latido") al servidor (RF-10).
- **`test_conexion.py`**: El script de diagnóstico para verificar que tu Raspberry Pi realmente se comunica con tu computadora por Wi-Fi y probar el "clic" físico del relevador.
- **`config.json`**: El archivo donde colocas la IP de tu computadora y el Token generado en el Dashboard.
- **`setup_rpi.sh`**: Script para instalar todo automáticamente con un comando.
- **`requirements.txt`**: Librerías de Python requeridas (`requests`, `RPi.GPIO`, `numpy`).

---

## 2. Diagrama de Conexión de Pines Físicos (GPIO)

Conecta tu módulo de relevador (Relay) de 5V y tus indicadores a los pines de la Raspberry Pi Zero W:

| Componente Físico | Pin BCM Raspberry Pi | Pin Físico Header | Función |
| :--- | :--- | :--- | :--- |
| **Señal Relevador (Cerradura)** | **GPIO 17** | Pin 11 | Abre la cerradura electromagnética |
| **LED Indicador Verde** | **GPIO 27** | Pin 13 | Indica acceso permitido / en horario |
| **LED Indicador Rojo** | **GPIO 22** | Pin 15 | Indica acceso denegado / fuera de horario |
| **Zumbador (Buzzer)** | **GPIO 23** | Pin 16 | Pitido de confirmación sonora |
| **Botón de verificación** | **GPIO 24** | Pin 18 | La otra pata del botón va a **GND (Pin 20)** |
| **VCC Relevador** | **5V Power** | Pin 2 o 4 | Alimentación de 5V |
| **GND Relevador** | **Ground** | Pin 6 o 9 | Tierra común |

> **Cómo funciona el botón:** la persona presiona el botón, el LED verde parpadea y suena un pitido cada segundo durante **5 segundos** (para que se acomode frente a la cámara) y al final se toma la foto y se verifica. Si no se ve un rostro, se enciende el LED rojo y hay que volver a presionar. No hace falta resistencia: se usa la *pull-up* interna de la Raspberry.
> En `config.json`: `"segundos_cuenta_regresiva"` cambia los 5 s, `"pin_boton_gpio"` el pin, y `"modo_captura": "continuo"` vuelve al modo sin botón (la cámara busca rostros todo el tiempo).

> **Nota para la cerradura:** El relevador se conecta como interruptor entre la fuente de 12V de la cerradura y la misma cerradura. La Raspberry Pi no alimenta directamente la cerradura electromagnética de 12V; solo conmuta el relé.

---

## 3. Cómo Agregar tu Raspberry Pi Real al Dashboard (Paso a Paso)

### Paso A: Obtener la IP de tu computadora
1. En tu computadora (donde corre el servidor), abre la terminal (CMD o PowerShell) y escribe:
   ```cmd
   ipconfig
   ```
2. Busca la línea **Dirección IPv4** de tu adaptador Wi-Fi (por ejemplo: `192.168.1.75`).

### Paso B: Registrar el dispositivo en el Dashboard
1. Abre tu navegador en `http://localhost:8000` e inicia sesión (`admin` / `admin123`).
2. Ve a la sección **Dispositivos y Puertas**.
3. Haz clic en **"+ Agregar Dispositivo (Puerta)"**.
4. Escribe el ID (por ejemplo `DEV-PI-STEM01`), selecciona el laboratorio correspondiente y guarda.
5. Haz clic en **"Ver Detalle / Conectar"** en la tarjeta de esa puerta:
   - Verás tu **Token API** único (ejemplo: `neo_pi_robotica_stem_01`).
   - Puedes hacer clic en **"Descargar config.json"**.

### Paso C: Configurar el archivo `config.json` en la Raspberry Pi
En tu Raspberry Pi, abre el archivo `config.json` y asegúrate de que tenga los datos de tu computadora:

```json
{
  "dispositivo_id": "DEV-PI-STEM01",
  "nombre": "RPi Zero W - Puerta Robótica STEM",
  "token_api": "neo_pi_robotica_stem_01",
  "servidor_url": "http://192.168.1.75:8000",
  "intervalo_latido_seg": 300,
  "pin_cerradura_gpio": 17,
  "pin_led_verde_gpio": 27,
  "pin_led_rojo_gpio": 22,
  "pin_buzzer_gpio": 23,
  "segundos_puerta_abierta": 5,
  "umbral_similitud_coseno": 0.363,
  "segundos_espera_mismo_usuario": 10,
  "intervalo_comandos_seg": 3,
  "camara_indice": 0,
  "resolucion_camara": [320, 240],
  "tamano_minimo_rostro_px": 60
}
```
*(Cambia `192.168.1.75` por la IP real de tu máquina obtenida en el Paso A).*

---

## 4. Comprobar la Conexión Real (Script de Diagnóstico)

En la terminal de tu Raspberry Pi Zero W, ejecuta:
```bash
python3 test_conexion.py
```

El script ejecutará 4 pruebas automáticas en tiempo real:
1. **Prueba de Red:** Verifica si la Raspberry Pi puede alcanzar el servidor web en el puerto 8000 y mide la latencia en milisegundos.
2. **Prueba de Autenticación:** Envía la señal de vida ("latido") con tu Token API al servidor. **¡En este momento verás cómo la tarjeta en el Dashboard cambia inmediatamente a color VERDE ("En línea")!**
3. **Prueba de Descarga de Reglas:** Descarga la lista de usuarios autorizados y los horarios de clase en la memoria local (`cache_offline.json`), garantizando que la puerta funcionará incluso si se cae el Wi-Fi escolar (RF-08).
4. **Prueba Física de Hardware:** Activará el relevador en el GPIO 17 durante 3 segundos. **Escucharás el "clic" mecánico del relevador y verás encender el LED verde.**

---

## 5. Poner en Marcha el Sistema en la Puerta

Una vez verificada la conexión con el diagnóstico, puedes iniciar el programa de control de puerta:

```bash
python3 rpi_main.py
```

O si deseas que arranque automáticamente cada vez que se encienda la Raspberry Pi:
```bash
sudo ./setup_rpi.sh
sudo systemctl start neoaccess-door
```

¡Listo! Con esto tienes tu nodo físico de acceso funcionando al 100% con hardware real.
