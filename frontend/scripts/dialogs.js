// ─────────────────────────────────────────────────────────────
// Diálogos propios de NeoAccess (reemplazan alert/confirm del navegador).
// Las ventanas nativas muestran "localhost:8000 dice", se ven distinto en
// cada celular y algunos navegadores móviles las bloquean. Estas se ven
// igual en PC y en móvil.
//
//   await showAlert("Mensaje", { type: "success" | "error" | "info", title });
//   if (!(await showConfirm("¿Seguro?", { danger: true, confirmText: "Eliminar" }))) return;
// ─────────────────────────────────────────────────────────────
(function () {
  const ICONOS = {
    info:    { color: "#2563eb", bg: "#dbeafe", svg: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>' },
    success: { color: "#059669", bg: "#d1fae5", svg: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>' },
    error:   { color: "#dc2626", bg: "#fee2e2", svg: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>' },
    warning: { color: "#d97706", bg: "#fef3c7", svg: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>' },
    question:{ color: "#0369a1", bg: "#e0f2fe", svg: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>' },
  };
  const TITULOS = { info: "Aviso", success: "Listo", error: "Ocurrió un problema", warning: "Atención", question: "Confirmar" };

  const cola = [];
  let abierto = false;

  function escapar(t) {
    const d = document.createElement("div");
    d.textContent = String(t ?? "");
    return d.innerHTML;
  }

  // Detecta el tipo a partir del texto cuando no se indica (✓ / Error ...)
  function tipoPorTexto(msg) {
    const m = String(msg || "").trim().toLowerCase();
    if (m.startsWith("✓")) return "success";
    if (m.startsWith("✗") || m.startsWith("error") || m.startsWith("no se pudo")) return "error";
    return "info";
  }

  function mostrar(op) {
    return new Promise(resolve => {
      cola.push({ ...op, resolve });
      if (!abierto) siguiente();
    });
  }

  function siguiente() {
    const op = cola.shift();
    if (!op) { abierto = false; return; }
    abierto = true;

    const tipo = op.type || (op.confirm ? (op.danger ? "warning" : "question") : tipoPorTexto(op.message));
    const icono = ICONOS[tipo] || ICONOS.info;
    const titulo = op.title || TITULOS[tipo];
    const mensaje = String(op.message ?? "").replace(/^[✓✗]\s*/, "");
    const textoOk = op.confirmText || (op.confirm ? "Aceptar" : "Entendido");
    const textoCancel = op.cancelText || "Cancelar";

    const previo = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "na-dialog-overlay";
    overlay.setAttribute("role", op.confirm ? "alertdialog" : "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML = `
      <div class="na-dialog" role="document" aria-labelledby="na-dialog-title" aria-describedby="na-dialog-msg">
        <div class="na-dialog-body">
          <div class="na-dialog-icon" style="background:${icono.bg};color:${icono.color}">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icono.svg}</svg>
          </div>
          <div class="na-dialog-text">
            <h3 id="na-dialog-title">${escapar(titulo)}</h3>
            <p id="na-dialog-msg">${escapar(mensaje)}</p>
          </div>
        </div>
        <div class="na-dialog-actions">
          ${op.confirm ? `<button type="button" class="na-btn na-btn-secondary" data-r="0">${escapar(textoCancel)}</button>` : ""}
          <button type="button" class="na-btn ${op.danger ? "na-btn-danger" : "na-btn-primary"}" data-r="1">${escapar(textoOk)}</button>
        </div>
      </div>`;

    function cerrar(valor) {
      document.removeEventListener("keydown", teclas, true);
      overlay.classList.add("na-dialog-closing");
      setTimeout(() => {
        overlay.remove();
        if (previo && typeof previo.focus === "function") { try { previo.focus(); } catch (_) {} }
        op.resolve(op.confirm ? valor : undefined);
        siguiente();
      }, 120);
    }

    function teclas(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); cerrar(false); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); cerrar(true); }
      else if (e.key === "Tab") {
        // Mantener el foco dentro del diálogo
        const btns = [...overlay.querySelectorAll("button")];
        const i = btns.indexOf(document.activeElement);
        e.preventDefault();
        btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
      }
    }

    overlay.addEventListener("click", e => {
      const b = e.target.closest("button[data-r]");
      if (b) cerrar(b.dataset.r === "1");
      else if (e.target === overlay && !op.confirm) cerrar(true); // tocar fuera cierra solo los avisos
    });
    document.addEventListener("keydown", teclas, true);
    document.body.appendChild(overlay);
    overlay.querySelector('button[data-r="1"]').focus();
  }

  window.showAlert = (message, opciones = {}) => mostrar({ ...opciones, message, confirm: false });
  window.showConfirm = (message, opciones = {}) => mostrar({ ...opciones, message, confirm: true });
})();
