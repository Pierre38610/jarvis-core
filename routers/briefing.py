"""routers/briefing.py
Endpoints FastAPI pour la gestion du Morning Briefing et de l'Agenda J.A.R.V.I.S.
Permet au Cron n8n de déclencher la compilation quotidienne à 07h00,
et au HUD ou aux clients de consulter le briefing et l'agenda du jour.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import auth
from services.briefing_service import briefing_service
from services.cache import cache_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CompileBriefingRequest(BaseModel):
    force_refresh: Optional[bool] = True
    source: Optional[str] = "api"


@router.post("/api/briefing/compile")
async def compile_morning_briefing_endpoint(req: Optional[CompileBriefingRequest] = None, request: Request = None):
    """Déclenche la compilation du Morning Briefing et sa mise en cache dans Redis (TTL 16h).
    Accessible en local par le workflow Cron n8n ou via authentification standard.
    """
    client_ip = request.client.host if (request and request.client) else ""
    is_local = client_ip in ("127.0.0.1", "::1", "localhost", "172.17.0.1", "172.18.0.1")

    # Si requête externe, vérifier le token
    if not is_local:
        token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
        if not auth.is_device_authorized(token):
            return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    force = req.force_refresh if req is not None else True
    try:
        briefing_data = await briefing_service.compiler_morning_briefing(force_refresh=force)
        return {
            "status": "success",
            "message": "Morning Briefing compilé avec succès et mis en cache dans Redis.",
            "briefing": briefing_data
        }
    except Exception as exc:
        logger.error("[Router/Briefing] Erreur compilation : %s", exc)
        return JSONResponse(
            content={"status": "error", "message": f"Erreur lors de la compilation du briefing : {exc}"},
            status_code=500
        )


@router.get("/api/briefing/today")
@router.get("/api/briefing")
async def get_today_briefing_endpoint(request: Request):
    """Retourne le Morning Briefing du jour depuis le cache Redis (ou le génère si absent)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    force_refresh = request.query_params.get("refresh", "false").lower() in ("true", "1", "yes")
    briefing_data = await briefing_service.get_today_briefing(force_refresh=force_refresh)
    return briefing_data


@router.get("/api/agenda/today")
async def get_today_agenda_endpoint(request: Request):
    """Retourne les rendez-vous du jour mis en cache pour l'agenda Google / Samsung."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    cached_agenda = await cache_service.get("jarvis:agenda:today")
    events = cached_agenda if isinstance(cached_agenda, list) else []
    return {
        "status": "ok",
        "count": len(events),
        "events": events
    }
