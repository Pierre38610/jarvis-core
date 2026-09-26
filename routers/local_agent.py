"""routers/local_agent.py
WebSocket /ws/local-agent : relais vers le PC de bureau Windows de Pierre.
Et endpoint REST /api/local-agent/status.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import config
from services.local_agent_service import local_agent_service

router = APIRouter()


@router.websocket("/ws/local-agent")
async def local_agent_ws_endpoint(websocket: WebSocket):
    """WebSocket relais local entre le VPS et le PC Windows de Pierre."""
    token = websocket.query_params.get("token") or websocket.headers.get("x-jarvis-token")
    if token != config.ACCESS_PASSWORD:
        await websocket.close(code=4003, reason="Token agent invalide")
        return
    await local_agent_service.register(websocket)
    await local_agent_service.handle_agent_messages()


@router.get("/api/local-agent/status")
async def local_agent_status_endpoint():
    """Retourne l'état de la connexion de l'agent local Windows."""
    return local_agent_service.get_info()
