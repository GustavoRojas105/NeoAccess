/**
 * NeoAccess - Módulo de Métricas y Visualización (Sección 5, 9, RF-19)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\metrics.js
 */

let chartLabInstance = null;
let chartDayInstance = null;

// Puerta elegida ("todas" = vista general) y cuántas filas del historial se muestran
let METRICAS_PUERTA = "todas";
let METRICAS_PUERTAS = [];
const HISTORIAL_PASO = 15;
let METRICAS_LIMITE = HISTORIAL_PASO;

function filtrosMetricas() {
  const labId = document.getElementById("filter-metrics-lab")?.value || "todos";
  const carrera = document.getElementById("filter-metrics-career")?.value || "todas";
  const period = document.getElementById("filter-metrics-period")?.value || "7";
  let fechaInicio = "";
  if (period !== "all") {
    const d = new Date();
    d.setDate(d.getDate() - parseInt(period));
    fechaInicio = d.toISOString().split("T")[0];
  }
  const params = new URLSearchParams();
  if (labId !== "todos") params.append("laboratorio_id", labId);
  if (carrera !== "todas") params.append("carrera", carrera);
  if (fechaInicio) params.append("fecha_inicio", fechaInicio);
  if (METRICAS_PUERTA !== "todas") params.append("dispositivo_id", METRICAS_PUERTA);
  return { labId, carrera, period, fechaInicio, params };
}

function pintarKpis(summary) {
  document.getElementById("kpi-total-accesos").textContent = summary.total_accesos;
  document.getElementById("kpi-usuarios-unicos").textContent = summary.usuarios_distintos;
  document.getElementById("kpi-tasa-exito").textContent = `${summary.tasa_efectividad_porcentaje}%`;
  document.getElementById("kpi-permitidos").textContent = summary.accesos_permitidos;
  document.getElementById("kpi-denegados").textContent = summary.accesos_denegados;
  document.getElementById("kpi-dispositivos-activos").textContent = summary.dispositivos.en_linea;
}

function urlHistorial() {
  const q = new URLSearchParams({ limit: String(METRICAS_LIMITE) });
  if (METRICAS_PUERTA !== "todas") q.append("dispositivo_id", METRICAS_PUERTA);
  const res = document.getElementById("filter-metrics-result")?.value;
  if (res) q.append("resultado", res);
  return `/api/metrics/recent-accesses?${q.toString()}`;
}

async function loadMetricsData() {
  const { labId, carrera, period, fechaInicio, params } = filtrosMetricas();
  try {
    pintarKpis(await apiFetch(`/api/metrics/summary?${params.toString()}`));

    const porPuerta = new URLSearchParams();
    if (carrera !== "todas") porPuerta.append("carrera", carrera);
    if (fechaInicio) porPuerta.append("fecha_inicio", fechaInicio);
    METRICAS_PUERTAS = await apiFetch(`/api/metrics/by-door?${porPuerta.toString()}`);
    if (METRICAS_PUERTA !== "todas" && !METRICAS_PUERTAS.some(p => p.id === METRICAS_PUERTA)) METRICAS_PUERTA = "todas";
    pintarPuertasMetricas();

    renderLabChart(await apiFetch(`/api/metrics/by-lab?${params.toString()}`));

    const dia = new URLSearchParams({ laboratorio_id: labId, carrera, dias: String(period === "all" ? 30 : parseInt(period)) });
    if (METRICAS_PUERTA !== "todas") dia.append("dispositivo_id", METRICAS_PUERTA);
    renderDayChart(await apiFetch(`/api/metrics/by-day?${dia.toString()}`));

    renderRecentAccesses(await apiFetch(urlHistorial()));
  } catch (err) {
    console.error("Error al cargar métricas:", err);
  }
}

const ESTADO_PUERTA = {
  en_linea: ["bg-emerald-500", "En línea"],
  intermitente: ["bg-amber-500", "Intermitente"],
  fuera_de_linea: ["bg-red-500", "Fuera de línea"],
  desactivado: ["bg-slate-400", "Desactivada"],
};

function pintarPuertasMetricas() {
  // Selector de puerta en los filtros
  const sel = document.getElementById("filter-metrics-door");
  if (sel) {
    sel.innerHTML = `<option value="todas">Todas las puertas (general)</option>` +
      METRICAS_PUERTAS.map(p => `<option value="${esc(p.id)}">${esc(p.nombre)} · ${esc(p.laboratorio_nombre || p.laboratorio_id || "")}</option>`).join("");
    sel.value = METRICAS_PUERTA;
  }

  const general = METRICAS_PUERTA === "todas";
  const btn = document.getElementById("btn-metricas-general");
  if (btn) btn.className = "px-3 py-1.5 text-xs font-semibold rounded-lg border transition " +
    (general ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-700 border-slate-300 hover:bg-slate-50");

  const actual = METRICAS_PUERTAS.find(p => p.id === METRICAS_PUERTA);
  document.getElementById("metrics-door-banner")?.classList.toggle("hidden", general);
  const nombre = document.getElementById("metrics-door-banner-name");
  if (nombre) nombre.textContent = actual ? `${actual.nombre} (${actual.laboratorio_nombre || actual.laboratorio_id})` : "—";
  const titulo = document.getElementById("metrics-history-title");
  if (titulo) titulo.textContent = actual ? `Historial de accesos · ${actual.nombre}` : "Historial de accesos · todas las puertas";

  const grid = document.getElementById("grid-puertas-metricas");
  if (!grid) return;
  if (!METRICAS_PUERTAS.length) {
    grid.innerHTML = `<p class="text-xs text-slate-400">No hay puertas dadas de alta. Agrégalas en Dispositivos y Puertas.</p>`;
    return;
  }
  grid.innerHTML = METRICAS_PUERTAS.map(p => {
    const [punto, estado] = ESTADO_PUERTA[p.estado] || ESTADO_PUERTA.fuera_de_linea;
    const activa = p.id === METRICAS_PUERTA;
    const u = p.ultimo_acceso;
    const ultimo = u
      ? `<span class="${u.resultado === "permitido" ? "text-emerald-600" : "text-red-600"} font-semibold">${u.resultado === "permitido" ? "✓" : "✗"}</span> ${esc(u.usuario_nombre || "No identificado")} · <span class="font-mono">${esc(u.fecha_hora)}</span>`
      : "Sin accesos registrados";
    return `
      <div class="rounded-xl border p-4 transition ${activa ? "border-slate-900 ring-2 ring-slate-900/10 bg-slate-50" : "border-slate-200 hover:border-slate-400"}">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="font-semibold text-sm text-slate-900 truncate" title="${esc(p.nombre)}">${esc(p.nombre)}</p>
            <p class="text-[11px] text-slate-500 truncate">${esc(p.laboratorio_nombre || p.laboratorio_id || "Sin laboratorio")} · <span class="font-mono">${esc(p.id)}</span></p>
          </div>
          <span class="shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold text-slate-600">
            <span class="w-2 h-2 rounded-full ${punto}"></span>${estado}
          </span>
        </div>
        <div class="grid grid-cols-4 gap-2 mt-3 text-center">
          <div class="bg-white rounded-lg border border-slate-200 py-1.5"><p class="text-base font-bold text-slate-900">${p.total}</p><p class="text-[9px] uppercase text-slate-400">Accesos</p></div>
          <div class="bg-white rounded-lg border border-slate-200 py-1.5"><p class="text-base font-bold text-emerald-600">${p.permitidos}</p><p class="text-[9px] uppercase text-slate-400">Permitidos</p></div>
          <div class="bg-white rounded-lg border border-slate-200 py-1.5"><p class="text-base font-bold text-red-600">${p.denegados}</p><p class="text-[9px] uppercase text-slate-400">Denegados</p></div>
          <div class="bg-white rounded-lg border border-slate-200 py-1.5"><p class="text-base font-bold text-slate-900">${p.hoy}</p><p class="text-[9px] uppercase text-slate-400">Hoy</p></div>
        </div>
        <p class="text-[11px] text-slate-500 mt-3 truncate">Último: ${ultimo}</p>
        <button type="button" onclick="verPuertaMetricas(${escJsArg(p.id)})"
          class="mt-3 w-full py-1.5 text-xs font-semibold rounded-lg border transition ${activa ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-800 border-slate-300 hover:bg-slate-100"}">
          ${activa ? "Viendo su historial" : "Ver historial de esta puerta"}
        </button>
      </div>`;
  }).join("");
  if (window.lucide) lucide.createIcons();
}

function verPuertaMetricas(id) {
  METRICAS_PUERTA = id || "todas";
  METRICAS_LIMITE = HISTORIAL_PASO;
  _lastTopAccessId = null;
  pintarPuertasMetricas();
  loadMetricsData();
  if (METRICAS_PUERTA !== "todas") document.getElementById("metrics-door-banner")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function reiniciarHistorialMetricas() {
  METRICAS_LIMITE = HISTORIAL_PASO;
  _lastTopAccessId = null;
  refreshRecentAccesses();
}

function cargarMasHistorialMetricas() {
  METRICAS_LIMITE += HISTORIAL_PASO * 2;
  refreshRecentAccesses();
}

function renderLabChart(data) {
  const ctx = document.getElementById("chart-by-lab")?.getContext("2d");
  if (!ctx) return;

  if (chartLabInstance) {
    chartLabInstance.destroy();
  }

  const labels = data.map(d => d.lab_nombre.replace("Laboratorio", "Lab"));
  const values = data.map(d => d.total_accesos);

  chartLabInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Total de Accesos",
        data: values,
        backgroundColor: "#334155",
        borderRadius: 6,
        hoverBackgroundColor: "#1e293b"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0f172a",
          padding: 10
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "#f1f5f9" },
          ticks: { precision: 0, font: { size: 11 } }
        },
        x: {
          grid: { display: false },
          ticks: {
            font: { size: 10 },
            callback: function(val, index) {
              const text = this.getLabelForValue(val);
              return text.length > 18 ? text.substr(0, 15) + "..." : text;
            }
          }
        }
      }
    }
  });
}

function renderDayChart(data) {
  const ctx = document.getElementById("chart-by-day")?.getContext("2d");
  if (!ctx) return;

  if (chartDayInstance) {
    chartDayInstance.destroy();
  }

  const labels = data.map(d => d.dia);
  const permitidos = data.map(d => d.permitidos);
  const denegados = data.map(d => d.denegados);

  chartDayInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Permitidos (En horario)",
          data: permitidos,
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.08)",
          fill: true,
          tension: 0.35,
          pointRadius: 4
        },
        {
          label: "Denegados (Fuera de regla)",
          data: denegados,
          borderColor: "#ef4444",
          backgroundColor: "transparent",
          borderDash: [5, 5],
          tension: 0.35,
          pointRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { boxWidth: 12, font: { size: 11 } }
        },
        tooltip: { backgroundColor: "#0f172a", padding: 10 }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "#f1f5f9" },
          ticks: { precision: 0, font: { size: 11 } }
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 } }
        }
      }
    }
  });
}

// ID del último acceso conocido para detectar filas nuevas
let _lastTopAccessId = null;

function renderRecentAccesses(items) {
  const tbody = document.getElementById("table-recent-accesses");
  if (!tbody) return;

  const contador = document.getElementById("metrics-history-count");
  const masBtn = document.getElementById("btn-metrics-more");
  const hayMas = !!items && items.length >= METRICAS_LIMITE;
  if (contador) contador.textContent = items && items.length ? `Mostrando ${items.length} registro${items.length === 1 ? "" : "s"}${hayMas ? "" : " (todos)"}` : "";
  if (masBtn) masBtn.classList.toggle("hidden", !hayMas);

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-400">Sin registros de acceso ${METRICAS_PUERTA !== "todas" ? "en esta puerta" : "disponibles"}</td></tr>`;
    _lastTopAccessId = null;
    return;
  }

  // Detectar si el primer elemento (más reciente) cambió → es un registro nuevo
  const topId = items[0]?.id ?? items[0]?.fecha_hora;
  const hayFilaNueva = _lastTopAccessId !== null && topId !== _lastTopAccessId;
  _lastTopAccessId = topId;

  tbody.innerHTML = items.map((item, idx) => {
    const isSuccess = item.resultado === "permitido";
    const badgeClass = isSuccess ? "badge-status-online" : "badge-status-offline";
    const badgeText  = isSuccess ? "✓ Permitido" : "✗ Denegado";

    // Resaltar en amarillo tenue la primera fila si es nueva
    const highlightClass = (idx === 0 && hayFilaNueva) ? "bg-amber-50 animate-pulse-once" : "";

    return `
      <tr class="hover:bg-slate-50 transition ${highlightClass}" style="transition:background .6s;">
        <td class="px-4 py-2.5 font-mono text-[11px] text-slate-600 whitespace-nowrap">${esc(item.fecha_hora)}</td>
        <td class="px-4 py-2.5 font-medium text-slate-900">
          ${item.usuario_nombre ? esc(item.usuario_nombre) : '<em class="text-slate-400 font-normal">No Identificado</em>'}
          ${item.matricula_clave ? `<span class="block text-[10px] text-slate-400">${esc(item.matricula_clave)}</span>` : ''}
        </td>
        <td class="px-4 py-2.5 text-slate-700">
          ${esc(item.laboratorio_nombre || '—')}
          <span class="block text-[10px] text-slate-400">${esc(item.edificio || '')}</span>
        </td>
        <td class="px-4 py-2.5 text-slate-500 font-mono text-[11px]">${esc(item.dispositivo_nombre || item.dispositivo_id || '—')}</td>
        <td class="px-4 py-2.5">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${badgeClass}">
            ${badgeText}
          </span>
          ${item.sincronizado_offline ? '<span class="ml-1 text-[9px] bg-slate-100 text-slate-500 px-1 py-0.5 rounded">offline</span>' : ''}
        </td>
        <td class="px-4 py-2.5 text-slate-500 text-[11px]">${esc(item.motivo || '—')}</td>
      </tr>
    `;
  }).join("");
}

/**
 * Refresco LIGERO: actualiza la tabla de accesos recientes (cada 1 seg).
 * Si detecta una acción nueva, actualiza los contadores KPI al instante sin parpadeos.
 */
async function refreshRecentAccesses() {
  try {
    const recent = await apiFetch(urlHistorial());
    const topId = recent[0]?.id ?? recent[0]?.fecha_hora;
    const isNew = _lastTopAccessId !== null && topId !== _lastTopAccessId;
    renderRecentAccesses(recent);

    if (isNew) {
      // KPIs con los MISMOS filtros (puerta, laboratorio, carrera, periodo) que la vista actual
      pintarKpis(await apiFetch(`/api/metrics/summary?${filtrosMetricas().params.toString()}`));
    }
  } catch (err) {
    // Silencioso: no interrumpe la navegación
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-apply-metrics-filter")?.addEventListener("click", () => {
    loadMetricsData();
  });
});
