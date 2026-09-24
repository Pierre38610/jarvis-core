"""Service de contrôle et métriques système pour J.A.R.V.I.S."""

import os
import subprocess
import psutil
from typing import Dict, Any

# Applications locales autorisées
ALLOWED_APPS = {
    "calculatrice": "calc.exe",
    "calc": "calc.exe",
    "bloc-notes": "notepad.exe",
    "notepad": "notepad.exe",
    "explorateur": "explorer.exe",
    "fichiers": "explorer.exe",
    "code": "code",
    "vscode": "code",
    "chrome": "chrome",
    "terminal": "wt.exe",
    "cmd": "cmd.exe"
}

def get_system_status() -> Dict[str, Any]:
    """Retourne l'état en temps réel des ressources du système (CPU, RAM, batterie)."""
    try:
        cpu_usage = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        ram_used_gb = round((mem.total - mem.available) / (1024 ** 3), 1)
        ram_total_gb = round(mem.total / (1024 ** 3), 1)
        
        battery = psutil.sensors_battery()
        battery_info = None
        if battery:
            battery_info = {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged
            }

        return {
            "status": "success",
            "cpu_percent": f"{cpu_usage}%",
            "ram_usage": f"{ram_used_gb} Go / {ram_total_gb} Go ({mem.percent}%)",
            "battery": f"{battery.percent}% ({'En charge' if battery.power_plugged else 'Sur batterie'})" if battery else "Secteur",
            "summary": f"Processeur à {cpu_usage}%, RAM utilisée à {mem.percent}% ({ram_used_gb}/{ram_total_gb} Go)."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erreur lecture système: {str(e)}"
        }

def launch_application(app_name: str) -> Dict[str, Any]:
    """Ouvre une application locale sur la machine de l'utilisateur."""
    name_clean = (app_name or "").strip().lower()
    target_cmd = None
    for key, cmd in ALLOWED_APPS.items():
        if key in name_clean:
            target_cmd = cmd
            break

    if not target_cmd:
        # Tentative d'exécution directe si commande simple sans caractères dangereux
        if name_clean in ["mspaint", "taskmgr", "write"]:
            target_cmd = f"{name_clean}.exe"

    if not target_cmd:
        return {
            "status": "error",
            "message": f"Application '{app_name}' non reconnue dans la liste sécurisée ({', '.join(ALLOWED_APPS.keys())})."
        }

    try:
        subprocess.Popen(target_cmd, shell=True)
        return {
            "status": "success",
            "app": app_name,
            "message": f"Application {app_name} lancée avec succès sur votre écran."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Impossible de lancer {app_name}: {str(e)}"
        }
