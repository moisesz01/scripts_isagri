"""Sincroniza DOCEN, DELRG, Docec, ADHES y codiv (Paradox) con sus tablas
<nombre>_finanzas en SQL Server."""
import os
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(CARPETA))

from comun.paradox_sync import TablaParadox, ejecutar  # noqa: E402

TABLAS = [
    TablaParadox(
        nombre="DOCEN",
        columnas=["Acti", "TypDoc", "Socie", "Exo", "Ecri", "NrLig", "Dt", "DtLiv", "Ref", "Clien", "Nr", "Adres", "AdrLiv", "TiersLiv", "AdrFac", "TiersFac", "DtFac", "DelRg", "HtTtc", "STva", "PaysTx", "DtEsc", "RmqClient", "MtHt", "ZlAplha", "NbColis", "NrExp", "CommiVer", "NrDeb", "CommiDu", "CoeffMn", "TotalQtUni", "MtTtcRistourne", "EtatSync", "Site", "Deco", "BaseCommi", "DtDematerialisation", "LieuTaxation", "RefFournFactRectif", "ZlListe", "MtHtRistourne", "MtRDu"],
    ),
    TablaParadox(
        nombre="DELRG",
        columnas=["Code", "Lib", "TypRg", "Nbj1", "Nbj2", "TxEch1", "TxEch2", "TxEch3", "DateBaseEch1", "AvecJourFixeOblig"],
    ),
    TablaParadox(
        nombre="Docec",
        columnas=["Docen", "TypDoc", "Exo", "Ecri", "NrLig", "Clien", "MtTtc", "TxTtc", "Dt"],
    ),
    TablaParadox(
        nombre="ADHES",
        columnas=["Tiers", "DelRg"],
    ),
    TablaParadox(
        nombre="codiv",
        columnas=["Objet", "Code", "CodTrad", "Lib", "Info"],
    ),
]

if __name__ == "__main__":
    ejecutar(TABLAS, "log_docen.txt")
