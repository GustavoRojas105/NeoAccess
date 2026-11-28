/*
 * NeoAccess - Alumnos de un grupo (administrador o jefe de carrera).
 * Lista con casillas de los alumnos de la carrera del grupo; al guardar se mandan
 * solo los que entran y los que salen (PUT /api/groups/{id}/alumnos).
 */
let GA_GRUPO = null;      // { id, clave, nombre, carrera }
let GA_ALUMNOS = [];      // alumnos de la carrera
let GA_MARCADOS = new Set();

async function abrirAlumnosDeGrupo(grupo) {
  GA_GRUPO = grupo;
  document.getElementById("ga-titulo").textContent = `Alumnos del grupo ${grupo.clave || grupo.id}`;
  document.getElementById("ga-subtitulo").textContent = `${grupo.nombre} · ${grupo.carrera}`;
  document.getElementById("ga-buscar").value = "";
  document.getElementById("ga-sin-grupo").checked = false;
  document.getElementById("ga-lista").innerHTML = `<p class="p-4 text-center text-xs text-slate-400">Cargando...</p>`;
  openModal("modal-grupo-alumnos");
  try {
    GA_ALUMNOS = await apiFetch(`/api/jefe/alumnos?carrera=${encodeURIComponent(grupo.carrera)}`);
    GA_MARCADOS = new Set(GA_ALUMNOS.filter(a => a.grupo_id === grupo.id).map(a => a.id));
    pintarAlumnosDeGrupo();
  } catch (err) {
    document.getElementById("ga-lista").innerHTML = `<p class="p-4 text-center text-xs text-red-600">${esc(err.message)}</p>`;
  }
}

function pintarAlumnosDeGrupo() {
  const q = document.getElementById("ga-buscar").value.trim().toUpperCase();
  const soloSin = document.getElementById("ga-sin-grupo").checked;
  const lista = GA_ALUMNOS.filter(a =>
    (!q || a.nombre_completo.toUpperCase().includes(q) || String(a.matricula_clave).includes(q)) &&
    (!soloSin || !a.grupo_id || GA_MARCADOS.has(a.id)));
  document.getElementById("ga-lista").innerHTML = !lista.length
    ? `<p class="p-4 text-center text-xs text-slate-400">No hay alumnos de ${esc(GA_GRUPO.carrera)} con ese filtro. Los alumnos aparecen aquí cuando crean su cuenta.</p>`
    : lista.map(a => {
      const otro = a.grupo_id && a.grupo_id !== GA_GRUPO.id;
      return `
      <label class="flex items-center gap-3 py-2 px-1 cursor-pointer hover:bg-slate-50">
        <input type="checkbox" class="w-4 h-4 accent-slate-900" ${GA_MARCADOS.has(a.id) ? "checked" : ""}
          onchange="marcarAlumnoDeGrupo(${escJsArg(a.id)}, this.checked)">
        <span class="min-w-0 flex-1">
          <span class="block text-xs font-semibold text-slate-900 truncate">${esc(a.nombre_completo)}</span>
          <span class="block text-[11px] text-slate-500"><span class="font-mono">${esc(a.matricula_clave)}</span>
            · ${a.grupo_id ? (otro ? `<span class="text-amber-700">ahora en ${esc(a.grupo_clave)}</span>` : "en este grupo") : "sin grupo"}</span>
        </span>
      </label>`;
    }).join("");
  actualizarConteoGrupo();
}

function marcarAlumnoDeGrupo(id, marcado) {
  if (marcado) GA_MARCADOS.add(id); else GA_MARCADOS.delete(id);
  actualizarConteoGrupo();
}

function cambiosDeGrupo() {
  const antes = new Set(GA_ALUMNOS.filter(a => a.grupo_id === GA_GRUPO.id).map(a => a.id));
  return {
    agregar: [...GA_MARCADOS].filter(id => !antes.has(id)),
    quitar: [...antes].filter(id => !GA_MARCADOS.has(id)),
  };
}

function actualizarConteoGrupo() {
  const { agregar, quitar } = cambiosDeGrupo();
  const mueve = agregar.filter(id => (GA_ALUMNOS.find(a => a.id === id) || {}).grupo_id).length;
  document.getElementById("ga-conteo").textContent =
    `${GA_MARCADOS.size} seleccionado(s)` + (agregar.length || quitar.length
      ? ` · entran ${agregar.length}${mueve ? ` (${mueve} cambian de grupo)` : ""}, salen ${quitar.length}` : "");
  document.getElementById("ga-guardar").disabled = !agregar.length && !quitar.length;
}

async function guardarAlumnosDeGrupo() {
  const cambios = cambiosDeGrupo();
  const btn = document.getElementById("ga-guardar");
  btn.disabled = true;
  try {
    const r = await apiFetch(`/api/groups/${encodeURIComponent(GA_GRUPO.id)}/alumnos`, { method: "PUT", body: cambios });
    closeModal("modal-grupo-alumnos");
    showAlert(r.message, { type: "success" });
    if (typeof loadGroupsTable === "function") loadGroupsTable();
  } catch (err) {
    showAlert("No se pudo guardar: " + err.message, { type: "error" });
    btn.disabled = false;
  }
}
