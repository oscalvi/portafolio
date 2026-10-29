"""PY Training: entrada web, aplicaciones de escritorio y asistente de bases de datos.

Para correrla:
    pip install flask
    python app.py
Luego abre en el navegador:  http://127.0.0.1:5000
"""
import json
import os
from urllib.parse import urlencode
from pathlib import Path

# Las clases genéricas (basedatos, idiomas, ventanas) viven en la carpeta "comun" del proyecto
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "comun"))

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

import idiomas
from idiomas import Traductor, t

from analista import Analista
from aplicador import (AdaptadorClaude, AdaptadorLocal, Aplicacion, Credenciales,
                       GeneradorDocumentos, GeneradorPDF, HojaDeVida, RemitenteSMTP)
from asistente_bd import TIPOS_CAMPO, AsistenteBD, ErrorAsistente
from basedatos import Administracion, Conexion, Datos, ErrorDatos
from bolsas import (ATS, SUGERIDAS, Adzuna, EmpresasSeguidas, Himalayas, RemoteOK, TheMuse, WeWorkRemotely,
                    enlaces_otras_bolsas, importar_oferta, panorama)
from empleos import BuscadorEmpleos, Evaluador, Jobicy, RegistroEmpleos, Remotive, como_dict
from entrevista import (ETAPAS, ArchivoEntrevistas, EvaluadorClaude, EvaluadorRespuesta, GeneradorClaude,
                        GeneradorLocal, puntos_en)
from escritorio import Escritorio
from respuestas_modelo import ejemplo
from externas import AplicacionExterna
from soporte import SoporteClaude, SoporteLocal

CARPETA = Path(__file__).parent
os.chdir(CARPETA)                       # rutas relativas de los JSON = esta carpeta
CONFIG = CARPETA / "bd.json"
CATALOGO = Escritorio(CARPETA / "escritorio.json")
ASISTENTE = AsistenteBD(CARPETA / "motores.json", CARPETA / "configuraciones")
ANALISTA = Analista(CARPETA / "aplicaciones.json", CARPETA / "reglas.json")
CRITERIOS = CARPETA / "criterios_empleo.json"
CACHE_EMPLEOS = CARPETA / "cache_empleos"
EMPRESAS = EmpresasSeguidas(CARPETA / "configuraciones" / "empresas_seguidas.json")   # privado
BOLSAS = [Remotive(CACHE_EMPLEOS), Jobicy(CACHE_EMPLEOS), Himalayas(CACHE_EMPLEOS), RemoteOK(CACHE_EMPLEOS),
          WeWorkRemotely(CACHE_EMPLEOS), TheMuse(CACHE_EMPLEOS)]
BUSCADOR = BuscadorEmpleos(BOLSAS, Evaluador(CRITERIOS), CACHE_EMPLEOS)
REGISTRO = RegistroEmpleos(CARPETA / "empleos_bd.json")
CREDENCIALES = Credenciales(CARPETA / "credenciales.json")      # privado: no compartir


def fuentes_actuales():
    """Las bolsas públicas, Adzuna si tiene clave y las páginas de empleo de las empresas que sigue."""
    fuentes = list(BOLSAS)
    a = CREDENCIALES.leer().get("adzuna") or {}
    if a.get("app_id") and a.get("app_key"):
        fuentes.append(Adzuna(CACHE_EMPLEOS, a["app_id"], a["app_key"], a.get("pais", "us")))
    return fuentes + EMPRESAS.fuentes(CACHE_EMPLEOS)
HOJA_DE_VIDA = HojaDeVida(CARPETA / "hojas_de_vida")
APLICACION = Aplicacion(
    HOJA_DE_VIDA,
    # con la API de Claude solo si está activada en Configuración; si no, sin IA
    lambda: AdaptadorClaude(CREDENCIALES) if CREDENCIALES.usar_api() else AdaptadorLocal(),
    GeneradorDocumentos(HOJA_DE_VIDA.adaptadas),
    GeneradorPDF(HOJA_DE_VIDA.adaptadas))

ENTREVISTAS = ArchivoEntrevistas(CARPETA / "entrevistas")     # privado: planes y prácticas de entrevista

GUIA = CARPETA / "ayuda.json"                # guía de uso: la usan el agente de soporte y el README


def agente_soporte():
    """Con la API de Claude si está activada en Configuración; si no, la guía sin IA."""
    return SoporteClaude(GUIA, CREDENCIALES) if CREDENCIALES.usar_api() else SoporteLocal(GUIA)


CLIENTES_EJEMPLO = [
    {"nombre": "Ana García",    "telefono": "305-555-1234"},
    {"nombre": "Luis Martínez", "telefono": "786-555-9876"},
    {"nombre": "María López",   "telefono": "954-555-4433"},
    {"nombre": "Carlos Rojas",  "telefono": "305-555-7788"},
    {"nombre": "Sofía Herrera", "telefono": "786-555-2211"},
]

app = Flask(__name__)


# ======================= Idioma del visitante =======================
TRADUCTOR = Traductor(CARPETA / "idiomas")
idiomas.configurar(TRADUCTOR, lambda: g.idioma)


@app.before_request
def escoger_idioma():
    g.idioma = TRADUCTOR.elegir(request)        # selector → navegador → inglés


@app.after_request
def recordar_idioma(respuesta):
    if request.args.get("lang") in TRADUCTOR.disponibles:
        respuesta.set_cookie("idioma", request.args["lang"], max_age=60 * 60 * 24 * 365)
    return respuesta


@app.context_processor
def datos_de_idioma():
    def url_idioma(codigo):
        """La misma página en otro idioma."""
        argumentos = request.args.to_dict()
        argumentos["lang"] = codigo
        return request.path + "?" + urlencode(argumentos)
    return {"t": t, "idioma": g.get("idioma", "en"), "idiomas": TRADUCTOR.disponibles,
            "url_idioma": url_idioma}


# ======================= Entrada =======================
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(CARPETA, "favicon.ico")


@app.route("/")
def inicio():
    """Entrada: logo, mensaje y la cinta con las aplicaciones hechas y las que se pueden crear."""
    disponibles = [
        {"icono": "🧠", "nombre": "Diseñador virtual de aplicaciones", "url": url_for("bd_inicio"),
         "descripcion": "Describa su idea por voz, texto o documento y el analista virtual le propone la aplicación, la base de datos y las tablas."},
        {"icono": "🗄️", "nombre": "Administración de bases de datos", "url": url_for("bd_tipo"),
         "descripcion": "Cree o conecte una base de datos y diseñe tablas, campos y llaves desde el navegador."},
    ]
    disponibles += [{"icono": a["icono"], "nombre": a["nombre"], "url": a["url"],
                     "descripcion": a.get("descripcion", "")} for a in apps_web()]
    disponibles += [{"icono": a["icono"], "nombre": t(a["nombre"]) + " " + t("(escritorio)"),
                     "url": url_for("escritorio"), "descripcion": a.get("descripcion", "")}
                    for a in CATALOGO.lista()]
    ideas = [{"icono": a["icono"], "nombre": a["nombre"], "url": url_for("bd_inicio", idea=a["id"]),
              "descripcion": a.get("descripcion", "")} for a in ANALISTA.aplicaciones]
    return render_template("index.html", mensaje=request.args.get("mensaje"),
                           disponibles=disponibles, ideas=ideas)


# ======================= Aplicaciones de escritorio =======================
@app.route("/escritorio")
def escritorio():
    """Lista las aplicaciones de escritorio del catálogo (escritorio.json)."""
    return render_template("escritorio.html", aplicaciones=CATALOGO.lista(),
                           mensaje=request.args.get("mensaje"))


def apps_web():
    """Aplicaciones web de aplicaciones_web.json, cada una con su "url":
    las internas van a su página; las externas (su propio servidor) pasan por /web/<id>/abrir."""
    with open(CARPETA / "aplicaciones_web.json", encoding="utf-8") as f:
        aplicaciones = json.load(f)
    for a in aplicaciones:
        a["url"] = url_for("abrir_web", id_app=a["id"]) if "externa" in a else url_for(a["ruta"])
    return aplicaciones


@app.route("/web")
def aplicaciones_web():
    """Lista las aplicaciones web del training (aplicaciones_web.json)."""
    return render_template("aplicaciones_web.html", aplicaciones=apps_web(),
                           mensaje=request.args.get("mensaje"))


@app.route("/web/<id_app>/abrir")
def abrir_web(id_app):
    """Arranca (si hace falta) el servidor de una aplicación web externa y la abre."""
    datos = next((a for a in apps_web() if a["id"] == id_app and "externa" in a), None)
    if datos is None:
        return redirect(url_for("aplicaciones_web", mensaje=t("Esa aplicación no existe en el catálogo.")), code=303)
    url, error = AplicacionExterna(CARPETA, datos).abrir()
    return redirect(url or url_for("aplicaciones_web", mensaje=error), code=303)


@app.route("/escritorio/<id_app>", methods=["POST"])
def abrir_escritorio(id_app):
    """Minimiza el navegador y abre la aplicación escogida."""
    mensaje = CATALOGO.abrir(id_app)
    return redirect(url_for("escritorio", mensaje=mensaje), code=303)


# ======================= Asistente de bases de datos =======================
@app.route("/databases", methods=["GET", "POST"])
def bd_inicio():
    """Paso 1: ¿qué aplicación quiere? (voz, documento o texto) y dimensionamiento."""
    error = None
    if request.method == "POST":
        ASISTENTE.borrador = {
            "descripcion": request.form.get("descripcion", "").strip(),
            "respuestas": {p["id"]: request.form[p["id"]]
                           for p in ANALISTA.preguntas if request.form.get(p["id"])}}
        if ASISTENTE.borrador["descripcion"]:
            return redirect(url_for("bd_propuesta"))
        error = t("Cuénteme primero qué aplicación quiere desarrollar.")
    elif not request.args.get("editar"):
        ASISTENTE.reiniciar()               # entrar de nuevo = empezar un análisis nuevo
        idea = ANALISTA.aplicacion(request.args.get("idea", ""))
        if idea:                            # viene de la cinta «Cree la suya»
            ASISTENTE.borrador["descripcion"] = t("Quiero una aplicación de {nombre}.",
                                                  nombre=t(idea["nombre"]).lower())
    return render_template("bd_necesidad.html", paso=1, error=error,
                           aplicaciones=ANALISTA.aplicaciones, preguntas=preguntas_traducidas(),
                           descripcion=ASISTENTE.borrador["descripcion"],
                           respuestas=ASISTENTE.borrador["respuestas"])


def preguntas_traducidas():
    """Las preguntas del analista en el idioma del visitante (para la voz)."""
    return [{**p, "texto": t(p["texto"]),
             "opciones": [{**o, "texto": t(o["texto"])} for o in p["opciones"]]}
            for p in ANALISTA.preguntas]


@app.route("/databases/interpretar", methods=["POST"])
def bd_interpretar():
    """La página manda lo que el usuario dijo; el analista dice qué opción es."""
    datos = request.get_json(silent=True) or {}
    valor = ANALISTA.interpretar(datos.get("pregunta", ""), datos.get("texto", ""))
    opcion = ANALISTA.opcion(datos.get("pregunta", ""), valor) if valor else None
    return jsonify(valor=valor, texto=t(opcion["texto"]) if opcion else None)


@app.route("/databases/documento", methods=["POST"])
def bd_documento():
    """Extrae el texto de un documento con las especificaciones."""
    archivo = request.files.get("documento")
    if not archivo:
        return jsonify(error=t("No llegó ningún archivo."))
    try:
        return jsonify(texto=ANALISTA.leer_documento(archivo.filename, archivo.read()).strip())
    except ImportError:
        return jsonify(error=t("Falta instalar: {libreria}", libreria="pip install python-docx pypdf"))
    except Exception as e:
        return jsonify(error=t("No pude leer el documento: {e}", e=e))


@app.route("/databases/propuesta", methods=["GET", "POST"])
def bd_propuesta():
    """Paso 2: el analista propone tipo de aplicación, base de datos y tablas."""
    if not ASISTENTE.borrador["descripcion"]:
        return redirect(url_for("bd_inicio"))
    id_app = request.values.get("app") or None
    propuesta = ANALISTA.proponer(ASISTENTE.borrador["descripcion"],
                                  ASISTENTE.borrador["respuestas"], id_app)
    if request.method == "POST":
        ASISTENTE.guardar_analisis(propuesta, request.form.getlist("tablas"))
        ASISTENTE.escoger_tipo(propuesta["recomendacion"]["motor"])
        return redirect(url_for("bd_tipo"))
    rec = propuesta["recomendacion"]
    return render_template("bd_propuesta.html", paso=2, propuesta=propuesta, rec=rec,
                           app=ANALISTA.aplicacion(propuesta["aplicacion"]),
                           aplicaciones=ANALISTA.aplicaciones,
                           motor_recomendado=ASISTENTE.motor(rec["motor"]),
                           alternativas=[ASISTENTE.motor(m)["nombre"] for m in rec["alternativas"]])


@app.route("/databases/tipo", methods=["GET", "POST"])
def bd_tipo():
    """Paso 3: tipo de base de datos (viene preseleccionado con la recomendación)."""
    error = None
    if request.method == "POST":
        try:
            ASISTENTE.escoger_tipo(request.form["tipo"])
            return redirect(url_for("bd_conexion"))
        except ErrorAsistente as e:
            error = str(e)
    recomendado = (ASISTENTE.analisis or {}).get("recomendacion", {}).get("motor")
    return render_template("bd_tipo.html", paso=3, motores=ASISTENTE.motores,
                           tipo=ASISTENTE.tipo or recomendado, recomendado=recomendado,
                           error=error)


@app.route("/databases/conexion", methods=["GET", "POST"])
def bd_conexion():
    """Paso 2: ¿ya existe? -> ubicación y credenciales (o crearla)."""
    if not ASISTENTE.tipo:
        return redirect(url_for("bd_tipo"))
    motor = ASISTENTE.motor()
    if request.method == "POST":
        crear = request.form.get("accion") == "crear"
        try:
            ASISTENTE.conectar(request.form, crear)
            texto = t("Base de datos creada.") if crear else t("Conexión correcta.")
            return redirect(url_for("bd_tablas", mensaje=texto))
        except ErrorAsistente as e:
            return render_template("bd_conexion.html", paso=4, motor=motor, error=str(e),
                                   accion=request.form.get("accion"),
                                   valores=ASISTENTE.leer_parametros(request.form))
    return render_template("bd_conexion.html", paso=4, motor=motor, accion="existente",
                           valores=ASISTENTE.parametros)


@app.route("/databases/tablas")
def bd_tablas():
    """Paso 3: tablas de la base y opción de agregar una."""
    if not ASISTENTE.conectado:
        return redirect(url_for("bd_tipo"))
    p = ASISTENTE.parametros
    ubicacion = p.get("archivo") or f"{p.get('servidor', p.get('dsn'))} / {ASISTENTE.nombre_base()}"
    try:
        tablas, error = ASISTENTE.tablas(), request.args.get("error")
        pendientes = ASISTENTE.tablas_pendientes()
    except Exception as e:
        tablas, pendientes, error = [], [], t("No se pudieron leer las tablas: {e}", e=e)
    return render_template("bd_tablas.html", paso=5, motor=ASISTENTE.motor(),
                           ubicacion=ubicacion, tablas=tablas,
                           relaciones=ASISTENTE.diseno["relaciones"], pendientes=pendientes,
                           analisis=ASISTENTE.analisis,
                           ruta_diseno=ASISTENTE.ruta_diseno().relative_to(CARPETA),
                           mensaje=request.args.get("mensaje"), error=error)


@app.route("/databases/crear-propuesta", methods=["POST"])
def bd_crear_propuesta():
    """Crea de una vez las tablas que propuso el analista."""
    try:
        creadas = ASISTENTE.crear_propuesta()
        return redirect(url_for("bd_tablas", mensaje=t("Tablas creadas: {tablas}", tablas=", ".join(creadas))))
    except ErrorAsistente as e:
        return redirect(url_for("bd_tablas", error=str(e)))


def filas_del_formulario(formulario):
    """Convierte las columnas del formulario en una lista de campos.

    Los textos y listas llegan en orden (una entrada por fila). Las casillas
    y la llave primaria llegan con el número de su fila.
    """
    numeros = formulario.getlist("fila")
    nombres = formulario.getlist("nombre")
    tipos = formulario.getlist("tipo")
    largos = formulario.getlist("largo")
    referencias = formulario.getlist("referencia")
    obligatorios = set(formulario.getlist("obligatorio"))
    autos = set(formulario.getlist("auto"))
    pk = formulario.get("pk")
    return [{"nombre": nombres[i], "tipo": tipos[i], "largo": largos[i],
             "obligatorio": n in obligatorios, "pk": n == pk, "auto": n in autos,
             "referencia": referencias[i]}
            for i, n in enumerate(numeros)]


@app.route("/databases/tabla", methods=["GET", "POST"])
def bd_tabla_nueva():
    """Paso 4: nombre de la tabla, campos, llave primaria y relaciones."""
    if not ASISTENTE.conectado:
        return redirect(url_for("bd_tipo"))
    error, nombre, filas = None, "", []
    if request.method == "POST":
        nombre = request.form.get("tabla", "")
        filas = filas_del_formulario(request.form)
        try:
            ASISTENTE.agregar_tabla(nombre, filas)
            return redirect(url_for("bd_tablas", mensaje=t("Tabla {tabla} creada.", tabla=nombre.strip())))
        except ErrorAsistente as e:
            error = str(e)
    return render_template("bd_tabla_nueva.html", paso=6, tipos=TIPOS_CAMPO,
                           referencias=ASISTENTE.referencias(), error=error,
                           nombre_tabla=nombre, filas_previas=filas)


# ======================= Buscador de empleadores =======================
@app.route("/empleos")
def empleos():
    """Busca en las bolsas de empleo y en las páginas de empleo de las empresas que sigue."""
    criterios = json.loads(CRITERIOS.read_text(encoding="utf-8"))
    buscar = "buscar" in request.args
    filtros = {
        "terminos": request.args.get("terminos", criterios["busqueda_inicial"]),
        "solo_temporales": request.args.get("temporales") == "1" or not buscar,
        "solo_administrativos": request.args.get("administrativos") == "1" or not buscar,
        "ocultar_sospechosas": request.args.get("sospechosas") != "1",
    }
    BUSCADOR.fuentes = fuentes_actuales()
    todas_fuentes = [f.nombre for f in BUSCADOR.fuentes]
    elegidas = request.args.getlist("fuente") if buscar and request.args.getlist("fuente") else todas_fuentes
    ofertas, errores, fuentes, mercado = [], [], [], None
    if buscar:
        ofertas, errores, fuentes = BUSCADOR.buscar(
            filtros["terminos"].split(","), filtros["solo_temporales"],
            filtros["solo_administrativos"], filtros["ocultar_sospechosas"], nombres=set(elegidas))
        mercado = panorama(getattr(BUSCADOR, "ultimas_todas", []))
    guardadas = {o["url"] for o in REGISTRO.guardadas()}
    return render_template("empleos.html", ofertas=ofertas, errores=errores, fuentes=fuentes,
                           filtros=filtros, buscar=buscar, criterios=criterios,
                           guardadas=guardadas, mensaje=request.args.get("mensaje"),
                           como_dict=como_dict, todas_fuentes=todas_fuentes, elegidas=set(elegidas),
                           mercado=mercado, otras=enlaces_otras_bolsas(filtros["terminos"].split(",")),
                           tiene_adzuna=any(f.nombre == "Adzuna" for f in BUSCADOR.fuentes))


@app.route("/empleos/importar", methods=["POST"])
def empleos_importar():
    """Una oferta encontrada en Dice, Monster, Indeed, LinkedIn o la página de una empresa, pegada a mano."""
    f = request.form
    try:
        oferta = BUSCADOR.evaluador.evaluar(importar_oferta(f.get("url"), f.get("texto"), f.get("titulo", "").strip(),
                                                            f.get("empresa", "").strip(), f.get("ubicacion", "").strip(),
                                                            f.get("tipo", "").strip()))
    except ValueError as e:
        return redirect(url_for("empleos", mensaje=str(e)))
    BUSCADOR.recordar(oferta)
    REGISTRO.guardar(como_dict(oferta))
    return redirect(url_for("empleos_aplicar", url=oferta.url))


@app.route("/empleos/empresas", methods=["GET", "POST"])
def empleos_empresas():
    """Las empresas cuyas páginas de empleo se consultan en cada búsqueda."""
    error = mensaje = None
    if request.method == "POST":
        try:
            if request.form.get("accion") == "quitar":
                EMPRESAS.quitar(request.form["ats"], request.form["slug"])
                mensaje = t("Empresa quitada.")
            else:
                e = EMPRESAS.agregar(request.form.get("nombre", ""), request.form.get("enlace", ""),
                                     request.form.get("ats") or None, request.form.get("slug") or None)
                mensaje = t("Listo: {empresa} se consultará en cada búsqueda.", empresa=e["nombre"])
        except ValueError as ex:
            error = str(ex)
    seguidas = EMPRESAS.lista()
    estado = {}
    for fuente in EMPRESAS.fuentes(CACHE_EMPLEOS):
        estado[fuente.nombre] = fuente.edad_cache()
    claves = {(e["ats"], e["slug"]) for e in seguidas}
    return render_template("empleos_empresas.html", seguidas=seguidas, ats=ATS, error=error, mensaje=mensaje,
                           sugeridas=[s for s in SUGERIDAS if (s["ats"], s["slug"]) not in claves], estado=estado)


@app.route("/empleos/guardar", methods=["POST"])
def empleos_guardar():
    oferta = json.loads(request.form["oferta"])
    nueva = REGISTRO.guardar(oferta)
    return jsonify(ok=True, nueva=nueva)


@app.route("/empleos/guardadas", methods=["GET", "POST"])
def empleos_guardadas():
    if request.method == "POST":
        id_oferta = int(request.form["id"])
        if request.form.get("accion") == "borrar":
            REGISTRO.borrar(id_oferta)
        else:
            REGISTRO.cambiar_estado(id_oferta, request.form.get("estado", ""))
        return redirect(url_for("empleos_guardadas"))
    return render_template("empleos_guardadas.html", ofertas=REGISTRO.guardadas(),
                           estados=REGISTRO.ESTADOS)


@app.route("/empleos/hoja-de-vida", methods=["GET", "POST"])
def empleos_hoja_de_vida():
    """Subir la hoja de vida. El original se guarda tal cual y nunca se modifica."""
    error = mensaje = None
    if request.method == "POST":
        archivo = request.files.get("archivo")
        try:
            if not archivo or not archivo.filename:
                raise ValueError(t("Escoja un archivo."))
            HOJA_DE_VIDA.subir(archivo.filename, archivo.read())
            mensaje = t("Hoja de vida guardada. El original queda intacto.")
        except ImportError:
            error = t("Falta instalar: {libreria}", libreria="pip install python-docx pypdf")
        except ValueError as e:
            error = str(e)
    return render_template("empleos_cv.html", hdv=HOJA_DE_VIDA.datos(), error=error,
                           mensaje=mensaje, volver=request.args.get("volver"))


@app.route("/empleos/configuracion", methods=["GET", "POST"])
def empleos_configuracion():
    """Clave de la API de Claude y correo de envío (se guardan en credenciales.json)."""
    datos = CREDENCIALES.leer()
    if request.method == "POST":
        f = request.form
        if f.get("api_key"):
            datos["anthropic_api_key"] = f["api_key"].strip()
        datos["modelo"] = f.get("modelo", datos["modelo"]).strip() or datos["modelo"]
        datos["usar_api"] = f.get("usar_api") == "1"
        datos["correo"]["nombre"] = f.get("nombre", "").strip()
        datos["correo"]["remitente"] = f.get("remitente", "").strip()
        if f.get("clave_app"):
            datos["correo"]["clave_app"] = f["clave_app"].replace(" ", "")
        datos["correo"]["servidor"] = f.get("servidor", "smtp.gmail.com").strip()
        datos["correo"]["puerto"] = int(f.get("puerto") or 465)
        adzuna = datos.get("adzuna") or {}
        adzuna["app_id"] = f.get("adzuna_id", "").strip() or adzuna.get("app_id", "")
        if f.get("adzuna_key"):
            adzuna["app_key"] = f["adzuna_key"].strip()
        if f.get("adzuna_borrar") == "1":
            adzuna = {}
        adzuna["pais"] = (f.get("adzuna_pais") or adzuna.get("pais") or "us").strip().lower()
        datos["adzuna"] = adzuna
        CREDENCIALES.guardar(datos)
        return redirect(url_for("empleos_configuracion", guardado=1))
    return render_template("empleos_config.html", d=datos, guardado=request.args.get("guardado"),
                           usar_api=CREDENCIALES.usar_api(),
                           tiene_ia=CREDENCIALES.tiene_ia(), tiene_correo=CREDENCIALES.tiene_correo(),
                           adzuna=datos.get("adzuna") or {})


@app.route("/empleos/aplicar", methods=["GET", "POST"])
def empleos_aplicar():
    """Preparar la aplicación a una oferta: hoja de vida adaptada, carta y correo."""
    url = request.values.get("url", "")
    oferta = BUSCADOR.por_url(url)
    if not oferta:
        return redirect(url_for("empleos", mensaje=t("No encontré esa oferta; vuelva a buscar.")))
    datos_oferta = como_dict(oferta) | {"descripcion": oferta.descripcion, "resumen": oferta.resumen,
                                        "tareas": oferta.tareas, "requisitos": oferta.requisitos}
    error = mensaje = None
    if request.method == "POST":
        accion = request.form.get("accion")
        ficha = APLICACION.cargar(url)
        try:
            if accion == "preparar":
                adaptar = request.form.get("adaptar") == "si"
                APLICACION.preparar(datos_oferta, adaptar)
                mensaje = (t("Listo: su hoja de vida adaptada, la carta y el borrador del correo están preparados.")
                           if adaptar else t("Listo: se usará su hoja de vida original; la carta y el correo están preparados."))
            elif accion == "enviar" and ficha:
                adjuntos = [HOJA_DE_VIDA.adaptadas / n for n in adjuntos_de(ficha)]
                RemitenteSMTP(CREDENCIALES).enviar(request.form["para"], request.form["asunto"],
                                                   request.form["cuerpo"], adjuntos)
                REGISTRO.registrar_aplicacion(datos_oferta, "correo", request.form["para"],
                                              ficha["archivo_cv"], ficha["archivo_carta"])
                mensaje = t("Correo enviado a {para}. La oferta quedó como «Aplicado».", para=request.form["para"])
            elif accion == "sitio" and ficha:
                REGISTRO.registrar_aplicacion(datos_oferta, "sitio web", oferta.url,
                                              ficha["archivo_cv"], ficha["archivo_carta"])
                mensaje = t("Quedó registrada como «Aplicado» en sus guardadas.")
        except Exception as e:
            error = str(e)
    return render_template("empleos_aplicar.html", o=oferta, ficha=APLICACION.cargar(url),
                           hdv=HOJA_DE_VIDA.datos(), usar_api=CREDENCIALES.usar_api(),
                           tiene_correo=CREDENCIALES.tiene_correo(),
                           cuenta=CREDENCIALES.cuenta_correo(), adjuntos=adjuntos_de(APLICACION.cargar(url)),
                           pdf_disponible=GeneradorPDF.disponible(),
                           aplicaciones=REGISTRO.aplicaciones(url), error=error, mensaje=mensaje)


# ======================= Entrevista virtual =======================
def oferta_completa(url):
    """La oferta con su descripción (si sigue en la copia de las bolsas); si no, lo guardado."""
    oferta = BUSCADOR.por_url(url) if url else None
    if oferta:
        return como_dict(oferta) | {"descripcion": oferta.descripcion, "tareas": oferta.tareas,
                                    "requisitos": oferta.requisitos}
    g = next((o for o in REGISTRO.guardadas() if o["url"] == url), None)
    if g:
        return {"url": url, "titulo": g["titulo"], "empresa": g["empresa"], "fuente": g["fuente"],
                "tipo": g["tipo_contrato"], "ubicacion": g["ubicacion"], "salario": g["salario"],
                "descripcion": "", "tareas": [], "requisitos": []}
    return None


@app.route("/empleos/entrevista", methods=["GET", "POST"])
def empleos_entrevista():
    """Prepara una entrevista virtual (técnica y personal) para una oferta y la practica de viva voz."""
    url = request.values.get("url", "")
    oferta, datos = oferta_completa(url), ENTREVISTAS.cargar(url)
    if not oferta and not datos:
        return redirect(url_for("empleos_guardadas"))
    if not datos or (request.method == "POST" and oferta):
        generador = GeneradorClaude(CREDENCIALES) if CREDENCIALES.usar_api() else GeneradorLocal()
        datos = ENTREVISTAS.preparar(oferta, HOJA_DE_VIDA.datos(), generador, rehacer=request.method == "POST")
        if request.method == "POST":
            return redirect(url_for("empleos_entrevista", url=url))
    plan = datos["plan"]
    hoja = HOJA_DE_VIDA.datos()
    for p in plan["preguntas"]:
        if not p.get("ejemplo"):                      # planes preparados antes de que existieran los ejemplos
            p["ejemplo"] = ejemplo(p, plan["idioma"], hoja, {"puesto": datos.get("titulo", ""), "empresa": datos.get("empresa", "")})
        p["etapa_texto"] = t(ETAPAS.get(p["etapa"], p["etapa"]))
        p["objetivo_texto"] = t(p.get("objetivo", ""))
        p["puntos_ver"] = [x for x in puntos_en(p.get("puntos", []), plan["idioma"]) if x != "?"]
    return render_template("empleos_entrevista.html", d=datos, plan=plan, o=oferta or datos,
                           hdv=hoja, usar_api=CREDENCIALES.usar_api())


@app.route("/empleos/entrevista/evaluar", methods=["POST"])
def empleos_entrevista_evaluar():
    j = request.get_json(force=True)
    datos = ENTREVISTAS.cargar(j.get("url", ""))
    if not datos:
        return jsonify(error=t("Primero prepare la entrevista.")), 404
    pregunta = next((p for p in datos["plan"]["preguntas"] if p["id"] == j.get("id")), None)
    if pregunta is None or j.get("repregunta"):
        pregunta = {"id": j.get("id", "seguimiento"), "texto": j.get("texto_pregunta", ""), "etapa": "seguimiento",
                    "tipo": "libre", "puntos": [], "segundos": 60, "es_repregunta": True,
                    "objetivo": "Pregunta de seguimiento del entrevistador."}
    evaluador = EvaluadorClaude(CREDENCIALES, HOJA_DE_VIDA.datos()) if CREDENCIALES.usar_api() else EvaluadorRespuesta()
    return jsonify(evaluador.evaluar(pregunta, j.get("respuesta", ""), float(j.get("segundos") or 0),
                                     datos["plan"]["idioma"]))


@app.route("/empleos/entrevista/terminar", methods=["POST"])
def empleos_entrevista_terminar():
    j = request.get_json(force=True)
    try:
        return jsonify(ENTREVISTAS.registrar_practica(j.get("url", ""), j.get("modo", ""), j.get("respuestas", []),
                                                      int(j.get("total") or 0) or None))
    except ValueError as e:
        return jsonify(error=str(e)), 404


def adjuntos_de(ficha):
    """Lo que se adjunta al correo: los PDF si existen (se ven igual en cualquier equipo); si no, los Word."""
    if not ficha:
        return []
    return [ficha.get("pdf_cv") or ficha["archivo_cv"], ficha.get("pdf_carta") or ficha["archivo_carta"]]


@app.route("/empleos/archivo/<path:nombre>")
def empleos_archivo(nombre):
    """Descarga un documento adaptado (hoja de vida o carta)."""
    return send_from_directory(HOJA_DE_VIDA.adaptadas, nombre, as_attachment=True)


@app.route("/empleos/ver/<path:nombre>")
def empleos_ver(nombre):
    """Abre un PDF dentro del navegador, para leerlo antes de enviarlo."""
    return send_from_directory(HOJA_DE_VIDA.adaptadas, nombre, as_attachment=False,
                               mimetype="application/pdf")


# ======================= Demo: clientes (usa la clase Datos) =======================
def conexion_clientes():
    return Conexion.desde_config(CONFIG)


def preparar_base():
    """Crea la tabla de clientes si falta y carga ejemplos si está vacía."""
    con = conexion_clientes()
    with Administracion(con) as admin:
        admin.crear_esquema(con.config)
    with Datos(con) as datos:
        if not datos.contar("clientes"):
            for cliente in CLIENTES_EJEMPLO:
                datos.escribir("clientes", cliente)


def datos_formulario():
    return {"nombre": request.form["nombre"].strip(),
            "telefono": request.form["telefono"].strip()}


# ======================= Agente de soporte técnico =======================
@app.route("/ayuda/temas")
def ayuda_temas():
    """Temas sugeridos para la página donde está el usuario."""
    return jsonify(temas=SoporteLocal(GUIA).sugerencias(request.args.get("pagina")))


@app.route("/ayuda", methods=["POST"])
def ayuda():
    """Responde cómo hacer una tarea dentro de la aplicación. Solo explica: no hace nada por el usuario."""
    datos = request.get_json(silent=True) or {}
    respuesta = agente_soporte().responder(str(datos.get("pregunta", ""))[:1500],
                                           datos.get("pagina"), datos.get("tema"))
    destino = respuesta.get("ir_a")
    try:
        respuesta["url"] = url_for(destino) if destino else None
    except Exception:                       # la página de destino necesita datos (ej. una base conectada)
        respuesta["url"] = None
    return jsonify(respuesta)


@app.route("/clientes")
def clientes():
    with Datos(conexion_clientes()) as datos:
        lista = datos.leer("clientes", orden="nombre")
    return render_template("clientes.html", clientes=lista, error=request.args.get("error"))


@app.route("/agregar", methods=["POST"])
def agregar():
    """La validación (obligatorios, largo) la hacen las clases de datos."""
    try:
        with Datos(conexion_clientes()) as datos:
            datos.escribir("clientes", datos_formulario())
    except ErrorDatos as e:
        return redirect(url_for("clientes", error=str(e)))
    return redirect(url_for("clientes"))


@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    error = None
    with Datos(conexion_clientes()) as datos:
        if request.method == "POST":
            try:
                datos.actualizar("clientes", id, datos_formulario())
                return redirect(url_for("clientes"))
            except ErrorDatos as e:
                error = str(e)
        cliente = datos.buscar("clientes", id)
    if not cliente:
        return redirect(url_for("clientes"))
    return render_template("editar.html", cliente=cliente, error=error)


@app.route("/borrar/<int:id>", methods=["POST"])
def borrar(id):
    try:
        with Datos(conexion_clientes()) as datos:
            datos.borrar("clientes", id)
    except ErrorDatos as e:
        return redirect(url_for("clientes", error=str(e)))
    return redirect(url_for("clientes"))


if __name__ == "__main__":
    preparar_base()
    app.run(debug=True)
