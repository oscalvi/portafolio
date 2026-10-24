import tkinter as tk

COLOR_FONDO = "#E8F0FE"
COLOR_BOTON = "#1A73E8"
COLOR_TEXTO_BOTON = "white"
FUENTE = ("Arial", 10)
FUENTE_NEGRITA = ("Arial", 10, "bold")


""" class Ventana:
    def __init__(self, titulo, ancho, alto, padre=None):
        if padre is None:
            self.raiz = tk.Tk()
        else:
            self.raiz = tk.Toplevel(padre)
        self.raiz.title(titulo)
        self.raiz.configure(bg=COLOR_FONDO)
        self.centrar(ancho, alto)

        self.marco = tk.Frame(self.raiz, bg=COLOR_FONDO)
        self.marco.place(relx=0.5, rely=0.5, anchor="center")

    def centrar(self, ancho, alto):
        self.raiz.update_idletasks()
        x = (self.raiz.winfo_screenwidth() - ancho) // 2
        y = (self.raiz.winfo_screenheight() - alto) // 2
        self.raiz.geometry(f"{ancho}x{alto}+{x}+{y}")

    def label(self, texto):
        return tk.Label(self.marco, text=texto, bg=COLOR_FONDO, font=FUENTE_NEGRITA)

    def texto(self, ancho=30):
        return tk.Entry(self.marco, width=ancho, font=FUENTE)

    def boton(self, texto, accion):
        return tk.Button(self.marco, text=texto, command=accion, width=15,
                         bg=COLOR_BOTON, fg=COLOR_TEXTO_BOTON, font=FUENTE_NEGRITA)

    def cerrar(self):
        self.raiz.destroy()

    def iniciar(self):
        self.raiz.mainloop() """

class Ventana:
    def __init__(self, titulo, ancho, alto, padre=None, color=COLOR_FONDO):
        self.color = color
        if padre is None:
            self.raiz = tk.Tk()
        else:
            self.raiz = tk.Toplevel(padre)
        self.raiz.title(titulo)
        self.raiz.configure(bg=self.color)
        self.centrar(ancho, alto)

        self.marco = tk.Frame(self.raiz, bg=self.color)
        self.marco.place(relx=0.5, rely=0.5, anchor="center")
        self.al_frente()

    def al_frente(self):
        """Pone la ventana delante de todas (por ejemplo, del navegador)."""
        self.raiz.lift()
        self.raiz.attributes("-topmost", True)        # la sube encima de todo
        self.raiz.after(300, lambda: self.raiz.attributes("-topmost", False))
        self.raiz.focus_force()                       # le da el foco del teclado

    def centrar(self, ancho, alto):
        self.raiz.update_idletasks()
        x = (self.raiz.winfo_screenwidth() - ancho) // 2
        y = (self.raiz.winfo_screenheight() - alto) // 2
        self.raiz.geometry(f"{ancho}x{alto}+{x}+{y}")

    def label(self, texto, padre=None, fuente=FUENTE_NEGRITA):
        return tk.Label(padre or self.marco, text=texto, bg=self.color, font=fuente)

    def texto(self, ancho=30):
        return tk.Entry(self.marco, width=ancho, font=FUENTE)

    def boton(self, texto, accion):
        return tk.Button(self.marco, text=texto, command=accion, width=15,
                         bg=COLOR_BOTON, fg=COLOR_TEXTO_BOTON, font=FUENTE_NEGRITA)

    def opcion(self, texto, variable, valor, accion=None):
        return tk.Radiobutton(self.marco, text=texto, variable=variable, value=valor,
                              command=accion, bg=self.color, font=FUENTE, anchor="w")

    """     def opcion(self, texto, variable, valor):
        return tk.Radiobutton(self.marco, text=texto, variable=variable, value=valor,
                              bg=self.color, font=FUENTE, anchor="w") """

    def cerrar(self):
        self.raiz.destroy()

    def iniciar(self):
        self.raiz.mainloop()