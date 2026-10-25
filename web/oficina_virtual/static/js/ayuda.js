// Agente de soporte técnico: panel «Ayuda» del encabezado (texto o voz).
// Pregunta a /ayuda y muestra los pasos para hacer la tarea dentro de la aplicación.
(function () {
  const $ = id => document.getElementById(id);
  const panel = $("panel-ayuda"), boton = $("abrir-ayuda");
  if (!panel || !boton) return;
  const T = window.TEXTOS_AYUDA || {};
  const pagina = document.body.dataset.pagina || "";
  const lengua = document.body.dataset.idioma === "en" ? "en-US" : "es-US";
  let sugerenciasCargadas = false;

  function abrir(abierto) {
    panel.hidden = !abierto;
    boton.setAttribute("aria-expanded", String(abierto));
    if (abierto) {
      $("pregunta-ayuda").focus();
      if (!sugerenciasCargadas) cargarSugerencias();
    }
  }
  boton.addEventListener("click", () => abrir(panel.hidden));
  $("cerrar-ayuda").addEventListener("click", () => abrir(false));
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) abrir(false); });

  async function cargarSugerencias() {
    try {
      const r = await fetch("/ayuda/temas?pagina=" + encodeURIComponent(pagina));
      const datos = await r.json();
      const caja = $("sugerencias-ayuda");
      caja.replaceChildren();
      for (const tema of datos.temas) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "ayuda-chip"; b.textContent = tema.titulo;
        b.addEventListener("click", () => preguntar("", tema.id));
        caja.append(b);
      }
      sugerenciasCargadas = true;
    } catch (e) { /* sin sugerencias: la pregunta libre sigue funcionando */ }
  }

  function mostrar(r) {
    const caja = $("respuesta-ayuda");
    caja.replaceChildren();
    const h = document.createElement("h4"); h.textContent = r.titulo || ""; caja.append(h);
    if (r.texto) { const p = document.createElement("p"); p.textContent = r.texto; caja.append(p); }
    if (r.pasos && r.pasos.length) {
      const ol = document.createElement("ol");
      for (const paso of r.pasos) { const li = document.createElement("li"); li.textContent = paso; ol.append(li); }
      caja.append(ol);
    }
    const acciones = document.createElement("div"); acciones.className = "ayuda-acciones";
    if (r.url && r.url !== location.pathname) {
      const a = document.createElement("a"); a.className = "boton"; a.href = r.url; a.textContent = T.irA; acciones.append(a);
    }
    if ("speechSynthesis" in window && (r.pasos || []).length) {
      const leer = document.createElement("button"); leer.type = "button"; leer.className = "gris"; leer.textContent = T.leer;
      leer.addEventListener("click", () => {
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance([r.titulo, ...r.pasos].join(". "));
        u.lang = lengua; speechSynthesis.speak(u);
      });
      acciones.append(leer);
    }
    caja.append(acciones);
    if (r.metodo) { const m = document.createElement("p"); m.className = "ayuda-metodo"; m.textContent = T.via + " " + r.metodo; caja.append(m); }
  }

  async function preguntar(texto, tema) {
    $("respuesta-ayuda").textContent = T.pensando;
    try {
      const r = await fetch("/ayuda", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta: texto, pagina: pagina, tema: tema || null }) });
      if (!r.ok) throw new Error();
      mostrar(await r.json());
    } catch (e) { $("respuesta-ayuda").textContent = T.error; }
  }

  $("form-ayuda").addEventListener("submit", e => {
    e.preventDefault();
    const texto = $("pregunta-ayuda").value.trim();
    if (texto) preguntar(texto);
  });

  // Preguntar hablando (Web Speech API, en el idioma de la página)
  $("voz-ayuda").addEventListener("click", () => {
    const Reconocedor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Reconocedor) { $("respuesta-ayuda").textContent = T.sinVoz; return; }
    const rec = new Reconocedor();
    rec.lang = lengua; rec.interimResults = false; rec.maxAlternatives = 1;
    $("respuesta-ayuda").textContent = T.escuchando;
    rec.onresult = ev => {
      const texto = ev.results[0][0].transcript;
      $("pregunta-ayuda").value = texto;
      preguntar(texto);
    };
    rec.onerror = () => { $("respuesta-ayuda").textContent = T.sinVoz; };
    rec.start();
  });
})();
