"""routers/settings.py
Endpoints de configuration dynamique : modèle vocal, clé payante, consentement.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.genai import types

import auth
import config
from services.supervision_service import supervision_service
from core.shared_state import (
    active_task_controller,
    broadcast_supervision,
    broadcast_paid_key_status,
    safe_send_live_client_content,
)

router = APIRouter()


class LiveModelRequest(BaseModel):
    model: str


class PaidKeyAuthRequest(BaseModel):
    authorized: bool


class PaidConsentRequest(BaseModel):
    action: str
    approved: bool


@router.get("/api/version")
async def get_version():
    """Retourne la version applicative centrale de J.A.R.V.I.S. Core."""
    return {
        "version": getattr(config, "APP_VERSION", "5.94.0"),
        "app": "J.A.R.V.I.S. - Stark Industries",
    }


@router.get("/api/live-model")
async def get_live_model():
    """Retourne le modèle Gemini Live configuré pour la voix de Jarvis."""
    return {
        "current_model": config.GEMINI_LIVE_MODEL,
        "available_models": ["gemini-3.8-live", "gemini-3.8-live-extended-thinking"]
    }


@router.post("/api/live-model")
@router.post("/api/supervision/set-model")
async def set_live_model(req: LiveModelRequest):
    """Bascule le modèle vocal Gemini Live entre gemini-3.8-live et gemini-3.8-live-extended-thinking (tous deux sur clé FREE par défaut)."""
    from core.shared_state import is_speech_idle, ModelSwitchRequested

    if req.model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
        config.GEMINI_LIVE_MODEL = req.model
        is_paid = bool(supervision_service._free_quota_exhausted or not config.GEMINI_API_KEY_FREE)
        supervision_service.update_voice_state(supervision_service._voice_state.get("status", "idle"), model=req.model, is_paid=is_paid)
        await broadcast_supervision()

        # Si une session live est active, appliquer ou différer selon SpeechState
        ws = active_task_controller.get("websocket")
        if ws:
            if not is_speech_idle():
                active_task_controller["pending_model_switch"] = req.model
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Bascule vers {req.model} différée jusqu'à la fin de la parole...",
                    "voice": False,
                }))
            else:
                active_task_controller["pending_model_switch"] = req.model
                # Signal au canal vocal de traiter la bascule
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Bascule immédiate vers {req.model}...",
                    "voice": False,
                }))

        return {"status": "ok", "current_model": config.GEMINI_LIVE_MODEL}
    return JSONResponse(
        status_code=400,
        content={"error": "Modèle non supporté. Choix: gemini-3.8-live ou gemini-3.8-live-extended-thinking"}
    )


@router.post("/api/settings/paid-key")
async def post_paid_key_auth(req: PaidKeyAuthRequest, request: Request):
    """Met à jour l'encoche d'autorisation de la clé payante (cochée ou décochée)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    config.set_paid_key_authorized(req.authorized)
    active_task_controller["paid_consent_given"] = req.authorized
    await broadcast_paid_key_status(req.authorized)

    ws = active_task_controller.get("websocket")
    if ws:
        try:
            status_text = "activée et autorisée" if req.authorized else "verrouillée (accès physique coupé)"
            await ws.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Clé payante {status_text}.",
                "voice": False
            }))
            if active_task_controller.get("live_session"):
                try:
                    await safe_send_live_client_content(
                        active_task_controller["live_session"],
                        text_content=(
                            f"[INFO SYSTÈME EN DIRECT] Pierre vient de {'COCHER' if req.authorized else 'DÉCOCHER'} "
                            f"l'encoche d'autorisation de la clé payante dans l'application. "
                            f"La clé payante est désormais {'AUTORISÉE' if req.authorized else 'VERROUILLÉE ET INTERDITE PHYSIQUEMENT'}."
                        ),
                        priority=3,
                        role="user",
                        turn_complete=True
                    )
                except Exception:
                    pass
        except Exception:
            pass

    await broadcast_supervision()
    return {
        "status": "ok",
        "authorized": config.is_paid_key_authorized(),
        "paid_key_authorized": config.is_paid_key_authorized()
    }


@router.get("/api/settings/paid-key")
async def get_paid_key_auth(request: Request):
    return {
        "status": "ok",
        "authorized": config.is_paid_key_authorized(),
        "paid_key_authorized": config.is_paid_key_authorized(),
        "has_paid_key": config.HAS_PAID_API_KEY
    }


@router.post("/api/paid-consent")
async def post_paid_consent(req: PaidConsentRequest, request: Request):
    """Permet à Pierre de valider ou refuser l'utilisation de la clé payante via REST ou interface."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    active_task_controller["paid_consent_given"] = req.approved
    if req.approved:
        config.set_paid_key_authorized(True)
        await broadcast_paid_key_status(True)
        await broadcast_supervision()

    if req.action == "live_fallback":
        active_task_controller["paid_live_approved"] = req.approved
    if active_task_controller.get("paid_consent_event"):
        active_task_controller["paid_consent_event"].set()

    ws = active_task_controller.get("websocket")
    if ws:
        try:
            status_text = "accordée" if req.approved else "refusée"
            await ws.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Autorisation d'accès payant {status_text}.",
                "voice": False
            }))
            if req.approved:
                await ws.send_text(json.dumps({"type": "hide_paid_consent"}))
        except Exception:
            pass

    return {"status": "ok", "action": req.action, "approved": req.approved}


@router.get("/api/tunnel-info")
async def get_tunnel_info():
    """Retourne l'URL Cloudflare active et les informations d'accès mobile."""
    import os
    url_file = os.path.join(config.BASE_DIR, "tunnel_url.txt")
    tunnel_url = None
    if os.path.exists(url_file):
        try:
            with open(url_file, "r", encoding="utf-8") as f:
                tunnel_url = f.read().strip()
        except Exception:
            pass
    return {
        "tunnel_url": tunnel_url,
        "status": "ready" if tunnel_url else "waiting"
    }
