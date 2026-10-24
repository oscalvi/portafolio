"""Catálogo y lanzador de aplicaciones de escritorio.

Las aplicaciones se definen en escritorio.json (no en el código):

    [
      {"id": "clientes", "nombre": "Clientes", "icono": "👤",
       "descripcion": "Captura de clientes", "archivo": "../main.py"}
    ]

"archivo" es relativo a la carpeta de escritorio.json.
Para agregar una aplicación nueva, solo se agrega un bloque al JSON.
"""
import json
import subprocess
import sys
from pathlib import Path
from idiomas import t


class Escritorio:
    def __init__(self, ruta_json):
        self.ruta = Path(ruta_json)
        self.carpeta = self.ruta.parent

    def lista(self):
        """Devuelve todas las aplicaciones del catálogo."""
        with self.ruta.open(encoding="utf-8") as f:
            return json.load(f)

    def buscar(self, id_app):
        return next((a for a in self.lista() if a["id"] == id_app), None)

    def abrir(self, id_app):
        """Minimiza el navegador y abre la aplicación. Devuelve un mensaje."""
        app = self.buscar(id_app)
        if app is None:
            return t("Esa aplicación no existe en el catálogo.")
        archivo = (self.carpeta / app["archivo"]).resolve()
        if not archivo.exists():
            return t("No encontré {archivo}.", archivo=archivo.name)
        self.minimizar_navegador()
        subprocess.Popen([sys.executable, str(archivo)], cwd=archivo.parent)
        return t("Abriendo {nombre}…", nombre=t(app["nombre"]))

    @staticmethod
    def minimizar_navegador():
        """Minimiza la ventana activa, que es el navegador donde se hizo clic.

        Solo funciona en Windows; en otros sistemas no hace nada.
        """
        if sys.platform != "win32":
            return
        import ctypes
        user32 = ctypes.windll.user32
        ventana = user32.GetForegroundWindow()
        if ventana:
            user32.ShowWindow(ventana, 6)        # 6 = SW_MINIMIZE
