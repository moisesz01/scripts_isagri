"""Sincroniza Ecri (Paradox) con ecri_finanzas (SQL Server)."""
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CARPETA))

from comun.paradox_sync import TablaParadox, ejecutar  # noqa: E402

TABLAS = [
    TablaParadox(
        nombre="Ecri",
        columnas=["Exo", "Code", "Nrfisc", "Jnx", "Dtpie", "Nrpie", "Lib", "Dtfac", "Cptcp", "Mtdebe", "Mtcree", "Typdoc"],
    ),
]

if __name__ == "__main__":
    ejecutar(TABLAS, "log_ecri.txt")
