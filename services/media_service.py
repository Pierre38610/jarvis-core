"""Service multimedia J.A.R.V.I.S. - Stremio & VLC.
Contrôle Stremio (recherche film/serie via API Cinemeta + stream 1080p le plus leger via Torrentio)
et VLC pour la lecture locale.
Note : la musique est desormais geree par services/spotify_service.py.
"""

import os
import sys
import re
import subprocess
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal


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
                    "message": "Votre ordinateur personnel est éteint ou le script start_local_agent.bat n'est pas lancé. Impossible d'ouvrir Stremio sur votre écran."
                }
            return local_agent_service.execute_command_sync(
                "launch_media",
                timeout=12.0,
                app="stremio",
                stremio_id=stremio_id,
                content_type=content_type
            )
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
                    "message": "Votre ordinateur personnel est éteint ou le script start_local_agent.bat n'est pas lancé. Impossible d'ouvrir VLC sur votre écran."
                }
            return local_agent_service.execute_command_sync(
                "launch_media",
                timeout=12.0,
                app="vlc",
                target=target
            )
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