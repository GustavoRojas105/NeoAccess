// ─────────────────────────────────────────────────────────────
// Materias oficiales del ITSOEH, tomadas de su página de Oferta Educativa
// (https://www.itsoeh.edu.mx/front/services.html, consultada 24/11/2026).
//
// - Ingeniería Civil: retícula completa ICIV-2010-208 (con semestre).
// - Resto de carreras: la página oficial solo publica una parte de las
//   asignaturas (bloque PILA2021, sin semestre). Cuando el ITSOEH publique
//   la retícula completa, agréguelas aquí: { s: semestre o null, m: "Nombre" }.
// ─────────────────────────────────────────────────────────────
const MATERIAS_ITSOEH = (() => {
  const conSemestre = (porSemestre) =>
    Object.entries(porSemestre).flatMap(([s, lista]) => lista.map(m => ({ s: Number(s), m })));
  const sinSemestre = (lista) => lista.map(m => ({ s: null, m }));

  return {
    "Ingeniería Civil": conSemestre({
      1: ["Fundamentos de Investigación", "Cálculo Diferencial", "Taller de Ética", "Química",
          "Software en Ingeniería Civil", "Dibujo en Ingeniería Civil"],
      2: ["Probabilidad y Estadística", "Cálculo Integral", "Estática", "Geología", "Topografía",
          "Métodos Numéricos"],
      3: ["Álgebra Lineal", "Cálculo Vectorial", "Dinámica", "Mecánica de Suelos",
          "Modelos de Optimización de Recursos", "Materiales y Procesos Constructivos"],
      4: ["Hidráulica Básica", "Ecuaciones Diferenciales", "Fundamentos de la Mecánica de los Medios Continuos",
          "Mecánica de Suelos Aplicada", "Tecnología del Concreto", "Costos y Presupuestos"],
      5: ["Hidrología Superficial", "Maquinaria Pesada y Movimiento de Tierra", "Mecánica de Materiales",
          "Carreteras", "Sistemas de Transporte", "Administración de la Construcción", "Desarrollo Sustentable"],
      6: ["Hidráulica de Canales", "Taller de Investigación I", "Análisis Estructural",
          "Diseño y Construcción de Pavimentos", "Instalaciones en los Edificios"],
      7: ["Abastecimiento de Agua", "Taller de Investigación II", "Análisis Estructural Avanzado",
          "Diseño de Elementos de Concreto Reforzado"],
      8: ["Alcantarillado", "Formulación y Evaluación de Proyectos", "Diseño de Elementos de Acero",
          "Diseño Estructural de Cimentaciones"],
    }),
    "Ingeniería Industrial": sinSemestre([
      "Administración de Operaciones I", "Control Estadístico de la Calidad", "Ergonomía",
      "Gestión de los Sistemas de Calidad", "Investigación de Operaciones II",
      "Logística y Cadena de Suministro", "Planeación Financiera", "Planeación y Diseño de Instalaciones",
    ]),
    "Ingeniería en Industrias Alimentarias": sinSemestre([
      "Biología", "Calidad e Inocuidad Alimentaria", "Taller de Investigación I",
    ]),
    "Ingeniería en Electromecánica": sinSemestre([
      "Análisis de Circuitos de CA", "Sistemas y Máquinas de Fluidos", "Taller de Investigación II",
    ]),
    "Ingeniería en Sistemas Computacionales": sinSemestre([
      "Conmutación y Enrutamiento en Redes de Datos", "Lenguajes y Autómatas II", "Matemáticas Discretas",
      "Programación Web", "Sistemas Operativos I",
    ]),
    "Ingeniería en Gestión Empresarial": sinSemestre([
      "Calidad Aplicada a la Gestión Empresarial", "El Emprendedor y la Innovación", "Ingeniería de Procesos",
      "Mercadotecnia", "Mercadotecnia Electrónica",
    ]),
    "Arquitectura": sinSemestre([
      "Administración de Empresas Constructoras II", "Administración de la Construcción II",
      "Análisis Crítico de la Arquitectura y el Arte I", "Análisis Crítico de la Arquitectura y el Arte III",
      "Estructuras I", "Estructuras de Concreto", "Taller de Diseño I", "Taller de Diseño III",
      "Taller de Diseño V", "Taller de Investigación I", "Urbanismo I",
    ]),
    "Ingeniería en Tecnologías de la Información y Comunicaciones": sinSemestre([
      "Interacción Humano Computadora", "Negocios Electrónicos I", "Redes de Computadoras",
      "Sistemas Operativos I",
    ]),
    "Ingeniería en Logística": sinSemestre([
      "Administración de Flotillas de Transporte", "Centros de Distribución",
      "Logística de Flujos Internacionales", "Operación y Control de Transporte de Carga Terrestre",
      "Taller de Habilidades Directivas",
    ]),
  };
})();

// Llena un <select> de materias según la carrera (y semestre) del grupo.
// Sin carrera conocida muestra todas, agrupadas por carrera.
function fillSubjectSelect(select, carrera, semestre) {
  if (!select) return;
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
