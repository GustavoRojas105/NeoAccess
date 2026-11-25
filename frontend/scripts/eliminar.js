// ─────────────────────────────────────────────────────────────
// Eliminación definitiva con vista previa de lo que se pierde.
// Antes de borrar consulta /api/delete-preview y lo explica en el diálogo.
// ─────────────────────────────────────────────────────────────

const ELIMINAR_CFG = {
  usuario: {
    url: (id) => `/api/users/${encodeURIComponent(id)}/permanent`,
    titulo: "Eliminar persona",
    detalle: (n) => [
      n.rostro ? "su rostro registrado" : null,
      n.horarios ? `${n.horarios} horario(s) donde es docente` : null,
      n.bitacoras_limpieza ? `${n.bitacoras_limpieza} registro(s) de limpieza` : null,
    ],
    nota: (n) => n.accesos_conservados
      ? `Sus ${n.accesos_conservados} acceso(s) del historial se conservan, pero aparecerán como "Desconocido".`
      : "",
  },
  laboratorio: {
    url: (id) => `/api/labs/${encodeURIComponent(id)}/permanent`,
    titulo: "Eliminar laboratorio",
    detalle: (n) => [
      n.horarios ? `${n.horarios} horario(s)` : null,
      n.accesos ? `${n.accesos} acceso(s) del historial` : null,
      n.bitacoras_limpieza ? `${n.bitacoras_limpieza} registro(s) de limpieza` : null,
    ],
    nota: (n) => n.dispositivos_sin_lab
      ? `${n.dispositivos_sin_lab} Raspberry quedará(n) sin laboratorio asignado.`
      : "",
  },
  dispositivo: {
    url: (id) => `/api/devices/${encodeURIComponent(id)}/permanent`,
    titulo: "Eliminar Raspberry",
    detalle: (n) => [
      n.accesos ? `${n.accesos} acceso(s) del historial` : null,
      n.bitacoras_limpieza ? `${n.bitacoras_limpieza} registro(s) de limpieza` : null,
      n.eventos ? `${n.eventos} evento(s) del dispositivo` : null,
    ],
    nota: () => "La Raspberry ya no podrá conectarse con su token actual.",
  },
  grupo: {
    url: (id) => `/api/groups/${encodeURIComponent(id)}`,
    titulo: "Eliminar grupo",
    detalle: (n) => [n.horarios ? `${n.horarios} horario(s) del grupo` : null],
    nota: (n) => n.alumnos_sin_grupo ? `${n.alumnos_sin_grupo} alumno(s) quedarán sin grupo.` : "",
  },
};

/**
 * Pide confirmación (mostrando lo que se pierde) y elimina para siempre.
 * Devuelve true si se eliminó.
 */
async function eliminarDefinitivo(tipo, id, nombre) {
  const cfg = ELIMINAR_CFG[tipo];
  let n;
  try {
    n = await apiFetch(`/api/delete-preview/${tipo}/${encodeURIComponent(id)}`);
  } catch (err) {
    showAlert("No se pudo consultar el registro: " + err.message, { type: "error" });
    return false;
  }
  const extras = cfg.detalle(n).filter(Boolean);
  let msg = `¿Eliminar definitivamente "${nombre}"?`;
  if (extras.length) msg += `\n\nTambién se borrará:\n• ${extras.join("\n• ")}`;
  const nota = cfg.nota(n);
  if (nota) msg += `\n\n${nota}`;
  msg += "\n\nEsto no se puede deshacer.";

  const ok = await showConfirm(msg, { title: cfg.titulo, confirmText: "Eliminar definitivamente", danger: true });
  if (!ok) return false;
  try {
    const res = await apiFetch(cfg.url(id), { method: "DELETE" });
    showAlert(res.message, { type: "success" });
    return true;
  } catch (err) {
    showAlert("No se pudo eliminar: " + err.message, { type: "error" });
    return false;
  }
}
