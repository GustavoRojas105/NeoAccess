// ─────────────────────────────────────────────────────────────
// Sección "Administradores": alta, activar/desactivar y cambio de contraseña
// ─────────────────────────────────────────────────────────────

async function loadAdminsData() {
  const tbody = document.getElementById("table-admins");
  const cards = document.getElementById("cards-admins");
  if (!tbody) return;
  try {
    const admins = await apiFetch("/api/admins");
    renderAdmins(admins);
  } catch (err) {
    const msg = `No se pudieron cargar los administradores: ${esc(err.message)}`;
    tbody.innerHTML = `<tr><td colspan="6" class="p-6 text-center text-slate-400">${msg}</td></tr>`;
    if (cards) cards.innerHTML = `<p class="p-4 text-center text-xs text-slate-400">${msg}</p>`;
  }
}

function adminEstadoBadge(a) {
  return a.activo
    ? `<span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold badge-status-online">Activo</span>`
    : `<span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold badge-status-offline">Desactivado</span>`;
}

function adminAccion(a) {
  if (a.es_yo) return `<span class="text-[10px] text-slate-400 font-semibold">Tu cuenta</span>`;
  const reset = typeof botonRestablecer === "function" ? botonRestablecer("admin", a.id, a.nombre) : "";
  return `<span class="inline-flex flex-wrap gap-1.5 justify-end">${reset}` + (a.activo
    ? `<button onclick="toggleAdmin(${a.id}, ${a.activo}, '${esc(a.username)}')" class="px-2.5 py-1.5 text-[11px] font-semibold rounded-lg border border-red-200 text-red-600 hover:bg-red-50">Desactivar</button>`
    : `<button onclick="toggleAdmin(${a.id}, ${a.activo}, '${esc(a.username)}')" class="px-2.5 py-1.5 text-[11px] font-semibold rounded-lg border border-emerald-200 text-emerald-700 hover:bg-emerald-50">Reactivar</button>`) + `</span>`;
}

function renderAdmins(admins) {
  const tbody = document.getElementById("table-admins");
  const cards = document.getElementById("cards-admins");
  const fecha = (f) => esc((f || "").slice(0, 10) || "—");

  tbody.innerHTML = admins.map(a => `
    <tr class="hover:bg-slate-50 ${a.activo ? "" : "opacity-60"}">
      <td class="px-4 py-3 font-semibold text-slate-900">${esc(a.nombre)}${a.es_yo ? ' <span class="text-[10px] text-emerald-600">(tú)</span>' : ""}</td>
      <td class="px-4 py-3 font-mono text-[11px] text-slate-700">${esc(a.username)}</td>
      <td class="px-4 py-3 text-slate-600">${esc(a.email || "—")}</td>
      <td class="px-4 py-3 font-mono text-[11px] text-slate-500">${fecha(a.fecha_creacion)}</td>
      <td class="px-4 py-3">${adminEstadoBadge(a)}</td>
      <td class="px-4 py-3 text-right">${adminAccion(a)}</td>
    </tr>`).join("");

  if (cards) {
    cards.innerHTML = admins.map(a => `
      <div class="p-3 rounded-lg border border-slate-200 bg-white ${a.activo ? "" : "opacity-60"}">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="font-semibold text-sm text-slate-900 truncate">${esc(a.nombre)}${a.es_yo ? ' <span class="text-[10px] text-emerald-600">(tú)</span>' : ""}</p>
            <p class="font-mono text-[11px] text-slate-600">${esc(a.username)}</p>
            <p class="text-[11px] text-slate-500 truncate">${esc(a.email || "Sin correo")}</p>
          </div>
          ${adminEstadoBadge(a)}
        </div>
        <div class="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
          <span class="text-[10px] text-slate-400">Alta: ${fecha(a.fecha_creacion)}</span>
          ${adminAccion(a)}
        </div>
      </div>`).join("");
  }
}

async function toggleAdmin(id, activo, username) {
  const desactivar = !!activo;
  const ok = await showConfirm(
    desactivar
      ? `¿Desactivar al administrador "${username}"?\n\nSe cerrará su sesión de inmediato y no podrá volver a entrar hasta que lo reactives.`
      : `¿Reactivar al administrador "${username}"? Podrá volver a iniciar sesión con su contraseña.`,
    { title: desactivar ? "Desactivar administrador" : "Reactivar administrador",
      confirmText: desactivar ? "Desactivar" : "Reactivar", danger: desactivar }
  );
  if (!ok) return;
  try {
    const res = await apiFetch(`/api/admins/${id}/toggle`, { method: "POST" });
    showAlert(res.message, { type: "success" });
    loadAdminsData();
  } catch (err) {
    showAlert("No se pudo cambiar el estado: " + err.message, { type: "error" });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-open-add-admin")?.addEventListener("click", () => {
    document.getElementById("form-add-admin")?.reset();
    openModal("modal-add-admin");
  });
  document.getElementById("btn-open-change-password")?.addEventListener("click", () => {
    document.getElementById("form-change-password")?.reset();
    openModal("modal-change-password");
  });

  document.getElementById("form-add-admin")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pw = document.getElementById("admin-new-password").value;
    if (pw !== document.getElementById("admin-new-password2").value) {
      showAlert("Las contraseñas no coinciden.", { type: "error" });
      return;
    }
    const payload = {
      nombre: document.getElementById("admin-new-nombre").value.trim(),
      username: document.getElementById("admin-new-username").value.trim().toLowerCase(),
      email: document.getElementById("admin-new-email").value.trim() || null,
      password: pw,
    };
    try {
      const res = await apiFetch("/api/admins", { method: "POST", body: payload });
      closeModal("modal-add-admin");
      e.target.reset();
      showAlert(res.message, { type: "success" });
      loadAdminsData();
    } catch (err) {
      showAlert("No se pudo crear el administrador: " + err.message, { type: "error" });
    }
  });

  document.getElementById("form-change-password")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nueva = document.getElementById("pw-nueva").value;
    if (nueva !== document.getElementById("pw-nueva2").value) {
      showAlert("Las contraseñas nuevas no coinciden.", { type: "error" });
      return;
    }
    try {
      const res = await apiFetch("/api/admins/me/password", {
        method: "POST",
        body: { actual: document.getElementById("pw-actual").value, nueva },
      });
      closeModal("modal-change-password");
      e.target.reset();
      showAlert(res.message, { type: "success" });
    } catch (err) {
      showAlert("No se pudo cambiar la contraseña: " + err.message, { type: "error" });
    }
  });
});
