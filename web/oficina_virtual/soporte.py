"""Agente de soporte técnico: le dice al usuario cómo hacer, dentro de la aplicación,
la tarea que quiere hacer.

    AgenteSoporte            Clase padre: carga la guía (ayuda.json) y escoge los temas.
    ├── SoporteLocal             Sin IA: compara las palabras de la pregunta con la guía.
    └── SoporteClaude            Con la API de Claude: entiende preguntas libres, pero solo
                                 responde con lo que dice la guía (no inventa botones ni pasos).

La guía es la única fuente: los dos agentes y el README dicen lo mismo.
El agente solo explica; nunca hace acciones por el usuario.
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

from analista import contiene, normalizar
from idiomas import idioma, t


class AgenteSoporte:
    nombre = ""

    def __init__(self, ruta_guia):
        self.temas = json.loads(Path(ruta_guia).read_text(encoding="utf-8"))["temas"]

    def tema(self, id_tema):
        return next((x for x in self.temas if x["id"] == id_tema), None)

    def candidatos(self, pregunta, pagina=None):
        """Temas ordenados por coincidencia: palabras en ambos idiomas; la página actual desempata."""
        texto = normalizar(pregunta or "")
        resultado = []
        for tema in self.temas:
            frases = tema["palabras"]["es"] + tema["palabras"]["en"]
            encontradas = [f for f in frases if contiene(texto, f)]
            puntos = sum(len(f.split()) for f in encontradas) * 2     # frases largas pesan más
            if pagina and pagina in tema["paginas"]:
                puntos += 1
            if encontradas or (pagina and pagina in tema["paginas"]):
                mas_larga = max((len(f.split()) for f in encontradas), default=0)
                resultado.append((puntos, mas_larga, len(encontradas), tema))
        # empate: gana la frase más específica (más larga), luego la que tuvo más coincidencias
        resultado.sort(key=lambda r: (-r[0], -r[1], -r[2]))
        return [(p, n, tema) for p, _, n, tema in resultado]

    def sugerencias(self, pagina=None, cuantas=4):
        """Temas útiles en la página actual (para los botones de sugerencia)."""
        propios = [x for x in self.temas if pagina in x["paginas"]]
        otros = [x for x in self.temas if x not in propios]
        return [{"id": x["id"], "titulo": x["titulo"][self.lengua()]} for x in (propios + otros)[:cuantas]]

    @staticmethod
    def lengua():
        return "en" if idioma() == "en" else "es"

    def responder(self, pregunta, pagina=None):
        """{"titulo", "pasos": [...], "ir_a": endpoint|None, "texto", "metodo"}"""
        raise NotImplementedError


class SoporteLocal(AgenteSoporte):
    nombre = "Guía (sin IA)"
    VAGAS = ("ayuda", "ayudame", "que hago", "que puedo hacer", "como funciona", "no entiendo",
             "help", "what do i do", "what now", "how does this work", "i don't understand")

    @classmethod
    def _es_vaga(cls, pregunta):
        texto = normalizar(pregunta or "")
        return len(texto.split()) <= 2 or any(contiene(texto, v) for v in cls.VAGAS)

    def responder(self, pregunta, pagina=None, id_tema=None):
        lengua = self.lengua()
        tema = self.tema(id_tema) if id_tema else None
        if not tema:
            candidatos = self.candidatos(pregunta, pagina)
            # una coincidencia de palabras gana; si solo hay «está en esta página», se usa si la pregunta es vaga
            con_palabras = [c for c in candidatos if c[1] > 0]
            if con_palabras:
                tema = con_palabras[0][2]
            elif candidatos and self._es_vaga(pregunta):
                tema = candidatos[0][2]             # «ayuda», «¿qué hago aquí?»: el tema de esta página
        if not tema:
            return {"titulo": t("No encontré ese tema en la guía"),
                    "pasos": [], "ir_a": None, "metodo": t(self.nombre),
                    "texto": t("Intente con otras palabras, por ejemplo «cómo creo una tabla» o «cómo envío mi aplicación», o escoja uno de los temas sugeridos.")}
        return {"titulo": tema["titulo"][lengua], "pasos": tema["pasos"][lengua],
                "ir_a": tema["ir_a"], "id": tema["id"], "texto": "", "metodo": t(self.nombre)}


class SoporteClaude(AgenteSoporte):
    """Responde preguntas libres con la API de Claude, limitado a la guía de la aplicación."""
    nombre = "Claude (API)"
    URL = "https://api.anthropic.com/v1/messages"
    SISTEMA = (
        "You are the technical support agent of a small web application. You explain to a non-technical "
        "user HOW to do what they want inside the application.\n"
        "RULES:\n"
        "1. Use ONLY the user guide below. Never invent buttons, pages, settings or features.\n"
        "2. If the guide does not cover the request, say so in one sentence and suggest the closest topic.\n"
        "3. You only explain. You never perform actions, send anything or change data for the user.\n"
        "4. Answer in {lengua}, in at most 6 short numbered steps, quoting button names exactly as the guide does.\n"
        "5. Answer with ONLY one JSON object: {{\"tema\": \"<topic id or empty>\", \"titulo\": \"...\", "
        "\"pasos\": [\"...\"], \"texto\": \"<one optional short sentence>\"}}\n\n"
        "The user is currently on the page: {pagina}\n\nUSER GUIDE (JSON):\n{guia}"
    )

    def __init__(self, ruta_guia, credenciales, respaldo=None):
        super().__init__(ruta_guia)
        self.cred = credenciales
        self.respaldo = respaldo or SoporteLocal(ruta_guia)

    def _pedir(self, sistema, pregunta):
        c = self.cred.leer()
        cuerpo = json.dumps({"model": c["modelo"], "max_tokens": 900, "system": sistema,
                             "messages": [{"role": "user", "content": pregunta[:1500]}]}).encode("utf-8")
        pedido = urllib.request.Request(self.URL, data=cuerpo, method="POST", headers={
            "x-api-key": c["anthropic_api_key"], "anthropic-version": c["version_api"],
            "content-type": "application/json"})
        with urllib.request.urlopen(pedido, timeout=60) as r:
            respuesta = json.load(r)
        return "".join(b.get("text", "") for b in respuesta.get("content", []))

    def responder(self, pregunta, pagina=None, id_tema=None):
        if id_tema or not (pregunta or "").strip():            # un tema escogido no necesita IA
            return self.respaldo.responder(pregunta, pagina, id_tema)
        lengua = self.lengua()
        guia = [{"id": x["id"], "ir_a": x["ir_a"], "titulo": x["titulo"][lengua], "pasos": x["pasos"][lengua]}
                for x in self.temas]
        sistema = self.SISTEMA.format(lengua="English" if lengua == "en" else "Spanish",
                                      pagina=pagina or "-", guia=json.dumps(guia, ensure_ascii=False))
        try:
            crudo = self._pedir(sistema, pregunta)
            datos = json.loads(crudo[crudo.index("{"): crudo.rindex("}") + 1])
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError):
            local = self.respaldo.responder(pregunta, pagina)    # sin conexión: la guía local responde
            local["texto"] = (local.get("texto") or "") + " " + t("(No pude consultar la IA; respondí con la guía.)")
            return local
        tema = self.tema(datos.get("tema") or "")
        return {"titulo": str(datos.get("titulo") or (tema["titulo"][lengua] if tema else "")),
                "pasos": [str(p) for p in (datos.get("pasos") or [])][:6],
                "texto": str(datos.get("texto") or ""),
                "ir_a": tema["ir_a"] if tema else None,
                "id": tema["id"] if tema else None, "metodo": t(self.nombre)}
