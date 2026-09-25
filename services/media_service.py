"""Service multimedia J.A.R.V.I.S. - Deezer Web Player & Stremio.
Contrôle Deezer Web Player à 100% en temps réel (play, pause, next, prev, choix de musique, albums, playlists, volume, shuffle)
via le serveur WebSocket bridge local (deezer_bridge.py) et l'Userscript Tampermonkey (deezer_controller.user.js).
Et Stremio (recherche film/serie via API Cinemeta + stream 1080p le plus leger via Torrentio).
"""

import os
import sys
import re
import subprocess
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal

from deezer_bridge import (
    deezer_controller,
    search_catalog,
    play as bridge_play,
    pause as bridge_pause,
    next_track as bridge_next,
    previous_track as bridge_prev,
    toggle_shuffle as bridge_shuffle,
    play_music as bridge_play_music,
    get_playback_status as bridge_status
)

_CURRENT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _CURRENT_DIR.parent

# Chemins d'installation Stremio
STREMIO_PATHS = [
    r"C:\Users\pierr\AppData\Local\Programs\LNV\Stremio 5\Stremio.exe",
    r"C:\Users\pierr\AppData\Local\Programs\Stremio\Stremio.exe",
    r"C:\Program Files\Stremio\Stremio.exe",
    r"C:\Program Files (x86)\Stremio\Stremio.exe",
    r"C:\Users\pierr\AppData\Local\Programs\stremio\Stremio.exe",
]
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"

# API Cinemeta (base de donnees officielle Stremio)
STREMIO_CINEMETA_URL = "https://v3-cinemeta.strem.io"
# Torrentio - addon Stremio pour les streams
TORRENTIO_URL = "https://torrentio.strem.fun"


def _find_exe(paths: list) -> Optional[str]:
    """Cherche le premier executable existant dans la liste."""
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def is_deezer_running() -> bool:
    """Vérifie si le Web Player Deezer est connecté via WebSocket ou si le processus Deezer tourne."""
    if deezer_controller.is_connected():
        return True
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        cmd = ["tasklist", "/FI", "IMAGENAME eq Deezer.exe", "/NH"]
        res = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=2)
        return "deezer.exe" in res.stdout.lower()
    except Exception:
        return False


# ─── DEEZER WEB PLAYER (WEBSOCKET BRIDGE & REST API) ──────────────────────────

def launch_deezer(query: str = "") -> Dict[str, Any]:
    """Ouvre Deezer Web Player dans le navigateur par défaut."""
    try:
        from services.local_agent_service import local_agent_service
        if sys.platform != "win32" or local_agent_service.is_connected():
            if not local_agent_service.is_connected():
                return {
                    "status": "pc_offline",
                    "app": "Deezer Web",
                    "message": "Votre ordinateur personnel est éteint ou hors ligne. Impossible d'ouvrir Deezer sur votre écran."
                }
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                return asyncio.run_coroutine_threadsafe(
                    local_agent_service.execute_command("launch_media", app="deezer", query=query),
                    loop
                ).result(timeout=12)
            else:
                return asyncio.run(local_agent_service.execute_command("launch_media", app="deezer", query=query))
    except Exception:
        pass

    import webbrowser
    url = f"https://www.deezer.com/search/{query}" if query else "https://www.deezer.com"
    try:
        webbrowser.open(url)
        return {
            "status": "launched",
            "app": "Deezer Web",
            "query": query,
            "url": url,
            "message": f"Web Player Deezer ouvert sur : {url}"
        }
    except Exception as e:
        return {
            "status": "error",
            "app": "Deezer Web",
            "message": f"Impossible d'ouvrir Deezer : {e}"
        }


async def search_deezer(query: str, search_type: str = "track", limit: int = 5) -> List[Dict[str, Any]]:
    """Recherche des morceaux, albums, artistes ou playlists via l'API publique Deezer."""
    res = await deezer_controller.search_catalog(query=query, search_type=search_type, limit=limit)
    return res.get("results", [])


async def play_deezer_track(track_query: str = "", item_type: str = "track") -> Dict[str, Any]:
    """Lance la lecture d'un morceau, album, artiste ou playlist sur le Web Player Deezer."""
    return await deezer_controller.play_music(query=track_query, search_type=item_type)


async def deezer_play() -> Dict[str, Any]:
    """Reprend ou lance la lecture sur Deezer Web."""
    return await deezer_controller.play()


async def deezer_pause() -> Dict[str, Any]:
    """Met la lecture en pause sur Deezer Web."""
    return await deezer_controller.pause()


async def deezer_play_pause() -> Dict[str, Any]:
    """Bascule entre lecture et pause sur Deezer Web."""
    return await deezer_controller.toggle_play()


async def deezer_next() -> Dict[str, Any]:
    """Passe à la piste suivante sur Deezer Web."""
    return await deezer_controller.next_track()


async def deezer_prev() -> Dict[str, Any]:
    """Revient à la piste précédente sur Deezer Web."""
    return await deezer_controller.previous_track()


async def deezer_send_command(action: str) -> bool:
    """Envoie une commande basique au Web Player Deezer."""
    act = (action or "playpause").lower().strip()
    if act in ("next",):
        res = await deezer_controller.next_track()
    elif act in ("prev", "previous"):
        res = await deezer_controller.previous_track()
    elif act in ("pause", "stop"):
        res = await deezer_controller.pause()
    elif act in ("play",):
        res = await deezer_controller.play()
    else:
        res = await deezer_controller.toggle_play()
    return res.get("status") in ("success", "completed")


async def control_deezer(action: str = "playpause", query: str = "", item_type: str = "track", **kwargs) -> Dict[str, Any]:
    """Point d'entrée universel pour le contrôle complet (100%) de Deezer Web Player."""
    return await deezer_controller.control_deezer(action=action, query=query, item_type=item_type, **kwargs)




# ─── STREMIO ───────────────────────────────────────────────────────────────────

async def search_stremio_content(title: str, content_type: str = "movie") -> Dict[str, Any]:
    """Recherche un film ou serie via l'API Cinemeta de Stremio."""
    from urllib.parse import quote
    clean = title.strip()
    cat_type = "series" if content_type in ("series", "serie", "tv") else "movie"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            search_url = f"{STREMIO_CINEMETA_URL}/catalog/{cat_type}/top/search={quote(clean)}.json"
            resp = await client.get(search_url)

            if resp.status_code == 200:
                data = resp.json()
                metas = data.get("metas", [])
                if metas:
                    best = metas[0]
                    return {
                        "found": True,
                        "id": best.get("id", ""),
                        "name": best.get("name", title),
                        "year": best.get("year", ""),
                        "type": best.get("type", cat_type),
                        "poster": best.get("poster", ""),
                        "description": (best.get("description") or "")[:300],
                        "imdb_rating": best.get("imdbRating", "")
                    }
    except Exception as e:
        print(f"[Stremio Cinemeta] Erreur: {e}")

    return {"found": False, "name": title, "type": cat_type}


async def find_best_1080p_stream(imdb_id: str, content_type: str = "movie") -> Dict[str, Any]:
    """Interroge Torrentio pour trouver le stream 1080p le plus leger."""
    if not imdb_id:
        return {"found": False}

    cat_type = "series" if content_type in ("series", "serie", "tv") else "movie"

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            url = f"{TORRENTIO_URL}/stream/{cat_type}/{imdb_id}.json"
            resp = await client.get(url)

            if resp.status_code == 200:
                streams = resp.json().get("streams", [])

                def extract_size_gb(s: dict) -> float:
                    text = (s.get("title", "") or "") + (s.get("name", "") or "")
                    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:GB|GiB)", text, re.IGNORECASE)
                    if m:
                        return float(m.group(1))
                    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:MB|MiB)", text, re.IGNORECASE)
                    if m2:
                        return float(m2.group(1)) / 1024.0
                    return 9999.0

                streams_1080 = [
                    s for s in streams
                    if "1080" in ((s.get("name") or "") + (s.get("title") or ""))
                ]
                target_streams = streams_1080 if streams_1080 else streams
                if target_streams:
                    target_streams.sort(key=extract_size_gb)
                    best = target_streams[0]
                    size = extract_size_gb(best)
                    return {
                        "found": True,
                        "is_1080p": bool(streams_1080),
                        "stream_name": best.get("name", "Stream"),
                        "stream_title": best.get("title", ""),
                        "size_gb": round(size, 2) if size < 9000 else None,
                        "infoHash": best.get("infoHash"),
                        "url": best.get("url"),
                    }
    except Exception as e:
        print(f"[Stremio Torrentio] Erreur: {e}")

    return {"found": False}


def launch_stremio(stremio_id: str = "", content_type: str = "movie") -> Dict[str, Any]:
    """Ouvre Stremio, avec deeplink direct vers un contenu si l'ID est fourni."""
    try:
        from services.local_agent_service import local_agent_service
        if sys.platform != "win32" or local_agent_service.is_connected():
            if not local_agent_service.is_connected():
                return {
                    "status": "pc_offline",
                    "app": "Stremio",
                    "message": "Votre ordinateur personnel est éteint ou hors ligne. Impossible d'ouvrir Stremio sur votre écran."
                }
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                return asyncio.run_coroutine_threadsafe(
                    local_agent_service.execute_command("launch_media", app="stremio", stremio_id=stremio_id, content_type=content_type),
                    loop
                ).result(timeout=12)
            else:
                return asyncio.run(local_agent_service.execute_command("launch_media", app="stremio", stremio_id=stremio_id, content_type=content_type))
    except Exception:
        pass

    exe = _find_exe(STREMIO_PATHS)
    cat = "series" if content_type in ("series", "serie", "tv") else "movie"

    try:
        if stremio_id:
            deeplink = f"stremio:///detail/{cat}/{stremio_id}"
            if exe:
                subprocess.Popen([exe, deeplink], shell=False)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)
            return {
                "status": "launched",
                "app": "Stremio",
                "deeplink": deeplink,
                "message": f"Stremio ouvert sur le contenu {stremio_id}"
            }
        else:
            if exe:
                subprocess.Popen([exe], shell=False)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", "stremio://"], shell=False)
            return {
                "status": "launched",
                "app": "Stremio",
                "message": "Stremio ouvert sur votre ecran."
            }
    except Exception as e:
        return {
            "status": "error",
            "app": "Stremio",
            "message": f"Impossible de lancer Stremio : {e}"
        }


async def play_on_stremio(title: str, content_type: str = "movie") -> Dict[str, Any]:
    """Mission complete Stremio : recherche le film/serie, trouve le meilleur
    stream 1080p (le plus leger), et lance Stremio directement dessus."""

    print(f"[Stremio] Mission : '{title}' ({content_type})")

    # 1. Recherche metadata via Cinemeta
    meta = await search_stremio_content(title, content_type)
    if not meta.get("found") and content_type == "movie":
        meta = await search_stremio_content(title, "series")

    if not meta.get("found"):
        res = launch_stremio()
        return {
            "status": "not_found",
            "title_searched": title,
            "launch": res,
            "message": f"'{title}' introuvable dans la base Stremio. Stremio est ouvert, tu peux rechercher manuellement."
        }

    imdb_id = meta.get("id", "")
    found_title = meta.get("name", title)
    found_year = meta.get("year", "")
    found_type = meta.get("type", "movie")
    imdb_rating = meta.get("imdb_rating", "")

    print(f"[Stremio] Trouve : '{found_title}' ({found_year}) IMDb:{imdb_id}")

    # 2. Recherche du meilleur stream 1080p
    stream_info = {}
    if imdb_id:
        stream_info = await find_best_1080p_stream(imdb_id, found_type)

    # 3. Lancement Stremio via deeplink
    launch_res = launch_stremio(imdb_id, found_type)

    # 4. Message de synthese
    if stream_info.get("found"):
        qual = "1080p" if stream_info.get("is_1080p") else "meilleure qualite dispo"
        size_str = f"{stream_info['size_gb']} Go" if stream_info.get("size_gb") else "taille inconnue"
        stream_msg = f" Stream {qual} selectionne : {size_str}."
    else:
        stream_msg = " Les streams seront listes directement dans Stremio."

    rating_msg = f" Note IMDb : {imdb_rating}." if imdb_rating else ""

    return {
        "status": "launched",
        "app": "Stremio",
        "found_title": found_title,
        "year": found_year,
        "imdb_id": imdb_id,
        "content_type": found_type,
        "imdb_rating": imdb_rating,
        "stream_info": stream_info,
        "launch": launch_res,
        "message": f"Stremio lance sur '{found_title}' ({found_year}).{rating_msg}{stream_msg}"
    }


# ─── VLC ───────────────────────────────────────────────────────────────────────

def launch_vlc(target: str = "") -> Dict[str, Any]:
    """Ouvre VLC avec un fichier local ou une URL."""
    try:
        from services.local_agent_service import local_agent_service
        if sys.platform != "win32" or local_agent_service.is_connected():
            if not local_agent_service.is_connected():
                return {
                    "status": "pc_offline",
                    "app": "VLC",
                    "message": "Votre ordinateur personnel est éteint ou hors ligne. Impossible d'ouvrir VLC sur votre écran."
                }
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                return asyncio.run_coroutine_threadsafe(
                    local_agent_service.execute_command("launch_media", app="vlc", target=target),
                    loop
                ).result(timeout=12)
            else:
                return asyncio.run(local_agent_service.execute_command("launch_media", app="vlc", target=target))
    except Exception:
        pass

    if not os.path.exists(VLC_PATH):
        return {"status": "error", "message": f"VLC introuvable a {VLC_PATH}"}
    try:
        args = [VLC_PATH]
        if target:
            args.append(target)
        subprocess.Popen(args, shell=False)
        return {"status": "launched", "app": "VLC", "target": target}
    except Exception as e:
        return {"status": "error", "message": f"Impossible de lancer VLC : {e}"}