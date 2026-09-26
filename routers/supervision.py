"""routers/supervision.py
Endpoints de supervision temps réel, gestion des tâches et directives.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import auth
from google_antigravity import is_stop_directive
from services.supervision_service import supervision_service
from core.shared_state import (
    active_task_controller,
    broadcast_supervision,
    stop_active_task,
)

router = APIRouter()


class DirectiveRequest(BaseModel):
    directive: str


@router.get("/api/supervision/overview")
async def get_supervision_overview(request: Request):
    """Retourne la vue d'ensemble complète : modèle vocal, clé API, actions actives, outils et fenêtres ouvertes."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return supervision_service.get_full_overview()


@router.get("/api/supervision/windows")
async def get_supervision_windows(request: Request):
    """Retourne la liste rafraîchie des fenêtres ouvertes."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return {"windows": supervision_service.get_open_windows()}


@router.post("/api/task/directive")
async def post_task_directive(req: DirectiveRequest, request: Request):
    """Permet à l'utilisateur d'adapter ou guider en direct la tâche de code en cours de développement."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    directive = req.directive.strip()
    if not directive:
        return JSONResponse(content={"status": "error", "message": "Directive vide"}, status_code=400)

    if is_stop_directive(directive):
        await stop_active_task(source="directive_stop", reason=directive)
        return {"status": "cancelled", "message": "Développement immédiatement interrompu."}

    if active_task_controller["info"]["running"]:
        await active_task_controller["queue"].put(directive)
        active_task_controller.setdefault("directives", []).append(directive)
        ws = active_task_controller.get("websocket")
        if ws:
            try:
                import json
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Consigne reçue : {directive}. Adaptation en cours.",
                    "voice": False
                }))
            except Exception:
                pass
        return {"status": "ok", "message": f"Consigne '{directive}' transmise au moteur Antigravity."}
    return {"status": "ignored", "message": "Aucune tâche active à adapter."}


@router.post("/api/task/stop")
async def post_task_stop(request: Request):
    """Interrompt immédiatement toute tâche ou développement en cours à la demande de l'utilisateur."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await stop_active_task(source="api_button", reason="Arrêt demandé via l'interface")
    return JSONResponse(content=res)
