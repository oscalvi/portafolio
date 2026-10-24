import json
import tkinter as tk
import urllib.request
from datetime import date
from tkinter import messagebox

from ventanas import Ventana

CIUDADES = {
    "Miami": (25.76, -80.19),
    "New York": (40.71, -74.01),
    "Chicago": (41.88, -87.63),
    "Los Angeles": (34.05, -118.24),
    "Denver": (39.74, -104.99),
}

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def icono(codigo):
    """Convierte el código del clima en un icono y una descripción."""
    if codigo == 0:
        return "☀️", "Soleado"
    if codigo in (1, 2):
        return "⛅", "Parcial"
    if codigo == 3:
        return "☁️", "Nublado"
    if codigo in (45, 48):
        return "🌫️", "Niebla"
    if 71 <= codigo <= 77 or codigo in (85, 86):
        return "❄️", "Nieve"
    if codigo >= 95:
        return "⛈️", "Tormenta"
    return "🌧️", "Lluvia"


def pronostico(lat, lon):
    """Pide a Open-Meteo el pronóstico de 5 días."""
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min"
           "&temperature_unit=fahrenheit&timezone=auto&forecast_days=5")
    with urllib.request.urlopen(url, timeout=10) as respuesta:
        return json.load(respuesta)["daily"]


""" def abrir_clima(padre=None):
    v = Ventana("El tiempo", 400, 400, padre, color="#FFF4D6")

    v.label("Escoge una ciudad", fuente=("Arial", 12, "bold")).pack(pady=5)

    ciudad = tk.StringVar(value="Miami")
    for nombre in CIUDADES:
        v.opcion(nombre, ciudad, nombre).pack(fill="x", padx=40)

    resultados = tk.Frame(v.marco, bg=v.color)

    def buscar():
        for elemento in resultados.winfo_children():
            elemento.destroy()
        try:
            datos = pronostico(*CIUDADES[ciudad.get()])
        except Exception:
            messagebox.showerror("Error", "No se pudo obtener el tiempo. Revisa tu internet.")
            return

        for i in range(5):
            dia = DIAS[date.fromisoformat(datos["time"][i]).weekday()]
            simbolo, descripcion = icono(datos["weather_code"][i])
            maxima = round(datos["temperature_2m_max"][i])
            minima = round(datos["temperature_2m_min"][i])
            v.label(f"{dia:<10} {simbolo}  {descripcion:<9} {maxima}° / {minima}°F",
                    padre=resultados, fuente=("Segoe UI Emoji", 10)).pack(anchor="w")

    v.boton("Ver tiempo", buscar).pack(pady=8)
    resultados.pack()
    return v
 """
def abrir_clima(padre=None):
    v = Ventana("El tiempo", 400, 400, padre, color="#FFF4D6")

    v.label("Escoge una ciudad", fuente=("Arial", 12, "bold")).pack(pady=5)

    ciudad = tk.StringVar(value="Miami")
    resultados = tk.Frame(v.marco, bg=v.color)

    def buscar():
        for elemento in resultados.winfo_children():
            elemento.destroy()
        try:
            datos = pronostico(*CIUDADES[ciudad.get()])
        except Exception:
            messagebox.showerror("Error", "No se pudo obtener el tiempo. Revisa tu internet.")
            return

        for i in range(5):
            dia = DIAS[date.fromisoformat(datos["time"][i]).weekday()]
            simbolo, descripcion = icono(datos["weather_code"][i])
            maxima = round(datos["temperature_2m_max"][i])
            minima = round(datos["temperature_2m_min"][i])
            v.label(f"{dia:<10} {simbolo}  {descripcion:<9} {maxima}° / {minima}°F",
                    padre=resultados, fuente=("Segoe UI Emoji", 10)).pack(anchor="w")

    for nombre in CIUDADES:
        v.opcion(nombre, ciudad, nombre, buscar).pack(fill="x", padx=40)

    resultados.pack(pady=10)
    buscar()          # muestra Miami al abrir la pantalla
    return v


if __name__ == "__main__":
    abrir_clima().iniciar()