// ─────────────────────────────────────────────────────────────
// Materias oficiales del ITSOEH.
// La lista vive en scripts/materias_itsoeh.json (la misma que usa el servidor
// para validar la importación de horarios). Para agregar materias, edite ese
// archivo: { "Carrera": { "semestre": ["Materia", ...] } }  ("0" = sin semestre).
// ─────────────────────────────────────────────────────────────
let MATERIAS_ITSOEH = {};

const MATERIAS_LISTAS = fetch("/scripts/materias_itsoeh.json?v=20261125_1")
  .then(r => r.json())
  .then(data => {
    MATERIAS_ITSOEH = Object.fromEntries(Object.entries(data.carreras).map(([carrera, porSemestre]) => [
      carrera,
      Object.entries(porSemestre).flatMap(([s, lista]) =>
        lista.map(m => ({ s: s === "0" ? null : Number(s), m })))
    ]));
    return MATERIAS_ITSOEH;
  })
  .catch(err => { console.error("No se pudo cargar el catálogo de materias:", err); return {}; });

// Llena un <select> de carreras con las carreras oficiales.
async function fillCareerSelect(select, primeraOpcion) {
  if (!select) return;
  await MATERIAS_LISTAS;
  const escapar = (t) => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const propias = (typeof STATE !== "undefined" && STATE.user && STATE.user.rol === "jefe_carrera") ? (STATE.user.carreras || []) : null;
  select.innerHTML = `<option value="">${escapar(primeraOpcion)}</option>` +
    Object.keys(MATERIAS_ITSOEH).filter(c => !propias || propias.includes(c)).map(c => `<option value="${escapar(c)}">${escapar(c)}</option>`).join("");
}

// Llena un <select> de materias según la carrera (y semestre) del grupo.
// Sin carrera conocida muestra todas, agrupadas por carrera.
async function fillSubjectSelect(select, carrera, semestre) {
  if (!select) return;
  await MATERIAS_LISTAS;
  const escapar = (t) => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const opcion = (m) => `<option value="${escapar(m)}">${escapar(m)}</option>`;
  const grupo = (etiqueta, lista) => `<optgroup label="${escapar(etiqueta)}">${lista.map(opcion).join("")}</optgroup>`;

  let html = `<option value="">Seleccione la materia...</option>`;
  const lista = MATERIAS_ITSOEH[carrera];
  if (lista) {
    const delSemestre = lista.filter(x => x.s === Number(semestre)).map(x => x.m);
    const resto = lista.filter(x => x.s !== Number(semestre)).map(x => x.m);
    if (delSemestre.length) html += grupo(`${semestre}° semestre`, delSemestre);
    if (resto.length) html += grupo(delSemestre.length ? "Otros semestres" : carrera, resto);
  } else {
    for (const [c, l] of Object.entries(MATERIAS_ITSOEH)) html += grupo(c, l.map(x => x.m));
  }
  select.innerHTML = html;
}
