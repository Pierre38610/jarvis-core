"""core/shared_state.py
État partagé global de JARVIS : clients Gemini, active_task_controller, helpers.
Ce module est importé par tous les routeurs pour éviter les imports circulaires.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"

import asyncio
import json
import time

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
    "reasoning_bg_task": None,   # asyncio.Task de réflexion approfondie universelle
    "deep_research_task": None,  # asyncio.Task du moteur de deep research
    "agent_instance": None,      # Instance active d'AntigravityAgent si applicable
    "paid_consent_given": False, # Clé payante verrouillée par défaut (demande orale requise)
    "paid_live_approved": False, # Accord vocal payant par défaut verrouillé
    "paid_consent_modal_open": False,
    "paid_consent_event": None,  # asyncio.Event pour attendre la confirmation
    "speaking_active": False,    # True pendant l'émission de chunks audio par le modèle
    "estimated_speech_end": 0.0, # Timestamp estimé de fin de restitution audio dans les enceintes
    "client_speaking": False,    # True tant que le navigateur joue le flux sonore
    "awaiting_tool_response": False, # True pendant l'exécution d'un outil
    "tool_response_cooldown": 0.0,   # Période de grâce après send_tool_response
    "last_audio_chunk_time": 0.0,    # Horodatage du dernier paquet audio reçu
    "last_turn_complete_time": 0.0,  # Horodatage du dernier turn_complete
    "sync_resolved_actions": {},     # Actions terminées en mode synchrone {action_name: timestamp}
}


def mark_action_sync_completed(action_name: str) -> None:
    """Enregistre qu'une action s'est exécutée de manière synchrone et a répondu via tool_response (Règle d'or de canal unique)."""
    if not action_name:
        return
    sync_actions = active_task_controller.setdefault("sync_resolved_actions", {})
    sync_actions[action_name] = time.time()


def is_action_sync_completed(action_name: str, window_seconds: float = 60.0) -> bool:
    """Vérifie si une action a déjà été résolue de manière synchrone via tool_response."""
    sync_actions = active_task_controller.get("sync_resolved_actions", {})
    resolved_at = sync_actions.get(action_name)
    if resolved_at and (time.time() - resolved_at < window_seconds):
        return True
    return False


def is_model_speaking() -> bool:
    """Vérifie si le modèle Gemini Live est en train de parler ou si son flux audio est actif / en cours d'élocution."""
    now = time.time()
    if active_task_controller.get("speaking_active", False):
        return True
    if now < active_task_controller.get("estimated_speech_end", 0.0) + 0.35:
        return True
    if active_task_controller.get("client_speaking", False):
        return True
    if active_task_controller.get("awaiting_tool_response", False):
        return True
    if now < active_task_controller.get("tool_response_cooldown", 0.0):
        return True
    return False


async def wait_until_speech_finished(timeout: float = 15.0, buffer_drainage_delay: float = 0.3) -> None:
    """
    Attend que J.A.R.V.I.S. ait réellement fini de prononcer sa phrase en cours
    avant d'injecter une nouvelle interaction dans la session Gemini Live.
    Évite absolument toute coupure de parole intempestive en pleine phrase (anti-barge-in prématuré).
    Si le modèle parlait ou finissait d'émettre, respecte le délai de drainage du buffer audio.
    """
    start = time.time()
    was_speaking = False
    while time.time() - start < timeout:
        if is_model_speaking():
            was_speaking = True
            await asyncio.sleep(0.1)
        else:
            break

    # Si le modèle était en train de parler, pause de respiration et drainage audio pour laisser les enceintes terminer
    if was_speaking:
        await asyncio.sleep(buffer_drainage_delay)
    else:
        await asyncio.sleep(0.2)


async def safe_send_live_client_content(
    session,
    text: str,
    action_key: str | None = None,
    wait_if_speaking: bool = True,
    drainage_delay: float = 2.0
) -> bool:
    """
    Injecte un message client dans la session Live en s'assurant :
    1. Du respect de la règle d'or de canal unique (interdiction formelle d'appel si déjà résolu via tool_response).
    2. Du verrou d'élocution anti-coupure (si Aoede parle, différer de 2 à 3s pour éviter de couper sa phrase).
    """
    if not session:
        return False

    # 1. Règle d'or de canal unique : interdire formellement tout doublon si l'action a déjà répondu dans tool_response
    if action_key and is_action_sync_completed(action_key):
        print(f"[Canal Unique] Action '{action_key}' déjà traitée de manière synchrone via tool_response. Injection client annulée pour éliminer tout bégaiement.")
        return False

    # 2. Verrou d'élocution : attendre que Aoede ait fini de parler + drainage du buffer audio (2 à 3s)
    if wait_if_speaking:
        await wait_until_speech_finished(timeout=15.0, buffer_drainage_delay=drainage_delay)

    try:
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
            turn_complete=True
        )
        return True
    except Exception as e:
        print(f"[Safe Live Injection] Erreur: {e}")
        return False


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


async def broadcast_subagents():
    """Diffuse la liste complète et actualisée des sous-agents actifs."""
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "subagents_update",
                "agents": supervision_service.get_active_subagents()
            }))
        except Exception:
            pass


async def spawn_subagent(
    agent_id: str,
    name: str,
    role: str,
    activity: str = "coding",
    task: str = "",
    model: str = ""
):
    """Spawne un sous-agent Antigravity CLI et notifie le frontend."""
    agent = supervision_service.spawn_subagent(agent_id, name, role, activity, task, model)
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "subagent_spawn",
                "agent": agent
            }))
        except Exception:
            pass
    await broadcast_supervision()
    return agent


async def update_subagent(
    agent_id: str,
    activity: str = None,
    task: str = None,
    progress: int = None
):
    """Met à jour un sous-agent et diffuse la transition d'activité."""
    agent = supervision_service.update_subagent(agent_id, activity, task, progress)
    if agent:
        ws = active_task_controller.get("websocket")
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": "subagent_update",
                    "id": agent_id,
                    "activity": agent.get("activity"),
                    "task": agent.get("task"),
                    "progress": agent.get("progress")
                }))
            except Exception:
                pass
        await broadcast_supervision()
    return agent


async def complete_subagent(agent_id: str, summary: str = ""):
    """Marque un sous-agent comme terminé et déclenche son animation de disparition."""
    agent = supervision_service.complete_subagent(agent_id, summary)
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "subagent_done",
                "id": agent_id,
                "summary": summary
            }))
        except Exception:
            pass
    await broadcast_supervision()
    return agent


async def clear_all_subagents():
    """Retire tous les sous-agents et vide la constellation."""
    supervision_service.clear_subagents()
    await broadcast_subagents()
    await broadcast_supervision()


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
    for task_key in ["bg_task", "browser_bg_task", "search_bg_task", "reasoning_bg_task", "deep_research_task"]:
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

    # 5. Supervision & Constellation
    await clear_all_subagents()
    for act in ["antigravity_task", "browser_task", "search_web", "deep_reasoning", "deep_research"]:
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
    if name in ("search_and_download_ebook", "download_ebook", "send_to_ereader", "send_page_to_kindle", "send_file_to_kindle"):
        query = args.get("query") or args.get("title") or args.get("file_path") or args.get("source") or args.get("url") or "Livre Kindle"
        return {"state": "kindle", "msg": f"Liseuse Kindle : {query}", "task": f"Kindle : {query}", "engine": "Amazon Send to Kindle", "model": "Send to Kindle / Anna's Archive", "api_type": "free", "api_label": "Service Local"}
    elif name in ("play_music_deezer", "deezer_action"):
        q = args.get("query") or args.get("action") or "Musique"
        return {"state": "music", "msg": f"Deezer — {q}", "task": f"Deezer : {q}", "engine": "WebSocket Bridge", "model": "Deezer Web Player", "api_type": "free", "api_label": "Local"}
    elif name in ("play_video_stremio", "launch_media"):
        t = args.get("title") or "Cinéma"
        return {"state": "media", "msg": f"Stremio — Recherche de '{t}'...", "task": f"Stremio : {t}", "engine": "Cinemeta / Torrentio", "model": "Stremio 4K", "api_type": "free", "api_label": "Local"}
    elif name in ("download_file", "file_download"):
        fn = args.get("filename") or args.get("url") or "Fichier"
        return {"state": "downloading", "msg": f"Téléchargement : {fn}...", "task": f"Téléchargement : {fn}", "engine": "Stark Transfer", "model": "Secure Downloader", "api_type": "free", "api_label": "Service Local"}
    elif name in ("ask_deep_reasoning", "deep_reasoning"):
        q = args.get("question") or "Analyse approfondie..."
        model_choice = args.get("model") or "gemini-3.1-pro-high"
        _, m_label = resolve_antigravity_model(model_choice)
        return {"state": "coding", "msg": "Agents Antigravity CLI sur le VPS...", "task": q, "engine": "Antigravity CLI (VPS)", "model": m_label, "api_type": "free", "api_label": "Session Pro"}
    elif name in ("launch_deep_research", "lancer_mission_deep_research"):
        s = args.get("consigne_utilisateur") or args.get("sujet") or "Mission Deep Research"
        return {"state": "coding", "msg": f"Deep Research : {s[:35]}...", "task": f"Deep Research : {s[:35]}", "engine": "Antigravity CLI (VPS)", "model": "Gemini 3.1 Pro High", "api_type": "free", "api_label": "Google AI Pro VPS"}
    elif name in ("search_web", "web_search", "run_browser_task", "browser_task", "interact_web_page", "open_user_browser", "open_browser"):
        q = args.get("query") or args.get("goal") or args.get("url") or "Navigation internet"
        return {"state": "browsing", "msg": f"Navigation Web : {q}", "task": q, "engine": "Playwright / DuckDuckGo", "model": "Browser Engine", "api_type": "free", "api_label": "Clé Gratuite"}
    elif name in ("send_email", "mail_send", "read_emails", "get_emails"):
        sub = args.get("subject") or "Messagerie Gmail"
        return {"state": "emailing", "msg": f"Messagerie Stark : {sub}", "task": sub, "engine": "SMTP / IMAP Stark", "model": "Gmail Protocol", "api_type": "free", "api_label": "Service Local"}
    elif name in ("draft_email_response", "triage_et_brouillon_email"):
        q = args.get("query") or "Triage e-mail"
        return {"state": "emailing", "msg": f"Brouillon e-mail : {q}...", "task": f"Triage {q}", "engine": "Antigravity CLI", "model": "Email Agent", "api_type": "free", "api_label": "Session Pro"}
    elif name in ("generate_book_summary", "curation_livre_synthese"):
        tl = args.get("titre_livre") or "Livre"
        return {"state": "document", "msg": f"Synthèse livre : {tl}...", "task": f"Fiche de lecture {tl}", "engine": "Antigravity CLI", "model": "Book Curator", "api_type": "free", "api_label": "Session Pro"}
    elif name in ("system_self_healing", "auto_guerison_systeme"):
        m = args.get("motif") or "SRE"
        return {"state": "coding", "msg": f"Auto-guérison SRE : {m}...", "task": f"SRE {m}", "engine": "Antigravity SRE", "model": "Healing Agent", "api_type": "free", "api_label": "Session Pro"}
    elif name in ("save_memory", "remember_user_fact", "memoriser_information", "recall_user_memories", "search_memories"):
        f = args.get("fact") or args.get("valeur") or args.get("key") or args.get("query") or "Mémoire persistante"
        return {"state": "memory", "msg": f"Mémoire durable : {f}", "task": f, "engine": "SQLite Durable Memory", "model": "Stark Memory Protocol", "api_type": "free", "api_label": "Service Local"}
    elif name in ("prepare_web_cart_or_checkout", "prepare_cart"):
        p = args.get("product_or_service") or "Panier web"
        return {"state": "shopping", "msg": f"Préparation du panier : {p}", "task": f"Panier : {p}", "engine": "Playwright E-Commerce", "model": "Chrome Automation", "api_type": "free", "api_label": "Clé Gratuite"}
    elif name in ("execute_external_action", "executer_action_externe", "generate_spreadsheet", "generer_fichier_tableur", "generate_presentation", "generer_presentation", "save_notion_entry", "notion_enregistrer"):
        act = args.get("nom_fichier") or args.get("titre") or args.get("action_name") or args.get("action") or name
        return {"state": "document", "msg": f"Pôle Documentaire n8n : {act}...", "task": f"n8n : {act}", "engine": "n8n Community", "model": "Document Automation", "api_type": "free", "api_label": "Local n8n"}
    elif name in ("manage_calendar_event", "agenda_gerer_evenement"):
        t = args.get("titre") or "Événement"
        act = args.get("action") or "Agenda"
        return {"state": "calendar", "msg": f"Agenda ({act}) : {t}...", "task": f"Agenda : {t}", "engine": "n8n / Google Calendar", "model": "Samsung Sync", "api_type": "free", "api_label": "Local n8n"}
    elif name in ("create_push_reminder", "creer_rappel_push"):
        m = args.get("message") or "Rappel"
        ech = args.get("echeance") or ""
        return {"state": "reminder", "msg": f"Rappel push ({ech}) : {m}...", "task": f"Rappel : {m}", "engine": "n8n Push", "model": "Push Notification", "api_type": "free", "api_label": "Local n8n"}
    elif name in ("get_morning_briefing", "demander_morning_briefing"):
        return {"state": "briefing", "msg": "Morning Briefing Stark...", "task": "Morning Briefing", "engine": "FastAPI / Redis", "model": "Briefing Protocol", "api_type": "free", "api_label": "Local Service"}
    elif name in ("search_train_routes", "rechercher_train"):
        orig = args.get("origine", "")
        dest = args.get("destination", "")
        return {"state": "browsing", "msg": f"Recherche trains : {orig} → {dest}...", "task": f"Train {orig} - {dest}", "engine": "Transport Service", "model": "Playwright VPS", "api_type": "free", "api_label": "Headless VPS"}
    elif name in ("monitor_train", "surveiller_train"):
        num = args.get("numero_train", "")
        return {"state": "system", "msg": f"Surveillance train {num} via n8n...", "task": f"Veille Train {num}", "engine": "n8n / Trafikverket / SNCF", "model": "Real-time Monitor", "api_type": "free", "api_label": "Local n8n"}
    elif name in ("open_train_booking", "reserver_billet_train_local"):
        op = (args.get("operateur") or "SNCF").upper()
        return {"state": "shopping", "msg": f"Préparation réservation {op} sur PC...", "task": f"Réservation {op}", "engine": "jarvis_local_agent", "model": "Chrome Local Windows", "api_type": "free", "api_label": "Local GUI"}
    elif name in ("query_jarvis_architecture", "consulter_architecture_jarvis"):
        s = args.get("section") or args.get("sujet") or "Spécifications"
        return {"state": "system", "msg": f"Consultation architecture ({s})...", "task": f"Architecture {s}", "engine": "Architecture Service", "model": "ARCHITECTURE_COMPLETE_JARVIS.md", "api_type": "free", "api_label": "Local Spec"}
    elif name in ("check_console_errors", "get_system_status", "launch_application", "list_chrome_extensions"):
        return {"state": "system", "msg": "Diagnostic et maintenance système...", "task": "Diagnostic système", "engine": "OS Monitor", "model": "System Telemetry", "api_type": "free", "api_label": "Service Local"}
    else:
        return {"state": "thinking", "msg": f"Exécution : {name}...", "task": name, "engine": "Système Jarvis", "model": "Agent Core", "api_type": "free", "api_label": "Service Local"}


def estimate_tool_cost(tool_name: str, args: dict) -> tuple[str, str]:
    """Retourne (reason, cost_string) pour une action nécessitant la clé payante"""
    if tool_name == "run_browser_task":
        goal = (args.get("goal") or "")[:80]
        return f"Navigation autonome Browser-Use pour : '{goal}'", "~0.02 $"
    elif tool_name == "ask_deep_reasoning":
        question = (args.get("question") or "")[:80]
        model_choice = args.get("model", "gemini-3.1-pro-high")
        return f"Investigation multi-agents Antigravity CLI ({model_choice}) : '{question}'", "~0.03 $"
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
