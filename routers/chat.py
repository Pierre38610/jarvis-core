"""routers/chat.py
Endpoints de messagerie écrite et d'analyse visuelle multimodale.
"""
import json

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse

import auth
from services.chat_service import chat_service
from core.shared_state import active_task_controller

router = APIRouter()


@router.get("/api/chat/history")
async def get_chat_history(request: Request, limit: int = 50):
    """Retourne l'historique des échanges écrits et photos analysées."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    messages = chat_service.get_history(limit=limit)
    return {"status": "success", "messages": messages}


@router.post("/api/chat/message")
async def post_chat_message(
    request: Request,
    text: str | None = Form(None),
    image: UploadFile | None = File(None)
):
    """Reçoit un message écrit et/ou une photo pour analyse multimodale par JARVIS."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    image_bytes = None
    image_mime = "image/jpeg"
    filename = None
    if image:
        image_bytes = await image.read()
        image_mime = image.content_type or "image/jpeg"
        filename = image.filename

    res = await chat_service.process_user_message(
        text=text,
        image_bytes=image_bytes,
        image_mime=image_mime,
        filename=filename
    )

    # Notification en direct au WebSocket si connecté
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "chat_message_received",
                "user_message": res.get("user_message"),
                "jarvis_message": res.get("jarvis_message")
            }))
        except Exception:
            pass

    return JSONResponse(content=res)


@router.post("/api/chat/clear")
async def post_chat_clear(request: Request):
    """Efface l'historique complet de la messagerie."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    chat_service.clear_history()
    return {"status": "success", "message": "Historique de discussion effacé."}
