/**
 * NeoAccess - Módulo de Métricas y Visualización (Sección 5, 9, RF-19)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\metrics.js
 */

let chartLabInstance = null;
let chartDayInstance = null;

async function loadMetricsData() {
  const labId = document.getElementById("filter-metrics-lab")?.value || "todos";
  const carrera = document.getElementById("filter-metrics-career")?.value || "todas";
  const period = document.getElementById("filter-metrics-period")?.value || "7";

  let fechaInicio = "";
  if (period !== "all") {
    const days = parseInt(period);
    const d = new Date();
    d.setDate(d.getDate() - days);
    fechaInicio = d.toISOString().split("T")[0];
  }

  try {
    const params = new URLSearchParams();
    if (labId !== "todos") params.append("laboratorio_id", labId);
    if (carrera !== "todas") params.append("carrera", carrera);
    if (fechaInicio) params.append("fecha_inicio", fechaInicio);

    const summary = await apiFetch(`/api/metrics/summary?${params.toString()}`);
    document.getElementById("kpi-total-accesos").textContent = summary.total_accesos;
    document.getElementById("kpi-usuarios-unicos").textContent = summary.usuarios_distintos;
    document.getElementById("kpi-tasa-exito").textContent = `${summary.tasa_efectividad_porcentaje}%`;
    document.getElementById("kpi-permitidos").textContent = summary.accesos_permitidos;
    document.getElementById("kpi-denegados").textContent = summary.accesos_denegados;
    document.getElementById("kpi-dispositivos-activos").textContent = summary.dispositivos.en_linea;

    const labStats = await apiFetch(`/api/metrics/by-lab?${params.toString()}`);
    renderLabChart(labStats);

    const daysParam = period === "all" ? 30 : parseInt(period);
    const dayStats = await apiFetch(`/api/metrics/by-day?laboratorio_id=${labId}&carrera=${carrera}&dias=${daysParam}`);
    renderDayChart(dayStats);

    const recent = await apiFetch("/api/metrics/recent-accesses?limit=8");
    renderRecentAccesses(recent);

  } catch (err) {
    console.error("Error al cargar métricas:", err);
  }
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

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-400">Sin registros de acceso disponibles</td></tr>`;
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
    const recent = await apiFetch("/api/metrics/recent-accesses?limit=10");
    const topId = recent[0]?.id ?? recent[0]?.fecha_hora;
    const isNew = _lastTopAccessId !== null && topId !== _lastTopAccessId;
    renderRecentAccesses(recent);

    if (isNew) {
      const summary = await apiFetch("/api/metrics/summary");
      if (summary) {
        const elTotal = document.getElementById("kpi-total-accesos");
        const elUnicos = document.getElementById("kpi-usuarios-unicos");
        const elTasa = document.getElementById("kpi-tasa-exito");
        const elPerm = document.getElementById("kpi-permitidos");
        const elDen = document.getElementById("kpi-denegados");
        if (elTotal) elTotal.textContent = summary.total_accesos;
        if (elUnicos) elUnicos.textContent = summary.usuarios_distintos;
        if (elTasa) elTasa.textContent = `${summary.tasa_efectividad_porcentaje}%`;
        if (elPerm) elPerm.textContent = summary.accesos_permitidos;
        if (elDen) elDen.textContent = summary.accesos_denegados;
      }
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
