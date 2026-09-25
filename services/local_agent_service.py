"""Service de liaison avec l'Agent Relais Local (PC Windows de Pierre).
Permet à Jarvis hébergé sur VPS de détecter si le PC personnel est allumé,
et d'y exécuter des actions locales (lancer VS Code, VLC, Deezer, etc.).
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

class LocalAgentService:
    def __init__(self):
        self._ws: Optional[WebSocket] = None
        self._connected_at: Optional[float] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._last_pc_status: Optional[Dict[str, Any]] = None

    def is_connected(self) -> bool:
        """Indique si le PC de Pierre est allumé et connecté au VPS."""
        return self._ws is not None

    def get_info(self) -> Dict[str, Any]:
        """Retourne les informations de connexion du PC."""
        return {
            "online": self.is_connected(),
            "connected_at": self._connected_at,
            "uptime_seconds": round(time.time() - self._connected_at, 1) if self._connected_at else 0,
            "last_status": self._last_pc_status
        }

    async def register(self, websocket: WebSocket):
        """Enregistre le client WebSocket du PC."""
        await websocket.accept()
        self._ws = websocket
        self._connected_at = time.time()
        print("[LocalAgent] ✅ Ordinateur personnel de Pierre connecté au VPS.", flush=True)

    def unregister(self):
        """Déconnecte le client WebSocket."""
        self._ws = None
        self._connected_at = None
        # Annule les requêtes en attente
        for req_id, fut in list(self._pending_requests.items()):
            if not fut.done():
                fut.set_result({
                    "status": "pc_disconnected",
                    "message": "Le PC s'est déconnecté avant la fin de l'action."
                })
        self._pending_requests.clear()
        print("[LocalAgent] ⚠️ Ordinateur personnel de Pierre déconnecté du VPS.", flush=True)

    async def handle_agent_messages(self):
        """Boucle de réception des réponses et télémétrie de l'agent local."""
        try:
            while True:
                msg = await self._ws.receive_text()
                try:
                    data = json.loads(msg)
                except Exception:
                    continue

                msg_type = data.get("type")
                req_id = data.get("req_id")

                if req_id and req_id in self._pending_requests:
                    fut = self._pending_requests.pop(req_id, None)
                    if fut and not fut.done():
                        fut.set_result(data.get("result", data))
                elif msg_type == "telemetry":
                    self._last_pc_status = data.get("data")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[LocalAgent] Exception flux : {e}", flush=True)
        finally:
            self.unregister()

    async def execute_command(self, action: str, timeout: float = 12.0, **kwargs) -> Dict[str, Any]:
        """Transmet une commande à exécuter sur le PC personnel de Pierre."""
        if not self.is_connected():
            return {
                "status": "pc_offline",
                "message": (
                    "Votre ordinateur personnel est actuellement éteint ou déconnecté. "
                    "Impossible de lancer cette application sur votre écran physique pour le moment."
                )
            }

        req_id = f"cmd_{int(time.time() * 1000)}_{action}"
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_requests[req_id] = fut

        payload = {
            "req_id": req_id,
            "action": action,
            "params": kwargs
        }

        try:
            await self._ws.send_text(json.dumps(payload))
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            return {
                "status": "timeout",
                "message": "Votre PC n'a pas répondu dans le délai imparti."
            }
        except Exception as e:
            self._pending_requests.pop(req_id, None)
            return {
                "status": "error",
                "message": f"Erreur de communication avec votre PC : {e}"
            }

# Instance singleton
local_agent_service = LocalAgentService()
