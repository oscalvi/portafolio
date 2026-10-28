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


def buscar_programa(nombre):
    """Ruta completa de un programa (por ejemplo, node).

    Primero busca en el PATH. Si no está (pasa cuando el portafolio se abrió antes de instalar
    Node.js, o cuando el instalador no actualizó el PATH de esta sesión), revisa las carpetas
    donde Windows suele instalarlo. Devuelve None si no lo encuentra.
    """
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    if sys.platform != "win32":
        return None
    exe = nombre if nombre.lower().endswith(".exe") else nombre + ".exe"
    carpetas = [os.environ.get("NVM_SYMLINK", "")]
    for variable, sub in (("ProgramFiles", "nodejs"), ("ProgramFiles(x86)", "nodejs"),
                          ("LOCALAPPDATA", r"Programs\nodejs"), ("ProgramW6432", "nodejs")):
        if os.environ.get(variable):
            carpetas.append(os.path.join(os.environ[variable], sub))
    nvm = os.environ.get("NVM_HOME") or os.path.join(os.environ.get("APPDATA", ""), "nvm")
    if os.path.isdir(nvm):
        carpetas += sorted((str(d) for d in Path(nvm).iterdir() if d.is_dir()), reverse=True)
    for carpeta in carpetas:
        ruta = os.path.join(carpeta, exe) if carpeta else ""
        if ruta and os.path.isfile(ruta):
            return ruta
    return None


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
        if self.comando:
            # Aplicaciones con su propio botón "Terminar" (AI Litigation): corren sin ventana negra.
            # Lo que escriben queda en servidor.log, en su carpeta, por si hay que revisar un error.
            registro = open(self.cwd / "servidor.log", "a", encoding="utf-8")
            opciones = {"stdout": registro, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
            if sys.platform == "win32":
                opciones["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            opciones = {"creationflags": subprocess.CREATE_NEW_CONSOLE} if sys.platform == "win32" else {}
        comando = list(self.comando) if self.comando else [sys.executable, str(self.archivo)]
        if comando[0] != sys.executable:
            programa = buscar_programa(comando[0])
            if not programa:
                return None, t("Para abrir {nombre} hace falta instalar {programa}.", nombre=self.nombre, programa=comando[0])
            comando[0] = programa                                 # ruta completa: no depende del PATH
        subprocess.Popen(comando, cwd=self.cwd, env=entorno, **opciones)
        if "stdout" in opciones:
            opciones["stdout"].close()                            # el proceso conserva su propia copia
        limite = time.time() + espera
        while time.time() < limite:
            if self.corriendo():
                return self.url, None
            time.sleep(0.3)
        return None, t("{nombre} no respondió. Revise la ventana de su servidor.", nombre=self.nombre)
