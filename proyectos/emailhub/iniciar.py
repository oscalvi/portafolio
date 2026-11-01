"""Email Hub - starts the whole app with one command (used by the portfolio).

What it does, in order:
  1. Uses the project's own virtual environment (.venv); if it doesn't exist yet,
     creates it and installs requirements.txt (only the first time).
  2. Creates .env with a new encryption key if it is missing.
  3. Updates the database (manage.py migrate).
  4. Starts the background worker (qcluster) and the web server (runserver).
Closing this window stops both.

Run it:  python iniciar.py      (port 8000, or the PORT environment variable)
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
VENV = CARPETA / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARCA = VENV / ".requisitos_ok"


class EmailHub:
    """Prepares the environment and runs the web server plus the worker."""

    def __init__(self, puerto: str | None = None):
        self.puerto = puerto or os.environ.get("PORT", "8000")

    # -- preparation -------------------------------------------------------
    def preparar_entorno(self) -> None:
        if not PYTHON.exists():
            print("Creating the virtual environment (only the first time)...")
            venv.create(VENV, with_pip=True)
        if not MARCA.exists():
            print("Installing the libraries (only the first time)...")
            self._python("-m", "pip", "install", "--upgrade", "pip", "-q")
            self._python("-m", "pip", "install", "-r", "requirements.txt", "-q")
            MARCA.write_text("ok", encoding="utf-8")

    def preparar_env(self) -> None:
        """Creates .env from .env.example with a fresh encryption key, if it doesn't exist."""
        destino = CARPETA / ".env"
        if destino.exists():
            return
        clave = subprocess.run(
            [str(PYTHON), "-c", "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"],
            capture_output=True, text=True, check=True).stdout.strip()
        secreto = subprocess.run(
            [str(PYTHON), "-c", "import secrets; print(secrets.token_urlsafe(50))"],
            capture_output=True, text=True, check=True).stdout.strip()
        texto = (CARPETA / ".env.example").read_text(encoding="utf-8")
        texto = texto.replace("FIELD_ENCRYPTION_KEY=", f"FIELD_ENCRYPTION_KEY={clave}", 1)
        texto = texto.replace("DJANGO_SECRET_KEY=dev-insecure-change-me", f"DJANGO_SECRET_KEY={secreto}", 1)
        destino.write_text(texto, encoding="utf-8")
        print("Created .env with a new encryption key (keep this file private).")

    # -- run ---------------------------------------------------------------
    def correr(self) -> int:
        self.preparar_entorno()
        self.preparar_env()
        self._python("manage.py", "migrate", "--noinput", "-v", "0")
        trabajador = subprocess.Popen([str(PYTHON), "manage.py", "qcluster"], cwd=CARPETA)
        print(f"Email Hub is running at http://127.0.0.1:{self.puerto}/  (close this window to stop it)")
        try:
            return subprocess.call(
                [str(PYTHON), "manage.py", "runserver", f"127.0.0.1:{self.puerto}", "--noreload"], cwd=CARPETA)
        except KeyboardInterrupt:
            return 0
        finally:
            trabajador.terminate()

    @staticmethod
    def _python(*argumentos: str) -> None:
        subprocess.run([str(PYTHON), *argumentos], cwd=CARPETA, check=True)


def main() -> None:
    try:
        sys.exit(EmailHub().correr())
    except subprocess.CalledProcessError as error:
        print(f"\nEmail Hub could not start: {error}")
        input("Press Enter to close this window.")
        sys.exit(1)


if __name__ == "__main__":
    main()
