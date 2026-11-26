// ─────────────────────────────────────────────────────────────
// Periodos escolares (Ene–Jun / Ago–Dic), histórico y jefes de carrera
// ─────────────────────────────────────────────────────────────

function fmtFecha(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  const meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return `${Number(d)} ${meses[Number(m) - 1] || m} ${y}`;
}

let PERIODOS_INFO = { periodos: [], siguiente: null };

async function loadPeriodosData() {
  try {
    PERIODOS_INFO = await apiFetch("/api/periodos");
  } catch (err) {
    showAlert("No se pudieron cargar los periodos: " + err.message, { type: "error" });
    return;
  }
  const { periodos, siguiente } = PERIODOS_INFO;
  const activo = periodos.find(p => p.estado === "activo");
  const dato = (titulo, valor, extra = "") => `
    <div class="p-3 rounded-lg bg-slate-50 border border-slate-200 ${extra}">
      <p class="text-[10px] uppercase font-semibold text-slate-400">${titulo}</p>
      <p class="text-sm font-bold text-slate-900 mt-0.5">${valor}</p>
    </div>`;
  document.getElementById("periodo-activo-card").innerHTML = activo ? [
    dato("Periodo", esc(activo.nombre), "col-span-2 md:col-span-1"),
    dato("Fechas", `${fmtFecha(activo.fecha_inicio)} – ${fmtFecha(activo.fecha_fin)}`, "col-span-2 md:col-span-1"),
    dato("Grupos", esc(activo.grupos)),
    dato("Horarios", esc(activo.horarios)),
    dato("Accesos", esc(activo.accesos)),
  ].join("") : `<p class="text-xs text-slate-500">No hay periodo activo.</p>`;

  const btn = document.getElementById("btn-cerrar-periodo");
  if (btn && siguiente) btn.querySelector("span").textContent = `Cerrar periodo y abrir ${siguiente.nombre}`;

  const estado = p => p.estado === "activo"
    ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">Activo</span>`
    : `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">Cerrado${p.fecha_cierre ? " " + esc(String(p.fecha_cierre).slice(0, 10)) : ""}</span>`;
  const acciones = p => `
    <button onclick="verHistorico(${escJsArg(p.id)})" class="px-2 py-1 text-[11px] font-semibold rounded border border-slate-300 text-slate-700 hover:bg-slate-50">Grupos y horarios</button>
    <button onclick="abrirReportePeriodo(${escJsArg(p.id)})" class="px-2 py-1 text-[11px] font-semibold rounded border border-slate-300 text-slate-700 hover:bg-slate-50">Accesos</button>`;

  document.getElementById("table-periodos").innerHTML = periodos.map(p => `
    <tr class="hover:bg-slate-50">
      <td class="px-4 py-3 font-semibold text-slate-900 whitespace-nowrap">${esc(p.nombre)} <span class="block text-[10px] font-mono text-slate-400">${esc(p.id)}</span></td>
      <td class="px-4 py-3 text-slate-600 whitespace-nowrap">${fmtFecha(p.fecha_inicio)} – ${fmtFecha(p.fecha_fin)}</td>
      <td class="px-4 py-3 whitespace-nowrap">${estado(p)}</td>
      <td class="px-4 py-3">${esc(p.grupos)}</td>
      <td class="px-4 py-3">${esc(p.horarios)}</td>
      <td class="px-4 py-3">${esc(p.accesos)}</td>
      <td class="px-4 py-3">${p.estado === "activo" ? "—" : esc(p.inscripciones)}</td>
      <td class="px-4 py-3 text-right whitespace-nowrap space-x-1">${acciones(p)}</td>
    </tr>`).join("");
  document.getElementById("cards-periodos").innerHTML = periodos.map(p => `
    <div class="p-3 rounded-lg border border-slate-200">
      <div class="flex items-center justify-between gap-2">
        <span class="font-semibold text-sm text-slate-900">${esc(p.nombre)}</span>${estado(p)}
      </div>
      <p class="text-[11px] text-slate-500 mt-1">${esc(p.grupos)} grupos • ${esc(p.horarios)} horarios • ${esc(p.accesos)} accesos</p>
      <div class="flex gap-1 mt-2">${acciones(p)}</div>
    </div>`).join("");
}

async function verHistorico(periodoId) {
  const p = PERIODOS_INFO.periodos.find(x => x.id === periodoId);
  try {
    const [grupos, horarios] = await Promise.all([
      apiFetch(`/api/groups?periodo_id=${encodeURIComponent(periodoId)}`),
      apiFetch(`/api/schedules?periodo_id=${encodeURIComponent(periodoId)}`),
    ]);
    document.getElementById("historico-titulo").textContent = p ? p.nombre : periodoId;
    document.getElementById("historico-grupos").innerHTML = grupos.length ? grupos.map(g => `
      <tr><td class="px-3 py-2 font-mono font-bold">${esc(g.clave || g.id)}</td><td class="px-3 py-2">${esc(g.carrera)}</td>
          <td class="px-3 py-2">${esc(g.semestre)}°</td><td class="px-3 py-2">${esc(g.alumnos ?? 0)}</td></tr>`).join("")
      : `<tr><td colspan="4" class="p-4 text-center text-slate-400">Sin grupos</td></tr>`;
    document.getElementById("historico-horarios").innerHTML = horarios.length ? horarios.map(h => `
      <tr><td class="px-3 py-2 whitespace-nowrap">${esc(h.dia_semana)} ${esc(h.hora_inicio)}–${esc(h.hora_fin)}</td>
          <td class="px-3 py-2 font-mono">${esc(h.grupo_clave || h.grupo_id)}</td><td class="px-3 py-2">${esc(h.materia)}</td>
          <td class="px-3 py-2">${esc(h.docente_nombre || h.docente_id)}</td></tr>`).join("")
      : `<tr><td colspan="4" class="p-4 text-center text-slate-400">Sin horarios</td></tr>`;
    document.getElementById("btn-historico-reporte").onclick = () => abrirReportePeriodo(periodoId);
    const panel = document.getElementById("historico-panel");
    panel.classList.remove("hidden");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showAlert("No se pudo consultar el histórico: " + err.message, { type: "error" });
  }
}

async function cerrarPeriodo() {
  const activo = PERIODOS_INFO.periodos.find(p => p.estado === "activo");
  const sig = PERIODOS_INFO.siguiente;
  if (!activo || !sig) return;
  const ok = await showConfirm(
    `¿Cerrar el periodo ${activo.nombre} y abrir ${sig.nombre}?\n\n` +
    `• Grupos (${activo.grupos}) y horarios (${activo.horarios}) pasan al histórico; no se borran.\n` +
    `• Las puertas dejan de usar esos horarios en cuanto se sincronicen.\n` +
    `• Los alumnos quedan sin grupo hasta que se les asigne uno del nuevo periodo.\n` +
    `• Los jefes de carrera deberán crear los grupos y subir los horarios nuevos.\n\n` +
    `Esta acción no se puede deshacer.`,
    { title: "Cerrar periodo escolar", confirmText: "Sí, cerrar periodo", danger: true });
  if (!ok) return;
  const ok2 = await showConfirm(`Confirme de nuevo: se cerrará ${activo.nombre}.`,
    { title: "Confirmación final", confirmText: `Cerrar ${activo.nombre}`, danger: true });
  if (!ok2) return;
  try {
    const res = await apiFetch("/api/periodos/cerrar", { method: "POST" });
    showAlert(`${res.message}\n\nGrupos archivados: ${res.grupos_archivados}. Alumnos guardados en el historial: ${res.inscripciones}.`,
      { type: "success", title: "Periodo cerrado" });
    cargarPeriodoActivo();
    loadPeriodosData();
  } catch (err) {
    showAlert("No se pudo cerrar el periodo: " + err.message, { type: "error" });
  }
}

// ───────────── Jefes de carrera (sección Administradores) ─────────────
let JEFE_EDITANDO = null;

async function loadJefesData() {
  const cont = document.getElementById("cards-jefes");
  if (!cont) return;
  try {
    const jefes = await apiFetch("/api/jefes");
    cont.innerHTML = jefes.length ? jefes.map(j => `
      <div class="p-3 rounded-lg border border-slate-200 flex flex-col sm:flex-row sm:items-center gap-3 ${j.activo ? "" : "opacity-60"}">
        <div class="flex-1 min-w-0">
          <p class="font-semibold text-sm text-slate-900">${esc(j.nombre)}
            <span class="ml-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${j.activo ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-slate-100 text-slate-500"}">${j.activo ? "Activo" : "Desactivado"}</span></p>
          <p class="text-[11px] text-slate-500 font-mono">${esc(j.username)}${j.email ? " • " + esc(j.email) : ""}</p>
          <div class="flex flex-wrap gap-1 mt-1.5">${j.carreras.map(c => `<span class="px-2 py-0.5 rounded bg-slate-100 text-[10px] text-slate-700">${esc(c)}</span>`).join("")}</div>
        </div>
        <div class="flex gap-2 shrink-0">
          <button onclick='editarCarrerasJefe(${JSON.stringify({ id: j.id, nombre: j.nombre, carreras: j.carreras }).replace(/'/g, "&#39;")})' class="px-3 py-1.5 text-[11px] font-semibold rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50">Carreras</button>
          ${typeof botonRestablecer === "function" ? botonRestablecer("jefe", j.id, j.nombre) : ""}
          <button onclick="toggleJefe(${Number(j.id)}, ${j.activo ? 1 : 0}, ${escJsArg(j.username)})" class="px-3 py-1.5 text-[11px] font-semibold rounded-lg ${j.activo ? "border border-red-200 text-red-700 hover:bg-red-50" : "bg-emerald-600 text-white hover:bg-emerald-700"}">${j.activo ? "Desactivar" : "Reactivar"}</button>
        </div>
      </div>`).join("")
      : `<p class="text-xs text-slate-400 p-3 text-center">Aún no hay jefes de carrera. Use "Agregar jefe de carrera".</p>`;
  } catch (err) {
    cont.innerHTML = `<p class="text-xs text-red-600">No se pudieron cargar los jefes de carrera: ${esc(err.message)}</p>`;
  }
}

async function pintarCheckCarreras(marcadas) {
  await MATERIAS_LISTAS;
  document.getElementById("jefe-carreras").innerHTML = Object.keys(MATERIAS_ITSOEH).map(c => `
    <label class="flex items-start gap-2 p-1.5 rounded hover:bg-white cursor-pointer">
      <input type="checkbox" value="${esc(c)}" class="mt-0.5" ${marcadas.includes(c) ? "checked" : ""}>
      <span>${esc(c)}</span>
    </label>`).join("");
}

async function abrirModalJefe(jefe) {
  JEFE_EDITANDO = jefe ? jefe.id : null;
  document.getElementById("form-jefe").reset();
  document.getElementById("jefe-datos").classList.toggle("hidden", !!jefe);
  ["jefe-nombre", "jefe-username", "jefe-password", "jefe-password2"].forEach(id => {
    document.getElementById(id).required = !jefe;
  });
  document.getElementById("jefe-modal-title").textContent = jefe ? `Carreras de ${jefe.nombre}` : "Agregar jefe de carrera";
  document.getElementById("jefe-modal-submit").textContent = jefe ? "Guardar carreras" : "Crear jefe de carrera";
  await pintarCheckCarreras(jefe ? jefe.carreras : []);
  openModal("modal-jefe");
}
function editarCarrerasJefe(jefe) { abrirModalJefe(jefe); }

async function toggleJefe(id, activo, username) {
  const ok = await showConfirm(
    activo ? `¿Desactivar al jefe de carrera "${username}"?\n\nSe cerrará su sesión y no podrá entrar. Lo que subió (grupos, horarios, docentes) se conserva.`
           : `¿Reactivar al jefe de carrera "${username}"?`,
    { title: activo ? "Desactivar jefe de carrera" : "Reactivar jefe de carrera", confirmText: activo ? "Desactivar" : "Reactivar", danger: !!activo });
  if (!ok) return;
  try {
    const res = await apiFetch(`/api/jefes/${id}/toggle`, { method: "POST" });
    showAlert(res.message, { type: "success" });
    loadJefesData();
  } catch (err) {
    showAlert("No se pudo cambiar el estado: " + err.message, { type: "error" });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-cerrar-periodo")?.addEventListener("click", cerrarPeriodo);
  document.getElementById("btn-open-add-jefe")?.addEventListener("click", () => abrirModalJefe(null));
  document.getElementById("btn-jefe-password")?.addEventListener("click", () => {
    document.getElementById("form-change-password")?.reset();
    document.body.classList.remove("sidebar-open");
    openModal("modal-change-password");
  });

  document.getElementById("form-jefe")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const carreras = [...document.querySelectorAll("#jefe-carreras input:checked")].map(i => i.value);
    if (!carreras.length) {
      showAlert("Seleccione al menos una carrera.", { type: "error" });
      return;
    }
    try {
      let res;
      if (JEFE_EDITANDO) {
        res = await apiFetch(`/api/jefes/${JEFE_EDITANDO}/carreras`, { method: "PUT", body: { carreras } });
      } else {
        const pw = document.getElementById("jefe-password").value;
        if (pw !== document.getElementById("jefe-password2").value) {
          showAlert("Las contraseñas no coinciden.", { type: "error" });
          return;
        }
        res = await apiFetch("/api/jefes", { method: "POST", body: {
          nombre: document.getElementById("jefe-nombre").value.trim(),
          username: document.getElementById("jefe-username").value.trim().toLowerCase(),
          email: document.getElementById("jefe-email").value.trim() || null,
          password: pw, carreras,
        } });
      }
      closeModal("modal-jefe");
      showAlert(res.message, { type: "success" });
      loadJefesData();
    } catch (err) {
      showAlert("No se pudo guardar: " + err.message, { type: "error" });
    }
  });
});
