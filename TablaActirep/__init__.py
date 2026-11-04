"""Sincroniza Actirep (Paradox) con actirep_finanzas (SQL Server)."""
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CARPETA))

from comun.paradox_sync import TablaParadox, ejecutar  # noqa: E402

TABLAS = [
    TablaParadox(
        nombre="Actirep",
        columnas=["Exo", "Code", "Acti", "Deco", "Pourc", "Nrlig"],
    ),
]

if __name__ == "__main__":
    ejecutar(TABLAS, "log_actirep.txt")
