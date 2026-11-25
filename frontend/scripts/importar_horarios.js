// ─────────────────────────────────────────────────────────────
// Importación masiva de horarios: plantilla de Excel → revisión → guardar
// ─────────────────────────────────────────────────────────────

let importArchivo = null;

async function downloadScheduleTemplate() {
  try {
    const res = await fetch("/api/schedules/template", { headers: { Authorization: `Bearer ${STATE.token}` } });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "plantilla_horarios_neoaccess.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    showAlert("No se pudo descargar la plantilla: " + err.message, { type: "error" });
  }
}

function importShowStep(paso) {
  document.getElementById("import-step-file").classList.toggle("hidden", paso !== "file");
  document.getElementById("import-step-review").classList.toggle("hidden", paso !== "review");
}

function importReset() {
  importArchivo = null;
  const input = document.getElementById("import-schedules-file");
  if (input) input.value = "";
  document.getElementById("import-schedules-filename").textContent = "Toque para elegir el archivo (.xlsx o .csv)";
  document.getElementById("btn-import-review").disabled = true;
  importShowStep("file");
}

async function importSend(confirmar) {
  const fd = new FormData();
  fd.append("archivo", importArchivo);
  return apiFetch(`/api/schedules/import?confirmar=${confirmar}`, { method: "POST", body: fd });
}

function renderImportReview(res) {
  const chip = (texto, clases) => `<span class="px-2.5 py-1 rounded-full font-semibold ${clases}">${texto}</span>`;
  document.getElementById("import-summary").innerHTML =
    chip(`${res.total} fila(s) en el archivo`, "bg-slate-100 text-slate-700") +
    chip(`✓ ${res.validas} lista(s) para guardar`, "bg-emerald-50 text-emerald-700 border border-emerald-200") +
    (res.con_error ? chip(`✗ ${res.con_error} con error (no se guardarán)`, "bg-red-50 text-red-700 border border-red-200") : "");

  document.getElementById("import-rows").innerHTML = res.filas.map(f => {
    const h = f.horario, d = f.datos;
    const okFila = !!h;
    return `
      <tr class="${okFila ? "" : "bg-red-50/60"} align-top">
        <td class="px-3 py-2 font-mono text-slate-500">${esc(f.fila)}</td>
        <td class="px-3 py-2 whitespace-nowrap">${okFila ? `${esc(h.dia_semana)}<br>${esc(h.hora_inicio)}–${esc(h.hora_fin)}` : `${esc(d.dia)}<br>${esc(d.hora_inicio)}–${esc(d.hora_fin)}`}</td>
        <td class="px-3 py-2">${esc(okFila ? h.laboratorio_nombre : d.laboratorio)}</td>
        <td class="px-3 py-2">${esc(okFila ? (h.grupo_id || "Libre") : d.grupo)}</td>
        <td class="px-3 py-2">${esc(okFila ? h.docente_nombre : d.docente)}</td>
        <td class="px-3 py-2">${esc(okFila ? h.materia : d.materia)}</td>
        <td class="px-3 py-2 ${okFila ? "text-emerald-700 font-semibold" : "text-red-700"}">
          ${okFila ? "✓ Lista" : f.errores.map(e => `• ${esc(e)}`).join("<br>")}
        </td>
      </tr>`;
  }).join("");

  // Celular: una tarjeta por fila, con el motivo del error visible
  document.getElementById("import-cards").innerHTML = res.filas.map(f => {
    const h = f.horario, d = f.datos;
    const v = (campoH, campoD) => esc(h ? (h[campoH] ?? (campoH === "grupo_id" ? "Libre" : "")) : d[campoD]);
    return `
      <div class="p-3 rounded-lg border ${h ? "border-emerald-200 bg-white" : "border-red-200 bg-red-50/60"}">
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-slate-900">${v("dia_semana", "dia")} ${v("hora_inicio", "hora_inicio")}–${v("hora_fin", "hora_fin")}</span>
          <span class="text-[10px] font-mono text-slate-400">Fila ${esc(f.fila)}</span>
        </div>
        <p class="text-slate-700 mt-1">${v("materia", "materia")}</p>
        <p class="text-[11px] text-slate-500">${v("laboratorio_nombre", "laboratorio")} • ${v("grupo_id", "grupo")} • ${v("docente_nombre", "docente")}</p>
        <p class="mt-1 text-[11px] ${h ? "text-emerald-700 font-semibold" : "text-red-700"}">
          ${h ? "✓ Lista para guardar" : f.errores.map(e => `• ${esc(e)}`).join("<br>")}
        </p>
      </div>`;
  }).join("");

  const btn = document.getElementById("btn-import-confirm");
  btn.disabled = res.validas === 0;
  btn.textContent = res.validas ? `Guardar ${res.validas} horario(s) válido(s)` : "No hay horarios válidos";
  importShowStep("review");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-download-schedule-template")?.addEventListener("click", downloadScheduleTemplate);

  document.getElementById("btn-modal-import-schedules")?.addEventListener("click", () => {
    importReset();
    openModal("modal-import-schedules");
  });

  document.getElementById("import-schedules-file")?.addEventListener("change", (e) => {
    importArchivo = e.target.files[0] || null;
    document.getElementById("import-schedules-filename").textContent =
      importArchivo ? importArchivo.name : "Toque para elegir el archivo (.xlsx o .csv)";
    document.getElementById("btn-import-review").disabled = !importArchivo;
  });

  document.getElementById("btn-import-review")?.addEventListener("click", async (e) => {
    if (!importArchivo) return;
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Revisando...";
    try {
      renderImportReview(await importSend(false));
    } catch (err) {
      showAlert("No se pudo leer el archivo: " + err.message, { type: "error" });
    } finally {
      btn.disabled = !importArchivo;
      btn.textContent = "Revisar archivo";
    }
  });

  document.getElementById("btn-import-back")?.addEventListener("click", importReset);

  document.getElementById("btn-import-confirm")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const res = await importSend(true);
      closeModal("modal-import-schedules");
      loadSchedulesData();
      const omitidas = res.total - res.guardados;
      showAlert(`Se guardaron ${res.guardados} horario(s).` +
        (omitidas ? `\n\n${omitidas} fila(s) con error no se guardaron; corríjalas en el archivo y vuelva a importarlo (las ya guardadas no se duplican).` : ""),
        { type: "success", title: "Importación terminada" });
    } catch (err) {
      btn.disabled = false;
      showAlert("No se pudo guardar: " + err.message, { type: "error" });
    }
  });
});
