/**
 * NeoAccess - Script Principal de Control y Enrutamiento (SPA) Multi-Rol
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\app.js
 */

const STATE = {
  token: localStorage.getItem("neoaccess_token") || null,
  user: JSON.parse(localStorage.getItem("neoaccess_user") || "null"),
  currentSection: "metrics",
  laboratorios: [],
  dispositivos: []
};

// -------------------------------------------------------------
// ESCAPADO DE HTML (anti-XSS)
// Todo dato que venga de la BD/API y se inserte con innerHTML debe pasar por esc().
// -------------------------------------------------------------
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Argumento seguro para handlers inline: onclick="fn(${escJsArg(x)})"
// Genera un literal de cadena JS válido y lo escapa para el atributo HTML.
function escJsArg(value) {
  return esc(JSON.stringify(value === null || value === undefined ? "" : String(value)));
}

// API Helper
async function apiFetch(endpoint, options = {}) {
  const headers = options.headers || {};
  if (STATE.token) {
    headers["Authorization"] = `Bearer ${STATE.token}`;
  }
  if (!(options.body instanceof FormData) && options.body && typeof options.body === "object") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  options.headers = headers;

  const res = await fetch(endpoint, options);
  if (res.status === 401) {
    logoutUser();
    throw new Error("Sesión no autorizada o expirada");
  }
  if (res.status === 503 && res.headers.get("X-NeoAccess-Mantenimiento")) {
    const data = await res.json().catch(() => ({}));
    showMaintenanceScreen(data.detail);
    throw new Error(data.detail || "Sistema en mantenimiento");
  }
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    const detalle = Array.isArray(errorData.detail)
      ? "Revise los datos: " + errorData.detail.map(d => (d.loc || []).slice(-1)[0] + " " + (d.msg || "")).join("; ")
      : errorData.detail;
    throw new Error(detalle || "Error en la petición al servidor");
  }
  return res.json();
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }
  checkAuth();
  setupNavigation();
  setupAuthEvents();
  setupGlobalEvents();
});

function checkAuth() {
  if (!STATE.token || !STATE.user) {
    // Si no hay sesión válida, limpiar DOM y redirigir inmediatamente al login puro
    document.body.innerHTML = "";
    const dest = window.location.protocol === "file:" ? "login.html" : "/login?t=" + Date.now();
    window.location.replace(dest);
    return;
  }

  const adminSidebar = document.getElementById("admin-sidebar");
  const portalTeacher = document.getElementById("portal-teacher-view");
  const portalStudent = document.getElementById("portal-student-view");
  const portalCleaning = document.getElementById("portal-cleaning-view");
  const adminContent = document.getElementById("admin-content-area");

  const adminUserDisplay = document.getElementById("admin-user-display");
  if (adminUserDisplay) adminUserDisplay.textContent = STATE.user.nombre;
  const userRoleBadge = document.getElementById("user-role-badge");
  if (userRoleBadge) userRoleBadge.textContent = (STATE.user.rol || "administrador").toUpperCase();

  const rol = STATE.user.rol || "administrador";

  // Ocultar todas las vistas de rol inicialmente
  if (portalTeacher) portalTeacher.classList.add("hidden");
  if (portalStudent) portalStudent.classList.add("hidden");
  if (portalCleaning) portalCleaning.classList.add("hidden");

  if (rol === "administrador") {
    if (adminSidebar) adminSidebar.classList.remove("hidden");
    if (adminContent) adminContent.classList.remove("hidden");
    loadInitialData();
  } else if (rol === "docente") {
    if (adminSidebar) adminSidebar.classList.add("hidden");
    if (adminContent) adminContent.classList.add("hidden");
    if (portalTeacher) portalTeacher.classList.remove("hidden");
    loadTeacherPortalView();
  } else if (rol === "alumno") {
    if (adminSidebar) adminSidebar.classList.add("hidden");
    if (adminContent) adminContent.classList.add("hidden");
    if (portalStudent) portalStudent.classList.remove("hidden");
    loadStudentPortalView();
  } else if (rol === "personal_limpieza") {
    if (adminSidebar) adminSidebar.classList.add("hidden");
    if (adminContent) adminContent.classList.add("hidden");
    if (portalCleaning) portalCleaning.classList.remove("hidden");
    loadCleaningPortalView();
  }

  if (window.lucide) lucide.createIcons();
}

function setupAuthEvents() {
  // Delegación de eventos global para TODOS los botones de cerrar sesión
  document.addEventListener("click", (e) => {
    const logoutBtn = e.target.closest(".btn-logout-action");
    if (logoutBtn) {
      e.preventDefault();
      logoutUser();
    }
  });
}

function logoutUser() {
  const token = STATE.token;
  if (token) {
    fetch("/api/auth/logout", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` }
    }).catch(() => {});
  }
  STATE.token = null;
  STATE.user = null;
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch (e) {}

  // 1. Borrar TODA la página del dashboard de golpe y pintar fondo negro sólido
  document.documentElement.style.backgroundColor = '#0f172a';
  document.documentElement.style.minHeight = '100vh';
  document.body.style.backgroundColor = '#0f172a';
  document.body.style.minHeight = '100vh';
  document.body.innerHTML = `
    <div style="min-height: 100vh; background-color: #0f172a; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-family: sans-serif; font-size: 14px;">
      <span>Cerrando sesión...</span>
    </div>
  `;

  // 2. Redirigir inmediatamente al login puro (con ?logout=1 para evitar redirección al dashboard)
  const dest = window.location.protocol === "file:" ? "login.html" : "/login?logout=1&t=" + Date.now();
  window.location.replace(dest);
}

// -------------------------------------------------------------
// VISTAS DE PORTALES POR ROL (Docente, Alumno, Limpieza)
// -------------------------------------------------------------
async function loadTeacherPortalView() {
  try {
    const data = await apiFetch("/api/portal/teacher-data");
    document.getElementById("docente-portal-name").textContent = data.perfil.nombre;
    document.getElementById("docente-portal-clave").textContent = data.perfil.matricula_clave;
    document.getElementById("docente-portal-carrera").textContent = data.perfil.carrera || "Sin carrera asignada";

    // Clases Asignadas
    const clasesTbody = document.getElementById("table-portal-teacher-classes");
    if (clasesTbody) {
      clasesTbody.innerHTML = data.clases_asignadas.map(c => `
        <tr class="hover:bg-slate-50 transition">
          <td class="px-4 py-3 font-semibold text-slate-900">${esc(c.dia_semana)}</td>
          <td class="px-4 py-3 font-mono text-xs font-bold text-slate-700">${esc(c.hora_inicio)} - ${esc(c.hora_fin)}</td>
          <td class="px-4 py-3 font-medium text-slate-800">${esc(c.materia)}</td>
          <td class="px-4 py-3"><span class="px-2 py-0.5 bg-slate-100 rounded text-xs font-bold">${esc(c.grupo_nombre || c.grupo_id)}</span></td>
          <td class="px-4 py-3 text-slate-700">${esc(c.laboratorio_nombre)} <span class="text-xs text-slate-400">(${esc(c.edificio)})</span></td>
        </tr>
      `).join("");
    }

    // Pase de Lista de Alumnos en Vivo (RF-06)
    const listadoTbody = document.getElementById("table-portal-teacher-attendance");
    if (listadoTbody) {
      if (data.pase_de_lista_alumnos.length === 0) {
        listadoTbody.innerHTML = `<tr><td colspan="5" class="p-6 text-center text-slate-400">Sin asistencias registradas recientemente</td></tr>`;
      } else {
        listadoTbody.innerHTML = data.pase_de_lista_alumnos.map(a => {
          const isOk = a.resultado === "permitido";
          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="px-4 py-2.5 font-mono text-xs text-slate-600">${esc(a.fecha_hora)}</td>
              <td class="px-4 py-2.5 font-bold text-slate-900">${esc(a.alumno_nombre)} <span class="block text-[11px] text-slate-400 font-mono">${esc(a.matricula_clave)}</span></td>
              <td class="px-4 py-2.5">${esc(a.grupo_nombre || 'N/A')}</td>
              <td class="px-4 py-2.5 text-slate-700">${esc(a.laboratorio_nombre)}</td>
              <td class="px-4 py-2.5">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${isOk ? 'badge-status-online' : 'badge-status-offline'}">
                  ${isOk ? 'Presente (Asistencia)' : 'Denegado'}
                </span>
              </td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch (err) {
    console.error("Error al cargar portal de docente:", err);
  }
}

async function loadStudentPortalView() {
  try {
    const data = await apiFetch("/api/portal/student-data");
    document.getElementById("alumno-portal-name").textContent = data.perfil.nombre;
    document.getElementById("alumno-portal-matricula").textContent = data.perfil.matricula_clave;
    document.getElementById("alumno-portal-grupo").textContent = data.perfil.grupo_nombre || data.perfil.grupo_id || "N/A";
    document.getElementById("alumno-portal-carrera").textContent = data.perfil.carrera || "Sin carrera asignada";

    const faceBadge = document.getElementById("alumno-portal-face-status");
    if (faceBadge) {
      faceBadge.innerHTML = data.tiene_rostro_registrado
        ? `<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-full text-xs font-semibold"><span class="status-dot online"></span> Vector Biométrico Activo (128-d)</span>`
        : `<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-50 text-amber-800 border border-amber-200 rounded-full text-xs font-semibold"><span class="status-dot intermittent"></span> Sin Vector Registrado</span>`;
    }

    // Horarios autorizados de clase
    const horariosTbody = document.getElementById("table-portal-student-schedules");
    if (horariosTbody) {
      horariosTbody.innerHTML = data.horarios_autorizados.map(h => `
        <tr class="hover:bg-slate-50 transition">
          <td class="px-4 py-3 font-semibold text-slate-900">${esc(h.dia_semana)}</td>
          <td class="px-4 py-3 font-mono text-xs font-bold text-slate-700">${esc(h.hora_inicio)} - ${esc(h.hora_fin)}</td>
          <td class="px-4 py-3 font-medium text-slate-800">${esc(h.materia)}</td>
          <td class="px-4 py-3 text-slate-700">${esc(h.laboratorio_nombre)} <span class="text-xs text-slate-400">(${esc(h.edificio)})</span></td>
          <td class="px-4 py-3 text-slate-600">${esc(h.docente_nombre || 'Docente Titular')}</td>
        </tr>
      `).join("");
    }

    // Historial de asistencias
    const histTbody = document.getElementById("table-portal-student-history");
    if (histTbody) {
      if (data.historial_asistencias.length === 0) {
        histTbody.innerHTML = `<tr><td colspan="4" class="p-6 text-center text-slate-400">Sin accesos registrados aún</td></tr>`;
      } else {
        histTbody.innerHTML = data.historial_asistencias.map(a => {
          const isOk = a.resultado === "permitido";
          return `
            <tr class="hover:bg-slate-50 transition">
              <td class="px-4 py-2.5 font-mono text-xs text-slate-600">${esc(a.fecha_hora)}</td>
              <td class="px-4 py-2.5 font-medium text-slate-800">${esc(a.laboratorio_nombre)}</td>
              <td class="px-4 py-2.5">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${isOk ? 'badge-status-online' : 'badge-status-offline'}">
                  ${isOk ? 'Pase de Lista Válido' : 'Acceso Denegado'}
                </span>
              </td>
              <td class="px-4 py-2.5 text-xs text-slate-500">${esc(a.motivo)}</td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch (err) {
    console.error("Error al cargar portal de alumno:", err);
  }
}

async function loadCleaningPortalView() {
  try {
    const data = await apiFetch("/api/portal/cleaning-data");
    document.getElementById("limpieza-portal-name").textContent = data.perfil.nombre;
    document.getElementById("limpieza-portal-clave").textContent = data.perfil.matricula_clave;

    const bitacoraTbody = document.getElementById("table-portal-cleaning-logs");
    if (bitacoraTbody) {
      bitacoraTbody.innerHTML = data.bitacora.map(b => {
        const isEnCurso = !b.hora_salida;
        return `
          <tr class="hover:bg-slate-50 transition">
            <td class="px-4 py-3 font-medium text-slate-900">${esc(b.laboratorio_nombre)} <span class="text-xs text-slate-400">(${esc(b.edificio)})</span></td>
            <td class="px-4 py-3 font-mono text-xs">${esc(b.hora_entrada)}</td>
            <td class="px-4 py-3 font-mono text-xs">${b.hora_salida ? esc(b.hora_salida) : '<em>En progreso...</em>'}</td>
            <td class="px-4 py-3">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${isEnCurso ? 'badge-status-intermittent' : 'badge-status-online'}">
                ${isEnCurso ? 'Aseo en Progreso' : 'Turno Completado'}
              </span>
            </td>
          </tr>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Error al cargar portal de limpieza:", err);
  }
}

// -------------------------------------------------------------
// CONTROL DE NAVEGACIÓN ADMINISTRATIVA (Sección 9)
// -------------------------------------------------------------
function setupNavigation() {
  const navBtns = document.querySelectorAll(".nav-btn");
  navBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const section = btn.getAttribute("data-section");
      switchSection(section);
      document.body.classList.remove("sidebar-open"); // cerrar menú en celular
    });
  });

  // Modo mantenimiento
  document.getElementById("btn-open-maintenance")?.addEventListener("click", openMaintenanceModal);
  document.getElementById("btn-maintenance-toggle")?.addEventListener("click", () => setMaintenance(!STATE.mantenimiento.activo));
  document.getElementById("btn-maintenance-off-banner")?.addEventListener("click", () => setMaintenance(false));

  // Menú deslizable en la versión móvil
  document.getElementById("btn-mobile-menu")?.addEventListener("click", () => {
    document.body.classList.toggle("sidebar-open");
  });
  document.getElementById("sidebar-backdrop")?.addEventListener("click", () => {
    document.body.classList.remove("sidebar-open");
  });
}

function switchSection(sectionId) {
  STATE.currentSection = sectionId;
  const sections = ["metrics", "devices", "laboratories", "schedules", "students", "teachers", "reports", "admins"];

  sections.forEach(s => {
    const secEl = document.getElementById(`section-${s}`);
    if (secEl) {
      if (s === sectionId) {
        secEl.classList.remove("hidden");
        secEl.classList.add("fade-in");
      } else {
        secEl.classList.add("hidden");
      }
    }
  });

  document.querySelectorAll(".nav-btn").forEach(btn => {
    const target = btn.getAttribute("data-section");
    if (target === sectionId) {
      btn.classList.add("bg-slate-800", "text-white");
      btn.classList.remove("text-slate-300");
    } else {
      btn.classList.remove("bg-slate-800", "text-white");
      btn.classList.add("text-slate-300");
    }
  });

  const titles = {
    metrics: { title: "Métricas y Resumen General", sub: "Panel de Monitoreo" },
    devices: { title: "Dispositivos y Puertas", sub: "Hardware Raspberry Pi Zero W" },
    laboratories: { title: "Gestión de Laboratorios", sub: "Edificio 6 y STEM" },
    schedules: { title: "Horarios y Grupos", sub: "Validación de Acceso" },
    students: { title: "Control de Alumnos", sub: "Pase de Lista Digital" },
    teachers: { title: "Maestros y Personal", sub: "Docencia y Limpieza" },
    reports: { title: "Generación de Reportes", sub: "Descarga de Evidencias" },
    admins: { title: "Administradores", sub: "Cuentas con acceso al Dashboard" }
  };
  if (titles[sectionId]) {
    document.getElementById("page-title").textContent = titles[sectionId].title;
    document.getElementById("page-subtitle").textContent = titles[sectionId].sub;
  }

  refreshActiveSection();
}

function refreshActiveSection() {
  if (STATE.currentSection === "metrics") loadMetricsData();
  else if (STATE.currentSection === "devices") loadDevicesData();
  else if (STATE.currentSection === "laboratories") loadLaboratoriesData();
  else if (STATE.currentSection === "schedules") loadSchedulesData();
  else if (STATE.currentSection === "students") loadStudentsData();
  else if (STATE.currentSection === "teachers") loadTeachersData();
  else if (STATE.currentSection === "reports") loadReportsDropdowns();
  else if (STATE.currentSection === "admins") loadAdminsData();
}

// -------------------------------------------------------------
// MODO MANTENIMIENTO GLOBAL
// -------------------------------------------------------------
STATE.mantenimiento = { activo: false, mensaje: "" };

function showMaintenanceScreen(mensaje) {
  const screen = document.getElementById("maintenance-screen");
  if (!screen) return;
  document.getElementById("maintenance-screen-text").textContent =
    mensaje || "El sistema está en mantenimiento. Intente más tarde.";
  screen.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

function renderMaintenanceState() {
  const m = STATE.mantenimiento;
  const chip = document.getElementById("maintenance-chip");
  if (chip) {
    chip.textContent = m.activo ? "ON" : "OFF";
    chip.className = "text-[10px] font-bold px-1.5 py-0.5 rounded " +
      (m.activo ? "bg-amber-500 text-white" : "bg-slate-800 text-slate-400");
  }
  const banner = document.getElementById("maintenance-banner");
  if (banner) {
    banner.classList.toggle("hidden", !m.activo);
    banner.classList.toggle("flex", m.activo);
    const desde = m.desde ? ` (desde ${m.desde}${m.por ? ", " + m.por : ""})` : "";
    document.getElementById("maintenance-banner-text").textContent =
      `Solo los administradores pueden entrar${desde}. Mensaje: "${m.mensaje}"`;
  }
  const stateEl = document.getElementById("maintenance-modal-state");
  if (stateEl) {
    stateEl.textContent = m.activo ? "Estado: ACTIVADO" : "Estado: desactivado";
    stateEl.className = "text-xs " + (m.activo ? "text-amber-700 font-bold" : "text-slate-500");
  }
  const btn = document.getElementById("btn-maintenance-toggle");
  if (btn) {
    btn.textContent = m.activo ? "Desactivar mantenimiento" : "Activar mantenimiento";
    btn.className = "px-4 py-1.5 text-white text-xs font-semibold rounded-lg " +
      (m.activo ? "bg-emerald-600 hover:bg-emerald-700" : "bg-amber-600 hover:bg-amber-700");
  }
}

async function loadMaintenanceState() {
  try {
    STATE.mantenimiento = await apiFetch("/api/system/maintenance");
    renderMaintenanceState();
  } catch (err) {
    console.error("Error al consultar modo mantenimiento:", err);
  }
}

function openMaintenanceModal() {
  document.getElementById("maintenance-message").value = STATE.mantenimiento.mensaje || "";
  renderMaintenanceState();
  openModal("modal-maintenance");
}

async function setMaintenance(activo) {
  const mensaje = document.getElementById("maintenance-message")?.value.trim() || STATE.mantenimiento.mensaje;
  const pregunta = activo
    ? "¿Activar el modo mantenimiento?\n\nAlumnos, docentes y limpieza no podrán usar la plataforma hasta que lo desactives. Las puertas siguen funcionando."
    : "¿Desactivar el modo mantenimiento? Todos los usuarios podrán volver a entrar.";
  if (!(await showConfirm(pregunta, { title: "Modo mantenimiento", confirmText: activo ? "Activar" : "Desactivar", danger: activo }))) return;
  try {
    STATE.mantenimiento = await apiFetch("/api/system/maintenance", { method: "POST", body: { activo, mensaje } });
    renderMaintenanceState();
    closeModal("modal-maintenance");
  } catch (err) {
    showAlert("No se pudo cambiar el modo mantenimiento: " + err.message);
  }
}

async function loadInitialData() {
  loadMaintenanceState();
  try {
    const labs = await apiFetch("/api/labs");
    STATE.laboratorios = labs;
    populateLabDropdowns(labs);
    switchSection("metrics");
    updateGlobalDeviceStatus();
  } catch (err) {
    console.error("Error al cargar datos iniciales:", err);
  }
}

function populateLabDropdowns(labs) {
  const selects = [
    document.getElementById("filter-metrics-lab"),
    document.getElementById("dev-new-lab"),
    document.getElementById("filter-schedule-lab"),
    document.getElementById("schedule-new-lab"),
    document.getElementById("report-filter-lab")
  ];

  selects.forEach(sel => {
    if (!sel) return;
    const currentVal = sel.value;
    const isFilter = sel.id.startsWith("filter") || sel.id.startsWith("report");
    sel.innerHTML = isFilter ? '<option value="todos">Todos los laboratorios</option>' : '<option value="">Seleccione laboratorio...</option>';
    labs.forEach(l => {
      const opt = document.createElement("option");
      opt.value = l.id;
      opt.textContent = `${l.nombre} (${l.edificio})`;
      sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
  });
}

async function updateGlobalDeviceStatus() {
  try {
    const devices = await apiFetch("/api/devices");
    STATE.dispositivos = devices;
    let online = 0, intermittent = 0, offline = 0;
    devices.forEach(d => {
      if (d.estado === "en_linea") online++;
      else if (d.estado === "intermitente") intermittent++;
      else offline++;
    });
    document.getElementById("pill-online").textContent = online;
    document.getElementById("pill-intermittent").textContent = intermittent;
    document.getElementById("pill-offline").textContent = offline;
  } catch (err) {
    console.error("Error actualizando dispositivos:", err);
  }
}

function setupGlobalEvents() {
  // ── Intervalo RÁPIDO: tabla de accesos recientes en tiempo real (cada 1 seg) ──────
  // Una sola petición ligera de 6ms → actualización instantánea tras simular
  setInterval(() => {
    if (STATE.token && STATE.user && STATE.user.rol === 'administrador') {
      if (STATE.currentSection === 'metrics') {
        refreshRecentAccesses();   // actualiza tabla y KPIs al instante
      }
    }
  }, 1000);

  // ── Intervalo NORMAL: KPIs + gráficas completas (cada 10 seg) ───────────
  setInterval(() => {
    if (STATE.token && STATE.user && STATE.user.rol === 'administrador') {
      if (STATE.currentSection === 'metrics') {
        loadMetricsData();         // refresco completo con gráficas y KPIs
      } else if (STATE.currentSection === 'devices') {
        loadDevicesData();
      }
      updateGlobalDeviceStatus();
    }
  }, 10000);

  document.getElementById("btn-refresh")?.addEventListener("click", () => {
    refreshActiveSection();
    updateGlobalDeviceStatus();
  });
}

window.openModal = function(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove("hidden");
    if (window.lucide) lucide.createIcons();
  }
};

window.closeModal = function(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("hidden");
  if (id === "modal-face-capture") {
    const video = document.getElementById("webcam-preview");
    if (video && video.srcObject) {
      video.srcObject.getTracks().forEach(track => track.stop());
      video.srcObject = null;
    }
    if (typeof clearPhonePhotos === "function") clearPhonePhotos(); // RF-07
  }
};
