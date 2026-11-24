# Guía de Conectividad: Cómo Conectar tu Raspberry Pi Zero W al Dashboard NeoAccess

Esta guía detalla paso a paso cómo conectar e integrar tu **Raspberry Pi Zero W** con cerradura electromagnética al servidor central de **NeoAccess** para los laboratorios del ITSOEH.

---

## 1. Diagrama de Conexión de Hardware (Pines GPIO)

La Raspberry Pi Zero W controla la cerradura mediante un módulo de relevador (Relay) de 5V y dispone de indicadores visuales y auditivos (opcionales):

| Componente | Pin Raspberry Pi (BCM) | Pin Físico | Función |
| :--- | :--- | :--- | :--- |
| **Módulo Relevador (Cerradura)** | **GPIO 17** | Pin 11 | Señal de activación de la cerradura electromagnética |
| **LED Indicador Verde** | **GPIO 27** | Pin 13 | Acceso autorizado / Puerta abierta |
| **LED Indicador Rojo** | **GPIO 22** | Pin 15 | Acceso denegado / Intento no válido |
| **Zumbador (Buzzer)** | **GPIO 23** | Pin 16 | Alerta sonora de acceso |
| **Alimentación VCC Relevador** | **5V Power** | Pin 2 o 4 | Alimentación de 5V |
| **Tierra (GND)** | **Ground** | Pin 6 o 9 | Tierra común del circuito |

> **Nota eléctrica:** La cerradura electromagnética usualmente requiere una fuente externa de 12V DC. El relevador actúa como interruptor entre la fuente de 12V y la cerradura.

---

## 2. Obtener la Dirección IP del Servidor Central en la Red de la Escuela

Para que la Raspberry Pi Zero W se comunique con la computadora o servidor central (RF-22):

1. En tu computadora con Windows, abre una terminal (PowerShell o CMD).
2. Ejecuta el comando:
   ```powershell
   ipconfig
   ```
3. Busca tu adaptador Wi-Fi y anota tu dirección IPv4 (por ejemplo: `192.168.1.150` o `10.0.0.5`).
4. Tu servidor NeoAccess correrá en: `http://<TU_IP_LOCAL>:8000`.

---

## 3. Dar de Alta la Raspberry Pi en el Dashboard Web

1. Inicia el servidor ejecutando el archivo `run_server.bat` en tu Escritorio.
2. Ingresa a `http://localhost:8000` con el usuario `admin` y contraseña `admin123`.
3. Ve a la sección **Dispositivos y Puertas** en el menú izquierdo.
4. Haz clic en el botón superior **"+ Agregar Dispositivo (Puerta)"**.
5. Completa los datos:
   - **ID Dispositivo:** Por ejemplo, `DEV-PI-STEM04` o `DEV-PI-ED603`.
   - **Nombre:** Por ejemplo, `RPi Zero W - Puerta Lab Robótica`.
   - **Laboratorio:** Selecciona el salón al que pertenecerá esta puerta.
   - **Intervalo de Latido:** 300 segundos (5 minutos) o 600 segundos (10 minutos) (RF-10).
6. Haz clic en **Guardar Dispositivo**. El sistema generará automáticamente un **Token de Seguridad (API Key)** exclusivo para ese dispositivo.

---

## 4. Descargar y Pasar la Configuración a la Raspberry Pi

1. En la tarjeta de la puerta recién creada, haz clic en **"Ver Detalle"**.
2. Aparecerá la ventana modal con la opción de **"Descargar config.json para Raspberry Pi"**.
3. Descarga ese archivo. Su contenido tendrá esta estructura:
   ```json
   {
     "dispositivo_id": "DEV-PI-STEM04",
     "nombre": "RPi Zero W - Puerta Lab Robótica",
     "token_api": "neo_pi_xxxxxxxxxxxxxxxx",
     "servidor_url": "http://192.168.1.150:8000",
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
   *(Asegúrate de que `servidor_url` tenga la IP real de tu máquina local).*

---

## 5. Puesta en Marcha en la Raspberry Pi Zero W

1. Copia la carpeta `edge_device/` a tu Raspberry Pi Zero W (puedes usar una memoria USB o SCP/FileZilla).
2. Dentro de la Raspberry Pi, coloca el archivo `config.json` en dicha carpeta.
3. Abre una terminal en la Raspberry Pi y ejecuta el script de instalación:
   ```bash
   cd edge_device
   chmod +x setup_rpi.sh
   ./setup_rpi.sh
   ```
4. Para ejecutar el cliente manualmente y ver el proceso en tiempo real:
   ```bash
   python3 rpi_client.py
   ```
5. Si deseas que inicie automáticamente cada vez que se encienda la Raspberry Pi:
   ```bash
   sudo systemctl start neoaccess-door
   sudo systemctl status neoaccess-door
   ```

---

## 6. Verificación en el Dashboard

Una vez encendida la Raspberry Pi Zero W:
- La tarjeta de la puerta en el Dashboard cambiará inmediatamente su estado a **Verde ("En línea")**.
- El contador superior mostrará la puerta activa.
- Podrás presionar el botón de la **Llave ("Probar apertura remota")** para comprobar el accionamiento del relevador.
- La Raspberry Pi descargará automáticamente la lista de usuarios y horarios autorizados para los próximos días, garantizando que **seguirá abriendo la puerta incluso si se cae el Wi-Fi de la escuela (RF-08 y RF-09)**.
