"""Sincronización incremental de tablas Paradox -> SQL Server.

En lugar de borrar la tabla entera y volver a insertarla, compara lo que hay
en Paradox con lo que ya está en SQL Server y solo escribe la diferencia:
  - filas que cambiaron  -> UPDATE (reutiliza el id de la fila vieja)
  - filas nuevas         -> INSERT
  - filas que ya no están -> DELETE
Leer es barato en Azure SQL; lo que consume DTU y log es escribir.

Cada lote de escritura se envía como un único JSON (OPENJSON), que es mucho
más rápido que fila a fila con executemany.
"""
import json
import os
import struct
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

import pyodbc
import requests
from pypxlib import Table

from comun.db import RAIZ, conectar_db

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(RAIZ, "logs")
# Carpeta única, en la raíz del proyecto, para las tablas Paradox descargadas
TMP_DIR = os.path.join(RAIZ, "tmp")
CHUNK_SIZE = 5000

ENTEROS = ("int", "bigint", "smallint", "tinyint", "bit")
DECIMALES = ("decimal", "numeric", "money", "smallmoney")
FECHAS_HORA = ("datetime", "datetime2", "smalldatetime")
TEXTOS = ("varchar", "nvarchar", "char", "nchar", "text", "ntext")


@dataclass
class TablaParadox:
    """Una tabla Paradox a sincronizar con su tabla en SQL Server."""
    nombre: str                          # nombre del archivo Paradox, sin .DB
    columnas: List[str]                  # columnas a copiar
    tabla_sql: Optional[str] = None      # por defecto: <nombre>_finanzas
    columna_fecha: Optional[str] = None  # si se indica, solo se sincroniza
    dias: Optional[int] = None           # la ventana columna_fecha >= hoy - dias

    def __post_init__(self):
        if self.tabla_sql is None:
            self.tabla_sql = self.nombre.lower() + "_finanzas"

    @property
    def variable_url(self):
        return "PARADOX_URL_" + self.nombre.upper()

    @property
    def url(self):
        """Enlace de descarga (blob de Azure con token SAS), leído del .env
        para que el token no quede en el código."""
        url = os.environ.get(self.variable_url, "").strip()
        if not url:
            raise RuntimeError(f"Falta la variable {self.variable_url} en el .env")
        return url


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
def _tipo_sql(tipo, largo, precision, escala):
    """Tipo SQL completo de una columna a partir de INFORMATION_SCHEMA."""
    if tipo in ("varchar", "nvarchar", "char", "nchar", "varbinary"):
        return f"{tipo}({'max' if largo == -1 else largo})"
    if tipo in ("decimal", "numeric"):
        return f"{tipo}({precision},{escala})"
    return tipo


def leer_columnas(cursor, tabla, nombres):
    """Devuelve, en el orden de `nombres`, las columnas de la tabla como
    (nombre_real, tipo, largo, precisión, escala). La búsqueda no distingue
    mayúsculas/minúsculas, igual que SQL Server."""
    cursor.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = ? AND TABLE_SCHEMA = OBJECT_SCHEMA_NAME(OBJECT_ID(?))",
        tabla, tabla,
    )
    por_nombre = {c[0].lower(): tuple(c) for c in cursor.fetchall()}
    if not por_nombre:
        raise RuntimeError(f"No existe la tabla {tabla} en SQL Server")
    faltan = [n for n in nombres if n.lower() not in por_nombre]
    if faltan:
        raise RuntimeError(f"{tabla} no tiene las columnas {faltan}")
    return [por_nombre[n.lower()] for n in nombres]


def columna_identidad(cursor, tabla):
    """Nombre de la columna IDENTITY de la tabla, o None si no tiene."""
    cursor.execute("SELECT name FROM sys.identity_columns WHERE object_id = OBJECT_ID(?)", tabla)
    fila = cursor.fetchone()
    return fila[0] if fila else None


# ---------------------------------------------------------------------------
# Normalización: dejar cada valor tal como queda guardado en SQL Server, para
# poder comparar lo que viene de Paradox con lo que ya está en la tabla.
# ---------------------------------------------------------------------------
def _a_fechahora(valor):
    if isinstance(valor, datetime):
        # pandas.Timestamp -> datetime normal, para que compare y haga hash igual
        return valor.to_pydatetime() if hasattr(valor, "to_pydatetime") else valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    return datetime.fromisoformat(str(valor).strip())


def _redondear_datetime(valor):
    """El tipo datetime de SQL Server guarda la hora en saltos de 1/300 s."""
    tics = round(valor.microsecond * 300 / 1_000_000)
    micro = round(tics * 1_000_000 / 300 / 1000) * 1000
    return valor.replace(microsecond=0) + timedelta(microseconds=micro)


def _redondear_minuto(valor):
    """smalldatetime guarda la hora redondeada al minuto."""
    base = valor.replace(second=0, microsecond=0)
    return base + timedelta(minutes=1) if valor.second >= 30 else base


def normalizar(valor, columna):
    """Convierte `valor` al tipo Python que corresponde a la columna SQL."""
    _, tipo, largo, _, escala = columna
    if valor is None:
        return None
    es_texto = tipo in TEXTOS
    # Paradox devuelve "" cuando no puede leer un campo: en columnas que no son
    # de texto eso se guarda como NULL
    if not es_texto and isinstance(valor, str) and not valor.strip():
        return None
    try:
        if tipo in ENTEROS:
            return int(float(valor))  # igual que CAST(float AS int): trunca
        if tipo in DECIMALES:
            return Decimal(str(valor)).quantize(Decimal(1).scaleb(-(escala or 0)), rounding=ROUND_HALF_UP)
        if tipo == "float":
            return float(valor)
        if tipo == "real":
            return struct.unpack("f", struct.pack("f", float(valor)))[0]
        if tipo == "date":
            return _a_fechahora(valor).date()
        if tipo == "datetime":
            return _redondear_datetime(_a_fechahora(valor))
        if tipo == "smalldatetime":
            return _redondear_minuto(_a_fechahora(valor))
        if tipo in FECHAS_HORA:
            return _a_fechahora(valor)
    except (ValueError, TypeError, ArithmeticError, OverflowError, struct.error):
        pass
    texto = str(valor)
    if es_texto and largo not in (None, -1):
        texto = texto[:largo]  # SQL Server lo truncaría al guardarlo
    return texto


def clave_comparacion(fila):
    """SQL Server ignora los espacios finales al comparar textos."""
    return tuple(v.rstrip() if isinstance(v, str) else v for v in fila)


def _json_default(valor):
    if isinstance(valor, datetime):
        # Formato ISO con 'T': no depende del idioma/DATEFORMAT del servidor
        return valor.isoformat(timespec="milliseconds")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)  # Decimal y otros: como texto, OPENJSON lo convierte


def _a_json(filas):
    return json.dumps(filas, default=_json_default, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Escrituras en lote
# ---------------------------------------------------------------------------
def _with_openjson(columnas, desplazamiento=0):
    return ", ".join(
        f"c{i} {_tipo_sql(*col[1:])} '$[{i + desplazamiento}]'" for i, col in enumerate(columnas)
    )


def _ejecutar_en_lotes(cursor, sentencia, filas):
    if not filas:
        return
    # Enviar el JSON como nvarchar(max); si no, pyodbc lo manda como ntext (más lento)
    cursor.setinputsizes([(pyodbc.SQL_WVARCHAR, 0, 0)])
    try:
        for i in range(0, len(filas), CHUNK_SIZE):
            cursor.execute(sentencia, _a_json(filas[i:i + CHUNK_SIZE]))
    finally:
        cursor.setinputsizes(None)


def insertar_filas(cursor, tabla, columnas, filas):
    nombres = ", ".join(f"[{c[0]}]" for c in columnas)
    select = ", ".join(f"c{i}" for i in range(len(columnas)))
    sentencia = (
        f"INSERT INTO [{tabla}] ({nombres}) SELECT {select} "
        f"FROM OPENJSON(?) WITH ({_with_openjson(columnas)})"
    )
    _ejecutar_en_lotes(cursor, sentencia, filas)


def actualizar_filas(cursor, tabla, columnas, id_col, cambios):
    """cambios: lista de (id, fila_nueva). Un UPDATE ... JOIN OPENJSON por lote."""
    sets = ", ".join(f"t.[{c[0]}] = j.c{i}" for i, c in enumerate(columnas))
    sentencia = (
        f"UPDATE t SET {sets} FROM [{tabla}] AS t "
        f"JOIN OPENJSON(?) WITH (id_fila bigint '$[0]', {_with_openjson(columnas, 1)}) AS j "
        f"ON t.[{id_col}] = j.id_fila"
    )
    _ejecutar_en_lotes(cursor, sentencia, [[id_fila, *fila] for id_fila, fila in cambios])


def borrar_por_id(cursor, tabla, id_col, ids):
    sentencia = (
        f"DELETE FROM [{tabla}] WHERE [{id_col}] IN "
        f"(SELECT CAST([value] AS bigint) FROM OPENJSON(?))"
    )
    _ejecutar_en_lotes(cursor, sentencia, ids)


def borrar_por_contenido(cursor, tabla, columnas, filas):
    """Para tablas sin columna IDENTITY: borra una fila por cada fila indicada
    buscándola por el valor de todas sus columnas."""
    por_sentencia = defaultdict(list)
    for fila in filas:
        condiciones, params = [], []
        for col, valor in zip(columnas, fila):
            if valor is None:
                condiciones.append(f"[{col[0]}] IS NULL")
            else:
                condiciones.append(f"[{col[0]}] = CAST(? AS {_tipo_sql(*col[1:])})")
                params.append(valor)
        sentencia = f"DELETE TOP (1) FROM [{tabla}] WHERE {' AND '.join(condiciones)}"
        por_sentencia[sentencia].append(params)
    cursor.fast_executemany = True
    try:
        for sentencia, params in por_sentencia.items():
            cursor.executemany(sentencia, params)
    finally:
        cursor.fast_executemany = False


# ---------------------------------------------------------------------------
# Paradox
# ---------------------------------------------------------------------------
def descargar_tabla(url, destino):
    """Descarga en streaming para no cargar el archivo entero en memoria."""
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(destino, "wb") as f:
            for bloque in response.iter_content(chunk_size=1024 * 1024):
                f.write(bloque)


# Paradox marca un entero vacío con el mínimo de 32 bits. La librería pxlib de
# Linux lo devuelve tal cual y la de Windows como None: sin esta conversión, la
# VM y el Programador de tareas de Windows se reescribían la tabla el uno al otro.
NULO_ENTERO_PARADOX = -2147483648


def _texto_paradox(texto):
    """Los .DB guardan el texto en cp1252 (la codificación de Windows), donde
    0x80 es '€', 0x8A 'Š', 0x93/0x94 las comillas “ ”... Se leen como latin-1,
    que nunca falla, y aquí se reinterpretan. Si el texto tiene un byte que no
    existe en cp1252 se deja como estaba."""
    try:
        return texto.encode("latin-1").decode("cp1252")
    except UnicodeError:
        return texto


def leer_tabla(ruta, columnas_deseadas):
    """Lee la tabla Paradox. Devuelve (columnas_encontradas, filas). Cada
    registro se lee una sola vez (antes se recorría la tabla una vez por columna)."""
    table = Table(ruta, encoding="latin-1")
    try:
        campos = set(table.fields.keys())
        keys = [c for c in columnas_deseadas if c in campos]
        faltan = [c for c in columnas_deseadas if c not in campos]
        if faltan:
            print(f"  Aviso: {os.path.basename(ruta)} no tiene las columnas {faltan}, se omiten")

        filas = []
        for i in range(len(table)):
            try:
                row = table[i]
            except Exception:
                filas.append([""] * len(keys))
                continue
            fila = []
            for col in keys:
                try:
                    valor = row[col]
                except Exception:
                    valor = ""
                if isinstance(valor, str):
                    valor = _texto_paradox(valor)
                elif valor == NULO_ENTERO_PARADOX and isinstance(valor, int):
                    valor = None
                fila.append(valor)
            filas.append(fila)
    finally:
        table.close()
    return keys, filas


# ---------------------------------------------------------------------------
# Sincronización
# ---------------------------------------------------------------------------
def sincronizar_tabla(cnxn, tabla, keys, filas_paradox):
    """Compara Paradox con la tabla SQL y escribe solo las diferencias."""
    cursor = cnxn.cursor()
    try:
        columnas = leer_columnas(cursor, tabla.tabla_sql, keys)
        id_col = columna_identidad(cursor, tabla.tabla_sql)
        nombres_sql = ", ".join(f"[{c[0]}]" for c in columnas)

        # Ventana de fechas (opcional): solo se mira lo reciente en ambos lados
        filtro, params, i_fecha, limite = "", [], None, None
        if tabla.columna_fecha:
            i_fecha = [k.lower() for k in keys].index(tabla.columna_fecha.lower())
            col_fecha = columnas[i_fecha]
            if col_fecha[1] not in FECHAS_HORA + ("date",):
                raise RuntimeError(
                    f"{tabla.tabla_sql}.{col_fecha[0]} es {col_fecha[1]}, no una fecha: no se puede filtrar por ventana"
                )
            limite_dt = datetime.combine(date.today() - timedelta(days=tabla.dias), datetime.min.time())
            limite = normalizar(limite_dt, col_fecha)
            filtro = f" WHERE [{col_fecha[0]}] >= CAST(? AS {_tipo_sql(*col_fecha[1:])})"
            params = [limite]

        # Paradox: filas normalizadas, agrupadas por contenido
        nuevas = defaultdict(list)  # clave -> filas a escribir
        total_paradox = 0
        for fila in filas_paradox:
            n = [normalizar(v, c) for v, c in zip(fila, columnas)]
            if i_fecha is not None:
                f = n[i_fecha]
                if f is None or isinstance(f, str) or f < limite:
                    continue
            total_paradox += 1
            nuevas[clave_comparacion(n)].append(n)

        # SQL Server: lo que ya está cargado (en la misma ventana)
        select_id = f"[{id_col}], " if id_col else ""
        cursor.execute(f"SELECT {select_id}{nombres_sql} FROM [{tabla.tabla_sql}]{filtro}", *params)
        actuales = defaultdict(list)  # clave -> ids (o filas, si no hay IDENTITY)
        for fila in cursor.fetchall():
            if id_col:
                ident, valores = fila[0], fila[1:]
            else:
                ident, valores = None, fila
            n = [normalizar(v, c) for v, c in zip(valores, columnas)]
            actuales[clave_comparacion(n)].append(ident if id_col else n)

        # Diferencia como multiconjunto: las filas repetidas se cuentan
        sobran, faltan = [], []
        for clave in nuevas.keys() | actuales.keys():
            a, n = actuales.get(clave, []), nuevas.get(clave, [])
            comunes = min(len(a), len(n))
            sobran.extend(a[comunes:])
            faltan.extend(n[comunes:])

        if id_col:
            # Una fila que sobra + una que falta = un UPDATE en vez de DELETE+INSERT
            cambios = list(zip(sobran, faltan))
            borrar, insertar = sobran[len(cambios):], faltan[len(cambios):]
            actualizar_filas(cursor, tabla.tabla_sql, columnas, id_col, cambios)
            borrar_por_id(cursor, tabla.tabla_sql, id_col, borrar)
        else:
            cambios, borrar, insertar = [], sobran, faltan
            borrar_por_contenido(cursor, tabla.tabla_sql, columnas, borrar)
        insertar_filas(cursor, tabla.tabla_sql, columnas, insertar)

        return {
            "filas_paradox": total_paradox,
            "actualizadas": len(cambios),
            "insertadas": len(insertar),
            "borradas": len(borrar),
        }
    finally:
        cursor.close()


# Los tres pasos de procesar() por separado: orquestacion/flujos.py los
# envuelve como tareas de Prefect para ver en el dashboard cuál falló.
def paso_descargar(tabla):
    """Descarga la tabla Paradox a TMP_DIR y devuelve la ruta local."""
    os.makedirs(TMP_DIR, exist_ok=True)
    ruta = os.path.join(TMP_DIR, tabla.nombre + ".DB")
    print(f"Descargando {tabla.nombre}.DB")
    descargar_tabla(tabla.url, ruta)
    return ruta


def paso_leer(tabla, ruta):
    print(f"Leyendo {tabla.nombre}.DB")
    return leer_tabla(ruta, tabla.columnas)


def paso_sincronizar(tabla, keys, filas):
    """Cada tabla va en su propia transacción."""
    print(f"Sincronizando {tabla.tabla_sql} ({len(filas)} filas en Paradox)")
    with conectar_db() as cnxn:
        return sincronizar_tabla(cnxn, tabla, keys, filas)


def procesar(tabla):
    """Descarga, lee y sincroniza una tabla."""
    ruta = paso_descargar(tabla)
    keys, filas = paso_leer(tabla, ruta)
    return paso_sincronizar(tabla, keys, filas)


# ---------------------------------------------------------------------------
# Log y punto de entrada
# ---------------------------------------------------------------------------
def escribir_log(nombre_archivo, mensaje):
    os.makedirs(LOG_DIR, exist_ok=True)
    # cp1252: la codificación del Bloc de notas y de las líneas antiguas del log
    with open(os.path.join(LOG_DIR, nombre_archivo), "a", encoding="cp1252", errors="replace") as archivo:
        archivo.write(mensaje + "\n")


def ejecutar(tablas, archivo_log):
    """Sincroniza todas las tablas. Si una falla, sigue con las demás y el
    proceso termina con código 1 para que el Programador de tareas lo marque."""
    inicio = time.time()
    resultados, hubo_error = [], False

    for tabla in tablas:
        t0 = time.time()
        try:
            r = procesar(tabla)
            resultados.append(
                f"{tabla.tabla_sql}: OK ({r['filas_paradox']} filas, {r['actualizadas']} actualizadas, "
                f"{r['insertadas']} insertadas, {r['borradas']} borradas, {time.time() - t0:.1f}s)"
            )
        except Exception as e:
            hubo_error = True
            resultados.append(f"{tabla.tabla_sql}: ERROR {e!r}")
        print(resultados[-1])

    duracion = time.time() - inicio
    estado = "Error" if hubo_error else "Success"
    escribir_log(
        archivo_log,
        f"Fecha de Ejecución: {datetime.now():%Y-%m-%d %H:%M:%S} | Estado Ejecución: {estado} | "
        f"Tiempo: {duracion:.2f}s | " + " | ".join(resultados),
    )
    print(f"Tiempo de ejecución: {duracion:.2f} segundos")
    sys.exit(1 if hubo_error else 0)
