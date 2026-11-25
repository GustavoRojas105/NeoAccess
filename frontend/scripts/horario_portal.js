// ─────────────────────────────────────────────────────────────
// Horario semanal "bonito" para los portales de alumno y docente
// + estado de acceso de hoy que se actualiza solo (con la hora del servidor)
// ─────────────────────────────────────────────────────────────

const HP_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
const HP_DIAS_JS = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
const HP_COLORES = [
  "bg-sky-50 border-sky-300 text-sky-900",
  "bg-emerald-50 border-emerald-300 text-emerald-900",
  "bg-violet-50 border-violet-300 text-violet-900",
  "bg-amber-50 border-amber-300 text-amber-900",
  "bg-rose-50 border-rose-300 text-rose-900",
  "bg-teal-50 border-teal-300 text-teal-900",
  "bg-indigo-50 border-indigo-300 text-indigo-900",
  "bg-lime-50 border-lime-300 text-lime-900",
];
const HP_PX_HORA = 56;                 // alto de una hora en la cuadrícula
const HP_ESTADO = {};                  // por contenedor: { clases, offsetMs, tolerancia, opts }
let HP_TIMER = null;

function hpMin(hhmm) {
  const [h, m] = String(hhmm || "0:0").split(":").map(Number);
  return h * 60 + (m || 0);
}
function hpHHMM(min) {
  const h = Math.floor(min / 60), m = min % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
function hpColor(materia) {
  let s = 0;
  for (const ch of String(materia || "")) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
  return HP_COLORES[s % HP_COLORES.length];
}
function hpAhora(estado) {
  return new Date(Date.now() + estado.offsetMs);
}
function hpEnMinutos(min) {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Estado de una clase de HOY respecto a la hora actual. */
function hpEstadoClase(c, ahoraMin, tolerancia) {
  const ini = hpMin(c.hora_inicio), fin = hpMin(c.hora_fin), abre = ini - tolerancia;
  if (ahoraMin < abre) return { tipo: "espera", abre, faltan: abre - ahoraMin };
  if (ahoraMin <= fin) return { tipo: "permitido", fin };
  return { tipo: "terminada" };
}

/**
 * Pinta horario + panel "hoy".
 * opts: { gridId, hoyId, rol: "alumno"|"docente", rostro: bool, ahora: "YYYY-MM-DDTHH:MM:SS", tolerancia }
 */
function renderPortalTimetable(clases, opts) {
  const servidor = opts.ahora ? new Date(opts.ahora) : new Date();
  HP_ESTADO[opts.gridId] = {
    clases: clases || [],
    offsetMs: isNaN(servidor) ? 0 : servidor.getTime() - Date.now(),
    tolerancia: Number.isFinite(opts.tolerancia) ? opts.tolerancia : 10,
    opts,
  };
  hpPintar(opts.gridId);
  if (!HP_TIMER) {
    HP_TIMER = setInterval(() => Object.keys(HP_ESTADO).forEach(hpPintar), 30000);
  }
}

function hpDetalle(c, rol) {
  return rol === "docente"
    ? `${esc(c.grupo_clave || c.grupo_nombre || c.grupo_id || "")} • ${esc(c.laboratorio_nombre)}`
    : `${esc(c.laboratorio_nombre)}${c.docente_nombre ? " • " + esc(c.docente_nombre) : ""}`;
}

function hpPintar(gridId) {
  const st = HP_ESTADO[gridId];
  if (!st) return;
  const { clases, tolerancia, opts } = st;
  const grid = document.getElementById(opts.gridId);
  const hoyEl = document.getElementById(opts.hoyId);
  const ahora = hpAhora(st);
  const hoy = HP_DIAS_JS[ahora.getDay()];
  const ahoraMin = ahora.getHours() * 60 + ahora.getMinutes();

  if (!clases.length) {
    const vacio = opts.rol === "docente"
      ? "Aún no tiene clases asignadas en este periodo. Su jefe de carrera las registra."
      : "Tu grupo aún no tiene horario en este periodo. Tu jefe de carrera lo publicará pronto.";
    if (grid) grid.innerHTML = `<div class="p-10 text-center text-slate-400 text-sm">
      <i data-lucide="calendar-x" class="w-8 h-8 mx-auto mb-2 text-slate-300"></i>${vacio}</div>`;
    if (hoyEl) hoyEl.innerHTML = "";
    if (window.lucide) lucide.createIcons();
    return;
  }

  // ── Cuadrícula semanal (escritorio) ──
  const dias = HP_DIAS.filter((d, i) => i < 5 || clases.some(c => c.dia_semana === d));
  const minIni = Math.floor(Math.min(...clases.map(c => hpMin(c.hora_inicio))) / 60) * 60;
  const maxFin = Math.ceil(Math.max(...clases.map(c => hpMin(c.hora_fin))) / 60) * 60;
  const alto = ((maxFin - minIni) / 60) * HP_PX_HORA;
  const horas = [];
  for (let m = minIni; m <= maxFin; m += 60) horas.push(m);

  const columnas = dias.map(d => {
    const esHoy = d === hoy;
    const bloques = clases.filter(c => c.dia_semana === d).map(c => {
      const top = ((hpMin(c.hora_inicio) - minIni) / 60) * HP_PX_HORA;
      const h = Math.max(((hpMin(c.hora_fin) - hpMin(c.hora_inicio)) / 60) * HP_PX_HORA - 3, 22);
      const activa = esHoy && hpEstadoClase(c, ahoraMin, tolerancia).tipo === "permitido";
      return `
        <div class="absolute left-1 right-1 rounded-lg border-l-4 border px-2 py-1 overflow-hidden shadow-sm ${hpColor(c.materia)} ${activa ? "ring-2 ring-emerald-500" : ""}"
             style="top:${top + 1}px;height:${h}px" title="${esc(c.materia)} — ${esc(c.hora_inicio)} a ${esc(c.hora_fin)}">
          <p class="text-[11px] font-bold leading-tight line-clamp-2">${esc(c.materia)}</p>
          <p class="text-[10px] opacity-80 font-mono">${esc(c.hora_inicio)}–${esc(c.hora_fin)}</p>
          ${h > 50 ? `<p class="text-[10px] opacity-80 truncate">${hpDetalle(c, opts.rol)}</p>` : ""}
          ${activa ? `<span class="absolute top-1 right-1 w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>` : ""}
        </div>`;
    }).join("");
    const lineaAhora = esHoy && ahoraMin >= minIni && ahoraMin <= maxFin
      ? `<div class="absolute left-0 right-0 border-t-2 border-red-500 z-10" style="top:${((ahoraMin - minIni) / 60) * HP_PX_HORA}px">
           <span class="absolute -left-1 -top-1.5 w-2.5 h-2.5 rounded-full bg-red-500"></span></div>` : "";
    return `
      <div class="min-w-0">
        <div class="h-9 flex items-center justify-center text-xs font-bold ${esHoy ? "text-white bg-slate-900 rounded-md" : "text-slate-600"}">${d}${esHoy ? " • Hoy" : ""}</div>
        <div class="relative border-l border-slate-100 ${esHoy ? "bg-slate-50/80" : ""}" style="height:${alto}px">${bloques}${lineaAhora}</div>
      </div>`;
  }).join("");

  const guia = horas.map(m => `
    <div class="absolute left-0 right-0 border-t border-dashed border-slate-100" style="top:${((m - minIni) / 60) * HP_PX_HORA}px"></div>`).join("");
  const etiquetas = horas.map(m => `
    <div class="absolute right-2 -translate-y-1/2 text-[10px] font-mono text-slate-400" style="top:${((m - minIni) / 60) * HP_PX_HORA}px">${hpHHMM(m)}</div>`).join("");

  const escritorio = `
    <div class="hidden md:block p-4 overflow-x-auto">
      <div class="grid gap-1 min-w-[640px]" style="grid-template-columns:52px repeat(${dias.length}, minmax(0,1fr))">
        <div><div class="h-9"></div><div class="relative" style="height:${alto}px">${etiquetas}</div></div>
        <div class="contents">${columnas}</div>
      </div>
    </div>`;

  // ── Lista por día (celular) ──
  const movil = `
    <div class="md:hidden divide-y divide-slate-100">
      ${dias.filter(d => clases.some(c => c.dia_semana === d)).map(d => `
        <div class="p-3 ${d === hoy ? "bg-slate-50" : ""}">
          <p class="text-xs font-bold mb-2 ${d === hoy ? "text-slate-900" : "text-slate-500"}">${d}${d === hoy ? " • Hoy" : ""}</p>
          <div class="space-y-2">
            ${clases.filter(c => c.dia_semana === d).map(c => `
              <div class="rounded-lg border-l-4 border px-3 py-2 ${hpColor(c.materia)}">
                <div class="flex items-center justify-between gap-2">
                  <p class="text-xs font-bold">${esc(c.materia)}</p>
                  <span class="text-[11px] font-mono shrink-0">${esc(c.hora_inicio)}–${esc(c.hora_fin)}</span>
                </div>
                <p class="text-[11px] opacity-80">${hpDetalle(c, opts.rol)}</p>
              </div>`).join("")}
          </div>
        </div>`).join("")}
    </div>`;

  if (grid) grid.innerHTML = escritorio + movil;
  // guías horizontales: se añaden a cada columna para no depender de posicionamiento cruzado
  grid?.querySelectorAll(".relative[style*='height']").forEach(col => col.insertAdjacentHTML("afterbegin", guia));

  // ── Panel de acceso de hoy ──
  if (!hoyEl) return;
  const deHoy = clases.filter(c => c.dia_semana === hoy).sort((a, b) => hpMin(a.hora_inicio) - hpMin(b.hora_inicio));
  const avisoRostro = opts.rostro ? "" : `
    <div class="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs">
      <i data-lucide="scan-face" class="w-4 h-4 shrink-0 mt-0.5"></i>
      <span><b>Aún no tienes tu rostro registrado.</b> Aunque tu horario lo permita, la puerta no podrá reconocerte. Acude con el administrador para registrarlo.</span>
    </div>`;

  let cuerpo;
  if (!deHoy.length) {
    // siguiente clase de la semana
    const orden = d => (HP_DIAS_JS.indexOf(d) - ahora.getDay() + 7) % 7 || 7;
    const prox = [...clases].sort((a, b) => orden(a.dia_semana) - orden(b.dia_semana) || hpMin(a.hora_inicio) - hpMin(b.hora_inicio))[0];
    cuerpo = `<div class="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600">
      Hoy (${hoy}) no tienes clases en laboratorio.
      ${prox ? `Tu siguiente acceso: <b>${esc(prox.dia_semana)} a las ${hpHHMM(Math.max(0, hpMin(prox.hora_inicio) - tolerancia))}</b> — ${esc(prox.materia)}.` : ""}
    </div>`;
  } else {
    cuerpo = deHoy.map(c => {
      const e = hpEstadoClase(c, ahoraMin, tolerancia);
      const chip = e.tipo === "permitido"
        ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
             <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Acceso permitido ahora</span>`
        : e.tipo === "espera"
          ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
               <i data-lucide="clock" class="w-3 h-3"></i> Podrás entrar a las ${hpHHMM(e.abre)}</span>`
          : `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-500 border border-slate-200">
               <i data-lucide="check" class="w-3 h-3"></i> Terminada</span>`;
      const nota = e.tipo === "permitido" ? `La puerta te deja pasar hasta las ${esc(c.hora_fin)}.`
        : e.tipo === "espera" ? `Faltan ${hpEnMinutos(e.faltan)}. La puerta abre ${tolerancia} min antes de la clase.`
        : `La clase terminó a las ${esc(c.hora_fin)}.`;
      return `
        <div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 p-3 rounded-lg border ${e.tipo === "permitido" ? "border-emerald-300 bg-emerald-50/40" : e.tipo === "terminada" ? "border-slate-200 opacity-70" : "border-slate-200"}">
          <div class="sm:w-24 shrink-0 font-mono text-sm font-bold text-slate-900">${esc(c.hora_inicio)}<span class="text-slate-400 font-normal">–${esc(c.hora_fin)}</span></div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-slate-900">${esc(c.materia)}</p>
            <p class="text-[11px] text-slate-500">${hpDetalle(c, opts.rol)}${c.edificio ? ` (${esc(c.edificio)})` : ""}</p>
            <p class="text-[11px] text-slate-500 mt-0.5">${nota}</p>
          </div>
          <div class="shrink-0">${chip}</div>
        </div>`;
    }).join("");
  }
  hoyEl.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <h4 class="text-sm font-bold text-slate-900 flex items-center gap-2">
        <i data-lucide="door-open" class="w-4 h-4 text-slate-500"></i> Mi acceso de hoy
      </h4>
      <span class="text-[11px] text-slate-400 font-mono">Hora del sistema ${hpHHMM(ahoraMin)}</span>
    </div>
    <div class="space-y-2">${avisoRostro}${cuerpo}</div>`;
  if (window.lucide) lucide.createIcons();
}
