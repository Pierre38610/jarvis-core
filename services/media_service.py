"""Service multimedia J.A.R.V.I.S. - Deezer et Stremio.
Contrôle Deezer à 100% (play, pause, next, prev, choix de musique, albums, playlists via deezer-ctl WinRT SMTC et API Deezer)
et Stremio (recherche film/serie via API Cinemeta + stream 1080p le plus leger via Torrentio).
"""

import os
import sys
import re
import subprocess
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal

# Chemins d'installation Deezer
DEEZER_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\deezer-desktop\Deezer.exe"),
    r"C:\Users\pierr\AppData\Local\Programs\deezer-desktop\Deezer.exe",
    r"C:\Users\pierr\AppData\Local\Programs\Deezer\Deezer.exe",
    r"C:\Program Files\Deezer\Deezer.exe",
    r"C:\Program Files (x86)\Deezer\Deezer.exe",
]

# Répertoire de deezer-ctl (WinRT SMTC binaries et wrapper python)
_CURRENT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _CURRENT_DIR.parent
DEEZER_CTL_DIR = _WORKSPACE_ROOT / "my-project" / "deezer-ctl"
DEEZER_CTL_BIN = DEEZER_CTL_DIR / "bin"

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

DEEZER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}


def _find_exe(paths: list) -> Optional[str]:
    """Cherche le premier executable existant dans la liste."""
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def is_deezer_running() -> bool:
    """Vérifie si le processus Deezer Desktop est actuellement en cours d'exécution."""
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        cmd = ["tasklist", "/FI", "IMAGENAME eq Deezer.exe", "/NH"]
        res = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=4)
        return "deezer.exe" in res.stdout.lower()
    except Exception:
        return False


# ─── DEEZER-CTL (WinRT SMTC) ──────────────────────────────────────────────────

def deezer_send_command(action: str) -> bool:
    """Envoie une commande de contrôle média direct (WinRT SMTC) à Deezer Desktop via deezer-ctl.
    Cette commande n'affecte QUE Deezer, même si une vidéo YouTube ou un autre lecteur est actif.
    Actions supportées : 'playpause', 'play', 'pause', 'next', 'prev', 'previous', 'toggle'.
    """
    # 1. Tentative d'import direct du module Python de deezer-ctl
    if DEEZER_CTL_DIR.exists():
        str_ctl_dir = str(DEEZER_CTL_DIR)
        if str_ctl_dir not in sys.path:
            sys.path.insert(0, str_ctl_dir)
        try:
            import deezer_ctl  # type: ignore
            res = deezer_ctl.send_command(action)
            if res:
                return True
        except Exception as e:
            print(f"[deezer-ctl Python] Erreur: {e}")

    # 2. Exécution directe des exécutables compilés dans bin/
    action_clean = (action or "playpause").lower().strip()
    if action_clean in ("next",):
        exe_name, arg = "deezer-next.exe", "next"
    elif action_clean in ("prev", "previous"):
        exe_name, arg = "deezer-prev.exe", "prev"
    else:
        exe_name, arg = "deezer-playpause.exe", "playpause"

    exe_path = DEEZER_CTL_BIN / exe_name
    if not exe_path.exists():
        exe_path = DEEZER_CTL_BIN / "deezer-playpause.exe"

    if exe_path.exists():
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            proc = subprocess.run(
                [str(exe_path), arg],
                startupinfo=startupinfo,
                capture_output=True,
                text=True,
                timeout=5
            )
            return proc.returncode == 0
        except Exception as ex:
            print(f"[deezer-ctl EXE] Erreur: {ex}")

    return False


def deezer_play_pause() -> Dict[str, Any]:
    """Bascule entre lecture et pause sur Deezer Desktop."""
    success = deezer_send_command("playpause")
    return {
        "status": "success" if success else "warning",
        "action": "playpause",
        "app": "Deezer",
        "message": "Lecture / Pause basculée sur Deezer." if success else "Commande envoyée à Deezer."
    }


def deezer_play() -> Dict[str, Any]:
    """Reprend ou lance la lecture sur Deezer Desktop."""
    if not is_deezer_running():
        launch_deezer()
        import time; time.sleep(1.0)
    success = deezer_send_command("play")
    return {
        "status": "success" if success else "completed",
        "action": "play",
        "app": "Deezer",
        "message": "Lecture Deezer lancée."
    }


def deezer_pause() -> Dict[str, Any]:
    """Met la musique en pause sur Deezer Desktop."""
    success = deezer_send_command("pause")
    return {
        "status": "success" if success else "completed",
        "action": "pause",
        "app": "Deezer",
        "message": "Deezer mis en pause."
    }


def deezer_next() -> Dict[str, Any]:
    """Passe au morceau suivant sur Deezer Desktop."""
    success = deezer_send_command("next")
    return {
        "status": "success" if success else "completed",
        "action": "next",
        "app": "Deezer",
        "message": "Morceau suivant sur Deezer."
    }


def deezer_prev() -> Dict[str, Any]:
    """Revient au morceau précédent sur Deezer Desktop."""
    success = deezer_send_command("prev")
    return {
        "status": "success" if success else "completed",
        "action": "previous",
        "app": "Deezer",
        "message": "Morceau précédent sur Deezer."
    }


# ─── RECHERCHE & SÉLECTION MUSICALE (API DEEZER PUBLIQUE) ──────────────────────

async def search_deezer(query: str, search_type: str = "track", limit: int = 5) -> List[Dict[str, Any]]:
    """Recherche des morceaux, albums, artistes ou playlists via l'API publique Deezer."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    st = search_type.lower()
    if st in ("album", "albums"):
        endpoint = "https://api.deezer.com/search/album"
    elif st in ("playlist", "playlists"):
        endpoint = "https://api.deezer.com/search/playlist"
    elif st in ("artist", "artiste", "artists"):
        endpoint = "https://api.deezer.com/search/artist"
    else:
        endpoint = "https://api.deezer.com/search"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=DEEZER_HEADERS) as client:
            resp = await client.get(endpoint, params={"q": clean_q, "limit": limit})
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                results = []
                for item in data:
                    item_id = item.get("id")
                    title = item.get("title") or item.get("name") or "Inconnu"
                    artist_obj = item.get("artist") or {}
                    artist_name = artist_obj.get("name") if isinstance(artist_obj, dict) else ""
                    album_obj = item.get("album") or {}
                    album_title = album_obj.get("title") if isinstance(album_obj, dict) else ""
                    cover = album_obj.get("cover_medium") if isinstance(album_obj, dict) else (item.get("picture_medium") or "")

                    results.append({
                        "id": item_id,
                        "title": title,
                        "artist": artist_name,
                        "album": album_title,
                        "type": item.get("type", search_type),
                        "duration": item.get("duration", 0),
                        "link": item.get("link", f"https://www.deezer.com/{search_type}/{item_id}"),
                        "deeplink": f"deezer://{item.get('type', search_type)}/{item_id}",
                        "cover": cover,
                        "preview": item.get("preview", "")
                    })
                return results
    except Exception as e:
        print(f"[Deezer API] Erreur recherche : {e}")

    return []


# ─── LANCEMENT & CONTRÔLE COMPLET DEEZER ──────────────────────────────────────

def launch_deezer(query: str = "") -> Dict[str, Any]:
    """Ouvre Deezer Desktop. Si query est fourni, ouvre la recherche via deeplink."""
    exe = _find_exe(DEEZER_PATHS)

    try:
        if exe:
            subprocess.Popen([exe], shell=False)
            import time; time.sleep(0.8)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", "deezer://"], shell=False)
            import time; time.sleep(0.8)

        msg = "Deezer est ouvert sur votre écran."

        if query:
            deeplink = "deezer://www.deezer.com/search/" + query.replace(" ", "%20")
            try:
                subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)
                msg = f"Deezer ouvert et recherche lancée pour : {query}"
            except Exception:
                msg = f"Deezer ouvert. Recherche suggérée : {query}"

        return {
            "status": "launched",
            "app": "Deezer",
            "query": query,
            "exe_found": bool(exe),
            "message": msg
        }
    except Exception as e:
        return {
            "status": "error",
            "app": "Deezer",
            "message": f"Impossible de lancer Deezer : {e}"
        }


async def play_deezer_track(track_query: str = "", item_type: str = "track") -> Dict[str, Any]:
    """Lance Deezer et démarre la lecture précise d'un morceau, album, playlist ou artiste.
    1. Recherche le meilleur résultat via l'API Deezer.
    2. Ouvre le contenu directement dans Deezer Desktop via le protocole URI 'deezer://'.
    3. Envoie la commande de lecture pour s'assurer que la musique démarre immédiatement.
    """
    clean_q = (track_query or "").strip()
    if not clean_q:
        # Sans requête, on démarre Deezer ou on relance la lecture
        if not is_deezer_running():
            return launch_deezer()
        return deezer_play()

    # 1. Recherche du contenu
    items = await search_deezer(clean_q, search_type=item_type, limit=5)
    best_item = items[0] if items else None

    # Si non trouvé en track, chercher sans type spécifique
    if not best_item and item_type != "track":
        items = await search_deezer(clean_q, search_type="track", limit=5)
        best_item = items[0] if items else None

    exe = _find_exe(DEEZER_PATHS)

    # Vérifier si Deezer Desktop doit être démarré
    if not is_deezer_running():
        if exe:
            subprocess.Popen([exe], shell=False)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", "deezer://"], shell=False)
        await asyncio.sleep(1.2)

    if best_item:
        item_id = best_item["id"]
        found_type = best_item.get("type", "track")
        deeplink = f"deezer://{found_type}/{item_id}"
        web_link = best_item.get("link", f"https://www.deezer.com/{found_type}/{item_id}")

        # Ouvrir le lien profond dans Deezer Desktop
        try:
            if exe:
                subprocess.Popen([exe, deeplink], shell=False)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)
        except Exception:
            subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)

        # Attendre un bref instant pour que Deezer charge la page du morceau, puis forcer Play
        await asyncio.sleep(0.8)
        deezer_send_command("play")

        title = best_item.get("title", clean_q)
        artist = best_item.get("artist", "")
        artist_str = f" par {artist}" if artist else ""
        album = best_item.get("album", "")
        album_str = f" (Album : {album})" if album else ""

        return {
            "status": "playing",
            "app": "Deezer",
            "query": clean_q,
            "track": best_item,
            "title": title,
            "artist": artist,
            "album": album,
            "deeplink": deeplink,
            "web_link": web_link,
            "cover": best_item.get("cover", ""),
            "message": f"Lecture de '{title}'{artist_str}{album_str} lancée sur Deezer Desktop."
        }
    else:
        # Repli : ouvrir la recherche globale dans Deezer
        deeplink = "deezer://www.deezer.com/search/" + clean_q.replace(" ", "%20")
        subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)
        await asyncio.sleep(0.5)
        deezer_send_command("play")

        return {
            "status": "playing",
            "app": "Deezer",
            "query": clean_q,
            "deeplink": deeplink,
            "message": f"Deezer ouvert sur la recherche : '{clean_q}'."
        }


async def control_deezer(action: str = "playpause", query: str = "", item_type: str = "track") -> Dict[str, Any]:
    """Point d'entrée universel pour le contrôle complet (100%) de Deezer Desktop.
    Actions :
    - 'play', 'resume', 'reprendre' : reprend ou démarre la lecture (ou joue query si fourni)
    - 'pause', 'stop', 'arreter' : met en pause
    - 'playpause', 'toggle', 'basculer' : bascule lecture / pause
    - 'next', 'suivant' : morceau suivant
    - 'prev', 'previous', 'precedent' : morceau précédent
    - 'choose', 'select', 'choisir', 'jouer', 'search' : choisit et joue un morceau/artiste/album précis
    - 'open', 'launch', 'ouvrir' : ouvre l'application Deezer Desktop
    - 'info', 'rechercher' : recherche et renvoie les détails de musique sans lancer immédiatement
    """
    act = (action or "playpause").lower().strip()

    if act in ("pause", "stop", "arreter", "arrête", "pause_music"):
        return deezer_pause()

    elif act in ("play", "reprendre", "resume", "lecture"):
        if query:
            return await play_deezer_track(track_query=query, item_type=item_type)
        return deezer_play()

    elif act in ("playpause", "toggle", "basculer"):
        return deezer_play_pause()

    elif act in ("next", "suivant", "next_track"):
        return deezer_next()

    elif act in ("prev", "previous", "precedent", "précédent", "prev_track"):
        return deezer_prev()

    elif act in ("choose", "select", "choisir", "jouer", "search", "track", "album", "playlist", "artist"):
        return await play_deezer_track(track_query=query, item_type=item_type)

    elif act in ("open", "launch", "ouvrir"):
        return launch_deezer(query=query)

    elif act in ("info", "search_info", "rechercher"):
        results = await search_deezer(query=query, search_type=item_type, limit=5)
        return {
            "status": "success",
            "query": query,
            "count": len(results),
            "results": results,
            "message": f"{len(results)} résultats trouvés sur Deezer pour '{query}'."
        }

    else:
        # Par défaut : si query est fourni, jouer la musique, sinon toggle playpause
        if query:
            return await play_deezer_track(track_query=query, item_type=item_type)
        return deezer_play_pause()



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