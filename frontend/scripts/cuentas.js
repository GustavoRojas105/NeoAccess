/**
 * NeoAccess - Cuentas de portal por perfil (sección Administradores):
 * apartados de Docentes, Alumnos y Personal de limpieza, con alta, edición,
 * contraseña y baja/reactivación. Mismo estilo que "Jefes de carrera".
 */
const CUENTA_PERFILES = {
  docente: { nombre: "docente", clave: "Clave docente *", vacio: "Aún no hay docentes." },
  alumno: { nombre: "alumno", clave: "Matrícula *", vacio: "Aún no hay alumnos." },
  personal_limpieza: { nombre: "personal de limpieza", clave: "Clave *", vacio: "Aún no hay personal de limpieza." },
};
const CUENTAS = { docente: [], alumno: [], personal_limpieza: [] };
const CUENTA_FILTRO = { docente: "", alumno: "", personal_limpieza: "" };
let CUENTA_EDITANDO = null;   // usuario que se edita (null = alta)
let CUENTA_TIPO = null;
let CUENTA_GRUPOS = [];

async function loadCuentasData() {
  await Promise.all(Object.keys(CUENTA_PERFILES).map(async (tipo) => {
    const cont = document.getElementById(`cards-cuentas-${tipo}`);
    if (!cont) return;
    try {
      CUENTAS[tipo] = await apiFetch(`/api/users?tipo=${tipo}`);
      pintarCuentas(tipo);
    } catch (err) {
      cont.innerHTML = `<p class="text-xs text-red-600">No se pudieron cargar: ${esc(err.message)}</p>`;
    }
  }));
}

function filtrarCuentas(tipo, texto) {
  CUENTA_FILTRO[tipo] = (texto || "").trim().toLowerCase();
  pintarCuentas(tipo);
}

function pintarCuentas(tipo) {
  const cont = document.getElementById(`cards-cuentas-${tipo}`);
  const f = CUENTA_FILTRO[tipo];
  const lista = CUENTAS[tipo]
    .filter(u => !f || `${u.nombre_completo} ${u.matricula_clave}`.toLowerCase().includes(f))
    .sort((a, b) => (a.estado === b.estado ? 0 : a.estado === "activo" ? -1 : 1) || a.nombre_completo.localeCompare(b.nombre_completo));
  if (!lista.length) {
    cont.innerHTML = `<p class="text-xs text-slate-400 p-3 text-center">${f ? "Nadie coincide con la búsqueda." : CUENTA_PERFILES[tipo].vacio}</p>`;
    return;
  }
  cont.innerHTML = lista.map(u => {
    const activo = u.estado === "activo";
    const detalle = [u.carrera, u.grupo_id ? `Grupo ${u.grupo_nombre || u.grupo_id}` : (tipo === "alumno" ? "Sin grupo" : "")]
      .filter(Boolean).map(esc).join(" • ");
    return `
      <div class="p-3 rounded-lg border border-slate-200 flex flex-col sm:flex-row sm:items-center gap-3 ${activo ? "" : "opacity-60"}">
        <div class="flex-1 min-w-0">
          <p class="font-semibold text-sm text-slate-900">${esc(u.nombre_completo)}
            <span class="ml-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${activo ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-slate-100 text-slate-500"}">${activo ? "Activo" : "Dado de baja"}</span>
            <span class="ml-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${u.tiene_password ? "bg-sky-50 text-sky-700 border border-sky-200" : "bg-amber-50 text-amber-700 border border-amber-200"}">${u.tiene_password ? "Con contraseña" : "Sin contraseña"}</span>
          </p>
          <p class="text-[11px] text-slate-500 font-mono">${esc(u.matricula_clave)}${u.correo ? " • " + esc(u.correo) : ""}</p>
          ${detalle ? `<p class="text-[11px] text-slate-500 mt-0.5">${detalle}</p>` : ""}
        </div>
        <div class="flex gap-2 shrink-0">
          <button onclick="abrirModalCuenta(${escJsArg(tipo)}, ${escJsArg(u.id)})" class="px-3 py-1.5 text-[11px] font-semibold rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50">Editar</button>
          <button onclick="toggleCuenta(${escJsArg(tipo)}, ${escJsArg(u.id)})" class="px-3 py-1.5 text-[11px] font-semibold rounded-lg ${activo ? "border border-red-200 text-red-700 hover:bg-red-50" : "bg-emerald-600 text-white hover:bg-emerald-700"}">${activo ? "Dar de baja" : "Reactivar"}</button>
        </div>
      </div>`;
  }).join("");
}

async function pintarSelectsCuenta(tipo, carrera, grupo) {
  await MATERIAS_LISTAS;
  const selCarrera = document.getElementById("cuenta-carrera");
  selCarrera.innerHTML = `<option value="">— Sin carrera —</option>` + Object.keys(MATERIAS_ITSOEH)
    .map(c => `<option value="${esc(c)}" ${c === carrera ? "selected" : ""}>${esc(c)}</option>`).join("");
  if (tipo !== "alumno") return;
  try { CUENTA_GRUPOS = await apiFetch("/api/groups"); } catch (err) { CUENTA_GRUPOS = []; }
  pintarGruposCuenta(carrera, grupo);
}

function pintarGruposCuenta(carrera, grupo) {
  const grupos = CUENTA_GRUPOS.filter(g => !carrera || g.carrera === carrera);
  document.getElementById("cuenta-grupo").innerHTML = `<option value="">— Sin grupo —</option>` + grupos
    .map(g => `<option value="${esc(g.id)}" ${g.id === grupo ? "selected" : ""}>${esc(g.clave || g.id)} • ${esc(g.nombre)}</option>`).join("");
}

async function abrirModalCuenta(tipo, userId) {
  const u = userId ? CUENTAS[tipo].find(x => x.id === userId) : null;
  CUENTA_TIPO = tipo;
  CUENTA_EDITANDO = u || null;
  const perfil = CUENTA_PERFILES[tipo];
  document.getElementById("form-cuenta").reset();
  document.getElementById("cuenta-modal-title").textContent = u ? `Editar ${perfil.nombre}: ${u.nombre_completo}` : `Agregar ${perfil.nombre}`;
  document.getElementById("cuenta-clave-label").textContent = perfil.clave;
  document.getElementById("cuenta-nombre").value = u ? u.nombre_completo : "";
  document.getElementById("cuenta-clave").value = u ? u.matricula_clave : "";
  document.getElementById("cuenta-clave").dataset.tipo = tipo;
  if (window.revisarCampo) ["cuenta-nombre", "cuenta-clave"].forEach(id => revisarCampo(document.getElementById(id)));
  document.getElementById("cuenta-estado-box").classList.toggle("hidden", !u);
  document.getElementById("cuenta-estado").value = u ? u.estado : "activo";
  document.getElementById("cuenta-carrera-box").classList.toggle("hidden", tipo === "personal_limpieza");
  document.getElementById("cuenta-grupo-box").classList.toggle("hidden", tipo !== "alumno");
  document.getElementById("cuenta-pw-label").textContent = u ? "Nueva contraseña" : "Contraseña";
  document.getElementById("cuenta-pw-help").textContent = u
    ? (u.tiene_password ? "Déjela vacía para conservar la contraseña actual. Si la cambia, se cierran sus sesiones abiertas."
                        : "Aún no tiene contraseña: asígnele una para que pueda entrar a su portal.")
    : "Opcional: si la deja vacía, la persona no podrá entrar a su portal hasta que se le asigne una (alumnos y docentes también pueden activarla con su correo @itsoeh.edu.mx).";
  document.getElementById("cuenta-modal-submit").textContent = u ? "Guardar cambios" : `Crear ${perfil.nombre}`;
  await pintarSelectsCuenta(tipo, u ? u.carrera : "", u ? u.grupo_id : "");
  revisarPasswordsCuenta();
  document.querySelectorAll("#modal-cuenta .pw-ojo").forEach(b => verPasswordCuenta(b, true));  // siempre abre ocultas
  openModal("modal-cuenta");
}

// Aviso en vivo debajo de las contraseñas: si no coinciden (o son cortas) no deja guardar
function revisarPasswordsCuenta() {
  const p1 = document.getElementById("cuenta-password");
  const p2 = document.getElementById("cuenta-password2");
  const msg = document.getElementById("cuenta-pw-match");
  const a = p1.value, b = p2.value;
  let texto = "", ok = true;
  if (a && a.length < 8) { texto = `La contraseña es muy corta (${a.length} de 8 caracteres mínimo).`; ok = false; }
  else if (b && a !== b) { texto = "Las contraseñas no coinciden."; ok = false; }
  else if (a && !b) { texto = "Repita la contraseña para confirmarla."; ok = false; }
  else if (a && a === b) { texto = "✓ Las contraseñas coinciden."; }
  p2.setCustomValidity(ok ? "" : texto);
  [p1, p2].forEach(el => {
    el.classList.toggle("border-red-400", !ok && !!b);
    el.classList.toggle("border-slate-300", ok || !b);
  });
  msg.textContent = texto;
  msg.classList.toggle("hidden", !texto);
  msg.classList.toggle("text-red-600", !ok);
  msg.classList.toggle("text-emerald-600", ok);
  return ok;
}

// Ojito: muestra u oculta la contraseña de su campo
function verPasswordCuenta(btn, ocultar = false) {
  const input = document.getElementById(btn.dataset.input);
  const mostrar = !ocultar && input.type === "password";
  input.type = mostrar ? "text" : "password";
  const texto = mostrar ? "Ocultar contraseña" : "Mostrar contraseña";
  btn.title = texto;
  btn.setAttribute("aria-label", texto);
  btn.innerHTML = `<i data-lucide="${mostrar ? "eye-off" : "eye"}" class="w-4 h-4"></i>`;
  if (window.lucide) lucide.createIcons();
}

async function toggleCuenta(tipo, userId) {
  const u = CUENTAS[tipo].find(x => x.id === userId);
  if (!u) return;
  const activo = u.estado === "activo";
  const ok = await showConfirm(
    activo ? `¿Dar de baja a ${u.nombre_completo}?\n\nNo podrá entrar a su portal ni abrir puertas. Su historial se conserva y se puede reactivar.`
           : `¿Reactivar a ${u.nombre_completo}?`,
    { title: activo ? "Dar de baja" : "Reactivar", confirmText: activo ? "Dar de baja" : "Reactivar", danger: activo });
  if (!ok) return;
  try {
    if (activo) await apiFetch(`/api/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
    else await apiFetch(`/api/users/${encodeURIComponent(userId)}/reactivate`, { method: "POST" });
    loadCuentasData();
  } catch (err) {
    showAlert("No se pudo cambiar el estado: " + err.message, { type: "error" });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  ["cuenta-password", "cuenta-password2"].forEach(id =>
    document.getElementById(id)?.addEventListener("input", revisarPasswordsCuenta));

  document.getElementById("cuenta-carrera")?.addEventListener("change", (e) => {
    if (CUENTA_TIPO === "alumno") pintarGruposCuenta(e.target.value, document.getElementById("cuenta-grupo").value);
  });

  document.getElementById("form-cuenta")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pw = document.getElementById("cuenta-password").value;
    if (!revisarPasswordsCuenta()) {
      document.getElementById("cuenta-password2").focus();
      return;
    }
    const clave = document.getElementById("cuenta-clave").value.trim().toUpperCase();
    const u = CUENTA_EDITANDO;
    const body = {
      id: u ? u.id : clave,
      nombre_completo: document.getElementById("cuenta-nombre").value.trim(),
      tipo: CUENTA_TIPO,
      matricula_clave: clave,
      carrera: CUENTA_TIPO === "personal_limpieza" ? null : (document.getElementById("cuenta-carrera").value || null),
      grupo_id: CUENTA_TIPO === "alumno" ? (document.getElementById("cuenta-grupo").value || null) : null,
      estado: u ? document.getElementById("cuenta-estado").value : "activo",
      password: pw || null,
    };
    try {
      const res = u
        ? await apiFetch(`/api/users/${encodeURIComponent(u.id)}`, { method: "PUT", body })
        : await apiFetch("/api/users", { method: "POST", body });
      closeModal("modal-cuenta");
      showAlert(res.message, { type: "success" });
      loadCuentasData();
    } catch (err) {
      showAlert("No se pudo guardar: " + err.message, { type: "error" });
    }
  });
});
