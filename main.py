from ventanas import Ventana
from cliente import abrir_cliente

app = Ventana("Mi Aplicación", 400, 250)

app.label("Menú principal").pack(pady=10)
app.boton("Capturar cliente", lambda: abrir_cliente(app.raiz)).pack(pady=5)
app.boton("Salir", app.cerrar).pack(pady=5)

app.iniciar()