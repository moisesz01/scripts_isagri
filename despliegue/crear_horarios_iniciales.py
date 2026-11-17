"""Crea los horarios iniciales de los 8 deployments en una instalación nueva.

Solo se ejecuta UNA VEZ, después del primer "prefect deploy --all". A partir
de ahí los horarios se cambian desde el dashboard (Deployments -> el
deployment -> Schedules -> Edit), y volver a desplegar no los toca.

Es seguro ejecutarlo de nuevo: un deployment que ya tiene algún horario se deja
como está (no se duplica ni se sobrescribe lo cambiado en el dashboard).

Uso en la VM:
  /opt/isagri/venv/bin/python /opt/isagri/scripts_isagri/despliegue/crear_horarios_iniciales.py
"""
from prefect.client.orchestration import get_client
from prefect.client.schemas.schedules import CronSchedule

ZONA_HORARIA = "Europe/Madrid"

# deployment -> cron ("minuto hora * * *"), hora de Madrid, todos los días
HORARIOS = {
    "paradox-actirep/actirep": "0 2 * * *",                                       # 02:00
    "paradox-docen/docen": "20 2 * * *",                                          # 02:20
    "paradox-ecri/ecri": "40 2 * * *",                                            # 02:40
    "paradox-mvts/mvts": "0 3 * * *",                                             # 03:00
    "paradox-balan-balme/balan-balme": "20 3 * * *",                              # 03:20
    "compras-detalle-pedidos/detalle-pedidos": "0 4 * * *",                       # 04:00
    "compras-detalle-albaranes/detalle-albaranes": "20 4 * * *",                  # 04:20
    "compras-asociacion-factura-albaran/asociacion-factura-albaran": "40 4 * * *",  # 04:40
}


def main():
    with get_client(sync_client=True) as cliente:
        for nombre, cron in HORARIOS.items():
            deployment = cliente.read_deployment_by_name(nombre)
            existentes = cliente.read_deployment_schedules(deployment.id)
            if existentes:
                actuales = ", ".join(getattr(s.schedule, "cron", str(s.schedule)) for s in existentes)
                print(f"{nombre}: ya tiene horario ({actuales}), no se toca")
                continue
            cliente.create_deployment_schedules(
                deployment.id, [(CronSchedule(cron=cron, timezone=ZONA_HORARIA), True)])
            print(f"{nombre}: horario creado ({cron}, {ZONA_HORARIA})")


if __name__ == "__main__":
    main()
