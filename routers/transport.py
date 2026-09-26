"""routers/transport.py
Endpoints REST et Webhooks pour le système de transport ferroviaire de J.A.R.V.I.S.
Gère les recherches d'itinéraires, la surveillance proactive et la réception d'alertes n8n.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel
import json
import logging

from google.genai import types
from services.transport_service import transport_service
from services.supervision_service import supervision_service
from core.shared_state import active_task_controller, broadcast_supervision

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/train", tags=["transport"])


class TrainSearchRequest(BaseModel):
    origine: str
    destination: str
    date_depart: str
    heure_souhaitee: Optional[str] = None
    pays: str = "auto"
    reserver_automatiquement: bool = False


class TrainMonitorRequest(BaseModel):
    numero_train: str
    date: str
    operateur: str = "sncf"


class TrainAlertPayload(BaseModel):
    numero_train: str
    date: str
    operateur: str
    delay_minutes: int = 0
    is_cancelled: bool = False
    track: Optional[str] = None
    alert_message: str
    timestamp: Optional[str] = None


class TrainReserveLocalRequest(BaseModel):
    operateur: str
    url_trajet: Optional[str] = None
    urls_trajets: Optional[list] = None
    description_trajet: Optional[str] = None


@router.post("/search")
async def search_train_endpoint(req: TrainSearchRequest):
    """Recherche des trains en France ou en Suède avec deep links et tarifs indicatifs."""
    return await transport_service.rechercher_itineraires(
        origine=req.origine,
        destination=req.destination,
        date_depart=req.date_depart,
        heure_souhaitee=req.heure_souhaitee,
        pays=req.pays,
        reserver_automatiquement=req.reserver_automatiquement
    )


@router.post("/monitor")
async def monitor_train_endpoint(req: TrainMonitorRequest):
    """Active la surveillance proactive via n8n."""
    return await transport_service.surveiller_train(
        numero_train=req.numero_train,
        date=req.date,
        operateur=req.operateur
    )


@router.post("/alert")
async def receive_train_alert(alert: TrainAlertPayload):
    """Webhook appelé par n8n dès qu'une perturbation ou un retard > 5 min est détecté sur un train surveillé."""
    logger.warning(
        "[TrainAlert] Perturbation détectée sur le train %s (%s) : %s",
        alert.numero_train, alert.operateur, alert.alert_message
    )

    # 1. Enregistrement dans la supervision
    supervision_service.start_action(
        f"train_alert_{alert.numero_train}",
        f"Alerte Train {alert.numero_train}",
        "surveiller_train",
        alert.alert_message,
        "n8n / Trafikverket / SNCF",
        api_type="free",
        api_label="Monitoring Service",
        cost_est="0.00 $"
    )
    supervision_service.complete_action(
        f"train_alert_{alert.numero_train}",
        status="warning" if not alert.is_cancelled else "error",
        summary=alert.alert_message
    )
    await broadcast_supervision()

    # 2. Diffusion WebSocket vers le HUD mobile PWA
    current_ws = active_task_controller.get("websocket")
    if current_ws:
        try:
            await current_ws.send_text(json.dumps({
                "type": "train_delay_alert",
                "numero_train": alert.numero_train,
                "delay_minutes": alert.delay_minutes,
                "is_cancelled": alert.is_cancelled,
                "track": alert.track,
                "message": alert.alert_message,
                "date": alert.date,
                "operateur": alert.operateur
            }))
        except Exception as e:
            logger.error("[TrainAlert] Erreur envoi WebSocket : %s", e)

    # 3. Notification vocale en direct dans la session Gemini Live (Aoede prévient Pierre oralement)
    current_sess = active_task_controller.get("live_session")
    if current_sess:
        status_txt = "est ANNULÉ" if alert.is_cancelled else f"a un retard de {alert.delay_minutes} minutes"
        track_info = f" Voie annoncée : {alert.track}." if alert.track else ""
        speech_text = (
            f"[ALERTE PERTURBATION FERROVIAIRE EN DIRECT - À ANNONCER IMMÉDIATEMENT À PIERRE AVEC TA VOIX AOEDE] "
            f"Pierre, information importante concernant ton train {alert.numero_train} du {alert.date} : "
            f"il {status_txt}.{track_info} "
            f"Je t'ai affiché l'alerte sur ton écran."
        )
        try:
            await current_sess.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=speech_text)]),
                turn_complete=True
            )
        except Exception as e:
            logger.error("[TrainAlert] Erreur injection session Live : %s", e)

    return {
        "status": "alert_received",
        "numero_train": alert.numero_train,
        "processed": True
    }


@router.post("/reserve-local")
async def reserve_train_local_endpoint(req: TrainReserveLocalRequest):
    """Déclenche la préparation de réservation sur le PC physique de Pierre via jarvis_local_agent."""
    return await transport_service.reserver_billet_train_local(
        operateur=req.operateur,
        url_trajet=req.url_trajet,
        urls_trajets=req.urls_trajets,
        description_trajet=req.description_trajet
    )
