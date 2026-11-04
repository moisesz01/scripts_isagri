"""Sincroniza BALAN y BALME (Paradox) con balan_finanzas y balme_finanzas."""
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CARPETA))

from comun.paradox_sync import TablaParadox, ejecutar  # noqa: E402

TABLAS = [
    TablaParadox(
        nombre="BALAN",
        columnas=["Exo", "Cpte", "Typbal", "Mtdeb", "Mtdebe", "Mtcre", "Mtcree", "Qt1", "Qt1deb", "Qt1cre", "Qt2", "Qt2deb", "Qt2cre", "Nbmvt", "Rmq"],
    ),
    TablaParadox(
        nombre="BALME",
        columnas=["Exo", "Cpte", "Typbal", "Mois", "Lib", "Mtdeb", "Mtdebe", "Mtcre", "Mtcree", "Qt1", "Qt1deb", "Qt1Cre", "Qt2", "Qt2deb", "Qt2Cre"],
    ),
]

if __name__ == "__main__":
    ejecutar(TABLAS, "log_balan_balme.txt")
