"""Prueba de las clases de basedatos.py.

Para cambiar de base de datos NO se toca este archivo ni basedatos.py:
solo se cambian "tipo" y "conexion" en bd.json.
"""
from pathlib import Path

from basedatos import Administracion, Conexion, Datos

CARPETA = Path(__file__).parent

con = Conexion.desde_config(CARPETA / "bd.json")     # fábrica: escoge el motor

with Administracion(con) as admin:                    # estructura (DDL)
    admin.crear_esquema(con.config)                   # crea la tabla si no existe
    print("Tablas:", admin.listar_tablas())
    print("Campos de clientes:", admin.columnas("clientes"))

with Datos(con) as datos:                             # registros (DML)
    datos.escribir("clientes", {"nombre": "Prueba", "telefono": "305-555-0000"})
    print("Después de escribir:", datos.leer("clientes", {"nombre": "Prueba"}))

    datos.actualizar("clientes", {"telefono": "305-111-1111"}, {"nombre": "Prueba"})
    print("Actualizado:        ", datos.leer("clientes", {"nombre": "Prueba"}))

    datos.borrar("clientes", {"nombre": "Prueba"})
    print("Total de clientes:  ", datos.contar("clientes"))
