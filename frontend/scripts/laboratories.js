/**
 * NeoAccess - Módulo Exclusivo de Laboratorios (Laboratories)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\laboratories.js
 * Permite agregar laboratorios reales, editarlos y listarlos.
 */

async function loadLaboratoriesData() {
  try {
    const labs = await apiFetch("/api/labs?todos=true");
    STATE.laboratorios = labs;
    populateLabDropdowns(labs);
    renderLaboratoriesTable(labs);
  } catch (err) {
    console.error("Error al cargar laboratorios:", err);
  }
}

function renderLaboratoriesTable(labs) {
  const tbody = document.getElementById("table-laboratories");
  if (!tbody) return;

  if (labs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">No hay laboratorios registrados</td></tr>`;
    return;
  }

  tbody.innerHTML = labs.map(lab => {
    const isActivo = lab.activo === 1;
    const onlineDevs = lab.dispositivos_en_linea || 0;
    const totalDevs = lab.total_dispositivos || 0;

    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-mono font-bold text-slate-900">${esc(lab.id)}</td>
        <td class="px-4 py-3 font-semibold text-slate-800">
          ${esc(lab.nombre)}
          ${lab.descripcion ? `<span class="block text-[11px] text-slate-400 font-normal">${esc(lab.descripcion)}</span>` : ''}
        </td>
        <td class="px-4 py-3 text-slate-600">${esc(lab.edificio)}</td>
        <td class="px-4 py-3 text-slate-600">${esc(lab.carrera)}</td>
        <td class="px-4 py-3 text-slate-700">${esc(lab.capacidad)} alumnos</td>
        <td class="px-4 py-3">
          <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${totalDevs > 0 ? (onlineDevs > 0 ? 'badge-status-online' : 'badge-status-offline') : 'badge-status-disabled'}">
            <span class="status-dot ${totalDevs > 0 ? (onlineDevs > 0 ? 'online' : 'offline') : 'disabled'}"></span>
            ${totalDevs} puerta(s) • ${onlineDevs} en línea
          </span>
        </td>
        <td class="px-4 py-3 text-right space-x-1">
          <button onclick="toggleLabStatus(${escJsArg(lab.id)}, ${isActivo ? 0 : 1})"
            class="p-1.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded transition"
            title="${isActivo ? 'Desactivar laboratorio' : 'Activar laboratorio'}">
            <i data-lucide="${isActivo ? 'trash-2' : 'rotate-ccw'}" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

async function toggleLabStatus(labId, newStatus) {
  const actionText = newStatus === 0 ? "desactivar" : "activar";
  if (!(await showConfirm(`¿Está seguro de ${actionText} este laboratorio?`, { confirmText: newStatus === 0 ? "Desactivar" : "Activar", danger: newStatus === 0 }))) return;

  try {
    if (newStatus === 0) {
      await apiFetch(`/api/labs/${labId}`, { method: "DELETE" });
    } else {
      // Activar nuevamente
      const lab = STATE.laboratorios.find(l => l.id === labId);
      if (lab) {
        await apiFetch(`/api/labs/${labId}`, {
          method: "PUT",
          body: {
            nombre: lab.nombre,
            edificio: lab.edificio,
            carrera: lab.carrera,
            capacidad: lab.capacidad,
            descripcion: lab.descripcion,
            activo: 1
          }
        });
      }
    }
    await loadLaboratoriesData();
    updateGlobalDeviceStatus();
  } catch (err) {
    showAlert("Error al cambiar estado del laboratorio: " + err.message);
  }
}

// Inicialización de eventos para formulario de Agregar Laboratorio
document.addEventListener("DOMContentLoaded", () => {
  const btnOpenModal = document.getElementById("btn-modal-add-lab");
  if (btnOpenModal) {
    btnOpenModal.addEventListener("click", () => {
      openModal("modal-add-lab");
    });
  }

  const formAddLab = document.getElementById("form-add-lab");
  if (formAddLab) {
    formAddLab.addEventListener("submit", async (e) => {
      e.preventDefault();

      const payload = {
        id: document.getElementById("lab-new-id").value.trim().toUpperCase(),
        nombre: document.getElementById("lab-new-name").value.trim(),
        edificio: document.getElementById("lab-new-building").value.trim(),
        carrera: document.getElementById("lab-new-career").value.trim(),
        capacidad: parseInt(document.getElementById("lab-new-capacity").value) || 30,
        descripcion: document.getElementById("lab-new-desc").value.trim()
      };

      try {
        const res = await apiFetch("/api/labs", {
          method: "POST",
          body: payload
        });

        showAlert(`✓ ¡Laboratorio '${payload.nombre}' creado con éxito!`);
        closeModal("modal-add-lab");
        formAddLab.reset();

        // Recargar datos y actualizar dropdowns en toda la aplicación
        await loadLaboratoriesData();
      } catch (err) {
        showAlert("Error al agregar laboratorio: " + err.message);
      }
    });
  }
});
