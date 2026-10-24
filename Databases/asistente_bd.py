"""Asistente para crear o conectar una base de datos y diseñar sus tablas.

No sabe nada de páginas web: recibe datos y usa las clases de basedatos.py
(Conexion y Administracion). Por eso se puede reutilizar desde Flask,
desde Tkinter o desde la consola.

Los motores disponibles y los datos de conexión que pide cada uno están en
motores.json. Para agregar un motor: su subclase de Conexion en basedatos.py
y su bloque en motores.json.

Cada base diseñada queda guardada en configuraciones/<nombre>.json con el
mismo formato de bd.json (sin la clave), para poder recrearla después.
"""
import json
import re
from pathlib import Path

from basedatos import Administracion, Conexion
from idiomas import t

NOMBRE_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")
TIPOS_CAMPO = ["entero", "texto", "decimal", "fecha"]


class ErrorAsistente(Exception):
    """Error con un mensaje claro para mostrarle al usuario."""


class AsistenteBD:
    def __init__(self, ruta_motores, carpeta_config):
        with open(ruta_motores, encoding="utf-8") as f:
            self.motores = json.load(f)
        self.carpeta_config = Path(carpeta_config)
        self.reiniciar()

    # ---------- estado ----------
    def reiniciar(self):
        self.tipo = None
        self.parametros = {}
        self.diseno = {"tablas": {}, "relaciones": []}
        self.analisis = None                # propuesta del analista (si la hubo)
        self.borrador = {"descripcion": "", "respuestas": {}}   # lo que va diciendo el usuario

    @property
    def conectado(self):
        return bool(self.tipo and self.parametros)

    def motor(self, tipo=None):
        tipo = tipo or self.tipo
        for m in self.motores:
            if m["id"] == tipo:
                return m
        raise ErrorAsistente(t("Ese tipo de base de datos no está en la lista."))

    def nombre_base(self):
        p = self.parametros
        return p.get("base") or (Path(p["archivo"]).stem if p.get("archivo") else p.get("usuario", "base"))

    def administracion(self):
        """Objeto Administracion sobre la base conectada (usar con 'with')."""
        if not self.conectado:
            raise ErrorAsistente(t("Primero escoja y conecte una base de datos."))
        return Administracion(Conexion.crear(self.tipo, **self.parametros))

    # ---------- paso 1: tipo ----------
    def escoger_tipo(self, tipo):
        self.motor(tipo)                    # valida que exista
        analisis = self.analisis            # el análisis se conserva al cambiar de motor
        self.reiniciar()
        self.analisis = analisis
        self.tipo = tipo

    # ---------- pasos 1 y 2: análisis del analista ----------
    def guardar_analisis(self, propuesta, tablas_aceptadas):
        """Guarda la propuesta con solo las tablas que el usuario aceptó."""
        tablas = {t: c for t, c in propuesta["tablas"].items() if t in tablas_aceptadas}
        relaciones = [r for r in propuesta["relaciones"]
                      if r["tabla"] in tablas and r["referencia"].split(".")[0] in tablas]
        self.analisis = {**propuesta, "tablas": tablas, "relaciones": relaciones}

    def tablas_pendientes(self):
        """Tablas propuestas que todavía no existen en la base."""
        if not self.analisis:
            return []
        existentes = {n.lower() for n, _ in self.tablas()}
        return [t for t in self.analisis["tablas"] if t.lower() not in existentes]

    def crear_propuesta(self):
        """Crea en la base las tablas propuestas que falten, con sus relaciones."""
        pendientes = self.tablas_pendientes()
        if not pendientes:
            raise ErrorAsistente(t("Las tablas propuestas ya están creadas."))
        config = {"tablas": self.analisis["tablas"], "relaciones": self.analisis["relaciones"]}
        try:
            with self.administracion() as admin:
                admin.crear_esquema(config)
        except Exception as e:
            raise ErrorAsistente(t("No se pudieron crear las tablas propuestas: {e}", e=e)) from e
        for tabla in pendientes:
            self.diseno["tablas"][tabla] = self.analisis["tablas"][tabla]
        self.diseno["relaciones"].extend(r for r in self.analisis["relaciones"]
                                         if r["tabla"] in pendientes)
        self.guardar_diseno()
        return pendientes

    # ---------- paso 2: ubicación y credenciales ----------
    def leer_parametros(self, formulario):
        """Toma del formulario solo los campos que pide este motor."""
        parametros = {}
        for campo in self.motor()["campos"]:
            if campo["tipo"] == "check":
                parametros[campo["nombre"]] = campo["nombre"] in formulario
            else:
                parametros[campo["nombre"]] = formulario.get(campo["nombre"], "").strip()
        return parametros

    def conectar(self, formulario, crear):
        """Conecta a una base existente, o la crea primero si crear=True."""
        motor = self.motor()
        parametros = self.leer_parametros(formulario)
        con_windows = parametros.get("confianza")
        faltan = [c["etiqueta"] for c in motor["campos"]
                  if c["tipo"] != "check" and not parametros[c["nombre"]]
                  and not (con_windows and c["nombre"] in ("usuario", "clave"))]
        if faltan:
            raise ErrorAsistente(t("Faltan datos: {campos}", campos=", ".join(t(f) for f in faltan)))
        if crear and not motor["puede_crear"]:
            raise ErrorAsistente(t("En {motor} la base la crea el administrador (DBA). Pídale los datos de conexión y escoja «Sí, ya la tengo».", motor=motor["nombre"]))

        admin = Administracion(Conexion.crear(self.tipo, **parametros))
        try:
            if crear:
                admin.crear_base()
            else:
                admin.con.probar()
        except ImportError as e:
            raise ErrorAsistente(t("Falta instalar la librería: {libreria}", libreria=t(motor["libreria"]))) from e
        except FileExistsError as e:
            raise ErrorAsistente(t("{e} Escoja «Sí, ya la tengo» para usarla.", e=e)) from e
        except Exception as e:
            raise ErrorAsistente(t("No se pudo crear la base: {e}", e=e) if crear else t("No se pudo abrir la base: {e}", e=e)) from e

        self.parametros = parametros
        self.cargar_diseno()                # si ya se había diseñado, lo recupera
        self.guardar_diseno()

    # ---------- paso 3: tablas ----------
    def tablas(self):
        """[(tabla, [campos])] de la base conectada."""
        with self.administracion() as admin:
            return [(t, admin.columnas(t)) for t in admin.listar_tablas()]

    def referencias(self):
        """Opciones para las llaves foráneas: 'tabla.campo'."""
        return [f"{t}.{c}" for t, campos in self.tablas() for c in campos]

    # ---------- paso 4: nueva tabla ----------
    def agregar_tabla(self, nombre, filas):
        """filas: lista de dict con nombre, tipo, largo, obligatorio, pk, auto, referencia."""
        nombre = nombre.strip()
        if not NOMBRE_VALIDO.match(nombre):
            raise ErrorAsistente(t("El nombre de la tabla debe empezar con letra y llevar solo letras, números o _ (sin espacios ni tildes)."))
        if nombre.lower() in {n.lower() for n, _ in self.tablas()}:
            raise ErrorAsistente(t("Ya existe una tabla llamada {nombre}.", nombre=nombre))

        campos, relaciones = {}, []
        for f in filas:
            campo = f["nombre"].strip()
            if not campo:
                continue
            if not NOMBRE_VALIDO.match(campo):
                raise ErrorAsistente(t("Nombre de campo no válido: «{campo}» (sin espacios ni tildes).", campo=campo))
            if campo.lower() in {c.lower() for c in campos}:
                raise ErrorAsistente(t("El campo «{campo}» está repetido.", campo=campo))
            if f["tipo"] not in TIPOS_CAMPO:
                raise ErrorAsistente(t("Tipo no válido en «{campo}».", campo=campo))
            d = {"tipo": f["tipo"]}
            if f["tipo"] == "texto":
                d["largo"] = int(f.get("largo") or 50)
            if f.get("obligatorio"):
                d["obligatorio"] = True
            if f.get("pk"):
                d["pk"] = True
                if f.get("auto"):
                    if f["tipo"] != "entero":
                        raise ErrorAsistente(t("Solo una llave primaria de tipo entero puede ser autonumérica."))
                    d["auto"] = True
            campos[campo] = d
            if f.get("referencia"):
                relaciones.append({"tabla": nombre, "campo": campo,
                                   "referencia": f["referencia"]})

        if not campos:
            raise ErrorAsistente(t("La tabla necesita al menos un campo."))
        if sum(1 for d in campos.values() if d.get("pk")) != 1:
            raise ErrorAsistente(t("Marque exactamente un campo como llave primaria."))

        try:
            with self.administracion() as admin:
                admin.crear_tabla(nombre, campos, relaciones)
        except Exception as e:
            raise ErrorAsistente(t("No se pudo crear la tabla: {e}", e=e)) from e

        self.diseno["tablas"][nombre] = campos
        self.diseno["relaciones"].extend(relaciones)
        self.guardar_diseno()

    # ---------- guardar el diseño ----------
    def ruta_diseno(self):
        return self.carpeta_config / f"{self.nombre_base()}.json"

    def cargar_diseno(self):
        """Recupera tablas y relaciones guardadas antes para esta misma base."""
        ruta = self.ruta_diseno()
        if ruta.exists():
            with ruta.open(encoding="utf-8") as f:
                guardado = json.load(f)
            if guardado.get("tipo") == self.tipo:
                self.diseno = {"tablas": guardado.get("tablas", {}),
                               "relaciones": guardado.get("relaciones", [])}
                if not self.analisis:
                    self.analisis = guardado.get("analisis")

    def guardar_diseno(self):
        """Guarda tipo, conexión (sin la clave), tablas y relaciones."""
        self.carpeta_config.mkdir(exist_ok=True)
        conexion = {k: v for k, v in self.parametros.items() if k != "clave"}
        datos = {"tipo": self.tipo, "conexion": conexion, **self.diseno}
        if self.analisis:
            datos["analisis"] = self.analisis   # descripción, respuestas y propuesta
        with self.ruta_diseno().open("w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
