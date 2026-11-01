/* Entrevista virtual: el entrevistador habla (voz del navegador), el candidato responde de viva voz
   (reconocimiento de voz de Chrome/Edge) o escribiendo, y el servidor revisa cada respuesta. */
(() => {
  const $ = id => document.getElementById(id);
  const D = JSON.parse($('datos-entrevista').textContent);
  const T = JSON.parse($('textos-entrevista').textContent);
  const lengua = D.plan.idioma === 'es' ? 'es' : 'en';
  const lenguaVoz = lengua === 'es' ? 'es-CO' : 'en-US';
  const lenguaPagina = (document.body.dataset.idioma || 'es') === 'es' ? 'es' : 'en';
  const nombre = (D.nombre || '').trim().split(/\s+/)[0] || '';
  const fmt = (s, datos) => s.replace(/\{(\w+)\}/g, (_, k) => datos[k] ?? '');

  const FRASES = {
    en: { hola: n => `Hi${n ? ' ' + n : ''}, thanks for joining today. I'll ask you some questions about your experience and this role. Take your time and answer as you would in a real interview.`,
          etapa: { personal: "Let's talk about your experience.", tecnica: "Now a few technical questions.", caso: "Let's go through a practical scenario.",
                   brecha: "A couple of questions about specific requirements.", cierre: "We're getting close to the end." },
          adios: "That's all from me. Thank you for your time, and good luck!" },
    es: { hola: n => `Hola${n ? ' ' + n : ''}, gracias por acompañarnos hoy. Le haré algunas preguntas sobre su experiencia y esta posición. Tómese su tiempo y responda como en una entrevista real.`,
          etapa: { personal: 'Hablemos de su experiencia.', tecnica: 'Ahora unas preguntas técnicas.', caso: 'Veamos un caso práctico.',
                   brecha: 'Un par de preguntas sobre requisitos puntuales.', cierre: 'Ya vamos terminando.' },
          adios: 'Eso es todo de mi parte. Gracias por su tiempo y mucha suerte.' },
  };

  let preguntas = [], i = 0, respuestas = [], actual = null, etapaAnterior = '';
  let grabando = false, reconocedor = null, textoFinal = '', inicio = 0, reloj = null, ultimaVoz = 0, enRepregunta = false;

  /* ---------- Voz del entrevistador ---------- */
  function vozPara(codigo) {
    const voces = speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().startsWith(codigo.slice(0, 2)));
    const natural = voces.find(v => /natural|online|google/i.test(v.name) && v.lang.replace('_', '-') === codigo)
      || voces.find(v => /natural|online|google/i.test(v.name)) || voces.find(v => v.lang.replace('_', '-') === codigo);
    return natural || voces[0] || null;
  }
  function hablar(texto, codigo = lenguaVoz) {
    return new Promise(listo => {
      if (!$('voz').checked || !('speechSynthesis' in window) || !texto) return listo();
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(texto);
      u.voice = vozPara(codigo); u.lang = u.voice ? u.voice.lang : codigo; u.rate = 0.98;
      $('avatar').classList.add('hablando');
      const fin = () => { $('avatar').classList.remove('hablando'); listo(); };
      u.onend = fin; u.onerror = fin;
      speechSynthesis.speak(u);
    });
  }
  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};

  /* ---------- Micrófono ---------- */
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  // Cada vez que se abre el micrófono se crea un reconocedor NUEVO: reutilizar uno que Chrome cerró
  // (por silencio, por la red o porque la voz del entrevistador lo interrumpió) lo dejaba mudo.
  let sesion = 0, vigilante = null, oyendo = false;
  function crearReconocedor(miSesion) {
    const r = new Reconocimiento();
    r.lang = lenguaVoz; r.continuous = true; r.interimResults = true; r.maxAlternatives = 1;
    r.onaudiostart = () => { if (miSesion === sesion) { oyendo = true; aviso(T.escuchando, true); } };
    r.onresult = e => {
      if (miSesion !== sesion) return;
      let provisional = '';
      for (let k = e.resultIndex; k < e.results.length; k++) {
        const pedazo = e.results[k][0].transcript;
        if (e.results[k].isFinal) textoFinal += (textoFinal && !textoFinal.endsWith(' ') ? ' ' : '') + pedazo.trim();
        else provisional += pedazo;
      }
      $('respuesta').value = (textoFinal + ' ' + provisional).trim();
      ultimaVoz = Date.now();
    };
    r.onerror = e => {
      if (miSesion !== sesion) return;
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { aviso(T.mic_negado); grabando = false; botonHablar(); }
      else if (e.error === 'audio-capture') { aviso(T.mic_ausente); grabando = false; botonHablar(); }
      else if (e.error === 'network') aviso(T.mic_red);
    };
    r.onend = () => {                                  // Chrome corta tras un silencio o un error: se abre uno nuevo
      oyendo = false;
      if (miSesion === sesion && grabando) setTimeout(() => { if (miSesion === sesion && grabando) abrir(); }, 250);
    };
    return r;
  }
  function abrir() {
    const viejo = reconocedor;
    if (viejo) { viejo.onend = null; viejo.onresult = null; viejo.onerror = null; try { viejo.abort(); } catch (_) {} }
    const miSesion = ++sesion;
    reconocedor = crearReconocedor(miSesion);
    oyendo = false;
    try { reconocedor.start(); } catch (_) { setTimeout(() => { if (miSesion === sesion && grabando) abrir(); }, 400); return; }
    clearTimeout(vigilante);                           // si en 3 s no arrancó el audio, se intenta de nuevo
    vigilante = setTimeout(() => { if (miSesion === sesion && grabando && !oyendo) abrir(); }, 3000);
  }
  function empezarGrabar() {
    if (!Reconocimiento) { aviso(T.sin_voz); $('respuesta').focus(); return; }
    speechSynthesis.cancel();
    textoFinal = $('respuesta').value.trim();
    grabando = true; ultimaVoz = Date.now();
    if (!inicio) iniciarReloj();
    aviso(T.abriendo, true); botonHablar();
    abrir();
  }
  function pararGrabar() {
    grabando = false; sesion++; clearTimeout(vigilante);
    if (reconocedor) { const r = reconocedor; r.onend = null; try { r.stop(); } catch (_) {} }
    reconocedor = null;
    botonHablar();
  }
  function botonHablar() {
    $('hablar').textContent = grabando ? T.detener : T.responder;
    $('hablar').classList.toggle('grabando', grabando);
  }
  function aviso(texto, vivo = false) { $('estado-mic').textContent = texto; $('estado-mic').classList.toggle('vivo', vivo); }

  /* ---------- Reloj y silencio ---------- */
  function iniciarReloj() {
    inicio = Date.now();
    clearInterval(reloj);
    reloj = setInterval(() => {
      const s = Math.floor((Date.now() - inicio) / 1000);
      $('reloj').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
      if (grabando && $('autofin').checked && $('respuesta').value.trim().split(/\s+/).length > 6 && Date.now() - ultimaVoz > 4000) terminar();
    }, 250);
  }
  $('respuesta').addEventListener('input', () => { if (!inicio) iniciarReloj(); if (!grabando) textoFinal = $('respuesta').value; });
  $('respuesta').addEventListener('focus', () => { if (grabando) { pararGrabar(); aviso(T.corrigiendo); } });

  /* ---------- Flujo ---------- */
  async function mostrarPregunta(p, esRepregunta = false) {
    actual = p; enRepregunta = esRepregunta;
    $('caja-pista').hidden = true; if (!esRepregunta) $('caja-retro').hidden = true;
    $('respuesta').value = ''; textoFinal = ''; inicio = 0; clearInterval(reloj); $('reloj').textContent = '0:00';
    $('progreso').textContent = fmt(T.pregunta_de, { i: i + 1, n: preguntas.length });
    $('etapa').textContent = esRepregunta ? T.seguimiento : p.etapa_texto;
    $('etapa').className = 'etapa e-' + (esRepregunta ? 'seguimiento' : p.etapa);
    $('pregunta').textContent = p.texto;
    $('pregunta').classList.toggle('oculta', !$('mostrar').checked);
    $('meta').textContent = fmt(T.meta, { s: p.segundos || 60 });
    ['listo', 'repetir', 'pista', 'saltar', 'hablar'].forEach(b => $(b).disabled = false);
    aviso(T.escuche);
    let dicho = p.texto;
    if (!esRepregunta && p.etapa !== etapaAnterior && FRASES[lengua].etapa[p.etapa]) dicho = FRASES[lengua].etapa[p.etapa] + ' ' + dicho;
    if (!esRepregunta) etapaAnterior = p.etapa;
    await hablar(dicho);
    if (actual === p) { if (Reconocimiento) empezarGrabar(); else { aviso(T.sin_voz); $('respuesta').focus(); } }
  }

  async function terminar() {
    if (!actual) return;
    pararGrabar(); clearInterval(reloj);
    const texto = $('respuesta').value.trim();
    const segundos = inicio ? (Date.now() - inicio) / 1000 : 0;
    const p = actual; actual = null;
    ['listo', 'repetir', 'pista', 'saltar', 'hablar'].forEach(b => $(b).disabled = true);
    aviso(T.evaluando);
    let ev;
    try {
      const r = await fetch('/empleos/entrevista/evaluar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: D.url, id: p.id, respuesta: texto, segundos, repregunta: enRepregunta, texto_pregunta: p.texto }) });
      ev = await r.json();
      if (!r.ok) throw new Error(ev.error || r.status);
    } catch (e) { aviso(T.error + ' ' + e.message); ['listo', 'hablar'].forEach(b => $(b).disabled = false); actual = p; return; }
    respuestas.push({ id: p.id, pregunta: p.texto, texto, segundos: Math.round(segundos), evaluacion: ev, seguimiento: enRepregunta,
                      ejemplo: enRepregunta ? '' : (p.ejemplo || '') });

    // Pregunta de seguimiento, como los entrevistadores con IA (una por pregunta).
    if (!enRepregunta && $('repreguntas').checked && ev.repregunta && texto.split(/\s+/).length > 6) {
      if ($('retro').value === 'cada') mostrarRetro(ev, p, false);
      return mostrarPregunta({ ...p, id: p.id + '_seg', texto: ev.repregunta, segundos: 60, apoyo: [], puntos_ver: [], ejemplo: '' }, true);
    }
    if ($('retro').value === 'cada') {
      mostrarRetro(ev, p, true);
      await hablar(ev.resumen + ' ' + (ev.mejorar[0] || ''), lenguaPagina === 'es' ? 'es-CO' : 'en-US');
    } else siguiente();
  }

  function lista(titulo, cosas, clase) {
    return cosas && cosas.length ? `<div class="${clase}"><b>${titulo}</b><ul>${cosas.map(c => `<li>${esc(c)}</li>`).join('')}</ul></div>` : '';
  }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function mostrarRetro(ev, p, conBotones) {
    const caja = $('caja-retro');
    caja.innerHTML = `<div class="nota n${ev.puntaje}">${'★'.repeat(ev.puntaje)}${'☆'.repeat(5 - ev.puntaje)} <span>${esc(ev.resumen)}</span>
        <small>${ev.segundos} ${T.segundos}</small></div>
      ${ev.comentario ? `<p>${esc(ev.comentario)}</p>` : ''}
      ${lista(T.fortalezas, ev.fortalezas, 'bien')}${lista(T.mejorar, ev.mejorar, 'mal')}
      ${ev.mejor_respuesta ? `<details open><summary>${T.mejor}</summary><p class="mejor">${esc(ev.mejor_respuesta)}</p></details>` : ''}
      ${p.ejemplo ? `<details ${ev.mejor_respuesta ? '' : 'open'}><summary>${T.ejemplo}</summary><p class="mejor">${esc(p.ejemplo)}</p>
        <p class="sub">${T.corchetes}</p><button type="button" class="gris chico" id="b-oir">${T.oir}</button></details>` : ''}
      ${conBotones ? `<div class="botones-ent"><button type="button" id="b-sig">${T.siguiente}</button>
        <button type="button" class="gris" id="b-otra">${T.otra_vez}</button></div>` : ''}`;
    caja.hidden = false;
    if ($('b-oir')) $('b-oir').onclick = () => hablar(p.ejemplo.replace(/\[[^\]]*\]/g, ''));
    if (conBotones) {
      $('b-sig').onclick = () => { speechSynthesis.cancel(); siguiente(); };
      $('b-otra').onclick = () => {
        speechSynthesis.cancel();
        respuestas = respuestas.filter(r => r.id !== p.id && r.id !== p.id + '_seg');
        mostrarPregunta(preguntas[i]);
      };
    }
  }

  function siguiente() {
    i += 1;
    if (i < preguntas.length) mostrarPregunta(preguntas[i]);
    else finalizar();
  }

  async function finalizar() {
    pararGrabar(); clearInterval(reloj); actual = null;
    hablar(FRASES[lengua].adios);
    const principales = respuestas.filter(r => !r.seguimiento);
    const r = await fetch('/empleos/entrevista/terminar', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: D.url, modo: $('modo').value, respuestas: principales, total: preguntas.length }) });
    const inf = await r.json();
    $('sala').hidden = true;
    const etapas = Object.entries(inf.por_etapa || {}).map(([k, v]) => `<li>${esc(k)}: <b>${v}</b>/5</li>`).join('');
    $('informe').innerHTML = `<h2>${T.informe}</h2>
      <div class="resumen-final"><div class="gran-nota">${inf.promedio}<small>/5</small></div>
        <div><b>${esc(inf.nivel || '')}</b><br>${T.respondidas}: ${inf.respondidas}/${inf.total}
        <br>${T.muletillas}: ${inf.muletillas ?? 0}</div></div>
      ${etapas ? `<h3>${T.por_etapa}</h3><ul>${etapas}</ul>` : ''}
      ${lista(T.repasar, inf.repasar, 'mal')}${lista(T.fuertes, inf.fuertes, 'bien')}
      <details><summary>${T.detalle}</summary>${respuestas.map(x => `<div class="detalle">
        <div class="q">${x.seguimiento ? '↳ ' : ''}${esc(x.pregunta)}</div>
        <div class="nota n${x.evaluacion.puntaje}">${'★'.repeat(x.evaluacion.puntaje)}${'☆'.repeat(5 - x.evaluacion.puntaje)} <span>${esc(x.evaluacion.resumen)}</span></div>
        <p><b>${T.su_respuesta}:</b> ${esc(x.texto || T.saltada)}</p>
        ${lista(T.mejorar, x.evaluacion.mejorar, 'mal')}
        ${x.evaluacion.mejor_respuesta ? `<p class="mejor">${esc(x.evaluacion.mejor_respuesta)}</p>` : ''}
        ${x.ejemplo ? `<p class="mejor"><b>${T.ejemplo}:</b> ${esc(x.ejemplo)}</p>` : ''}</div>`).join('')}</details>
      <div class="botones-ent"><a class="boton" href="${location.pathname}?url=${encodeURIComponent(D.url)}">${T.practicar_otra}</a></div>`;
    $('informe').hidden = false;
    $('informe').scrollIntoView({ behavior: 'smooth' });
  }

  /* ---------- Botones ---------- */
  $('empezar').onclick = async () => {
    preguntas = D.plan.preguntas.filter(p => $('modo').value === 'completa' || p.rapida);
    i = 0; respuestas = []; etapaAnterior = 'apertura';
    $('preparacion').hidden = true; $('informe').hidden = true; $('sala').hidden = false;
    $('pregunta').textContent = ''; $('progreso').textContent = ''; $('etapa').textContent = '';
    await hablar(FRASES[lengua].hola(nombre));
    mostrarPregunta(preguntas[0]);
  };
  $('hablar').onclick = () => grabando ? (pararGrabar(), aviso(T.pausado)) : empezarGrabar();
  $('listo').onclick = terminar;
  $('repetir').onclick = () => { pararGrabar(); hablar(actual ? actual.texto : '').then(() => actual && empezarGrabar()); };
  $('saltar').onclick = () => {
    if (!actual) return;
    pararGrabar(); clearInterval(reloj);
    if (!enRepregunta) respuestas.push({ id: actual.id, pregunta: actual.texto, texto: '', segundos: 0, saltada: true, ejemplo: actual.ejemplo || '',
      evaluacion: { puntaje: 1, resumen: T.saltada, mejorar: [], fortalezas: [] } });
    actual = null; siguiente();
  };
  $('pista').onclick = () => {
    const p = actual; if (!p) return;
    const caja = $('caja-pista');
    caja.innerHTML = `<b>🎯 ${T.objetivo}:</b> ${esc(p.objetivo_texto || '')}
      ${p.puntos_ver && p.puntos_ver.length ? `<br><b>🔑 ${T.claves}:</b> ${esc(p.puntos_ver.slice(0, 8).join(', '))}` : ''}
      ${p.apoyo && p.apoyo.length ? `<br><b>📄 ${T.apoyo}:</b><ul>${p.apoyo.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}`;
    caja.hidden = !caja.hidden;
  };
  $('mostrar').onchange = () => $('pregunta').classList.toggle('oculta', !$('mostrar').checked);
  $('salir').onclick = () => { if (confirm(T.confirmar_salir)) { speechSynthesis.cancel(); finalizar(); } };
})();
