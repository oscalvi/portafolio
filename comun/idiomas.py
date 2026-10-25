"""Idiomas de la aplicación.

Cómo funciona:
    - Los textos se escriben en español dentro del código y de las plantillas,
      envueltos en t("..."). El español es el texto original.
    - idiomas/en.json traduce cada texto al inglés: {"texto en español": "English text"}.
      Para agregar otro idioma basta con crear idiomas/<código>.json.
    - El idioma de cada visitante se escoge así:
        1. Si eligió uno en el selector EN | ES, se usa ese (queda en una cookie).
        2. Si no, el idioma configurado en su navegador (encabezado Accept-Language).
        3. Si su navegador no está en un idioma disponible, inglés.

    Textos con datos variables:  t("Faltan datos: {campos}", campos="Servidor")
"""
import json
from pathlib import Path

PREDETERMINADO = "en"
ORIGINAL = "es"                     # idioma en que están escritos los textos


class Traductor:
    NOMBRES = {"en": "English", "es": "Español"}

    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.diccionarios = {}
        for ruta in self.carpeta.glob("*.json"):
            self.diccionarios[ruta.stem] = json.loads(ruta.read_text(encoding="utf-8"))
        self.disponibles = sorted({ORIGINAL, *self.diccionarios})

    def traducir(self, texto, idioma, **datos):
        if not isinstance(texto, str):
            return texto
        if idioma != ORIGINAL:
            texto = self.diccionarios.get(idioma, {}).get(texto, texto)
        return texto.format(**datos) if datos else texto

    def elegir(self, peticion):
        """Idioma del visitante: selector (cookie o ?lang=) → navegador → inglés."""
        pedido = peticion.args.get("lang") or peticion.cookies.get("idioma")
        if pedido in self.disponibles:
            return pedido
        return peticion.accept_languages.best_match(self.disponibles) or PREDETERMINADO


# ---- Acceso desde cualquier clase (sin depender de Flask) ----
_traductor = None
_idioma_actual = lambda: PREDETERMINADO


def configurar(traductor, funcion_idioma):
    """Lo llama app.py al arrancar: indica el traductor y cómo saber el idioma actual."""
    global _traductor, _idioma_actual
    _traductor, _idioma_actual = traductor, funcion_idioma


def idioma():
    try:
        return _idioma_actual()
    except Exception:                   # fuera de una petición web (consola, pruebas)
        return ORIGINAL


def t(texto, **datos):
    """Traduce un texto al idioma actual del visitante."""
    if _traductor is None:
        return texto.format(**datos) if datos else texto
    return _traductor.traducir(texto, idioma(), **datos)
