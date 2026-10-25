from tkinter import messagebox
from ventanas import Ventana


def abrir_cliente(padre):
    v = Ventana("Datos del cliente", 400, 220, padre)

    campos = ["Nombre", "Teléfono", "Correo"]
    entradas = {}
    for fila, campo in enumerate(campos):
        v.label(campo + ":").grid(row=fila, column=0, padx=5, pady=5, sticky="e")
        entradas[campo] = v.texto()
        entradas[campo].grid(row=fila, column=1, padx=5, pady=5)

    def guardar():
        if not entradas["Nombre"].get():
            messagebox.showwarning("Falta dato", "El nombre es obligatorio")
            return
        messagebox.showinfo("Guardado", "Cliente capturado")
        v.cerrar()

    v.boton("Guardar", guardar).grid(row=3, column=1, pady=10)