"""Sincroniza mvts (Paradox) con mvts_finanzas (SQL Server), solo los
movimientos de los últimos 548 días (Dtpie); lo anterior no se toca."""
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CARPETA))

from comun.paradox_sync import TablaParadox, ejecutar  # noqa: E402

TABLAS = [
    TablaParadox(
        nombre="mvts",
        columnas=["Exo", "Ecri", "Nrlig", "Dtpie", "Jnx", "Nrpie", "Cpte", "Lib", "Dtdecl", "Dtval", "Mtdebe", "Mtcree", "Nrepart", "Tva", "Lettr"],
        columna_fecha="Dtpie",
        dias=548,
    ),
]

if __name__ == "__main__":
    ejecutar(TABLAS, "log_mvts.txt")
