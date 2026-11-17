"""Flujos de Prefect para scripts_isagri.

Sustituyen a los .bat del Programador de tareas de Windows: un flujo por cada
.bat, independiente y con su propio horario (ver prefect.yaml). Reutilizan la
lógica existente (comun/paradox_sync.py y Compras/*.py) y la envuelven en
@flow / @task para que cada ejecución, sus logs y sus fallos se vean en el
dashboard de Prefect (http://<IP-VM>:4200).

  Flujo                              Antes era
  ---------------------------------  ------------------------------
  paradox-actirep                    TablaActirep.bat
  paradox-docen                      TablaDocen.bat
  paradox-ecri                       TablaEcri.bat
  paradox-mvts                       TablaMvts.bat
  paradox-balan-balme                TablasBalanBalme.bat
  compras-detalle-pedidos            detalle_pedidos_compras.bat
  compras-detalle-albaranes          detalle_albaranes_compras.bat
  compras-asociacion-factura-albaran asociacion_factura_albaran.bat

Ejecución manual de todos, uno tras otro (desde la raíz del proyecto, con el
venv activado):
  python orquestacion/flujos.py
"""
import importlib
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from prefect import flow, get_run_logger, task  # noqa: E402
from prefect.artifacts import create_table_artifact  # noqa: E402
from prefect.cache_policies import NO_CACHE  # noqa: E402
from prefect.runtime import deployment as deployment_actual  # noqa: E402
from prefect.runtime import flow_run as run_actual  # noqa: E402
from prefect.utilities.annotations import quote  # noqa: E402

from comun import paradox_sync  # noqa: E402

ZONA_HORARIA = ZoneInfo("Europe/Madrid")

# grupo -> paquete con la lista TABLAS (el mismo que usaba cada .bat)
GRUPOS_PARADOX = {
    "actirep": "TablaActirep",
    "docen": "TablaDocen",
    "ecri": "TablaEcri",
    "mvts": "TablaMvts",
    "balan_balme": "TablasBalanBalme",
}

# paso -> (módulo, función)
PASOS_COMPRAS = {
    "detalle_pedidos": ("Compras.detalle_pedidos_compras", "migrar_datos"),
    "detalle_albaranes": ("Compras.detalle_albaranes_compras", "migrar_albaranes_compras"),
    "asociacion_factura_albaran": ("Compras.asociacion_factura_albaran_compras", "actualizar_facturas_en_albaranes"),
    # Sin .bat en Windows ni flujo propio: se pueden lanzar a mano con
    # ejecutar_paso_compras("consumo_pedidos") desde Python
    "consumo_pedidos": ("Compras.consumo_pedidos_compras", "migrar_datos_ak"),
    "consumo_albaranes": ("Compras.consumo_albaranes_compras", "migrar_datos_al"),
}


# ---------------------------------------------------------------------------
# Nombres de las ejecuciones: <flujo>-<fecha>, p. ej. paradox-mvts-2026-11-17
# ---------------------------------------------------------------------------
def _fecha_run():
    """Fecha (hora de Madrid) para la que estaba programada la ejecución, así
    un run que arranca tarde conserva el día que le corresponde."""
    inicio = run_actual.scheduled_start_time or datetime.now(timezone.utc)
    return f"{inicio.astimezone(ZONA_HORARIA):%Y-%m-%d}"


def _nombre_run():
    return f"{run_actual.flow_name}-{_fecha_run()}"


def renombrar_programadas(deployment_id, prefijo):
    """Pone nombre con fecha a las ejecuciones que el planificador ya dejó
    creadas en cola: llegan con nombre aleatorio (p. ej. bright-tarantula) y
    así se verían en la columna "Next Run". Devuelve cuántas cambió."""
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.filters import (
        DeploymentFilter, DeploymentFilterId, FlowRunFilter, FlowRunFilterStateType)
    from prefect.client.schemas.objects import StateType

    cambiadas = 0
    with get_client(sync_client=True) as cliente:
        programadas = cliente.read_flow_runs(
            limit=200,
            deployment_filter=DeploymentFilter(id=DeploymentFilterId(any_=[deployment_id])),
            flow_run_filter=FlowRunFilter(state=dict(type=FlowRunFilterStateType(any_=[StateType.SCHEDULED]))),
        )
        for r in programadas:
            nombre = f"{prefijo}-{r.expected_start_time.astimezone(ZONA_HORARIA):%Y-%m-%d}"
            if r.name != nombre:
                cliente.update_flow_run(r.id, name=nombre)
                cambiadas += 1
    return cambiadas


def _renombrar_cola():
    """Al terminar cada flujo (aunque haya fallado) se renombra la cola de su
    deployment. Va al final porque el planificador repone la cola poco después
    de que arranque la ejecución. Un error aquí nunca afecta al resultado."""
    try:
        deployment_id = deployment_actual.id
        if not deployment_id:
            return  # ejecución manual sin deployment
        n = renombrar_programadas(deployment_id, run_actual.flow_name)
        get_run_logger().info(f"Ejecuciones programadas renombradas: {n}")
    except Exception as e:
        get_run_logger().warning(f"No se pudieron renombrar las ejecuciones programadas: {e!r}")


# ---------------------------------------------------------------------------
# Tareas Paradox. NO_CACHE: los argumentos son listas de miles de filas y no
# tiene sentido calcular su hash ni reutilizar resultados entre ejecuciones.
# ---------------------------------------------------------------------------
@task(
    name="descargar-paradox",
    task_run_name="descargar-{tabla.nombre}",
    retries=3,
    retry_delay_seconds=60,  # cortes de red / Azure Blob transitorios
    cache_policy=NO_CACHE,
    log_prints=True,
)
def descargar_paradox(tabla):
    return paradox_sync.paso_descargar(tabla)


@task(name="leer-paradox", task_run_name="leer-{tabla.nombre}", cache_policy=NO_CACHE, log_prints=True)
def leer_paradox(tabla, ruta):
    keys, filas = paradox_sync.paso_leer(tabla, ruta)
    if not filas:
        # Una tabla vacía borraría todo el contenido de SQL Server en la sincronización
        raise RuntimeError(f"{tabla.nombre}.DB no tiene filas: se cancela para no vaciar {tabla.tabla_sql}")
    return keys, filas


@task(
    name="sincronizar-sql",
    task_run_name="sincronizar-{tabla.tabla_sql}",
    retries=1,  # cada tabla es una transacción: si falla se hace rollback y es seguro repetir
    retry_delay_seconds=120,
    cache_policy=NO_CACHE,
    log_prints=True,
)
def sincronizar_sql(tabla, keys, filas):
    return paradox_sync.paso_sincronizar(tabla, keys, filas)


def sincronizar_grupo(grupo):
    """Sincroniza las tablas de un grupo. Si una tabla falla sigue con las
    demás y al final el flujo queda en estado Failed con el detalle."""
    logger = get_run_logger()
    filas_resumen, fallos = [], []
    try:
        for tabla in importlib.import_module(GRUPOS_PARADOX[grupo]).TABLAS:
            t0 = time.time()
            try:
                _ = tabla.url  # falta de configuración en el .env: falla ya, sin reintentos
                ruta = descargar_paradox(tabla)
                keys, filas = leer_paradox(tabla, ruta)
                # quote(): Prefect no recorre las filas una a una buscando
                # dependencias entre tareas. Sin esto, en mvts (400 000 filas)
                # el traspaso tardaba ~35 s y subía la RAM unos 600 MB.
                r = sincronizar_sql(tabla, quote(keys), quote(filas))
                filas_resumen.append({"tabla": tabla.tabla_sql, "estado": "OK", **r,
                                      "segundos": round(time.time() - t0, 1)})
                logger.info(f"{tabla.tabla_sql}: {r}")
            except Exception as e:
                fallos.append(f"{tabla.tabla_sql}: {e!r}")
                filas_resumen.append({"tabla": tabla.tabla_sql, "estado": "ERROR", "detalle": repr(e)[:300],
                                      "segundos": round(time.time() - t0, 1)})
                logger.error(f"{tabla.tabla_sql} falló: {e!r}")

        # Tabla de resultados visible en la pestaña "Artifacts" del run
        create_table_artifact(key=f"paradox-{grupo.replace('_', '-')}", table=filas_resumen,
                              description=f"Resultado de la sincronización {grupo}")
        if fallos:
            raise RuntimeError(f"{len(fallos)} tabla(s) con error en {grupo}: " + " | ".join(fallos))
        return filas_resumen
    finally:
        _renombrar_cola()


# ---------------------------------------------------------------------------
# Compras: cada script es una transacción completa, así que es una tarea.
# Los scripts propagan la excepción tras el rollback, y Prefect la registra.
# ---------------------------------------------------------------------------
@task(name="compras-paso", task_run_name="{paso}", cache_policy=NO_CACHE, log_prints=True)
def ejecutar_paso_compras(paso: str):
    modulo, funcion = PASOS_COMPRAS[paso]
    getattr(importlib.import_module(modulo), funcion)()


def ejecutar_compras(paso):
    try:
        ejecutar_paso_compras(paso)
    finally:
        _renombrar_cola()


# ---------------------------------------------------------------------------
# Un flujo por cada .bat. Su horario se define en prefect.yaml.
# ---------------------------------------------------------------------------
OPCIONES = dict(flow_run_name=_nombre_run, log_prints=True, timeout_seconds=2 * 3600)


@flow(name="paradox-actirep", description="Actirep -> actirep_finanzas", **OPCIONES)
def paradox_actirep():
    return sincronizar_grupo("actirep")


@flow(name="paradox-docen", description="DOCEN, DELRG, Docec, ADHES y codiv -> *_finanzas", **OPCIONES)
def paradox_docen():
    return sincronizar_grupo("docen")


@flow(name="paradox-ecri", description="Ecri -> ecri_finanzas", **OPCIONES)
def paradox_ecri():
    return sincronizar_grupo("ecri")


@flow(name="paradox-mvts", description="mvts -> mvts_finanzas (últimos 548 días)", **OPCIONES)
def paradox_mvts():
    return sincronizar_grupo("mvts")


@flow(name="paradox-balan-balme", description="BALAN y BALME -> balan_finanzas y balme_finanzas", **OPCIONES)
def paradox_balan_balme():
    return sincronizar_grupo("balan_balme")


@flow(name="compras-detalle-pedidos", description="docli_t (pedidos) -> detalle_pedido_compras", **OPCIONES)
def compras_detalle_pedidos():
    ejecutar_compras("detalle_pedidos")


@flow(name="compras-detalle-albaranes",
      description="docli_t (albaranes) -> detalle_albaran_compras; enlaza pedidos con albaranes", **OPCIONES)
def compras_detalle_albaranes():
    ejecutar_compras("detalle_albaranes")


@flow(name="compras-asociacion-factura-albaran",
      description="Enlaza las facturas de los últimos 90 días con sus albaranes", **OPCIONES)
def compras_asociacion_factura_albaran():
    ejecutar_compras("asociacion_factura_albaran")


TODOS = [paradox_actirep, paradox_docen, paradox_ecri, paradox_mvts, paradox_balan_balme,
         compras_detalle_pedidos, compras_detalle_albaranes, compras_asociacion_factura_albaran]

if __name__ == "__main__":
    # Ejecución manual de todos, en el mismo orden que los horarios. Si uno
    # falla se sigue con el siguiente (cada uno es independiente).
    for flujo in TODOS:
        flujo(return_state=True)
