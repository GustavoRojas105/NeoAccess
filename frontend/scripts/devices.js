/**
 * NeoAccess - Módulo de Dispositivos y Puertas (RF-10 al RF-13)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\devices.js
 * Muestra tarjetas por puerta con los estados verde (en línea), amarillo (intermitente) y rojo (fuera de línea).
 */

async function loadDevicesData() {
  try {
    const devices = await apiFetch("/api/devices");
    STATE.dispositivos = devices;
    renderDeviceCards(devices);
    updateGlobalDeviceStatus();
  } catch (err) {
    console.error("Error al cargar dispositivos:", err);
  }
}

function renderDeviceCards(devices) {
  const grid = document.getElementById("devices-grid");
  if (!grid) return;

  if (devices.length === 0) {
    grid.innerHTML = `<div class="col-span-full p-8 text-center text-slate-400 bg-white rounded-xl border">No hay dispositivos registrados</div>`;
    return;
  }

  grid.innerHTML = devices.map(dev => {
    let statusClass = "badge-status-offline";
    let dotClass = "offline";
    let statusLabel = "Fuera de línea";

    if (!dev.activo) {
      statusClass = "badge-status-disabled";
      dotClass = "disabled";
      statusLabel = "Desactivado";
    } else if (dev.estado === "en_linea") {
      statusClass = "badge-status-online";
      dotClass = "online";
      statusLabel = "En línea";
    } else if (dev.estado === "intermitente") {
      statusClass = "badge-status-intermittent";
      dotClass = "intermittent";
      statusLabel = "Intermitente";
    }

    const lastSeen = dev.ultima_senal || "Sin señal registrada";

    return `
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col justify-between hover:shadow-md transition">
        <div>
          <!-- Header de tarjeta -->
          <div class="flex items-start justify-between mb-3">
            <div>
              <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${statusClass}">
                <span class="status-dot ${dotClass}"></span>
                ${statusLabel}
              </span>
              <h4 class="text-sm font-bold text-slate-900 mt-2">${esc(dev.nombre)}</h4>
              <p class="text-xs text-slate-500 font-mono">${esc(dev.id)}</p>
            </div>
            <div class="p-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-600">
              <i data-lucide="door-closed" class="w-5 h-5"></i>
            </div>
          </div>

          <!-- Información de Salón y Red -->
          <div class="space-y-2 py-3 border-y border-slate-100 text-xs">
            <div class="flex justify-between">
              <span class="text-slate-400">Laboratorio:</span>
              <span class="font-semibold text-slate-800 text-right">${esc(dev.laboratorio_nombre || 'Sin asignar')}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Edificio:</span>
              <span class="text-slate-700">${esc(dev.laboratorio_edificio || 'ITSOEH')}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">IP Raspberry Pi:</span>
              <span class="font-mono text-slate-700">${esc(dev.ip_address || 'DHCP')}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Latido Configurado:</span>
              <span class="text-slate-700">${esc(dev.intervalo_latido_seg)} seg (${Math.round(dev.intervalo_latido_seg / 60)} min)</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Última Señal:</span>
              <span class="text-slate-700 font-mono text-[11px]">${esc(lastSeen)}</span>
            </div>
          </div>
        </div>

        <!-- Botones de Acción -->
        <div class="pt-4 flex items-center justify-between gap-2">
          <button onclick="showConnectRpiModal(${escJsArg(dev.id)})"
            class="flex-1 py-1.5 px-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold rounded-lg transition flex items-center justify-center gap-1.5 shadow-sm">
            <i data-lucide="cpu" class="w-3.5 h-3.5"></i>
            <span>Ver Detalle / Conectar</span>
          </button>

          <button onclick="testDoorUnlock(${escJsArg(dev.id)})"
            class="py-1.5 px-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs rounded-lg border border-slate-300 transition flex items-center justify-center"
            title="Probar apertura remota">
            <i data-lucide="key" class="w-3.5 h-3.5"></i>
          </button>

          <button onclick="toggleDeviceStatus(${escJsArg(dev.id)})"
            class="py-1.5 px-2.5 ${dev.activo ? 'bg-slate-100 hover:bg-red-50 text-slate-600 hover:text-red-700' : 'bg-slate-100 hover:bg-emerald-50 text-slate-600 hover:text-emerald-700'} text-xs rounded-lg border border-slate-300 transition flex items-center justify-center"
            title="${dev.activo ? 'Desactivar dispositivo' : 'Activar dispositivo'}">
            <i data-lucide="${dev.activo ? 'power-off' : 'power'}" class="w-3.5 h-3.5"></i>
          </button>

          <button onclick="deleteDevicePermanent(${escJsArg(dev.id)}, ${escJsArg(dev.nombre)})"
            class="py-1.5 px-2.5 bg-slate-100 hover:bg-red-50 text-slate-600 hover:text-red-700 text-xs rounded-lg border border-slate-300 transition flex items-center justify-center"
            title="Eliminar definitivamente">
            <i data-lucide="trash-2" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </div>
    `;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

function showConnectRpiModal(deviceId) {
  const dev = STATE.dispositivos.find(d => d.id === deviceId);
  if (!dev) return;

  document.getElementById("modal-rpi-dev-name").textContent = `${dev.nombre} • ${dev.laboratorio_nombre || ''}`;
  document.getElementById("modal-rpi-id").textContent = dev.id;
  document.getElementById("modal-rpi-token").textContent = dev.token_api;

  RPI_MODAL_ID = dev.id;
  document.getElementById("modal-rpi-cmd").textContent =
    `unzip neoaccess_${dev.id}.zip
bash neoaccess/setup_rpi.sh`;
  openModal("modal-connect-rpi");
}

let RPI_MODAL_ID = null;

async function descargarArchivoRpi(ruta, nombre, queEs) {
  if (!RPI_MODAL_ID) return;
  try {
    const res = await fetch(`/api/devices/${encodeURIComponent(RPI_MODAL_ID)}/${ruta}`,
      { headers: { Authorization: `Bearer ${STATE.token}` } });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    showAlert(`No se pudo descargar ${queEs}: ` + err.message, { type: "error" });
  }
}

function descargarConfigRpi() {
  return descargarArchivoRpi("config-file", "config.json", "el config.json");
}

function descargarPaqueteRpi() {
  return descargarArchivoRpi("rpi-package", `neoaccess_${RPI_MODAL_ID}.zip`, "el paquete");
}

async function regenerarTokenRpi() {
  if (!RPI_MODAL_ID) return;
  const ok = await showConfirm(
    "Se generará un Token API nuevo y el actual dejará de funcionar. La Raspberry Pi no podrá conectarse hasta que copies el nuevo config.json. ¿Continuar?",
    { title: "Regenerar token", confirmText: "Regenerar" });
  if (!ok) return;
  try {
    const res = await apiFetch(`/api/devices/${encodeURIComponent(RPI_MODAL_ID)}/regenerate-token`, { method: "POST" });
    document.getElementById("modal-rpi-token").textContent = res.token_api;
    const dev = STATE.dispositivos.find(d => d.id === RPI_MODAL_ID);
    if (dev) dev.token_api = res.token_api;
    showAlert(res.message);
  } catch (err) {
    showAlert("No se pudo regenerar el token: " + err.message);
  }
}

async function toggleDeviceStatus(deviceId) {
  try {
    const res = await apiFetch(`/api/devices/${deviceId}/toggle`, { method: "POST" });
    loadDevicesData();
  } catch (err) {
    showAlert("Error al cambiar estado del dispositivo: " + err.message);
  }
}

async function testDoorUnlock(deviceId) {
  if (!(await showConfirm("¿Abrir esta puerta de forma remota?", { title: "Apertura remota", confirmText: "Abrir puerta" }))) return;
  const id = encodeURIComponent(deviceId);
  try {
    const res = await apiFetch(`/api/devices/${id}/manual-unlock`, { method: "POST" });

    // Esperar la confirmación real del dispositivo (máx. ~35 s)
    const limite = Date.now() + 35000;
    let estado = "pendiente";
    while (Date.now() < limite && (estado === "pendiente" || estado === "entregado")) {
      await new Promise(r => setTimeout(r, 1500));
      const cmd = await apiFetch(`/api/devices/${id}/commands/${res.comando_id}`);
      estado = cmd.estado;
    }

    const mensajes = {
      ejecutado: "✓ La puerta confirmó la apertura.",
      fallido: "✗ El dispositivo recibió la orden pero no pudo ejecutarla.",
      expirado: "✗ El dispositivo no respondió a tiempo (¿está encendido y conectado?). La orden se canceló.",
    };
    showAlert(mensajes[estado] || "El dispositivo aún no confirma la apertura.");
    loadDevicesData();
  } catch (err) {
    showAlert("Error al emitir apertura: " + err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-modal-add-device")?.addEventListener("click", () => {
    openModal("modal-add-device");
  });

  document.getElementById("form-add-device")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      id: document.getElementById("dev-new-id").value.trim().toUpperCase(),
      nombre: document.getElementById("dev-new-name").value.trim(),
      laboratorio_id: document.getElementById("dev-new-lab").value,
      ip_address: document.getElementById("dev-new-ip").value.trim(),
      intervalo_latido_seg: parseInt(document.getElementById("dev-new-interval").value) || 300
    };

    try {
      const res = await apiFetch("/api/devices", {
        method: "POST",
        body: payload
      });
      closeModal("modal-add-device");
      document.getElementById("form-add-device").reset();
      await loadDevicesData();
      showConnectRpiModal(res.dispositivo_id);
    } catch (err) {
      showAlert("Error al registrar dispositivo: " + err.message);
    }
  });
});


async function deleteDevicePermanent(deviceId, nombre) {
  if (await eliminarDefinitivo("dispositivo", deviceId, nombre)) loadDevicesData();
}
