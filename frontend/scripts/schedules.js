/**
 * NeoAccess - Módulo de Horarios y Grupos (RF-02, RF-03, RF-17)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\schedules.js
 */

async function loadSchedulesData() {
  const labId = document.getElementById("filter-schedule-lab")?.value || "todos";

  try {
    const params = new URLSearchParams();
    if (labId !== "todos") params.append("laboratorio_id", labId);

    const schedules = await apiFetch(`/api/schedules?${params.toString()}`);
    renderSchedulesTable(schedules);
  } catch (err) {
    console.error("Error al cargar horarios:", err);
  }
}

function renderSchedulesTable(schedules) {
  const tbody = document.getElementById("table-schedules");
  if (!tbody) return;

  if (schedules.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">No se encontraron horarios para los filtros seleccionados</td></tr>`;
    return;
  }

  tbody.innerHTML = schedules.map(s => {
    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-semibold text-slate-900">${esc(s.dia_semana)}</td>
        <td class="px-4 py-3 font-mono text-[11px] bg-slate-50/50">
          <span class="inline-block px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-bold">
            ${esc(s.hora_inicio)} - ${esc(s.hora_fin)}
          </span>
        </td>
        <td class="px-4 py-3">
          <div class="font-medium text-slate-900">${esc(s.laboratorio_nombre)}</div>
          <div class="text-[10px] text-slate-400">${esc(s.edificio)}</div>
        </td>
        <td class="px-4 py-3">
          <span class="inline-block px-2 py-0.5 bg-slate-200 text-slate-800 rounded text-[11px] font-semibold">
            ${esc(s.grupo_clave || s.grupo_id || (s.docente_id ? 'N/A' : 'Libre'))}
          </span>
          <div class="text-[10px] text-slate-400 mt-0.5">${esc(s.grupo_nombre || "")}${s.grupo_carrera ? " • " + esc(s.grupo_carrera) : ""}</div>
        </td>
        <td class="px-4 py-3 font-medium text-slate-800">${esc(s.materia)}</td>
        <td class="px-4 py-3 text-slate-700">
          <i data-lucide="user-check" class="w-3.5 h-3.5 inline text-slate-400 mr-1"></i>
          <span>${s.docente_id ? esc(s.docente_nombre || s.docente_id) : '<span class="italic text-slate-400">Sin docente (actividad)</span>'}</span>
        </td>
        <td class="px-4 py-3 text-right">
          <button onclick="deleteSchedule(${esc(s.id)})" class="p-1 text-slate-400 hover:text-red-600 transition" title="Eliminar Horario">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

// Grupos reales (con su carrera) para el formulario "Agregar horario"
async function loadScheduleFormOptions() {
  const selGrupo = document.getElementById("schedule-new-group");
  const selMateria = document.getElementById("schedule-new-subject");
  if (!selGrupo) return;
  try {
    const grupos = await apiFetch("/api/groups");
    selGrupo.innerHTML = grupos.length
      ? `<option value="">Seleccione un grupo...</option>` + grupos.map(g =>
          `<option value="${esc(g.id)}" data-carrera="${esc(g.carrera || "")}" data-semestre="${esc(g.semestre || "")}">${esc(g.id)} • ${esc(g.nombre)}</option>`
        ).join("")
      : `<option value="">No hay grupos registrados</option>`;
  } catch (err) {
    selGrupo.innerHTML = `<option value="">No se pudieron cargar los grupos</option>`;
  }
  fillSubjectSelect(selMateria, null, null);

  try {
    const labs = await apiFetch("/api/labs");   // por si se agregaron laboratorios hace un momento
    STATE.laboratorios = labs;
    populateLabDropdowns(labs);
  } catch (err) { /* se conserva la lista anterior */ }

  const selDocente = document.getElementById("schedule-new-teacher");
  try {
    const docentes = (await apiFetch("/api/users?tipo=docente")).filter(d => d.estado === "activo");
    selDocente.innerHTML = docentes.length
      ? `<option value="">Seleccione un docente...</option>` + docentes.map(d =>
          `<option value="${esc(d.id)}">${esc(d.nombre_completo)} (${esc(d.matricula_clave)})</option>`).join("")
      : `<option value="">No hay docentes: regístrelos en Maestros y Personal</option>`;
    selDocente.innerHTML += `<option value="SIN-DOCENTE">— Sin docente (actividad del laboratorio) —</option>`;
  } catch (err) {
    selDocente.innerHTML = `<option value="">No se pudieron cargar los docentes</option>`;
  }
  toggleScheduleActivityMode();
}

// "Sin docente": el grupo es opcional y la materia se escribe (Práctica de Redes, Club IoT...)
function toggleScheduleActivityMode() {
  const actividad = document.getElementById("schedule-new-teacher")?.value === "SIN-DOCENTE";
  const selGrupo = document.getElementById("schedule-new-group");
  const selMateria = document.getElementById("schedule-new-subject");
  const txt = document.getElementById("schedule-new-activity");
  if (!selGrupo || !selMateria || !txt) return;
  selGrupo.required = !actividad;
  selMateria.required = !actividad;
  selMateria.classList.toggle("hidden", actividad);
  txt.required = actividad;
  txt.classList.toggle("hidden", !actividad);
  document.getElementById("schedule-new-activity-help")?.classList.toggle("hidden", !actividad);
  const label = document.getElementById("schedule-new-subject-label");
  if (label) label.textContent = actividad ? "Nombre de la actividad *" : "Materia (retícula oficial ITSOEH) *";
}

async function deleteSchedule(scheduleId) {
  if (!(await showConfirm("¿Está seguro de eliminar este horario? Los alumnos y docentes no podrán acceder en este bloque.", { title: "Eliminar horario", confirmText: "Eliminar", danger: true }))) {
    return;
  }
  try {
    await apiFetch(`/api/schedules/${scheduleId}`, { method: "DELETE" });
    loadSchedulesData();
  } catch (err) {
    showAlert("Error al eliminar horario: " + err.message);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("filter-schedule-lab")?.addEventListener("change", () => {
    loadSchedulesData();
  });

  // Modal para agregar horario
  document.getElementById("btn-modal-add-schedule")?.addEventListener("click", async () => {
    await loadScheduleFormOptions();
    openModal("modal-add-schedule");
  });

  document.getElementById("schedule-new-teacher")?.addEventListener("change", toggleScheduleActivityMode);

  // Al elegir el grupo, la lista de materias muestra las de su carrera (y semestre)
  document.getElementById("schedule-new-group")?.addEventListener("change", (e) => {
    const opt = e.target.selectedOptions[0];
    fillSubjectSelect(document.getElementById("schedule-new-subject"), opt?.dataset.carrera, opt?.dataset.semestre);
  });

  document.getElementById("form-add-schedule")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      laboratorio_id: document.getElementById("schedule-new-lab").value,
      grupo_id: document.getElementById("schedule-new-group").value || null,
      docente_id: document.getElementById("schedule-new-teacher").value,
      materia: (document.getElementById("schedule-new-teacher").value === "SIN-DOCENTE"
        ? document.getElementById("schedule-new-activity").value
        : document.getElementById("schedule-new-subject").value).trim(),
      dia_semana: document.getElementById("schedule-new-day").value,
      hora_inicio: document.getElementById("schedule-new-start").value,
      hora_fin: document.getElementById("schedule-new-end").value
    };

    try {
      await apiFetch("/api/schedules", {
        method: "POST",
        body: payload
      });
      closeModal("modal-add-schedule");
      document.getElementById("form-add-schedule").reset();
      toggleScheduleActivityMode();
      loadSchedulesData();
    } catch (err) {
      showAlert("Error al registrar horario: " + err.message);
    }
  });
});


// ─────────────── Grupos ───────────────
async function loadGroupsTable() {
  const tbody = document.getElementById("table-groups");
  if (!tbody) return;
  try {
    const grupos = await apiFetch("/api/groups");
    tbody.innerHTML = grupos.length ? grupos.map(g => `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-mono font-bold text-slate-900">${esc(g.id)}</td>
        <td class="px-4 py-3 font-medium text-slate-900">${esc(g.nombre)}</td>
        <td class="px-4 py-3 text-slate-600">${esc(g.carrera)}</td>
        <td class="px-4 py-3 text-slate-600">${esc(g.semestre)}°</td>
        <td class="px-4 py-3 text-slate-600">${esc(g.alumnos ?? 0)}</td>
        <td class="px-4 py-3 text-right whitespace-nowrap">
          <button onclick='abrirAlumnosDeGrupo(${JSON.stringify({ id: g.id, clave: g.clave || g.id, nombre: g.nombre, carrera: g.carrera }).replace(/'/g, "&#39;")})' class="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-slate-700 border border-slate-300 hover:bg-slate-50 rounded-lg transition" title="Asignar alumnos a este grupo">
            <i data-lucide="users" class="w-3.5 h-3.5"></i> Alumnos
          </button>
          <button onclick='editGroup(${JSON.stringify({ id: g.id, nombre: g.nombre, carrera: g.carrera, semestre: g.semestre }).replace(/'/g, "&#39;")})' class="p-1.5 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded transition" title="Editar grupo">
            <i data-lucide="pencil" class="w-4 h-4"></i>
          </button>
          <button onclick="deleteGroup(${escJsArg(g.id)}, ${escJsArg(g.nombre)})" class="jefe-hide p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition" title="Eliminar grupo">
            <i data-lucide="trash-2" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>`).join("")
      : `<tr><td colspan="6" class="p-4 text-center text-slate-400">No hay grupos en este periodo. Use "Agregar grupo" para crear el primero.</td></tr>`;
    if (window.lucide) lucide.createIcons();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="p-4 text-center text-slate-400">No se pudieron cargar los grupos</td></tr>`;
  }
}

async function deleteGroup(groupId, nombre) {
  if (await eliminarDefinitivo("grupo", groupId, nombre)) {
    loadGroupsTable();
    loadSchedulesData();
  }
}

let GRUPO_EDITANDO = null;

async function abrirModalGrupo(grupo) {
  GRUPO_EDITANDO = grupo ? grupo.id : null;
  const form = document.getElementById("form-add-group");
  form?.reset();
  await fillCareerSelect(document.getElementById("group-new-career"), "Seleccione una carrera...");
  const idInput = document.getElementById("group-new-id");
  idInput.disabled = !!grupo;
  document.getElementById("group-modal-title").textContent = grupo ? `Editar grupo ${grupo.id}` : "Agregar grupo";
  document.getElementById("group-modal-submit").textContent = grupo ? "Guardar cambios" : "Crear grupo";
  if (grupo) {
    idInput.value = grupo.id;
    document.getElementById("group-new-name").value = grupo.nombre;
    document.getElementById("group-new-career").value = grupo.carrera;
    document.getElementById("group-new-semester").value = String(grupo.semestre);
  } else if (esJefe() && (STATE.user.carreras || []).length === 1) {
    document.getElementById("group-new-career").value = STATE.user.carreras[0];
  }
  openModal("modal-add-group");
}
function editGroup(grupo) { abrirModalGrupo(grupo); }

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-modal-add-group")?.addEventListener("click", () => abrirModalGrupo(null));
  document.getElementById("form-add-group")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      id: document.getElementById("group-new-id").value.trim().toUpperCase(),
      nombre: document.getElementById("group-new-name").value.trim(),
      carrera: document.getElementById("group-new-career").value,
      semestre: parseInt(document.getElementById("group-new-semester").value, 10),
    };
    try {
      const res = GRUPO_EDITANDO
        ? await apiFetch(`/api/groups/${encodeURIComponent(GRUPO_EDITANDO)}`, { method: "PUT", body: payload })
        : await apiFetch("/api/groups", { method: "POST", body: payload });
      closeModal("modal-add-group");
      e.target.reset();
      showAlert(res.message, { type: "success" });
      loadGroupsTable();
      loadSchedulesData();
    } catch (err) {
      showAlert((GRUPO_EDITANDO ? "No se pudo guardar el grupo: " : "No se pudo crear el grupo: ") + err.message, { type: "error" });
    }
  });
});
