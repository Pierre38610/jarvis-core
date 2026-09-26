"""J.A.R.V.I.S. Local Relay Agent - Stark Industries PC Companion
Ce script s'exécute en arrière-plan sur votre PC Windows.
Il se connecte via WebSocket sécurisé à votre serveur Jarvis sur le VPS.
Lorsque Jarvis sur le Cloud reçoit un ordre d'ouvrir une application (VS Code, VLC, Deezer, etc.),
d'ouvrir une page web, ou de contrôler le lecteur audio, cet agent l'exécute instantanément sur votre écran physique.
"""

import os
import sys
import json
import time
import asyncio
import subprocess
import webbrowser
from typing import Dict, Any

# Forcer l'encodage UTF-8 dans la console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import psutil
import websockets
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

HOSTNAME = os.environ.get("CLOUDFLARE_HOSTNAME", "jarvis.signalcraftapps.com").strip()
PASSWORD = os.environ.get("JARVIS_PASSWORD", "Bonjourmotdepassedu52..").strip()

# Détection Chrome Windows
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
CHROME_PATH = next((p for p in CHROME_PATHS if os.path.exists(p)), None)

# Applications locales autorisées
ALLOWED_APPS = {
    # Utilitaires Windows
    "calculatrice": "calc.exe",
    "calc": "calc.exe",
    "bloc-notes": "notepad.exe",
    "notepad": "notepad.exe",
    "explorateur": "explorer.exe",
    "fichiers": "explorer.exe",
    "explorer": "explorer.exe",
    "mes fichiers": "explorer.exe",
    # Développement
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    # Navigateur
    "chrome": CHROME_PATH or "chrome.exe",
    "google chrome": CHROME_PATH or "chrome.exe",
    "navigateur": CHROME_PATH or "chrome.exe",
    "browser": CHROME_PATH or "chrome.exe",
    # Terminal
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "invite de commandes": "cmd.exe",
    "powershell": "powershell.exe",
    # Multimédia
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "spotify": r"C:\Users\pierr\AppData\Roaming\Spotify\Spotify.exe",
    # Office
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "taskmgr": "taskmgr.exe",
    "gestionnaire": "taskmgr.exe",
    "gestionnaire des taches": "taskmgr.exe",
    "parametres": "ms-settings:",
    "settings": "ms-settings:",
}

STREMIO_PATHS = [
    r"C:\Users\pierr\AppData\Local\Programs\LNV\Stremio 5\Stremio.exe",
    r"C:\Users\pierr\AppData\Local\Programs\Stremio\Stremio.exe",
    r"C:\Program Files\Stremio\Stremio.exe",
    r"C:\Program Files (x86)\Stremio\Stremio.exe",
]
VLC_PATH = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def get_local_metrics() -> Dict[str, Any]:
    """Lit l'état matériel du PC Windows (CPU, RAM, batterie)."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        bat = psutil.sensors_battery()
        bat_str = "Secteur"
        if bat:
            bat_str = f"{bat.percent}% ({'En charge' if bat.power_plugged else 'Sur batterie'})"
        return {
            "status": "success",
            "cpu_percent": f"{cpu}%",
            "ram_usage": f"{round((mem.total - mem.available) / (1024**3), 1)} Go / {round(mem.total / (1024**3), 1)} Go ({mem.percent}%)",
            "battery": bat_str,
            "machine": os.environ.get("COMPUTERNAME", "PC Pierre"),
            "summary": f"PC Pierre : Processeur à {cpu}%, RAM {mem.percent}%, Batterie: {bat_str}."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def execute_open_browser(url: str, load_extensions: bool = True) -> Dict[str, Any]:
    """Ouvre une URL directement dans Google Chrome ou le navigateur par défaut sur l'écran."""
    target = (url or "").strip()
    if not target:
        target = "https://www.google.com"
    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target

    try:
        if CHROME_PATH and os.path.exists(CHROME_PATH):
            subprocess.Popen([CHROME_PATH, target], shell=False)
        else:
            webbrowser.open(target)
        return {
            "status": "success",
            "url": target,
            "message": f"Page '{target}' ouverte avec succès sur votre écran d'ordinateur."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Impossible d'ouvrir le navigateur sur '{target}' : {e}"
        }


def execute_open_browsers(urls: list, load_extensions: bool = True) -> Dict[str, Any]:
    """Ouvre plusieurs URLs directement dans des onglets Google Chrome sur l'écran Windows."""
    clean_urls = []
    for u in urls:
        target = (u or "").strip()
        if target:
            if not target.startswith("http://") and not target.startswith("https://"):
                target = "https://" + target
            clean_urls.append(target)

    if not clean_urls:
        clean_urls = ["https://www.google.com"]

    try:
        if CHROME_PATH and os.path.exists(CHROME_PATH):
            subprocess.Popen([CHROME_PATH, *clean_urls], shell=False)
        else:
            for target in clean_urls:
                webbrowser.open_new_tab(target)
        return {
            "status": "success",
            "urls": clean_urls,
            "message": f"{len(clean_urls)} onglet(s) de réservation ouvert(s) avec succès dans Google Chrome."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Impossible d'ouvrir le navigateur pour les onglets : {e}"
        }


def execute_local_app(app_name: str) -> Dict[str, Any]:
    """Lance une application sur l'écran Windows."""
    name_clean = (app_name or "").strip().lower()

    if "deezer" in name_clean:
        return execute_media_action({"app": "deezer", "query": ""})

    if "stremio" in name_clean:
        return execute_media_action({"app": "stremio"})

    if "vlc" in name_clean:
        return execute_media_action({"app": "vlc"})

    if any(k in name_clean for k in ["chrome", "navigateur", "browser"]):
        return execute_open_browser("https://www.google.com")

    target_cmd = None
    for key, cmd in ALLOWED_APPS.items():
        if key in name_clean and cmd:
            target_cmd = cmd
            break

    if not target_cmd:
        safe_names = ["mspaint", "taskmgr", "write", "notepad", "calc"]
        for s in safe_names:
            if s in name_clean:
                target_cmd = f"{s}.exe"
                break

    if not target_cmd:
        target_cmd = name_clean

    try:
        subprocess.Popen(f'start "" {target_cmd}', shell=True)
        return {
            "status": "success",
            "app": app_name,
            "message": f"Application '{app_name}' lancée avec succès sur votre écran d'ordinateur."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Impossible de lancer '{app_name}' : {e}"
        }


def execute_media_action(params: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute une action multimédia locale (Deezer, Stremio, VLC)."""
    app = params.get("app", "").lower()
    query = params.get("query", "")
    target = params.get("target", "")
    stremio_id = params.get("stremio_id", "")
    content_type = params.get("content_type", "movie")

    try:
        if "deezer" in app:
            url = f"https://www.deezer.com/search/{query}" if query else "https://www.deezer.com"
            webbrowser.open(url)
            return {"status": "success", "message": f"Deezer ouvert dans votre navigateur sur : {url}"}

        elif "stremio" in app:
            exe = None
            for p in STREMIO_PATHS:
                if os.path.exists(p):
                    exe = p
                    break
            cat = "series" if content_type in ("series", "serie", "tv") else "movie"
            deeplink = f"stremio:///detail/{cat}/{stremio_id}" if stremio_id else "stremio://"
            if exe:
                subprocess.Popen([exe, deeplink], shell=False)
            else:
                subprocess.Popen(["cmd", "/c", "start", "", deeplink], shell=False)
            return {"status": "success", "message": "Stremio ouvert sur votre écran."}

        elif "vlc" in app:
            if os.path.exists(VLC_PATH):
                args = [VLC_PATH]
                if target:
                    args.append(target)
                subprocess.Popen(args, shell=False)
                return {"status": "success", "message": "VLC lancé sur votre écran."}
            else:
                subprocess.Popen(["cmd", "/c", "start", "vlc", target], shell=True)
                return {"status": "success", "message": "VLC lancé sur votre écran."}

        return {"status": "error", "message": f"Application média '{app}' non supportée."}
    except Exception as e:
        return {"status": "error", "message": f"Erreur média : {e}"}


async def execute_deezer_action(params: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute une action de contrôle Deezer via le bridge WebSocket local."""
    try:
        from deezer_bridge import deezer_controller
        action = params.get("action", "playpause")
        query = params.get("query", "")
        item_type = params.get("item_type", "track")
        volume = params.get("volume")
        enable = params.get("enable")
        seek_pos = params.get("position")

        res = await deezer_controller.control_deezer(
            action=action,
            query=query,
            item_type=item_type,
            volume=volume,
            enable=enable,
            position=seek_pos
        )
        return res
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erreur lors du contrôle Deezer local : {e}"
        }


async def send_telemetry_loop(ws):
    """Envoie l'état matériel du PC et l'état Deezer toutes les 30 secondes au serveur."""
    try:
        while True:
            metrics = get_local_metrics()
            payload = {"type": "telemetry", "data": metrics}
            await ws.send(json.dumps(payload))

            # Remonter l'état Deezer si disponible
            try:
                from deezer_bridge import deezer_controller
                if deezer_controller.is_connected() or deezer_controller.last_status:
                    await ws.send(json.dumps({
                        "type": "deezer_status",
                        "data": deezer_controller.last_status
                    }))
            except Exception:
                pass

            await asyncio.sleep(30)
    except Exception:
        pass


async def agent_loop():
    """Boucle principale de maintien de la connexion WebSocket avec Jarvis VPS."""
    uri = f"wss://{HOSTNAME}/ws/local-agent?token={PASSWORD}"

    print("=" * 70, flush=True)
    print("       ✦  J . A . R . V . I . S .   L O C A L   A G E N T  ✦", flush=True)
    print("                 STARK INDUSTRIES PC COMPANION", flush=True)
    print("=" * 70, flush=True)
    print(f"[*] Cible Cloud      : wss://{HOSTNAME}/ws/local-agent", flush=True)

    # 1. Démarrage du bridge Deezer local pour écouter le Userscript Tampermonkey sur ws://127.0.0.1:8765
    try:
        from deezer_bridge import deezer_controller
        await deezer_controller.start()
        print("[✔] Deezer Bridge    : Actif sur ws://127.0.0.1:8765 (Tampermonkey prêt)", flush=True)
    except Exception as e:
        print(f"[!] Deezer Bridge    : Note ({e})", flush=True)

    print("[*] En attente de synchronisation avec Jarvis Cloud...", flush=True)

    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=15) as ws:
                print(f"\n[✔] CONNECTÉ À JARVIS CLOUD ({HOSTNAME}) !", flush=True)
                print("[*] Votre PC est synchronisé : prêt à ouvrir des applications, pages web et contrôler Deezer.\n", flush=True)

                # Lance l'envoi périodique de métriques
                telemetry_task = asyncio.create_task(send_telemetry_loop(ws))

                async for message in ws:
                    try:
                        data = json.loads(message)
                        req_id = data.get("req_id")
                        action = data.get("action")
                        params = data.get("params", {})

                        print(f"\n[ORDRE REÇU DU CLOUD] Action: '{action}' | Params: {params}", flush=True)

                        result = {}
                        if action == "launch_app":
                            app_name = params.get("app_name", "")
                            result = execute_local_app(app_name)
                        elif action == "open_browser":
                            url = params.get("url", "")
                            load_ext = params.get("load_extensions", True)
                            result = execute_open_browser(url, load_extensions=load_ext)
                        elif action == "launch_media":
                            result = execute_media_action(params)
                        elif action == "deezer_action":
                            result = await execute_deezer_action(params)
                        elif action == "prepare_train_checkout":
                            urls = params.get("urls") or ([params.get("url")] if params.get("url") else [])
                            operateur = params.get("operateur", "sncf")
                            open_res = execute_open_browsers(urls, load_extensions=True)
                            n_trains = len(urls)
                            label_trains = f"{n_trains} billets de train ({operateur.upper()})" if n_trains > 1 else f"Trajet {operateur.upper()}"
                            result = {
                                "status": open_res.get("status", "success"),
                                "operateur": operateur,
                                "urls": urls,
                                "message": f"{label_trains} ouvert(s) dans Chrome sur votre écran Windows. Vos trajets sont préremplis, il ne vous reste plus qu'à sélectionner vos places/couchettes et finaliser l'achat en toute sécurité."
                            }
                        elif action == "prepare_web_cart_or_checkout":
                            try:
                                from services.browser_service import prepare_web_cart_or_checkout
                                result = await prepare_web_cart_or_checkout(
                                    product_or_service=params.get("product_or_service", ""),
                                    merchant_url=params.get("merchant_url", ""),
                                    autofill_details=params.get("autofill_details"),
                                    open_when_ready=params.get("open_when_ready", True),
                                    execution_target="local_gui",
                                    _is_local_relay=True
                                )
                            except Exception as e:
                                result = {"status": "error", "message": f"Erreur prepare_web_cart_or_checkout local : {e}"}
                        elif action == "interact_web_page":
                            try:
                                from services.browser_service import interact_web_page
                                result = await interact_web_page(
                                    url=params.get("url", ""),
                                    action=params.get("action", "read"),
                                    selector=params.get("selector", ""),
                                    text_to_fill=params.get("text_to_fill", ""),
                                    actions_list=params.get("actions_list"),
                                    wait_seconds=params.get("wait_seconds", 2.0),
                                    execution_target="local_gui"
                                )
                            except Exception as e:
                                result = {"status": "error", "message": f"Erreur interact_web_page local : {e}"}
                        elif action == "get_status":
                            result = get_local_metrics()
                        else:
                            result = {"status": "error", "message": f"Action inconnue : {action}"}

                        print(f"  -> Résultat : {result.get('message', result.get('status'))}", flush=True)

                        # Répond au VPS
                        response = {
                            "req_id": req_id,
                            "type": "response",
                            "result": result
                        }
                        await ws.send(json.dumps(response))
                    except Exception as e:
                        print(f"[!] Erreur traitement commande : {e}", flush=True)

                telemetry_task.cancel()

        except (websockets.ConnectionClosed, websockets.InvalidStatusCode) as e:
            print(f"[!] Déconnecté ({e}). Reconnexion automatique dans 5 secondes...", flush=True)
        except Exception as e:
            print(f"[!] Erreur réseau ({e}). Reconnexion automatique dans 5 secondes...", flush=True)

        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(agent_loop())
    except KeyboardInterrupt:
        print("\n[*] Arrêt de l'agent local.", flush=True)
