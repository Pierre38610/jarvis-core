"""Service de controle et metriques systeme pour J.A.R.V.I.S."""

import os
import subprocess
import psutil
from typing import Dict, Any

# Applications locales autorisees - liste etendue avec medias et outils modernes
ALLOWED_APPS = {
    # Utilitaires Windows
    "calculatrice": "calc.exe",
    "calc": "calc.exe",
    "bloc-notes": "notepad.exe",
    "notepad": "notepad.exe",
    "explorateur": "explorer.exe",
    "fichiers": "explorer.exe",
    "explorer": "explorer.exe",
    # Developpement
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
    # Multimedia
    "deezer": None,   # Gere par media_service.launch_deezer()
    "stremio": None,  # Gere par media_service.launch_stremio()
    "vlc": r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "spotify": r"C:\Users\pierr\AppData\Roaming\Spotify\Spotify.exe",
    # Office / Productivite
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "taskmgr": "taskmgr.exe",
    "gestionnaire": "taskmgr.exe",
    "gestionnaire des taches": "taskmgr.exe",
    "write": "write.exe",
}

MEDIA_APPS = {"deezer", "stremio"}


def is_local_pc_online() -> bool:
    """Indique si le PC local de Pierre est allumé et connecté."""
    from services.local_agent_service import is_pc_connected
    return is_pc_connected()


def get_system_status() -> Dict[str, Any]:
    try:
        from services.local_agent_service import local_agent_service
        if local_agent_service.is_connected() and local_agent_service._last_pc_status:
            return local_agent_service._last_pc_status
    except Exception:
        pass

    try:
        cpu_usage = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        ram_used_gb = round((mem.total - mem.available) / (1024 ** 3), 1)
        ram_total_gb = round(mem.total / (1024 ** 3), 1)

        battery = psutil.sensors_battery()
        battery_str = "Secteur (pas de batterie)"
        if battery:
            battery_str = f"{battery.percent}% ({'En charge' if battery.power_plugged else 'Sur batterie'})"

        # Processus actifs notables
        notable = []
        for p in psutil.process_iter(["name", "cpu_percent"]):
            try:
                n = p.info["name"] or ""
                if any(k in n.lower() for k in ["chrome", "code", "python", "stremio", "deezer", "spotify"]):
                    notable.append(n)
            except Exception:
                pass

        return {
            "status": "success",
            "cpu_percent": f"{cpu_usage}%",
            "ram_usage": f"{ram_used_gb} Go / {ram_total_gb} Go ({mem.percent}%)",
            "battery": battery_str,
            "active_apps": list(set(notable))[:8],
            "summary": f"Processeur a {cpu_usage}%, RAM utilisee a {mem.percent}% ({ram_used_gb}/{ram_total_gb} Go)."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erreur lecture systeme: {str(e)}"
        }


def launch_application(app_name: str) -> Dict[str, Any]:
    """Ouvre une application locale. Les apps media (Deezer, Stremio) sont gerees
    via media_service pour un lancement intelligent."""
    name_clean = (app_name or "").strip().lower()

    # Detection applications media -> redirection vers media_service
    for media_key in MEDIA_APPS:
        if media_key in name_clean:
            return {
                "status": "redirect_media",
                "app": media_key,
                "message": f"Utilise l'outil media dedie pour lancer {media_key.capitalize()}."
            }

    # Recherche dans la liste autorisee
    target_cmd = None
    for key, cmd in ALLOWED_APPS.items():
        if key in name_clean and cmd:
            target_cmd = cmd
            break

    # Tentative directe pour les .exe simples
    if not target_cmd:
        safe_names = ["mspaint", "taskmgr", "write", "notepad", "calc"]
        for s in safe_names:
            if s in name_clean:
                target_cmd = f"{s}.exe"
                break

    if not target_cmd:
        return {
            "status": "error",
            "message": (
                f"Application '{app_name}' non reconnue. "
                f"Applications disponibles : {', '.join(k for k in ALLOWED_APPS.keys() if ALLOWED_APPS[k])}."
            )
        }

    # Delegation a l'Agent PC si sur Linux VPS ou si le PC de bureau est connecte
    try:
        import sys
        from services.local_agent_service import local_agent_service
        if sys.platform != "win32" or local_agent_service.is_connected():
            if not local_agent_service.is_connected():
                return {
                    "status": "pc_offline",
                    "app": app_name,
                    "message": (
                        f"Votre ordinateur personnel est actuellement éteint ou le script start_local_agent.bat n'est pas lancé. "
                        f"Impossible de lancer '{app_name}' sur votre écran physique pour le moment."
                    )
                }
            return local_agent_service.execute_command_sync("launch_app", timeout=12.0, app_name=app_name)
    except Exception as e:
        if sys.platform != "win32":
            return {"status": "error", "message": f"Erreur relais PC: {e}"}

    try:
        subprocess.Popen(target_cmd, shell=True)
        return {
            "status": "success",
            "app": app_name,
            "message": f"Application {app_name} lancee avec succes sur votre ecran."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Impossible de lancer {app_name}: {str(e)}"
        }


def get_running_processes() -> Dict[str, Any]:
    """Retourne la liste des processus importants actuellement en cours d execution."""
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                name = p.info["name"] or ""
                cpu = p.info["cpu_percent"] or 0
                mem_mb = round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024**2), 1)
                if cpu > 1 or mem_mb > 50:
                    procs.append({"name": name, "cpu_percent": cpu, "mem_mb": mem_mb})
            except Exception:
                pass
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
        return {"status": "success", "processes": procs[:15]}
    except Exception as e:
        return {"status": "error", "message": str(e)}