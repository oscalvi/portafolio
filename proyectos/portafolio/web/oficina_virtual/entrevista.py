"""Entrevista virtual: prepara al candidato para una oferta guardada.

    GeneradorEntrevista        arma el plan (apertura, personales, técnicas, caso práctico, cierre)
      ├─ GeneradorLocal        sin IA: lee la oferta y la hoja de vida y escoge de un banco de preguntas
      └─ GeneradorClaude       con la API de Claude (si está activada en Configuración)
    EvaluadorRespuesta         califica cada respuesta (sin IA: estructura STAR, puntos clave, ritmo,
      └─ EvaluadorClaude       muletillas, duración; con IA: además una versión mejorada de la respuesta)
    ArchivoEntrevistas         guarda el plan y cada práctica en entrevistas/ (privado: no se sube)

Las preguntas se hacen en el idioma de la oferta; los consejos, en el idioma de la página.
"""
import hashlib
import json
import re
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from idiomas import idioma, t
from respuestas_modelo import ejemplo


def normal(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def idioma_de(texto):
    """'es' o 'en' según las palabras más comunes del texto."""
    palabras = re.findall(r"[a-záéíóúñ]+", normal(texto))
    es = sum(p in {"de", "la", "que", "el", "en", "los", "para", "con", "una", "experiencia", "y"} for p in palabras)
    en = sum(p in {"the", "and", "to", "of", "you", "with", "for", "experience", "we", "your", "a"} for p in palabras)
    return "es" if es > en else "en"


# =====================================================================
#  BANCO DE PREGUNTAS (en el idioma de la oferta)
# =====================================================================
#  Cada técnica tiene: señales (regex en la oferta), pregunta en/es, puntos clave que el
#  entrevistador espera oír y la intención (en español; la página la traduce).

APERTURA = [
    {"id": "presentacion", "tipo": "libre", "segundos": 120,
     "en": "Thanks for joining. To start, tell me about yourself and what brings you to this {puesto} role.",
     "es": "Gracias por acompañarnos. Para empezar, cuénteme sobre usted y qué lo trae a esta posición de {puesto}.",
     "objetivo": "Resumen de 60 a 90 segundos: quién es hoy, 2 logros que conecten con la oferta y por qué esta posición.",
     "puntos": ["experience", "experiencia", "years", "años", "project", "proyecto", "role", "posicion"]},
    {"id": "por_que", "tipo": "libre", "segundos": 90,
     "en": "Why are you interested in working with {empresa}, and why now?",
     "es": "¿Por qué le interesa trabajar con {empresa} y por qué ahora?",
     "objetivo": "Muestre que leyó la oferta: mencione algo concreto de la empresa o del trabajo y cómo encaja con su momento.",
     "puntos": []},
]

PERSONALES = [
    {"id": "aprender", "senales": r"learn|new|fast|quickly|aprend|nuev|self", "tipo": "star", "segundos": 120,
     "en": "Tell me about a time you had to learn a new language, tool or codebase quickly. How did you approach it?",
     "es": "Cuénteme de una vez en que tuvo que aprender rápido un lenguaje, herramienta o código nuevo. ¿Cómo lo abordó?",
     "objetivo": "Situación concreta, cómo aprendió (método), y el resultado medible.",
     "puntos": ["learn", "aprend", "weeks", "semanas", "month", "mes", "documentation", "documentacion", "result"]},
    {"id": "problema", "senales": r".", "tipo": "star", "segundos": 150,
     "en": "Walk me through the hardest technical problem or bug you've solved. How did you find the root cause?",
     "es": "Cuénteme el problema técnico o el error más difícil que ha resuelto. ¿Cómo encontró la causa?",
     "objetivo": "Pasos de diagnóstico (hipótesis, pruebas, herramientas), la causa real y cómo evitó que volviera a pasar.",
     "puntos": ["root cause", "causa", "debug", "log", "test", "prueba", "reproduce", "reproduj", "fix", "corregi"]},
    {"id": "explicar", "senales": r"explain|communicat|clear|concise|explic|comunica|stakeholder|client",
     "tipo": "star", "segundos": 120,
     "en": "Tell me about a time you had to explain a complex technical change to someone who wasn't technical, or in very few words.",
     "es": "Cuénteme de una vez en que tuvo que explicar un cambio técnico complejo a alguien no técnico, o en muy pocas palabras.",
     "objetivo": "Cómo simplificó (analogía, antes y después, impacto) y cómo supo que lo entendieron.",
     "puntos": ["explain", "explic", "simple", "analog", "impact", "impacto", "client", "cliente", "user", "usuario"]},
    {"id": "retro", "senales": r"review|feedback|revis|revise|quality|calidad", "tipo": "star", "segundos": 120,
     "en": "Tell me about a time your work went through a tough review and you had to revise it. What did you change?",
     "es": "Cuénteme de una vez en que su trabajo tuvo una revisión exigente y tuvo que corregirlo. ¿Qué cambió?",
     "objetivo": "Actitud abierta ante la crítica, qué corrigió y qué aprendizaje aplicó después.",
     "puntos": ["feedback", "review", "revision", "changed", "cambie", "learned", "aprendi", "improv", "mejor"]},
    {"id": "conflicto", "senales": r"team|collabor|equipo|colabor|stakeholder", "tipo": "star", "segundos": 120,
     "en": "Describe a disagreement with a teammate or client about a technical decision. How was it resolved?",
     "es": "Describa un desacuerdo con un compañero o cliente sobre una decisión técnica. ¿Cómo se resolvió?",
     "objetivo": "Escuchó, usó datos para decidir y mantuvo la relación. Evite culpar.",
     "puntos": ["listen", "escuch", "data", "datos", "agreed", "acord", "compromise", "decision"]},
    {"id": "reglas", "senales": r"guideline|rubric|criteria|review|quality|strict|instruction|annotat|label|task|criterio|instruc",
     "tipo": "star", "segundos": 120,
     "en": "Tell me about a time you had to follow a strict, complex set of rules or guidelines. How did you make sure nothing slipped?",
     "es": "Cuénteme de una vez en que tuvo que seguir un conjunto de reglas o instrucciones estrictas y complejas. ¿Cómo se aseguró de no omitir nada?",
     "objetivo": "Atención al detalle (las plataformas de IA como Alignerr la evalúan): método de verificación, listas de control, cómo resolvió ambigüedades.",
     "puntos": ["checklist", "lista", "verif", "double", "doble", "detail", "detalle", "guideline", "instruc", "ambigu"]},
    {"id": "fallo", "senales": r".", "tipo": "star", "segundos": 120,
     "en": "Tell me about a project that didn't go as planned. What happened and what did you learn?",
     "es": "Cuénteme de un proyecto que no salió como se planeó. ¿Qué pasó y qué aprendió?",
     "objetivo": "Asuma su parte, explique la corrección y lo que hace distinto desde entonces.",
     "puntos": ["learned", "aprendi", "mistake", "error", "differently", "distinto", "now", "ahora"]},
    {"id": "prioridades", "senales": r"deadline|week|hours|independ|self-direct|autonom|plazo|horas|remote|remoto",
     "tipo": "star", "segundos": 90,
     "en": "This is remote, self-directed work. How do you organize your week and keep quality up without supervision?",
     "es": "Es un trabajo remoto y autónomo. ¿Cómo organiza su semana y mantiene la calidad sin supervisión?",
     "objetivo": "Rutina concreta, herramientas, cómo mide su avance y cómo comunica bloqueos.",
     "puntos": ["schedule", "horario", "plan", "checklist", "track", "seguimiento", "communicat", "comunic"]},
]

SIMPLE = {"id": "simple", "tipo": "libre", "segundos": 90,
          "en": "Explain {concepto} as if you were talking to a 12-year-old.",
          "es": "Explique {concepto} como si le hablara a un niño de 12 años.",
          "objetivo": "Capacidad de resumir (pregunta típica de las entrevistas con IA): una analogía, sin jerga, en 3 o 4 frases.",
          "puntos": ["like", "como", "imagine", "imagin", "example", "ejemplo"]}
CONCEPTOS = [(r"docker|container", {"en": "what a Docker container is", "es": "qué es un contenedor Docker"}),
             (r"\bgit\b|repositor", {"en": "what version control with Git is for", "es": "para qué sirve el control de versiones con Git"}),
             (r"test", {"en": "why automated tests matter", "es": "por qué importan las pruebas automáticas"}),
             (r"database|sql", {"en": "what a database index does", "es": "qué hace un índice en una base de datos"}),
             (r"\bai\b|model", {"en": "how an AI coding assistant learns", "es": "cómo aprende un asistente de IA para programar"})]

CV = {"en": "I see on your resume: “{linea}” Walk me through that — what exactly was your role, and what was the result?",
      "es": "Veo en su hoja de vida: «{linea}» Cuénteme más: ¿cuál fue exactamente su papel y cuál fue el resultado?"}

TECNICAS = [
    {"id": "estructuras", "senales": r"python|java|c\+\+|go\b|rust|typescript|algorithm|data structure|software engineer", "segundos": 120,
     "en": "When would you choose a hash map over a list or a tree? Give me a real case where that choice mattered.",
     "es": "¿Cuándo escogería un diccionario (hash map) en vez de una lista o un árbol? Dé un caso real en que esa decisión importó.",
     "objetivo": "Complejidad (búsqueda O(1) vs O(n) vs O(log n)), orden, memoria, y un ejemplo propio. Pregunta típica del modo experto de Alignerr.",
     "puntos": ["o(1)", "constant", "constante", "lookup", "busqueda", "order", "orden", "memory", "memoria", "log n", "key", "clave"]},
    {"id": "python", "senales": r"\bpython\b", "segundos": 120,
     "en": "How do you structure, test and package a Python project? Which tools do you rely on and why?",
     "es": "¿Cómo estructura, prueba y empaqueta un proyecto en Python? ¿Qué herramientas usa y por qué?",
     "objetivo": "Entornos virtuales, estructura de paquetes, pytest, linters/formatters, dependencias fijadas.",
     "puntos": ["venv", "virtual", "pytest", "unittest", "requirements", "pyproject", "lint", "type hint", "module", "modulo"]},
    {"id": "typescript", "senales": r"typescript|javascript|\bnode\b", "segundos": 120,
     "en": "What problems does TypeScript solve over plain JavaScript, and where can its types still lie to you?",
     "es": "¿Qué problemas resuelve TypeScript frente a JavaScript, y dónde pueden fallar sus tipos?",
     "objetivo": "Tipos estáticos, any/unknown, datos externos sin validar, compilación vs. ejecución.",
     "puntos": ["types", "tipos", "any", "unknown", "runtime", "compile", "valid", "interface"]},
    {"id": "go", "senales": r"\bgo\b|golang", "segundos": 120,
     "en": "How does concurrency work in Go, and how would you avoid a race condition?",
     "es": "¿Cómo funciona la concurrencia en Go y cómo evitaría una condición de carrera?",
     "objetivo": "Goroutines, channels, sync.Mutex, race detector.",
     "puntos": ["goroutine", "channel", "mutex", "race", "sync", "context"]},
    {"id": "rust", "senales": r"\brust\b", "segundos": 120,
     "en": "Explain ownership and borrowing in Rust and the kind of bugs they prevent.",
     "es": "Explique ownership y borrowing en Rust y qué errores previenen.",
     "objetivo": "Dueño único, préstamos mutables/inmutables, lifetimes, sin data races.",
     "puntos": ["ownership", "borrow", "lifetime", "mutable", "memory", "memoria"]},
    {"id": "java", "senales": r"\bjava\b|\bc#|\.net", "segundos": 120,
     "en": "In an object-oriented codebase, how do you apply SOLID principles without over-engineering?",
     "es": "En un código orientado a objetos, ¿cómo aplica los principios SOLID sin complicar de más?",
     "objetivo": "Ejemplos concretos de responsabilidad única e inversión de dependencias; equilibrio con simplicidad.",
     "puntos": ["single responsibility", "responsabilidad", "interface", "dependency", "dependencia", "solid", "simple"]},
    {"id": "cpp", "senales": r"c\+\+", "segundos": 120,
     "en": "How do you manage memory and resources safely in modern C++?",
     "es": "¿Cómo maneja memoria y recursos de forma segura en C++ moderno?",
     "objetivo": "RAII, smart pointers, evitar new/delete manual.",
     "puntos": ["raii", "unique_ptr", "shared_ptr", "smart pointer", "destructor"]},
    {"id": "docker", "senales": r"docker|container|contenedor", "segundos": 120,
     "en": "How would you use Docker to reproduce a repository exactly as it was before a specific change, so anyone gets the same result?",
     "es": "¿Cómo usaría Docker para reproducir un repositorio exactamente como estaba antes de un cambio, de modo que cualquiera obtenga el mismo resultado?",
     "objetivo": "Dockerfile con imagen base fija, checkout del commit, dependencias con versión fija, build y pruebas dentro del contenedor.",
     "puntos": ["dockerfile", "image", "imagen", "commit", "checkout", "pin", "version", "build", "reproducib"]},
    {"id": "linux", "senales": r"linux|unix|shell|bash", "segundos": 90,
     "en": "A process on a Linux server is hanging. What commands would you use to investigate?",
     "es": "Un proceso en un servidor Linux se quedó colgado. ¿Qué comandos usaría para investigar?",
     "objetivo": "ps/top, logs, strace, lsof, df/free, revisar puertos y permisos.",
     "puntos": ["ps", "top", "log", "strace", "lsof", "kill", "df", "free", "journalctl", "grep"]},
    {"id": "git", "senales": r"\bgit\b|repositor|pull request|commit", "segundos": 120,
     "en": "How would you find the exact commit that introduced a bug, and how do you check out the code as it was right before it?",
     "es": "¿Cómo encontraría el commit exacto que introdujo un error, y cómo deja el código como estaba justo antes?",
     "objetivo": "git log/blame, git bisect, checkout del commit padre (hash^), ramas.",
     "puntos": ["bisect", "log", "blame", "checkout", "commit", "branch", "rama", "diff", "hash"]},
    {"id": "pruebas", "senales": r"test|grading|check|rubric|evaluation|prueba", "segundos": 150,
     "en": "How do you write automated tests or grading checks that catch incorrect or shortcut solutions, without only accepting your own implementation?",
     "es": "¿Cómo escribe pruebas automáticas o verificaciones que atrapen soluciones incorrectas o atajos, sin aceptar solo su propia implementación?",
     "objetivo": "Probar comportamiento y no implementación, casos borde, entradas ocultas, pruebas negativas, intentar romper sus propias pruebas.",
     "puntos": ["edge case", "caso borde", "behavior", "comportamiento", "hidden", "ocult", "negative", "negativ", "mutation", "shortcut", "atajo"]},
    {"id": "ia_codigo", "senales": r"ai coding|coding tool|copilot|llm|ai model|modelo|\bai\b", "segundos": 120,
     "en": "Which AI coding tools do you use day to day? Give me an example where the tool got it wrong and how you caught it.",
     "es": "¿Qué herramientas de IA para programar usa a diario? Dé un ejemplo en que la herramienta se equivocó y cómo lo detectó.",
     "objetivo": "Uso real (Claude, ChatGPT, Copilot), cómo revisa lo generado, un error concreto y la prueba que lo atrapó.",
     "puntos": ["claude", "chatgpt", "copilot", "review", "revis", "test", "prueba", "wrong", "error", "hallucin"]},
    {"id": "rubrica", "senales": r"rubric|evaluation criteria|grading|benchmark|evaluaci", "segundos": 150,
     "en": "If you had to write a task brief and a rubric for a coding change so that strong AI models often fail but a skilled engineer can solve it, how would you design it?",
     "es": "Si tuviera que escribir el enunciado y la rúbrica de un cambio de código para que los mejores modelos de IA suelan fallar pero un ingeniero hábil lo resuelva, ¿cómo lo diseñaría?",
     "objetivo": "Enunciado claro y justo, contexto real del repositorio, requisitos verificables, pruebas que castiguen atajos, iterar contra los modelos.",
     "puntos": ["brief", "enunciado", "fair", "justo", "context", "contexto", "verif", "test", "prueba", "iterat", "model"]},
    {"id": "open_source", "senales": r"open.source|public|repositor|codebase", "segundos": 150,
     "en": "Tell me about a change you made in a codebase you know well. What was the problem, what did you change, and how did you verify it?",
     "es": "Cuénteme un cambio que hizo en un código que conoce bien. ¿Cuál era el problema, qué cambió y cómo lo verificó?",
     "objetivo": "Un cambio real y propio (no de un empleador), explicado en sus palabras: antes, cambio, pruebas, resultado.",
     "puntos": ["problem", "problema", "change", "cambi", "test", "prueba", "verif", "merge", "review"]},
    {"id": "bases_datos", "senales": r"database|sql|oracle|postgres|mysql|base de datos", "segundos": 150,
     "en": "How would you migrate a production database to a new system without losing data?",
     "es": "¿Cómo migraría una base de datos en producción a un sistema nuevo sin perder datos?",
     "objetivo": "Inventario y mapeo de esquemas, pruebas en copia, conteos y sumas de control, plan de reversa, ventana de corte.",
     "puntos": ["mapping", "mapeo", "schema", "esquema", "backup", "respaldo", "checksum", "count", "conteo", "rollback", "revers", "validat"]},
    {"id": "distribuidos", "senales": r"distributed|microservice|scal|distribuid", "segundos": 120,
     "en": "What makes distributed systems hard to test, and how would you test retries and timeouts?",
     "es": "¿Qué hace difícil probar sistemas distribuidos, y cómo probaría reintentos y tiempos de espera?",
     "objetivo": "Fallos parciales, idempotencia, relojes, simular fallas de red, pruebas deterministas.",
     "puntos": ["idempot", "retry", "reintent", "timeout", "partial", "parcial", "network", "red", "mock"]},
    {"id": "seguridad", "senales": r"security|secure|segur", "segundos": 120,
     "en": "How do you keep secrets and client code safe when you work remotely?",
     "es": "¿Cómo protege las claves y el código de clientes cuando trabaja de forma remota?",
     "objetivo": "Equipo propio y cifrado, gestor de claves, nada de claves en el código, MFA, no publicar trabajo confidencial.",
     "puntos": ["encrypt", "cifr", "password manager", "gestor", "mfa", "2fa", "env", "secret", "vpn", "private"]},
    {"id": "apis", "senales": r"\bapi|rest|integration|integraci|web service", "segundos": 120,
     "en": "Describe an integration you built between two systems. How did you handle errors and data that didn't match?",
     "es": "Describa una integración que construyó entre dos sistemas. ¿Cómo manejó errores y datos que no coincidían?",
     "objetivo": "Contrato de datos, validación, reintentos, registro de errores, conciliación.",
     "puntos": ["validat", "valid", "mapping", "mapeo", "retry", "log", "reconcil", "concili", "format"]},
    {"id": "agentes", "senales": r"agent|rl environment|reinforcement|agente", "segundos": 120,
     "en": "Have you built agent tasks or evaluation environments? If not, how would you approach your first one?",
     "es": "¿Ha construido tareas para agentes o entornos de evaluación? Si no, ¿cómo abordaría el primero?",
     "objetivo": "Honestidad sobre la experiencia; plan concreto: estado inicial reproducible, objetivo verificable, recompensa/puntaje.",
     "puntos": ["environment", "entorno", "reproduc", "state", "estado", "reward", "recompensa", "score", "puntaje"]},
]

CIERRE = [
    {"id": "disponibilidad", "senales": r"hours|week|horas|semana|part.time|start", "tipo": "libre", "segundos": 60,
     "en": "This role needs {horas}. What's your availability, and when could you start?",
     "es": "Esta posición requiere {horas}. ¿Cuál es su disponibilidad y cuándo podría empezar?",
     "objetivo": "Respuesta directa con horas y fecha. Si hay condiciones (horario, otro trabajo), dígalas con claridad.",
     "puntos": ["hours", "horas", "week", "semana", "start", "empez", "available", "disponib"]},
    {"id": "preguntas", "tipo": "libre", "segundos": 90,
     "en": "We're almost out of time. What questions do you have for us?",
     "es": "Ya casi terminamos. ¿Qué preguntas tiene para nosotros?",
     "objetivo": "Tenga 2 o 3 preguntas: cómo es la revisión, qué distingue una tarea aprobada, siguientes pasos.",
     "puntos": ["?", "how", "como", "what", "que", "review", "revision", "next", "siguiente"],
     "sugerencias": {"en": ["What separates work that passes review on the first round from work that needs several?",
                            "How is quality measured, and how is feedback shared?",
                            "What are the next steps after this interview?"],
                     "es": ["¿Qué distingue un trabajo que se aprueba en la primera revisión de uno que necesita varias?",
                            "¿Cómo se mide la calidad y cómo recibo la retroalimentación?",
                            "¿Cuáles son los siguientes pasos después de esta entrevista?"]}},
]

# Puntos clave en español (para mostrar al usuario solo los del idioma de la entrevista).
PUNTOS_ES = set("""acord ahora aprend aprendi atajo años busqueda cambi cambie causa cifr clave cliente como comportamiento
comunic concili constante conteo contexto corregi datos dependencia detalle disponib distinto doble documentacion ejemplo
empez entorno enunciado escuch esquema estado experiencia explic gestor horario horas imagen imagin impacto justo lista
mapeo mejor memoria mes modulo ocult orden parcial posicion problema proyecto prueba que rama recompensa red reintent
reproduj respaldo responsabilidad revers revis revision seguimiento semana semanas siguiente tipos usuario verif
caso borde puntaje negativ""".split()) | {"caso borde"}
GENERICAS = set("""experience experiencia project proyecto years role posicion result data datos change cambi problem
problema plan model simple like como que what how now ahora user usuario client cliente format version""".split())


def puntos_en(lista, lengua):
    """Los puntos clave en el idioma de la entrevista (sin repetir la misma idea en el otro idioma)."""
    return [p for p in lista if (p in PUNTOS_ES) == (lengua == "es") or p in ("verif",)]


ETAPAS = {"apertura": "Apertura", "personal": "Personal y conducta", "tecnica": "Técnica",
          "caso": "Caso práctico", "brecha": "Requisito por reforzar", "cierre": "Cierre"}


class GeneradorEntrevista:
    nombre = "base"

    def generar(self, oferta, hoja):
        raise NotImplementedError


class GeneradorLocal(GeneradorEntrevista):
    """Sin IA. Escoge del banco según lo que pide la oferta y conecta cada pregunta con la hoja de vida."""
    nombre = "local"
    MAX_PERSONALES, MAX_TECNICAS, MAX_CASOS, MAX_BRECHAS = 3, 5, 2, 1
    MAX_CV = 1

    @staticmethod
    def _texto_oferta(oferta):
        partes = [oferta.get("titulo"), oferta.get("descripcion"), " ".join(oferta.get("requisitos") or []),
                  " ".join(oferta.get("tareas") or []), " ".join(oferta.get("etiquetas") or [])]
        return normal(" ".join(p for p in partes if p))

    @staticmethod
    def lineas_hoja(hoja):
        texto = (hoja or {}).get("texto", "")
        return [l.strip() for l in texto.splitlines() if len(l.strip()) > 25]

    @classmethod
    def apoyo(cls, hoja, palabras, maximo=2):
        """Frases de la hoja de vida que sirven para responder (las que más palabras clave tocan)."""
        claves = [normal(p) for p in palabras if len(p) > 2 and normal(p) not in GENERICAS]
        patrones = [re.compile(r"(?<![a-z])" + re.escape(c)) for c in claves]
        puntuadas = []
        for linea in cls.lineas_hoja(hoja):
            if len(linea) > 300:                    # el párrafo del perfil no sirve como apoyo puntual
                continue
            n = normal(linea)
            puntos = sum(1 for pt in patrones if pt.search(n))
            if puntos:
                puntuadas.append((puntos, len(linea) < 260, linea))
        puntuadas.sort(key=lambda x: (-x[0], not x[1]))
        return [l for _, _, l in puntuadas[:maximo]]

    @staticmethod
    def _horas(texto):
        m = re.search(r"(?:at least|minimum of|about|around|al menos|minimo de|unas)?\s*(\d{1,2})\s*(?:\+\s*)?(hours|horas)\s*(?:a|per|por|a la|each)?\s*(week|semana)",
                      texto)
        return m.group(0).strip() if m else ""

    def _pregunta(self, base, etapa, idioma_oferta, datos, hoja, extra_puntos=()):
        texto = base[idioma_oferta].format(**datos)
        puntos = list(base.get("puntos", [])) + list(extra_puntos)
        return {"id": base["id"], "etapa": etapa, "tipo": base.get("tipo", "tecnica"), "texto": texto,
                "objetivo": base["objetivo"], "puntos": puntos, "segundos": base.get("segundos", 120),
                "apoyo": self.apoyo(hoja, puntos)}

    def generar(self, oferta, hoja):
        texto = self._texto_oferta(oferta)
        lengua = idioma_de(oferta.get("descripcion") or oferta.get("titulo") or "")
        datos = {"puesto": oferta.get("titulo", ""), "empresa": oferta.get("empresa") or "the company",
                 "horas": self._horas(texto) or ("some hours a week" if lengua == "en" else "algunas horas por semana")}
        preguntas = [self._pregunta(b, "apertura", lengua, datos, hoja) for b in APERTURA]
        lineas = self.lineas_hoja(hoja)
        titular = next((l for l in lineas[:6] if re.search(r"engineer|manager|developer|analyst|ingenier|gerente|desarroll", normal(l))), "")
        resumen = next((l for l in lineas if len(l) > 150), "")
        primera = re.split(r"(?<=\.)\s", resumen)[0] if resumen else ""
        preguntas[0]["apoyo"] = [l[:260] for l in (titular, primera) if l]

        # Técnicas: las que la oferta pide, primero las que aparecen en los requisitos.
        requisitos = normal(" ".join(oferta.get("requisitos") or []))
        candidatas = []
        for b in TECNICAS:
            en_req = len(re.findall(b["senales"], requisitos))
            en_todo = len(re.findall(b["senales"], texto))
            if en_todo:
                candidatas.append((en_req * 3 + en_todo, b))
        candidatas.sort(key=lambda x: -x[0])
        tecnicas = [self._pregunta(b, "tecnica", lengua, datos, hoja) for _, b in candidatas[:self.MAX_TECNICAS]]

        personales = [b for b in PERSONALES if re.search(b["senales"], texto)]
        personales.sort(key=lambda b: (b["senales"] == ".", PERSONALES.index(b)))
        personales = [self._pregunta(b, "personal", lengua, datos, hoja) for b in personales[:self.MAX_PERSONALES]]

        # Caso práctico: pasos del trabajo que describe la oferta.
        casos = []
        for tarea in (oferta.get("tareas") or [])[:8]:
            limpia = re.sub(r"^\W+", "", tarea).strip()
            if len(limpia) < 30 or re.match(r"(apply|aplic|complete a short)", normal(limpia)):
                continue
            casos.append(limpia)
        casos.sort(key=lambda c: -len(re.findall(r"test|check|solution|model|review|prueba|solucion", normal(c))))
        plantilla = {"en": "Here's part of the job: “{tarea}” Walk me through exactly how you would do it.",
                     "es": "Esta es parte del trabajo: «{tarea}» Explíqueme paso a paso cómo lo haría."}
        caso_preguntas = []
        for i, c in enumerate(casos[:self.MAX_CASOS]):
            palabras = re.findall(r"[a-z]{5,}", normal(c))[:8]
            caso_preguntas.append({"id": f"caso_{i + 1}", "etapa": "caso", "tipo": "tecnica",
                                   "texto": plantilla[lengua].format(tarea=c.rstrip(".")),
                                   "objetivo": "Pasos concretos y en orden, herramientas, cómo verifica el resultado y qué riesgos vigila.",
                                   "puntos": palabras + ["test", "prueba", "verif", "step", "paso"], "segundos": 180,
                                   "apoyo": self.apoyo(hoja, palabras)})

        # Brechas: requisitos que la hoja de vida no muestra.
        hoja_n = normal((hoja or {}).get("texto", ""))
        brechas = []
        for req in oferta.get("requisitos") or []:
            palabras = [p for p in re.findall(r"[a-z+#]{3,}", normal(req))
                        if p not in {"with", "and", "the", "one", "least", "years", "your", "you", "can", "for", "ideally",
                                     "professional", "strong", "solid", "regular", "use", "experience", "own", "may", "also",
                                     "qualify", "not", "employer", "client", "code", "into", "well", "know", "public", "secure",
                                     "personal", "work", "computer", "shared", "machines", "starting", "now", "hours", "week",
                                     "anos", "experiencia", "con", "los", "las", "del", "para", "por", "una", "uno", "clara",
                                     "conocimiento", "manejo", "minimo", "deseable", "bases", "datos", "trabajo"}]
            if len(palabras) < 2:
                continue
            tiene = sum(1 for p in palabras if re.search(r"(?<![a-z])" + re.escape(p), hoja_n)) / len(palabras)
            if tiene < 0.34:
                brechas.append((tiene, req))
        brechas.sort(key=lambda x: x[0])
        plantilla_b = {"en": "The role asks for: “{req}” Tell me about your experience with that.",
                       "es": "La posición pide: «{req}» Cuénteme su experiencia con eso."}
        brecha_preguntas = [{"id": f"brecha_{i + 1}", "etapa": "brecha", "tipo": "libre",
                             "texto": plantilla_b[lengua].format(req=r.rstrip(".")),
                             "objetivo": "Su hoja de vida no lo muestra claramente. Sea honesto: diga lo más cercano que sí ha hecho y cómo lo cerraría (curso, proyecto propio, fechas).",
                             "puntos": re.findall(r"[a-z]{4,}", normal(r))[:6] + ["learn", "aprend", "project", "proyecto"],
                             "segundos": 90, "apoyo": self.apoyo(hoja, re.findall(r"[a-z]{4,}", normal(r)))}
                            for i, (_, r) in enumerate(brechas[:self.MAX_BRECHAS])]

        # Sobre la hoja de vida (como Mercor): logros que más tocan la oferta.
        claves_oferta = [w for w in set(re.findall(r"[a-z]{5,}", texto)) if len(w) > 5][:200]
        cv = []
        for linea in self.lineas_hoja(hoja):
            n = normal(linea)
            if len(linea) < 60 or len(linea) > 240 or not re.match(r"[A-Z]", linea) or re.search(r"(19|20)\d\d\s*[–-]", linea) \
                    or ":" in linea[:40]:
                continue
            verbo = linea.split()[0].lower()
            toque = (sum(1 for w in claves_oferta if w in n) + (2 if re.search(r"\d", linea) else 0)
                     + (3 if verbo.endswith("ed") else 0)
                     + 2 * len(re.findall(r"recogni|zero|nationwide|national|team of|award|led\b", n)))
            cv.append((toque, linea))
        cv.sort(key=lambda x: -x[0])
        cv_preguntas = [{"id": f"cv_{i + 1}", "etapa": "personal", "tipo": "star", "texto": CV[lengua].format(linea=l.rstrip(".")),
                         "objetivo": "Las plataformas con IA (Mercor) preguntan por líneas exactas de su hoja de vida para validar la experiencia: dé contexto, su papel, cómo lo hizo y el resultado.",
                         "puntos": [w for w in re.findall(r"[a-z]{6,}", normal(l)) if w not in {"during", "received", "between", "including",
                                    "across", "through", "within", "company", "clients"}][:5], "segundos": 120, "apoyo": [l]}
                        for i, (_, l) in enumerate(cv[:2])][:2]
        concepto = next((c for r, c in CONCEPTOS if re.search(r, texto)), None)
        simple = [self._pregunta({**SIMPLE, lengua: SIMPLE[lengua].replace("{concepto}", concepto[lengua])}, "personal", lengua, datos, hoja)] if concepto else []

        cierre = [self._pregunta(b, "cierre", lengua, datos, hoja) for b in CIERRE
                  if "senales" not in b or re.search(b["senales"], texto)]
        for q, b in zip(cierre, [b for b in CIERRE if "senales" not in b or re.search(b["senales"], texto)]):
            q["apoyo"] = b.get("sugerencias", {}).get(lengua, [])

        orden = (preguntas + cv_preguntas[:1] + personales[:2] + tecnicas[:3] + simple + caso_preguntas + tecnicas[3:]
                 + cv_preguntas[1:] + personales[2:] + brecha_preguntas + cierre)
        # Versión rápida (15-20 min, como Alignerr): presentación, 1 de la hoja de vida, 2 técnicas,
        # explicar simple, 1 caso, 1 personal y preguntas finales.
        rapida = {preguntas[0]["id"], *(c["id"] for c in cv_preguntas[:1]), *(q["id"] for q in tecnicas[:2]),
                  *(q["id"] for q in simple), *(c["id"] for c in caso_preguntas[:1]), *(q["id"] for q in personales[:1]), "preguntas"}
        for q in orden:
            q["rapida"] = q["id"] in rapida
            q["ejemplo"] = ejemplo(q, lengua, hoja, datos)
        return {"idioma": lengua, "generado_con": self.nombre, "preguntas": self._numerar(orden),
                "brechas": [r for _, r in brechas[:4]],
                "duracion_min": round(sum(p["segundos"] for p in orden) / 60 + len(orden) * 0.5)}

    @staticmethod
    def _numerar(preguntas):
        vistos = set()
        salida = []
        for p in preguntas:
            if p["id"] in vistos:
                continue
            vistos.add(p["id"])
            salida.append(p)
        return salida


# ---------------------------------------------------------------------
#  Con la API de Claude
# ---------------------------------------------------------------------

def pedir_claude(credenciales, sistema, mensaje, max_tokens=4000):
    c = credenciales.leer()
    if not c.get("anthropic_api_key"):
        raise ValueError(t("Falta la clave de la API de Claude. Configúrela en «Configuración»."))
    cuerpo = json.dumps({"model": c["modelo"], "max_tokens": max_tokens, "system": sistema,
                         "messages": [{"role": "user", "content": mensaje}]}).encode("utf-8")
    pedido = urllib.request.Request("https://api.anthropic.com/v1/messages", data=cuerpo, method="POST", headers={
        "x-api-key": c["anthropic_api_key"], "anthropic-version": c.get("version_api", "2023-06-01"),
        "content-type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            respuesta = json.load(r)
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:300]
        raise ValueError(t("La API de Claude respondió con error {codigo}: {detalle}", codigo=e.code, detalle=detalle)) from e
    texto = "".join(b.get("text", "") for b in respuesta.get("content", []))
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin < 0:
        raise ValueError(t("La respuesta de Claude no trajo el formato esperado. Intente otra vez."))
    return json.loads(texto[inicio:fin + 1])


class GeneradorClaude(GeneradorEntrevista):
    nombre = "Claude (API)"
    SISTEMA = ("You are an experienced technical recruiter and hiring manager. You prepare a realistic virtual "
               "interview (screening + technical + behavioral) for ONE specific job posting and ONE candidate. "
               "Ask what interviewers really ask today for this kind of role (12-15 questions, 35-50 minutes). "
               "Write the questions in the language of the job posting. Write 'objetivo' in {ui}. "
               "'apoyo' must quote ONLY lines that exist in the candidate's resume. Never invent facts. "
               "Answer with ONLY one JSON object.")
    FORMATO = {"preguntas": [{"id": "short_id", "etapa": "apertura|personal|tecnica|caso|brecha|cierre",
                              "tipo": "libre|star|tecnica", "texto": "question as the interviewer says it",
                              "objetivo": "what the interviewer is evaluating and how to answer well",
                              "puntos": ["keywords a strong answer mentions"], "segundos": 120,
                              "apoyo": ["exact resume lines the candidate can use"],
                              "ejemplo": "a strong sample answer in first person, 80-150 words, using ONLY resume facts; put [brackets] where the candidate must add a detail"}],
               "brechas": ["requirements the resume does not show"]}

    def __init__(self, credenciales, respaldo=None):
        self.cred, self.respaldo = credenciales, respaldo or GeneradorLocal()

    def generar(self, oferta, hoja):
        ui = "Spanish" if idioma() == "es" else "English"
        mensaje = ("RESUME:\n<resume>\n" + (hoja or {}).get("texto", "")[:12000] + "\n</resume>\n\nJOB POSTING:\n<job>\n"
                   f"Title: {oferta.get('titulo')}\nCompany: {oferta.get('empresa')}\n"
                   f"Description:\n{(oferta.get('descripcion') or '')[:8000]}\n</job>\n\nReturn JSON with exactly:\n"
                   + json.dumps(self.FORMATO, ensure_ascii=False))
        datos = pedir_claude(self.cred, self.SISTEMA.replace("{ui}", ui), mensaje)
        preguntas = [p for p in datos.get("preguntas", []) if p.get("texto")]
        if len(preguntas) < 5:
            raise ValueError(t("La respuesta de Claude no trajo el formato esperado. Intente otra vez."))
        for i, p in enumerate(preguntas):
            p.setdefault("id", f"p{i + 1}")
            p["etapa"] = p.get("etapa") if p.get("etapa") in ETAPAS else "tecnica"
            p.setdefault("tipo", "star" if p["etapa"] == "personal" else "libre")
            p["segundos"] = int(p.get("segundos") or 120)
            p.setdefault("puntos", [])
            p.setdefault("apoyo", [])
        lengua = idioma_de(oferta.get("descripcion") or oferta.get("titulo") or "")
        for p in preguntas:
            p["ejemplo"] = p.get("ejemplo") or ejemplo(p, lengua, hoja)
        lengua = idioma_de(oferta.get("descripcion") or oferta.get("titulo") or "")
        return {"idioma": lengua, "generado_con": self.nombre, "preguntas": GeneradorLocal._numerar(preguntas),
                "brechas": datos.get("brechas", [])[:4],
                "duracion_min": round(sum(p["segundos"] for p in preguntas) / 60 + len(preguntas) * 0.5)}


# =====================================================================
#  EVALUACIÓN DE CADA RESPUESTA
# =====================================================================

MULETILLAS = {
    "en": [r"\bum+\b", r"\buh+\b", r"\blike\b", r"\byou know\b", r"\bbasically\b", r"\bactually\b", r"\bkind of\b",
           r"\bsort of\b", r"\bi mean\b"],
    "es": [r"\beh+\b", r"\bem+\b", r"\beste\b", r"\bo sea\b", r"\bpues\b", r"\bdigamos\b", r"\bbasicamente\b",
           r"\bentonces\b", r"\bcomo que\b"],
}
STAR = {
    "situacion": r"\b(when|at|while|in (19|20)\d\d|our team|the company|the client|cuando|en (19|20)\d\d|la empresa|el cliente|nuestro equipo|trabajaba)\b",
    "tarea": r"\b(my (goal|job|task|role)|i was (responsible|asked)|i had to|we needed|needed to|objective|mi (tarea|objetivo|rol|responsabilidad)|tenia que|teniamos que|me pidieron)\b",
    "accion": r"\b(i (built|designed|wrote|led|created|decided|analyzed|implemented|tested|migrated|studied|proposed|fixed|reviewed|set up|used)|(dise|constru|escrib|lider|cre|decid|analic|implement|prob|migr|estudi|propus|correg|revis)\w* yo|yo (dise|constru|escrib|lider|cre|decid|analic|implement|prob|migr|estudi|propus|correg|revis))",
    "resultado": r"(\d+\s?%|\b\d+\s?(hours|days|weeks|months|users|records|horas|dias|semanas|meses|usuarios|registros)\b|"
                 r"\b(result|as a result|reduced|increased|saved|delivered|zero|recognized|on time|resultado|reduj|aument|ahorr|entreg|cero|reconoc|a tiempo)\w*)",
}


class EvaluadorRespuesta:
    """Sin IA: revisa estructura, puntos clave, duración, ritmo y muletillas. Da 1 a 5 y consejos concretos."""
    nombre = "local"

    def evaluar(self, pregunta, texto, segundos, lengua="en"):
        n = normal(texto)
        palabras = re.findall(r"[\w']+", n)
        total = len(palabras)
        minutos = max(segundos, 1) / 60
        ppm = round(total / minutos) if segundos >= 5 else None
        fortalezas, mejorar = [], []
        if total < 8:
            return {"puntaje": 1, "palabras": total, "ppm": ppm, "segundos": round(segundos),
                    "fortalezas": [], "mejorar": [t("No escuché una respuesta. Intente de nuevo hablando cerca del micrófono, o escríbala.")],
                    "star": {}, "puntos_tocados": [], "puntos_faltan": pregunta.get("puntos", [])[:5], "muletillas": 0,
                    "resumen": t("Sin respuesta suficiente.")}

        puntaje = 3.0
        # Duración frente a lo esperado
        esperado = pregunta.get("segundos", 120)
        if segundos and segundos < esperado * 0.35:
            puntaje -= 0.7
            mejorar.append(t("Fue muy corta ({s} s). Desarrolle más: ejemplo concreto y resultado.", s=round(segundos)))
        elif segundos and segundos > esperado * 1.6:
            puntaje -= 0.5
            mejorar.append(t("Fue larga ({s} s). Apunte a {e} segundos: vaya al punto y cierre con el resultado.",
                             s=round(segundos), e=esperado))
        else:
            fortalezas.append(t("Buena duración."))

        # Muletillas
        muletillas = sum(len(re.findall(m, n)) for m in MULETILLAS.get(lengua, []) + MULETILLAS["en" if lengua == "es" else "es"][:0])
        if total and muletillas / total > 0.03:
            puntaje -= 0.4
            mejorar.append(t("Muchas muletillas ({n}). Cámbielas por una pausa en silencio.", n=muletillas))

        # Estructura STAR (personales)
        star = {k: bool(re.search(r, n)) for k, r in STAR.items()}
        if pregunta.get("tipo") == "star":
            presentes = sum(star.values())
            puntaje += (presentes - 2) * 0.5
            nombres = {"situacion": t("situación"), "tarea": t("tarea"), "accion": t("acción"), "resultado": t("resultado")}
            faltan = [nombres[k] for k, v in star.items() if not v]
            if faltan:
                mejorar.append(t("Use el método STAR. Faltó: {faltan}.", faltan=", ".join(faltan)))
            else:
                fortalezas.append(t("Respuesta completa con el método STAR."))
            if not star["resultado"]:
                mejorar.append(t("Cierre con un resultado medible (tiempo, porcentaje, cantidad o reconocimiento)."))
            yo = len(re.findall(r"\b(i|yo)\b", n))
            nosotros = len(re.findall(r"\b(we|nosotros|hicimos|logramos)\b", n))
            if nosotros > yo and nosotros >= 3:
                mejorar.append(t("Habló mucho en plural. Diga qué hizo usted personalmente."))

        # Puntos clave esperados
        puntos = [p for p in pregunta.get("puntos", []) if p and p != "?"]
        tocados = [p for p in puntos if normal(p) in n]
        faltan = [p for p in puntos_en(puntos, lengua) if p not in tocados and normal(p) not in GENERICAS]
        if puntos:
            cobertura = len(tocados) / min(max(len(puntos_en(puntos, lengua)), 1), 6)
            puntaje += (min(cobertura, 1) - 0.4) * 1.5
            if tocados:
                fortalezas.append(t("Mencionó: {puntos}.", puntos=", ".join(tocados[:5])))
            if cobertura < 0.5 and faltan:
                mejorar.append(t("Podría mencionar: {puntos}.", puntos=", ".join(faltan[:5])))
        if pregunta.get("id") == "preguntas" and "?" not in texto and not re.search(r"\b(how|what|which|when|como|que|cual|cuando)\b", n):
            mejorar.append(t("Lleve 2 o 3 preguntas preparadas para el entrevistador."))
        # Ejemplos concretos
        if re.search(r"\d", texto):
            fortalezas.append(t("Dio datos concretos."))
        elif pregunta.get("etapa") in ("personal", "caso", "tecnica"):
            mejorar.append(t("Agregue un dato concreto: un número, una fecha o un nombre de herramienta."))

        # Fluidez (lo miden Alignerr y Mercor): variedad de vocabulario y conectores.
        if total >= 40:
            variedad = len(set(palabras)) / total
            conectores = len(re.findall(r"\b(however|therefore|because|so that|for example|first|then|finally|as a result|"
                                        r"sin embargo|por lo tanto|porque|por ejemplo|primero|luego|finalmente|como resultado)\b", n))
            if conectores >= 2:
                fortalezas.append(t("Buena conexión de ideas (primero, luego, por eso…)."))
            else:
                mejorar.append(t("Use conectores para ordenar la respuesta: primero, luego, por eso, como resultado."))
            if variedad < 0.42:
                mejorar.append(t("Repitió muchas palabras; varíe el vocabulario."))

        puntaje = max(1, min(5, round(puntaje)))
        repregunta = self.repregunta(pregunta, star, tocados, puntos, segundos, lengua) if puntaje <= 4 else ""
        resumen = {5: t("Excelente respuesta."), 4: t("Buena respuesta."), 3: t("Respuesta aceptable; se puede mejorar."),
                   2: t("Respuesta débil; practíquela otra vez."), 1: t("Respuesta muy débil.")}[puntaje]
        return {"puntaje": puntaje, "palabras": total, "ppm": ppm, "segundos": round(segundos),
                "fortalezas": fortalezas[:4], "mejorar": mejorar[:5], "star": star,
                "puntos_tocados": tocados, "puntos_faltan": faltan[:6], "muletillas": muletillas, "resumen": resumen,
                "repregunta": repregunta}

    @staticmethod
    def repregunta(pregunta, star, tocados, puntos, segundos, lengua):
        """Como los entrevistadores con IA: una pregunta de seguimiento sobre lo que faltó."""
        textos = {
            "resultado": {"en": "What was the measurable result of that?", "es": "¿Cuál fue el resultado medible de eso?"},
            "accion": {"en": "What did you personally do, step by step?", "es": "¿Qué hizo usted personalmente, paso a paso?"},
            "corta": {"en": "Can you give me a concrete example?", "es": "¿Me puede dar un ejemplo concreto?"},
            "verificar": {"en": "How would you verify that it works?", "es": "¿Cómo verificaría que funciona?"},
        }
        if pregunta.get("etapa") in ("cierre", "apertura") or pregunta.get("es_repregunta"):
            return ""
        if segundos and segundos < pregunta.get("segundos", 120) * 0.35:
            return textos["corta"][lengua]
        if pregunta.get("tipo") == "star":
            if not star.get("accion"):
                return textos["accion"][lengua]
            if not star.get("resultado"):
                return textos["resultado"][lengua]
        if pregunta.get("etapa") in ("tecnica", "caso") and not re.search(r"test|prueba|verif", " ".join(tocados)):
            return textos["verificar"][lengua]
        return ""


class EvaluadorClaude(EvaluadorRespuesta):
    """Con la API de Claude: añade comentarios de un entrevistador y una versión mejorada usando solo la hoja de vida."""
    nombre = "Claude (API)"
    SISTEMA = ("You are a supportive but honest interview coach. Evaluate ONE answer to ONE interview question for a "
               "specific job. Use ONLY facts from the candidate's resume or from the answer itself for the improved "
               "version; never invent experience. Write 'comentario' and 'mejorar' in {ui}; write 'mejor_respuesta' in "
               "the language of the question, 120-200 words, first person, natural spoken style. Answer with ONLY one JSON object.")

    def __init__(self, credenciales, hoja):
        self.cred, self.hoja = credenciales, hoja

    def evaluar(self, pregunta, texto, segundos, lengua="en"):
        base = super().evaluar(pregunta, texto, segundos, lengua)
        if base["palabras"] < 8:
            return base
        ui = "Spanish" if idioma() == "es" else "English"
        mensaje = ("RESUME:\n" + (self.hoja or {}).get("texto", "")[:8000] + "\n\nQUESTION:\n" + pregunta["texto"]
                   + "\nWHAT THE INTERVIEWER EVALUATES:\n" + pregunta.get("objetivo", "") + "\n\nCANDIDATE ANSWER (speech-to-text, "
                   f"{round(segundos)} seconds):\n" + texto[:4000]
                   + '\n\nReturn JSON: {"puntaje": 1-5, "comentario": "2-3 sentences", "mejorar": ["up to 3 concrete tips"], '
                     '"mejor_respuesta": "improved answer"}')
        try:
            ia = pedir_claude(self.cred, self.SISTEMA.replace("{ui}", ui), mensaje, max_tokens=1500)
            base["puntaje"] = max(1, min(5, int(ia.get("puntaje") or base["puntaje"])))
            base["comentario"] = ia.get("comentario", "")
            base["mejorar"] = (ia.get("mejorar") or [])[:3] + base["mejorar"][:2]
            base["mejor_respuesta"] = ia.get("mejor_respuesta", "")
        except Exception as e:                      # sin conexión o error de la API: queda la evaluación local
            base["aviso"] = str(e)[:200]
        return base


def informe(plan, respuestas, total=None):
    """Resumen de una práctica completa."""
    hechas = [r for r in respuestas if r.get("evaluacion")]
    if not hechas:
        return {"promedio": 0, "respondidas": 0, "total": total or len(plan["preguntas"]), "nivel": t("Necesita más práctica"), "por_etapa": {}, "repasar": [], "fuertes": []}
    por_id = {p["id"]: p for p in plan["preguntas"]}
    por_etapa = {}
    for r in hechas:
        etapa = por_id.get(r["id"], {}).get("etapa", "tecnica")
        por_etapa.setdefault(etapa, []).append(r["evaluacion"]["puntaje"])
    promedio = round(sum(r["evaluacion"]["puntaje"] for r in hechas) / len(hechas), 1)
    ppm = [r["evaluacion"]["ppm"] for r in hechas if r["evaluacion"].get("ppm")]
    ordenadas = sorted(hechas, key=lambda r: r["evaluacion"]["puntaje"])
    return {"promedio": promedio, "respondidas": len(hechas), "total": total or len(plan["preguntas"]),
            "por_etapa": {t(ETAPAS.get(k, k)): round(sum(v) / len(v), 1) for k, v in por_etapa.items()},
            "ppm": round(sum(ppm) / len(ppm)) if ppm else None,
            "muletillas": sum(r["evaluacion"].get("muletillas", 0) for r in hechas),
            "repasar": [por_id.get(r["id"], {}).get("texto", r["id"]) for r in ordenadas[:3] if r["evaluacion"]["puntaje"] <= 3],
            "fuertes": [por_id.get(r["id"], {}).get("texto", r["id"]) for r in ordenadas[::-1][:2] if r["evaluacion"]["puntaje"] >= 4],
            "nivel": (t("Listo para la entrevista") if promedio >= 4 else
                      t("Casi listo: repase las preguntas marcadas") if promedio >= 3 else t("Necesita más práctica"))}


# =====================================================================
#  ARCHIVO: plan y prácticas por oferta (carpeta privada)
# =====================================================================

class ArchivoEntrevistas:
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)

    def ruta(self, url):
        return self.carpeta / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:12] + ".json")

    def cargar(self, url):
        r = self.ruta(url)
        return json.loads(r.read_text(encoding="utf-8")) if r.exists() else None

    def guardar(self, datos):
        r = self.ruta(datos["url"])
        temporal = r.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        temporal.replace(r)

    def preparar(self, oferta, hoja, generador, rehacer=False):
        """Devuelve el plan guardado o crea uno nuevo (si no hay o se pide rehacer)."""
        datos = self.cargar(oferta["url"])
        if datos and not rehacer:
            return datos
        try:
            plan = generador.generar(oferta, hoja)
            aviso = ""
        except Exception as e:                      # la API falló: se prepara sin IA
            plan, aviso = GeneradorLocal().generar(oferta, hoja), str(e)[:200]
        nuevo = {"url": oferta["url"], "titulo": oferta.get("titulo", ""), "empresa": oferta.get("empresa", ""),
                 "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "plan": plan, "aviso": aviso,
                 "practicas": (datos or {}).get("practicas", [])}
        self.guardar(nuevo)
        return nuevo

    def registrar_practica(self, url, modo, respuestas, total=None):
        datos = self.cargar(url)
        if not datos:
            raise ValueError(t("Primero prepare la entrevista."))
        resumen = informe(datos["plan"], respuestas, total)
        datos["practicas"].append({"fecha": datetime.now().strftime("%Y-%m-%d %H:%M"), "modo": modo,
                                   "respuestas": respuestas, "informe": resumen})
        datos["practicas"] = datos["practicas"][-20:]
        self.guardar(datos)
        return resumen
