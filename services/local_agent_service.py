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
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connected_at: Optional[float] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._last_pc_status: Optional[Dict[str, Any]] = None
        self._last_deezer_status: Optional[Dict[str, Any]] = None

    def is_connected(self) -> bool:
        """Indique si le PC de Pierre est allumé et connecté au VPS."""
        return self._ws is not None

    def get_info(self) -> Dict[str, Any]:
        """Retourne les informations de connexion du PC."""
        return {
            "online": self.is_connected(),
            "connected_at": self._connected_at,
            "uptime_seconds": round(time.time() - self._connected_at, 1) if self._connected_at else 0,
            "last_status": self._last_pc_status,
            "deezer_status": self._last_deezer_status
        }

    async def register(self, websocket: WebSocket):
        """Enregistre le client WebSocket du PC."""
        await websocket.accept()
        if self._ws and self._ws != websocket:
            try:
                await self._ws.close(code=1000, reason="Nouvelle connexion active")
            except Exception:
                pass
        self._ws = websocket
        self._loop = asyncio.get_running_loop()
        self._connected_at = time.time()
        print("[LocalAgent] ✅ Ordinateur personnel de Pierre connecté au VPS.", flush=True)

        # Enregistrement de présence dans le cache Redis
        try:
            from services.cache import cache_service
            asyncio.create_task(cache_service.set_device_presence(
                "pc_status",
                status={"online": True, "connected_at": self._connected_at},
                ttl=120
            ))
        except Exception:
            pass

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

        # Mise à jour présence Redis
        try:
            from services.cache import cache_service
            if self._loop and self._loop.is_running():
                asyncio.create_task(cache_service.set_device_presence(
                    "pc_status",
                    status={"online": False},
                    ttl=60
                ))
        except Exception:
            pass

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
                    # Synchronisation présence avec télémétrie dans Redis
                    try:
                        from services.cache import cache_service
                        status_dict = {"online": True}
                        if isinstance(self._last_pc_status, dict):
                            status_dict.update(self._last_pc_status)
                        asyncio.create_task(cache_service.set_device_presence(
                            "pc_status",
                            status=status_dict,
                            ttl=120
                        ))
                    except Exception:
                        pass
                elif msg_type == "deezer_status":
                    self._last_deezer_status = data.get("data")
        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"[LocalAgent] Exception flux : {e}", flush=True)
        finally:
            self.unregister()

    async def execute_command(self, action: str, timeout: float = 12.0, **kwargs) -> Dict[str, Any]:
        """Transmet une commande à exécuter sur le PC personnel de Pierre (appel async)."""
        if not self.is_connected():
            return {
                "status": "pc_offline",
                "message": (
                    "Votre ordinateur personnel est actuellement éteint ou le script start_local_agent.bat n'est pas lancé. "
                    "Impossible d'exécuter cette action sur votre écran physique pour le moment."
                )
            }

        req_id = f"cmd_{int(time.time() * 1000)}_{action}"
        loop = self._loop or asyncio.get_running_loop()
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

    async def send_command(self, action: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 12.0, **kwargs) -> Dict[str, Any]:
        """Router une commande vers l'agent local (supporte un dictionnaire payload ou des kwargs)."""
        params = dict(payload or {})
        params.update(kwargs)
        return await self.execute_command(action, timeout=timeout, **params)

    def execute_command_sync(self, action: str, timeout: float = 12.0, **kwargs) -> Dict[str, Any]:
        """Transmet une commande depuis un thread synchrone (ex: thread pool) en toute sécurité."""
        if not self.is_connected() or not self._loop or not self._loop.is_running():
            return {
                "status": "pc_offline",
                "message": (
                    "Votre ordinateur personnel est actuellement éteint ou le script start_local_agent.bat n'est pas lancé. "
                    "Impossible d'exécuter cette action sur votre écran physique pour le moment."
                )
            }
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.execute_command(action, timeout=timeout, **kwargs),
                self._loop
            )
            return future.result(timeout=timeout + 2.0)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erreur relais PC : {e}"
            }

# Instance singleton
local_agent_service = LocalAgentService()


def is_pc_connected() -> bool:
    """Helper synchrone rapide indiquant si le PC de Pierre est connecté au serveur."""
    return local_agent_service.is_connected()


async def is_pc_connected_async() -> bool:
    """Helper asynchrone vérifiant le WebSocket local et l'état de présence Redis."""
    if local_agent_service.is_connected():
        return True
    try:
        from services.cache import cache_service
        pres = await cache_service.get_device_presence("pc_status")
        if pres and isinstance(pres, dict):
            status = pres.get("status")
            if isinstance(status, dict) and status.get("online"):
                return True
            elif status in ("online", True):
                return True
    except Exception:
        pass
    return False


