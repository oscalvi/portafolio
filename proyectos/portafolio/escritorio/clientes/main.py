# Las clases genéricas (basedatos, idiomas, ventanas) viven en la carpeta "comun" del proyecto
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "comun"))

from ventanas import Ventana
from cliente import abrir_cliente

app = Ventana("Mi Aplicación", 400, 250)

app.label("Menú principal").pack(pady=10)
app.boton("Capturar cliente", lambda: abrir_cliente(app.raiz)).pack(pady=5)
app.boton("Salir", app.cerrar).pack(pady=5)

app.iniciar()