"""Conexión a SQL Server compartida por todos los scripts.

Las credenciales se leen del .env de la raíz del proyecto (ver .env_example).
"""
import os
from contextlib import contextmanager

import pyodbc
from dotenv import load_dotenv

# Raíz del proyecto (carpeta que contiene "comun"). El Programador de tareas
# ejecuta desde otra carpeta, así que el .env se busca siempre aquí.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(RAIZ, ".env")
load_dotenv(ENV_PATH)

DRIVER = os.environ.get("SqlDriver", "ODBC Driver 17 for SQL Server")

SQL_CONFIG = {
    "server": os.environ.get("Server", ""),
    "database": os.environ.get("Database", ""),
    "username": os.environ.get("UsernameDB", ""),
    "password": os.environ.get("Password", ""),
}


def cadena_conexion(config=SQL_CONFIG):
    faltantes = [k for k, v in config.items() if not v]
    if faltantes:
        raise RuntimeError(f"Faltan variables en {ENV_PATH}: {faltantes}")
    return (
        f"DRIVER={{{DRIVER}}};"
        f"SERVER={config['server']};DATABASE={config['database']};"
        f"UID={config['username']};PWD={config['password']}"
    )


@contextmanager
def conectar_db(config=SQL_CONFIG):
    """Abre una sesión en SQL Server. Commit al salir sin errores, rollback si
    hay una excepción, y siempre cierra la conexión."""
    cadena = cadena_conexion(config)
    try:
        cnxn = pyodbc.connect(cadena, autocommit=False)
    except pyodbc.Error as e:
        raise RuntimeError(
            f"No se pudo conectar a SERVER={config['server']!r} DATABASE={config['database']!r}: {e}"
        ) from e
    try:
        yield cnxn
        cnxn.commit()
    except Exception:
        cnxn.rollback()
        raise
    finally:
        cnxn.close()
