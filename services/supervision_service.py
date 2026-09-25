"""Service de supervision globale de J.A.R.V.I.S.
Gère le suivi en temps réel :
- Modèle vocal actif et clé API associée (gratuite vs payante)
- Actions et développements en cours d'exécution avec modèle et clé
- Outils actuellement sollicités et statut de leur API
- Fenêtres et applications ouvertes sur le système et le navigateur
- Synthèse des clés API et de leur consommation
"""

import os
import sys
import time
import ctypes
import psutil
from datetime import datetime
from typing import Dict, Any, List, Optional

import config

class SupervisionService:
    def __init__(self):
        self._actions: Dict[str, Dict[str, Any]] = {}
        self._recent_actions: List[Dict[str, Any]] = []
        self._active_tools: Dict[str, Dict[str, Any]] = {
            "gemini_live_voice": {
                "name": "Gemini Live Audio (Voix)",
                "tool": "gemini_live_voice",
                "model": config.GEMINI_LIVE_MODEL,
                "api_type": "free",
                "api_label": "Clé Gratuite",
                "cost_est": "0.00 $ (Plan Gratuit)",
                "active": False,
                "description": "Conversation vocale bidirectionnelle naturelle avec Aoede"
            },
            "run_antigravity_task": {
                "name": "Développement de Code Antigravity",
                "tool": "run_antigravity_task",
                "model": "Gemini 3.8 Flash (High)",
                "api_type": "paid",
                "api_label": "Clé Payante",
                "cost_est": "~0.005 $ à 0.03 $",
                "active": False,
                "description": "Agent autonome outillé modifiant le code du workspace"
            },
            "ask_deep_reasoning": {
                "name": "Raisonnement Approfondi (Thinking)",
                "tool": "ask_deep_reasoning",
                "model": "Gemini Thinking (Gratuite→Payante)",
                "api_type": "hybrid",
                "api_label": "Gratuite → Payante (repli)",
                "cost_est": "0.00 $ (Gratuite) / ~0.03 $ (Payante)",
                "active": False,
                "description": "Thinking: clé gratuite en priorité, repli payante si quota épuisé"
            },
            "run_browser_task": {
                "name": "Navigation Autonome Browser-Use",
                "tool": "run_browser_task",
                "model": "Gemini 3.6 Flash (Vision LLM)",
                "api_type": "paid",
                "api_label": "Clé Payante",
                "cost_est": "~0.02 $",
                "active": False,
                "description": "Exploration visuelle autonome de sites et formulaires"
            },
            "search_web": {
                "name": "Recherche Internet Directe",
                "tool": "search_web",
                "model": "Playwright / DuckDuckGo",
                "api_type": "free",
                "api_label": "Clé Gratuite",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Recherche web rapide d'informations et liens directs"
            },
            "send_email": {
                "name": "Transmission E-mail Stark",
                "tool": "send_email",
                "model": "SMTP Stark Protocol",
                "api_type": "free",
                "api_label": "Service Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Expédition de rapports et synthèses par courriel"
            },
            "open_user_browser": {
                "name": "Affichage Chrome Utilisateur",
                "tool": "open_user_browser",
                "model": "Système OS Local",
                "api_type": "local",
                "api_label": "Système Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Ouverture d'une fenêtre de navigateur réelle à l'écran"
            },
            "get_system_status": {
                "name": "Diagnostic Système",
                "tool": "get_system_status",
                "model": "Système OS Local",
                "api_type": "local",
                "api_label": "Système Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Surveillance CPU, RAM et batterie en temps réel"
            },
            "launch_application": {
                "name": "Lancement d'Application",
                "tool": "launch_application",
                "model": "Système OS Local",
                "api_type": "local",
                "api_label": "Système Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Démarrage d'outils Windows (VS Code, Calculatrice...)"
            },
            "remember_user_fact": {
                "name": "Mémoire Persistante SQLite",
                "tool": "remember_user_fact",
                "model": "SQLite Local",
                "api_type": "local",
                "api_label": "Système Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Mémorisation et rappel des faits et préférences"
            },
            "check_console_errors": {
                "name": "Diagnostic Console & Auto-résolution",
                "tool": "check_console_errors",
                "model": "Analyseur Local",
                "api_type": "local",
                "api_label": "Système Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Inspection des erreurs d'exécution et auto-correction"
            },
            "interact_web_page": {
                "name": "Interaction & Formulaires Web",
                "tool": "interact_web_page",
                "model": "Playwright Automation Engine",
                "api_type": "free",
                "api_label": "Clé Gratuite / Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Lecture, saisie de formulaires et clics sur pages web"
            },
            "prepare_web_cart_or_checkout": {
                "name": "Préparation Panier & Préremplissage",
                "tool": "prepare_web_cart_or_checkout",
                "model": "Playwright E-Commerce Engine",
                "api_type": "free",
                "api_label": "Clé Gratuite / Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Création de panier, préremplissage coordonnées et ouverture Chrome pour paiement"
            },
            "download_file": {
                "name": "Téléchargement Sécurisé Fichiers",
                "tool": "download_file",
                "model": "Stark Transfer Protocol",
                "api_type": "free",
                "api_label": "Service Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Téléchargement de documents et ebooks avec accord oral préalable"
            },
            "send_to_ereader": {
                "name": "Acheminement Liseuse (Kindle/Kobo)",
                "tool": "send_to_ereader",
                "model": "USB / SMTP Protocol",
                "api_type": "free",
                "api_label": "Service Local",
                "cost_est": "0.00 $",
                "active": False,
                "description": "Transfert direct d'ebooks vers la liseuse par e-mail ou USB"
            }
        }
        self._tracked_windows: List[Dict[str, Any]] = []
        self._free_quota_exhausted: bool = False
        initial_is_paid = ("extended-thinking" in config.GEMINI_LIVE_MODEL) or not bool(config.GEMINI_API_KEY_FREE)
        initial_label = "Clé Payante" if initial_is_paid else "Clé Gratuite"
        initial_key = config.GEMINI_API_KEY_PAID if initial_is_paid else config.GEMINI_API_KEY_FREE
        self._voice_state: Dict[str, Any] = {
            "model": config.GEMINI_LIVE_MODEL,
            "display_label": "Gemini 3.8 Live (Thinking)" if "extended-thinking" in config.GEMINI_LIVE_MODEL else "Gemini 3.8 Live",
            "voice_name": config.JARVIS_VOICE,
            "api_type": "paid" if initial_is_paid else "free",
            "api_label": initial_label,
            "api_key_masked": self._mask_key(initial_key),
            "status": "offline",
            "is_paid": initial_is_paid
        }

    @staticmethod
    def _mask_key(key: str | None) -> str:
        if not key:
            return "Non configurée"
        s = key.strip()
        if len(s) <= 8:
            return "••••" + s[-4:]
        return f"{s[:4]}••••••••{s[-4:]}"

    def set_free_quota_exhausted(self, exhausted: bool = True):
        """Marque ou réinitialise l'état d'épuisement du quota de la clé gratuite."""
        self._free_quota_exhausted = exhausted

    def update_voice_state(self, status: str, model: str | None = None, is_paid: bool | None = None, api_label: str | None = None):
        """Met à jour l'état du canal vocal en direct."""
        if model:
            self._voice_state["model"] = model
            is_thinking = "extended-thinking" in model
            self._voice_state["display_label"] = "Gemini 3.8 Live (Thinking)" if is_thinking else "Gemini 3.8 Live"
            if is_paid is None:
                is_paid = is_thinking or self._free_quota_exhausted or not bool(config.GEMINI_API_KEY_FREE)

        if is_paid is not None:
            self._voice_state["is_paid"] = is_paid
            self._voice_state["api_type"] = "paid" if is_paid else "free"
            
        current_is_paid = self._voice_state["is_paid"]
        if api_label:
            self._voice_state["api_label"] = api_label
        else:
            self._voice_state["api_label"] = "Clé Payante" if current_is_paid else "Clé Gratuite"

        active_key = config.GEMINI_API_KEY_PAID if current_is_paid else config.GEMINI_API_KEY_FREE
        self._voice_state["api_key_masked"] = self._mask_key(active_key)
        self._voice_state["status"] = status
        
        # Outil voix en activité si parole ou écoute
        if status in ("speaking", "listening"):
            self._active_tools["gemini_live_voice"]["active"] = True
            self._active_tools["gemini_live_voice"]["model"] = self._voice_state["display_label"]
            self._active_tools["gemini_live_voice"]["api_type"] = self._voice_state["api_type"]
            self._active_tools["gemini_live_voice"]["api_label"] = self._voice_state["api_label"]
        else:
            self._active_tools["gemini_live_voice"]["active"] = False

    def start_action(
        self,
        action_id: str,
        name: str,
        tool: str,
        detail: str,
        model: str,
        api_type: str = "paid",
        api_label: str = "Clé Payante",
        cost_est: str = "~0.005 $"
    ) -> Dict[str, Any]:
        """Enregistre le démarrage d'une action lourde ou d'un processus."""
        now = datetime.now()
        action_data = {
            "id": action_id,
            "name": name,
            "tool": tool,
            "detail": detail,
            "model": model,
            "api_type": api_type,
            "api_label": api_label,
            "cost_est": cost_est,
            "status": "running",
            "progress_step": "Initialisation...",
            "progress_text": detail,
            "started_at": now.strftime("%H:%M:%S"),
            "start_timestamp": time.time()
        }
        self._actions[action_id] = action_data

        # Met à jour le registre d'outils
        if tool in self._active_tools:
            self._active_tools[tool]["active"] = True
            self._active_tools[tool]["model"] = model
            self._active_tools[tool]["api_type"] = api_type
            self._active_tools[tool]["api_label"] = api_label

        return action_data

    def update_action_progress(self, action_id: str, step: str, text: str, model: str | None = None):
        """Met à jour l'état de progression d'une action en cours."""
        if action_id in self._actions:
            self._actions[action_id]["progress_step"] = step
            self._actions[action_id]["progress_text"] = text
            if model:
                self._actions[action_id]["model"] = model
                tool = self._actions[action_id].get("tool")
                if tool and tool in self._active_tools:
                    self._active_tools[tool]["model"] = model

    def complete_action(self, action_id: str, status: str = "completed", summary: str = "", model: str | None = None):
        """Termine une action et la déplace dans l'historique récent."""
        if action_id in self._actions:
            act = self._actions.pop(action_id)
            act["status"] = status
            act["summary"] = summary
            if model:
                act["model"] = model
            act["completed_at"] = datetime.now().strftime("%H:%M:%S")
            duration_sec = round(time.time() - act.get("start_timestamp", time.time()), 1)
            act["duration"] = f"{duration_sec}s"
            self._recent_actions.insert(0, act)
            self._recent_actions = self._recent_actions[:8]

            # Libère l'outil si aucune autre action du même outil ne tourne
            tool = act.get("tool")
            if tool and tool in self._active_tools:
                still_running = any(a.get("tool") == tool for a in self._actions.values())
                if not still_running:
                    self._active_tools[tool]["active"] = False

    def track_browser_window(self, url: str, title: str = "Google Chrome"):
        """Enregistre une fenêtre ou un onglet ouvert par Jarvis."""
        now = datetime.now().strftime("%H:%M:%S")
        # Évite les doublons exacts
        self._tracked_windows = [w for w in self._tracked_windows if w.get("url") != url]
        self._tracked_windows.insert(0, {
            "title": title or "Navigation Web",
            "url": url,
            "process": "chrome.exe",
            "opened_by": "J.A.R.V.I.S.",
            "timestamp": now
        })
        self._tracked_windows = self._tracked_windows[:10]

    def get_open_windows(self) -> List[Dict[str, Any]]:
        """Enumère toutes les fenêtres ouvertes sur l'ordinateur de l'utilisateur."""
        desktop_windows: List[Dict[str, Any]] = []

        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                EnumWindows = user32.EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                GetWindowTextLengthW = user32.GetWindowTextLengthW
                GetWindowTextW = user32.GetWindowTextW
                IsWindowVisible = user32.IsWindowVisible
                GetWindowThreadProcessId = user32.GetWindowThreadProcessId

                seen_titles = set()
                excluded = {
                    "Program Manager", "Settings", "Default IME", "MSCTFIME UI",
                    "Windows Shell Experience Host", "Task Switching", "Cortana"
                }

                def _enum_cb(hwnd, lparam):
                    if IsWindowVisible(hwnd):
                        length = GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            GetWindowTextW(hwnd, buff, length + 1)
                            title = buff.value.strip()
                            if title and title not in excluded and title not in seen_titles:
                                seen_titles.add(title)
                                pid = ctypes.c_ulong()
                                GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                                proc_name = "application.exe"
                                try:
                                    if pid.value:
                                        p = psutil.Process(pid.value)
                                        proc_name = p.name()
                                except Exception:
                                    pass
                                desktop_windows.append({
                                    "title": title,
                                    "process": proc_name,
                                    "pid": pid.value,
                                    "opened_by": "Système Windows"
                                })
                    return True

                EnumWindows(EnumWindowsProc(_enum_cb), 0)
            except Exception:
                pass

        # Si l'énumération Win32 est indisponible (sandbox ou session 0), on complète avec les processus GUI notables
        if not desktop_windows:
            try:
                gui_known = ["code.exe", "chrome.exe", "explorer.exe", "notepad.exe", "windowsterminal.exe", "wt.exe", "cmd.exe", "powershell.exe"]
                for p in psutil.process_iter(["pid", "name"]):
                    try:
                        pname = p.info["name"].lower()
                        if pname in gui_known:
                            desktop_windows.append({
                                "title": f"Processus {p.info['name']} (actif)",
                                "process": p.info["name"],
                                "pid": p.info["pid"],
                                "opened_by": "Système Windows"
                            })
                    except Exception:
                        pass
            except Exception:
                pass

        # Fusionne les fenêtres ouvertes par Jarvis
        combined = []
        # En premier : fenêtres / pages ouvertes par Jarvis
        for w in self._tracked_windows:
            combined.append({
                "title": w["title"],
                "process": w["process"],
                "url": w.get("url"),
                "opened_by": "J.A.R.V.I.S.",
                "timestamp": w.get("timestamp")
            })

        # Ensuite : fenêtres système de bureau
        for w in desktop_windows:
            combined.append(w)

        return combined

    def get_full_overview(self) -> Dict[str, Any]:
        """Retourne la vue d'ensemble globale complète pour le HUD et le modal de supervision."""
        open_windows = self.get_open_windows()

        active_actions_list = list(self._actions.values())
        running_count = len(active_actions_list)

        return {
            "status": "ok",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "voice": self._voice_state,
            "active_actions": active_actions_list,
            "running_count": running_count,
            "recent_actions": self._recent_actions,
            "tools": list(self._active_tools.values()),
            "open_windows": open_windows,
            "api_keys": {
                "free_key": {
                    "configured": bool(config.GEMINI_API_KEY_FREE),
                    "masked": self._mask_key(config.GEMINI_API_KEY_FREE),
                    "role": "Modèle vocal standard Gemini 3.8 Live (parole courante sans réflexion)",
                    "cost": "0.00 $ (Inclus)",
                    "exhausted": self._free_quota_exhausted,
                    "status": "Quota épuisé (repli actif)" if self._free_quota_exhausted else "Active (Par défaut)"
                },
                "paid_key": {
                    "configured": bool(config.GEMINI_API_KEY_PAID),
                    "masked": self._mask_key(config.GEMINI_API_KEY_PAID),
                    "role": "Live Thinking, Gemini 3.8 Flash, Agents Antigravity & Repli automatique",
                    "security": "Accès direct et permanent sans restriction",
                    "status": "Active (En écoute / Repli)"
                }
            }
        }

supervision_service = SupervisionService()
