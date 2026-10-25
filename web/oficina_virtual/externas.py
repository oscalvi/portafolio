"""Aplicaciones web externas: cada una es su propio servidor Flask (por ejemplo, EmailMover).

Se declaran en aplicaciones_web.json con un bloque "externa" en vez de "ruta":

    {"id": "emailmover", "nombre": "EmailMover", "icono": "✉️", "descripcion": "...",
     "externa": {"archivo": "../emailmover/app.py", "puerto": 5050}}

"archivo" es relativo a la carpeta de aplicaciones_web.json. Al abrirla, si su servidor
no está corriendo, se arranca en ese puerto y se espera a que responda.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from idiomas import t


class AplicacionExterna:
    def __init__(self, carpeta, datos):
        self.nombre = datos["nombre"]
        self.archivo = (Path(carpeta) / datos["externa"]["archivo"]).resolve()
        self.puerto = int(datos["externa"]["puerto"])

    @property
    def url(self):
        return f"http://127.0.0.1:{self.puerto}/"

    def corriendo(self):
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", self.puerto)) == 0

    def abrir(self, espera=15):
        """Arranca el servidor si hace falta. Devuelve (url, None) o (None, mensaje de error)."""
        if self.corriendo():
            return self.url, None
        if not self.archivo.exists():
            return None, t("No encontré {archivo}.", archivo=self.archivo.name)
        entorno = dict(os.environ, PORT=str(self.puerto))
        opciones = {"creationflags": subprocess.CREATE_NEW_CONSOLE} if sys.platform == "win32" else {}
        subprocess.Popen([sys.executable, str(self.archivo)], cwd=self.archivo.parent, env=entorno, **opciones)
        limite = time.time() + espera
        while time.time() < limite:
            if self.corriendo():
                return self.url, None
            time.sleep(0.3)
        return None, t("{nombre} no respondió. Revise la ventana de su servidor.", nombre=self.nombre)
