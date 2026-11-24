/**
 * NeoAccess - Módulo de Usuarios (Alumnos, Docentes y Limpieza)
 * Ubicación: C:\Users\gr321\Desktop\NeoAccess\frontend\scripts\users.js
 * Cumple con RF-07 (Sin fotos guardadas), RF-14, RF-15 (Metadatos faciales 128-d) y RF-16 (Detalle e Historial)
 */

let activeCapturingUserId = null;
let activeCapturingUserName = null;

async function loadStudentsData() {
  const searchQuery = document.getElementById("search-student")?.value.trim() || "";
  try {
    const params = new URLSearchParams({ tipo: "alumno" });
    if (searchQuery) params.append("q", searchQuery);

    const students = await apiFetch(`/api/users?${params.toString()}`);
    renderStudentsTable(students);
  } catch (err) {
    console.error("Error al cargar alumnos:", err);
  }
}

function renderStudentsTable(students) {
  const tbody = document.getElementById("table-students");
  if (!tbody) return;

  if (students.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="p-6 text-center text-slate-400">No se encontraron alumnos</td></tr>`;
    return;
  }

  tbody.innerHTML = students.map(u => {
    const isActivo = u.estado === "activo";
    const hasFace = u.tiene_rostro === 1;

    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-mono font-bold text-slate-900">${esc(u.matricula_clave)}</td>
        <td class="px-4 py-3 font-medium text-slate-900">${esc(u.nombre_completo)}</td>
        <td class="px-4 py-3 text-slate-600">${esc(u.carrera || 'ITSOEH')}</td>
        <td class="px-4 py-3">
          <span class="px-2 py-0.5 bg-slate-100 text-slate-800 rounded font-semibold text-[11px]">
            ${esc(u.grupo_nombre || u.grupo_id || 'N/A')}
          </span>
        </td>
        <td class="px-4 py-3">
          ${hasFace ? `
            <span class="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
              <span class="status-dot online"></span> Vector 128-d listo
            </span>
          ` : `
            <span class="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
              <span class="status-dot intermittent"></span> Sin registrar
            </span>
          `}
        </td>
        <td class="px-4 py-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${isActivo ? 'bg-slate-100 text-slate-800' : 'bg-red-50 text-red-700'}">
            ${isActivo ? 'Activo' : 'Baja'}
          </span>
        </td>
        <td class="px-4 py-3 text-right space-x-1">
          <button onclick="openFaceCaptureModal(${escJsArg(u.id)}, ${escJsArg(u.nombre_completo)})"
            class="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition" title="Registrar Rostro (Metadatos Vectoriales)">
            <i data-lucide="scan-face" class="w-4 h-4"></i>
          </button>

          <button onclick="viewUserDetails(${escJsArg(u.id)})"
            class="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition" title="Ver Detalle e Historial de Accesos">
            <i data-lucide="eye" class="w-4 h-4"></i>
          </button>

          <button onclick="toggleUserStatus(${escJsArg(u.id)})"
            class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-slate-100 rounded transition" title="Dar de baja">
            <i data-lucide="user-x" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

async function loadTeachersData() {
  try {
    const docentes = await apiFetch("/api/users?tipo=docente");
    renderDocentesTable(docentes);

    const limpiezas = await apiFetch("/api/reports/cleaning");
    renderLimpiezaTable(limpiezas);
  } catch (err) {
    console.error("Error al cargar docentes y personal:", err);
  }
}

function renderDocentesTable(docentes) {
  const tbody = document.getElementById("table-docentes");
  if (!tbody) return;

  tbody.innerHTML = docentes.map(d => {
    const isActivo = d.estado === "activo";
    const hasFace = d.tiene_rostro === 1;

    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-mono font-bold text-slate-900">${esc(d.matricula_clave)}</td>
        <td class="px-4 py-3 font-medium text-slate-900">${esc(d.nombre_completo)}</td>
        <td class="px-4 py-3 text-slate-600">${esc(d.carrera || 'Área Académica')}</td>
        <td class="px-4 py-3">
          ${hasFace ? `
            <span class="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
              <span class="status-dot online"></span> Vector 128-d listo
            </span>
          ` : `
            <span class="inline-flex items-center gap-1 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full font-medium">
              <span class="status-dot intermittent"></span> Sin registrar
            </span>
          `}
        </td>
        <td class="px-4 py-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${isActivo ? 'bg-slate-100 text-slate-800' : 'bg-red-50 text-red-700'}">
            ${isActivo ? 'Activo' : 'Baja'}
          </span>
        </td>
        <td class="px-4 py-3 text-right space-x-1">
          <button onclick="openFaceCaptureModal(${escJsArg(d.id)}, ${escJsArg(d.nombre_completo)})"
            class="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition" title="Registrar Rostro">
            <i data-lucide="scan-face" class="w-4 h-4"></i>
          </button>
          <button onclick="viewUserDetails(${escJsArg(d.id)})"
            class="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition" title="Ver Detalle e Historial">
            <i data-lucide="eye" class="w-4 h-4"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");

  if (window.lucide) lucide.createIcons();
}

function renderLimpiezaTable(limpiezas) {
  const tbody = document.getElementById("table-limpieza");
  if (!tbody) return;

  if (limpiezas.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-slate-400">Sin bitácoras de limpieza registradas</td></tr>`;
    return;
  }

  tbody.innerHTML = limpiezas.map(l => {
    const isEnCurso = !l.hora_salida;
    return `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-4 py-3 font-medium text-slate-900">${esc(l.personal_nombre)} (${esc(l.personal_clave)})</td>
        <td class="px-4 py-3 text-slate-700">${esc(l.laboratorio_nombre)} <span class="text-slate-400">(${esc(l.edificio)})</span></td>
        <td class="px-4 py-3 font-mono text-[11px]">${esc(l.hora_entrada)}</td>
        <td class="px-4 py-3 font-mono text-[11px] text-slate-600">${l.hora_salida ? esc(l.hora_salida) : '<em>En curso...</em>'}</td>
        <td class="px-4 py-3">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${isEnCurso ? 'badge-status-intermittent' : 'badge-status-online'}">
            ${isEnCurso ? 'En Progreso' : 'Completada'}
          </span>
        </td>
      </tr>
    `;
  }).join("");
}

async function viewUserDetails(userId) {
  try {
    const res = await apiFetch(`/api/users/${userId}/details`);
    const u = res.usuario;
    const history = res.historial;

    document.getElementById("user-details-name").textContent = u.nombre_completo;
    document.getElementById("user-details-badge").textContent = `${u.tipo.toUpperCase()} • ${u.grupo_nombre || u.carrera || 'ITSOEH'}`;
    document.getElementById("user-details-clave").textContent = u.matricula_clave;
    document.getElementById("user-details-carrera").textContent = u.carrera || 'General';
    document.getElementById("user-details-rostro-info").textContent = u.fecha_rostro ? `Vector 128-d (${u.fecha_rostro})` : 'Sin vector';

    const tbody = document.getElementById("user-details-history-table");
    if (history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-slate-400">Sin historial de accesos</td></tr>`;
    } else {
      tbody.innerHTML = history.map(h => {
        const isOk = h.resultado === "permitido";
        return `
          <tr class="hover:bg-slate-50 transition">
            <td class="px-3 py-2 font-mono text-[11px]">${esc(h.fecha_hora)}</td>
            <td class="px-3 py-2 font-medium">${esc(h.laboratorio_nombre || h.laboratorio_id)}</td>
            <td class="px-3 py-2">
              <span class="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold ${isOk ? 'badge-status-online' : 'badge-status-offline'}">
                ${isOk ? 'Permitido' : 'Denegado'}
              </span>
            </td>
            <td class="px-3 py-2 text-slate-500 text-[11px]">${esc(h.motivo)}</td>
          </tr>
        `;
      }).join("");
    }

    openModal("modal-user-details");
  } catch (err) {
    alert("Error al obtener detalle del usuario: " + err.message);
  }
}

async function toggleUserStatus(userId) {
  if (!confirm("¿Está seguro de dar de baja a este usuario?")) return;
  try {
    await apiFetch(`/api/users/${userId}`, { method: "DELETE" });
    loadStudentsData();
  } catch (err) {
    alert("Error al dar de baja: " + err.message);
  }
}

function openFaceCaptureModal(userId, userName) {
  activeCapturingUserId = userId;
  activeCapturingUserName = userName;

  document.getElementById("modal-face-user-name").textContent = `Usuario: ${userName} (ID: ${userId})`;
  const statusEl = document.getElementById("vector-status");
  statusEl.classList.add("hidden");
  statusEl.textContent = "";

  openModal("modal-face-capture");
}

async function startWebcam() {
  const video = document.getElementById("webcam-preview");
  const placeholder = document.getElementById("camera-placeholder");

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 360 } });
    video.srcObject = stream;
    video.classList.remove("hidden");
    placeholder.classList.add("hidden");
  } catch (err) {
    alert("No se pudo acceder a la cámara web. Verifique permisos del navegador (se requiere http://localhost o HTTPS).");
  }
}

// Captura N fotogramas de la webcam como JPEG en base64 (solo en memoria)
async function captureWebcamFrames(count = 3, delayMs = 350) {
  const video = document.getElementById("webcam-preview");
  const canvas = document.getElementById("face-canvas");
  if (!video || !video.srcObject || video.readyState < 2) return null;

  canvas.width = video.videoWidth || 480;
  canvas.height = video.videoHeight || 360;
  const ctx = canvas.getContext("2d");
  const frames = [];
  for (let i = 0; i < count; i++) {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    frames.push(canvas.toDataURL("image/jpeg", 0.9));
    if (i < count - 1) await new Promise(r => setTimeout(r, delayMs));
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height); // RF-07: no dejar la imagen en el canvas
  return frames;
}

async function extractAndSaveVector() {
  if (!activeCapturingUserId) return;

  const statusEl = document.getElementById("vector-status");
  const btn = document.getElementById("btn-capture-and-extract");
  statusEl.classList.remove("hidden");

  const frames = await captureWebcamFrames();
  if (!frames) {
    statusEl.textContent = "Primero active la cámara y espere a que se vea su rostro.";
    return;
  }

  statusEl.textContent = "Analizando rostro en el servidor (vector 128-d, YuNet + SFace)...";
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch(`/api/users/${encodeURIComponent(activeCapturingUserId)}/facial-capture`, {
      method: "POST",
      body: { imagenes: frames }
    });
    frames.length = 0; // RF-07: descartar fotogramas en el navegador

    statusEl.innerHTML = `
      <span class="text-emerald-700 font-bold">✓ ${esc(res.message)}</span><br>
      <span class="text-[10px] text-slate-500">Calidad de detección: ${esc(res.calidad_muestra)} • Privacidad (RF-07): las fotos no se guardan.</span>
    `;

    setTimeout(() => {
      closeModal("modal-face-capture");
      loadStudentsData();
      loadTeachersData();
    }, 1800);

  } catch (err) {
    statusEl.textContent = "No se pudo registrar el rostro: " + err.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("search-student")?.addEventListener("input", () => {
    loadStudentsData();
  });

  document.getElementById("btn-start-camera")?.addEventListener("click", () => {
    startWebcam();
  });

  document.getElementById("btn-capture-and-extract")?.addEventListener("click", () => {
    extractAndSaveVector();
  });

  // Modal para agregar alumno
  document.getElementById("btn-modal-add-student")?.addEventListener("click", () => {
    openModal("modal-add-student");
  });

  document.getElementById("form-add-student")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      id: document.getElementById("student-new-id").value.trim().toUpperCase(),
      nombre_completo: document.getElementById("student-new-name").value.trim(),
      matricula_clave: document.getElementById("student-new-matricula").value.trim(),
      carrera: document.getElementById("student-new-career").value.trim(),
      grupo_id: document.getElementById("student-new-group").value.trim().toUpperCase(),
      tipo: "alumno",
      estado: "activo"
    };

    try {
      await apiFetch("/api/users", {
        method: "POST",
        body: payload
      });
      closeModal("modal-add-student");
      document.getElementById("form-add-student").reset();
      loadStudentsData();
    } catch (err) {
      alert("Error al registrar alumno: " + err.message);
    }
  });

  const tabDoc = document.getElementById("tab-docentes");
  const tabLim = document.getElementById("tab-limpieza");
  const cDoc = document.getElementById("container-docentes");
  const cLim = document.getElementById("container-limpieza");

  tabDoc?.addEventListener("click", () => {
    tabDoc.classList.add("text-slate-900", "border-b-2", "border-slate-900");
    tabDoc.classList.remove("text-slate-400");
    tabLim.classList.remove("text-slate-900", "border-b-2", "border-slate-900");
    tabLim.classList.add("text-slate-400");
    cDoc.classList.remove("hidden");
    cLim.classList.add("hidden");
  });

  tabLim?.addEventListener("click", () => {
    tabLim.classList.add("text-slate-900", "border-b-2", "border-slate-900");
    tabLim.classList.remove("text-slate-400");
    tabDoc.classList.remove("text-slate-900", "border-b-2", "border-slate-900");
    tabDoc.classList.add("text-slate-400");
    cLim.classList.remove("hidden");
    cDoc.classList.add("hidden");
  });
});
