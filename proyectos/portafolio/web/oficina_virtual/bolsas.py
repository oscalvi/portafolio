"""Más bolsas de empleo y las páginas de empleo de las empresas, para ver el mercado completo.

ESTRUCTURA
    Bolsas públicas (sin clave)      Himalayas · Remote OK · We Work Remotely · The Muse
    Bolsa con clave gratuita         Adzuna (reúne ofertas de miles de sitios; clave en Configuración)
    EmpresasSeguidas                 Las empresas que el usuario sigue (configuraciones/empresas_seguidas.json)
    FuenteEmpresa                    Las vacantes publicadas por la propia empresa en su sistema de empleo:
                                     Greenhouse, Lever, Ashby o Workable (páginas públicas hechas para compartirse)
    OTRAS_BOLSAS                     Dice, Monster, Indeed, LinkedIn… no permiten que un programa lea sus ofertas:
                                     se abren con la búsqueda ya escrita y la oferta que interese se importa a mano.
    importar_oferta()                Crea la oferta a partir del enlace y el texto que el usuario pega.
    panorama()                       Resumen del mercado: fuentes, empresas, habilidades pedidas, tipos y salarios.

Cada oferta enlaza a su publicación original y muestra su fuente, como piden los términos de cada sitio.
"""
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from empleos import FuenteEmpleos, Oferta, Resumidor, normalizar, sin_html
from idiomas import t


def _fecha(valor):
    """Fecha AAAA-MM-DD a partir de texto ISO, segundos o milisegundos."""
    if valor in (None, ""):
        return ""
    if isinstance(valor, (int, float)) or str(valor).isdigit():
        n = int(valor)
        n = n / 1000 if n > 10 ** 11 else n
        return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
    texto = str(valor)
    if re.match(r"\d{4}-\d{2}-\d{2}", texto):
        return texto[:10]
    try:                                            # RSS: "Thu, 29 Oct 2026 14:00:00 +0000"
        return datetime.strptime(texto[:25].strip(), "%a, %d %b %Y %H:%M:%S").date().isoformat()
    except ValueError:
        return ""


def _salario(minimo, maximo, moneda="", periodo=""):
    if not minimo and not maximo:
        return ""
    minimo, maximo = minimo or maximo, maximo or minimo
    rango = f"{int(minimo):,}" if minimo == maximo else f"{int(minimo):,}–{int(maximo):,}"
    return " ".join(x for x in (rango, moneda or "", periodo or "") if x).strip()


def _primeros(terminos, n=3):
    return [p for p in (terminos or []) if p.strip()][:n]


# =====================================================================
#  BOLSAS PÚBLICAS
# =====================================================================

class Himalayas(FuenteEmpleos):
    """himalayas.app: API pública de búsqueda. Pide enlazar a Himalayas y usar su enlace de aplicación."""
    nombre = "Himalayas"
    sitio = "https://himalayas.app/jobs"
    url = "https://himalayas.app/jobs/api"
    minutos_cache = 12 * 60                         # sus datos se renuevan una vez al día
    por_busqueda = True

    def traer(self, terminos=None):
        lotes = []
        palabras = _primeros(terminos) or [""]
        for palabra in palabras:
            for pagina in (1, 2):
                q = urllib.parse.urlencode({"q": palabra, "sort": "recent", "page": pagina})
                datos = self.descargar(f"https://himalayas.app/jobs/api/search?{q}") or {}
                lotes += datos.get("jobs") or []
                if len(datos.get("jobs") or []) < 20:
                    break
        return lotes

    def convertir(self, datos):
        ofertas = []
        for j in datos:
            enlace = j.get("guid") if str(j.get("guid", "")).startswith("http") else j.get("applicationLink")
            if not enlace:
                continue
            ofertas.append(Oferta(
                fuente=self.nombre, url=enlace, titulo=j.get("title", ""), empresa=j.get("companyName", ""),
                tipo=j.get("employmentType", ""), ubicacion=", ".join(j.get("locationRestrictions") or []) or "Remote",
                salario=_salario(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod")),
                categoria=", ".join(j.get("categories") or []), fecha=_fecha(j.get("pubDate")),
                descripcion=j.get("description") or j.get("excerpt", "")))
        return ofertas


class RemoteOK(FuenteEmpleos):
    """remoteok.com: las 100 ofertas más nuevas. Pide enlazar a la oferta en Remote OK y nombrarlo como fuente."""
    nombre = "Remote OK"
    sitio = "https://remoteok.com"
    url = "https://remoteok.com/api"
    minutos_cache = 6 * 60

    def convertir(self, datos):
        ofertas = []
        for j in (datos or [])[1:]:                 # el primer elemento es el aviso legal
            if not isinstance(j, dict) or not j.get("url"):
                continue
            ofertas.append(Oferta(
                fuente=self.nombre, url=j["url"], titulo=j.get("position", ""), empresa=j.get("company", ""),
                tipo="", ubicacion=j.get("location") or "Remote",
                salario=_salario(j.get("salary_min"), j.get("salary_max"), "USD", "year"),
                categoria=", ".join(j.get("tags") or []), fecha=_fecha(j.get("date") or j.get("epoch")),
                descripcion=j.get("description", "")))
        return ofertas


class WeWorkRemotely(FuenteEmpleos):
    """weworkremotely.com: sus canales RSS públicos. Piden enlazar de vuelta a We Work Remotely."""
    nombre = "We Work Remotely"
    sitio = "https://weworkremotely.com"
    url = "https://weworkremotely.com/remote-jobs.rss"
    minutos_cache = 6 * 60
    CANALES = ["https://weworkremotely.com/remote-jobs.rss",
               "https://weworkremotely.com/categories/remote-programming-jobs.rss"]

    def traer(self, terminos=None):
        return [self.descargar(c, formato="xml") for c in self.CANALES]

    def convertir(self, datos):
        ofertas = []
        for xml in datos:
            try:
                raiz = ET.fromstring(xml)
            except ET.ParseError:
                continue
            for item in raiz.iter("item"):
                dato = lambda tag: (item.findtext(tag) or "").strip()
                titulo = dato("title")
                empresa, _, puesto = titulo.partition(": ")
                if not puesto:
                    empresa, puesto = "", titulo
                ofertas.append(Oferta(
                    fuente=self.nombre, url=dato("link"), titulo=puesto, empresa=empresa, tipo=dato("type"),
                    ubicacion=dato("region") or "Remote", categoria=dato("category"), fecha=_fecha(dato("pubDate")),
                    descripcion=dato("description")))
        return ofertas


class TheMuse(FuenteEmpleos):
    """themuse.com: API pública (500 consultas por hora sin clave)."""
    nombre = "The Muse"
    sitio = "https://www.themuse.com"
    url = "https://www.themuse.com/api/public/jobs"
    minutos_cache = 12 * 60
    CATEGORIAS = ["Software Engineering", "Data and Analytics", "IT"]

    def traer(self, terminos=None):
        lotes = []
        for categoria in self.CATEGORIAS:
            for pagina in (0, 1):
                q = urllib.parse.urlencode({"page": pagina, "descending": "true", "category": categoria,
                                            "location": "Flexible / Remote"})
                lotes += (self.descargar(f"{self.url}?{q}") or {}).get("results") or []
        return lotes

    def convertir(self, datos):
        return [Oferta(fuente=self.nombre, url=(j.get("refs") or {}).get("landing_page", ""), titulo=j.get("name", ""),
                       empresa=(j.get("company") or {}).get("name", ""),
                       tipo=", ".join(l.get("name", "") for l in j.get("levels") or []),
                       ubicacion=", ".join(l.get("name", "") for l in j.get("locations") or []),
                       categoria=", ".join(c.get("name", "") for c in j.get("categories") or []),
                       fecha=_fecha(j.get("publication_date")), descripcion=j.get("contents", ""))
                for j in datos if (j.get("refs") or {}).get("landing_page")]


class Adzuna(FuenteEmpleos):
    """adzuna.com: reúne ofertas de miles de sitios de empleo. Necesita una clave gratuita (Configuración)."""
    nombre = "Adzuna"
    sitio = "https://www.adzuna.com"
    url = "https://api.adzuna.com/v1/api/jobs"
    minutos_cache = 6 * 60                          # la clave gratuita permite 250 consultas al día
    por_busqueda = True

    def __init__(self, carpeta_cache, app_id, app_key, pais="us"):
        super().__init__(carpeta_cache)
        self.app_id, self.app_key, self.pais = app_id, app_key, (pais or "us").lower()

    def traer(self, terminos=None):
        lotes = []
        for palabra in _primeros(terminos) or ["remote"]:
            q = urllib.parse.urlencode({"app_id": self.app_id, "app_key": self.app_key, "what": palabra,
                                        "results_per_page": 50, "sort_by": "date", "content-type": "application/json"})
            lotes += (self.descargar(f"{self.url}/{self.pais}/search/1?{q}") or {}).get("results") or []
        return lotes

    def _ruta_cache(self, url=None):                # la clave no se usa en el nombre del archivo de caché
        return super()._ruta_cache(re.sub(r"app_(id|key)=[^&]+", "", url or self.url))

    def convertir(self, datos):
        tipos = {"full_time": "Full time", "part_time": "Part time", "contract": "Contract", "permanent": "Permanent"}
        return [Oferta(fuente=self.nombre, url=j.get("redirect_url", ""), titulo=sin_html(j.get("title", "")),
                       empresa=(j.get("company") or {}).get("display_name", ""),
                       tipo=", ".join(tipos.get(j.get(k), "") for k in ("contract_time", "contract_type") if j.get(k)),
                       ubicacion=(j.get("location") or {}).get("display_name", ""),
                       salario="" if j.get("salary_is_predicted") in (1, "1") else _salario(j.get("salary_min"), j.get("salary_max"), "USD", "year"),
                       categoria=(j.get("category") or {}).get("label", ""), fecha=_fecha(j.get("created")),
                       descripcion=j.get("description", ""))
                for j in datos if j.get("redirect_url")]


# =====================================================================
#  PÁGINAS DE EMPLEO DE LAS EMPRESAS
# =====================================================================

ATS = {
    "greenhouse": {"nombre": "Greenhouse", "patron": r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)",
                   "api": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
                   "pagina": "https://job-boards.greenhouse.io/{slug}"},
    "lever": {"nombre": "Lever", "patron": r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)",
              "api": "https://api.lever.co/v0/postings/{slug}?mode=json", "pagina": "https://jobs.lever.co/{slug}"},
    "ashby": {"nombre": "Ashby", "patron": r"jobs\.ashbyhq\.com/([\w.%-]+)",
              "api": "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
              "pagina": "https://jobs.ashbyhq.com/{slug}"},
    "workable": {"nombre": "Workable", "patron": r"apply\.workable\.com/([\w-]+)",
                 "api": "https://www.workable.com/api/accounts/{slug}?details=true", "pagina": "https://apply.workable.com/{slug}"},
}

# Empresas conocidas que publican así (para agregarlas con un clic). Si alguna cambia de sistema, la búsqueda lo avisa.
SUGERIDAS = [
    {"nombre": "Anthropic", "ats": "greenhouse", "slug": "anthropic"},
    {"nombre": "OpenAI", "ats": "ashby", "slug": "openai"},
    {"nombre": "Scale AI", "ats": "greenhouse", "slug": "scaleai"},
]


def detectar_ats(enlace):
    """('greenhouse', 'anthropic') a partir del enlace de la página de empleos; (None, None) si no se reconoce."""
    for clave, datos in ATS.items():
        m = re.search(datos["patron"], enlace or "", re.I)
        if m:
            return clave, urllib.parse.unquote(m.group(1)).strip("/")
    return None, None


class FuenteEmpresa(FuenteEmpleos):
    """Las vacantes que publica la propia empresa en su página de empleos."""
    minutos_cache = 6 * 60

    def __init__(self, carpeta_cache, empresa):
        super().__init__(carpeta_cache)
        self.empresa = empresa
        self.ats = empresa["ats"]
        self.nombre = f"{empresa['nombre']} ({ATS[self.ats]['nombre']})"
        self.url = ATS[self.ats]["api"].format(slug=urllib.parse.quote(empresa["slug"]))
        self.sitio = ATS[self.ats]["pagina"].format(slug=empresa["slug"])

    def convertir(self, datos):
        e, nombre = self.empresa, self.empresa["nombre"]
        ofertas = []
        if self.ats == "greenhouse":
            for j in (datos or {}).get("jobs", []):
                ofertas.append(Oferta(fuente=self.nombre, url=j.get("absolute_url", ""), titulo=j.get("title", ""),
                                      empresa=j.get("company_name") or nombre, ubicacion=(j.get("location") or {}).get("name", ""),
                                      fecha=_fecha(j.get("updated_at")), descripcion=sin_html_escapado(j.get("content", ""))))
        elif self.ats == "lever":
            for j in datos or []:
                c = j.get("categories") or {}
                partes = [j.get("description") or j.get("descriptionPlain", "")]
                partes += [f"<h3>{l.get('text', '')}</h3><ul>{l.get('content', '')}</ul>" for l in j.get("lists") or []]
                partes.append(j.get("additional", ""))
                s = j.get("salaryRange") or {}
                ofertas.append(Oferta(fuente=self.nombre, url=j.get("hostedUrl", ""), titulo=j.get("text", ""), empresa=nombre,
                                      tipo=c.get("commitment", ""), ubicacion=c.get("location", "") or j.get("workplaceType", ""),
                                      salario=_salario(s.get("min"), s.get("max"), s.get("currency"), s.get("interval")),
                                      categoria=c.get("team", ""), fecha=_fecha(j.get("createdAt")), descripcion="".join(partes)))
        elif self.ats == "ashby":
            for j in (datos or {}).get("jobs", []):
                comp = (j.get("compensation") or {}).get("scrapeableCompensationSalarySummary") or ""
                ubic = j.get("location", "") + (" · Remote" if j.get("isRemote") else "")
                ofertas.append(Oferta(fuente=self.nombre, url=j.get("jobUrl", ""), titulo=j.get("title", ""), empresa=nombre,
                                      tipo=j.get("employmentType", ""), ubicacion=ubic, salario=comp,
                                      categoria=j.get("department", "") or j.get("team", ""), fecha=_fecha(j.get("publishedAt")),
                                      descripcion=j.get("descriptionHtml") or j.get("descriptionPlain", "")))
        elif self.ats == "workable":
            for j in (datos or {}).get("jobs", []):
                lugar = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
                ofertas.append(Oferta(fuente=self.nombre, url=j.get("url") or j.get("shortlink", ""), titulo=j.get("title", ""),
                                      empresa=nombre, tipo=j.get("employment_type", ""),
                                      ubicacion=(lugar + (" · Remote" if j.get("telecommuting") else "")).strip(" ·"),
                                      categoria=j.get("department", "") or j.get("function", ""),
                                      fecha=_fecha(j.get("published_on") or j.get("created_at")), descripcion=j.get("description", "")))
        return [o for o in ofertas if o.url]


def sin_html_escapado(texto):
    """Greenhouse entrega el HTML de la descripción escapado (&lt;p&gt;…)."""
    import html
    return html.unescape(texto or "")


class EmpresasSeguidas:
    """Lista de empresas cuyas páginas de empleo se consultan en cada búsqueda (archivo privado del usuario)."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)

    def lista(self):
        try:
            return json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _guardar(self, lista):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")

    def agregar(self, nombre, enlace="", ats=None, slug=None):
        if enlace and not (ats and slug):
            ats, slug = detectar_ats(enlace)
        if not ats or ats not in ATS or not slug:
            raise ValueError(t("No reconozco el sistema de empleos de esa página. Funciona con páginas de Greenhouse, "
                               "Lever, Ashby o Workable; las demás ofertas se pueden importar una por una."))
        nombre = (nombre or slug.replace("-", " ").title()).strip()
        lista = [e for e in self.lista() if not (e["ats"] == ats and e["slug"].lower() == slug.lower())]
        lista.append({"nombre": nombre, "ats": ats, "slug": slug})
        self._guardar(sorted(lista, key=lambda e: e["nombre"].lower()))
        return {"nombre": nombre, "ats": ats, "slug": slug}

    def quitar(self, ats, slug):
        self._guardar([e for e in self.lista() if not (e["ats"] == ats and e["slug"] == slug)])

    def fuentes(self, carpeta_cache):
        return [FuenteEmpresa(carpeta_cache, e) for e in self.lista() if e.get("ats") in ATS]


# =====================================================================
#  OTRAS BOLSAS: se abren con la búsqueda escrita (no permiten lectura automática)
# =====================================================================

OTRAS_BOLSAS = [
    ("Dice", "https://www.dice.com/jobs?q={q}&location=Remote"),
    ("Monster", "https://www.monster.com/jobs/search?q={q}&where=remote"),
    ("Indeed", "https://www.indeed.com/jobs?q={q}&l=Remote"),
    ("LinkedIn", "https://www.linkedin.com/jobs/search/?keywords={q}&f_WT=2"),
    ("ZipRecruiter", "https://www.ziprecruiter.com/jobs-search?search={q}&location=Remote"),
    ("Glassdoor", "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q}&remoteWorkType=1"),
    ("USAJOBS", "https://www.usajobs.gov/search/results/?k={q}&hp=public"),
]


def enlaces_otras_bolsas(terminos):
    q = urllib.parse.quote_plus(" ".join(_primeros(terminos, 1)) or "remote")
    return [{"nombre": n, "url": u.format(q=q)} for n, u in OTRAS_BOLSAS]


def importar_oferta(enlace, texto, titulo="", empresa="", ubicacion="", tipo=""):
    """Una oferta de cualquier sitio, a partir del enlace y del texto que el usuario copió de la página."""
    enlace = (enlace or "").strip()
    if not re.match(r"https?://", enlace):
        raise ValueError(t("Pegue el enlace completo de la oferta (empieza por https://)."))
    texto = (texto or "").strip()
    if len(texto) < 80:
        raise ValueError(t("Pegue el texto de la oferta (la descripción completa), para poder evaluarla."))
    dominio = urllib.parse.urlparse(enlace).netloc.lower().removeprefix("www.")
    sitio = next((n for n, u in OTRAS_BOLSAS if urllib.parse.urlparse(u).netloc.removeprefix("www.") == dominio), dominio)
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    html = "".join(f"<p>{l}</p>" for l in lineas)
    oferta = Oferta(fuente=t("{sitio} (importada)", sitio=sitio), url=enlace, titulo=(titulo or lineas[0])[:200],
                    empresa=empresa or "—", tipo=tipo, ubicacion=ubicacion, fecha=datetime.now().date().isoformat(),
                    descripcion=html)
    Resumidor.resumir(oferta)
    return oferta


# =====================================================================
#  PANORAMA DEL MERCADO
# =====================================================================

HABILIDADES = ["Python", "Java", "JavaScript", "TypeScript", "C#", ".NET", "C++", "Go", "Rust", "SQL", "PostgreSQL",
               "Oracle", "SQL Server", "MongoDB", "React", "Node.js", "Django", "Flask", "AWS", "Azure", "GCP", "Docker",
               "Kubernetes", "Linux", "Git", "CI/CD", "REST", "GraphQL", "Machine Learning", "LLM", "AI", "Data Analysis",
               "Excel", "Power BI", "Tableau", "Salesforce", "SAP", "Agile", "Scrum", "Project Management", "COBOL",
               "Testing", "QA", "Security", "Spanish", "Customer Service"]


def panorama(ofertas):
    """Cuántas ofertas hay por fuente y tipo, qué empresas y habilidades aparecen más y qué salarios se publican."""
    if not ofertas:
        return None
    por_fuente = Counter(o.fuente for o in ofertas)
    empresas = Counter(o.empresa for o in ofertas if o.empresa and o.empresa != "—")
    habilidades = Counter()
    for o in ofertas:
        texto = f" {o.titulo} {o.categoria} {o.descripcion} "
        for h in HABILIDADES:
            patron = r"(?<![\w.#+])" + re.escape(h) + r"(?![\w#+])"
            if re.search(patron, texto, re.I if len(h) > 3 else 0):
                habilidades[h] += 1
    tipos = Counter()
    for o in ofertas:
        n = normalizar(f"{o.tipo} {o.titulo}")
        tipos[t("Contrato / freelance") if re.search(r"contract|freelance|contractor", n) else
              t("Medio tiempo") if re.search(r"part.?time", n) else
              t("Tiempo completo") if re.search(r"full.?time|permanent", n) else t("No indicado")] += 1
    anuales = []
    for o in ofertas:
        numeros = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{3,}", o.salario or "")]
        numeros += [int(float(x) * 1000) for x in re.findall(r"(\d+(?:\.\d+)?)\s?[kK]\b", o.salario or "")]
        if numeros and not re.search(r"hour|hora|month|mes", o.salario or "", re.I):
            anuales.append(sum(numeros[:2]) / len(numeros[:2]))
    anuales.sort()
    return {"total": len(ofertas), "por_fuente": por_fuente.most_common(),
            "empresas": empresas.most_common(10), "habilidades": habilidades.most_common(14),
            "tipos": tipos.most_common(), "con_salario": len(anuales),
            "salario_mediana": round(anuales[len(anuales) // 2], -3) if anuales else None,
            "salario_rango": (round(anuales[0], -3), round(anuales[-1], -3)) if anuales else None,
            "remotas": sum(1 for o in ofertas if re.search(r"remote|anywhere|worldwide|remoto", normalizar(o.ubicacion + " " + o.titulo)))}
