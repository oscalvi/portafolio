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
from empleos import BuscadorEmpleos, Evaluador, Jobicy, RegistroEmpleos, Remotive, como_dict
from escritorio import Escritorio

CARPETA = Path(__file__).parent
os.chdir(CARPETA)                       # rutas relativas de los JSON = esta carpeta
CONFIG = CARPETA / "bd.json"
CATALOGO = Escritorio(CARPETA / "escritorio.json")
ASISTENTE = AsistenteBD(CARPETA / "motores.json", CARPETA / "configuraciones")
ANALISTA = Analista(CARPETA / "aplicaciones.json", CARPETA / "reglas.json")
CRITERIOS = CARPETA / "criterios_empleo.json"
BUSCADOR = BuscadorEmpleos([Remotive(CARPETA / "cache_empleos"), Jobicy(CARPETA / "cache_empleos")],
                           Evaluador(CRITERIOS))
REGISTRO = RegistroEmpleos(CARPETA / "empleos_bd.json")
CREDENCIALES = Credenciales(CARPETA / "credenciales.json")      # privado: no compartir
HOJA_DE_VIDA = HojaDeVida(CARPETA / "hojas_de_vida")
APLICACION = Aplicacion(
    HOJA_DE_VIDA,
    # con la API de Claude solo si está activada en Configuración; si no, sin IA
    lambda: AdaptadorClaude(CREDENCIALES) if CREDENCIALES.usar_api() else AdaptadorLocal(),
    GeneradorDocumentos(HOJA_DE_VIDA.adaptadas),
    GeneradorPDF(HOJA_DE_VIDA.adaptadas))

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
        {"icono": "🧠", "nombre": "Diseñador virtual de aplicaciones", "url": url_for("bd_inicio")},
        {"icono": "🗄️", "nombre": "Administración de bases de datos", "url": url_for("bd_tipo")},
    ]
    with open(CARPETA / "aplicaciones_web.json", encoding="utf-8") as f:
        disponibles += [{"icono": a["icono"], "nombre": a["nombre"], "url": url_for(a["ruta"])}
                        for a in json.load(f)]
    disponibles += [{"icono": a["icono"], "nombre": t(a["nombre"]) + " " + t("(escritorio)"),
                     "url": url_for("escritorio")} for a in CATALOGO.lista()]
    ideas = [{"icono": a["icono"], "nombre": a["nombre"], "url": url_for("bd_inicio", idea=a["id"])}
             for a in ANALISTA.aplicaciones]
    return render_template("index.html", mensaje=request.args.get("mensaje"),
                           disponibles=disponibles, ideas=ideas)


# ======================= Aplicaciones de escritorio =======================
@app.route("/escritorio")
def escritorio():
    """Lista las aplicaciones de escritorio del catálogo (escritorio.json)."""
    return render_template("escritorio.html", aplicaciones=CATALOGO.lista(),
                           mensaje=request.args.get("mensaje"))


@app.route("/web")
def aplicaciones_web():
    """Lista las aplicaciones web del training (aplicaciones_web.json)."""
    with open(CARPETA / "aplicaciones_web.json", encoding="utf-8") as f:
        aplicaciones = json.load(f)
    return render_template("aplicaciones_web.html", aplicaciones=aplicaciones)


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
    """Busca trabajos remotos, temporales y administrativos en bolsas confiables."""
    criterios = json.loads(CRITERIOS.read_text(encoding="utf-8"))
    buscar = "buscar" in request.args
    filtros = {
        "terminos": request.args.get("terminos", criterios["busqueda_inicial"]),
        "solo_temporales": request.args.get("temporales") == "1" or not buscar,
        "solo_administrativos": request.args.get("administrativos") == "1" or not buscar,
        "ocultar_sospechosas": request.args.get("sospechosas") != "1",
    }
    ofertas, errores, fuentes = [], [], []
    if buscar:
        ofertas, errores, fuentes = BUSCADOR.buscar(
            filtros["terminos"].split(","), filtros["solo_temporales"],
            filtros["solo_administrativos"], filtros["ocultar_sospechosas"])
    guardadas = {o["url"] for o in REGISTRO.guardadas()}
    return render_template("empleos.html", ofertas=ofertas, errores=errores, fuentes=fuentes,
                           filtros=filtros, buscar=buscar, criterios=criterios,
                           guardadas=guardadas, mensaje=request.args.get("mensaje"),
                           como_dict=como_dict)


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
        CREDENCIALES.guardar(datos)
        return redirect(url_for("empleos_configuracion", guardado=1))
    return render_template("empleos_config.html", d=datos, guardado=request.args.get("guardado"),
                           usar_api=CREDENCIALES.usar_api(),
                           tiene_ia=CREDENCIALES.tiene_ia(), tiene_correo=CREDENCIALES.tiene_correo())


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
