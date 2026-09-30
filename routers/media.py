"""routers/media.py
Ressources média legacy (Tampermonkey userscript) et redirections post-migration.
Note : le streaming audio et le contrôle musical sont désormais gérés par routers/spotify.py (/api/media/spotify/*).
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

import auth
import config

router = APIRouter()


@router.post("/api/media/deezer/control")
async def api_control_deezer_deprecated(request: Request):
    """Endpoint déprécié suite à la migration vers Spotify."""
    return JSONResponse(
        status_code=410,
        content={
            "status": "deprecated",
            "message": "L'intégration Deezer a été remplacée par Spotify. Veuillez utiliser /api/media/spotify/control."
        }
    )


@router.get("/api/media/deezer/search")
async def api_search_deezer_deprecated(request: Request = None):
    """Endpoint déprécié suite à la migration vers Spotify."""
    return JSONResponse(
        status_code=410,
        content={
            "status": "deprecated",
            "message": "La recherche Deezer a été remplacée par Spotify. Veuillez utiliser /api/media/spotify/*."
        }
    )


@router.get("/api/media/deezer/status")
async def api_deezer_status_deprecated(request: Request = None):
    """Endpoint déprécié suite à la migration vers Spotify."""
    return JSONResponse(
        status_code=410,
        content={
            "status": "deprecated",
            "message": "Le statut Deezer a été remplacé par Spotify. Veuillez utiliser /api/media/spotify/status."
        }
    )


@router.get("/api/media/deezer/userscript")
async def api_deezer_userscript():
    """Sert le script Tampermonkey pour archive ou installation legacy."""
    script_path = os.path.join(config.STATIC_DIR, "deezer_controller.user.js")
    if not os.path.exists(script_path):
        script_path = os.path.join(config.BASE_DIR, "deezer_controller.user.js")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/javascript", filename="deezer_controller.user.js")
    return JSONResponse(status_code=404, content={"message": "Script Tampermonkey introuvable"})

