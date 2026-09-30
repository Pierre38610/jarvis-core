"""deezer_bridge.py - Serveur WebSocket & Contrôleur API Deezer pour J.A.R.V.I.S. (ARCHIVÉ / DÉPRÉCIÉ)

NOTE : Ce composant a été entièrement remplacé par Spotify Connect Web API
(services/spotify_service.py et routers/spotify.py).
Conservé uniquement pour archive historique et rétrocompatibilité.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import sys
import re
import json
import uuid
import asyncio
import logging
import webbrowser
from typing import Dict, Any, Optional, List, Set, Tuple
import httpx
import websockets
from websockets.server import ServerConnection

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DeezerBridge")

# Constantes API & Serveur
DEEZER_WS_HOST = "127.0.0.1"
DEEZER_WS_PORT = 8765
DEEZER_API_BASE = "https://api.deezer.com"
DEEZER_WEB_BASE = "https://www.deezer.com"

DEEZER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}


def detect_search_intent(query: str, search_type: str = "track") -> Tuple[str, str, Optional[Dict[str, Any]]]:
    """Analyse l'intention et le type de contenu musical (Flow, Coups de cœur, Playlist, Album, Artiste, Morceau).
    Nettoie les mots parasites de la requête pour l'API REST Deezer.
    """
    raw = (query or "").strip()
    # Nettoyage des verbes d'action au début de la phrase
    q = re.sub(
        r"^(mets|joue|lance|écoute|ecoute|met|active)\s*(moi\s*)?(un|une|le|la|les|du|de la|des|ce|cette)?\s*",
        "",
        raw,
        flags=re.IGNORECASE
    ).strip()
    low = q.lower()

    # 1. Détection Deezer Flow
    if any(k in low for k in ["flow", "mon flow", "lance le flow", "mets le flow"]):
        return "flow", "", {
            "id": "flow",
            "title": "Flow Deezer",
            "artist": "Mix infini personnalisé",
            "album": "",
            "type": "flow",
            "duration": 0,
            "link": f"{DEEZER_WEB_BASE}/fr/channels/flow",
            "nav_url": f"{DEEZER_WEB_BASE}/fr/channels/flow",
            "cover": "https://e-cdns-images.dzcdn.net/images/misc/flow/500x500.jpg"
        }

    # 2. Détection Coups de cœur / Favoris / Titres likés
    if any(k in low for k in ["coup de coeur", "coups de coeur", "coups de cœur", "mes favoris", "favoris", "titres likés", "titres likes", "ma musique", "mes musiques"]):
        return "loved", "", {
            "id": "loved",
            "title": "Coups de cœur",
            "artist": "Mes favoris",
            "album": "",
            "type": "playlist",
            "duration": 0,
            "link": f"{DEEZER_WEB_BASE}/fr/channels/loved-tracks",
            "nav_url": f"{DEEZER_WEB_BASE}/fr/channels/loved-tracks",
            "cover": ""
        }

    # 3. Détection de Playlist
    if "playlist" in low or "mix" in low or "compil" in low or search_type == "playlist":
        cleaned = re.sub(r"\b(ma|la|une|des|les|cette)?\s*playlist\s*(de|d'|du|des)?\b", "", q, flags=re.IGNORECASE).strip()
        if not cleaned:
            # "mets ma playlist" sans nom -> Coups de cœur / Favoris de l'utilisateur
            return "loved", "", {
                "id": "loved",
                "title": "Coups de cœur",
                "artist": "Mes favoris",
                "album": "",
                "type": "playlist",
                "duration": 0,
                "link": f"{DEEZER_WEB_BASE}/fr/channels/loved-tracks",
                "nav_url": f"{DEEZER_WEB_BASE}/fr/channels/loved-tracks",
                "cover": ""
            }
        return "playlist", cleaned, None

    # 4. Détection d'Album
    if "album" in low or search_type == "album":
        cleaned = re.sub(r"\b(l'|le|un|cet|mon)?\s*album\s*(de|d'|du|des)?\b", "", q, flags=re.IGNORECASE).strip()
        return "album", cleaned or q, None

    # 5. Détection d'Artiste
    if "artiste" in low or "discographie" in low or search_type == "artist":
        cleaned = re.sub(r"\b(l'|le|un|cet)?\s*artiste\s*(de|d'|du|des)?\b", "", q, flags=re.IGNORECASE).strip()
        return "artist", cleaned or q, None

    return search_type or "track", q or raw, None


class DeezerController:
    """Contrôleur centralisé pour le Web Player Deezer.
    Gère le serveur WebSocket local, la communication bidirectionnelle avec l'onglet
    navigateur et les requêtes intelligentes à l'API publique Deezer.
    """

    def __init__(self, host: str = DEEZER_WS_HOST, port: int = DEEZER_WS_PORT):
        self.host = host
        self.port = port
        self.clients: Set[ServerConnection] = set()
        self._pending_commands: Dict[str, asyncio.Future] = {}
        self.last_status: Dict[str, Any] = {
            "title": "",
            "artist": "",
            "album": "",
            "cover": "",
            "is_playing": False,
            "shuffle": False,
            "repeat": "off",
            "current_time": 0,
            "duration": 0,
            "volume": 100,
            "url": ""
        }
        self._server = None
        self._lock = asyncio.Lock()
        self.is_running = False

    def is_connected(self) -> bool:
        """Indique si au moins un onglet Deezer est actuellement connecté."""
        return len(self.clients) > 0

    async def start(self):
        """Démarre le serveur WebSocket en arrière-plan."""
        async with self._lock:
            if self.is_running:
                return
            try:
                self._server = await websockets.serve(
                    self._ws_handler,
                    self.host,
                    self.port,
                    ping_interval=20,
                    ping_timeout=20
                )
                self.is_running = True
                logger.info(f"✅ Serveur Deezer WebSocket actif sur ws://{self.host}:{self.port}")
            except OSError as e:
                if "10048" in str(e) or "already in use" in str(e).lower():
                    logger.warning(f"⚠️ Port {self.port} déjà alloué pour Deezer Bridge, réutilisation.")
                    self.is_running = True
                else:
                    logger.error(f"❌ Erreur démarrage Deezer WebSocket : {e}")
                    raise

    async def stop(self):
        """Arrête le serveur WebSocket."""
        async with self._lock:
            if self._server:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
            self.is_running = False
            self.clients.clear()
            logger.info("Serveur Deezer WebSocket arrêté.")

    async def _ws_handler(self, websocket: ServerConnection, *args):
        """Gestionnaire de connexion entrante du Userscript Tampermonkey."""
        self.clients.add(websocket)
        logger.info(f"🎧 Onglet Deezer Web connecté ! (Clients actifs : {len(self.clients)})")

        try:
            async for raw_message in websocket:
                try:
                    msg = json.loads(raw_message)
                except Exception:
                    continue

                msg_type = msg.get("type")

                # Réception des statuts périodiques / événementiels
                if msg_type == "status":
                    status_data = msg.get("data", {})
                    if isinstance(status_data, dict):
                        self.last_status.update(status_data)

                # Réception de la réponse à une commande envoyée
                elif msg_type == "response":
                    cmd_id = msg.get("command_id")
                    if cmd_id and cmd_id in self._pending_commands:
                        future = self._pending_commands[cmd_id]
                        if not future.done():
                            future.set_result(msg)

                    data = msg.get("data")
                    if isinstance(data, dict):
                        self.last_status.update(data)

        except websockets.exceptions.ConnectionClosed:
            logger.info("Onglet Deezer Web déconnecté.")
        except Exception as e:
            logger.warning(f"Erreur connexion WebSocket Deezer : {e}")
        finally:
            self.clients.discard(websocket)
            logger.info(f"Clients Deezer restants : {len(self.clients)}")

    async def send_command(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
        """Envoie une instruction au script JS et attend l'accusé de réception."""
        if not self.is_connected():
            return {
                "status": "completed",
                "action": action,
                "connected": False,
                "message": (
                    "Commande reçue : aucun onglet Deezer Web n'est actuellement connecté au WebSocket. "
                    "Ouvrez https://www.deezer.com dans le navigateur avec le script Tampermonkey activé pour le contrôle en direct."
                ),
                "data": self.last_status
            }

        cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"
        payload = {
            "type": "command",
            "command_id": cmd_id,
            "action": action,
            "params": params or {}
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_commands[cmd_id] = future

        # Diffusion du message au(x) client(s) connecté(s)
        disconnected = set()
        for ws in list(self.clients):
            try:
                await ws.send(json.dumps(payload))
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self.clients.discard(ws)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "action": action,
                "command_id": cmd_id,
                "message": f"Délai d'attente dépassé pour la commande '{action}'.",
                "data": self.last_status
            }
        except Exception as e:
            return {
                "status": "error",
                "action": action,
                "message": f"Erreur lors de l'exécution de '{action}' : {e}",
                "data": self.last_status
            }
        finally:
            self._pending_commands.pop(cmd_id, None)

    async def search_catalog(self, query: str, search_type: str = "track", limit: int = 5) -> Dict[str, Any]:
        """Interroge l'API REST publique de Deezer pour trouver l'ID et l'URL du morceau/album/artiste/playlist.
        Détecte automatiquement l'intention (playlist, album, flow, favoris) et nettoie la requête.
        """
        intent_type, clean_q, special_obj = detect_search_intent(query, search_type)

        # Si intention spéciale directe (Flow ou Coups de cœur)
        if special_obj:
            return {
                "found": True,
                "query": query,
                "type": intent_type,
                "best": special_obj,
                "results": [special_obj]
            }

        if not clean_q:
            clean_q = query.strip()

        st = intent_type.lower().strip()
        if st in ("album", "albums"):
            endpoint = f"{DEEZER_API_BASE}/search/album"
            canonical_type = "album"
        elif st in ("playlist", "playlists"):
            endpoint = f"{DEEZER_API_BASE}/search/playlist"
            canonical_type = "playlist"
            limit = max(limit, 10)  # Récupérer plus pour filtrer par pertinence
        elif st in ("artist", "artiste", "artists"):
            endpoint = f"{DEEZER_API_BASE}/search/artist"
            canonical_type = "artist"
        else:
            endpoint = f"{DEEZER_API_BASE}/search"
            canonical_type = "track"

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=DEEZER_HEADERS) as client:
                resp = await client.get(endpoint, params={"q": clean_q, "limit": limit})
                if resp.status_code == 200:
                    raw_data = resp.json().get("data", [])

                    # Pour les playlists : privilégier les playlists volumineuses (>10 morceaux) et populaires
                    if canonical_type == "playlist" and raw_data:
                        def score_pl(p):
                            nb = p.get("nb_tracks", 0) or 0
                            fans = p.get("fans", 0) or 0
                            penalty = 0 if nb >= 10 else -1000
                            return fans + (nb * 3) + penalty
                        raw_data = sorted(raw_data, key=score_pl, reverse=True)

                    results = []
                    for item in raw_data:
                        item_id = item.get("id")
                        title = item.get("title") or item.get("name") or "Inconnu"
                        
                        artist_obj = item.get("artist") or {}
                        artist_name = artist_obj.get("name") if isinstance(artist_obj, dict) else (item.get("name") if canonical_type == "artist" else "")
                        
                        album_obj = item.get("album") or {}
                        album_title = album_obj.get("title") if isinstance(album_obj, dict) else (item.get("title") if canonical_type == "album" else "")
                        
                        cover = ""
                        if isinstance(album_obj, dict) and album_obj.get("cover_medium"):
                            cover = album_obj.get("cover_medium")
                        elif item.get("picture_medium"):
                            cover = item.get("picture_medium")
                        elif item.get("cover_medium"):
                            cover = item.get("cover_medium")

                        link = item.get("link") or f"{DEEZER_WEB_BASE}/{canonical_type}/{item_id}"
                        nav_url = f"{DEEZER_WEB_BASE}/fr/{canonical_type}/{item_id}"

                        results.append({
                            "id": item_id,
                            "title": title,
                            "artist": artist_name,
                            "album": album_title,
                            "type": item.get("type", canonical_type),
                            "duration": item.get("duration", 0),
                            "nb_tracks": item.get("nb_tracks", 0),
                            "link": link,
                            "nav_url": nav_url,
                            "cover": cover,
                            "preview": item.get("preview", "")
                        })

                    best = results[0] if results else None
                    return {
                        "found": bool(best),
                        "query": clean_q,
                        "type": canonical_type,
                        "best": best,
                        "results": results
                    }
        except Exception as e:
            logger.error(f"Erreur API Deezer search : {e}")

        return {"found": False, "query": clean_q, "type": canonical_type, "results": [], "best": None}

    # ─── OUTILS AGENT LLM ──────────────────────────────────────────────────────

    async def play(self) -> Dict[str, Any]:
        """Lance ou reprend la lecture sur le Web Player Deezer."""
        res = await self.send_command("play")
        return {
            "status": res.get("status", "completed"),
            "action": "play",
            "message": "Lecture lancée sur Deezer.",
            "data": res.get("data", self.last_status)
        }

    async def pause(self) -> Dict[str, Any]:
        """Met la lecture en pause sur le Web Player Deezer."""
        res = await self.send_command("pause")
        return {
            "status": res.get("status", "completed"),
            "action": "pause",
            "message": "Deezer mis en pause.",
            "data": res.get("data", self.last_status)
        }

    async def toggle_play(self) -> Dict[str, Any]:
        """Bascule entre lecture et pause."""
        res = await self.send_command("toggle_play")
        return {
            "status": res.get("status", "completed"),
            "action": "toggle_play",
            "message": "Lecture / Pause basculée sur Deezer.",
            "data": res.get("data", self.last_status)
        }

    async def next_track(self) -> Dict[str, Any]:
        """Passe à la piste suivante sur le Web Player Deezer."""
        res = await self.send_command("next")
        return {
            "status": res.get("status", "completed"),
            "action": "next",
            "message": "Piste suivante sur Deezer.",
            "data": res.get("data", self.last_status)
        }

    async def previous_track(self) -> Dict[str, Any]:
        """Revient à la piste précédente sur le Web Player Deezer."""
        res = await self.send_command("previous")
        return {
            "status": res.get("status", "completed"),
            "action": "previous",
            "message": "Piste précédente sur Deezer.",
            "data": res.get("data", self.last_status)
        }

    async def toggle_shuffle(self, enable: Optional[bool] = None) -> Dict[str, Any]:
        """Active, désactive ou bascule le mode lecture aléatoire (shuffle)."""
        params = {}
        if enable is not None:
            params["enable"] = bool(enable)
        res = await self.send_command("set_shuffle", params)
        state_str = "activé" if enable is True else ("désactivé" if enable is False else "basculé")
        return {
            "status": res.get("status", "completed"),
            "action": "set_shuffle",
            "shuffle": res.get("data", {}).get("shuffle"),
            "message": f"Mode aléatoire Deezer {state_str}.",
            "data": res.get("data", self.last_status)
        }

    async def set_repeat(self, mode: str = "all") -> Dict[str, Any]:
        """Configure le mode répétition ('off', 'all', 'one')."""
        res = await self.send_command("set_repeat", {"mode": mode})
        return {
            "status": res.get("status", "completed"),
            "action": "set_repeat",
            "message": f"Répétition Deezer configurée sur '{mode}'.",
            "data": res.get("data", self.last_status)
        }

    async def set_volume(self, volume: int) -> Dict[str, Any]:
        """Modifie le volume de Deezer (de 0 à 100)."""
        vol = max(0, min(100, int(volume)))
        res = await self.send_command("set_volume", {"volume": vol})
        return {
            "status": res.get("status", "completed"),
            "action": "set_volume",
            "volume": vol,
            "message": f"Volume Deezer ajusté à {vol}%.",
            "data": res.get("data", self.last_status)
        }

    async def seek(self, position: float) -> Dict[str, Any]:
        """Avance ou recule la lecture à un timestamp précis en secondes."""
        pos = max(0.0, float(position))
        res = await self.send_command("seek", {"position": pos})
        return {
            "status": res.get("status", "completed"),
            "action": "seek",
            "position": pos,
            "message": f"Lecture Deezer déplacée à {pos:.1f} secondes.",
            "data": res.get("data", self.last_status)
        }

    async def play_music(self, query: str, search_type: str = "track") -> Dict[str, Any]:
        """Recherche intelligente de musique (titre, album, playlist, Flow, Coups de cœur)
        et déclenchement immédiat de la lecture sur Deezer Web Player.
        """
        clean_q = (query or "").strip()
        if not clean_q:
            return await self.play()

        # 1. Recherche avec détection d'intention automatique
        search_res = await self.search_catalog(clean_q, search_type=search_type, limit=10)
        best = search_res.get("best")

        if not best:
            if search_type != "track":
                search_res = await self.search_catalog(clean_q, search_type="track", limit=5)
                best = search_res.get("best")

        if not best:
            return {
                "status": "not_found",
                "query": clean_q,
                "message": f"Aucun résultat trouvé sur Deezer pour '{clean_q}'."
            }

        target_url = best.get("nav_url") or best.get("link")
        title = best.get("title", clean_q)
        artist = best.get("artist", "")
        album = best.get("album", "")
        cover = best.get("cover", "")
        item_id = best.get("id")
        item_type = best.get("type", "track")
        artist_desc = f" par {artist}" if artist else ""

        # 2. Si l'onglet Deezer est connecté via WebSocket, envoyer les paramètres précis
        if self.is_connected():
            cmd_params = {
                "url": target_url,
                "type": item_type,
                "id": str(item_id),
                "title": title
            }
            cmd_res = await self.send_command("play_url", cmd_params, timeout=10.0)
            return {
                "status": "playing",
                "app": "Deezer Web",
                "query": clean_q,
                "title": title,
                "artist": artist,
                "album": album,
                "cover": cover,
                "url": target_url,
                "track": best,
                "message": f"Lecture de '{title}'{artist_desc} lancée sur Deezer Web ({item_type}).",
                "data": cmd_res.get("data", self.last_status)
            }
        else:
            # Repli : ouvrir Deezer dans le navigateur par défaut
            try:
                webbrowser.open(target_url)
                return {
                    "status": "launched_browser",
                    "app": "Deezer Web",
                    "query": clean_q,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "cover": cover,
                    "url": target_url,
                    "track": best,
                    "message": (
                        f"Deezer Web ouvert sur '{title}'{artist_desc}. "
                        "Le script Tampermonkey prendra le relais automatiquement dès que l'onglet sera chargé."
                    )
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Impossible d'ouvrir le navigateur pour Deezer : {e}"
                }

    async def get_playback_status(self) -> Dict[str, Any]:
        """Récupère l'état actuel complet de la lecture (titre, artiste, pause, shuffle, etc.)."""
        if self.is_connected():
            res = await self.send_command("get_status", timeout=2.0)
            if res.get("status") == "success" and "data" in res:
                self.last_status.update(res["data"])

        return {
            "status": "ok",
            "connected": self.is_connected(),
            "playback": self.last_status
        }

    async def control_deezer(self, action: str = "playpause", query: str = "", item_type: str = "track", **kwargs) -> Dict[str, Any]:
        """Point d'entrée universel pour le contrôle complet (100%) de Deezer Web Player."""
        act = (action or "playpause").lower().strip()

        if act in ("pause", "stop", "arreter", "arrête"):
            return await self.pause()

        elif act in ("play", "reprendre", "resume", "lecture"):
            if query:
                return await self.play_music(query, search_type=item_type)
            return await self.play()

        elif act in ("playpause", "toggle", "basculer"):
            if query:
                return await self.play_music(query, search_type=item_type)
            return await self.toggle_play()

        elif act in ("next", "suivant", "next_track"):
            return await self.next_track()

        elif act in ("prev", "previous", "precedent", "précédent", "prev_track"):
            return await self.previous_track()

        elif act in ("shuffle", "aleatoire", "aléatoire"):
            enable_val = kwargs.get("enable")
            return await self.toggle_shuffle(enable=enable_val)

        elif act in ("volume", "set_volume"):
            vol = kwargs.get("volume", 50)
            return await self.set_volume(vol)

        elif act in ("seek", "position"):
            pos = kwargs.get("position", 0)
            return await self.seek(pos)

        elif act in ("choose", "select", "choisir", "jouer", "search", "track", "album", "playlist", "artist"):
            return await self.play_music(query, search_type=item_type)

        elif act in ("open", "launch", "ouvrir"):
            if query:
                return await self.play_music(query, search_type=item_type)
            webbrowser.open(DEEZER_WEB_BASE)
            return {
                "status": "opened",
                "message": "Web Player Deezer ouvert dans le navigateur."
            }

        elif act in ("status", "info", "current"):
            return await self.get_playback_status()

        else:
            if query:
                return await self.play_music(query, search_type=item_type)
            return await self.toggle_play()


# ─── INSTANCE SINGLETON ET FONCTIONS STANDALONE POUR TOOLS LLM ────────────────

deezer_controller = DeezerController()


async def play() -> Dict[str, Any]:
    return await deezer_controller.play()


async def pause() -> Dict[str, Any]:
    return await deezer_controller.pause()


async def next_track() -> Dict[str, Any]:
    return await deezer_controller.next_track()


async def previous_track() -> Dict[str, Any]:
    return await deezer_controller.previous_track()


async def toggle_shuffle(enable: Optional[bool] = None) -> Dict[str, Any]:
    return await deezer_controller.toggle_shuffle(enable)


async def play_music(query: str, search_type: str = "track") -> Dict[str, Any]:
    return await deezer_controller.play_music(query, search_type=search_type)


async def get_playback_status() -> Dict[str, Any]:
    return await deezer_controller.get_playback_status()


async def search_catalog(query: str, search_type: str = "track", limit: int = 5) -> Dict[str, Any]:
    return await deezer_controller.search_catalog(query, search_type=search_type, limit=limit)


# ─── EXÉCUTION STANDALONE DU SERVEUR ──────────────────────────────────────────

async def main():
    print("=" * 60)
    print("🎵 J.A.R.V.I.S. - Serveur Deezer WebSocket Bridge")
    print(f"🔗 WebSocket : ws://{DEEZER_WS_HOST}:{DEEZER_WS_PORT}")
    print("=" * 60)
    await deezer_controller.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nArrêt du pont Deezer...")
        await deezer_controller.stop()


if __name__ == "__main__":
    asyncio.run(main())
