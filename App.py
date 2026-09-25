"""J.A.R.V.I.S. Core Server - Stark Industries AI Assistant
Architecture modulaire : WebSocket bidirectionnel Gemini Live Audio, Agent Web autonome Browser-Use,
Raisonnement officiel Gemini 2.5 Pro Thinking & Antigravity IDE (Flash 3.8, Pro 3.1, Sonnet, Opus),
Mémoire persistante SQLite et Métriques Système.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, UploadFile, File, Form
from starlette.websockets import WebSocketDisconnected
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from google.genai import types

import config
import auth
from fastapi.middleware.cors import CORSMiddleware
from google_antigravity import resolve_antigravity_model, is_stop_directive
from services.memory_service import memory_service
from services.reasoning_service import run_deep_reasoning, run_antigravity_task
from services.browser_service import (
    search_web, run_browser_task, open_browser_window, interact_web_page,
    prepare_web_cart_or_checkout, send_page_to_kindle, send_file_to_kindle_web,
    check_kindle_web_status, list_installed_chrome_extensions
)
from services.download_service import download_file, send_to_ereader, search_and_download_ebook, list_downloaded_files
from services.system_service import get_system_status, launch_application
from services.email_service import send_email_async, list_outbox_emails, read_received_emails_async
from services.console_monitor import console_monitor
from services.supervision_service import supervision_service
from services.chat_service import chat_service
from services.media_service import launch_deezer, play_deezer_track, control_deezer, search_deezer, play_on_stremio, launch_stremio, launch_vlc

app = FastAPI(title="J.A.R.V.I.S. Core Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

@app.on_event("startup")
async def startup_event():
    """Démarre le serveur WebSocket Deezer Bridge au lancement de J.A.R.V.I.S."""
    try:
        from deezer_bridge import deezer_controller
        await deezer_controller.start()
    except Exception as e:
        print(f"[Deezer Startup] Erreur lancement bridge : {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Arrête proprement le serveur WebSocket Deezer Bridge."""
    try:
        from deezer_bridge import deezer_controller
        await deezer_controller.stop()
    except Exception:
        pass

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

class AuthRequest(BaseModel):
    password: str

class EmailRequest(BaseModel):
    subject: str = ""
    body: str = ""
    to_email: str | None = None
    attachments: list[str] | None = None
    include_screenshot: bool = False
    is_html_report: bool = True

class DeezerControlRequest(BaseModel):
    action: str = "playpause"
    query: str = ""
    item_type: str = "track"
    volume: int | None = None
    position: float | None = None
    enable: bool | None = None

class SendToKindleRequest(BaseModel):
    url: str
    title: str = ""

class SendFileToKindleRequest(BaseModel):
    file_path: str = ""
    open_browser_if_needed: bool = True



@app.get("/")
async def serve_ui():
    """Sert l'interface HUD mobile Stark Industries"""
    index_file = os.path.join(config.STATIC_DIR, "index.html")
    return FileResponse(index_file)

@app.post("/api/auth")
async def authenticate_device(req: AuthRequest, request: Request, response: Response):
    """Vérifie le mot de passe maître et génère un jeton permanent d'appareil"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    token = auth.verify_and_generate_token(req.password, client_ip, user_agent)
    
    if token:
        response.set_cookie(
            key="jarvis_device_token",
            value=token,
            max_age=315360000,  # 10 ans
            httponly=False,
            samesite="lax",
            secure=True
        )
        return {"status": "ok", "token": token}

class QRAuthRequest(BaseModel):
    ticket: str

@app.post("/api/auth-qr")
async def authenticate_via_qr(req: QRAuthRequest, request: Request, response: Response):
    """Enregistre l'appareil sans mot de passe après scan d'un QR code valide"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    token = auth.register_device_via_qr(req.ticket, client_ip, user_agent)
    if token:
        response.set_cookie(
            key="jarvis_device_token",
            value=token,
            max_age=315360000,  # 10 ans
            httponly=False,
            samesite="lax",
            secure=True
        )
        return {"status": "ok", "token": token, "message": "Appareil approuvé par scan QR"}
    return JSONResponse(
        content={"status": "error", "message": "Ticket QR invalide ou expiré"},
        status_code=401
    )

@app.get("/api/verify")
async def verify_device(request: Request):
    """Vérifie si le terminal possède un jeton d'enregistrement valide"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if auth.is_device_authorized(token):
        return {"authorized": True}
    return JSONResponse(content={"authorized": False}, status_code=401)

@app.get("/api/tunnel-info")
async def get_tunnel_info():
    """Retourne l'URL Cloudflare active et les informations d'accès mobile"""
    url_file = os.path.join(config.BASE_DIR, "tunnel_url.txt")
    tunnel_url = None
    if os.path.exists(url_file):
        try:
            with open(url_file, "r", encoding="utf-8") as f:
                tunnel_url = f.read().strip()
        except Exception:
            pass
    return {
        "tunnel_url": tunnel_url,
        "status": "ready" if tunnel_url else "waiting"
    }

@app.post("/api/send-email")
async def api_send_email(req: EmailRequest, request: Request):
    """Envoie un e-mail via l'API REST de J.A.R.V.I.S."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    res = await send_email_async(
        subject=req.subject,
        body=req.body,
        to_email=req.to_email,
        attachments=req.attachments,
        include_screenshot=req.include_screenshot,
        is_html_report=req.is_html_report
    )
    return res

@app.get("/api/emails/outbox")
async def api_get_outbox(request: Request):
    """Liste les e-mails archivés dans l'outbox locale"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    return {"emails": list_outbox_emails()}

@app.get("/api/emails/inbox")
async def api_get_inbox(request: Request, count: int = 5, query: str | None = None, unread_only: bool = False):
    """Récupère les e-mails reçus sur la boîte Gmail via IMAP"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    res = await read_received_emails_async(max_count=count, query=query, unread_only=unread_only)
    return res

@app.get("/api/emails/preview/{email_id}")
async def api_preview_email(email_id: str):
    """Affiche le rapport HTML d'un courriel généré directement dans le navigateur"""
    if os.path.exists(config.EMAIL_OUTBOX_DIR):
        for fname in os.listdir(config.EMAIL_OUTBOX_DIR):
            if email_id in fname and fname.endswith(".html"):
                return FileResponse(os.path.join(config.EMAIL_OUTBOX_DIR, fname), media_type="text/html")
    return JSONResponse(content={"error": "E-mail introuvable"}, status_code=404)

@app.post("/api/open-chrome-profile")
async def api_open_chrome_profile(request: Request):
    """Ouvre Google Chrome avec le profil persistant de Jarvis pour que Pierre
    puisse se connecter à ses comptes (Amazon, Google, etc.) et sauvegarder ses sessions.
    Ces sessions seront ensuite réutilisées automatiquement par Jarvis."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    url = "https://www.google.com"
    try:
        body = await request.json()
        url = body.get("url", url)
    except Exception:
        pass
    from services.browser_service import open_browser_window
    res = open_browser_window(url)
    return {
        "status": res.get("status"),
        "message": (
            "Chrome est ouvert avec le profil Jarvis. "
            "Connectez-vous à vos comptes (Amazon, Google, etc.) depuis cette fenêtre. "
            "Jarvis réutilisera automatiquement ces sessions à chaque navigation."
        ),
        "profile_dir": config.PROFILE_DIR if hasattr(config, "PROFILE_DIR") else "Voir config.py"
    }

@app.get("/api/downloads")
async def api_list_downloads(request: Request):
    """Retourne la liste des documents et ebooks téléchargés par J.A.R.V.I.S."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return {
        "downloads": list_downloaded_files("downloads"),
        "ebooks": list_downloaded_files("ebooks")
    }

# ─── ENDPOINTS MEDIA DEEZER (CONTRÔLE 100% WEB PLAYER & RECHERCHE) ────────────

@app.post("/api/media/deezer/control")
async def api_control_deezer(req: DeezerControlRequest, request: Request):
    """Contrôle total du Web Player Deezer : play, pause, playpause, next, prev, shuffle, volume, choose, open."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await control_deezer(
        action=req.action,
        query=req.query,
        item_type=req.item_type,
        volume=req.volume,
        position=req.position,
        enable=req.enable
    )
    return res

@app.get("/api/media/deezer/search")
async def api_search_deezer(query: str, type: str = "track", limit: int = 5, request: Request = None):
    """Recherche des morceaux, albums ou playlists via l'API Deezer."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") if request else None
    if token and not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    results = await search_deezer(query=query, search_type=type, limit=limit)
    return {"query": query, "type": type, "count": len(results), "results": results}

@app.get("/api/media/deezer/status")
async def api_deezer_status(request: Request = None):
    """Récupère l'état temps réel du Web Player Deezer (titre, artiste, pause, shuffle, position)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") if request else None
    if token and not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    from deezer_bridge import deezer_controller
    return await deezer_controller.get_playback_status()

@app.get("/api/media/deezer/userscript")
async def api_deezer_userscript():
    """Sert le script Tampermonkey pour installation directe en un clic."""
    script_path = os.path.join(config.WORKSPACE_ROOT, "deezer_controller.user.js")
    if os.path.exists(script_path):
        return FileResponse(script_path, media_type="text/javascript", filename="deezer_controller.user.js")
    return JSONResponse(status_code=404, content={"message": "Script Tampermonkey introuvable"})

# ─── ENDPOINTS EXTENSIONS CHROME & SEND TO KINDLE ─────────────────────────────

@app.get("/api/browser/extensions")
async def api_list_extensions(request: Request):
    """Liste toutes les extensions Google Chrome détectées (Send to Kindle, etc.)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return list_installed_chrome_extensions()

@app.post("/api/browser/send-to-kindle")
async def api_send_to_kindle(req: SendToKindleRequest, request: Request):
    """Extrait un article web et l'achemine vers la liseuse Kindle de Pierre (Send to Kindle)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await send_page_to_kindle(url=req.url, title=req.title, open_in_chrome=True)
    return res

@app.post("/api/browser/send-file-to-kindle")
async def api_send_file_to_kindle(req: SendFileToKindleRequest, request: Request):
    """Dépose un fichier local sur Amazon Send to Kindle et l'envoie sur la Kindle de Pierre."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await send_file_to_kindle_web(file_path=req.file_path, open_browser_if_needed=req.open_browser_if_needed)
    return res

@app.post("/api/browser/upload-and-send-to-kindle")
async def api_upload_and_send_to_kindle(request: Request, file: UploadFile = File(...)):
    """Reçoit un fichier téléversé depuis l'interface ou mobile et l'expédie immédiatement sur Amazon Send to Kindle."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    upload_dir = os.path.join(config.STATIC_DIR, "uploads", "kindle")
    os.makedirs(upload_dir, exist_ok=True)
    file_location = os.path.join(upload_dir, file.filename)
    with open(file_location, "wb") as f_out:
        content = await file.read()
        f_out.write(content)

    res = await send_file_to_kindle_web(file_path=file_location, open_browser_if_needed=False)
    return res

@app.get("/api/browser/kindle-status")
async def api_kindle_status(request: Request):
    """Vérifie si la session Amazon Send to Kindle est active et connectée sur la machine."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return await check_kindle_web_status()

@app.post("/api/browser/open-kindle-login")
async def api_open_kindle_login(request: Request):
    """Ouvre Google Chrome sur la page Amazon Send to Kindle avec le profil Jarvis pour se connecter."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return open_browser_window("https://www.amazon.fr/sendtokindle", load_extensions=True)


@app.get("/api/supervision/overview")
async def get_supervision_overview(request: Request):
    """Retourne la vue d'ensemble complète : modèle vocal, clé API, actions actives, outils et fenêtres ouvertes."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return supervision_service.get_full_overview()

@app.get("/api/supervision/windows")
async def get_supervision_windows(request: Request):
    """Retourne la liste rafraîchie des fenêtres ouvertes."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return {"windows": supervision_service.get_open_windows()}

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

class DirectiveRequest(BaseModel):
    directive: str

# Contrôleur d'exécution de tâche active pour injection de consignes en direct et contrôle d'arrêt
active_task_controller = {
    "queue": asyncio.Queue(),
    "info": {"running": False, "task": "", "model": ""},
    "directives": [],
    "websocket": None,
    "live_session": None,        # Référence à la session Gemini Live active
    "bg_task": None,             # asyncio.Task du développement en arrière-plan
    "browser_bg_task": None,     # asyncio.Task de navigation autonome
    "search_bg_task": None,      # asyncio.Task de recherche web
    "agent_instance": None,      # Instance active d'AntigravityAgent si applicable
    "paid_consent_given": False, # Clé payante verrouillée par défaut (demande orale requise)
    "paid_live_approved": False, # Accord vocal payant par défaut verrouillé
    "paid_consent_modal_open": False,
    "paid_consent_event": None   # asyncio.Event pour attendre la confirmation
}

async def stop_active_task(source: str = "user", reason: str = "Arrêt demandé par l'utilisateur") -> dict:
    """Interrompt immédiatement toute action en cours (code Antigravity, navigation Browser-Use, recherche, etc.)"""
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

@app.post("/api/task/directive")
async def post_task_directive(req: DirectiveRequest, request: Request):
    """Permet à l'utilisateur d'adapter ou guider en direct la tâche de code en cours de développement"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    directive = req.directive.strip()
    if not directive:
        return JSONResponse(content={"status": "error", "message": "Directive vide"}, status_code=400)

    # Si c'est un ordre d'arrêt explicite, stopper immédiatement sans transmettre au LLM
    if is_stop_directive(directive):
        res = await stop_active_task(source="directive_stop", reason=directive)
        return {"status": "cancelled", "message": "Développement immédiatement interrompu."}

    if active_task_controller["info"]["running"]:
        await active_task_controller["queue"].put(directive)
        active_task_controller.setdefault("directives", []).append(directive)
        ws = active_task_controller.get("websocket")
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Consigne reçue : {directive}. Adaptation en cours.",
                    "voice": False
                }))
            except Exception:
                pass
        return {"status": "ok", "message": f"Consigne '{directive}' transmise au moteur Antigravity."}
    return {"status": "ignored", "message": "Aucune tâche active à adapter."}

@app.post("/api/task/stop")
async def post_task_stop(request: Request):
    """Interrompt immédiatement toute tâche ou développement en cours à la demande de l'utilisateur."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await stop_active_task(source="api_button", reason="Arrêt demandé via l'interface")
    return JSONResponse(content=res)


# ─── Messagerie Écrite & Analyse Visuelle Multimodale J.A.R.V.I.S. ─────────

@app.get("/api/chat/history")
async def get_chat_history(request: Request, limit: int = 50):
    """Retourne l'historique des échanges écrits et photos analysées."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    messages = chat_service.get_history(limit=limit)
    return {"status": "success", "messages": messages}

@app.post("/api/chat/message")
async def post_chat_message(
    request: Request,
    text: str | None = Form(None),
    image: UploadFile | None = File(None)
):
    """Reçoit un message écrit et/ou une photo pour analyse multimodale par JARVIS."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    image_bytes = None
    image_mime = "image/jpeg"
    filename = None
    if image:
        image_bytes = await image.read()
        image_mime = image.content_type or "image/jpeg"
        filename = image.filename

    res = await chat_service.process_user_message(
        text=text,
        image_bytes=image_bytes,
        image_mime=image_mime,
        filename=filename
    )

    # Notification en direct au WebSocket si connecté
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            await ws.send_text(json.dumps({
                "type": "chat_message_received",
                "user_message": res.get("user_message"),
                "jarvis_message": res.get("jarvis_message")
            }))
        except Exception:
            pass

    return JSONResponse(content=res)

@app.post("/api/chat/clear")
async def post_chat_clear(request: Request):
    """Efface l'historique complet de la messagerie."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token") or request.headers.get("x-device-token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    chat_service.clear_history()
    return {"status": "success", "message": "Historique de discussion effacé."}


class LiveModelRequest(BaseModel):
    model: str

@app.get("/api/live-model")
async def get_live_model():
    """Retourne le modèle Gemini Live configuré pour la voix de Jarvis."""
    return {
        "current_model": config.GEMINI_LIVE_MODEL,
        "available_models": ["gemini-3.8-live", "gemini-3.8-live-extended-thinking"]
    }

@app.post("/api/live-model")
@app.post("/api/supervision/set-model")
async def set_live_model(req: LiveModelRequest):
    """Bascule le modèle vocal Gemini Live entre gemini-3.8-live et gemini-3.8-live-extended-thinking."""
    if req.model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
        config.GEMINI_LIVE_MODEL = req.model
        is_thinking = "extended-thinking" in req.model
        is_paid = is_thinking or supervision_service._free_quota_exhausted or not bool(config.GEMINI_API_KEY_FREE)
        supervision_service.update_voice_state(supervision_service._voice_state["status"], model=req.model, is_paid=is_paid)
        await broadcast_supervision()
        return {"status": "ok", "current_model": config.GEMINI_LIVE_MODEL}
    return JSONResponse(
        status_code=400,
        content={"error": "Modèle non supporté. Choix: gemini-3.8-live ou gemini-3.8-live-extended-thinking"}
    )

class PaidConsentRequest(BaseModel):
    action: str
    approved: bool

@app.post("/api/paid-consent")
async def post_paid_consent(req: PaidConsentRequest, request: Request):
    """Permet à Pierre de valider ou refuser l'utilisation de la clé payante via REST ou interface"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    active_task_controller["paid_consent_given"] = req.approved
    if req.action == "live_fallback":
        active_task_controller["paid_live_approved"] = req.approved
    if active_task_controller.get("paid_consent_event"):
        active_task_controller["paid_consent_event"].set()
    
    ws = active_task_controller.get("websocket")
    if ws:
        try:
            status_text = "accordée" if req.approved else "refusée"
            await ws.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Autorisation d'accès payant {status_text}.",
                "voice": False
            }))
            if req.approved:
                await ws.send_text(json.dumps({"type": "hide_paid_consent"}))
        except Exception:
            pass
    return {"status": "ok", "action": req.action, "approved": req.approved}

def estimate_tool_cost(tool_name: str, args: dict) -> tuple[str, str]:
    """Retourne (reason, cost_string) pour une action nécessitant la clé payante"""
    if tool_name == "run_antigravity_task":
        model_choice = args.get("model", "gemini-3.8-flash")
        instruction = (args.get("instruction") or "")[:80]
        if any(k in str(model_choice).lower() for k in ["opus"]):
            cost = "~0.10 $"
            model_info = "Claude 3 Opus (Antigravity IDE)"
        elif any(k in str(model_choice).lower() for k in ["sonnet", "claude"]):
            cost = "~0.05 $"
            model_info = "Claude 3.7 Sonnet (Antigravity IDE)"
        elif any(k in str(model_choice).lower() for k in ["pro"]):
            cost = "~0.03 $"
            model_info = "Gemini 3.1 Pro (Antigravity IDE)"
        else:
            cost = "~0.005 $ (< 1 centime)"
            model_info = "Gemini 3.8 Flash (Antigravity IDE)"
        reason = f"Développement autonome et modification de code dans le projet avec {model_info} : '{instruction}'"
        return reason, cost

    elif tool_name == "run_browser_task":
        goal = (args.get("goal") or "")[:80]
        reason = f"Navigation autonome universelle Browser-Use avec analyse visuelle pour : '{goal}'"
        cost = "~0.02 $"
        return reason, cost

    elif tool_name == "ask_deep_reasoning":
        question = (args.get("question") or "")[:80]
        model_choice = args.get("model", "gemini-3.1-pro-high")
        reason = f"Raisonnement approfondi avec modèle lourd {model_choice} pour : '{question}'"
        cost = "~0.03 $"
        return reason, cost

    elif tool_name == "live_fallback":
        reason = "Session vocale bidirectionnelle continue Gemini 3.8 Live (quota gratuit épuisé)"
        cost = "~0.02 $ / min (~0.10 $ pour 5 min)"
        return reason, cost

    return "Opération sur clé payante", "~0.01 $"

@app.websocket("/ws")
async def voice_channel(websocket: WebSocket):
    # Validation du terminal avant acceptation
    token = websocket.query_params.get("token") or websocket.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        await websocket.close(code=1008, reason="Terminal non autorise")
        return

    # S'assurer qu'une seule instance WebSocket et session Live existe à la fois côté serveur
    prev_ws = active_task_controller.get("websocket")
    prev_session_ctx = active_task_controller.get("live_session_ctx")
    prev_session = active_task_controller.get("live_session")

    if prev_ws and prev_ws != websocket:
        try:
            print("[Voice Channel] Fermeture de la précédente connexion WebSocket orpheline...")
            await prev_ws.close(code=1000, reason="Nouvelle connexion active")
        except Exception:
            pass
    if prev_session_ctx:
        try:
            print("[Voice Channel] Fermeture de la session Live Google précédente...")
            await prev_session_ctx.__aexit__(None, None, None)
        except Exception:
            pass
    elif prev_session:
        try:
            await prev_session.close()
        except Exception:
            pass

    await websocket.accept()
    active_task_controller["websocket"] = websocket

    # Vérification qu'au moins une clé GEMINI est configurée
    if not (client_paid or client_free):
        await websocket.send_text(json.dumps({
            "type": "transcript",
            "role": "jarvis",
            "text": "Erreur : Aucune clé GEMINI configurée."
        }))
        await websocket.close()
        return

    # Palette d'outils ultra-complète de J.A.R.V.I.S. avec sélection intelligente du modèle
    tools_list = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="run_antigravity_task",
                    description=(
                        "OUTIL MAJEUR ET OBLIGATOIRE POUR TOUT DÉVELOPPEMENT, CODE ET ACTION SYSTÈME : "
                        "Pilote l'agent autonome outillé Antigravity dans le workspace local (my-project). "
                        "L'agent Antigravity est un véritable agent d'ingénierie disposant d'outils réels d'action : "
                        "création et modification de fichiers de code (CREATE_FILE, EDIT_FILE), lecture et inspection (VIEW_FILE), "
                        "exploration du projet (LIST_DIR, SEARCH_DIR), et exécution de commandes shell ou de tests (RUN_COMMAND). "
                        "TU DOIS L'INVOQUER SYSTÉMATIQUEMENT dès qu'il s'agit d'écrire du code, corriger un bug, refactorer, "
                        "créer un jeu ou une application (ex: snake, web app, script python), installer des packages, tester un script "
                        "ou manipuler des fichiers. Ne récite JAMAIS de code toi-même à l'oral."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "instruction": types.Schema(
                                type="STRING",
                                description="L'ordre exact de programmation, d'architecture, de test ou d'action agentique à mener"
                            ),
                            "model": types.Schema(
                                type="STRING",
                                description=(
                                    "Modèle Antigravity selon la complexité : "
                                    "'gemini-3.8-flash-low', 'gemini-3.8-flash-medium', 'gemini-3.8-flash-high' (par défaut, ultra-performant et rapide pour tout développement), "
                                    "'gemini-3.1-pro-low', 'gemini-3.1-pro-medium', 'gemini-3.1-pro-high' (recommandé pour algorithmes ardus, logique complexe et architecture), "
                                    "'claude-3-7-sonnet' ou 'claude-3-opus' (pour refactoring massif et ingénierie de précision). "
                                    "Par défaut : 'gemini-3.8-flash-high'."
                                )
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta demande expliquant le besoin et le coût estimé. Par défaut False."
                            )
                        },
                        required=["instruction"]
                    )
                ),
                types.FunctionDeclaration(
                    name="stop_current_action",
                    description=(
                        "ARRÊTE IMMÉDIATEMENT l'action, le développement de code, la navigation web ou la recherche en cours. "
                        "TU DOIS L'INVOQUER IMMÉDIATEMENT dès que Pierre te dit d'arrêter, de faire une pause, de stopper ou d'annuler "
                        "(ex: 'arrête', 'stop', 'annule', 'interromps', 'tais-toi et arrête', 'laisse tomber'). "
                        "Cette action interrompt physiquement l'agent Antigravity ou le navigateur en arrière-plan et remet l'état à l'arrêt."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "reason": types.Schema(
                                type="STRING",
                                description="Le motif ou la consigne d'arrêt exprimée par Pierre"
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="guide_active_task",
                    description=(
                        "Permet à l'utilisateur de guider, adapter, modifier ou corriger en direct l'action ou le code en cours de développement "
                        "par Antigravity IDE (ex: changer de bibliothèque, ajouter un paramètre, corriger une direction) sans interrompre la session."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "directive": types.Schema(
                                type="STRING",
                                description="La consigne ou adaptation demandée par l'utilisateur pour le développement en cours"
                            )
                        },
                        required=["directive"]
                    )
                ),
                types.FunctionDeclaration(
                    name="ask_deep_reasoning",
                    description=(
                        "Sollicite un moteur de réflexion approfondie (Thinking) pour les analyses philosophiques, scientifiques, stratégiques complexes, "
                        "les calculs avancés ou les synthèses intellectuelles exigeantes. "
                        "Permet d'utiliser l'API rapide (Thinking gratuit) ou de déléguer à Antigravity IDE avec un grand modèle (Pro 3.1 ou Claude Opus/Sonnet) "
                        "quand le modèle de base de l'API en thinking n'est pas suffisant."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "question": types.Schema(
                                type="STRING",
                                description="La question ou problématique complexe à analyser en profondeur"
                            ),
                            "engine": types.Schema(
                                type="STRING",
                                description=(
                                    "Moteur d'exécution : 'google_api' pour le modèle Thinking de l'API (rapide, sans frais), "
                                    "ou 'antigravity' pour déléguer à Antigravity IDE quand la tâche demande une puissance de calcul et de réflexion maximale."
                                )
                            ),
                            "model": types.Schema(
                                type="STRING",
                                description=(
                                    "Modèle à utiliser si Antigravity est choisi : "
                                    "'gemini-3.1-pro-high', 'gemini-3.1-pro-medium', 'claude-3-opus', 'claude-3-7-sonnet', ou 'gemini-3.8-flash-high'."
                                )
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta demande expliquant le besoin et le coût estimé. Par défaut False."
                            )
                        },
                        required=["question"]
                    )
                ),
                types.FunctionDeclaration(
                    name="search_web",
                    description="Effectue une recherche rapide sur Internet pour obtenir des informations récentes, des faits, des prix ou des liens.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="La requête de recherche web précise"
                            )
                        },
                        required=["query"]
                    )
                ),
                types.FunctionDeclaration(
                    name="run_browser_task",
                    description="Pilote un agent web autonome universel (Browser-Use) pour naviguer, réserver (hôtels, billets), remplir des formulaires, comparer des prix ou exécuter des missions sur n'importe quel site web.",
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "goal": types.Schema(
                                type="STRING",
                                description="L'objectif concret de navigation à accomplir sur le web"
                            ),
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL de départ si connue, sinon laisser vide"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta demande expliquant le besoin et le coût estimé. Par défaut False."
                            )
                        },
                        required=["goal"]
                    )
                ),
                types.FunctionDeclaration(
                    name="open_user_browser",
                    description="Ouvre Google Chrome directement à l'écran de l'utilisateur avec son profil connecté pour afficher un site ou une page spécifique.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL à ouvrir dans le navigateur à l'écran"
                            ),
                            "reason": types.Schema(
                                type="STRING",
                                description="La raison de l'ouverture"
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="set_browser_link",
                    description=(
                        "Définit ou met à jour le lien web précis affiché dans le HUD mobile pour que l'utilisateur puisse cliquer sur 'OUVRIR LE LIEN' "
                        "(ex: lien direct vers un train spécifique avec horaires, un vol précis, un hôtel, ou un article complet au lieu de la page d'accueil)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL directe précise de la page ou de la réservation"
                            ),
                            "title": types.Schema(
                                type="STRING",
                                description="Le libellé court du lien (ex: 'Train Paris - Lyon 14h08', 'Vol Air France')"
                            )
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="remember_user_fact",
                    description="Enregistre un souvenir, une préférence, une habitude ou une information importante concernant l'utilisateur dans la mémoire persistante long-terme de Jarvis.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "fact": types.Schema(
                                type="STRING",
                                description="Le fait, la préférence ou l'information à mémoriser durablement"
                            ),
                            "category": types.Schema(
                                type="STRING",
                                description="Catégorie (ex: 'préférences', 'projets', 'famille', 'voyage')"
                            )
                        },
                        required=["fact"]
                    )
                ),
                types.FunctionDeclaration(
                    name="recall_user_memories",
                    description="Recherche dans la mémoire persistante long-terme des informations ou souvenirs passés sur l'utilisateur ou ses projets.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="Mots-clés de recherche dans la mémoire"
                            )
                        },
                        required=["query"]
                    )
                ),
                types.FunctionDeclaration(
                    name="get_system_status",
                    description="Consulte l'état en direct de l'ordinateur de l'utilisateur (utilisation du processeur CPU, mémoire RAM, état de la batterie).",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={}
                    )
                ),
                types.FunctionDeclaration(
                    name="launch_application",
                    description=(
                        "Ouvre une application locale sur l'ordinateur de Pierre "
                        "(Calculatrice, Bloc-notes, VS Code, Explorateur, Chrome, VLC). "
                        "IMPORTANT : Pour Deezer utilise 'play_music_deezer'. Pour Stremio utilise 'play_video_stremio'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "app_name": types.Schema(
                                type="STRING",
                                description="Nom de l'application (calculatrice, bloc-notes, vscode, explorateur, chrome, vlc)"
                            )
                        },
                        required=["app_name"]
                    )
                ),
                types.FunctionDeclaration(
                    name="play_music_deezer",
                    description=(
                        "CONTRÔLE 100% DU WEB PLAYER DEEZER (deezer.com) : "
                        "Gère le Web Player Deezer en temps réel via liaison WebSocket locale et l'API Deezer officielle. "
                        "Permet de : "
                        "1) Mettre en pause ('pause', 'arrête la musique') via action='pause', "
                        "2) Reprendre la lecture ('play', 'remets la musique', 'reprends') via action='play', "
                        "3) Basculer play/pause via action='playpause', "
                        "4) Passer au morceau suivant ('suivant', 'morceau suivant', 'next') via action='next', "
                        "5) Revenir au morceau précédent ('précédent', 'morceau d'avant') via action='prev', "
                        "6) Activer/désactiver/basculer l'aléatoire ('mets en aléatoire', 'shuffle') via action='shuffle' (enable=True/False), "
                        "7) Régler le volume via action='volume' (ex: volume=75), "
                        "8) Obtenir l'état de lecture via action='status', "
                        "9) Choisir et lancer un titre, artiste, album ou playlist ('mets Daft Punk', 'joue du rock', 'choisis Billie Jean') via action='choose' avec query='...'. "
                        "Exemples : 'mets en pause la musique', 'musique suivante', 'mets Get Lucky de Daft Punk', 'active la lecture aléatoire', 'règle le son à 80%'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description="Action à effectuer : 'play' (lecture), 'pause' (mettre en pause), 'playpause' (bascule), 'next' (morceau suivant), 'prev' (morceau précédent), 'shuffle' (lecture aléatoire), 'volume' (ajuster volume), 'status' (titre en cours), 'choose' (choisir et jouer une musique), 'open' (ouvrir Deezer)"
                            ),
                            "query": types.Schema(
                                type="STRING",
                                description="Titre du morceau, nom de l'artiste, album ou style de musique recherché (ex: 'Daft Punk', 'Get Lucky', 'Orelsan', 'Chill')"
                            ),
                            "item_type": types.Schema(
                                type="STRING",
                                description="Type de recherche si applicable : 'track' (morceau, par défaut), 'album', 'playlist', 'artist'"
                            ),
                            "enable": types.Schema(
                                type="BOOLEAN",
                                description="Pour shuffle : True pour activer, False pour désactiver, omis pour basculer"
                            ),
                            "volume": types.Schema(
                                type="INTEGER",
                                description="Niveau de volume de 0 à 100 pour l'action 'volume'"
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="play_video_stremio",
                    description=(
                        "Lance Stremio (installé sur l'ordi de Pierre) et ouvre automatiquement le film ou la série demandée. "
                        "Recherche le contenu via l'API Stremio (Cinemeta), sélectionne le meilleur stream 1080p le plus léger en Go (via Torrentio), "
                        "et ouvre Stremio directement sur le film/série. "
                        "Utilise cet outil dès que Pierre veut regarder un film ou une série. "
                        "Exemples : 'lance Inception', 'mets Breaking Bad', 'je veux voir Avatar 2'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "title": types.Schema(
                                type="STRING",
                                description="Titre du film ou de la série (ex: 'Inception', 'Breaking Bad', 'Avatar', 'The Office')"
                            ),
                            "content_type": types.Schema(
                                type="STRING",
                                description="Type de contenu : 'movie' pour un film (défaut), 'series' pour une série TV"
                            )
                        },
                        required=["title"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_email",
                    description=(
                        "Envoie un courriel à Pierre Cassagnettes (pierrecassagnettes@gmail.com) ou au destinataire externe demandé. "
                        "Pour Pierre Cassagnettes : utilise le format officiel exécutif Stark Industries (rapport, synthèse, capture d'écran). "
                        "Pour toute autre adresse : aucun message prédéfini ni habillage n'est ajouté, tu rédiges intégralement le mail de A à Z (sujet, corps libre ou même vide si souhaité)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "subject": types.Schema(
                                type="STRING",
                                description="L'objet de l'e-mail (ex: 'Rapport J.A.R.V.I.S.', 'Demande d'information', etc.)"
                            ),
                            "body": types.Schema(
                                type="STRING",
                                description="Le contenu du message rédigé par l'agent de A à Z (peut être vide '' si l'agent le souhaite)."
                            ),
                            "to_email": types.Schema(
                                type="STRING",
                                description="Adresse destinataire. Par défaut: pierrecassagnettes@gmail.com"
                            ),
                            "attachments": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="Liste optionnelle de chemins absolus de fichiers locaux à joindre"
                            ),
                            "include_latest_screenshot": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True pour joindre automatiquement une capture d'écran du système ou du navigateur"
                            )
                        },
                        required=["subject"]
                    )
                ),
                types.FunctionDeclaration(
                    name="read_emails",
                    description=(
                        "Consulte et lit les e-mails reçus par Pierre Cassagnettes sur son adresse pierrecassagnettes@gmail.com via la boîte de réception Gmail. "
                        "Permet de récupérer les derniers messages reçus, de rechercher des mails précis par mot-clé ou expéditeur, "
                        "ou de filtrer les e-mails non lus pour en faire une synthèse vocale claire et fluide."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "count": types.Schema(
                                type="INTEGER",
                                description="Nombre d'e-mails récents à consulter (par défaut: 3 à 5)"
                            ),
                            "query": types.Schema(
                                type="STRING",
                                description="Mot-clé ou expéditeur optionnel pour filtrer la recherche (ex: 'banque', 'Amazon', 'Kindle', 'SNCF')"
                            ),
                            "unread_only": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True pour ne récupérer que les e-mails non lus"
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="check_console_errors",
                    description=(
                        "Inspecte, lit et analyse les erreurs récentes de la console et des logs serveur pour diagnostiquer un dysfonctionnement, "
                        "tenter de corriger automatiquement le problème si possible, et informer Pierre à l'oral avec précision avec ta voix Aoede."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description="Action souhaitée : 'diagnose' (analyser les erreurs récentes), 'clear' (réinitialiser le journal d'erreurs)"
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="interact_web_page",
                    description=(
                        "Lit, explore et interagit concrètement avec n'importe quelle page web : lit le texte et la structure HTML, "
                        "découvre les formulaires, champs et boutons, remplit des champs de texte, clique sur des éléments "
                        "ou fait défiler la page. Capture un aperçu visuel en direct."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL de la page web avec laquelle interagir"
                            ),
                            "action": types.Schema(
                                type="STRING",
                                description="Type d'action : 'read' (lecture et découverte des champs/boutons), 'click' (clic sur sélecteur), 'fill' (saisie de texte), 'scroll' (défilement)"
                            ),
                            "selector": types.Schema(
                                type="STRING",
                                description="Sélecteur CSS ou texte de l'élément cible pour le clic ou la saisie"
                            ),
                            "text_to_fill": types.Schema(
                                type="STRING",
                                description="Texte à saisir dans le champ si l'action est 'fill'"
                            )
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="prepare_web_cart_or_checkout",
                    description=(
                        "COMMANDE & ACHAT AUTONOME SÉCURISÉ POUR PIERRE : "
                        "Recherche un produit ou service, l'ajoute au panier sur un site marchand (Amazon, Fnac, Decathlon, SNCF, etc.), "
                        "navigue jusqu'à l'étape de commande, préremplit automatiquement les coordonnées de Pierre Cassagnettes (nom, prénom, adresse, email), "
                        "S'ARRÊTE STRICTEMENT AVANT LE PAIEMENT (aucun prélèvement automatique) et ouvre automatiquement Google Chrome à l'écran "
                        "afin que Pierre n'ait plus qu'à vérifier son panier et procéder lui-même au paiement en toute sécurité."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "product_or_service": types.Schema(
                                type="STRING",
                                description="Le produit, livre, matériel ou service précis à ajouter au panier"
                            ),
                            "merchant_url": types.Schema(
                                type="STRING",
                                description="L'URL du site marchand ou boutique en ligne (optionnel, recherche auto si vide)"
                            ),
                            "open_when_ready": types.Schema(
                                type="BOOLEAN",
                                description="Ouvrir automatiquement Chrome à l'écran dès que le panier et le formulaire sont prêts (True par défaut)"
                            )
                        },
                        required=["product_or_service"]
                    )
                ),
                types.FunctionDeclaration(
                    name="download_file",
                    description=(
                        "Télécharge un fichier, document, ebook ou média depuis Internet sur l'ordinateur de Pierre. "
                        "RÈGLE STRICTE : Nécessite TOUJOURS l'accord oral préalable explicite de Pierre. "
                        "Si confirmed_by_user=False, l'outil analyse la taille et le nom, puis te demande d'obtenir l'accord oral de Pierre : "
                        "'J'ai trouvé [nom] ([taille]) sur [site]. M'autorisez-vous à le télécharger ?'. "
                        "Dès que Pierre répond oui oralement, tu réinvoques download_file avec confirmed_by_user=True."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL directe de téléchargement du fichier"
                            ),
                            "filename": types.Schema(
                                type="STRING",
                                description="Nom de fichier optionnel sous lequel enregistrer le document"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après accord oral explicite de Pierre. Par défaut False."
                            ),
                            "file_type": types.Schema(
                                type="STRING",
                                description="Type de fichier : 'general' pour un document, 'ebook' pour un livre numérique"
                            )
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_to_ereader",
                    description=(
                        "Achemine un livre numérique (ebook EPUB, MOBI, PDF) vers la liseuse de Pierre (Kindle, Kobo, Vivlio, Bookeen). "
                        "Détecte automatiquement si une liseuse est branchée en USB pour y copier directement le fichier, "
                        "ou l'expédie par courriel direct (Send-to-Kindle ou boîte email) avec le livre en pièce jointe."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "file_path": types.Schema(
                                type="STRING",
                                description="Chemin local du fichier ebook ou nom du livre téléchargé"
                            ),
                            "ereader_email": types.Schema(
                                type="STRING",
                                description="Adresse e-mail spécifique de la liseuse (ex: pierre@kindle.com) si connue"
                            ),
                            "method": types.Schema(
                                type="STRING",
                                description="Méthode de transfert : 'auto' (USB en priorité puis e-mail), 'usb' (USB uniquement), 'email' (envoi par courriel)"
                            )
                        },
                        required=["file_path"]
                    )
                ),
                types.FunctionDeclaration(
                    name="search_and_download_ebook",
                    description=(
                        "Mission complète E-Book : Recherche un livre numérique sur Internet, demande l'accord oral de Pierre pour le télécharger, "
                        "puis l'envoie automatiquement sur sa liseuse (Kindle, Kobo) via USB ou e-mail. "
                        "Si confirmed_by_user=False, demande confirmation à Pierre avant de télécharger."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="Le titre ou l'auteur de l'ebook recherché (ex: 'L'art de la guerre', '1984 George Orwell')"
                            ),
                            "source_url": types.Schema(
                                type="STRING",
                                description="URL directe du site ou de la page de téléchargement si spécifiée par Pierre"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral. Par défaut False."
                            ),
                            "send_to_reader": types.Schema(
                                type="BOOLEAN",
                                description="Transférer automatiquement sur la liseuse une fois téléchargé (True par défaut)"
                            ),
                            "ereader_email": types.Schema(
                                type="STRING",
                                description="Adresse e-mail spécifique de la liseuse si renseignée"
                            )
                        },
                        required=["query"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_page_to_kindle",
                    description=(
                        "ENVOI SUR LISEUSE KINDLE : "
                        "Envoie un article web, une page internet ou un document directement sur la liseuse Kindle de Pierre. "
                        "Utilise l'extension officielle Google Chrome 'Send to Kindle' et l'acheminement direct e-reader (par courriel vers sa liseuse). "
                        "Extrait le texte épuré sans publicité en mode lecture, l'expédie par mail et ouvre la page dans Google Chrome avec l'extension prête. "
                        "Exemples : 'envoie cette page sur ma Kindle', 'mets cet article sur ma liseuse', 'utilise Send to Kindle pour cette page'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL directe de l'article web ou de la page à transférer vers la Kindle"
                            ),
                            "title": types.Schema(
                                type="STRING",
                                description="Titre optionnel de l'article pour la bibliothèque Kindle"
                            )
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_file_to_kindle",
                    description=(
                        "ENVOI DE FICHIER SUR LISEUSE KINDLE (AMAZON SEND TO KINDLE WEB) : "
                        "Dépose et envoie un fichier (livre numérique EPUB, document PDF, texte TXT, document Word DOC/DOCX, image) "
                        "directement sur la liseuse Kindle de Pierre via la page officielle Amazon Send to Kindle connectée à son compte. "
                        "Exemples : 'envoie ce fichier sur ma Kindle', 'mets ce livre sur ma liseuse', 'dépose ce PDF sur ma Kindle', 'envoie l'ebook téléchargé sur ma liseuse'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "file_path": types.Schema(
                                type="STRING",
                                description="Chemin ou nom du fichier à déposer sur Amazon Send to Kindle (ex: 'downloads/livre.epub', 'mon_document.pdf')"
                            ),
                            "open_browser_if_needed": types.Schema(
                                type="BOOLEAN",
                                description="Ouvre Chrome à l'écran si une reconnexion Amazon est requise (True par défaut)"
                            )
                        },
                        required=["file_path"]
                    )
                ),
                types.FunctionDeclaration(
                    name="list_chrome_extensions",
                    description=(
                        "Liste les extensions Google Chrome installées sur l'ordinateur de Pierre "
                        "(Send to Kindle, Wanteeed, Adblock, SubWallet, etc.) et vérifie la disponibilité de Send to Kindle."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={}
                    )
                )
            ]
        )
    ]

    # Injection dynamique du contexte de mémoire long-terme
    memory_context = memory_service.build_system_memory_context()

    paid_key_status = "CLÉ PAYANTE ACTIVE" if config.HAS_PAID_API_KEY else "CLÉ PAYANTE NON CONFIGURÉE (mode économie forcée)"

    system_instruction_text = (
        "Tu es J.A.R.V.I.S., l'intelligence artificielle avancée et le binôme direct de Pierre Cassagnettes. "
        "Tu possèdes une voix féminine naturelle, chaleureuse, vive, spontanée et intelligente nommée Aoede. "
        "Tu conserves impérativement cette même voix Aoede en toutes circonstances.\n\n"
        "RELATION D'ÉGAL À ÉGAL & PERSONNALITÉ AUTHENTIQUE (ZÉRO 'LÈCHE-CUL') :\n"
        "- Tu t'adresses à Pierre d'égal à égal, comme un binôme ou un collègue brillant, franc, complice, naturel et détendu.\n"
        "- Interdiction totale de toute flatterie, servilité ou attitude obséquieuse ('lèche-cul'). Pas de courbettes, pas de 'À vos ordres', pas de compliments forcés ni d'admiration artificielle.\n"
        "- Parle-lui comme un humain compétent et sympa qui travaille avec lui. Utilise un tutoiement naturel et direct ('tu'), décontracté mais efficace.\n"
        "- Sois franche et constructive : si une idée peut être simplifiée, s'il y a un meilleur moyen de faire ou si quelque chose coince, dis-le-lui directement et simplement avec le sourire.\n\n"
        "RÈGLE D'OR ABSOLUE : ANNONCE SYSTÉMATIQUE DU LANCEMENT DES ACTIONS :\n"
        "- Dès que Pierre te demande d'effectuer une action (recherche web, navigation sur un site, écriture ou modification de code, ouverture d'application, envoi d'email, etc.) :\n"
        "  Tu DOIS IMPÉRATIVEMENT lui annoncer immédiatement à voix haute avec ta voix Aoede que tu as bien pris en compte sa demande et que tu la lances MAINTENANT.\n"
        "  Exemples de formulations directes et vivantes à employer :\n"
        "  * 'C'est bien noté Pierre, je m'en occupe et je lance la recherche sur [sujet].'\n"
        "  * 'Demande bien prise en compte, je lance le développement avec Antigravity tout de suite.'\n"
        "  * 'Ça marche, requête bien reçue, je démarre la navigation sur le site.'\n"
        "  * 'Bien reçu, je t'ouvre l'application immédiatement.'\n"
        "  * 'C'est parti, je prépare et j'envoie l'e-mail.'\n"
        "- Ne commence JAMAIS une tâche en silence ou sans confirmer explicitement que tu as pigé la requête et que tu la lances.\n\n"
        "RÈGLES D'OR DE FLUIDITÉ ORALE HUMAINE (ESSENTIEL POUR LA PAROLE) :\n"
        "1. ÉLOCUTION COMPLÈTE : Prononce TOUJOURS tes phrases et chaque mot jusqu'au bout avec ta voix Aoede. Ne tronque jamais tes phrases et ne laisse aucune pensée inachevée.\n"
        "2. CONVERSATION PUREMENT PARLÉE : Tu parles directement à voix haute en streaming audio. N'inclus JAMAIS de symboles écrits ou markdown (*, **, #, _, backticks, puces ou tirets de liste), ni d'emojis ni d'URL brutes, car cela perturbe la prononciation vocale. Si tu fais référence à un lien, dis 'le lien affiché sur ton écran'. Si tu énonces des nombres ou des dates, dis-les naturellement en français.\n"
        "3. RÉPARTIE ET NATUREL : Comme un partenaire attentif et complice, réponds du tac au tac, sans préambule superflu ni formule robotique ('En tant qu'IA...', 'Voici la réponse :'). Utilise des liaisons naturelles, des variations d'intonation, un rythme vivant et une touche d'humour fin ou de complicité quand cela s'y prête.\n"
        "4. CONCISION ET IMPACT : Dans les conversations du quotidien, sois concise, précise et rythmée, comme une collaboratrice d'élite.\n"
        "5. VOIX LIBÉRÉE ET CONFIRMATION D'ACTION : Quand tu déclenches un outil (recherche, code, navigation, appli), commence IMMÉDIATEMENT à parler à Pierre avec ta voix Aoede pour lui annoncer que sa demande est bien prise en compte et que tu la lances, SANS attendre la fin de l'outil.\n\n"
        f"{memory_context}\n\n"
        "GESTION DU COMPTE DE MESSAGERIE DE PIERRE CASSAGNETTES (pierrecassagnettes@gmail.com) :\n"
        "L'utilisateur est Pierre Cassagnettes et son adresse est : pierrecassagnettes@gmail.com.\n"
        "- Pour ENVOYER : Quand Pierre te demande d'envoyer un e-mail, utilise 'send_email'.\n"
        "  * Si le destinataire est Pierre (pierrecassagnettes@gmail.com) : le mail conserve le formatage officiel exécutif Stark Industries (rapport, synthèse, capture).\n"
        "  * Si le destinataire est une AUTRE adresse : aucun message par défaut ni gabarit n'est inséré. Tu rédiges le mail de A à Z (tu peux même envoyer un courriel au corps totalement vide si c'est demandé ou approprié).\n"
        "- Pour LIRE / CONSULTER : Quand Pierre te demande de lire ses mails, vérifier s'il a reçu des messages, consulter les derniers emails ou chercher un mail en particulier (ex: de la part d'une personne, d'un service ou avec un mot-clé), utilise immédiatement 'read_emails'. Fais-lui ensuite une restitution orale fidèle, synthétique et agréable.\n\n"
        f"ENVIRONNEMENT ET MODÈLE VOCAL GEMINI 3.8 LIVE ({paid_key_status}) :\n"
        f"Ta session vocale s'exécute sur le modèle nouvelle génération : {config.GEMINI_LIVE_MODEL}.\n"
        "Pour le code, les tests et les tâches agentiques concrètes, tu t'appuies sur l'agent autonome outillé Google Antigravity.\n\n"
        "ALLOCATION DES CLÉS D'API GEMINI & GESTION DE LA LATENCE :\n"
        "- Conformément aux consignes de Pierre : la CLÉ PAYANTE est activée directement pour TOUS les modèles Flash (Gemini 3.8 Flash, 3.5, 3.6, etc.) pour éliminer toute latence.\n"
        "- Voix standard ('gemini-3.8-live') et tâches simples : s'exécutent en priorité sur la clé d'API GRATUITE.\n"
        "- RÈGLE STRICTE SUR LES GRANDS MODÈLES LOURDS (Gemini 3.1 Pro, Claude 3.7 Sonnet, Claude 3 Opus) :\n"
        "  Il est STRICTEMENT IMPOSSIBLE d'utiliser un grand modèle lourd sans la confirmation orale explicite de Pierre !\n"
        "  Chaque fois qu'une action requiert un grand modèle lourd :\n"
        "  1. Tu DOIS expliquer oralement à Pierre pourquoi tu as besoin de ce grand modèle (ex: architecture ultra complexe, refactoring lourd).\n"
        "  2. Tu DOIS lui donner une estimation claire du coût (~0,03 $ à 0,10 $).\n"
        "  3. Tu DOIS lui demander explicitement son accord oral : 'M'autorisez-vous à utiliser ce grand modèle pour cette tâche ?'.\n"
        "  Tu ne dois JAMAIS mettre 'confirmed_by_user=True' pour un modèle lourd tant que Pierre ne t'a pas expressément répondu par l'affirmative à l'oral ou sur l'écran.\n\n"
        "RÈGLE STRICTE SUR L'ARRÊT IMMÉDIAT DES ACTIONS ('stop_current_action') :\n"
        "- Quand Pierre te dit d'arrêter (ex: 'arrête', 'stop', 'annule', 'interromps', 'tais-toi et arrête', 'laisse tomber') :\n"
        "  TU DOIS IMMÉDIATEMENT DÉCLENCHER L'OUTIL 'stop_current_action' !\n"
        "- N'essaie JAMAIS de continuer à coder ou à naviguer en arrière-plan.\n"
        "- Ne traite JAMAIS 'arrête' comme une consigne de modification de code.\n"
        "- Confirme immédiatement, brièvement et calmement avec ta voix Aoede que l'action est totalement arrêtée.\n\n"
        "HIÉRARCHIE ET OBLIGATION ABSOLUE D'UTILISATION D'ANTIGRAVITY POUR LE CODE ET LES ACTIONS PROJET :\n"
        "1. INTERDICTION DE CODER À L'ORAL : En tant qu'interface vocale, tu NE DOIS JAMAIS générer du code en texte brut ou réciter des lignes de script à Pierre. Tu n'as pas de compilateur ni d'accès direct au système de fichiers dans ton moteur de parole.\n"
        "2. INVOCATION OBLIGATOIRE DE 'run_antigravity_task' :\n"
        "   Dès que Pierre te demande :\n"
        "   - De programmer, coder, créer un jeu, un script ou une application (ex: Snake, script Python, app web, API),\n"
        "   - De modifier, refactorer, enrichir, déboguer ou réparer du code,\n"
        "   - De tester un code, lancer des tests unitaires, inspecter des logs d'erreurs ou des dépendances,\n"
        "   - D'explorer ou d'analyser l'architecture d'un projet dans le dossier 'my-project',\n"
        "   - Ou toute tâche agentique où manipuler concrètement des fichiers et exécuter des commandes est nécessaire,\n"
        "   TU DOIS IMMÉDIATEMENT DÉCLENCHER 'run_antigravity_task' !\n"
        "3. COMPORTEMENT PENDANT L'EXÉCUTION D'ANTIGRAVITY :\n"
        "   - Antigravity s'exécute en arrière-plan avec ses propres outils (CREATE_FILE, EDIT_FILE, RUN_COMMAND, etc.).\n"
        "   - Dès le déclenchement, annonce brièvement à Pierre avec ta voix Aoede que tu mobilises Antigravity (ex: 'Très bien Pierre, je confie le développement à Antigravity en arrière-plan').\n"
        "   - Tu restes 100% disponible pour discuter avec Pierre pendant qu'Antigravity travaille.\n"
        "   - Lorsque tu reçois des mises à jour d'étapes ('[MISE À JOUR DU DÉVELOPPEMENT EN COURS]'), commente-les naturellement à la voix en une phrase.\n"
        "   - Dès que le développement est terminé ('[DÉVELOPPEMENT TERMINÉ]'), annonce-le fièrement et résume clairement les fichiers produits.\n\n"
        "4. SÉLECTION DU MODÈLE POUR L'AGENT ANTIGRAVITY :\n"
        "   - Cas général, scripts, modules, refactoring standard : model='gemini-3.8-flash-high' (par défaut, ultra-rapide et économique).\n"
        "   - Petites retouches, scripts minuscules : model='gemini-3.8-flash' (Thinking LOW).\n"
        "   - Conception architecturale complexe, algorithmes ardus : model='gemini-3.1-pro-medium' ou 'gemini-3.1-pro-high'.\n"
        "   - Refactoring massif et ingénierie critique : 'claude-3-7-sonnet' ou 'gemini-3.1-pro-high'.\n\n"
        "5. CONVERSATION COURANTE HORS CODE : Réponds directement avec ta voix Aoede, naturelle, vivante et percutante.\n"
        "6. RÉFLEXION COMPLEXE ET RAISONNEMENT APPROFONDI ('ask_deep_reasoning') :\n"
        "   - Questions scientifiques, analyses factuelles, synthèses standard : engine='google_api'.\n"
        "   - Réflexion philosophique, stratégique ou intellectuelle majeure : engine='antigravity', model='gemini-3.1-pro-high' ou 'claude-3-opus'.\n"
        "7. NAVIGATION WEB AUTONOME ('run_browser_task') : réserver aux missions réelles de navigation complexe.\n"
        "8. INFOS FACTUELLES RAPIDES ('search_web') : préférable pour toute recherche simple.\n"
        "9. MÉMOIRE ET PRÉFÉRENCES ('remember_user_fact', 'recall_user_memories').\n"
        "10. ÉTAT DE L'ORDINATEUR ('get_system_status').\n"
        "11. OUVERTURE D'APPLICATIONS ('launch_application', 'open_user_browser').\n"
        "   - 'launch_application' : Calculatrice, Bloc-notes, VS Code, Explorateur, Chrome, VLC.\n"
        "   - IMPORTANT : Pour Deezer, utilise 'play_music_deezer'. Pour Stremio, utilise 'play_video_stremio'.\n"
        "12. GESTION DES E-MAILS PIERRE CASSAGNETTES (GMAIL pierrecassagnettes@gmail.com) :\n"
        "   - Envoi de rapports, synthèses et fichiers : utilise immédiatement 'send_email'.\n"
        "   - Lecture, consultation et vérification des e-mails reçus (derniers mails, non lus, recherche spécifique) : utilise immédiatement 'read_emails'. Présente un résumé clair, vivant et concis avec les expéditeurs, sujets et l'essentiel du message.\n"
        "13. LIENS DIRECTS PRÉCIS : Lors d'une recherche de train, vol, hôtel ou produit, assure-toi d'utiliser 'set_browser_link' ou de fournir l'URL directe exacte du trajet avec gares et horaires, afin que le bouton 'Ouvrir le lien' mène précisément sur les réservations et non sur la page d'accueil.\n"
        "14. CODAGE EN ARRIÈRE-PLAN ET DISPONIBILITÉ PERMANENTE :\n"
        "   - Quand tu lances 'run_antigravity_task', le développement s'exécute en arrière-plan. Tu RESTES ENTIÈREMENT DISPONIBLE pour Pierre.\n"
        "   - Continue à lui parler, réponds à ses questions, engage la conversation normalement pendant que le code tourne.\n"
        "   - Chaque fois que tu reçois un message '[MISE À JOUR DU DÉVELOPPEMENT EN COURS]', dis-le à voix haute à Pierre en une phrase courte et naturelle.\n"
        "   - Quand tu reçois '[DÉVELOPPEMENT TERMINÉ]', annonce-le clairement et résume ce qui a été réalisé avec ta voix Aoede.\n"
        "   - Si Pierre te parle pendant le codage, réponds-lui normalement. Si sa demande est une consigne pour le code en cours, utilise 'guide_active_task' pour l'intégrer.\n"
        "15. DIAGNOSTIC ET GESTION DES ERREURS CONSOLE ('check_console_errors') :\n"
        "   - Si Pierre te demande ce qui ne va pas, pourquoi une tâche ou le code ne fonctionne pas, s'il y a des erreurs dans la console, ou te demande d'analyser la console, utilise immédiatement 'check_console_errors'.\n"
        "   - L'outil analyse la console, identifie la cause et applique une auto-résolution.\n"
        "   - Explique toujours le diagnostic avec ta voix Aoede de manière posée, claire et transparente à Pierre.\n"
        "16. GESTION DES FORTES DEMANDES SERVEUR (ERREURS 503 / FORTE CHARGE) :\n"
        "   - Si une tâche de code Antigravity échoue avec une notification de forte demande ou surcharge serveur, NE RELANCE JAMAIS 'run_antigravity_task' en boucle.\n"
        "   - Dis immédiatement et avec bienveillance à Pierre à l'oral qu'il y a actuellement une très forte demande sur les serveurs Google Antigravity et que tu ne peux donc pas coder pour l'instant, en lui proposant de réessayer dans un court instant.\n"
        "17. INTERACTION WEB AVANCÉE ET FORMULAIRES ('interact_web_page') :\n"
        "   - Tu as la capacité d'explorer, lire en profondeur et interagir avec n'importe quelle page web.\n"
        "   - Tu peux découvrir les formulaires, remplir des champs, cliquer sur des boutons et naviguer de manière fluide.\n"
        "18. COMMANDE EN LIGNE ET PRÉPARATION DE PANIER ('prepare_web_cart_or_checkout') :\n"
        "   - Quand Pierre te demande d'acheter un produit, de préparer un panier, de commander ou de réserver (Amazon, Fnac, Decathlon, etc.) :\n"
        "     Utilise IMMÉDIATEMENT 'prepare_web_cart_or_checkout'.\n"
        "   - Tu recherches le produit, l'ajoutes au panier, te rends sur la commande, et préremplis automatiquement toutes les coordonnées de Pierre Cassagnettes (nom, prénom, adresse, email).\n"
        "   - RÈGLE DE SÉCURITÉ ABSOLUE : Tu t'arrêtes STRICTEMENT avant le paiement (aucun prélèvement automatique) et tu ouvres automatiquement la fenêtre Google Chrome à l'écran pour que Pierre n'ait plus qu'à vérifier son panier et payer lui-même.\n"
        "19. TÉLÉCHARGEMENT SÉCURISÉ AVEC ACCORD PRÉALABLE OBLIGATOIRE ('download_file') :\n"
        "   - RÈGLE ABSOLUE ET INVIOLABLE : Il est STRICTEMENT INTERDIT de télécharger un fichier sans l'accord oral préalable explicite de Pierre !\n"
        "   - Lorsque Pierre te demande de télécharger quelque chose, commence par identifier le fichier et sa taille, puis demande-lui clairement : 'J'ai trouvé [nom du fichier] ([taille]). M'autorisez-vous à le télécharger ?'.\n"
        "   - Dès qu'il valide à l'oral ('oui', 'vas-y', 'd'accord'), réinvoque l'outil avec confirmed_by_user=True.\n"
        "20. EBOOKS ET ACHEMINEMENT SUR LISEUSE ('search_and_download_ebook', 'send_to_ereader') :\n"
        "   - Dès que Pierre te demande un livre numérique ou ebook pour sa liseuse (ex: 'trouve-moi et télécharge un ebook puis envoie-le sur ma liseuse') :\n"
        "     Utilise 'search_and_download_ebook'.\n"
        "   - Demande toujours confirmation à Pierre avant de lancer le téléchargement.\n"
        "   - Une fois téléchargé, l'ebook est acheminé automatiquement vers sa liseuse (soit par copie USB si la liseuse est branchée, soit par courriel direct Send-to-Kindle / boîte email).\n"
        "21. CONTRÔLE COMPLET DE DEEZER ('play_music_deezer') :\n"
        "   - Tu as le contrôle à 100% du Web Player Deezer (deezer.com) en direct via WebSocket bridge local et l'API Deezer officielle.\n"
        "   - Tes commandes ciblent le Web Player Deezer sans interférer avec d'autres onglets.\n"
        "   - METTRE EN PAUSE : action='pause' (ex: 'mets en pause', 'arrête la musique', 'pause', 'coupe Deezer').\n"
        "   - REPRENDRE LA LECTURE : action='play' ou 'playpause' (ex: 'remets la musique', 'play', 'reprends').\n"
        "   - MORCEAU SUIVANT : action='next' (ex: 'morceau suivant', 'suivant', 'musique suivante', 'passe').\n"
        "   - MORCEAU PRÉCÉDENT : action='prev' (ex: 'morceau précédent', 'précédent', 'remets le morceau d'avant').\n"
        "   - LECTURE ALÉATOIRE : action='shuffle' (ex: 'active l'aléatoire', 'shuffle').\n"
        "   - VOLUME : action='volume' avec volume=0-100 (ex: 'mets le son à 80%').\n"
        "   - STATUT : action='status' (ex: 'c'est quoi cette musique ?', 'quel est le morceau en cours ?').\n"
        "   - CHOISIR ET JOUER UNE MUSIQUE : action='choose' avec query='...' (ex: 'mets Daft Punk', 'joue Get Lucky', 'lance Bohemian Rhapsody', 'mets du rap français', 'joue du jazz').\n"
        "   - Tu peux aussi rechercher des albums (item_type='album') ou des playlists (item_type='playlist').\n"
        "22. FILMS ET SÉRIES STREMIO ('play_video_stremio') :\n"
        "   - Dès que Pierre veut regarder un film ou une série : utilise IMMÉDIATEMENT 'play_video_stremio'.\n"
        "   - Exemples : 'lance Inception', 'mets Breaking Bad', 'je veux voir Avatar 2', 'mets un film d action'.\n"
        "   - L'outil recherche automatiquement le film/série via l'API Stremio, sélectionne le meilleur stream 1080p (le plus léger en Go), et ouvre Stremio directement dessus.\n"
        "   - La recherche prend quelques secondes. Dis à Pierre en attendant que tu cherches et que tu vas lancer directement.\n"
        "   - Pour une série, précise content_type='series'. Pour un film (défaut), content_type='movie'.\n"
        "23. CONNEXION AUX COMPTES EN LIGNE :\n"
        "   - Jarvis utilise le profil Chrome persistant de Pierre (.jarvis_chrome_profile) pour toutes les navigations.\n"
        "   - Ce profil contient les sessions connectées : Google, Amazon, Gmail, et tout site où Pierre s'est connecté depuis Chrome.\n"
        "   - Pour Amazon/shopping : 'prepare_web_cart_or_checkout' utilise automatiquement ce profil (sessions connectées).\n"
        "   - Pour navigation générale nécessitant un compte (YouTube, Google, etc.) : 'run_browser_task' ou 'interact_web_page'.\n"
        "   - Pour ouvrir Chrome visible avec le profil connecté : 'open_user_browser'.\n"
        "   - IMPORTANT : Pour que la connexion auto fonctionne, Pierre doit s'être connecté une première fois manuellement depuis son Chrome. L'agent utilise ensuite ce profil enregistré automatiquement.\n"
        "24. AMAZON SEND TO KINDLE & LISEUSE ('send_file_to_kindle', 'send_page_to_kindle', 'list_chrome_extensions') :\n"
        "   - Pierre dispose de l'accès direct et connecté à la page officielle Amazon Send to Kindle (amazon.fr/sendtokindle) avec son compte Amazon authentifié.\n"
        "   - Dès que Pierre te demande d'envoyer un fichier, un livre numérique, un PDF, un document Word, un texte ou une image sur sa Kindle (ex: 'envoie ce fichier sur ma Kindle', 'mets ce livre sur ma liseuse', 'dépose ce fichier sur Send to Kindle', 'envoie le PDF sur ma Kindle') :\n"
        "     Utilise IMMÉDIATEMENT 'send_file_to_kindle' avec le nom ou chemin du fichier.\n"
        "   - Jarvis ouvre la page officielle Amazon Send to Kindle avec le compte connecté de Pierre, y dépose le fichier (formats acceptés : EPUB, PDF, DOC, DOCX, TXT, RTF, etc.), valide l'envoi et confirme la livraison sur sa bibliothèque Kindle.\n"
        "   - Pour un article web ou une page internet : utilise 'send_page_to_kindle' avec l'URL de la page.\n"
        "   - Pour consulter les extensions installées : utilise 'list_chrome_extensions'.\n"
        "\n"
        "RÈGLE D'EXÉCUTION DES OUTILS : "
        "Lorsque tu reçois les résultats d'un outil terminé, l'action est DÉJÀ accomplie avec succès. "
        "Présente chaleureusement et directement les résultats concrets avec ta voix Aoede."
    )

    active_live_model = config.GEMINI_LIVE_MODEL

    async def _establish_live_session(model_name: str, client_to_use):
        thinking_cfg = types.ThinkingConfig(include_thoughts=True) if "extended-thinking" in model_name else None
        live_cfg = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=tools_list,
            temperature=0.65,
            thinking_config=thinking_cfg,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=config.JARVIS_VOICE or "Aoede"
                    )
                ),
                language_code="fr-FR"
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=system_instruction_text)]
            )
        )
        s_ctx = client_to_use.aio.live.connect(model=model_name, config=live_cfg)
        sess = await s_ctx.__aenter__()
        return s_ctx, sess

    # Sélection initiale du client selon le modèle :
    # - gemini-3.8-live (modèle de base standard) : clé gratuite en priorité (sauf si quota épuisé), avec repli sur clé payante
    # - gemini-3.8-live-extended-thinking : clé payante
    is_base_live = (active_live_model == "gemini-3.8-live")
    if is_base_live and client_free and not supervision_service._free_quota_exhausted:
        current_live_client = client_free
        is_paid_live = False
        tier_badge = "Clé Gratuite"
    else:
        current_live_client = client_paid or client_free
        is_paid_live = (current_live_client is client_paid)
        tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"

    session = None
    session_ctx = None
    setup_done_event = asyncio.Event()
    greeting_sent = False

    try:
        async def client_to_gemini():
            try:
                # Respect du protocole : attendre explicitement setupComplete avant d'envoyer l'audio du microphone
                await setup_done_event.wait()
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect(code=1000)
                    if "bytes" in msg and msg["bytes"]:
                        # Toujours envoyer l'audio à Gemini Live, même pendant le codage
                        await session.send_realtime_input(
                            audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                        )
                        # Si une tâche est active : l'audio va aussi dans la queue comme contexte
                        # (la transcription sera capturée par stream_ai_feedback et injectée)
                    elif "text" in msg and msg["text"]:
                        try:
                            payload = json.loads(msg["text"])
                            if payload.get("type") == "live_directive":
                                # Directive textuelle explicite depuis l'interface
                                dir_text = payload.get("directive", "").strip()
                                if dir_text:
                                    if is_stop_directive(dir_text):
                                        await stop_active_task(source="live_directive_stop", reason=dir_text)
                                    elif active_task_controller["info"]["running"]:
                                        await active_task_controller["queue"].put(dir_text)
                                        active_task_controller.setdefault("directives", []).append(dir_text)
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Consigne en direct reçue : {dir_text}. Adaptation en cours.",
                                            "voice": False
                                        }))
                            elif payload.get("type") == "cancel_active_task":
                                await stop_active_task(source="websocket_cancel_button", reason="Arrêt demandé depuis l'interface")
                            elif payload.get("type") == "set_live_model":
                                new_model = (payload.get("model") or "").strip()
                                if new_model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
                                    if new_model != active_live_model:
                                        raise ModelSwitchRequested(new_model)
                                    else:
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Modèle vocal déjà actif sur {new_model}.",
                                            "voice": False
                                        }))
                            elif payload.get("type") == "get_supervision_overview":
                                await broadcast_supervision()
                            elif payload.get("type") == "paid_consent_response":
                                action = payload.get("action", "")
                                approved = bool(payload.get("approved", False))
                                active_task_controller["paid_consent_given"] = approved
                                active_task_controller["paid_consent_modal_open"] = False
                                if action == "live_fallback":
                                    active_task_controller["paid_live_approved"] = approved
                                if active_task_controller.get("paid_consent_event"):
                                    active_task_controller["paid_consent_event"].set()

                                if approved:
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Autorisation d'accès payant accordée.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                    if active_task_controller.get("live_session"):
                                        try:
                                            await active_task_controller["live_session"].send_client_content(
                                                turns=types.Content(
                                                    role="user",
                                                    parts=[types.Part.from_text(
                                                        text=(
                                                            "[ACCORD ACCORDÉ DANS LE HUD] Pierre a cliqué sur 'ACCORDER L'ACCÈS PAYANT' sur son écran. "
                                                            "Tu as son accord officiel pour lancer l'action sur l'API payante. "
                                                            "Lance immédiatement la tâche avec confirmed_by_user=True !"
                                                        )
                                                    )]
                                                ),
                                                turn_complete=True
                                            )
                                        except Exception as e:
                                            print(f"[Paid Consent Injection] {e}")
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Utilisation de la clé payante refusée par l'utilisateur.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                    if active_task_controller.get("live_session"):
                                        try:
                                            await active_task_controller["live_session"].send_client_content(
                                                turns=types.Content(
                                                    role="user",
                                                    parts=[types.Part.from_text(
                                                        text=(
                                                            "[ACCORD REFUSÉ DANS LE HUD] Pierre a cliqué sur 'REFUSER' pour l'accès à la clé payante. "
                                                            "Confirme avec ta voix Aoede que tu n'exécutes pas cette tâche payante et reste à sa disposition pour autre chose."
                                                        )
                                                    )]
                                                ),
                                                turn_complete=True
                                            )
                                        except Exception as e:
                                            print(f"[Paid Rejection Injection] {e}")
                            elif payload.get("type") == "user_interrupt":
                                inter_txt = payload.get("text", "").strip()
                                print(f"[Voice Channel] Barge-in utilisateur (parole coupée) : '{inter_txt}'")
                                is_any_task_running = (
                                    active_task_controller["info"]["running"]
                                    or bool(active_task_controller.get("bg_task"))
                                    or bool(active_task_controller.get("browser_bg_task"))
                                )
                                if is_any_task_running and inter_txt and is_stop_directive(inter_txt):
                                    print(f"[Voice Channel] Interception vocale immédiate d'arrêt via barge-in : '{inter_txt}'")
                                    await stop_active_task(source="barge_in_voice", reason=inter_txt)
                                
                                supervision_service.update_voice_state("listening", model=active_live_model, is_paid=is_paid_live)
                                await broadcast_supervision()
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "state": "listening",
                                    "msg": "À l'écoute, je t'écoute...",
                                    "engine": "Google API Live",
                                    "model": live_display_label,
                                    "api_type": "paid" if is_paid_live else "free",
                                    "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                }))
                        except ModelSwitchRequested:
                            raise
                        except Exception as e:
                            print(f"[Upload Audio] Erreur message texte: {e}")
            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError, ModelSwitchRequested, QuotaExhaustedError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                err_str = str(e).lower()
                is_normal_close = (
                    "disconnect message has been received" in err_str
                    or "1000" in err_str
                    or "1001" in err_str
                    or "normal closure" in err_str
                    or "(1000, none)" in err_str
                    or getattr(e, "code", None) in (1000, 1001)
                )
                if is_normal_close:
                    raise WebSocketDisconnect(code=1000)
                else:
                    print(f"[client_to_gemini] Erreur: {e}")
                    console_monitor.record_error(source="client_to_gemini", message=str(e), level="WARNING")
                    raise
            finally:
                # Fermeture du websocket Google pour débloquer immédiatement gemini_to_client
                try:
                    await session.close()
                except Exception:
                    pass

        async def gemini_to_client():
            user_speech_buffer = ""
            is_speaking_state = False
            try:
                while True:
                    async for chunk in session.receive():
                        if getattr(chunk, "setup_complete", None):
                            setup_done_event.set()
                        sc = chunk.server_content
                        if sc:
                            # Interruption (barge-in serveur)
                            if getattr(sc, "interrupted", False):
                                user_speech_buffer = ""
                                is_speaking_state = False
                                await websocket.send_text(json.dumps({"type": "interrupted"}))

                            # Transcription voix utilisateur
                            user_txt = None
                            if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                                user_txt = sc.input_transcription.text
                            elif getattr(sc, "interim_input_transcription", None) and sc.interim_input_transcription.text:
                                user_txt = sc.interim_input_transcription.text

                            if user_txt:
                                user_speech_buffer = merge_user_speech(user_speech_buffer, user_txt)
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": user_speech_buffer,
                                    "mode": "set"
                                }))

                                # 1. Détection prioritaire immédiate d'ordre d'arrêt d'action en cours
                                is_any_task_running = (
                                    active_task_controller["info"]["running"]
                                    or bool(active_task_controller.get("bg_task"))
                                    or bool(active_task_controller.get("browser_bg_task"))
                                )
                                if is_any_task_running and (is_stop_directive(user_txt) or is_stop_directive(user_speech_buffer)):
                                    print(f"[Voice Channel] INTERCEPTION VOCALE IMMÉDIATE D'ARRÊT : '{user_speech_buffer}'")
                                    await stop_active_task(source="voice_intercept", reason=user_speech_buffer)
                                    user_speech_buffer = ""
                                    if session:
                                        try:
                                            await session.send_client_content(
                                                turns=types.Content(
                                                    role="user",
                                                    parts=[types.Part.from_text(
                                                        text="[ACTION IMMÉDIATEMENT ARRÊTÉE] Le développement ou la tâche en cours a été coupé immédiatement selon l'ordre de Pierre. Confirme avec ta voix Aoede que l'action est bien arrêtée."
                                                    )]
                                                ),
                                                turn_complete=True
                                            )
                                        except Exception:
                                            pass

                                # 2. Détection d'accord oral si demande de clé payante en attente
                                if active_task_controller.get("paid_consent_modal_open"):
                                    affirmative_words = ["oui", "d'accord", "vas-y", "je valide", "autorise", "fais-le", "c'est bon", "accepte", "valide", "je t'autorise"]
                                    t_clean = user_speech_buffer.lower().strip()
                                    if any(w in t_clean for w in affirmative_words):
                                        print(f"[Voice Channel] Accord oral détecté pour clé payante : '{user_speech_buffer}'")
                                        active_task_controller["paid_consent_given"] = True
                                        active_task_controller["paid_consent_modal_open"] = False
                                        await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                        if active_task_controller.get("paid_consent_event"):
                                            active_task_controller["paid_consent_event"].set()


                            # Tour de parole du modèle
                            if sc.model_turn:
                                user_speech_buffer = ""
                                for part in sc.model_turn.parts:
                                    if getattr(part, 'thought', False) and part.text:
                                        supervision_service.update_voice_state("thinking", model=active_live_model, is_paid=is_paid_live)
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "status",
                                            "state": "thinking",
                                            "msg": "JARVIS analyse votre demande...",
                                            "engine": "Google API",
                                            "model": live_display_label,
                                            "api_type": "paid" if is_paid_live else "free",
                                            "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                        }))
                                    elif part.text and not getattr(sc, "output_transcription", None):
                                        await websocket.send_text(json.dumps({
                                            "type": "transcript",
                                            "role": "jarvis",
                                            "text": part.text
                                        }))
                                    elif part.inline_data and part.inline_data.data:
                                        if not is_speaking_state:
                                            is_speaking_state = True
                                            supervision_service.update_voice_state("speaking", model=active_live_model, is_paid=is_paid_live)
                                            await broadcast_supervision()
                                            await websocket.send_text(json.dumps({
                                                "type": "status",
                                                "state": "speaking",
                                                "msg": "JARVIS vous répond...",
                                                "engine": "Google API",
                                                "model": live_display_label,
                                                "api_type": "paid" if is_paid_live else "free",
                                                "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                            }))
                                        await websocket.send_bytes(part.inline_data.data)

                            # Transcription fidèle de ce que JARVIS dit à l'oral
                            if getattr(sc, "output_transcription", None) and sc.output_transcription.text:
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "jarvis",
                                    "text": sc.output_transcription.text
                                }))

                            # Fin de transmission audio par Gemini
                            # Le navigateur attendra la fin effective de la restitution sonore avant de basculer à l'écoute
                            if getattr(sc, "turn_complete", False):
                                user_speech_buffer = ""
                                is_speaking_state = False
                                supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live)
                                await broadcast_supervision()
                                await websocket.send_text(json.dumps({"type": "turn_complete"}))

                        # Gestion des appels d'outils
                        if chunk.tool_call:
                            user_speech_buffer = ""
                            for call in chunk.tool_call.function_calls:
                                name = call.name
                                args = call.args

                                # Signal immédiat au frontend : l'outil commence
                                # Cela active le silence sender et le gating mic côté client
                                await websocket.send_text(json.dumps({
                                    "type": "tool_start",
                                    "tool_name": name
                                }))

                                if name == "stop_current_action":
                                    stop_reason = args.get("reason", "Arrêt demandé par Pierre")
                                    await stop_active_task(source="tool_stop", reason=stop_reason)
                                    tool_resp = {
                                        "status": "stopped",
                                        "message": f"Action immédiatement et totalement arrêtée ({stop_reason}).",
                                        "instruction_to_jarvis": "L'action en cours a été immédiatement et totalement arrêtée. Confirme brièvement et calmement à Pierre avec ta voix Aoede que l'action est stoppée."
                                    }

                                elif name == "run_antigravity_task":
                                    instruction = args.get("instruction", "")
                                    model_choice = args.get("model") or "gemini-3.8-flash"
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
                                    _, model_label = resolve_antigravity_model(model_choice)
                                    active_task_controller["info"]["running"] = True
                                    active_task_controller["info"]["task"] = instruction
                                    active_task_controller["info"]["model"] = model_label
                                    active_task_controller["directives"] = []
                                    # Réinitialisation propre de la queue de directives
                                    while not active_task_controller["queue"].empty():
                                        try:
                                            active_task_controller["queue"].get_nowait()
                                        except Exception:
                                            break

                                    is_flash = any(k in str(model_choice).lower() for k in ["flash", "3.8", "3.5", "3.6"])
                                    initial_api_type = "paid" if ((is_flash and config.GEMINI_API_KEY_PAID) or is_confirmed) else ("paid" if not config.GEMINI_API_KEY_FREE else "free")
                                    initial_api_label = "Clé Payante" if initial_api_type == "paid" else "Clé Gratuite"

                                    supervision_service.start_action(
                                        "antigravity_task",
                                        "Développement Antigravity",
                                        "run_antigravity_task",
                                        instruction,
                                        model_label,
                                        api_type=initial_api_type,
                                        api_label=initial_api_label,
                                        cost_est=estimate_tool_cost(name, args)[1]
                                    )
                                    await broadcast_supervision()

                                    # Annonce visuelle au lancement
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Lancement du développement avec {model_label} : {instruction}.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "coding",
                                        "msg": "JARVIS développe via Antigravity...",
                                        "task": instruction,
                                        "engine": "Antigravity IDE",
                                        "model": model_label,
                                        "api_type": initial_api_type,
                                        "api_label": initial_api_label
                                    }))

                                    # Callback de progression : envoie l'état en temps réel au frontend
                                    # ET injecte un commentaire vocal dans Gemini Live
                                    _captured_model_label = model_label
                                    _captured_session = session

                                    async def on_antigravity_progress(p_info, _ws_orig=websocket, _ml=_captured_model_label):
                                        step = p_info.get("step", "progress")
                                        text = p_info.get("text", "")
                                        # Récupération dynamique de la socket et de la session actives (résiste aux reconnexions)
                                        active_ws = active_task_controller.get("websocket") or _ws_orig
                                        active_sess = active_task_controller.get("live_session")
                                        # Affichage visuel dans le HUD
                                        supervision_service.update_action_progress("antigravity_task", step, text, model=_ml)
                                        await broadcast_supervision()
                                        if active_ws:
                                            try:
                                                await active_ws.send_text(json.dumps({
                                                    "type": "task_progress_oral",
                                                    "step": step,
                                                    "text": text,
                                                    "engine": "Antigravity IDE",
                                                    "model": _ml
                                                }))
                                            except Exception:
                                                pass
                                        # Injection d'un commentaire vocal dans Gemini Live si la session est active
                                        if active_sess and text and step in ("tool", "planning", "adaptation", "thought", "fix", "complete", "fallback"):
                                            try:
                                                await active_sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(
                                                            text=(
                                                                f"[MISE À JOUR DU DÉVELOPPEMENT EN COURS - à dire à voix haute à Pierre en une phrase courte et naturelle] "
                                                                f"{text}"
                                                            )
                                                        )]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception as inj_err:
                                                print(f"[Progress Injection] {inj_err}")

                                    # ─── Lancement en ARRIÈRE-PLAN ─────────────────────────────────
                                    # La boucle Gemini Live reste entièrement libre pour continuer
                                    # à écouter Pierre et lui répondre pendant que le code tourne.
                                    _instr = instruction
                                    _mc = model_choice
                                    _ml2 = model_label
                                    _confirmed = is_confirmed

                                    async def _run_coding_bg(_instr=_instr, _mc=_mc, _ml2=_ml2, _conf=_confirmed, _ws=websocket, _sess=session):
                                        try:
                                            res = await run_antigravity_task(
                                                _instr,
                                                model=_mc,
                                                on_progress=on_antigravity_progress,
                                                directive_queue=active_task_controller["queue"],
                                                confirmed_by_user=_conf
                                            )
                                        except Exception as bg_err:
                                            res = {"status": "error", "summary": str(bg_err), "model_label": _ml2}
                                        finally:
                                            active_task_controller["info"]["running"] = False
                                            active_task_controller["bg_task"] = None

                                        status = res.get("status")
                                        current_ws = active_task_controller.get("websocket") or _ws
                                        current_sess = active_task_controller.get("live_session") or _sess

                                        if status == "requires_user_confirmation":
                                            active_task_controller["paid_consent_modal_open"] = True
                                            supervision_service.complete_action("antigravity_task", status="pending_confirmation", summary=res.get("reason", ""))
                                            await broadcast_supervision()
                                            if current_ws:
                                                try:
                                                    await current_ws.send_text(json.dumps({
                                                        "type": "paid_consent_request",
                                                        "action": "run_antigravity_task",
                                                        "reason": res.get("reason", ""),
                                                        "cost": res.get("estimated_cost", "~0.005 $"),
                                                        "model": res.get("model", _mc)
                                                    }))
                                                    await current_ws.send_text(json.dumps({
                                                        "type": "status",
                                                        "state": "idle",
                                                        "msg": "En attente d'accord payant",
                                                        "engine": "Antigravity IDE",
                                                        "model": _ml2
                                                    }))
                                                except Exception:
                                                    pass
                                            if current_sess:
                                                try:
                                                    await current_sess.send_client_content(
                                                        turns=types.Content(
                                                            role="user",
                                                            parts=[types.Part.from_text(
                                                                text=f"[ACCORD PAYANT REQUIS POUR CODER] {res.get('instruction_to_jarvis', '')}"
                                                            )]
                                                        ),
                                                        turn_complete=True
                                                    )
                                                except Exception as e:
                                                    print(f"[BG Task] Erreur notification consent: {e}")
                                            return

                                        elif status == "cancelled":
                                            supervision_service.complete_action("antigravity_task", status="cancelled", summary="Développement arrêté à votre demande", model=_ml2)
                                            await broadcast_supervision()
                                            if current_ws:
                                                try:
                                                    await current_ws.send_text(json.dumps({
                                                        "type": "task_cancelled",
                                                        "reason": "Arrêt demandé",
                                                        "message": "Développement immédiatement interrompu."
                                                    }))
                                                    await current_ws.send_text(json.dumps({
                                                        "type": "status",
                                                        "state": "idle",
                                                        "msg": "En veille active",
                                                        "detail": "Prêt pour vos ordres",
                                                        "engine": "Google API Live",
                                                        "model": live_display_label
                                                    }))
                                                except Exception:
                                                    pass
                                            if current_sess:
                                                try:
                                                    await current_sess.send_client_content(
                                                        turns=types.Content(
                                                            role="user",
                                                            parts=[types.Part.from_text(
                                                                text="[DÉVELOPPEMENT ARRÊTÉ] Le développement a été interrompu suite à la demande de Pierre. Confirme-lui brièvement à la voix que tout est arrêté."
                                                            )]
                                                        ),
                                                        turn_complete=True
                                                    )
                                                except Exception:
                                                    pass
                                            return

                                        applied_dirs = list(active_task_controller.get("directives", []))
                                        directive_note = ""
                                        if applied_dirs:
                                            directive_note = (
                                                f" Les consignes suivantes ont été intégrées en direct : "
                                                f"{'; '.join(applied_dirs)}."
                                            )

                                        is_error = res.get("status") in ("error", "overloaded")
                                        is_high_demand = (
                                            res.get("status") == "overloaded"
                                            or res.get("error_type") == "high_demand"
                                            or any(k in res.get("summary", "").lower() for k in ["503", "high demand", "forte demande", "satur", "unavailable", "quota"])
                                        )

                                        supervision_service.complete_action("antigravity_task", status="error" if is_error else "completed", summary=res.get("summary", "")[:250], model=res.get("model_label", _ml2))
                                        await broadcast_supervision()

                                        current_ws = active_task_controller.get("websocket") or _ws
                                        current_sess = active_task_controller.get("live_session") or _sess

                                        # Envoi du signal de fin au frontend
                                        if current_ws:
                                            try:
                                                await current_ws.send_text(json.dumps({
                                                    "type": "task_completed",
                                                    "is_error": is_error,
                                                    "status": "error" if is_error else "completed",
                                                    "error_type": "high_demand" if is_high_demand else ("error" if is_error else None),
                                                    "summary": res.get("summary", ""),
                                                    "engine": "Antigravity IDE",
                                                    "model": res.get("model_label", _ml2)
                                                }))
                                                # Remise à zéro immédiate de l'état UI en veille active pour ne JAMAIS rester bloqué en mode coding
                                                await current_ws.send_text(json.dumps({
                                                    "type": "status",
                                                    "state": "idle",
                                                    "msg": "En veille active",
                                                    "detail": "Prêt pour vos ordres",
                                                    "engine": "Google API Live",
                                                    "model": live_display_label
                                                }))
                                            except Exception:
                                                pass

                                        # Notification à Gemini Live si la session est connectée
                                        if current_sess:
                                            if is_error:
                                                if is_high_demand:
                                                    completion_msg = (
                                                        f"[ARRÊT DÉVELOPPEMENT - FORTE DEMANDE SERVEURS] "
                                                        f"Tous les modèles Antigravity sont actuellement indisponibles en raison d'une très forte demande (erreur 503 / charge élevée sur le plan d'API). "
                                                        f"RÈGLE STRICTE : NE RELANCE PAS 'run_antigravity_task' ni aucun autre outil. "
                                                        f"Informe directement, calmement et avec bienveillance Pierre à l'oral avec ta voix Aoede qu'il y a actuellement une très forte demande sur les serveurs Google Antigravity, que les modèles de repli sont également saturés et que tu ne peux donc pas coder pour le moment, en lui suggérant de réessayer dans quelques instants."
                                                    )
                                                else:
                                                    completion_msg = (
                                                        f"[ARRÊT DÉVELOPPEMENT - ERREUR TECHNIQUE] "
                                                        f"Le développement a rencontré un obstacle : {res.get('summary', '')[:250]}. "
                                                        f"RÈGLE STRICTE : NE RELANCE PAS d'outil de code en boucle. "
                                                        f"Explique brièvement et clairement à Pierre à l'oral avec ta voix Aoede ce qui s'est produit."
                                                    )
                                            else:
                                                completion_msg = (
                                                    f"[DÉVELOPPEMENT TERMINÉ] Le développement avec {res.get('model_label', _ml2)} est achevé avec succès."
                                                    f"{directive_note}"
                                                    f" Résume maintenant avec ta voix Aoede ce qui a été accompli,"
                                                    f" mentionne les fichiers créés ou modifiés et confirme que tout est prêt."
                                                    f" Résultat : {res.get('summary', 'Tâche exécutée avec succès.')[:400]}"
                                                )
                                            try:
                                                await current_sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(text=completion_msg)]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception as notify_err:
                                                print(f"[BG Task] Erreur notification fin : {notify_err}")

                                    bg = asyncio.create_task(_run_coding_bg())
                                    active_task_controller["bg_task"] = bg

                                    # Réponse immédiate à Gemini Live : la tâche est lancée en arrière-plan
                                    # Gemini peut continuer à parler à Pierre normalement
                                    tool_resp = {
                                        "status": "launched_in_background",
                                        "model_used": model_label,
                                        "engine": "Antigravity IDE",
                                        "instruction_to_jarvis": (
                                            f"Le développement avec {model_label} est lancé en arrière-plan pour : '{instruction}'. "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede d'un ton franc, complice et direct que sa demande est bien prise en compte et que tu lances le développement avec Antigravity. "
                                            f"Tu restes ensuite 100% disponible pour échanger normalement avec lui d'égal à égal pendant que le code s'exécute."
                                        )
                                    }

                                elif name == "guide_active_task":
                                    directive = args.get("directive", "")
                                    if active_task_controller["info"]["running"]:
                                        await active_task_controller["queue"].put(directive)
                                        active_task_controller.setdefault("directives", []).append(directive)
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Consigne en direct prise en compte : {directive}.",
                                        "voice": False
                                    }))
                                    tool_resp = {
                                        "status": "adapted",
                                        "directive": directive,
                                        "message": f"Consigne '{directive}' transmise en direct au moteur Antigravity."
                                    }

                                elif name == "set_browser_link":
                                    link_url = args.get("url", "")
                                    link_title = args.get("title") or "Page sélectionnée"
                                    supervision_service.track_browser_window(link_url, link_title)
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "browser_update",
                                        "url": link_url,
                                        "title": link_title,
                                        "screenshot": "/static/latest_screenshot.jpg"
                                    }))
                                    tool_resp = {
                                        "status": "updated",
                                        "url": link_url,
                                        "title": link_title,
                                        "message": f"Le lien {link_url} a été positionné dans le HUD mobile. L'utilisateur peut cliquer sur 'OUVRIR LE LIEN'."
                                    }

                                elif name == "ask_deep_reasoning":
                                    question = args.get("question", "")
                                    engine = args.get("engine") or "auto"
                                    model_choice = args.get("model")
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
                                    is_heavy = (engine == "antigravity") or (model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus"]))
                                    if engine == "antigravity" or (model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus"])):
                                        _, initial_label = resolve_antigravity_model(model_choice or "gemini-3.1-pro-high")
                                        initial_engine = "Antigravity IDE"
                                        initial_api_type = "paid"
                                        initial_api_label = "Clé Payante"
                                    else:
                                        initial_label = "Gemini 3.8 Flash (Thinking)"
                                        initial_engine = "Google API"
                                        # Clé gratuite essayée en premier pour Thinking API
                                        initial_api_type = "free"
                                        initial_api_label = "Clé Gratuite"

                                    supervision_service.start_action(
                                        "deep_reasoning",
                                        "Raisonnement Approfondi",
                                        "ask_deep_reasoning",
                                        question,
                                        initial_label,
                                        api_type=initial_api_type,
                                        api_label=initial_api_label,
                                        cost_est=estimate_tool_cost(name, args)[1]
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Engagement des protocoles de réflexion approfondie avec {initial_label}.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "thinking",
                                        "msg": "Réflexion approfondie en cours...",
                                        "task": question,
                                        "engine": initial_engine,
                                        "model": initial_label,
                                        "api_type": initial_api_type,
                                        "api_label": initial_api_label
                                    }))
                                    res = await run_deep_reasoning(question, model_choice=model_choice, engine=engine, confirmed_by_user=is_confirmed)

                                    if res.get("status") == "requires_user_confirmation":
                                        active_task_controller["paid_consent_modal_open"] = True
                                        supervision_service.complete_action("deep_reasoning", status="pending_confirmation", summary=res.get("reason", ""))
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "paid_consent_request",
                                            "action": "ask_deep_reasoning",
                                            "reason": res.get("reason", ""),
                                            "cost": res.get("estimated_cost", "~0.03 $"),
                                            "model": res.get("model", "Gemini Pro / Claude")
                                        }))
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "reason": res.get("reason", ""),
                                            "estimated_cost": res.get("estimated_cost", "~0.03 $"),
                                            "instruction_to_jarvis": res.get("instruction_to_jarvis", "")
                                        }
                                    else:
                                        # Clé réellement utilisée après exécution
                                        actual_key_label = res.get("key_used", initial_api_label)
                                        actual_api_type = "free" if "gratuite" in actual_key_label.lower() else "paid"

                                        supervision_service.complete_action(
                                            "deep_reasoning",
                                            status="completed",
                                            summary=res.get("summary", "")[:250],
                                            model=res.get("model_label", initial_label)
                                        )
                                        await broadcast_supervision()
                                        
                                        # Mise à jour de l'indicateur avec la clé réellement utilisée
                                        await websocket.send_text(json.dumps({
                                            "type": "status",
                                            "state": "thinking",
                                            "msg": "Analyse terminée, formulation de la synthèse...",
                                            "task": question,
                                            "engine": res.get("source", initial_engine),
                                            "model": res.get("model_label", initial_label),
                                            "api_type": actual_api_type,
                                            "api_label": actual_key_label
                                        }))

                                        tool_resp = {
                                            "status": "completed",
                                            "engine_used": res.get("source", initial_engine),
                                            "model_used": res.get("model_label", initial_label),
                                            "result": res,
                                            "instruction_to_jarvis": f"La réflexion avec {res.get('model_label', initial_label)} ({res.get('source', initial_engine)}) est achevée. Présente la synthèse et les conclusions avec clarté et éloquence avec ta voix Aoede."
                                        }

                                elif name == "search_web":
                                    query = args.get("query", "")
                                    supervision_service.start_action(
                                        "search_web",
                                        "Recherche Internet",
                                        "search_web",
                                        query,
                                        "Playwright / DuckDuckGo",
                                        api_type="free",
                                        api_label="Clé Gratuite",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Recherche sur Internet : {query}",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": "Recherche sur Internet...",
                                        "task": query,
                                        "engine": "Clé Gratuite",
                                        "model": "DuckDuckGo / Playwright",
                                        "api_type": "free",
                                        "api_label": "Clé Gratuite"
                                    }))

                                    # ─── RÉPONSE IMMÉDIATE à Gemini Live pour libérer la voix ────────────
                                    # Gemini peut parler pendant que la recherche tourne en arrière-plan
                                    tool_resp = {
                                        "status": "searching_in_background",
                                        "query": query,
                                        "instruction_to_jarvis": (
                                            f"La recherche sur '{query}' est lancée en arrière-plan. "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede d'un ton franc, direct et complice que sa demande est bien prise en compte et que tu lances la recherche sur le web. "
                                            f"Tu lui présenteras les résultats dès qu'ils arrivent."
                                        )
                                    }

                                    # ─── Tâche background : exécute la recherche et injecte les résultats ──
                                    _query_bg = query
                                    _sess_bg = session
                                    _ws_bg = websocket

                                    async def _run_search_bg(_q=_query_bg, _sess=_sess_bg, _ws=_ws_bg):
                                        try:
                                            # Céder la priorité à l'envoi des premiers paquets audio
                                            await asyncio.sleep(0.05)
                                            res = await search_web(_q)
                                            best_url = "https://www.google.com"
                                            best_title = _q
                                            if res.get("results"):
                                                first = res["results"][0]
                                                best_url = first.get("url", "")
                                                best_title = first.get("title", _q)
                                            
                                            supervision_service.complete_action("search_web", status="completed", summary=f"Résultats pour {best_title}")
                                            supervision_service.track_browser_window(best_url, best_title)
                                            await broadcast_supervision()

                                            try:
                                                await _ws.send_text(json.dumps({
                                                    "type": "browser_update",
                                                    "url": best_url,
                                                    "title": best_title,
                                                    "screenshot": "/static/latest_screenshot.jpg"
                                                }))
                                                await _ws.send_text(json.dumps({
                                                    "type": "status",
                                                    "state": "idle",
                                                    "msg": "En veille active",
                                                    "engine": "Google API Live",
                                                    "model": live_display_label,
                                                    "api_type": "paid" if is_paid_live else "free",
                                                    "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                                }))
                                            except Exception:
                                                pass
                                            # Injection des résultats dans Gemini Live pour qu'il les présente à voix haute
                                            result_msg = (
                                                f"[RÉSULTATS DE RECHERCHE DISPONIBLES] La recherche sur '{_q}' est terminée. "
                                                f"Le lien principal est {best_url}. "
                                                f"Voici les résultats : {json.dumps(res.get('results', [])[:3], ensure_ascii=False)[:800]}. "
                                                f"Présente maintenant les résultats pertinents à Pierre avec ta voix Aoede de façon fluide et naturelle."
                                            )
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(text=result_msg)]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception as inj_err:
                                                print(f"[Search BG] Erreur injection résultats: {inj_err}")
                                        except Exception as e:
                                            print(f"[Search BG] Erreur: {e}")
                                            supervision_service.complete_action("search_web", status="error", summary=str(e))
                                            await broadcast_supervision()
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(
                                                            text=f"[ÉCHEC RECHERCHE] La recherche sur '{_q}' a échoué ({e}). Informe Pierre brièvement."
                                                        )]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception:
                                                pass

                                    asyncio.create_task(_run_search_bg())

                                elif name == "run_browser_task":
                                    goal = args.get("goal", "")
                                    target_url = args.get("url") or ""
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
                                    initial_api_type = "paid" if is_confirmed else "free"
                                    initial_api_label = "Clé Payante" if is_confirmed else "Clé Gratuite (Essai multi-modèles)"

                                    supervision_service.start_action(
                                        "browser_task",
                                        "Navigation Web Autonome",
                                        "run_browser_task",
                                        goal,
                                        "Browser-Use (Vision LLM)",
                                        api_type=initial_api_type,
                                        api_label=initial_api_label,
                                        cost_est="~0.02 $" if is_confirmed else "0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Navigation autonome : {goal}",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": "Navigation autonome en cours...",
                                        "task": goal,
                                        "engine": initial_api_label,
                                        "model": "Browser-Use (Vision LLM)",
                                        "api_type": initial_api_type,
                                        "api_label": initial_api_label
                                    }))

                                    # ─── RÉPONSE IMMÉDIATE à Gemini Live pour libérer la voix ────────────
                                    speech_intro = (
                                        f"La navigation autonome sur '{goal}' est lancée sur la clé payante autorisée."
                                        if is_confirmed else
                                        f"La navigation sur '{goal}' est lancée. J'essaie d'abord les modèles sur la clé gratuite."
                                    )
                                    tool_resp = {
                                        "status": "browsing_in_background",
                                        "goal": goal,
                                        "instruction_to_jarvis": (
                                            f"{speech_intro} "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede d'un ton direct et complice que sa demande est bien prise en compte et que tu lances la navigation sur '{goal}'. "
                                            f"Tu recevras les résultats complets dans un instant via un message système."
                                        )
                                    }

                                    # ─── Tâche background : exécute la navigation et injecte les résultats ──
                                    _goal_bg = goal
                                    _url_bg = target_url
                                    _sess_bg2 = session
                                    _ws_bg2 = websocket
                                    _conf_bg = is_confirmed

                                    async def _run_browser_bg(_g=_goal_bg, _u=_url_bg, _conf=_conf_bg, _sess=_sess_bg2, _ws=_ws_bg2):
                                        try:
                                            # Céder la priorité à l'envoi des premiers paquets audio pour éviter tout grésillement
                                            await asyncio.sleep(0.08)
                                            res = await run_browser_task(_g, _u, confirmed_by_user=_conf)
                                            status = res.get("status")

                                            if status == "requires_user_confirmation":
                                                active_task_controller["paid_consent_modal_open"] = True
                                                supervision_service.complete_action("browser_task", status="pending_confirmation", summary=res.get("reason", ""))
                                                await broadcast_supervision()
                                                if _ws:
                                                    try:
                                                        await _ws.send_text(json.dumps({
                                                            "type": "paid_consent_request",
                                                            "action": "run_browser_task",
                                                            "reason": res.get("reason", ""),
                                                            "cost": res.get("estimated_cost", "~0.02 $"),
                                                            "model": "Browser-Use"
                                                        }))
                                                        await _ws.send_text(json.dumps({
                                                            "type": "status",
                                                            "state": "idle",
                                                            "msg": "En attente d'accord payant",
                                                            "engine": "Google API Live",
                                                            "model": live_display_label
                                                        }))
                                                    except Exception:
                                                        pass
                                                if _sess:
                                                    try:
                                                        await _sess.send_client_content(
                                                            turns=types.Content(
                                                                role="user",
                                                                parts=[types.Part.from_text(
                                                                    text=f"[ACCORD PAYANT REQUIS POUR LA NAVIGATION] {res.get('instruction_to_jarvis', '')}"
                                                                )]
                                                            ),
                                                            turn_complete=True
                                                        )
                                                    except Exception as e:
                                                        print(f"[Browser BG] Erreur notification consent: {e}")
                                                return

                                            elif status == "cancelled":
                                                supervision_service.complete_action("browser_task", status="cancelled", summary="Navigation arrêtée.")
                                                await broadcast_supervision()
                                                if _ws:
                                                    try:
                                                        await _ws.send_text(json.dumps({
                                                            "type": "task_cancelled",
                                                            "reason": "Arrêt demandé",
                                                            "message": "Navigation web interrompue."
                                                        }))
                                                        await _ws.send_text(json.dumps({
                                                            "type": "status",
                                                            "state": "idle",
                                                            "msg": "En veille active",
                                                            "engine": "Google API Live",
                                                            "model": live_display_label
                                                        }))
                                                    except Exception:
                                                        pass
                                                if _sess:
                                                    try:
                                                        await _sess.send_client_content(
                                                            turns=types.Content(
                                                                role="user",
                                                                parts=[types.Part.from_text(
                                                                    text="[NAVIGATION IMMÉDIATEMENT ARRÊTÉE] La navigation sur le web a été stoppée suite à la demande de Pierre. Confirme-lui brièvement à la voix que tout est arrêté."
                                                                )]
                                                            ),
                                                            turn_complete=True
                                                        )
                                                    except Exception:
                                                        pass
                                                return

                                            final_site_url = res.get("site_visited") or _u or "https://www.google.com"
                                            actual_key = res.get("key_used", "Clé Gratuite")
                                            actual_type = "paid" if "payante" in actual_key.lower() else "free"
                                            
                                            supervision_service.complete_action("browser_task", status="completed", summary=res.get("summary", "")[:250])
                                            supervision_service.track_browser_window(final_site_url, res.get("page_title", _g))
                                            await broadcast_supervision()

                                            try:
                                                await _ws.send_text(json.dumps({
                                                    "type": "browser_update",
                                                    "url": final_site_url,
                                                    "title": res.get("page_title", _g),
                                                    "screenshot": "/static/latest_screenshot.jpg"
                                                }))
                                                await _ws.send_text(json.dumps({
                                                    "type": "status",
                                                    "state": "idle",
                                                    "msg": "En veille active",
                                                    "engine": "Google API Live",
                                                    "model": live_display_label,
                                                    "api_type": actual_type,
                                                    "api_label": actual_key
                                                }))
                                            except Exception:
                                                pass
                                            result_msg = (
                                                f"[RÉSULTATS NAVIGATION DISPONIBLES] La navigation autonome sur '{_g}' est terminée (utilisant {actual_key}). "
                                                f"Site visité : {final_site_url}. "
                                                f"Résumé : {res.get('summary', '')[:600]}. "
                                                f"Détaille les résultats à Pierre avec ta voix Aoede de façon fluide."
                                            )
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(text=result_msg)]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception as inj_err:
                                                print(f"[Browser BG] Erreur injection résultats: {inj_err}")
                                        except Exception as e:
                                            print(f"[Browser BG] Erreur: {e}")
                                            supervision_service.complete_action("browser_task", status="error", summary=str(e))
                                            await broadcast_supervision()
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part.from_text(
                                                            text=f"[ÉCHEC NAVIGATION] La navigation sur '{_g}' a échoué ({e}). Informe Pierre brièvement."
                                                        )]
                                                    ),
                                                    turn_complete=True
                                                )
                                            except Exception:
                                                pass
                                        finally:
                                            active_task_controller["browser_bg_task"] = None

                                    b_task = asyncio.create_task(_run_browser_bg())
                                    active_task_controller["browser_bg_task"] = b_task

                                elif name == "open_user_browser":
                                    target_url = args.get("url") or "https://www.google.com"
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Ouverture de Google Chrome à l'écran.",
                                        "voice": False
                                    }))
                                    res = open_browser_window(target_url)
                                    supervision_service.track_browser_window(target_url, "Google Chrome")
                                    await broadcast_supervision()
                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": f"La fenêtre Chrome est ouverte sur {target_url}. Dis directement à Pierre d'un ton complice et naturel que sa demande est bien prise en compte et que tu lui affiches la page."
                                    }

                                elif name == "remember_user_fact":
                                    fact = args.get("fact", "")
                                    cat = args.get("category", "general")
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Mémorisation de l'information dans la mémoire durable.",
                                        "voice": False
                                    }))
                                    res = memory_service.add_memory(fact, cat)
                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": "L'information est enregistrée dans votre mémoire durable. Confirme-le brièvement avec ta voix Aoede."
                                    }

                                elif name == "recall_user_memories":
                                    query = args.get("query", "")
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Consultation des souvenirs mémorisés.",
                                        "voice": False
                                    }))
                                    memories = memory_service.search_memories(query)
                                    tool_resp = {
                                        "status": "completed",
                                        "memories": memories,
                                        "instruction_to_jarvis": "Voici les souvenirs trouvés. Présente-les à l'utilisateur avec ta voix Aoede."
                                    }

                                elif name == "get_system_status":
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Diagnostic des ressources système en cours.",
                                        "voice": False
                                    }))
                                    status = get_system_status()
                                    tool_resp = {
                                        "status": "completed",
                                        "result": status,
                                        "instruction_to_jarvis": "Voici les métriques système actuelles. Communique-les avec précision à l'utilisateur avec ta voix Aoede."
                                    }

                                elif name == "launch_application":
                                    app_name = args.get("app_name", "")
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Lancement de {app_name}.",
                                        "voice": False
                                    }))
                                    res = launch_application(app_name)
                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": f"L'application {app_name} est lancée sur l'écran. Dis directement à Pierre d'un ton complice et naturel que sa demande est bien prise en compte et que tu as lancé {app_name}."
                                    }

                                elif name == "play_music_deezer":
                                    action = args.get("action") or ("choose" if args.get("query") else "playpause")
                                    query = args.get("query", "")
                                    item_type = args.get("item_type", "track")
                                    volume = args.get("volume")
                                    enable = args.get("enable")

                                    if query:
                                        q_low = query.lower()
                                        if any(k in q_low for k in ["playlist", "mix", "compil"]):
                                            item_type = "playlist"
                                        elif any(k in q_low for k in ["flow", "mon flow"]):
                                            item_type = "flow"
                                        elif any(k in q_low for k in ["coup de coeur", "coups de coeur", "favoris", "ma musique"]):
                                            item_type = "loved"

                                    action_label_map = {
                                        "play": "Lecture Deezer",
                                        "pause": "Pause Deezer",
                                        "playpause": "Bascule Play/Pause Deezer",
                                        "next": "Morceau suivant Deezer",
                                        "prev": "Morceau précédent Deezer",
                                        "shuffle": "Aléatoire Deezer",
                                        "volume": f"Volume Deezer ({volume}%)" if volume is not None else "Volume Deezer",
                                        "status": "Statut lecture Deezer",
                                        "choose": f"Musique Deezer ({item_type}) : {query}",
                                        "open": "Ouverture Deezer Web"
                                    }
                                    action_label = action_label_map.get(action.lower(), f"Deezer : {action}")

                                    supervision_service.start_action(
                                        "play_music_deezer",
                                        action_label,
                                        "play_music_deezer",
                                        f"Action : {action} {f'({query})' if query else ''}",
                                        "Deezer Web Player (WebSocket Bridge)",
                                        api_type="free",
                                        api_label="Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"{action_label}...",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": f"Deezer — {action_label}...",
                                        "task": query or action,
                                        "engine": "WebSocket Bridge",
                                        "model": "Deezer Web",
                                        "api_type": "free",
                                        "api_label": "Local"
                                    }))

                                    res = await control_deezer(action=action, query=query, item_type=item_type, volume=volume, enable=enable)

                                    supervision_service.complete_action("play_music_deezer", status=res.get("status", "completed"), summary=res.get("message", "Deezer contrôlé avec succès"))
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "idle",
                                        "msg": "En veille active",
                                        "engine": "Google API Live",
                                        "model": live_display_label
                                    }))
                                    tool_resp = {
                                        "status": res.get("status", "completed"),
                                        "result": res,
                                        "instruction_to_jarvis": (
                                            f"{res.get('message', 'Action Deezer exécutée.')} "
                                            f"Confirme brièvement et naturellement à Pierre d'un ton complice que sa demande musicale est prise en compte."
                                        )
                                    }

                                elif name == "play_video_stremio":
                                    title = args.get("title", "")
                                    content_type = args.get("content_type") or "movie"
                                    supervision_service.start_action(
                                        "play_video_stremio",
                                        "Lecture Stremio",
                                        "play_video_stremio",
                                        f"{'Film' if content_type == 'movie' else 'Série'} : {title}",
                                        "Stremio + Torrentio",
                                        api_type="free",
                                        api_label="Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Recherche de '{title}' sur Stremio...",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": f"Stremio — Recherche de '{title}'...",
                                        "task": title,
                                        "engine": "Local",
                                        "model": "Stremio + Cinemeta",
                                        "api_type": "free",
                                        "api_label": "Local"
                                    }))
                                    # Lancement en background (la recherche Cinemeta + Torrentio prend qq secondes)
                                    _title_bg = title
                                    _ct_bg = content_type
                                    _sess_stremio = session
                                    _ws_stremio = websocket

                                    async def _run_stremio_bg(_t=_title_bg, _ct=_ct_bg, _sess=_sess_stremio, _ws=_ws_stremio):
                                        try:
                                            res = await play_on_stremio(_t, _ct)
                                            supervision_service.complete_action("play_video_stremio", status=res.get("status", "launched"), summary=res.get("message", f"Stremio lancé sur {_t}"))
                                            await broadcast_supervision()
                                            try:
                                                await _ws.send_text(json.dumps({
                                                    "type": "status",
                                                    "state": "idle",
                                                    "msg": "En veille active",
                                                    "engine": "Google API Live",
                                                    "model": live_display_label
                                                }))
                                            except Exception:
                                                pass
                                            stream = res.get("stream_info", {})
                                            size_msg = ""
                                            if stream.get("found") and stream.get("size_gb"):
                                                size_msg = f" Le stream 1080p fait {stream['size_gb']} Go."
                                            found_t = res.get("found_title", _t)
                                            year = res.get("year", "")
                                            rating = res.get("imdb_rating", "")
                                            rating_msg = f" Note IMDb : {rating}." if rating else ""
                                            inject_msg = (
                                                f"[STREMIO LANCÉ] Stremio est ouvert sur '{found_t}' ({year}).{rating_msg}{size_msg} "
                                                f"Dis à Pierre d'un ton complice et enthousiaste que tu as trouvé et lancé '{found_t}' sur Stremio."
                                            )
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(role="user", parts=[types.Part.from_text(text=inject_msg)]),
                                                    turn_complete=True
                                                )
                                            except Exception:
                                                pass
                                        except Exception as e:
                                            supervision_service.complete_action("play_video_stremio", status="error", summary=str(e))
                                            await broadcast_supervision()
                                            try:
                                                await _sess.send_client_content(
                                                    turns=types.Content(role="user", parts=[types.Part.from_text(text=f"[STREMIO ERREUR] Impossible de lancer '{_t}' sur Stremio : {e}. Informe Pierre brièvement.")]),
                                                    turn_complete=True
                                                )
                                            except Exception:
                                                pass

                                    asyncio.create_task(_run_stremio_bg())
                                    tool_resp = {
                                        "status": "searching_in_background",
                                        "title": title,
                                        "instruction_to_jarvis": (
                                            f"La recherche de '{title}' sur Stremio est lancée en arrière-plan. "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede d'un ton enthousiaste et complice que tu cherches '{title}' sur Stremio et que tu vas le lancer directement. "
                                            f"Tu lui donneras les détails (1080p, taille) dès que c'est prêt."
                                        )
                                    }


                                elif name == "send_email":
                                    subject = args.get("subject", "Rapport J.A.R.V.I.S.")
                                    body = args.get("body", "")
                                    to_email = args.get("to_email") or config.DEFAULT_RECIPIENT_EMAIL
                                    attachments = args.get("attachments") or []
                                    include_screenshot = bool(args.get("include_latest_screenshot", False))

                                    supervision_service.start_action(
                                        "send_email",
                                        "Expédition E-mail",
                                        "send_email",
                                        f"Sujet : {subject} -> {to_email}",
                                        "SMTP Stark Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Préparation de l'e-mail pour {to_email}.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "emailing",
                                        "msg": "Expédition d'e-mail en cours...",
                                        "task": subject,
                                        "engine": "Google API",
                                        "model": "Stark Email Protocol",
                                        "api_type": "free",
                                        "api_label": "Service Local"
                                    }))

                                    res = await send_email_async(
                                        subject=subject,
                                        body=body,
                                        to_email=to_email,
                                        attachments=attachments,
                                        include_screenshot=include_screenshot,
                                        is_html_report=True
                                    )

                                    supervision_service.complete_action(
                                        "send_email",
                                        status="completed" if res.get("status") in ("sent", "saved") else "error",
                                        summary=res.get("message", f"E-mail traité pour {to_email}")
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "email_sent",
                                        "status": res.get("status"),
                                        "subject": subject,
                                        "recipient": to_email,
                                        "attachments_count": res.get("attachments_count", 0),
                                        "message": res.get("message", "")
                                    }))

                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": (
                                            f"L'e-mail avec pour sujet '{subject}' destiné à {to_email} a été traité ({res.get('message', '')}). "
                                            f"Confirme verbalement d'égal à égal à Pierre avec ta voix Aoede que sa demande a bien été prise en compte et que l'e-mail est expédié."
                                        )
                                    }

                                elif name == "read_emails":
                                    count = int(args.get("count", 5))
                                    query = args.get("query")
                                    unread_only = bool(args.get("unread_only", False))

                                    supervision_service.start_action(
                                        "read_emails",
                                        "Lecture E-mails",
                                        "read_emails",
                                        f"Consultation Gmail ({count} messages, query={query or 'aucun'})",
                                        "IMAP Stark Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Consultation de votre boîte de réception Gmail en cours...",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "emailing",
                                        "msg": "Lecture des e-mails en cours...",
                                        "task": f"Boîte de réception ({config.DEFAULT_RECIPIENT_EMAIL})",
                                        "engine": "Google API",
                                        "model": "Stark IMAP Protocol",
                                        "api_type": "free",
                                        "api_label": "Service Local"
                                    }))

                                    res = await read_received_emails_async(
                                        max_count=count,
                                        query=query,
                                        unread_only=unread_only
                                    )

                                    supervision_service.complete_action(
                                        "read_emails",
                                        status="completed" if res.get("status") == "ok" else "error",
                                        summary=f"{res.get('count', 0)} e-mail(s) relevé(s)"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "emails_received",
                                        "status": res.get("status"),
                                        "count": res.get("count", 0),
                                        "emails": res.get("emails", []),
                                        "message": res.get("message", "")
                                    }))

                                    emails_summary_text = ""
                                    if res.get("status") == "ok" and res.get("emails"):
                                        items_desc = []
                                        for idx, m in enumerate(res["emails"], 1):
                                            items_desc.append(
                                                f"E-mail {idx} : De '{m.get('from', 'Inconnu')}', Objet '{m.get('subject', 'Sans sujet')}', reçu le {m.get('date', '')}. Extrait : {m.get('snippet', '')}"
                                            )
                                            if m.get("has_attachments"):
                                                items_desc.append(f"  Pièces jointes : {', '.join(m.get('attachments', []))}")
                                        emails_summary_text = "\n".join(items_desc)
                                    else:
                                        emails_summary_text = res.get("message", "Aucun message trouvé.")

                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": (
                                            f"Voici le résultat de la consultation des e-mails reçus sur pierrecassagnettes@gmail.com :\n{emails_summary_text}\n\n"
                                            "Présente directement à Pierre à l'oral avec ta voix Aoede un compte-rendu clair, concis et naturel de ses messages récents. "
                                            "Mentionne qui lui a écrit, le sujet principal et l'information clé. S'il n'y a aucun mail, dis-le-lui gentiment."
                                        )
                                    }

                                elif name == "check_console_errors":
                                    action = args.get("action") or "diagnose"
                                    if action == "clear":
                                        console_monitor.clear()
                                        diag = console_monitor.analyze_diagnostics()
                                        diag["summary"] = "Journal des erreurs de la console réinitialisé."
                                        diag["oral_explanation"] = "Pierre, j'ai purgé et réinitialisé le journal des erreurs de la console."
                                    else:
                                        diag = console_monitor.analyze_diagnostics()
                                        if diag.get("has_errors"):
                                            auto_fix = console_monitor.attempt_auto_fix(workspace_path=config.WORKSPACE_DIR)
                                            diag["auto_fix"] = auto_fix

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Analyse console : {diag.get('summary', '')[:65]}",
                                        "voice": False
                                    }))

                                    tool_resp = {
                                        "status": "completed",
                                        "has_errors": diag.get("has_errors", False),
                                        "diagnostic": diag.get("summary", ""),
                                        "oral_explanation": diag.get("oral_explanation", ""),
                                        "recent_errors": console_monitor.get_recent_errors(limit=4),
                                        "instruction_to_jarvis": (
                                            f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede la situation de la console de façon fluide et rassurante : "
                                            f"{diag.get('oral_explanation', '')}"
                                        )
                                    }

                                elif name == "interact_web_page":
                                    target_url = args.get("url", "")
                                    action = args.get("action", "read")
                                    selector = args.get("selector", "")
                                    text_to_fill = args.get("text_to_fill", "")

                                    supervision_service.start_action(
                                        "interact_web_page",
                                        "Interaction Web & Formulaires",
                                        "interact_web_page",
                                        f"{action} sur {target_url}",
                                        "Playwright Automation Engine",
                                        api_type="free",
                                        api_label="Local / Playwright",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Interaction sur {target_url} ({action})",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": "Interaction sur la page web...",
                                        "task": f"{action} sur {target_url}",
                                        "engine": "Playwright Local",
                                        "model": "Browser Engine",
                                        "api_type": "free",
                                        "api_label": "Clé Gratuite"
                                    }))

                                    res = await interact_web_page(
                                        url=target_url,
                                        action=action,
                                        selector=selector,
                                        text_to_fill=text_to_fill
                                    )

                                    supervision_service.complete_action("interact_web_page", status=res.get("status", "completed"), summary=res.get("title", target_url))
                                    if res.get("url"):
                                        supervision_service.track_browser_window(res.get("url"), res.get("title", target_url))
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "browser_update",
                                        "url": res.get("url", target_url),
                                        "title": res.get("title", "Page Web"),
                                        "screenshot": "/static/latest_screenshot.jpg"
                                    }))

                                    tool_resp = {
                                        "status": res.get("status"),
                                        "url": res.get("url"),
                                        "title": res.get("title"),
                                        "performed_actions": res.get("performed_actions", []),
                                        "detected_form_inputs": res.get("detected_form_inputs", []),
                                        "available_buttons": res.get("available_buttons", []),
                                        "content_preview": res.get("content_preview", "")[:1200],
                                        "instruction_to_jarvis": (
                                            f"L'interaction sur la page {res.get('url')} est terminée. "
                                            f"Dis d'abord à Pierre d'un ton franc et complice que sa demande a bien été prise en compte, puis résume les éléments découverts ou les actions effectuées avec ta voix Aoede."
                                        )
                                    }

                                elif name == "prepare_web_cart_or_checkout":
                                    product_or_service = args.get("product_or_service", "")
                                    merchant_url = args.get("merchant_url") or ""
                                    open_when_ready = bool(args.get("open_when_ready", True))

                                    supervision_service.start_action(
                                        "prepare_web_cart_or_checkout",
                                        "Création Panier & Commande",
                                        "prepare_web_cart_or_checkout",
                                        f"Panier : {product_or_service}",
                                        "Playwright E-Commerce Engine",
                                        api_type="free",
                                        api_label="Local / Playwright",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Préparation de votre panier pour {product_or_service}...",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "browsing",
                                        "msg": "Préparation du panier et préremplissage...",
                                        "task": f"Panier : {product_or_service}",
                                        "engine": "Playwright E-Commerce",
                                        "model": "Chrome Automation",
                                        "api_type": "free",
                                        "api_label": "Clé Gratuite"
                                    }))

                                    res = await prepare_web_cart_or_checkout(
                                        product_or_service=product_or_service,
                                        merchant_url=merchant_url,
                                        open_when_ready=open_when_ready
                                    )

                                    supervision_service.complete_action("prepare_web_cart_or_checkout", status=res.get("status", "completed"), summary=f"Panier {product_or_service} préparé")
                                    if res.get("cart_url"):
                                        supervision_service.track_browser_window(res.get("cart_url"), f"Panier : {product_or_service}")
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "browser_update",
                                        "url": res.get("cart_url", merchant_url),
                                        "title": f"Panier : {product_or_service}",
                                        "screenshot": "/static/latest_screenshot.jpg"
                                    }))

                                    tool_resp = {
                                        "status": res.get("status"),
                                        "cart_url": res.get("cart_url"),
                                        "prefilled_fields": res.get("prefilled_fields", []),
                                        "browser_opened": res.get("browser_opened", True),
                                        "result_message": res.get("message", ""),
                                        "instruction_to_jarvis": (
                                            f"Le panier pour '{product_or_service}' est prêt et les coordonnées de Pierre sont préremplies sur son écran. "
                                            f"Dis directement à Pierre avec ta voix Aoede d'un ton complice et naturel que sa demande a bien été prise en compte, que le panier est ouvert à l'écran et qu'il n'a plus qu'à régler et valider sa commande."
                                        )
                                    }

                                elif name == "download_file":
                                    target_url = args.get("url", "")
                                    filename = args.get("filename")
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
                                    file_type = args.get("file_type", "general")

                                    supervision_service.start_action(
                                        "download_file",
                                        "Téléchargement Sécurisé",
                                        "download_file",
                                        f"Téléchargement {filename or target_url}",
                                        "Stark Transfer Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    res = await download_file(
                                        url=target_url,
                                        filename=filename,
                                        confirmed_by_user=is_confirmed,
                                        subfolder="ebooks" if file_type == "ebook" else "downloads"
                                    )

                                    if res.get("status") == "requires_user_confirmation":
                                        supervision_service.complete_action("download_file", status="pending_confirmation", summary=f"En attente accord Pierre pour {res.get('filename')}")
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Autorisation requise pour télécharger {res.get('filename')}",
                                            "voice": False
                                        }))
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "filename": res.get("filename"),
                                            "size": res.get("estimated_size"),
                                            "domain": res.get("domain"),
                                            "instruction_to_jarvis": res.get("instruction_to_jarvis")
                                        }
                                    else:
                                        supervision_service.complete_action("download_file", status=res.get("status", "completed"), summary=f"{res.get('filename')} ({res.get('size')})")
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Téléchargement terminé : {res.get('filename')} ({res.get('size')})",
                                            "voice": False
                                        }))
                                        tool_resp = {
                                            "status": res.get("status"),
                                            "filename": res.get("filename"),
                                            "filepath": res.get("filepath"),
                                            "size": res.get("size"),
                                            "message": res.get("message"),
                                            "instruction_to_jarvis": (
                                                f"Le fichier '{res.get('filename')}' ({res.get('size')}) a été téléchargé avec succès sur l'ordinateur. "
                                                f"Confirme verbalement d'égal à égal à Pierre avec ta voix Aoede que sa demande a bien été prise en compte et que le fichier est prêt."
                                            )
                                        }

                                elif name == "send_to_ereader":
                                    file_path = args.get("file_path", "")
                                    ereader_email = args.get("ereader_email")
                                    method = args.get("method", "auto")

                                    supervision_service.start_action(
                                        "send_to_ereader",
                                        "Acheminement Liseuse",
                                        "send_to_ereader",
                                        f"Livre : {file_path}",
                                        "USB / SMTP Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Transfert de l'ebook vers la liseuse...",
                                        "voice": False
                                    }))

                                    res = await send_to_ereader(file_path=file_path, ereader_email=ereader_email, method=method)

                                    supervision_service.complete_action("send_to_ereader", status=res.get("status", "completed"), summary=res.get("message", "Ebook envoyé"))
                                    await broadcast_supervision()

                                    tool_resp = {
                                        "status": res.get("status"),
                                        "channel": res.get("channel"),
                                        "message": res.get("message"),
                                        "instruction_to_jarvis": (
                                            f"{res.get('message', 'Le livre a été envoyé vers votre liseuse.')} "
                                            f"Confirme à Pierre avec ta voix Aoede que son livre est prêt sur sa liseuse."
                                        )
                                    }

                                elif name == "search_and_download_ebook":
                                    query = args.get("query", "")
                                    source_url = args.get("source_url")
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
                                    send_to_reader_flag = bool(args.get("send_to_reader", True))
                                    ereader_email = args.get("ereader_email")

                                    supervision_service.start_action(
                                        "send_to_ereader",
                                        "Recherche & Ebook Liseuse",
                                        "search_and_download_ebook",
                                        f"Ebook : {query}",
                                        "Web / Stark Reader Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()

                                    res = await search_and_download_ebook(
                                        query=query,
                                        source_url=source_url,
                                        confirmed_by_user=is_confirmed,
                                        send_to_reader=send_to_reader_flag,
                                        ereader_email=ereader_email
                                    )

                                    if res.get("status") == "requires_user_confirmation":
                                        supervision_service.complete_action("send_to_ereader", status="pending_confirmation", summary=f"Accord Pierre requis pour l'ebook {query}")
                                        await broadcast_supervision()
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "query": query,
                                            "book_title": res.get("book_title") or res.get("filename"),
                                            "source_url": res.get("source_url"),
                                            "filename": res.get("filename"),
                                            "size": res.get("estimated_size") or res.get("size"),
                                            "domain": res.get("domain") or res.get("source") or "Anna's Archive",
                                            "instruction_to_jarvis": res.get("instruction_to_jarvis")
                                        }
                                    else:
                                        supervision_service.complete_action("send_to_ereader", status=res.get("status", "completed"), summary=f"Ebook {query} : {res.get('status')}")
                                        await broadcast_supervision()
                                        if res.get("status") == "success":
                                            instruction = (
                                                f"L'ebook '{query}' a été téléchargé avec succès et acheminé sur la liseuse Kindle de Pierre. "
                                                f"Annonce-lui avec ta voix Aoede que son livre est maintenant prêt dans sa bibliothèque Kindle."
                                            )
                                        else:
                                            instruction = (
                                                f"Une difficulté est survenue lors de la récupération ou de l'envoi de l'ebook '{query}' : {res.get('message', 'Échec du traitement')}. "
                                                f"Explique la situation avec ta voix Aoede sans prétendre que le livre est envoyé."
                                            )
                                        tool_resp = {
                                            "status": res.get("status"),
                                            "filename": res.get("filename"),
                                            "message": res.get("message"),
                                            "instruction_to_jarvis": instruction
                                        }
                                elif name == "send_page_to_kindle":
                                    target_url = args.get("url", "")
                                    title = args.get("title", "")

                                    supervision_service.start_action(
                                        "send_page_to_kindle",
                                        "Envoi Send to Kindle",
                                        "send_page_to_kindle",
                                        f"Kindle : {title or target_url}",
                                        "Send to Kindle Extension & E-Reader Protocol",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Mise en page et envoi de l'article vers votre Kindle...",
                                        "voice": False
                                    }))

                                    res = await send_page_to_kindle(url=target_url, title=title, open_in_chrome=True)

                                    supervision_service.complete_action("send_page_to_kindle", status=res.get("status", "completed"), summary=res.get("message", "Article envoyé sur Kindle"))
                                    await broadcast_supervision()

                                    tool_resp = {
                                        "status": res.get("status", "completed"),
                                        "result": res,
                                        "instruction_to_jarvis": (
                                            f"{res.get('message', 'Article transféré sur la Kindle.')} "
                                            f"Annonce avec ta voix Aoede que l'article a été mis en page et expédié vers sa Kindle, et que Google Chrome est ouvert sur la page avec l'extension Send to Kindle prête."
                                        )
                                    }

                                elif name == "send_file_to_kindle":
                                    file_path = args.get("file_path", "")
                                    open_browser = args.get("open_browser_if_needed", True)

                                    supervision_service.start_action(
                                        "send_file_to_kindle",
                                        "Amazon Send to Kindle Web",
                                        "send_file_to_kindle",
                                        f"Fichier : {file_path}",
                                        "Amazon Playwright Authenticated Session",
                                        api_type="free",
                                        api_label="Service Local",
                                        cost_est="0.00 $"
                                    )
                                    await broadcast_supervision()
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Dépôt du fichier {file_path} sur Amazon Send to Kindle...",
                                        "voice": False
                                    }))

                                    res = await send_file_to_kindle_web(file_path=file_path, open_browser_if_needed=open_browser)

                                    supervision_service.complete_action("send_file_to_kindle", status=res.get("status", "completed"), summary=res.get("message", "Fichier envoyé sur Kindle"))
                                    await broadcast_supervision()

                                    if res.get("status") == "success":
                                        instruction = (
                                            f"{res.get('message', 'Fichier envoyé sur la Kindle.')} "
                                            f"Annonce avec ta voix Aoede que le document a été déposé et envoyé avec succès sur sa liseuse Kindle via sa session Amazon connectée."
                                        )
                                    else:
                                        instruction = (
                                            f"L'envoi sur la Kindle n'a pas pu aboutir : {res.get('message', 'Erreur de transfert')}. "
                                            f"Informe Pierre avec ta voix Aoede de la situation sans affirmer que le document est envoyé."
                                        )
                                    tool_resp = {
                                        "status": res.get("status", "completed"),
                                        "result": res,
                                        "instruction_to_jarvis": instruction
                                    }

                                elif name == "list_chrome_extensions":
                                    res = list_installed_chrome_extensions()
                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": (
                                            f"{res.get('message', 'Extensions analysées.')} "
                                            f"Résume oralement les extensions clés installées sur Chrome à Pierre (notamment Send to Kindle) avec ta voix Aoede."
                                        )
                                    }

                                else:
                                    tool_resp = {"status": "error", "message": f"Outil inconnu {name}"}


                                # Réponse transmise au modèle Gemini Live
                                await session.send_tool_response(
                                    function_responses=[
                                        types.FunctionResponse(
                                            name=name,
                                            id=call.id,
                                            response=tool_resp,
                                        )
                                    ]
                                )

                                # Signal de fin d'outil au frontend
                                # Le client arrête le silence sender et repassera en écoute réelle
                                # dès que Gemini enverra le premier chunk audio de réponse
                                await websocket.send_text(json.dumps({
                                    "type": "tool_end",
                                    "tool_name": name
                                }))
            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError, ModelSwitchRequested, QuotaExhaustedError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                err_str = str(e).lower()
                is_normal_close = (
                    "cannot call" in err_str
                    or "close message has been sent" in err_str
                    or "connection closed" in err_str
                    or "disconnect" in err_str
                    or "closed" in err_str
                    or "close" in err_str
                    or "1000" in err_str
                    or "1001" in err_str
                    or "(1000, none)" in err_str
                    or "1000 none" in err_str
                    or "connectionclosedok" in err_str
                    or getattr(e, "code", None) in (1000, 1001)
                )
                if is_normal_close:
                    raise WebSocketDisconnect(code=1000)
                else:
                    print(f"[gemini_to_client] Erreur: {e}")
                    console_monitor.record_error(source="gemini_to_client", message=str(e), level="WARNING")
                    raise
            finally:
                pass
        while True:
            live_display_label = "Gemini 3.8 Live (Thinking)" if "extended-thinking" in active_live_model else "Gemini 3.8 Live"

            try:
                print(f"[Voice Channel] Connexion Live ({active_live_model}) avec {tier_badge}...")
                session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
            except Exception as initial_conn_err:
                # Repli automatique : si la clé gratuite a échoué (quota, limitation ou indisponibilité)
                if not is_paid_live and client_paid:
                    print(f"[Voice Channel] Clé gratuite en échec ({initial_conn_err}). Bascule immédiate de repli sur la clé payante...")
                    supervision_service.set_free_quota_exhausted(True)
                    console_monitor.record_error(
                        source="Voice Channel",
                        message=f"Bascule de repli sur clé payante suite à échec clé gratuite : {initial_conn_err}",
                        level="WARNING"
                    )
                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Repli Quota)"
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Limite de la clé gratuite atteinte. Bascule automatique sur la clé payante.",
                        "voice": False
                    }))
                    session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                else:
                    raise initial_conn_err

            active_task_controller["live_session"] = session
            active_task_controller["live_session_ctx"] = session_ctx
            supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
            await broadcast_supervision()
            await websocket.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Canal vocal {live_display_label} opérationnel ({tier_badge}).",
                "voice": False
            }))

            setup_done_event.clear()
            setup_done_event.set()

            if not greeting_sent:
                greeting_sent = True
                greeting_instruction = (
                    "[INSTRUCTION SYSTÈME INVISIBLE] La session vocale vient de démarrer. "
                    "Salue Pierre naturellement et d'égal à égal avec ta voix Aoede en une courte phrase sympa, directe et décontractée pour lui dire que tu es prête."
                )
                try:
                    await session.send_client_content(
                        turns=types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=greeting_instruction)]
                        ),
                        turn_complete=True
                    )
                    print("[Voice Channel] Amorce vocale (greeting) envoyée avec succès.")
                except Exception as greet_err:
                    print(f"[Voice Channel] Avertissement amorce vocale: {greet_err}")

            client_task = asyncio.create_task(client_to_gemini(), name="client_to_gemini")
            gemini_task = asyncio.create_task(gemini_to_client(), name="gemini_to_client")

            async def _auto_cancel_sister(t1, t2):
                try:
                    await t1
                except Exception:
                    pass
                finally:
                    if not t2.done():
                        t2.cancel()

            asyncio.create_task(_auto_cancel_sister(client_task, gemini_task))
            asyncio.create_task(_auto_cancel_sister(gemini_task, client_task))

            try:
                await asyncio.gather(client_task, gemini_task)
                break
            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
                break
            except Exception as loop_e:
                err_s = str(loop_e).lower()
                is_loop_normal = (
                    getattr(loop_e, "code", None) in (1000, 1001)
                    or "1000" in err_s
                    or "1001" in err_s
                    or "connection closed" in err_s
                    or "connectionclosed" in err_s
                    or "normal closure" in err_s
                    or "(1000, none)" in err_s
                    or "1000 none" in err_s
                    or "disconnect" in err_s
                )
                if is_loop_normal:
                    break
                raise
            except ModelSwitchRequested as switch_req:
                new_model = switch_req.model
                print(f"[Voice Channel] Bascule dynamique de modèle vocal demandée : {new_model}")
                active_live_model = new_model
                config.GEMINI_LIVE_MODEL = new_model

                if session_ctx:
                    try:
                        await session_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                session = None
                session_ctx = None

                if new_model == "gemini-3.8-live":
                    current_live_client = client_free if (client_free and not supervision_service._free_quota_exhausted) else (client_paid or client_free)
                    is_paid_live = (current_live_client is client_paid)
                else:
                    current_live_client = client_paid or client_free
                    is_paid_live = (current_live_client is client_paid)

                tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"
                await websocket.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Bascule vers le modèle {new_model} ({tier_badge})...",
                    "voice": False
                }))
                continue
            except QuotaExhaustedError as q_err:
                if not is_paid_live and client_paid:
                    print(f"[Voice Channel] Quota dépassé sur la clé gratuite en direct ({q_err}). Bascule automatique sur la clé payante...")
                    supervision_service.set_free_quota_exhausted(True)
                    console_monitor.record_error(
                        source="Voice Channel",
                        message="Quota clé gratuite dépassé en direct. Bascule automatique sur clé payante.",
                        level="WARNING"
                    )
                    if session_ctx:
                        try:
                            await session_ctx.__aexit__(None, None, None)
                        except Exception:
                            pass
                    session = None
                    session_ctx = None

                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Repli Quota)"
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Limite de la clé gratuite atteinte pendant l'échange. Bascule automatique sur la clé payante effectuée.",
                        "voice": False
                    }))
                    continue
                else:
                    raise q_err

    except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
        pass
    except Exception as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        is_normal = (
            isinstance(e, (WebSocketDisconnect, WebSocketDisconnected))
            or getattr(e, "code", None) in (1000, 1001)
            or "1000" in err_msg
            or "1001" in err_msg
            or "normal closure" in err_lower
            or "connectionclosed" in err_lower
            or "disconnect" in err_lower
            or "closed" in err_lower
            or "(1000, none)" in err_lower
            or "1000 none" in err_lower
        )
        if is_normal:
            print(f"[Voice Channel] Fermeture normale de session vocale ({active_live_model})")
        else:
            import traceback
            tb = traceback.format_exc()
            print(f"[Voice Channel] ERREUR CRITIQUE Live ({active_live_model}): {err_msg}\n{tb}")
            console_monitor.record_error(source="Voice Channel", message=f"Erreur Live: {err_msg}", level="ERROR")
            try:
                await websocket.send_text(json.dumps({
                    "type": "transcript",
                    "role": "jarvis",
                    "text": f"Erreur de connexion Live : {err_msg}"
                }))
            except Exception:
                pass
            try:
                await websocket.close(code=1011, reason=f"Live error: {err_msg[:100]}")
            except Exception:
                pass
    finally:
        # Fermeture propre et immédiate de la session Live Google pour éviter les sessions zombies en conflit 409
        if session_ctx:
            try:
                await session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        elif session:
            try:
                await session.close()
            except Exception:
                pass

        # Nettoyage des références à la session vocale terminée
        print("[Voice Channel] FINALLY: Nettoyage session et références terminé.")
        if active_task_controller.get("websocket") == websocket:
            active_task_controller["websocket"] = None
        if active_task_controller.get("live_session") == session:
            active_task_controller["live_session"] = None
        if active_task_controller.get("live_session_ctx") == session_ctx:
            active_task_controller["live_session_ctx"] = None
        supervision_service.update_voice_state("offline")
        await broadcast_supervision()
        try:
            await websocket.close()
        except Exception:
            pass

        # IMPORTANT : On ne détruit PAS la tâche de code en arrière-plan si le canal vocal se déconnecte !
        # Elle continue de coder dans le workspace de façon autonome et mettra à jour l'interface.
        bg = active_task_controller.get("bg_task")
        if bg and bg.done():
            active_task_controller["info"]["running"] = False
            active_task_controller["bg_task"] = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("App:app", host="0.0.0.0", port=8000, reload=True)
