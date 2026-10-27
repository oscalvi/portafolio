"""Aplicaciones web externas: cada una es su propio servidor Flask (por ejemplo, EmailMover).

Se declaran en aplicaciones_web.json con un bloque "externa" en vez de "ruta":

    {"id": "emailmover", "nombre": "EmailMover", "icono": "✉️", "descripcion": "...",
     "externa": {"archivo": "../emailmover/app.py", "puerto": 5050}}

"archivo" es relativo a la carpeta de aplicaciones_web.json. Al abrirla, si su servidor
no está corriendo, se arranca en ese puerto y se espera a que responda.

Para aplicaciones que no son de Python (por ejemplo, AI Litigation en Node.js) se usa "comando":

    "externa": {"archivo": "../ai_litigation/app/modules/demo/iniciar.mjs",
                "carpeta": "../ai_litigation/app", "puerto": 4318,
                "comando": ["node", "--experimental-strip-types", "modules/demo/iniciar.mjs"],
                "entorno": {"JA_RAMA_JUDICIAL": "publica"}}
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from idiomas import t


class AplicacionExterna:
    def __init__(self, carpeta, datos):
        self.nombre = datos["nombre"]
        externa = datos["externa"]
        self.archivo = (Path(carpeta) / externa["archivo"]).resolve()
        self.puerto = int(externa["puerto"])
        self.comando = externa.get("comando")                     # None: es una aplicación de Python
        self.cwd = (Path(carpeta) / externa["carpeta"]).resolve() if externa.get("carpeta") else self.archivo.parent
        self.entorno = {str(k): str(v) for k, v in (externa.get("entorno") or {}).items()}

    @property
    def url(self):
        return f"http://127.0.0.1:{self.puerto}/"

    def corriendo(self):
        with socket.socket() as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", self.puerto)) == 0

    def abrir(self, espera=30):
        """Arranca el servidor si hace falta. Devuelve (url, None) o (None, mensaje de error)."""
        if self.corriendo():
            return self.url, None
        if not self.archivo.exists():
            return None, t("No encontré {archivo}.", archivo=self.archivo.name)
        entorno = dict(os.environ, PORT=str(self.puerto), **self.entorno)
        opciones = {"creationflags": subprocess.CREATE_NEW_CONSOLE} if sys.platform == "win32" else {}
        comando = list(self.comando) if self.comando else [sys.executable, str(self.archivo)]
        if not shutil.which(comando[0]) and comando[0] != sys.executable:
            return None, t("Para abrir {nombre} hace falta instalar {programa}.", nombre=self.nombre, programa=comando[0])
        subprocess.Popen(comando, cwd=self.cwd, env=entorno, **opciones)
        limite = time.time() + espera
        while time.time() < limite:
            if self.corriendo():
                return self.url, None
            time.sleep(0.3)
        return None, t("{nombre} no respondió. Revise la ventana de su servidor.", nombre=self.nombre)
