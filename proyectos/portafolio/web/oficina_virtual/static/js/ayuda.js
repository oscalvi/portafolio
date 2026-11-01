// Agente de soporte técnico: panel «Ayuda» del encabezado.
// Al abrirlo saluda en voz alta y deja el micrófono escuchando. La respuesta se dice
// en voz y se va escribiendo en el panel, paso por paso, al mismo ritmo.
(function () {
  const $ = id => document.getElementById(id);
  const panel = $("panel-ayuda"), boton = $("abrir-ayuda");
  if (!panel || !boton) return;
  const T = window.TEXTOS_AYUDA || {};
  const pagina = document.body.dataset.pagina || "";
  const lengua = document.body.dataset.idioma === "en" ? "en-US" : "es-US";
  const Reconocedor = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hayVoz = "speechSynthesis" in window;
  let sugerenciasCargadas = false, reconocedor = null, escuchando = false;

  // ---------- Voz de salida ----------
  function vozPreferida() {
    const voces = hayVoz ? speechSynthesis.getVoices() : [];
    const base = lengua.slice(0, 2);
    return voces.find(v => v.lang === lengua) || voces.find(v => v.lang.startsWith(base)) || null;
  }
  // Lo que se dice en voz: sin emojis, sin comillas «» y con las flechas leídas como «luego»
  function paraDecir(texto) {
    return String(texto || "")
      .replace(/\p{Extended_Pictographic}|️/gu, "")
      .replace(/[«»"]/g, "")
      .replace(/\s*→\s*/g, lengua.startsWith("en") ? ", then " : ", luego ")
      .replace(/\s+/g, " ").trim();
  }
  function decir(texto, alEmpezar, alTerminar) {
    if (!hayVoz) { if (alEmpezar) alEmpezar(); if (alTerminar) alTerminar(); return; }
    const u = new SpeechSynthesisUtterance(paraDecir(texto));
    u.lang = lengua;
    const v = vozPreferida(); if (v) u.voice = v;
    if (alEmpezar) u.onstart = alEmpezar;
    if (alTerminar) { u.onend = alTerminar; u.onerror = alTerminar; }
    speechSynthesis.speak(u);
  }
  function callar() { if (hayVoz) speechSynthesis.cancel(); }

  // ---------- Micrófono ----------
  function escuchar() {
    if (!Reconocedor) { estado(T.sinVoz); $("pregunta-ayuda").focus(); return; }
    if (/Edg\//.test(navigator.userAgent)) { estado(T.usarChrome); $("pregunta-ayuda").focus(); return; }
    if (escuchando) return;
    callar();
    reconocedor = new Reconocedor();
    reconocedor.lang = lengua; reconocedor.interimResults = true; reconocedor.maxAlternatives = 1;
    reconocedor.onstart = () => { escuchando = true; $("voz-ayuda").classList.add("escuchando"); estado(T.escuchando); };
    reconocedor.onresult = ev => {
      const r = ev.results[ev.results.length - 1];
      $("pregunta-ayuda").value = r[0].transcript;     // se ve lo que va entendiendo
      if (r.isFinal) preguntar(r[0].transcript.trim());
    };
    reconocedor.onerror = ev => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") estado(T.sinPermiso);
      else if (ev.error === "no-speech") estado(T.noOi);
      else if (ev.error === "network" || ev.error === "audio-capture") estado(T.usarChrome);
    };
    reconocedor.onend = () => { escuchando = false; $("voz-ayuda").classList.remove("escuchando"); };
    try { reconocedor.start(); } catch (e) { /* ya estaba escuchando */ }
  }
  function dejarDeEscuchar() { if (reconocedor && escuchando) reconocedor.abort(); }

  function estado(texto) {
    const caja = $("respuesta-ayuda");
    caja.replaceChildren();
    const p = document.createElement("p"); p.className = "ayuda-estado"; p.textContent = texto; caja.append(p);
  }

  // ---------- Abrir y cerrar ----------
  function abrir(abierto) {
    panel.hidden = !abierto;
    boton.setAttribute("aria-expanded", String(abierto));
    if (abierto) {
      if (!sugerenciasCargadas) cargarSugerencias();
      $("pregunta-ayuda").value = "";
      estado(T.saludo);
      // saluda y, al terminar de hablar, deja el micrófono escuchando
      decir(T.saludo, null, () => { if (!panel.hidden) escuchar(); });
    } else {
      callar(); dejarDeEscuchar();
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

  // ---------- Respuesta: se dice y se va escribiendo ----------
  function mostrar(r) {
    const caja = $("respuesta-ayuda");
    caja.replaceChildren();
    const h = document.createElement("h4"); h.textContent = r.titulo || ""; caja.append(h);
    if (r.texto) { const p = document.createElement("p"); p.textContent = r.texto; caja.append(p); }
    const pasos = r.pasos || [];
    const ol = document.createElement("ol");
    if (pasos.length) caja.append(ol);

    const acciones = document.createElement("div"); acciones.className = "ayuda-acciones";
    if (r.url && r.url !== location.pathname) {
      const a = document.createElement("a"); a.className = "boton"; a.href = r.url; a.textContent = T.irA; acciones.append(a);
    }
    const otra = document.createElement("button"); otra.type = "button"; otra.className = "gris"; otra.textContent = T.otra;
    otra.addEventListener("click", escuchar);
    acciones.append(otra);
    if (hayVoz && pasos.length) {
      const leer = document.createElement("button"); leer.type = "button"; leer.className = "gris"; leer.textContent = T.leer;
      leer.addEventListener("click", () => { callar(); hablarRespuesta(r, null, null); });
      acciones.append(leer);
    }
    const metodo = document.createElement("p"); metodo.className = "ayuda-metodo";
    if (r.metodo) metodo.textContent = T.via + " " + r.metodo;
    const terminar = () => { caja.append(acciones, metodo); acciones.scrollIntoView({ block: "nearest", behavior: "smooth" }); };

    if (!hayVoz) {                       // sin voz: se muestra todo de una vez
      for (const paso of pasos) { const li = document.createElement("li"); li.textContent = paso; ol.append(li); }
      terminar(); return;
    }
    hablarRespuesta(r, ol, terminar);
  }

  // Dice el título y cada paso; si recibe la lista, escribe cada paso cuando empieza a decirlo
  function hablarRespuesta(r, ol, alFinal) {
    const pasos = r.pasos || [];
    const partes = [r.titulo || ""].concat(r.texto ? [r.texto] : [], pasos);
    const desde = partes.length - pasos.length;
    let escritos = 0;
    const escribirHasta = n => {         // escribe los pasos que falten hasta el número n
      for (; ol && escritos < n; escritos++) {
        const li = document.createElement("li"); li.textContent = pasos[escritos]; li.className = "aparece";
        ol.append(li);
        li.scrollIntoView({ block: "nearest", behavior: "smooth" });   // el panel sigue al paso que se está diciendo
      }
    };
    partes.forEach((texto, i) => {
      const ultimo = i === partes.length - 1;
      decir(texto,
            i >= desde ? () => escribirHasta(i - desde + 1) : null,
            ultimo ? () => { escribirHasta(pasos.length); if (alFinal) alFinal(); } : null);
    });
  }

  async function preguntar(texto, tema) {
    dejarDeEscuchar(); callar();
    estado(T.pensando);
    try {
      const r = await fetch("/ayuda", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pregunta: texto, pagina: pagina, tema: tema || null }) });
      if (!r.ok) throw new Error();
      mostrar(await r.json());
    } catch (e) { estado(T.error); decir(T.error); }
  }

  $("form-ayuda").addEventListener("submit", e => {
    e.preventDefault();
    const texto = $("pregunta-ayuda").value.trim();
    if (texto) preguntar(texto);
  });
  $("voz-ayuda").addEventListener("click", () => escuchando ? dejarDeEscuchar() : escuchar());

  // Chrome carga la lista de voces un momento después de abrir la página
  if (hayVoz) speechSynthesis.getVoices();
})();
