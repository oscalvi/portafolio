"""
Manejo genérico de bases de datos, en programación orientada a objetos.

ESTRUCTURA
    GestorBD                 Clase padre: abrir, cerrar, ejecutar, confirmar, 'with'.
    ├── Conexion             Cómo hablar con cada motor (una subclase por motor):
    │     ├── SQLite             abrir, marcador de parámetros, tipos de campo,
    │     ├── Access             autonumérico, crear la base vacía, listar tablas.
    │     ├── SQLServer
    │     ├── MySQL
    │     └── Oracle
    ├── Administracion       Estructura de la base (DDL): crear base y tablas,
    │                        borrar tablas, agregar campos, vistas, procedimientos.
    └── Datos                Manipulación de datos (DML): leer, escribir,
                             actualizar, borrar, contar.

    Administracion y Datos reciben un objeto Conexion y le preguntan lo que
    cambia según el motor. Para agregar un motor nuevo basta con escribir su
    subclase de Conexion: la administración y los datos funcionan sin cambios.

LIBRERÍA NECESARIA POR MOTOR
    "sqlite"     -> incluida en Python
    "sqlserver"  -> pip install pyodbc   (y ODBC Driver 17 for SQL Server)
    "access"     -> pip install pyodbc pywin32   (y driver de Access)
    "oracle"     -> pip install oracledb
    "mysql"      -> pip install mysql-connector-python

PARÁMETROS DE CONEXIÓN POR MOTOR
    sqlite     -> archivo
    access     -> archivo (.accdb o .mdb)
    sqlserver  -> servidor, base, y usuario + clave  (o confianza=True para Windows)
    mysql      -> servidor, base, usuario, clave
    oracle     -> usuario, clave, dsn  (ej. "servidor:1521/servicio")

USO
    from basedatos import Conexion, Administracion, Datos

    con   = Conexion.crear("sqlite", archivo="mi_base.db")      # fábrica
    admin = Administracion(con)
    datos = Datos(con)

    with admin:
        admin.crear_tabla("clientes", {
            "id":     {"tipo": "entero", "pk": True, "auto": True},
            "nombre": {"tipo": "texto", "largo": 60, "obligatorio": True}})
        print(admin.listar_tablas())

    with datos:
        datos.escribir("clientes", {"nombre": "Ana"})
        datos.actualizar("clientes", {"nombre": "Ana María"}, {"id": 1})
        print(datos.leer("clientes"))
        datos.borrar("clientes", {"id": 1})

    O todo desde un archivo de configuración:
        con = Conexion.desde_config("bd.json")
        with Administracion(con) as admin:
            admin.crear_esquema(con.config)     # crea lo que falte

FORMATO DEL ARCHIVO DE CONFIGURACIÓN (bd.json)
    {
      "tipo": "sqlite",
      "conexion": {"archivo": "clientes.db"},
      "tablas": {
        "clientes": {
          "id":       {"tipo": "entero", "pk": true, "auto": true},
          "nombre":   {"tipo": "texto", "largo": 60, "obligatorio": true}
        },
        "facturas": {
          "id":         {"tipo": "entero", "pk": true, "auto": true},
          "cliente_id": {"tipo": "entero", "obligatorio": true},
          "valor":      {"tipo": "decimal"}
        }
      },
      "relaciones": [
        {"tabla": "facturas", "campo": "cliente_id", "referencia": "clientes.id"}
      ],
      "vistas":         {"v_facturas": "SELECT ... FROM ..."},
      "procedimientos": {"sp_nombre": "<cuerpo SQL propio del motor>"}
    }
    Tipos genéricos de campo: entero, texto, decimal, fecha.
    "auto": true -> el motor numera solo (IDENTITY, AUTO_INCREMENT, COUNTER...).
    "relaciones", "vistas" y "procedimientos" son opcionales.
"""
import json
import sqlite3
from abc import abstractmethod
from pathlib import Path


# =====================================================================
#  CLASE PADRE
# =====================================================================

class GestorBD:
    """Comportamiento común: todo pasa por un objeto Conexion."""

    def __init__(self, conexion):
        self.con = conexion

    def abrir(self):
        self.con.abrir()
        return self

    def cerrar(self):
        self.con.cerrar()

    def ejecutar(self, sql, valores=()):
        return self.con.ejecutar(sql, valores)

    def confirmar(self):
        self.con.confirmar()

    # abrir y cerrar solos con 'with'
    def __enter__(self):
        return self.abrir()

    def __exit__(self, *errores):
        self.cerrar()


# =====================================================================
#  CONEXIÓN: lo que cambia según el motor
# =====================================================================

class Conexion(GestorBD):
    """Clase base de los motores. Cada subclase define cómo conectarse."""

    TIPOS = {"entero": "INTEGER", "texto": "VARCHAR({largo})",
             "decimal": "DECIMAL(12,2)", "fecha": "DATE"}
    AUTO = "INTEGER PRIMARY KEY"            # cómo se escribe un id autonumérico
    soporta_procedimientos = True

    def __init__(self, config=None, **parametros):
        super().__init__(self)              # la conexión es su propio gestor
        self.parametros = parametros
        self.config = config or {}
        self.enlace = None                  # conexión real del driver
        self._usos = 0                      # permite 'with' anidados

    # ---------- fábrica ----------
    @staticmethod
    def crear(tipo, config=None, **parametros):
        motores = {"sqlite": SQLite, "sqlserver": SQLServer, "access": Access,
                   "oracle": Oracle, "mysql": MySQL}
        try:
            return motores[tipo.lower()](config, **parametros)
        except KeyError:
            raise ValueError(f"Tipo de base de datos no soportado: {tipo}") from None

    @staticmethod
    def desde_config(ruta_json):
        with open(ruta_json, encoding="utf-8") as f:
            config = json.load(f)
        return Conexion.crear(config["tipo"], config, **config["conexion"])

    # ---------- abrir y cerrar ----------
    @abstractmethod
    def conectar(self):
        """Devuelve la conexión del driver. Cada motor la implementa."""

    def abrir(self):
        if self._usos == 0:
            self.enlace = self.conectar()
        self._usos += 1
        return self

    def cerrar(self):
        self._usos = max(self._usos - 1, 0)
        if self._usos == 0 and self.enlace:
            self.enlace.close()
            self.enlace = None

    def probar(self):
        """Abre y cierra: lanza un error si algo está mal."""
        with self:
            pass

    def ejecutar(self, sql, valores=()):
        cursor = self.enlace.cursor()
        cursor.execute(sql, list(valores))
        return cursor

    def confirmar(self):
        self.enlace.commit()

    def deshacer(self):
        self.enlace.rollback()

    # ---------- dialecto: lo que cada motor escribe distinto ----------
    def marcador(self, n):
        """Marcador de parámetro en las instrucciones SQL."""
        return "?"

    def tipo_campo(self, definicion):
        if definicion.get("auto"):
            return self.AUTO
        return self.TIPOS[definicion["tipo"]].format(largo=definicion.get("largo", 50))

    def sql_procedimiento(self, nombre, cuerpo):
        return f"CREATE PROCEDURE {nombre} AS {cuerpo}"

    def crear_base(self):
        raise NotImplementedError(f"En {type(self).__name__} la base la crea el "
                                  "administrador; pídale los datos de conexión.")

    def listar_tablas(self):
        cursor = self.ejecutar("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                               "WHERE TABLE_TYPE = 'BASE TABLE'")
        return sorted(fila[0] for fila in cursor.fetchall())


class SQLite(Conexion):
    """Parámetros: archivo"""
    TIPOS = {**Conexion.TIPOS, "texto": "TEXT", "decimal": "REAL", "fecha": "TEXT"}
    AUTO = "INTEGER PRIMARY KEY"
    soporta_procedimientos = False

    def conectar(self):
        enlace = sqlite3.connect(self.parametros["archivo"])
        enlace.execute("PRAGMA foreign_keys = ON")
        return enlace

    def crear_base(self):
        archivo = Path(self.parametros["archivo"])
        if archivo.exists():
            raise FileExistsError(f"Ya existe {archivo}.")
        archivo.parent.mkdir(parents=True, exist_ok=True)
        self.probar()                       # SQLite crea el archivo al conectarse

    def listar_tablas(self):
        cursor = self.ejecutar("SELECT name FROM sqlite_master WHERE type = 'table' "
                               "AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return [fila[0] for fila in cursor.fetchall()]


class Access(Conexion):
    """Parámetros: archivo (.accdb o .mdb)"""
    TIPOS = {"entero": "LONG", "texto": "TEXT({largo})",
             "decimal": "CURRENCY", "fecha": "DATETIME"}
    AUTO = "COUNTER PRIMARY KEY"
    soporta_procedimientos = False

    def conectar(self):
        import pyodbc
        return pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ="
                              + self.parametros["archivo"])

    def crear_base(self):
        import win32com.client              # pip install pywin32
        archivo = Path(self.parametros["archivo"])
        if archivo.exists():
            raise FileExistsError(f"Ya existe {archivo}.")
        archivo.parent.mkdir(parents=True, exist_ok=True)
        catalogo = win32com.client.Dispatch("ADOX.Catalog")
        catalogo.Create(f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={archivo}")

    def listar_tablas(self):
        return sorted(t.table_name for t in self.enlace.cursor().tables(tableType="TABLE"))


class SQLServer(Conexion):
    """Parámetros: servidor, base, usuario, clave (o confianza=True para Windows)"""
    TIPOS = {**Conexion.TIPOS, "texto": "NVARCHAR({largo})"}
    AUTO = "INT IDENTITY(1,1) PRIMARY KEY"

    def _cadena(self, base):
        p = self.parametros
        cadena = (f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={p['servidor']};"
                  f"DATABASE={base};")
        if p.get("confianza"):
            return cadena + "Trusted_Connection=yes;"
        return cadena + f"UID={p['usuario']};PWD={p['clave']};"

    def conectar(self):
        import pyodbc
        return pyodbc.connect(self._cadena(self.parametros["base"]))

    def crear_base(self):
        import pyodbc
        with pyodbc.connect(self._cadena("master"), autocommit=True) as enlace:
            enlace.execute(f"CREATE DATABASE [{self.parametros['base']}]")


class MySQL(Conexion):
    """Parámetros: servidor, base, usuario, clave"""
    AUTO = "INT AUTO_INCREMENT PRIMARY KEY"

    def conectar(self, con_base=True):
        import mysql.connector
        p = self.parametros
        extra = {"database": p["base"]} if con_base else {}
        return mysql.connector.connect(host=p["servidor"], user=p["usuario"],
                                       password=p["clave"], **extra)

    def crear_base(self):
        enlace = self.conectar(con_base=False)
        enlace.cursor().execute(f"CREATE DATABASE `{self.parametros['base']}`")
        enlace.close()

    def listar_tablas(self):
        cursor = self.ejecutar("SELECT TABLE_NAME FROM information_schema.TABLES "
                               "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
                               "ORDER BY TABLE_NAME")
        return [fila[0] for fila in cursor.fetchall()]

    def marcador(self, n):
        return "%s"

    def sql_procedimiento(self, nombre, cuerpo):
        return f"CREATE PROCEDURE {nombre}() BEGIN {cuerpo} END"


class Oracle(Conexion):
    """Parámetros: usuario, clave, dsn (ej. 'servidor:1521/servicio')"""
    TIPOS = {"entero": "NUMBER(10)", "texto": "VARCHAR2({largo})",
             "decimal": "NUMBER(12,2)", "fecha": "DATE"}
    AUTO = "NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"

    def conectar(self):
        import oracledb
        p = self.parametros
        return oracledb.connect(user=p["usuario"], password=p["clave"], dsn=p["dsn"])

    def listar_tablas(self):
        cursor = self.ejecutar("SELECT table_name FROM user_tables ORDER BY table_name")
        return [fila[0] for fila in cursor.fetchall()]

    def marcador(self, n):
        return f":{n}"

    def sql_procedimiento(self, nombre, cuerpo):
        return f"CREATE OR REPLACE PROCEDURE {nombre} AS {cuerpo}"


# =====================================================================
#  ADMINISTRACIÓN: estructura de la base (DDL)
# =====================================================================

class Administracion(GestorBD):

    def crear_base(self):
        """Crea la base vacía y verifica que se pueda abrir."""
        self.con.crear_base()
        self.con.probar()

    def listar_tablas(self):
        return self.con.listar_tablas()

    def columnas(self, tabla):
        cursor = self.ejecutar(f"SELECT * FROM {tabla} WHERE 1 = 0")
        return [d[0] for d in cursor.description]

    def existe(self, nombre):
        """True si la tabla o vista ya existe."""
        try:
            self.ejecutar(f"SELECT * FROM {nombre} WHERE 1 = 0")
            return True
        except Exception:
            self.con.deshacer()
            return False

    def _definicion(self, nombre, d):
        col = f"{nombre} {self.con.tipo_campo(d)}"
        if d.get("pk") and not d.get("auto"):
            col += " PRIMARY KEY"
        elif d.get("obligatorio"):
            col += " NOT NULL"
        return col

    def crear_tabla(self, tabla, campos, relaciones=()):
        """campos:     {"id": {"tipo": "entero", "pk": True, "auto": True}, ...}
           relaciones: [{"tabla": tabla, "campo": "cliente_id", "referencia": "clientes.id"}]"""
        columnas = [self._definicion(n, d) for n, d in campos.items()]
        for r in relaciones:
            if r["tabla"] == tabla:
                ref_tabla, ref_campo = r["referencia"].split(".")
                columnas.append(f"FOREIGN KEY ({r['campo']}) "
                                f"REFERENCES {ref_tabla}({ref_campo})")
        self.ejecutar(f"CREATE TABLE {tabla} ({', '.join(columnas)})")
        self.confirmar()

    def borrar_tabla(self, tabla):
        self.ejecutar(f"DROP TABLE {tabla}")
        self.confirmar()

    def agregar_campo(self, tabla, nombre, definicion):
        self.ejecutar(f"ALTER TABLE {tabla} ADD {self._definicion(nombre, definicion)}")
        self.confirmar()

    def crear_vista(self, nombre, sql):
        self.ejecutar(f"CREATE VIEW {nombre} AS {sql}")
        self.confirmar()

    def crear_procedimiento(self, nombre, cuerpo):
        if not self.con.soporta_procedimientos:
            print(f"Aviso: {type(self.con).__name__} no soporta procedimientos almacenados.")
            return
        self.ejecutar(self.con.sql_procedimiento(nombre, cuerpo))
        self.confirmar()

    def crear_esquema(self, config):
        """Crea lo que falte de un diseño completo (formato de bd.json)."""
        if not config.get("tablas"):
            raise ValueError("Falta la configuración de tablas. "
                             "Ver documentación al inicio de basedatos.py")
        relaciones = config.get("relaciones", [])
        for tabla, campos in config["tablas"].items():
            if not self.existe(tabla):
                self.crear_tabla(tabla, campos, relaciones)
        for nombre, sql in config.get("vistas", {}).items():
            if not self.existe(nombre):
                self.crear_vista(nombre, sql)
        for nombre, cuerpo in config.get("procedimientos", {}).items():
            self.crear_procedimiento(nombre, cuerpo)


# =====================================================================
#  DATOS: manipulación de registros (DML)
# =====================================================================

class Datos(GestorBD):

    def _donde(self, condiciones, inicio=0):
        if not condiciones:
            return "", []
        partes = [f"{c} = {self.con.marcador(inicio + i + 1)}"
                  for i, c in enumerate(condiciones)]
        return " WHERE " + " AND ".join(partes), list(condiciones.values())

    def leer(self, tabla, condiciones=None, campos="*"):
        where, valores = self._donde(condiciones)
        cursor = self.ejecutar(f"SELECT {campos} FROM {tabla}{where}", valores)
        columnas = [d[0] for d in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    def contar(self, tabla, condiciones=None):
        where, valores = self._donde(condiciones)
        return self.ejecutar(f"SELECT COUNT(*) FROM {tabla}{where}", valores).fetchone()[0]

    def escribir(self, tabla, datos):
        columnas = ", ".join(datos)
        marcas = ", ".join(self.con.marcador(i + 1) for i in range(len(datos)))
        self.ejecutar(f"INSERT INTO {tabla} ({columnas}) VALUES ({marcas})", datos.values())
        self.confirmar()

    def actualizar(self, tabla, datos, condiciones):
        sets = ", ".join(f"{c} = {self.con.marcador(i + 1)}" for i, c in enumerate(datos))
        where, valores = self._donde(condiciones, inicio=len(datos))
        cursor = self.ejecutar(f"UPDATE {tabla} SET {sets}{where}",
                               list(datos.values()) + valores)
        self.confirmar()
        return cursor.rowcount

    def borrar(self, tabla, condiciones):
        where, valores = self._donde(condiciones)
        cursor = self.ejecutar(f"DELETE FROM {tabla}{where}", valores)
        self.confirmar()
        return cursor.rowcount
