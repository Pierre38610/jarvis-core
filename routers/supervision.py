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


@router.get("/api/supervision/metrics")
async def get_supervision_metrics(request: Request):
    """Retourne l'historique et les statistiques agrégées des appels d'outils (24h/7j/30j)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    window = request.query_params.get("window", "24h")
    from services.metrics_service import metrics_service
    summary = await metrics_service.get_metrics_summary(window_str=window)
    return JSONResponse(content=summary)


@router.get("/api/supervision/patches")
async def get_supervision_patches(request: Request):
    """Retourne le journal des patches d'auto-guérison (diff, tests, statut, release) depuis PostgreSQL."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    from services.system_healing_service import system_healing_service
    patches = await system_healing_service.get_recent_patches(limit=50)
    return JSONResponse(content={"patches": patches, "total": len(patches)})


@router.post("/api/supervision/patches/{patch_id}/rollback")
async def post_supervision_patch_rollback(patch_id: str, request: Request):
    """Déclenche le rollback instantané d'un patch appliqué vers la release précédente."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    from services.system_healing_service import system_healing_service
    res = await system_healing_service.rollback_patch(patch_id=patch_id)
    await broadcast_supervision()
    return JSONResponse(content=res, status_code=200 if res.get("success") else 400)


@router.post("/api/supervision/patches/{patch_id}/approve")
async def post_supervision_patch_approve(patch_id: str, request: Request):
    """Valide et applique en production un patch sur fichier critique en attente d'approbation."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    from services.system_healing_service import system_healing_service
    res = await system_healing_service.approve_and_apply_patch(patch_id=patch_id)
    await broadcast_supervision()
    return JSONResponse(content=res, status_code=200 if res.get("success") else 400)



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


@router.get("/api/supervision/turns")
async def get_supervision_turns(request: Request):
    """Retourne l'audit des tours de dialogue (outils, transcript, false_claim, durée, coupures) avec filtre 'since'."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    since = request.query_params.get("since")
    limit_param = request.query_params.get("limit", "50")
    try:
        limit = max(1, min(200, int(limit_param)))
    except ValueError:
        limit = 50

    from services.turn_audit import get_turn_audits
    turns = get_turn_audits(since=since, limit=limit)
    return JSONResponse(content={"turns": turns, "count": len(turns), "total": len(turns)})
