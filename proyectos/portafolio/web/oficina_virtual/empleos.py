"""Buscador de empleadores: trabajos remotos, temporales y administrativos.

ESTRUCTURA
    FuenteEmpleos            Clase padre: descarga con caché y convierte a Oferta.
    ├── Remotive             remotive.com  (máximo 4 descargas al día, según sus términos)
    ├── Jobicy               jobicy.com    (máximo 1 descarga por hora)
    └── (más bolsas y las páginas de empleo de las empresas en bolsas.py)
    Evaluador                Califica cada oferta contra criterios_empleo.json.
    BuscadorEmpleos          Junta las fuentes, filtra, quita repetidas y ordena.
    RegistroEmpleos          Guarda empresas y ofertas en la base (usa Administracion y Datos).

Para agregar una bolsa de empleo nueva: una subclase de FuenteEmpleos con
descargar() y convertir(). Los criterios se cambian en criterios_empleo.json.

Las ofertas siempre enlazan a la publicación original y se muestra la fuente,
como lo piden los términos de uso de Remotive y Jobicy.
"""
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from basedatos import Administracion, Conexion, Datos
from idiomas import t


def normalizar(texto):
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def sin_html(texto):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))).strip()


@dataclass
class Oferta:
    fuente: str
    url: str
    titulo: str
    empresa: str
    tipo: str = ""
    ubicacion: str = ""
    salario: str = ""
    categoria: str = ""
    fecha: str = ""
    descripcion: str = ""
    resumen: str = ""
    tareas: list = field(default_factory=list)
    requisitos: list = field(default_factory=list)
    puntaje: int = 0
    razones: list = field(default_factory=list)
    alertas: list = field(default_factory=list)
    es_temporal: bool = False           # banderas que pone el Evaluador (sirven en cualquier idioma)
    es_administrativa: bool = False
    fuera_de_zona: bool = False
    sospechosa: bool = False


# =====================================================================
#  FUENTES
# =====================================================================

class FuenteEmpleos:
    nombre = "Fuente"
    sitio = ""
    url = ""
    minutos_cache = 60

    def __init__(self, carpeta_cache):
        self.carpeta_cache = Path(carpeta_cache)
        self.carpeta_cache.mkdir(exist_ok=True)

    agente = "PY-Training-JobFinder/1.0 (+https://github.com/oscalvi/portafolio)"
    por_busqueda = False                    # True: la fuente busca con las palabras (no trae todo el listado)

    def _ruta_cache(self, url=None):
        clave = hashlib.md5((url or self.url).encode()).hexdigest()[:10]
        return self.carpeta_cache / f"{re.sub(r'[^a-z0-9]+', '_', self.nombre.lower())}_{clave}.json"

    def descargar(self, url=None, formato="json"):
        """Trae el JSON (o el XML de un RSS, como texto) de la fuente, usando la copia guardada si es reciente."""
        url = url or self.url
        ruta = self._ruta_cache(url)
        if ruta.exists() and time.time() - ruta.stat().st_mtime < self.minutos_cache * 60:
            return json.loads(ruta.read_text(encoding="utf-8"))
        pedido = urllib.request.Request(url, headers={"User-Agent": self.agente, "Accept": "application/json, application/xml, */*"})
        with urllib.request.urlopen(pedido, timeout=25) as respuesta:
            datos = json.load(respuesta) if formato == "json" else respuesta.read().decode("utf-8", "replace")
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        return datos

    def edad_cache(self):
        """Minutos desde la última descarga (None si nunca se ha descargado)."""
        rutas = list(self.carpeta_cache.glob(self._ruta_cache().name.rsplit("_", 1)[0] + "_*.json"))
        return int((time.time() - max(r.stat().st_mtime for r in rutas)) / 60) if rutas else None

    def traer(self, terminos=None):
        """Los datos crudos. Las fuentes que buscan con palabras lo cambian (varias consultas)."""
        return self.descargar()

    def convertir(self, datos):
        """Convierte el JSON de la fuente en una lista de Oferta."""
        raise NotImplementedError

    def ofertas(self, terminos=None):
        """Ofertas listas: con resumen, tareas y requisitos sacados de la descripción."""
        lista = self.convertir(self.traer(terminos))
        for o in lista:                     # convertir() deja la descripción en HTML
            Resumidor.resumir(o)
        return lista


class Remotive(FuenteEmpleos):
    nombre = "Remotive"
    sitio = "https://remotive.com"
    url = "https://remotive.com/api/remote-jobs"
    minutos_cache = 6 * 60                  # sus términos piden máximo 4 descargas al día

    def convertir(self, datos):
        return [Oferta(fuente=self.nombre, url=j["url"], titulo=j["title"],
                       empresa=j["company_name"], tipo=j.get("job_type", ""),
                       ubicacion=j.get("candidate_required_location", ""),
                       salario=j.get("salary", ""), categoria=j.get("category", ""),
                       fecha=(j.get("publication_date") or "")[:10],
                       descripcion=j.get("description", ""))
                for j in datos.get("jobs", [])]


class Jobicy(FuenteEmpleos):
    nombre = "Jobicy"
    sitio = "https://jobicy.com"
    url = "https://jobicy.com/api/jobs?count=200&geo=usa"
    minutos_cache = 60                      # sus términos piden máximo 1 descarga por hora

    def convertir(self, datos):
        ofertas = []
        for j in datos.get("jobs", []):
            salario = ""
            if j.get("salaryMin"):
                salario = f"{j['salaryMin']:,}–{j.get('salaryMax') or j['salaryMin']:,} " \
                          f"{j.get('salaryCurrency', '')} {j.get('salaryPeriod', '')}".strip()
            ofertas.append(Oferta(
                fuente=self.nombre, url=j["url"], titulo=sin_html(j["jobTitle"]),
                empresa=j["companyName"], tipo=", ".join(j.get("jobType") or []),
                ubicacion=j.get("jobGeo", ""), salario=salario,
                categoria=", ".join(j.get("jobIndustry") or []),
                fecha=(j.get("pubDate") or "")[:10],
                descripcion=j.get("jobDescription") or j.get("jobExcerpt", "")))
        return ofertas


# =====================================================================
#  RESUMIDOR: descripción breve, tareas y requisitos de cada oferta
# =====================================================================

class _Bloques(HTMLParser):
    """Parte el HTML en bloques (título, párrafo o viñeta) con su texto."""
    BLOQUE = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "br", "tr"}

    def __init__(self):
        super().__init__()
        self.bloques, self.texto, self.negrita, self.tag = [], [], [], "p"
        self.en_negrita = 0

    def _cerrar(self):
        texto = re.sub(r"\s+", " ", "".join(self.texto)).strip()
        if texto:
            negrita = re.sub(r"\s+", " ", "".join(self.negrita)).strip()
            self.bloques.append((self.tag, texto, len(negrita) / len(texto)))
        self.texto, self.negrita = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOQUE:
            self._cerrar()
            self.tag = tag if tag in ("li", "h1", "h2", "h3", "h4", "h5", "h6") else "p"
        elif tag in ("strong", "b"):
            self.en_negrita += 1

    def handle_endtag(self, tag):
        if tag in self.BLOQUE:
            self._cerrar()
            self.tag = "p"
        elif tag in ("strong", "b"):
            self.en_negrita = max(0, self.en_negrita - 1)

    def handle_data(self, data):
        self.texto.append(data)
        if self.en_negrita:
            self.negrita.append(data)

    def close(self):
        super().close()
        self._cerrar()


class Resumidor:
    """Lee la descripción de la oferta y saca lo esencial.

    Busca las secciones típicas ("Responsibilities", "Requirements"...) y toma
    sus viñetas. Si la oferta no tiene secciones, usa las frases que suenan
    a tareas ("you will...") o a requisitos ("experience", "required"...).
    """
    TAREAS = ["responsibilities", "responsibility", "what you'll do", "what you will do",
              "your role", "the role", "duties", "day to day", "day-to-day", "in this role",
              "tasks", "you will", "what you'll be doing", "job description", "how it works", "funciones",
              "responsabilidades"]
    REQUISITOS = ["requirements", "qualifications", "what we're looking for", "what we are looking for",
                  "what you'll need", "what you need", "who you are", "skills", "must have",
                  "you have", "about you", "you should have", "experience", "requisitos", "perfil"]
    OTRAS = ["nice to have", "bonus", "preferred", "benefits", "perks", "compensation", "about us", "about the company", "why join",
             "why work", "salary", "pay", "how to apply", "equal opportunity", "eeo", "beneficios"]
    FRASES_TAREA = ["you will", "you'll", "responsible for", "your day", "duties include", "tasks include"]
    FRASES_REQUISITO = ["experience", "required", "must", "years", "proficient", "proficiency",
                        "degree", "ability to", "knowledge of", "fluent", "familiar with"]
    MAXIMO = 8

    @staticmethod
    def _corto(texto, largo=170):
        return texto if len(texto) <= largo else texto[:largo].rsplit(" ", 1)[0] + "…"

    @classmethod
    def _seccion(cls, titulo):
        t = normalizar(titulo).rstrip(":")
        for nombre, palabras in (("otras", cls.OTRAS), ("tareas", cls.TAREAS),
                                 ("requisitos", cls.REQUISITOS)):
            if any(p in t for p in palabras):
                return nombre
        return None

    @classmethod
    def resumir(cls, oferta):
        lector = _Bloques()
        lector.feed(oferta.descripcion or "")
        lector.close()

        seccion, parrafos = None, []
        listas = {"tareas": [], "requisitos": []}
        bloques = lector.bloques
        for i, (tag, texto, negrita) in enumerate(bloques):
            antes_de_lista = i + 1 < len(bloques) and bloques[i + 1][0] == "li"
            es_titulo = tag.startswith("h") or (negrita > 0.8 and len(texto) < 80) or \
                        (len(texto) < 60 and texto.endswith(":")) or \
                        (tag == "p" and len(texto) < 45 and antes_de_lista)
            if es_titulo:
                seccion = cls._seccion(texto) or ("otras" if seccion else None)
                continue
            if seccion in listas and len(listas[seccion]) < cls.MAXIMO:
                listas[seccion].append(cls._corto(texto))
            elif seccion is None and tag == "p" and len(texto) > 40:
                parrafos.append(texto)

        texto_plano = sin_html(oferta.descripcion)
        if not listas["tareas"] or not listas["requisitos"]:
            frases = re.split(r"(?<=[.!?])\s+", texto_plano)
            for clave, pistas in (("tareas", cls.FRASES_TAREA), ("requisitos", cls.FRASES_REQUISITO)):
                if not listas[clave]:
                    listas[clave] = [cls._corto(f) for f in frases
                                     if any(p in f.lower() for p in pistas)][:cls.MAXIMO]

        resumen = " ".join(parrafos) or texto_plano
        oferta.resumen = cls._corto(resumen, 320)
        oferta.tareas, oferta.requisitos = listas["tareas"], listas["requisitos"]
        oferta.descripcion = texto_plano
        return oferta


# =====================================================================
#  EVALUADOR: qué tanto se parece cada oferta a lo que se busca
# =====================================================================

class Evaluador:
    def __init__(self, ruta_criterios):
        with open(ruta_criterios, encoding="utf-8") as f:
            self.c = json.load(f)

    @staticmethod
    def _encontradas(texto, palabras):
        return [p for p in palabras if re.search(rf"\b{re.escape(normalizar(p))}\b", texto)]

    def evaluar(self, o):
        titulo = normalizar(o.titulo)
        todo = normalizar(" ".join([o.titulo, o.tipo, o.categoria, o.descripcion]))
        puntos, razones, alertas = 20, [t("✅ Remoto")], []
        o.es_temporal = o.es_administrativa = o.fuera_de_zona = o.sospechosa = False

        tipo = normalizar(o.tipo)
        tiempo_completo = "full" in tipo and not any(p in tipo for p in self.c["temporal"]["tipos"])
        if any(p in tipo for p in self.c["temporal"]["tipos"]) or \
                (not tiempo_completo and self._encontradas(todo, self.c["temporal"]["palabras"])):
            puntos += 25
            o.es_temporal = True
            razones.append(t("✅ Temporal / medio tiempo / contrato"))

        admin_titulo = self._encontradas(titulo, self.c["administrativo"]["palabras"])
        if admin_titulo:
            puntos += 30
            o.es_administrativa = True
            razones.append(t("✅ Administrativo ({palabra})", palabra=admin_titulo[0]))
        elif self._encontradas(todo, self.c["administrativo"]["palabras"]):
            puntos += 15
            o.es_administrativa = True
            razones.append(t("➖ Tareas administrativas en la descripción"))

        pago = self._encontradas(todo, self.c["pago_rapido"]["palabras"])
        if pago:
            puntos += 15
            razones.append(t("✅ Menciona: {palabra}", palabra=pago[0]))

        ubicacion = normalizar(o.ubicacion)
        if not ubicacion or self._encontradas(ubicacion, self.c["ubicacion"]["aceptadas"]):
            puntos += 10
        elif self._encontradas(ubicacion, self.c["ubicacion"]["excluyentes"]):
            puntos -= 30
            o.fuera_de_zona = True
            alertas.append(t("🌎 Solo para: {lugar}", lugar=o.ubicacion))

        if o.salario:
            puntos += 5
            razones.append(t("✅ Publica el salario"))

        fraude = self._encontradas(todo, self.c["fraude"]["palabras"])
        if fraude:
            puntos = 0
            o.sospechosa = True
            alertas.append(t("⚠️ Posible fraude: menciona «{palabra}»", palabra=fraude[0]))

        o.puntaje, o.razones, o.alertas = max(0, min(puntos, 100)), razones, alertas
        return o


# =====================================================================
#  BUSCADOR
# =====================================================================

class BuscadorEmpleos:
    """Consulta todas las fuentes a la vez, filtra, quita repetidas y ordena.

    Recuerda cada oferta vista (vistas.json en la caché) para poder abrirla después aunque venga
    de una búsqueda por palabras, de la página de una empresa o de una oferta importada a mano."""

    def __init__(self, fuentes, evaluador, carpeta_cache=None):
        self.fuentes = fuentes
        self.evaluador = evaluador
        self.vistas = Path(carpeta_cache) / "vistas.json" if carpeta_cache else None

    def _recordar(self, ofertas):
        if not self.vistas:
            return
        try:
            datos = json.loads(self.vistas.read_text(encoding="utf-8")) if self.vistas.exists() else {}
        except ValueError:
            datos = {}
        for o in ofertas:
            datos[o.url] = asdict(o) | {"visto": date.today().isoformat()}
        if len(datos) > 3000:                     # se guardan las 3.000 más recientes
            datos = dict(sorted(datos.items(), key=lambda kv: kv[1].get("visto", ""))[-3000:])
        temporal = self.vistas.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        temporal.replace(self.vistas)

    def recordar(self, oferta):
        self._recordar([oferta])

    def buscar(self, terminos, solo_temporales=True, solo_administrativos=True,
               ocultar_sospechosas=True, puntaje_minimo=0, nombres=None):
        """Devuelve (ofertas, errores, estado_de_fuentes). nombres: solo esas fuentes (None = todas)."""
        crudos = [p.strip() for p in terminos if p.strip()]
        terminos = [normalizar(p) for p in crudos]
        fuentes = [f for f in self.fuentes if nombres is None or f.nombre in nombres]
        ofertas, errores, vistas, todas = [], [], set(), []

        def consultar(fuente):
            try:
                return fuente, fuente.ofertas(crudos), None
            except Exception as e:
                return fuente, [], e

        with ThreadPoolExecutor(max_workers=6) as grupo:     # todas las bolsas a la vez
            resultados = list(grupo.map(consultar, fuentes))
        for fuente, lista, error in resultados:
            if error is not None:
                errores.append(t("{fuente}: no se pudo consultar ({e}).", fuente=fuente.nombre, e=error))
                continue
            for o in lista:
                clave = (normalizar(o.titulo), normalizar(o.empresa))
                if clave in vistas:
                    continue                      # la misma oferta en dos fuentes
                texto = normalizar(f"{o.titulo} {o.categoria} {o.descripcion}")
                if terminos and not any(p in texto for p in terminos):
                    continue
                self.evaluador.evaluar(o)
                vistas.add(clave)
                todas.append(o)
                if solo_temporales and not o.es_temporal:
                    continue
                if solo_administrativos and not o.es_administrativa:
                    continue
                if ocultar_sospechosas and (o.sospechosa or o.fuera_de_zona):
                    continue
                if o.puntaje < puntaje_minimo:
                    continue
                ofertas.append(o)
        ofertas.sort(key=lambda o: (o.puntaje, o.fecha), reverse=True)
        self._recordar(todas)
        self.ultimas_todas = todas                # para el panorama del mercado (antes de los filtros)
        estado = [{"nombre": f.nombre, "sitio": f.sitio, "minutos": f.edad_cache()} for f in fuentes]
        return ofertas, errores, estado

    def por_url(self, url):
        """Busca una oferta por su enlace: primero en las ya vistas, luego en las fuentes (copia guardada)."""
        if self.vistas and self.vistas.exists():
            try:
                datos = json.loads(self.vistas.read_text(encoding="utf-8")).get(url)
            except ValueError:
                datos = None
            if datos:
                campos = {k: v for k, v in datos.items() if k in Oferta.__dataclass_fields__}
                return self.evaluador.evaluar(Oferta(**campos))
        for fuente in self.fuentes:
            if fuente.por_busqueda:
                continue
            try:
                for o in fuente.ofertas():
                    if o.url == url:
                        return self.evaluador.evaluar(o)
            except Exception:
                continue
        return None


# =====================================================================
#  REGISTRO: empresas y ofertas guardadas en la base de datos
# =====================================================================

class RegistroEmpleos:
    ESTADOS = ["Por revisar", "Aplicado", "Entrevista", "Descartado"]

    def __init__(self, ruta_config):
        self.con = Conexion.desde_config(ruta_config)
        with Administracion(self.con) as admin:
            admin.crear_esquema(self.con.config)  # crea las tablas si faltan

    def _recortar(self, tabla, registro):
        """Los textos que vienen de las bolsas de empleo pueden ser más largos que el campo:
        se recortan al largo del diseño para que la validación no los rechace."""
        diseno = self.con.config["tablas"][tabla]
        return {c: (v[:diseno[c]["largo"]] if isinstance(v, str) and diseno[c].get("largo") else v)
                for c, v in registro.items()}

    def _empresa(self, datos, nombre):
        encontradas = datos.leer("empresas", {"nombre": nombre}, limite=1)
        if encontradas:
            return encontradas[0]["id"]
        return datos.escribir("empresas", self._recortar("empresas", {"nombre": nombre or "—"}))

    def guardar(self, oferta):
        """Guarda la oferta (y su empresa). Devuelve False si ya estaba guardada."""
        with Datos(self.con) as datos, datos.transaccion():   # empresa y oferta: todo o nada
            if datos.contar("ofertas_guardadas", {"url": oferta["url"]}):
                return False
            datos.escribir("ofertas_guardadas", self._recortar("ofertas_guardadas", {
                "empresa_id": self._empresa(datos, oferta["empresa"]),
                "titulo": oferta["titulo"], "fuente": oferta["fuente"], "url": oferta["url"],
                "tipo_contrato": oferta.get("tipo", ""), "ubicacion": oferta.get("ubicacion", ""),
                "salario": oferta.get("salario", ""), "puntaje": int(oferta.get("puntaje", 0)),
                "estado": self.ESTADOS[0], "fecha_guardada": date.today().isoformat()}))
        return True

    def guardadas(self):
        with Datos(self.con) as datos:
            empresas = {e["id"]: e["nombre"] for e in datos.leer("empresas")}
            ofertas = datos.leer("ofertas_guardadas")
        for o in ofertas:
            o["empresa"] = empresas.get(o["empresa_id"], "")
        return sorted(ofertas, key=lambda o: (o["estado"] == "Descartado", -(o["puntaje"] or 0)))

    def cambiar_estado(self, id_oferta, estado):
        if estado in self.ESTADOS:
            with Datos(self.con) as datos:
                datos.actualizar("ofertas_guardadas", id_oferta, {"estado": estado})

    def registrar_aplicacion(self, oferta, metodo, destino="", archivo_cv="", archivo_carta=""):
        """Deja la oferta guardada como «Aplicado» y anota cómo se aplicó."""
        self.guardar(oferta)
        with Datos(self.con) as datos, datos.transaccion():
            id_oferta = datos.leer("ofertas_guardadas", {"url": oferta["url"]}, limite=1)[0]["id"]
            datos.actualizar("ofertas_guardadas", id_oferta, {"estado": "Aplicado"})
            datos.escribir("aplicaciones", self._recortar("aplicaciones", {
                "oferta_id": id_oferta, "fecha": date.today().isoformat(), "metodo": metodo,
                "destino": destino, "archivo_cv": archivo_cv, "archivo_carta": archivo_carta}))

    def aplicaciones(self, url):
        with Datos(self.con) as datos:
            encontradas = datos.leer("ofertas_guardadas", {"url": url})
            if not encontradas:
                return []
            return datos.leer("aplicaciones", {"oferta_id": encontradas[0]["id"]})

    def borrar(self, id_oferta):
        """Quita la oferta y sus aplicaciones, una por una y por su ID (todo o nada)."""
        with Datos(self.con) as datos, datos.transaccion():
            for a in datos.leer("aplicaciones", {"oferta_id": id_oferta}, campos=["id"]):
                datos.borrar("aplicaciones", a["id"])
            datos.borrar("ofertas_guardadas", id_oferta)


def como_dict(oferta):
    """La oferta como diccionario, sin la descripción (para guardarla)."""
    datos = asdict(oferta)
    for clave in ("descripcion", "resumen", "tareas", "requisitos"):
        datos.pop(clave, None)
    return datos
