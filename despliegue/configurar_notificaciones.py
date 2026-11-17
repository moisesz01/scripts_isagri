"""Configura los avisos a Microsoft Teams cuando algo falla en Prefect.

Crea (o actualiza, se puede ejecutar varias veces):
  - el bloque "teams-isagri" (MicrosoftTeamsWebhook) con la URL del webhook
  - la automatización "isagri: ejecución fallida"  (Failed / Crashed)
  - la automatización "isagri: ejecución sin arrancar" (Late: worker parado)
Ambas se aplican a las ejecuciones con la etiqueta "isagri" (los 8 deployments).

Uso en la VM (la URL se pasa por variable de entorno, no queda en el código):
  read -rs TEAMS_WEBHOOK_URL && export TEAMS_WEBHOOK_URL     # pegar la URL + Enter
  /opt/isagri/venv/bin/python /opt/isagri/scripts_isagri/despliegue/configurar_notificaciones.py
  unset TEAMS_WEBHOOK_URL

Añadir --prueba para enviar además un mensaje de prueba al canal.
"""
import os
import sys

from prefect.automations import Automation
from prefect.blocks.notifications import MicrosoftTeamsWebhook
from prefect.events.actions import SendNotification
from prefect.events.schemas.automations import EventTrigger, Posture

BLOQUE = "teams-isagri"
ETIQUETA = "isagri"

# Plantillas Jinja: Prefect rellena flow, flow_run y deployment
CUERPO_FALLO = """❌ {{ flow_run.name }} terminó en {{ flow_run.state.name }}

Flujo: {{ flow.name }}
Error: {{ flow_run.state.message }}

Ver logs: {{ flow_run|ui_url }}"""

CUERPO_LATE = """⚠️ {{ flow_run.name }} no ha arrancado a su hora (estado Late)

Suele significar que el worker está parado. En la VM:
  systemctl status prefect-worker
  sudo systemctl restart prefect-worker

Ver ejecución: {{ flow_run|ui_url }}"""


def trigger(eventos):
    return EventTrigger(
        expect=set(eventos),
        match={"prefect.resource.id": "prefect.flow-run.*"},
        match_related={"prefect.resource.id": f"prefect.tag.{ETIQUETA}", "prefect.resource.role": "tag"},
        posture=Posture.Reactive,
        threshold=1,
    )


def guardar_automatizacion(nombre, descripcion, eventos, asunto, cuerpo, bloque_id):
    # Se borra y se vuelve a crear para que el script sea repetible
    try:
        Automation.read(name=nombre).delete()
    except ValueError:
        pass
    Automation(
        name=nombre,
        description=descripcion,
        trigger=trigger(eventos),
        actions=[SendNotification(block_document_id=bloque_id, subject=asunto, body=cuerpo)],
    ).create()
    print(f"Automatización creada: {nombre}")


def main():
    url = os.environ.get("TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        sys.exit("Falta la variable de entorno TEAMS_WEBHOOK_URL (ver instrucciones al inicio del script)")

    bloque = MicrosoftTeamsWebhook(url=url)
    bloque_id = bloque.save(BLOQUE, overwrite=True)
    print(f"Bloque guardado: {BLOQUE}")

    guardar_automatizacion(
        "isagri: ejecución fallida",
        "Aviso a Teams cuando un flujo de scripts_isagri termina en Failed o Crashed",
        ["prefect.flow-run.Failed", "prefect.flow-run.Crashed"],
        "Prefect isagri: ejecución fallida",
        CUERPO_FALLO,
        bloque_id,
    )
    guardar_automatizacion(
        "isagri: ejecución sin arrancar",
        "Aviso a Teams cuando una ejecución programada no arranca (Late): normalmente el worker está parado",
        ["prefect.flow-run.Late"],
        "Prefect isagri: ejecución sin arrancar",
        CUERPO_LATE,
        bloque_id,
    )

    if "--prueba" in sys.argv:
        bloque.notify("✅ Prueba: los avisos de Prefect (scripts_isagri) llegan a este canal.",
                      subject="Prefect isagri: prueba")
        print("Mensaje de prueba enviado")


if __name__ == "__main__":
    main()
