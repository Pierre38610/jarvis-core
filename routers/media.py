"""routers/media.py
Endpoints Deezer (/api/media/deezer/*) et ressources média (Stremio, userscript).
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import auth
import config
from services.media_service import control_deezer, search_deezer

router = APIRouter()


class DeezerControlRequest(BaseModel):
    action: str = "playpause"
    query: str = ""
    item_type: str = "track"
    volume: int | None = None
    position: float | None = None
    enable: bool | None = None


@router.post("/api/media/deezer/control")
async def api_control_deezer(req: DeezerControlRequest, request: Request):
    """Contrôle total du Web Player Deezer : play, pause, playpause, next, prev, shuffle, volume, choose, open."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await control_deezer(
        action=req.action,
        query=req.query,
        item_type=req.item_type,
        volume=req.volume,
        position=req.position,
        enable=req.enable
    )
    return res


@router.get("/api/media/deezer/search")
async def api_search_deezer(query: str, type: str = "track", limit: int = 5, request: Request = None):
    """Recherche des morceaux, albums ou playlists via l'API Deezer."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") if request else None
    if token and not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    results = await search_deezer(query=query, search_type=type, limit=limit)
    return {"query": query, "type": type, "count": len(results), "results": results}


@router.get("/api/media/deezer/status")
async def api_deezer_status(request: Request = None):
    """Récupère l'état temps réel du Web Player Deezer."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") if request else None
    if token and not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    from services.local_agent_service import local_agent_service
    if local_agent_service.is_connected() and local_agent_service._last_deezer_status:
        return {"status": "ok", "connected": True, "playback": local_agent_service._last_deezer_status}
    from deezer_bridge import deezer_controller
    return await deezer_controller.get_playback_status()


@router.get("/api/media/deezer/userscript")
async def api_deezer_userscript():
    """Sert le script Tampermonkey pour installation directe en un clic."""
    script_path = os.path.join(config.STATIC_DIR, "deezer_controller.user.js")
    if not os.path.exists(script_path):
        script_path = os.path.join(config.BASE_DIR, "deezer_controller.user.js")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/javascript", filename="deezer_controller.user.js")
    return JSONResponse(status_code=404, content={"message": "Script Tampermonkey introuvable"})
