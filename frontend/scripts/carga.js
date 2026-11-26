/*
 * NeoAccess - Carga académica (SEIT) y alumnos de cada clase.
 *  - Alumno: pega su «Carga Académica» y queda inscrito en las clases de laboratorio que lleva.
 *  - Docente: ve los alumnos de cada clase y agrega/quita a quien la lleve desde otro grupo.
 */

// ── Alumno ──
function pintarResultadoCarga(res) {
  const caja = document.getElementById("carga-resultado");
  if (!caja) return;
  const fila = (s, color) => `
    <li class="flex flex-wrap items-baseline gap-x-2 py-1">
      <span class="font-mono text-[10px] px-1.5 rounded bg-${color}-50 text-${color}-700 border border-${color}-200">${esc(s.codigo)}</span>
      <span class="font-semibold text-slate-800">${esc(s.materia_neoaccess || s.materia)}</span>
      <span class="text-slate-500">${esc(s.dia || "")} ${esc(s.inicio)}–${esc(s.fin)} · ${esc(s.salon || s.laboratorio_id || "")} · ${esc(s.docente)}</span>
    </li>`;
  const bloque = (titulo, lista, color, ayuda) => !lista.length ? "" : `
    <div class="mt-3">
      <p class="text-[11px] font-bold uppercase text-${color}-700">${titulo} (${lista.length})</p>
      ${ayuda ? `<p class="text-[11px] text-slate-500">${ayuda}</p>` : ""}
      <ul class="text-xs divide-y divide-slate-100">${lista.map(s => fila(s, color)).join("")}</ul>
    </div>`;
  caja.innerHTML = `
    <p class="text-xs font-semibold text-slate-800">${esc(res.mensaje)}</p>
    ${bloque("Clases en laboratorio ligadas a tu cuenta", res.ligadas, "emerald", "La puerta te dejará entrar en estas clases y aparecerás en el pase de lista.")}
    ${bloque("En laboratorio, pero sin horario igual en NeoAccess", res.sin_clase, "amber", "Avísale a tu docente o al jefe de carrera: el horario registrado no coincide con el del SEIT.")}
    ${bloque("En salón normal (no tienen puerta de NeoAccess)", res.en_salon, "slate", "")}`;
}

async function subirMiCarga() {
  const texto = document.getElementById("carga-texto").value;
  const btn = document.getElementById("btn-carga");
  if (texto.trim().length < 20) {
    showAlert("Pega primero el texto de tu carga académica del SEIT.", { type: "error" });
    return;
  }
  btn.disabled = true;
  try {
    const res = await apiFetch("/api/portal/student/carga", { method: "POST", body: { texto } });
    pintarResultadoCarga(res);
    if (typeof loadStudentPortalView === "function") loadStudentPortalView();
  } catch (err) {
    showAlert(err.message, { type: "error" });
  } finally {
    btn.disabled = false;
  }
}

// ── Docente ──
let CLASE_ALUMNOS_ID = null;

function pintarMisClases(clases) {
  const cont = document.getElementById("mis-clases-alumnos");
  if (!cont) return;
  if (!clases.length) {
    cont.innerHTML = `<p class="p-6 text-center text-xs text-slate-400">No tienes clases asignadas en este periodo.</p>`;
    return;
  }
  cont.innerHTML = clases.map(c => `
    <div class="p-3 sm:px-4 flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <p class="text-sm font-semibold text-slate-900 truncate">${esc(c.materia)}</p>
        <p class="text-[11px] text-slate-500">
          ${esc(c.dia_semana)} <span class="font-mono">${esc(c.hora_inicio.slice(0, 5))}–${esc(c.hora_fin.slice(0, 5))}</span>
          · Grupo <strong>${esc(c.grupo_clave || c.grupo_id || "—")}</strong> · ${esc(c.laboratorio_nombre)}
        </p>
      </div>
      <button type="button" onclick="abrirAlumnosDeClase(${Number(c.id)})"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 font-semibold shrink-0">
        <i data-lucide="users" class="w-3.5 h-3.5"></i> ${Number(c.alumnos || 0)} alumno(s)
      </button>
    </div>`).join("");
  if (window.lucide) lucide.createIcons();
}

async function abrirAlumnosDeClase(horarioId) {
  CLASE_ALUMNOS_ID = horarioId;
  document.getElementById("clase-alumnos-matricula").value = "";
  await recargarAlumnosDeClase();
  openModal("modal-clase-alumnos");
}

async function recargarAlumnosDeClase() {
  const lista = document.getElementById("clase-alumnos-lista");
  try {
    const d = await apiFetch(`/api/portal/teacher/classes/${CLASE_ALUMNOS_ID}/students`);
    const c = d.clase;
    document.getElementById("clase-alumnos-titulo").textContent =
      `${c.materia} · ${c.dia_semana} ${c.hora_inicio.slice(0, 5)}–${c.hora_fin.slice(0, 5)} · Grupo ${c.grupo_id || "—"}`;
    lista.innerHTML = !d.alumnos.length
      ? `<p class="p-4 text-center text-xs text-slate-400">Aún no hay alumnos en esta clase.</p>`
      : d.alumnos.map(a => `
        <div class="py-2 flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="text-xs font-semibold text-slate-900 truncate">${esc(a.nombre_completo)}</p>
            <p class="text-[11px] text-slate-500"><span class="font-mono">${esc(a.matricula_clave)}</span>
              · ${a.como === "grupo" ? "por su grupo" : `de ${esc(a.grupo_id || "sin grupo")} · ${a.origen === "carga" ? "por su carga del SEIT" : "agregado por ti"}`}</p>
          </div>
          ${a.como === "grupo" ? "" : `<button type="button" onclick="quitarAlumnoDeClase(${escJsArg(a.id)})"
            class="px-2 py-1 text-[11px] rounded-lg border border-red-200 text-red-700 hover:bg-red-50 font-semibold shrink-0">Quitar</button>`}
        </div>`).join("");
  } catch (err) {
    lista.innerHTML = `<p class="p-4 text-center text-xs text-red-600">${esc(err.message)}</p>`;
  }
}

async function agregarAlumnoAClase(e) {
  e.preventDefault();
  const campo = document.getElementById("clase-alumnos-matricula");
  try {
    const r = await apiFetch(`/api/portal/teacher/classes/${CLASE_ALUMNOS_ID}/students`,
      { method: "POST", body: { matricula: campo.value } });
    showAlert(r.message, { type: "success" });
    campo.value = "";
    await recargarAlumnosDeClase();
    loadTeacherPortalView();
  } catch (err) {
    showAlert(err.message, { type: "error" });
  }
}

async function quitarAlumnoDeClase(usuarioId) {
  try {
    await apiFetch(`/api/portal/teacher/classes/${CLASE_ALUMNOS_ID}/students/${encodeURIComponent(usuarioId)}`, { method: "DELETE" });
    await recargarAlumnosDeClase();
    loadTeacherPortalView();
  } catch (err) {
    showAlert(err.message, { type: "error" });
  }
}
