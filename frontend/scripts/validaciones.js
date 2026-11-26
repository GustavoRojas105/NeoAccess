/*
 * NeoAccess - Validación de nombres y matrículas en los formularios.
 * Mismas reglas que backend/validaciones.py (el servidor las vuelve a revisar).
 *
 *   <input data-valida="nombre">                      -> se escribe en MAYÚSCULAS, solo letras
 *   <input data-valida="matricula" data-tipo="alumno"> -> 8 o 9 números (19011044, 230110427)
 *   <input data-valida="matricula" data-tipo-de="id-del-select"> -> toma el tipo de ese select
 *   Docente: número de empleado de RH, solo números (3 a 10). Personal: clave como LIM-01.
 *   data-actual="..." -> la clave que ya tenía (docentes antiguos tipo DOC-ISC-01) se respeta.
 */
(function () {
  const NOMBRE_RE = /^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ .'-]{2,119}$/;
  const MATRICULA_RE = /^\d{8,9}$/;
  const CLAVE_RE = /^[A-Z0-9-]{3,20}$/;
  const EMPLEADO_RE = /^\d{3,10}$/;

  function tipoDe(el) {
    if (el.dataset.tipoDe) {
      const sel = document.getElementById(el.dataset.tipoDe);
      if (sel) return sel.value;
    }
    return el.dataset.tipo || "alumno";
  }

  function conCursor(el, nuevo) {
    if (el.value === nuevo) return;
    const fin = el.value.length - (el.selectionEnd ?? el.value.length);
    el.value = nuevo;
    try { const p = Math.max(0, nuevo.length - fin); el.setSelectionRange(p, p); } catch (e) { /* sin cursor */ }
  }

  function revisar(el) {
    const regla = el.dataset.valida;
    let mensaje = "";
    if (regla === "nombre") {
      el.maxLength = 120;
      el.autocapitalize = "characters";
      conCursor(el, el.value.toUpperCase().replace(/\s{2,}/g, " ").replace(/^\s+/, ""));
      const v = el.value.trim();
      if (v && !NOMBRE_RE.test(v)) {
        mensaje = v.length < 3 ? "El nombre debe tener al menos 3 letras."
          : "El nombre solo puede tener letras y espacios (también acentos, ñ, punto, guion y apóstrofo).";
      }
    } else if (regla === "matricula") {
      const actual = (el.dataset.actual || "").toUpperCase();
      if (actual && el.value.trim().toUpperCase() === actual) {
        el.maxLength = 40;
        mensaje = "";
      } else if (tipoDe(el) === "docente") {
        el.maxLength = 10;
        el.inputMode = "numeric";
        el.placeholder = "Número de empleado (RH)";
        conCursor(el, el.value.replace(/\D/g, "").slice(0, 10));
        if (el.value && !EMPLEADO_RE.test(el.value)) mensaje = "El número de empleado debe tener de 3 a 10 números (es el que asigna Recursos Humanos).";
      } else if (tipoDe(el) === "alumno") {
        el.maxLength = 9;
        el.inputMode = "numeric";
        el.placeholder = "Ej: 230110427";
        conCursor(el, el.value.replace(/\D/g, "").slice(0, 9));
        if (el.value && !MATRICULA_RE.test(el.value)) mensaje = "La matrícula debe tener 8 o 9 números (p. ej. 19011044 o 230110427).";
      } else {
        el.maxLength = 20;
        el.inputMode = "text";
        el.placeholder = "Ej: LIM-01";
        conCursor(el, el.value.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 20));
        if (el.value && !CLAVE_RE.test(el.value)) mensaje = "La clave debe tener de 3 a 20 letras, números o guiones (p. ej. LIM-01).";
      }
    }
    el.removeAttribute("pattern");
    el.removeAttribute("minlength");
    el.setCustomValidity(mensaje);
    return !mensaje;
  }

  // Para cuando un script llena o cambia el tipo del campo (p. ej. al abrir un modal).
  window.revisarCampo = revisar;

  document.addEventListener("input", (e) => {
    if (e.target.matches && e.target.matches("[data-valida]")) revisar(e.target);
  }, true);

  // Si cambia el select del tipo (alumno / docente), se ajusta el campo de la matrícula.
  document.addEventListener("change", (e) => {
    if (!e.target.id) return;
    document.querySelectorAll(`[data-valida][data-tipo-de="${e.target.id}"]`).forEach(revisar);
  }, true);

  // Antes de enviar: revisar todos (también los que llenó un script) y avisar del primero mal.
  document.addEventListener("submit", (e) => {
    const campos = [...e.target.querySelectorAll("[data-valida]")].filter(el => !el.disabled && el.offsetParent !== null);
    const malos = campos.filter(el => !revisar(el));
    if (malos.length) {
      e.preventDefault();
      e.stopImmediatePropagation();
      malos[0].reportValidity();
    }
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-valida]").forEach(revisar);
  });
})();
