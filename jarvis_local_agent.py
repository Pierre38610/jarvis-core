"""J.A.R.V.I.S. Local Relay Agent - Stark Industries PC Companion
Ce script s'exécute en arrière-plan sur votre PC Windows.
Il se connecte via WebSocket sécurisé à votre serveur Jarvis sur le VPS.
Lorsque Jarvis sur le Cloud reçoit un ordre d'ouvrir une application (VS Code, VLC, Deezer, etc.),
cet agent l'exécute instantanément sur l'écran physique de votre ordinateur.
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
    # Développement
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    # Navigateur
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    # Terminal
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
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


def execute_local_app(app_name: str) -> Dict[str, Any]:
    """Lance une application sur l'écran Windows."""
    name_clean = (app_name or "").strip().lower()

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
        subprocess.Popen(target_cmd, shell=True)
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


async def send_telemetry_loop(ws):
    """Envoie l'état matériel du PC toutes les 30 secondes au serveur."""
    try:
        while True:
            metrics = get_local_metrics()
            payload = {"type": "telemetry", "data": metrics}
            await ws.send(json.dumps(payload))
            await asyncio.sleep(30)
    except Exception:
        pass


async def agent_loop():
    """Boucle principale de maintien de la connexion WebSocket avec Jarvis VPS."""
    uri = f"wss://{HOSTNAME}/ws/local-agent?token={PASSWORD}"
    
    print("=" * 70)
    print("       ✦  J . A . R . V . I . S .   L O C A L   A G E N T  ✦")
    print("                 STARK INDUSTRIES PC COMPANION")
    print("=" * 70)
    print(f"[*] Cible Cloud : wss://{HOSTNAME}/ws/local-agent")
    print("[*] En attente de connexion...")

    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=15) as ws:
                print(f"[✔] Connecté à Jarvis Cloud ({HOSTNAME}) ! Votre PC est synchronisé.")
                
                # Lance l'envoi périodique de métriques
                telemetry_task = asyncio.create_task(send_telemetry_loop(ws))

                async for message in ws:
                    try:
                        data = json.loads(message)
                        req_id = data.get("req_id")
                        action = data.get("action")
                        params = data.get("params", {})

                        print(f"\n[COMMANDE REÇUE] Action: '{action}' | Params: {params}")

                        result = {}
                        if action == "launch_app":
                            app_name = params.get("app_name", "")
                            result = execute_local_app(app_name)
                        elif action == "launch_media":
                            result = execute_media_action(params)
                        elif action == "get_status":
                            result = get_local_metrics()
                        else:
                            result = {"status": "error", "message": f"Action inconnue : {action}"}

                        print(f"  -> Résultat : {result.get('message', result.get('status'))}")

                        # Répond au VPS
                        response = {
                            "req_id": req_id,
                            "type": "response",
                            "result": result
                        }
                        await ws.send(json.dumps(response))
                    except Exception as e:
                        print(f"[!] Erreur traitement commande : {e}")

                telemetry_task.cancel()

        except (websockets.ConnectionClosed, websockets.InvalidStatusCode) as e:
            print(f"[!] Déconnecté ({e}). Reconnexion dans 5 secondes...")
        except Exception as e:
            print(f"[!] Erreur réseau ({e}). Reconnexion dans 5 secondes...")

        await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(agent_loop())
    except KeyboardInterrupt:
        print("\n[*] Arrêt de l'agent local.")
