"""El analista: entiende qué aplicación quiere el usuario y propone la base de datos.

Lee dos catálogos (configuración, no código):
    aplicaciones.json  tipos de aplicación, sus palabras clave y sus tablas sugeridas
    reglas.json        preguntas de dimensionamiento y reglas para recomendar el motor

Para agregar un tipo de aplicación (por ejemplo "Clínica"), se agrega su bloque
en aplicaciones.json. Para cambiar cuándo se recomienda cada motor, se edita
reglas.json. Esta clase no cambia.

La detección es por palabras clave. Para entender texto totalmente libre se
puede crear una subclase (por ejemplo AnalistaClaude) que reemplace detectar().
"""
import io
import json
import re
import unicodedata
from idiomas import t

NUMEROS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
           "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
           "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
           "noventa": 90, "cien": 100, "ciento": 100, "doscientos": 200,
           "trescientos": 300, "quinientos": 500,
           # inglés
           "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
           "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
           "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}
MULTIPLICADORES = {"mil": 1_000, "miles": 1_000, "millon": 1_000_000, "millones": 1_000_000,
                   "thousand": 1_000, "thousands": 1_000, "million": 1_000_000, "millions": 1_000_000,
                   "hundred": 100, "hundreds": 100}


def normalizar(texto):
    """Minúsculas, sin tildes y con espacios simples, para comparar palabras."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip()


def contiene(texto_normal, frase):
    """True si la frase aparece como palabra(s) completa(s)."""
    return re.search(rf"\b{re.escape(normalizar(frase))}\b", texto_normal) is not None


def extraer_numero(texto_normal):
    """Encuentra una cantidad en el texto: '15', '10.000', 'veinte', '10 mil', 'dos millones'."""
    fichas = re.findall(r"\d+(?:[.,]\d{3})*|[a-z]+", texto_normal)
    for i, ficha in enumerate(fichas):
        if ficha[0].isdigit():
            valor = int(re.sub(r"[.,]", "", ficha))
        elif ficha in NUMEROS:
            valor = NUMEROS[ficha]
        elif ficha in MULTIPLICADORES:          # "mil" solo = 1000
            return MULTIPLICADORES[ficha]
        else:
            continue
        siguiente = fichas[i + 1] if i + 1 < len(fichas) else ""
        return valor * MULTIPLICADORES.get(siguiente, 1)
    return None


class Analista:
    def __init__(self, ruta_aplicaciones, ruta_reglas):
        with open(ruta_aplicaciones, encoding="utf-8") as f:
            self.aplicaciones = json.load(f)
        with open(ruta_reglas, encoding="utf-8") as f:
            reglas = json.load(f)
        self.preguntas = reglas["preguntas"]
        self.reglas = reglas["reglas"]

    # ---------- catálogos ----------
    def aplicacion(self, id_app):
        return next((a for a in self.aplicaciones if a["id"] == id_app), None)

    def pregunta(self, id_pregunta):
        return next((p for p in self.preguntas if p["id"] == id_pregunta), None)

    # ---------- 1. ¿Qué aplicación quiere? ----------
    def detectar(self, descripcion):
        """Lista de candidatos ordenada: [{"aplicacion", "puntaje", "palabras"}]."""
        texto = normalizar(descripcion)
        candidatos = []
        for app in self.aplicaciones:
            encontradas = [p for p in app["palabras"] if contiene(texto, p)]
            if encontradas:
                candidatos.append({"aplicacion": app, "puntaje": len(encontradas),
                                   "palabras": encontradas})
        return sorted(candidatos, key=lambda c: c["puntaje"], reverse=True)

    # ---------- 2. Respuestas de dimensionamiento ----------
    def interpretar(self, id_pregunta, respuesta):
        """Convierte una respuesta hablada o escrita en el valor de una opción."""
        pregunta = self.pregunta(id_pregunta)
        if not pregunta:
            return None
        texto = normalizar(respuesta)
        for opcion in pregunta["opciones"]:     # 1. el usuario dijo el texto de la opción
            if contiene(texto, opcion["texto"]) or contiene(texto, t(opcion["texto"])) \
                    or texto == normalizar(opcion["valor"]):
                return opcion["valor"]
        numero = extraer_numero(texto)          # 2. dijo una cantidad
        if numero is not None:
            for opcion in pregunta["opciones"]:
                if "min" in opcion and opcion["min"] <= numero <= opcion["max"]:
                    return opcion["valor"]
        mejor, frase_mas_larga = None, 0        # 3. dijo palabras clave (gana la más específica)
        for opcion in pregunta["opciones"]:
            for frase in opcion["palabras"]:
                if contiene(texto, frase) and len(frase) > frase_mas_larga:
                    mejor, frase_mas_larga = opcion["valor"], len(frase)
        return mejor

    def opcion(self, id_pregunta, valor):
        pregunta = self.pregunta(id_pregunta)
        return next((o for o in pregunta["opciones"] if o["valor"] == valor), None)

    # ---------- 3. Recomendación ----------
    def puntaje(self, respuestas):
        total = 0
        for p in self.preguntas:
            o = self.opcion(p["id"], respuestas.get(p["id"]))
            total += o["puntos"] if o else 0
        return total

    def _cumple(self, condicion, respuestas, puntaje):
        if puntaje < condicion.get("puntaje_min", 0):
            return False
        if puntaje > condicion.get("puntaje_max", 10**9):
            return False
        for clave, permitidos in condicion.items():
            if clave.startswith("puntaje"):
                continue
            if respuestas.get(clave) not in permitidos:
                return False
        return True

    def recomendar(self, respuestas):
        """Aplica las reglas en orden; gana la primera que se cumple."""
        puntaje = self.puntaje(respuestas)
        regla = next(r for r in self.reglas if self._cumple(r["si"], respuestas, puntaje))
        resumen = []
        for p in self.preguntas:
            o = self.opcion(p["id"], respuestas.get(p["id"]))
            resumen.append({"pregunta": p["texto"], "respuesta": o["texto"] if o else "Sin respuesta"})
        return {"motor": regla["motor"], "solucion": regla["solucion"], "razon": regla["razon"],
                "alternativas": regla["alternativas"], "puntaje": puntaje, "resumen": resumen}

    # ---------- 4. Propuesta completa ----------
    def proponer(self, descripcion, respuestas, id_app=None):
        candidatos = self.detectar(descripcion)
        if id_app:                              # el usuario corrigió el tipo
            app = self.aplicacion(id_app)
        else:
            app = candidatos[0]["aplicacion"] if candidatos else None
        return {
            "descripcion": descripcion,
            "respuestas": respuestas,
            "aplicacion": app["id"] if app else None,
            "palabras": next((c["palabras"] for c in candidatos
                              if app and c["aplicacion"]["id"] == app["id"]), []),
            "candidatos": [c["aplicacion"]["id"] for c in candidatos],
            "recomendacion": self.recomendar(respuestas),
            "tablas": app["tablas"] if app else {},
            "relaciones": app["relaciones"] if app else [],
        }

    # ---------- Documentos con especificaciones ----------
    @staticmethod
    def leer_documento(nombre, contenido):
        """Extrae el texto de un .txt, .docx o .pdf (contenido en bytes)."""
        extension = nombre.lower().rsplit(".", 1)[-1]
        if extension in ("txt", "md"):
            for codificacion in ("utf-8", "latin-1"):
                try:
                    return contenido.decode(codificacion)
                except UnicodeDecodeError:
                    continue
        if extension == "docx":
            import docx                         # pip install python-docx
            documento = docx.Document(io.BytesIO(contenido))
            return "\n".join(p.text for p in documento.paragraphs)
        if extension == "pdf":
            import pypdf                        # pip install pypdf
            lector = pypdf.PdfReader(io.BytesIO(contenido))
            return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
        raise ValueError(t("Formato no soportado. Use un archivo .docx, .pdf o .txt."))
