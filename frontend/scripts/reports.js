/**
 * NeoAccess - Módulo de Reportes (RF-20)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\reports.js
 * Permite filtrar por salón o todos, periodo, resultado, generar reporte y descargar CSV
 */

async function loadReportPeriodos() {
  const sel = document.getElementById("report-filter-periodo");
  if (!sel) return;
  try {
    const { periodos } = await apiFetch("/api/periodos");
    const actual = sel.value;
    sel.innerHTML = `<option value="todos">Todos los periodos</option>` + periodos.map(p =>
      `<option value="${esc(p.id)}">${esc(p.nombre)}${p.estado === "activo" ? " (activo)" : ""}</option>`).join("");
    if (actual && [...sel.options].some(o => o.value === actual)) sel.value = actual;
  } catch (err) {
    console.error("No se pudieron cargar los periodos:", err);
  }
}

// Desde "Periodos e Histórico": abrir Reportes ya filtrado por un periodo (sin fechas)
async function abrirReportePeriodo(periodoId) {
  switchSection("reports");
  await loadReportPeriodos();
  document.getElementById("report-filter-periodo").value = periodoId;
  document.getElementById("report-filter-start").value = "";
  document.getElementById("report-filter-end").value = "";
  generateReport();
}

function reportParams() {
  const v = id => document.getElementById(id)?.value || "";
  const params = new URLSearchParams();
  if ((v("report-filter-lab") || "todos") !== "todos") params.append("laboratorio_id", v("report-filter-lab"));
  if (v("report-filter-start")) params.append("fecha_inicio", v("report-filter-start"));
  if (v("report-filter-end")) params.append("fecha_fin", v("report-filter-end"));
  if ((v("report-filter-result") || "todos") !== "todos") params.append("resultado", v("report-filter-result"));
  if ((v("report-filter-periodo") || "todos") !== "todos") params.append("periodo_id", v("report-filter-periodo"));
  if (v("report-filter-q").trim()) params.append("q", v("report-filter-q").trim());
  return params;
}

function loadReportsDropdowns() {
  loadReportPeriodos();
  const startInput = document.getElementById("report-filter-start");
  const endInput = document.getElementById("report-filter-end");

  if (!endInput.value) {
    const today = new Date().toISOString().split("T")[0];
    endInput.value = today;
  }
  if (!startInput.value) {
    const d = new Date();
    d.setDate(d.getDate() - 7);
    startInput.value = d.toISOString().split("T")[0];
  }
}

async function generateReport() {
  const params = reportParams();

  try {
    const data = await apiFetch(`/api/reports/data?${params.toString()}`);
    renderReportResults(data);
  } catch (err) {
    showAlert("Error al generar reporte: " + err.message);
  }
}

function renderReportResults(rows) {
  const tbody = document.getElementById("table-report-results");
  const countEl = document.getElementById("report-results-count");
  if (!tbody) return;

  countEl.textContent = `${rows.length} registros encontrados`;

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="p-6 text-center text-slate-400">No se encontraron accesos con los criterios indicados</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const isOk = r.resultado === "permitido";
    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-2.5 font-mono text-[11px] text-slate-600">${esc(r.fecha_hora)}</td>
        <td class="px-4 py-2.5 font-medium text-slate-900">${esc(r.laboratorio)} <span class="text-[10px] text-slate-400">(${esc(r.edificio)})</span></td>
        <td class="px-4 py-2.5 font-semibold text-slate-800">${esc(r.usuario || 'Desconocido')}</td>
        <td class="px-4 py-2.5 uppercase text-[10px] text-slate-500">${esc(r.tipo_usuario || 'N/A')}</td>
        <td class="px-4 py-2.5 font-mono text-[11px]">${esc(r.matricula_clave || 'N/A')}</td>
        <td class="px-4 py-2.5">
          <span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold ${isOk ? 'badge-status-online' : 'badge-status-offline'}">
            ${isOk ? 'Permitido' : 'Denegado'}
          </span>
        </td>
        <td class="px-4 py-2.5 text-slate-600 text-[11px]">${esc(r.motivo)}</td>
        <td class="px-4 py-2.5 text-[10px] text-slate-400 font-mono">${r.sincronizado_offline ? 'Sí (offline)' : 'No'}</td>
        <td class="px-4 py-2.5 text-[10px] text-slate-500 font-mono">${esc(r.periodo_id || '—')}</td>
      </tr>
    `;
  }).join("");
}

function downloadReportCSV() {
  const params = reportParams();

  fetch(`/api/reports/export-csv?${params.toString()}`, {
    headers: { "Authorization": `Bearer ${STATE.token}` }
  })
  .then(res => res.blob())
  .then(blob => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `reporte_neoaccess_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  })
  .catch(err => showAlert("Error al descargar archivo CSV: " + err.message));
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-generate-report")?.addEventListener("click", () => {
    generateReport();
  });

  document.getElementById("btn-export-csv")?.addEventListener("click", () => {
    downloadReportCSV();
  });

  document.getElementById("report-filter-q")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") generateReport();
  });
});
