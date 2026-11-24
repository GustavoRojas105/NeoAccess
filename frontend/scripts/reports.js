/**
 * NeoAccess - Módulo de Reportes (RF-20)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\reports.js
 * Permite filtrar por salón o todos, periodo, resultado, generar reporte y descargar CSV
 */

function loadReportsDropdowns() {
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
  const labId = document.getElementById("report-filter-lab")?.value || "todos";
  const start = document.getElementById("report-filter-start")?.value || "";
  const end = document.getElementById("report-filter-end")?.value || "";
  const result = document.getElementById("report-filter-result")?.value || "todos";

  const params = new URLSearchParams();
  if (labId !== "todos") params.append("laboratorio_id", labId);
  if (start) params.append("fecha_inicio", start);
  if (end) params.append("fecha_fin", end);
  if (result !== "todos") params.append("resultado", result);

  try {
    const data = await apiFetch(`/api/reports/data?${params.toString()}`);
    renderReportResults(data);
  } catch (err) {
    alert("Error al generar reporte: " + err.message);
  }
}

function renderReportResults(rows) {
  const tbody = document.getElementById("table-report-results");
  const countEl = document.getElementById("report-results-count");
  if (!tbody) return;

  countEl.textContent = `${rows.length} registros encontrados en el periodo`;

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="p-6 text-center text-slate-400">No se encontraron accesos con los criterios indicados</td></tr>`;
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
      </tr>
    `;
  }).join("");
}

function downloadReportCSV() {
  const labId = document.getElementById("report-filter-lab")?.value || "todos";
  const start = document.getElementById("report-filter-start")?.value || "";
  const end = document.getElementById("report-filter-end")?.value || "";
  const result = document.getElementById("report-filter-result")?.value || "todos";

  const params = new URLSearchParams();
  if (labId !== "todos") params.append("laboratorio_id", labId);
  if (start) params.append("fecha_inicio", start);
  if (end) params.append("fecha_fin", end);
  if (result !== "todos") params.append("resultado", result);

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
  .catch(err => alert("Error al descargar archivo CSV: " + err.message));
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-generate-report")?.addEventListener("click", () => {
    generateReport();
  });

  document.getElementById("btn-export-csv")?.addEventListener("click", () => {
    downloadReportCSV();
  });
});
