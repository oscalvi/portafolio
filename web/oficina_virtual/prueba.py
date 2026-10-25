"""Prueba de las clases de basedatos.py.

Para cambiar de base de datos NO se toca este archivo ni basedatos.py:
solo se cambian "tipo" y "conexion" en bd.json (sqlite, sqlserver, mysql, oracle,
access, json, csv o excel).
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "comun"))  # clases genéricas

from basedatos import Administracion, Almacen, Conexion, ErrorDatos

CARPETA = Path(__file__).parent
CONFIG = CARPETA / "bd.json"

datos = Almacen.desde_config(CONFIG)                  # fábrica: el "tipo" escoge la clase
if hasattr(datos, "con"):                             # base relacional: crear tablas si faltan
    with Administracion(Conexion.desde_config(CONFIG)) as admin:
        admin.crear_esquema(admin.con.config)

with datos:
    nuevo = datos.escribir("clientes", {"nombre": "Prueba", "telefono": "305-555-0000"})
    print("Registro nuevo, ID:", nuevo, datos.buscar("clientes", nuevo))

    datos.actualizar("clientes", nuevo, {"telefono": "305-111-1111"})    # siempre por ID
    print("Actualizado:       ", datos.buscar("clientes", nuevo))

    print("Los 3 primeros por nombre:", datos.leer("clientes", orden="nombre", limite=3))

    try:
        datos.borrar("clientes", None)                # sin ID: no se permite
    except ErrorDatos as e:
        print("Bloqueado:", e)

    datos.borrar("clientes", nuevo)
    print("Total de clientes: ", datos.contar("clientes"))
