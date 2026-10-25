"""Aplicar a una oferta: hoja de vida adaptada, carta y correo.

ESTRUCTURA
    Credenciales          Lee y guarda credenciales.json (clave de API y correo).
    HojaDeVida            Guarda el ORIGINAL sin tocarlo y su texto.
    AdaptadorCV           Clase padre: adapta la hoja de vida a una oferta.
    ├── AdaptadorLocal    Sin inteligencia artificial: compara palabras y reordena (gratis).
    └── AdaptadorClaude   Con la API de Claude (redacción más natural; tiene costo).
    GeneradorDocumentos   Crea la hoja de vida adaptada y la carta en Word (.docx).
    Remitente             Clase padre: envía el correo con los adjuntos.
    └── RemitenteSMTP     Gmail u otro correo con SMTP. Hoy usa la cuenta del dueño;
                          cuando haya usuarios, cada uno tendrá su propio Remitente.

Regla de oro del adaptador: reorganiza y resalta lo que la persona YA tiene;
nunca agrega experiencia, títulos ni habilidades que no estén en el original.
"""
import json
import mimetypes
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from analista import Analista
from idiomas import idioma, t

CORREO_EN_TEXTO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def nombre_archivo(texto, largo=40):
    texto = re.sub(r"[^\w\s-]", "", texto, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", texto)[:largo] or "archivo"


# =====================================================================
#  CREDENCIALES
# =====================================================================

class Credenciales:
    """credenciales.json: datos privados. No se comparte ni se sube a internet."""
    VACIAS = {
        "anthropic_api_key": "",
        "modelo": "claude-sonnet-5-5",
        "version_api": "2023-06-01",
        "usar_api": False,                  # False = adaptar sin IA (AdaptadorLocal)
        "correo": {"nombre": "", "remitente": "", "clave_app": "",
                   "servidor": "smtp.gmail.com", "puerto": 465},
    }

    def __init__(self, ruta):
        self.ruta = Path(ruta)

    def leer(self):
        datos = json.loads(json.dumps(self.VACIAS))
        if self.ruta.exists():
            guardado = json.loads(self.ruta.read_text(encoding="utf-8"))
            correo = {**datos["correo"], **guardado.get("correo", {})}
            datos.update(guardado)
            datos["correo"] = correo
        return datos

    def guardar(self, datos):
        self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    def tiene_ia(self):
        return bool(self.leer()["anthropic_api_key"])

    def usar_api(self):
        datos = self.leer()
        return bool(datos.get("usar_api") and datos["anthropic_api_key"])

    def tiene_correo(self):
        c = self.leer()["correo"]
        return bool(c["remitente"] and c["clave_app"])

    def cuenta_correo(self):
        """El correo del usuario (para abrir el borrador en su Gmail con esa cuenta)."""
        return self.leer()["correo"].get("remitente", "")


# =====================================================================
#  HOJA DE VIDA ORIGINAL
# =====================================================================

class HojaDeVida:
    """Guarda el original tal como se subió y su texto para el adaptador."""

    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.original = self.carpeta / "original"
        self.adaptadas = self.carpeta / "adaptadas"
        self.original.mkdir(parents=True, exist_ok=True)
        self.adaptadas.mkdir(parents=True, exist_ok=True)
        self.ficha = self.carpeta / "hoja_de_vida.json"

    def subir(self, nombre, contenido):
        texto = Analista.leer_documento(nombre, contenido).strip()
        if len(texto) < 200:
            raise ValueError(t("No pude leer suficiente texto de ese archivo. Pruebe con el Word (.docx) de la hoja de vida."))
        destino = self.original / Path(nombre).name
        destino.write_bytes(contenido)       # el original queda intacto
        self.ficha.write_text(json.dumps({
            "archivo": destino.name, "texto": texto,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def datos(self):
        if not self.ficha.exists():
            return None
        return json.loads(self.ficha.read_text(encoding="utf-8"))


# =====================================================================
#  ADAPTADOR
# =====================================================================

class AdaptadorCV:
    """Clase padre. Recibe la hoja de vida ({"texto", "ruta"}) y la oferta;
    devuelve un dict con el contenido adaptado (mismo formato en todas las subclases)."""
    nombre = "Adaptador"

    def adaptar(self, hoja, oferta):
        raise NotImplementedError


class AdaptadorClaude(AdaptadorCV):
    nombre = "Claude (API)"
    URL = "https://api.anthropic.com/v1/messages"
    SISTEMA = (
        "You are an expert recruiter and resume writer. You tailor a candidate's resume to a "
        "specific job posting so it passes ATS filters and reads well to a hiring manager.\n"
        "STRICT RULES:\n"
        "1. Use ONLY facts present in the original resume. Never invent employers, dates, titles, "
        "degrees, certifications, tools, skills, numbers or achievements.\n"
        "2. You may reword, reorder, select and emphasize what is relevant, and use the posting's "
        "vocabulary when it truthfully describes something in the resume.\n"
        "3. Requirements the resume does not show go in 'faltan', never in the resume.\n"
        "4. Write the resume and cover letter in the language of the job posting. Write 'cumple', "
        "'faltan' and 'consejos' in {idioma_usuario}.\n"
        "5. Answer with ONLY one JSON object, no extra text."
    )
    FORMATO = {
        "nombre": "full name from the resume",
        "contacto": "email · phone · city · LinkedIn, only what the resume has",
        "titular": "one-line professional headline aimed at this job",
        "resumen_profesional": "3-4 sentences focused on this job",
        "habilidades": ["most relevant skills first, only from the resume"],
        "experiencia": [{"cargo": "", "empresa": "", "lugar": "", "fechas": "",
                         "logros": ["2-4 bullets reworded for this job"]}],
        "educacion": ["degree, school, year — as in the resume"],
        "otros": ["certifications, languages, etc. only if in the resume"],
        "cumple": ["requisitos de la oferta que la hoja de vida sí muestra"],
        "faltan": ["requisitos que no aparecen en la hoja de vida"],
        "consejos": ["1-3 consejos breves para esta aplicación"],
        "carta": "cover letter body, 150-220 words, no address block, signed with the candidate's name",
        "asunto_correo": "email subject line for applying",
        "cuerpo_correo": "short email body (60-100 words) that mentions the attached resume and cover letter",
    }

    def __init__(self, credenciales):
        self.cred = credenciales

    def _pedir(self, mensaje):
        c = self.cred.leer()
        if not c["anthropic_api_key"]:
            raise ValueError(t("Falta la clave de la API de Claude. Configúrela en «Configuración»."))
        cuerpo = json.dumps({
            "model": c["modelo"], "max_tokens": 4000, "system": self.SISTEMA.replace("{idioma_usuario}", "Spanish" if idioma() == "es" else "English"),
            "messages": [{"role": "user", "content": mensaje}]}).encode("utf-8")
        pedido = urllib.request.Request(self.URL, data=cuerpo, method="POST", headers={
            "x-api-key": c["anthropic_api_key"], "anthropic-version": c["version_api"],
            "content-type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=120) as r:
                respuesta = json.load(r)
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ValueError(t("La API de Claude respondió con error {codigo}: {detalle}", codigo=e.code, detalle=detalle)) from e
        return "".join(b.get("text", "") for b in respuesta.get("content", []))

    def adaptar(self, hoja, oferta):
        mensaje = (
            "ORIGINAL RESUME:\n<resume>\n" + hoja["texto"][:15000] + "\n</resume>\n\n"
            "JOB POSTING:\n<job>\n"
            f"Title: {oferta['titulo']}\nCompany: {oferta['empresa']}\n"
            f"Type: {oferta.get('tipo', '')}\nLocation: {oferta.get('ubicacion', '')}\n"
            f"Description:\n{oferta.get('descripcion', '')[:8000]}\n</job>\n\n"
            "Return a JSON object with exactly these keys:\n"
            + json.dumps(self.FORMATO, ensure_ascii=False, indent=1))
        texto = self._pedir(mensaje)
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fin < 0:
            raise ValueError(t("La respuesta de Claude no trajo el formato esperado. Intente otra vez."))
        return json.loads(texto[inicio:fin + 1])


# ---------------------------------------------------------------------
#  Adaptador sin inteligencia artificial
# ---------------------------------------------------------------------

PALABRAS_VACIAS = set("""a an and are as at be by for from has have in into is it its of on or our
the their this to we with you your will can who what that than then they them also about across
not may all any more most other some such very just like well ideally least one plus must
experience experienced years year strong solid professional ability able work working skill skills
knowledge required preferred good great excellent using use new team role job position
el la los las de del y o en con para por un una que se su sus al""".split())


def raiz(p):
    """Raíz sencilla para que 'tools' coincida con 'tool' y 'coding' con 'code'."""
    for fin in ("ing", "ed", "es", "s"):
        if len(p) > 4 and p.endswith(fin):
            return p[: -len(fin)]
    return p


def palabras(texto):
    return {raiz(p.strip(".")) for p in re.findall(r"[a-z0-9+#.]{3,}", Analista_normalizar(texto))
            if p.strip(".") not in PALABRAS_VACIAS}


def Analista_normalizar(texto):
    from analista import normalizar
    return normalizar(texto).replace("/", " ")


class LectorHojaDeVida:
    """Convierte la hoja de vida (Word o texto) en secciones: nombre, contacto,
    titular, perfil, experiencia (empresa, cargo, fechas, viñetas), habilidades...
    Funciona con el formato de la hoja de vida que armamos y con otros parecidos."""

    SECCIONES = {"resumen": ["summary", "profile", "perfil", "objective", "about"],
                 "experiencia": ["experience", "employment", "work history", "experiencia"],
                 "proyectos": ["project", "proyecto"],
                 "habilidades": ["skill", "habilidad", "competenc", "technical"],
                 "educacion": ["education", "credential", "educacion", "certific", "formacion"]}

    @staticmethod
    def _lineas(hoja):
        """[(texto, es_vineta, es_titulo)] desde el Word, o desde el texto si no es Word."""
        ruta = Path(hoja.get("ruta", ""))
        if ruta.suffix.lower() == ".docx" and ruta.exists():
            import docx
            lineas = []
            for p in docx.Document(ruta).paragraphs:
                t = p.text.strip()
                if not t:
                    continue
                estilo = (p.style.name or "").lower()
                vineta = "list" in estilo or p._p.pPr is not None and p._p.pPr.numPr is not None
                titulo = estilo.startswith("heading") or (t.isupper() and len(t) < 45)
                lineas.append((t, vineta, titulo))
            return lineas
        lineas = []
        for t in hoja["texto"].splitlines():
            t = t.strip()
            if not t:
                continue
            vineta = t[:1] in "•-–*·"
            lineas.append((t.lstrip("•-–*· ").strip() if vineta else t, vineta,
                           t.isupper() and len(t) < 45))
        return lineas

    @classmethod
    def _seccion(cls, titulo):
        t = Analista_normalizar(titulo)
        for nombre, claves in cls.SECCIONES.items():
            if any(c in t for c in claves):
                return nombre
        return "otros"

    @classmethod
    def leer(cls, hoja):
        cv = {"nombre": "", "contacto": "", "titular": "", "lema": "", "resumen": "",
              "experiencia": [], "proyectos": [], "habilidades": [], "educacion": [], "otros": []}
        seccion, actual = None, None
        for texto, vineta, titulo in cls._lineas(hoja):
            if titulo:
                seccion, actual = cls._seccion(texto), None
                continue
            if seccion is None:                     # encabezado: antes del primer título
                if not cv["nombre"]:
                    cv["nombre"] = texto
                elif "@" in texto or re.search(r"\d{3}\D{0,2}\d{3}", texto):
                    cv["contacto"] = texto
                elif not cv["titular"]:
                    cv["titular"] = texto
                else:
                    cv["lema"] = texto
            elif seccion == "resumen":
                cv["resumen"] = (cv["resumen"] + " " + texto).strip()
            elif seccion in ("experiencia", "proyectos"):
                if vineta and actual:
                    actual["logros"].append(texto)
                elif actual and not actual["cargo"] and not actual["logros"]:
                    cargo, _, fechas = texto.partition(" · ")
                    actual["cargo"], actual["fechas"] = cargo.strip(), fechas.strip()
                else:
                    actual = {"empresa": texto, "cargo": "", "fechas": "", "lugar": "", "logros": []}
                    cv[seccion].append(actual)
            else:
                cv[seccion].append(texto)
        return cv


def primera_persona(frase):
    """Los perfiles suelen omitir el sujeto ("Has worked…", "Specializes in…").
    En una carta se lee mejor en primera persona: "I have worked…", "I specialize in…"."""
    primera, _, resto = frase.partition(" ")
    cambio = {"Has": "I have", "Is": "I am", "Was": "I was", "Brings": "I bring"}.get(primera)
    if not cambio and primera.endswith("ed"):
        cambio = "I " + primera.lower()
    elif not cambio and re.fullmatch(r"[A-Z][a-z]+(?<!s)s", primera):
        verbo = primera.lower()
        if verbo.endswith(("ches", "shes", "xes", "sses")) or (verbo.endswith("uses") and len(verbo) > 5):
            verbo = verbo[:-2]                  # teaches → teach, focuses → focus
        elif verbo.endswith("ies"):
            verbo = verbo[:-3] + "y"            # applies → apply
        else:
            verbo = verbo[:-1]                  # leads → lead
        cambio = "I " + verbo
    return f"{cambio} {resto}" if cambio else frase


class AdaptadorLocal(AdaptadorCV):
    """Adapta sin IA: compara las palabras de la oferta con las de la hoja de vida,
    pone primero lo más relacionado y arma carta y correo con plantillas.
    No redacta frases nuevas sobre la experiencia: solo ordena y resalta lo que ya existe."""
    nombre = "Sin IA (comparación de palabras)"

    @staticmethod
    def _puntaje(texto, terminos):
        return len(palabras(texto) & terminos)

    @staticmethod
    def _requisitos(oferta):
        lista = oferta.get("requisitos") or []
        if lista:
            return lista
        frases = re.split(r"(?<=[.!?])\s+", oferta.get("descripcion", ""))
        return [f for f in frases if re.search(r"experience|required|must|years|skills", f, re.I)][:8]

    @staticmethod
    def _correo(empresa, puesto, nombre, contacto, logros, habilidades):
        """Correo corto, armado con lo de la hoja de vida que responde a los requisitos de la oferta."""
        partes = [f"Hello {empresa} team,", "",
                  f"I am writing to apply for the {puesto} position. After reviewing the requirements, "
                  "these points from my experience match what you are looking for:"]
        partes += ["• " + l for l in logros]
        if habilidades:
            partes += ["", "Relevant skills for this role: " + ", ".join(habilidades) + "."]
        partes += ["", "I have attached my resume and a cover letter. I would be glad to talk "
                   "at your convenience.", "", "Best regards,", nombre]
        if contacto:
            partes.append(contacto)
        return "\n".join(partes)

    def adaptar(self, hoja, oferta):
        cv = LectorHojaDeVida.leer(hoja)
        texto_oferta = " ".join([oferta["titulo"], oferta.get("descripcion", "")] +
                                oferta.get("requisitos", []) + oferta.get("tareas", []))
        terminos = palabras(texto_oferta)
        texto_cv = hoja["texto"]
        vocabulario_cv = palabras(texto_cv)

        # Los requisitos y el título pesan doble al decidir qué es lo más relacionado
        clave = palabras(" ".join([oferta["titulo"]] + self._requisitos(oferta)))
        terminos = terminos | clave

        def relevancia(texto):
            p = palabras(texto)
            return 2 * len(p & clave) + len(p & terminos)

        # 1. Requisitos: «coincide» si al menos 40 % de sus palabras importantes están en la hoja de vida
        cumple, faltan = [], []
        for r in self._requisitos(oferta):
            propias = palabras(r)
            comunes = propias & vocabulario_cv
            (cumple if propias and len(comunes) >= max(1, round(0.4 * len(propias))) else faltan).append(r)

        # 2. Experiencia: cada empresa con sus viñetas más relacionadas primero
        experiencia = []
        for e in cv["experiencia"] + cv["proyectos"]:
            logros = sorted(e["logros"], key=lambda l: -relevancia(l))
            experiencia.append({**e, "logros": logros})

        # 3. Habilidades: las líneas y los elementos que menciona la oferta, primero
        habilidades = []
        for linea in cv["habilidades"]:
            etiqueta, _, items = linea.partition(":")
            elementos = [i.strip() for i in re.split(r",(?![^()]*\))", items or etiqueta) if i.strip()]
            habilidades.extend(elementos)
        habilidades.sort(key=lambda i: -relevancia(i))

        # 4. Perfil: las frases más relacionadas con la oferta van primero
        frases = re.split(r"(?<=[.!?])\s+", cv["resumen"])
        frases.sort(key=lambda f: -relevancia(f))
        resumen = " ".join(frases)

        # 5. Carta y correo con plantillas, usando sus logros más relacionados
        mejores = sorted((l for e in experiencia for l in e["logros"]),
                         key=lambda l: -relevancia(l))[:3]
        # Para el correo: los logros que más tocan los REQUISITOS, y las habilidades que la oferta pide
        def toca_requisitos(texto):
            return len(palabras(texto) & clave)
        para_correo = [l for l in sorted((l for e in experiencia for l in e["logros"]),
                                         key=lambda l: -toca_requisitos(l)) if toca_requisitos(l)][:3] or mejores
        habilidades_pedidas = [h for h in habilidades if palabras(h) & clave][:6]
        nombre = cv["nombre"] or "The candidate"
        puesto, empresa = oferta["titulo"].strip(), oferta["empresa"].strip()
        carta = (
            f"Dear {empresa} Hiring Team,\n"
            f"I am applying for the {puesto} position. {primera_persona(frases[0]) if frases else ''}\n"
            "Some of the experience most relevant to this role:\n"
            + "\n".join("• " + m for m in mejores) + "\n"
            "I would welcome the opportunity to discuss how I can contribute to your team. "
            "Thank you for your time and consideration.\n"
            f"Sincerely,\n{nombre}")
        return {
            "nombre": cv["nombre"], "contacto": cv["contacto"],
            "titular": cv["titular"], "lema": cv["lema"],
            "resumen_profesional": resumen,
            "habilidades": habilidades,
            "experiencia": experiencia,
            "educacion": cv["educacion"], "otros": cv["otros"],
            "cumple": cumple, "faltan": faltan,
            "consejos": ["Revise el perfil: las frases más relacionadas con la oferta quedaron primero.",
                         "Lo que está en «no aparece» solo agréguelo si de verdad lo tiene."] if faltan else [],
            "carta": carta,
            "asunto_correo": f"Application — {puesto} — {nombre}",
            "cuerpo_correo": self._correo(empresa, puesto, nombre, cv["contacto"],
                                          para_correo, habilidades_pedidas),
            "metodo": self.nombre,
        }


# =====================================================================
#  DOCUMENTOS WORD
# =====================================================================

class GeneradorDocumentos:
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)

    @staticmethod
    def _documento():
        import docx                             # pip install python-docx
        from docx.shared import Pt
        doc = docx.Document()
        estilo = doc.styles["Normal"]
        estilo.font.name, estilo.font.size = "Calibri", Pt(11)
        for s in doc.sections:
            s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = docx.shared.Inches(0.8)
        return doc

    @staticmethod
    def _titulo_seccion(doc, texto):
        from docx.shared import Pt, RGBColor
        p = doc.add_paragraph()
        r = p.add_run(texto.upper())
        r.bold, r.font.size, r.font.color.rgb = True, Pt(11.5), RGBColor(0x29, 0x53, 0x56)
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(10), Pt(2)

    @staticmethod
    def titulos(a):
        """Títulos de las secciones en el idioma en que está escrita la hoja de vida."""
        es = any(w in (a.get("resumen_profesional") or "").lower() for w in (" de ", " la ", " con "))
        return (("Perfil profesional", "Habilidades", "Experiencia", "Educación", "Otros") if es else
                ("Professional Summary", "Skills", "Experience", "Education & Credentials", "Additional"))

    def hoja_de_vida(self, a, base):
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor
        doc = self._documento()

        def centrado(texto, tam, negrita=False, color=None):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(texto); r.bold, r.font.size = negrita, Pt(tam)
            if color:
                r.font.color.rgb = color
            p.paragraph_format.space_after = Pt(2)

        centrado(a.get("nombre", ""), 20, True, RGBColor(0x29, 0x53, 0x56))
        for linea, tam, negrita in ((a.get("contacto"), 10, False), (a.get("titular"), 13, True),
                                    (a.get("lema"), 10, False)):
            if linea:
                centrado(linea, tam, negrita)
        titulos = self.titulos(a)
        self._titulo_seccion(doc, titulos[0]); doc.add_paragraph(a.get("resumen_profesional", ""))
        if a.get("habilidades"):
            self._titulo_seccion(doc, titulos[1]); doc.add_paragraph(" · ".join(a["habilidades"]))
        if a.get("experiencia"):
            self._titulo_seccion(doc, titulos[2])
            for e in a["experiencia"]:
                p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6)
                encabezado = " — ".join(x for x in (e.get("empresa"), e.get("lugar")) if x)
                p.add_run(encabezado).bold = True
                if e.get("cargo") or e.get("fechas"):
                    p = doc.add_paragraph()
                    r = p.add_run(e.get("cargo", "")); r.bold = r.italic = True
                    if e.get("fechas"):
                        p.add_run(" · " + e["fechas"])
                for logro in e.get("logros", []):
                    doc.add_paragraph(logro, style="List Bullet")
        for titulo, clave in ((titulos[3], "educacion"), (titulos[4], "otros")):
            if a.get(clave):
                self._titulo_seccion(doc, titulo)
                for item in a[clave]:
                    doc.add_paragraph(item, style="List Bullet")
        ruta = self.carpeta / f"{base}_hoja_de_vida.docx"
        doc.save(ruta)
        return ruta

    def carta(self, a, base):
        doc = self._documento()
        doc.add_paragraph(datetime.now().strftime("%B %d, %Y"))
        for parrafo in (a.get("carta") or "").split("\n"):
            if parrafo.strip():
                doc.add_paragraph(parrafo.strip())
        ruta = self.carpeta / f"{base}_carta.docx"
        doc.save(ruta)
        return ruta


# =====================================================================
#  DOCUMENTOS PDF (para verlos bien en el navegador y enviarlos)
# =====================================================================

class GeneradorPDF:
    """Arma la hoja de vida y la carta en PDF con reportlab (pip install reportlab).
    Recibe los mismos datos que GeneradorDocumentos, así el PDF y el Word dicen lo mismo."""
    VERDE = "#295356"

    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)

    @staticmethod
    def disponible():
        try:
            import reportlab                    # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _fuentes():
        """Usa Calibri si está en Windows; si no, Helvetica (viene con reportlab)."""
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        fuentes = Path("C:/Windows/Fonts")
        try:
            if "Calibri" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("Calibri", str(fuentes / "calibri.ttf")))
                pdfmetrics.registerFont(TTFont("Calibri-Bold", str(fuentes / "calibrib.ttf")))
                pdfmetrics.registerFont(TTFont("Calibri-Italic", str(fuentes / "calibrii.ttf")))
                from reportlab.lib.fonts import addMapping
                addMapping("Calibri", 0, 0, "Calibri"); addMapping("Calibri", 1, 0, "Calibri-Bold")
                addMapping("Calibri", 0, 1, "Calibri-Italic"); addMapping("Calibri", 1, 1, "Calibri-Bold")
            return "Calibri", "Calibri-Bold"
        except Exception:
            return "Helvetica", "Helvetica-Bold"

    def _estilos(self):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.styles import ParagraphStyle
        normal, negrita = self._fuentes()
        base = ParagraphStyle("base", fontName=normal, fontSize=10.5, leading=14, spaceAfter=3)
        return {
            "base": base,
            "nombre": ParagraphStyle("nombre", parent=base, fontName=negrita, fontSize=20, leading=24,
                                     alignment=TA_CENTER, textColor=HexColor(self.VERDE)),
            "centro": ParagraphStyle("centro", parent=base, alignment=TA_CENTER, spaceAfter=1),
            "titular": ParagraphStyle("titular", parent=base, fontName=negrita, fontSize=12.5,
                                      alignment=TA_CENTER, leading=16),
            "seccion": ParagraphStyle("seccion", parent=base, fontName=negrita, fontSize=11.5,
                                      textColor=HexColor(self.VERDE), spaceBefore=10, spaceAfter=3),
            "empresa": ParagraphStyle("empresa", parent=base, fontName=negrita, spaceBefore=6, spaceAfter=0),
            "vineta": ParagraphStyle("vineta", parent=base, leftIndent=14, bulletIndent=4, spaceAfter=1),
        }

    def _documento(self, ruta):
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate
        return SimpleDocTemplate(str(ruta), pagesize=LETTER, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                                 topMargin=0.7 * inch, bottomMargin=0.7 * inch)

    @staticmethod
    def _x(texto):
        from xml.sax.saxutils import escape
        return escape(texto or "")

    def hoja_de_vida(self, a, base, sufijo="hoja_de_vida"):
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import HRFlowable, Paragraph
        e, x = self._estilos(), self._x
        hist = [Paragraph(x(a.get("nombre", "")), e["nombre"])]
        for clave, estilo in (("contacto", "centro"), ("titular", "titular"), ("lema", "centro")):
            if a.get(clave):
                hist.append(Paragraph(x(a[clave]), e[estilo]))
        hist.append(HRFlowable(width="100%", thickness=1, color=HexColor(self.VERDE), spaceBefore=6, spaceAfter=2))
        titulos = GeneradorDocumentos.titulos(a)

        def seccion(titulo):
            hist.append(Paragraph(x(titulo.upper()), e["seccion"]))

        if a.get("resumen_profesional"):
            seccion(titulos[0]); hist.append(Paragraph(x(a["resumen_profesional"]), e["base"]))
        if a.get("habilidades"):
            seccion(titulos[1]); hist.append(Paragraph(x(" · ".join(a["habilidades"])), e["base"]))
        if a.get("experiencia"):
            seccion(titulos[2])
            for exp in a["experiencia"]:
                encabezado = " — ".join(v for v in (exp.get("empresa"), exp.get("lugar")) if v)
                hist.append(Paragraph(x(encabezado), e["empresa"]))
                if exp.get("cargo") or exp.get("fechas"):
                    linea = f"<b><i>{x(exp.get('cargo', ''))}</i></b>"
                    if exp.get("fechas"):
                        linea += " · " + x(exp["fechas"])
                    hist.append(Paragraph(linea, e["base"]))
                for logro in exp.get("logros", []):
                    hist.append(Paragraph(x(logro), e["vineta"], bulletText="•"))
        for titulo, clave in ((titulos[3], "educacion"), (titulos[4], "otros")):
            if a.get(clave):
                seccion(titulo)
                for item in a[clave]:
                    hist.append(Paragraph(x(item), e["vineta"], bulletText="•"))
        ruta = self.carpeta / f"{base}_{sufijo}.pdf"
        self._documento(ruta).build(hist)
        return ruta

    def carta(self, a, base):
        from reportlab.platypus import Paragraph, Spacer
        e, x = self._estilos(), self._x
        hist = [Paragraph(datetime.now().strftime("%B %d, %Y"), e["base"]), Spacer(1, 10)]
        for parrafo in (a.get("carta") or "").split("\n"):
            if parrafo.strip().startswith("•"):
                hist.append(Paragraph(x(parrafo.strip().lstrip("• ")), e["vineta"], bulletText="•"))
            elif parrafo.strip():
                hist.append(Paragraph(x(parrafo.strip()), e["base"]))
                hist.append(Spacer(1, 4))
        ruta = self.carpeta / f"{base}_carta.pdf"
        self._documento(ruta).build(hist)
        return ruta


# =====================================================================
#  CORREO
# =====================================================================

class Remitente:
    """Clase padre. Cada usuario tendrá su Remitente con su propia cuenta."""

    def enviar(self, para, asunto, cuerpo, adjuntos):
        raise NotImplementedError


class RemitenteSMTP(Remitente):
    def __init__(self, credenciales):
        self.c = credenciales.leer()["correo"]

    def enviar(self, para, asunto, cuerpo, adjuntos):
        if not (self.c["remitente"] and self.c["clave_app"]):
            raise ValueError(t("Falta configurar el correo de envío en «Configuración»."))
        if not CORREO_EN_TEXTO.fullmatch(para.strip()):
            raise ValueError(t("El correo del destinatario no es válido."))
        msg = EmailMessage()
        msg["From"] = f'{self.c["nombre"]} <{self.c["remitente"]}>' if self.c["nombre"] else self.c["remitente"]
        msg["To"], msg["Subject"] = para.strip(), asunto
        msg.set_content(cuerpo)
        for ruta in adjuntos:
            ruta = Path(ruta)
            tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
            principal, _, sub = tipo.partition("/")
            msg.add_attachment(ruta.read_bytes(), maintype=principal, subtype=sub, filename=ruta.name)
        puerto = int(self.c["puerto"])
        if puerto == 465:
            with smtplib.SMTP_SSL(self.c["servidor"], puerto, context=ssl.create_default_context(), timeout=30) as s:
                s.login(self.c["remitente"], self.c["clave_app"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.c["servidor"], puerto, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(self.c["remitente"], self.c["clave_app"])
                s.send_message(msg)


# =====================================================================
#  ORQUESTADOR: una aplicación completa
# =====================================================================

class Aplicacion:
    """Prepara (y guarda) todo lo de una oferta: adaptación, Word y borrador de correo."""

    def __init__(self, hoja_de_vida, elegir_adaptador, generador, generador_pdf=None):
        """elegir_adaptador: función que devuelve el adaptador a usar (con o sin IA)."""
        self.hdv, self.elegir_adaptador, self.generador = hoja_de_vida, elegir_adaptador, generador
        self.pdf = generador_pdf

    @staticmethod
    def correo_del_empleador(oferta):
        correos = [c.rstrip(".") for c in CORREO_EN_TEXTO.findall(oferta.get("descripcion", ""))
                   if not re.search(r"no-?reply|example\.com", c, re.I)]
        return correos[0] if correos else ""

    def ruta_ficha(self, url):
        import hashlib
        return self.hdv.adaptadas / f"{hashlib.md5(url.encode()).hexdigest()[:12]}.json"

    def cargar(self, url):
        ruta = self.ruta_ficha(url)
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None

    def preparar(self, oferta, adaptar=True):
        """adaptar=False: se envía una copia exacta de la original (la carta sí se arma)."""
        datos = self.hdv.datos()
        if not datos:
            raise ValueError(t("Primero suba su hoja de vida."))
        hoja = {"texto": datos["texto"], "ruta": str(self.hdv.original / datos["archivo"])}
        adaptador = self.elegir_adaptador() if adaptar else AdaptadorLocal()
        adaptada = adaptador.adaptar(hoja, oferta)
        adaptada.setdefault("metodo", adaptador.nombre)
        base = datetime.now().strftime("%Y%m%d") + "_" + nombre_archivo(oferta["empresa"], 25) \
            + "_" + nombre_archivo(oferta["titulo"], 30)
        if adaptar:
            archivo_cv = self.generador.hoja_de_vida(adaptada, base).name
        else:                                   # copia exacta; el original no se toca
            original = Path(hoja["ruta"])
            archivo_cv = f"{base}_hoja_de_vida_original{original.suffix}"
            (self.hdv.adaptadas / archivo_cv).write_bytes(original.read_bytes())
        ficha = {
            "url": oferta["url"], "titulo": oferta["titulo"], "empresa": oferta["empresa"],
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "adaptada": adaptada, "adaptar": adaptar,
            "archivo_cv": archivo_cv,
            "archivo_carta": self.generador.carta(adaptada, base).name,
            "correo_empleador": self.correo_del_empleador(oferta),
            "original": datos["archivo"],
            "pdf_cv": None, "pdf_carta": None,
        }
        if self.pdf and self.pdf.disponible():
            if adaptar:
                contenido, sufijo = adaptada, "hoja_de_vida"
            else:                               # el original, leído tal cual (sin reordenar nada)
                cv = LectorHojaDeVida.leer(hoja)
                contenido = {**cv, "resumen_profesional": cv["resumen"],
                             "experiencia": cv["experiencia"] + cv["proyectos"]}
                sufijo = "hoja_de_vida_original"
            ficha["pdf_cv"] = self.pdf.hoja_de_vida(contenido, base, sufijo).name
            ficha["pdf_carta"] = self.pdf.carta(adaptada, base).name
        self.ruta_ficha(oferta["url"]).write_text(json.dumps(ficha, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        return ficha
