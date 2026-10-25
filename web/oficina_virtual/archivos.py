"""
Clase para manejar archivos secuenciales (CSV / texto delimitado).

USO:
    from archivos import ArchivoSecuencial
    clientes = ArchivoSecuencial("P:/Proyectos/datos/clientes.csv",
                                 campos=["id", "nombre", "telefono"])
    clientes.escribir({"id": "1", "nombre": "Ana", "telefono": "305-555-1234"})
    clientes.leer()                                   # todos los registros
    clientes.leer({"nombre": "Ana"})                  # filtrados
    clientes.actualizar({"telefono": "305-000-0000"}, {"id": "1"})
    clientes.borrar({"id": "1"})
"""
import csv
from pathlib import Path


class ArchivoSecuencial:
    def __init__(self, ruta, campos, separador=","):
        self.ruta = Path(ruta)
        self.campos = campos
        self.separador = separador
        if not self.ruta.exists():
            self._grabar_todo([])

    # ---- métodos internos ----
    def _cumple(self, registro, condiciones):
        return all(registro.get(c) == str(v) for c, v in (condiciones or {}).items())

    def _grabar_todo(self, registros):
        with self.ruta.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.campos, delimiter=self.separador)
            w.writeheader()
            w.writerows(registros)

    # ---- métodos públicos ----
    def leer(self, condiciones=None):
        with self.ruta.open(newline="", encoding="utf-8") as f:
            return [r for r in csv.DictReader(f, delimiter=self.separador)
                    if self._cumple(r, condiciones)]

    def escribir(self, datos):
        with self.ruta.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.campos, delimiter=self.separador).writerow(datos)

    def actualizar(self, datos, condiciones):
        registros = self.leer()
        cambiados = 0
        for r in registros:
            if self._cumple(r, condiciones):
                r.update({k: str(v) for k, v in datos.items()})
                cambiados += 1
        self._grabar_todo(registros)
        return cambiados

    def borrar(self, condiciones):
        registros = self.leer()
        quedan = [r for r in registros if not self._cumple(r, condiciones)]
        self._grabar_todo(quedan)
        return len(registros) - len(quedan)