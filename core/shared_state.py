"""core/shared_state.py
État partagé global de JARVIS : clients Gemini, active_task_controller, helpers.
Ce module est importé par tous les routeurs pour éviter les imports circulaires.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"

import asyncio
import json

from google import genai
from google.genai import types

import config
from services.console_monitor import console_monitor
from services.supervision_service import supervision_service


# ─── Clients Gemini : Répartition Clé Gratuite / Clé Payante ─────────────────
# - Clé GRATUITE (client_free) : utilisée prioritairement pour gemini-3.8-live (voix standard sans réflexion).
# - Clé PAYANTE (client_paid) : utilisée pour gemini-3.8-live-extended-thinking, gemini-3.8-flash,
#   Antigravity Agents, Browser-Use et repli automatique immédiat si le quota gratuit est atteint.
client_paid = genai.Client(api_key=config.GEMINI_API_KEY_PAID) if config.GEMINI_API_KEY_PAID else None
client_free = genai.Client(api_key=config.GEMINI_API_KEY_FREE) if config.GEMINI_API_KEY_FREE else None
client = client_paid or client_free


def is_quota_or_limit_error(exc: Exception | None) -> bool:
    """Détecte si une exception correspond à un épuisement de quota ou limitation de débit (429, ResourceExhausted)."""
    if exc is None:
        return False
    err_str = f"{type(exc).__name__}: {str(exc)}".lower()
    quota_keywords = [
        "429", "quota", "resource_exhausted", "resourceexhausted",
        "rate limit", "ratelimit", "too many requests", "limit exceeded",
        "exceeded your current quota", "free tier", "billing", "exhausted"
    ]
    if any(k in err_str for k in quota_keywords):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 8):  # 8 corresponds to grpc.StatusCode.RESOURCE_EXHAUSTED
        return True
    return False


class QuotaExhaustedError(Exception):
    """Exception levée en cas de dépassement de quota ou limitation de débit sur une clé API."""
    pass


class ModelSwitchRequested(Exception):
    """Signal interne pour basculer dynamiquement le modèle vocal en direct."""
    def __init__(self, model: str):
        self.model = model


# Contrôleur d'exécution de tâche active pour injection de consignes en direct et contrôle d'arrêt
active_task_controller: dict = {
    "queue": asyncio.Queue(),
    "info": {"running": False, "task": "", "model": ""},
    "directives": [],
    "websocket": None,
    "live_session": None,        # Référence à la session Gemini Live active
    "live_session_ctx": None,    # Context manager de la session Live
    "bg_task": None,             # asyncio.Task du développement en arrière-plan
    "browser_bg_task": None,     # asyncio.Task de navigation autonome
    "search_bg_task": None,      # asyncio.Task de recherche web
    "agent_instance": None,      # Instance active d'AntigravityAgent si applicable
    "paid_consent_given": False, # Clé payante verrouillée par défaut (demande orale requise)
    "paid_live_approved": False, # Accord vocal payant par défaut verrouillé
    "paid_consent_modal_open": False,
    "paid_consent_event": None   # asyncio.Event pour attendre la confirmation
}


async def broadcast_supervision():
    """Diffuse la vue d'ensemble en temps réel via WebSocket au client connecté."""
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "supervision_update",
                "overview": supervision_service.get_full_overview()
            }))
        except Exception:
            pass


async def broadcast_jarvis_state(
    state: str, msg: str, task: str = "", detail: str = "",
    engine: str = "", model: str = "", api_type: str = "free", api_label: str = "Service Local"
):
    """Diffuse un changement d'état visuel et d'animation de JARVIS au client connecté."""
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "status",
                "state": state,
                "msg": msg,
                "task": task or msg,
                "detail": detail or task or msg,
                "engine": engine or "Local",
                "model": model or "JARVIS Engine",
                "api_type": api_type,
                "api_label": api_label
            }))
        except Exception:
            pass


async def broadcast_paid_key_status(authorized: bool):
    """Notifie le frontend du changement d'état de la clé payante."""
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "paid_key_authorized_update",
                "authorized": authorized,
                "has_paid_key": config.HAS_PAID_API_KEY
            }))
        except Exception:
            pass


async def stop_active_task(source: str = "user", reason: str = "Arrêt demandé par l'utilisateur") -> dict:
    """Interrompt immédiatement toute action en cours (code Antigravity, navigation Browser-Use, recherche, etc.)"""
    from google_antigravity import is_stop_directive  # Importé ici pour éviter circularité

    was_running = False
    cancelled_tasks = []

    # 1. Envoi du signal stop dans la queue de directives
    if active_task_controller["info"]["running"]:
        was_running = True
        try:
            await active_task_controller["queue"].put("__stop__")
        except Exception:
            pass

    # 2. Interruption explicite de l'agent Antigravity s'il est instancié
    agent_inst = active_task_controller.get("agent_instance")
    if agent_inst and hasattr(agent_inst, "cancel"):
        try:
            agent_inst.cancel()
            was_running = True
        except Exception as e:
            print(f"[Task Stop] Erreur cancel agent: {e}")

    # 3. Annulation des tâches asyncio de fond
    for task_key in ["bg_task", "browser_bg_task", "search_bg_task"]:
        task = active_task_controller.get(task_key)
        if task and not task.done():
            task.cancel()
            cancelled_tasks.append(task_key)
            was_running = True
            active_task_controller[task_key] = None

    # 4. Réinitialisation de l'état
    active_task_controller["info"]["running"] = False
    active_task_controller["info"]["task"] = ""
    active_task_controller["directives"] = []

    # 5. Supervision
    for act in ["antigravity_task", "browser_task", "search_web", "deep_reasoning"]:
        supervision_service.complete_action(act, status="cancelled", summary=reason)
    await broadcast_supervision()

    # 6. Notification immédiate au client Web
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "task_cancelled",
                "message": "Action immédiatement arrêtée.",
                "reason": reason
            }))
            await ws.send_text(json.dumps({
                "type": "status",
                "state": "idle",
                "msg": "En veille active",
                "detail": "Action interrompue",
                "engine": "Google API Live",
                "model": config.GEMINI_LIVE_MODEL
            }))
        except Exception:
            pass

    print(f"[Task Controller] Stop exécuté (source: {source}, was_running: {was_running}, tasks: {cancelled_tasks})")
    return {"status": "ok", "stopped": was_running, "cancelled_tasks": cancelled_tasks}


def get_tool_metadata(name: str, args: dict = None) -> dict:
    """Retourne l'état visuel pour l'avatar (Kindle, Musique, Média, Code, etc.), le message et les métadonnées de l'action."""
    from google_antigravity import resolve_antigravity_model  # Évite circularité
    args = args or {}
    if name in ("search_and_download_ebook", "send_to_ereader", "send_page_to_kindle", "send_file_to_kindle"):
        query = args.get("query") or args.get("title") or args.get("file_path") or args.get("url") or "Livre Kindle"
        return {"state": "kindle", "msg": f"Liseuse Kindle : {query}", "task": f"Kindle : {query}", "engine": "Amazon Send to Kindle", "model": "Send to Kindle / Anna's Archive", "api_type": "free", "api_label": "Service Local"}
    elif name == "play_music_deezer":
        q = args.get("query") or args.get("action") or "Musique"
        return {"state": "music", "msg": f"Deezer — {q}", "task": f"Deezer : {q}", "engine": "WebSocket Bridge", "model": "Deezer Web Player", "api_type": "free", "api_label": "Local"}
    elif name == "play_video_stremio":
        t = args.get("title") or "Cinéma"
        return {"state": "media", "msg": f"Stremio — Recherche de '{t}'...", "task": f"Stremio : {t}", "engine": "Cinemeta / Torrentio", "model": "Stremio 4K", "api_type": "free", "api_label": "Local"}
    elif name == "download_file":
        fn = args.get("filename") or args.get("url") or "Fichier"
        return {"state": "downloading", "msg": f"Téléchargement : {fn}...", "task": f"Téléchargement : {fn}", "engine": "Stark Transfer", "model": "Secure Downloader", "api_type": "free", "api_label": "Service Local"}
    elif name == "run_antigravity_task":
        instr = args.get("instruction") or "Développement de code..."
        model_choice = args.get("model") or "gemini-3.8-flash"
        _, m_label = resolve_antigravity_model(model_choice)
        return {"state": "coding", "msg": "JARVIS développe via Antigravity...", "task": instr, "engine": "Antigravity IDE", "model": m_label, "api_type": "paid", "api_label": "Clé Payante"}
    elif name == "ask_deep_reasoning":
        q = args.get("question") or "Analyse approfondie..."
        return {"state": "thinking", "msg": "Réflexion approfondie en cours...", "task": q, "engine": "Google API", "model": "Gemini Thinking", "api_type": "free", "api_label": "Clé Gratuite"}
    elif name in ("search_web", "run_browser_task", "interact_web_page", "open_user_browser"):
        q = args.get("query") or args.get("goal") or args.get("url") or "Navigation internet"
        return {"state": "browsing", "msg": f"Navigation Web : {q}", "task": q, "engine": "Playwright / DuckDuckGo", "model": "Browser Engine", "api_type": "free", "api_label": "Clé Gratuite"}
    elif name in ("send_email", "read_emails"):
        sub = args.get("subject") or "Messagerie Gmail"
        return {"state": "emailing", "msg": f"Messagerie Stark : {sub}", "task": sub, "engine": "SMTP / IMAP Stark", "model": "Gmail Protocol", "api_type": "free", "api_label": "Service Local"}
    elif name in ("remember_user_fact", "recall_user_memories"):
        f = args.get("fact") or args.get("query") or "Mémoire persistante"
        return {"state": "memory", "msg": f"Mémoire durable : {f}", "task": f, "engine": "SQLite Durable Memory", "model": "Stark Memory Protocol", "api_type": "free", "api_label": "Service Local"}
    elif name == "prepare_web_cart_or_checkout":
        p = args.get("product_or_service") or "Panier web"
        return {"state": "shopping", "msg": f"Préparation du panier : {p}", "task": f"Panier : {p}", "engine": "Playwright E-Commerce", "model": "Chrome Automation", "api_type": "free", "api_label": "Clé Gratuite"}
    elif name in ("executer_action_externe", "generer_fichier_tableur", "generer_presentation", "notion_enregistrer"):
        act = args.get("nom_fichier") or args.get("titre") or args.get("action_name") or args.get("action") or name
        return {"state": "document", "msg": f"Pôle Documentaire n8n : {act}...", "task": f"n8n : {act}", "engine": "n8n Community", "model": "Document Automation", "api_type": "free", "api_label": "Local n8n"}
    elif name in ("check_console_errors", "get_system_status", "launch_application", "list_chrome_extensions"):
        return {"state": "system", "msg": "Diagnostic et maintenance système...", "task": "Diagnostic système", "engine": "OS Monitor", "model": "System Telemetry", "api_type": "free", "api_label": "Service Local"}
    else:
        return {"state": "thinking", "msg": f"Exécution : {name}...", "task": name, "engine": "Système Jarvis", "model": "Agent Core", "api_type": "free", "api_label": "Service Local"}


def estimate_tool_cost(tool_name: str, args: dict) -> tuple[str, str]:
    """Retourne (reason, cost_string) pour une action nécessitant la clé payante"""
    if tool_name == "run_antigravity_task":
        model_choice = args.get("model", "gemini-3.8-flash")
        instruction = (args.get("instruction") or "")[:80]
        if any(k in str(model_choice).lower() for k in ["opus"]):
            cost = "~0.10 $"; model_info = "Claude 3 Opus (Antigravity IDE)"
        elif any(k in str(model_choice).lower() for k in ["sonnet", "claude"]):
            cost = "~0.05 $"; model_info = "Claude 3.7 Sonnet (Antigravity IDE)"
        elif any(k in str(model_choice).lower() for k in ["pro"]):
            cost = "~0.03 $"; model_info = "Gemini 3.1 Pro (Antigravity IDE)"
        else:
            cost = "~0.005 $ (< 1 centime)"; model_info = "Gemini 3.8 Flash (Antigravity IDE)"
        return f"Développement autonome avec {model_info} : '{instruction}'", cost
    elif tool_name == "run_browser_task":
        goal = (args.get("goal") or "")[:80]
        return f"Navigation autonome Browser-Use pour : '{goal}'", "~0.02 $"
    elif tool_name == "ask_deep_reasoning":
        question = (args.get("question") or "")[:80]
        model_choice = args.get("model", "gemini-3.1-pro-high")
        return f"Raisonnement approfondi avec {model_choice} pour : '{question}'", "~0.03 $"
    elif tool_name == "live_fallback":
        return "Session vocale Gemini 3.8 Live (quota gratuit épuisé)", "~0.02 $ / min (~0.10 $ pour 5 min)"
    return "Opération sur clé payante", "~0.01 $"


def merge_user_speech(current: str, incoming: str) -> str:
    """Consolide la transcription au fil de l'eau en gérant les deltas"""
    inc = (incoming or "").strip()
    if not inc:
        return current
    if not current:
        return inc
    cur_lower = current.lower()
    inc_lower = inc.lower()
    if inc_lower.startswith(cur_lower):
        return inc
    if inc_lower in cur_lower:
        return current
    if current.endswith(("-", "'")):
        return current + inc
    return current + " " + inc
