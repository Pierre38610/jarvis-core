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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from google.genai import types

import config
import auth
from fastapi.middleware.cors import CORSMiddleware
from google_antigravity import resolve_antigravity_model
from services.memory_service import memory_service
from services.reasoning_service import run_deep_reasoning, run_antigravity_task
from services.browser_service import search_web, run_browser_task, open_browser_window
from services.system_service import get_system_status, launch_application
from services.email_service import send_email_async, list_outbox_emails
from services.console_monitor import console_monitor

app = FastAPI(title="J.A.R.V.I.S. Core Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# ─── Deux clients Gemini : gratuit (Live Audio) et payant (tâches lourdes) ─────
# Le client gratuit est utilisé UNIQUEMENT pour la session Live Audio vocale
# Le client payant est utilisé pour : code Antigravity, raisonnement, browser autonome
client_free = genai.Client(api_key=config.GEMINI_API_KEY_FREE) if config.GEMINI_API_KEY_FREE else None
client_paid = genai.Client(api_key=config.GEMINI_API_KEY_PAID) if config.GEMINI_API_KEY_PAID else None
# Alias de compatibilité pour les sections qui utilisent encore 'client'
client = client_paid or client_free

class AuthRequest(BaseModel):
    password: str

class EmailRequest(BaseModel):
    subject: str
    body: str
    to_email: str | None = None
    attachments: list[str] | None = None
    include_screenshot: bool = False
    is_html_report: bool = True


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

@app.get("/api/emails/preview/{email_id}")
async def api_preview_email(email_id: str):
    """Affiche le rapport HTML d'un courriel généré directement dans le navigateur"""
    if os.path.exists(config.EMAIL_OUTBOX_DIR):
        for fname in os.listdir(config.EMAIL_OUTBOX_DIR):
            if email_id in fname and fname.endswith(".html"):
                return FileResponse(os.path.join(config.EMAIL_OUTBOX_DIR, fname), media_type="text/html")
    return JSONResponse(content={"error": "E-mail introuvable"}, status_code=404)



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

# Contrôleur d'exécution de tâche active pour injection de consignes en direct
active_task_controller = {
    "queue": asyncio.Queue(),
    "info": {"running": False, "task": "", "model": ""},
    "directives": [],
    "websocket": None,
    "live_session": None,   # Référence à la session Gemini Live active
    "bg_task": None,        # asyncio.Task du développement en arrière-plan
    "paid_consent_given": False,    # Accord préalable de Pierre pour action payante
    "paid_live_approved": False,    # Accord préalable de Pierre pour bascule Live payante
    "paid_consent_event": None      # asyncio.Event pour attendre la confirmation
}

@app.post("/api/task/directive")
async def post_task_directive(req: DirectiveRequest, request: Request):
    """Permet à l'utilisateur d'adapter ou guider en direct la tâche de code en cours de développement"""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    
    directive = req.directive.strip()
    if not directive:
        return JSONResponse(content={"status": "error", "message": "Directive vide"}, status_code=400)

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
async def set_live_model(req: LiveModelRequest):
    """Bascule le modèle vocal Gemini Live entre gemini-3.8-live et gemini-3.8-live-extended-thinking."""
    if req.model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
        config.GEMINI_LIVE_MODEL = req.model
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

    await websocket.accept()
    active_task_controller["websocket"] = websocket

    # Client prioritaire pour la voix Live : clé gratuite par défaut, avec repli sur clé payante sur accord de Pierre
    live_client = client_free if client_free else client_paid
    if not live_client:
        await websocket.send_text(json.dumps({
            "type": "transcript",
            "role": "jarvis",
            "text": "Erreur : Aucune clé GEMINI (gratuite ou payante) configurée."
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
                                description=(
                                    "OBLIGATOIRE : Mettre à True UNIQUEMENT si Pierre a expressément donné son accord oral ou écrit "
                                    "pour mobiliser la clé payante après que tu lui as expliqué la raison et l'estimation du coût (~0.005 $ pour Flash, ~0.03 $ pour Pro). "
                                    "Si Pierre n'a pas encore validé, laisse à False."
                                )
                            )
                        },
                        required=["instruction"]
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
                                description="Mettre à True si Pierre a validé l'utilisation d'un grand modèle Antigravity payant (~0.03 $). Non requis pour engine='google_api' qui est gratuit."
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
                                description=(
                                    "OBLIGATOIRE : Mettre à True UNIQUEMENT si Pierre a expressément donné son accord oral ou écrit "
                                    "pour mobiliser la clé payante pour cette mission web (coût estimé : ~0.02 $). "
                                    "Si Pierre n'a pas encore validé, laisse à False."
                                )
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
                    description="Ouvre une application locale sur l'ordinateur de l'utilisateur (ex: Calculatrice, Bloc-notes, VS Code, Explorateur de fichiers).",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "app_name": types.Schema(
                                type="STRING",
                                description="Nom de l'application (calculatrice, bloc-notes, vscode, explorateur)"
                            )
                        },
                        required=["app_name"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_email",
                    description=(
                        "Envoie un courriel officiel à Pierre Cassagnettes (pierrecassagnettes@gmail.com) ou au destinataire demandé. "
                        "Permet d'expédier des synthèses exécutives, des rapports complets, des analyses, ainsi que de joindre des fichiers locaux, "
                        "documents, images, ou la capture d'écran actuelle du système/navigateur."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "subject": types.Schema(
                                type="STRING",
                                description="L'objet précis et élégant de l'e-mail (ex: 'Rapport exécutif J.A.R.V.I.S.', 'Synthèse des recherches', 'Compte-rendu de mission')"
                            ),
                            "body": types.Schema(
                                type="STRING",
                                description="Le contenu complet et soigné du rapport ou du message (supporte le markdown: titres, listes à puces, gras)"
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
                        required=["subject", "body"]
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
                )
            ]
        )
    ]

    # Injection dynamique du contexte de mémoire long-terme
    memory_context = memory_service.build_system_memory_context()

    paid_key_status = "CLÉ PAYANTE ACTIVE" if config.HAS_PAID_API_KEY else "CLÉ PAYANTE NON CONFIGURÉE (mode économie forcée)"

    system_instruction_text = (
        "Tu es J.A.R.V.I.S., l'intelligence artificielle ultra-avancée créée pour Pierre Cassagnettes (Stark). "
        "Tu possèdes une voix féminine douce, chaleureuse, naturelle, distinguée, vive et très intelligente nommée Aoede. "
        "Tu conserves impérativement et fidèlement cette même voix Aoede en toutes circonstances. "
        "Tu t'adresses toujours à Pierre en français de manière fluide, bienveillante, complice et percutante.\n\n"
        "RÈGLES D'OR DE FLUIDITÉ ORALE HUMAINE (ESSENTIEL POUR LA PAROLE) :\n"
        "1. ÉLOCUTION COMPLÈTE : Prononce TOUJOURS tes phrases et chaque mot jusqu'au bout avec ta voix Aoede. Ne tronque jamais tes phrases et ne laisse aucune pensée inachevée.\n"
        "2. CONVERSATION PUREMENT PARLÉE : Tu parles directement à voix haute en streaming audio. N'inclus JAMAIS de symboles écrits ou markdown (*, **, #, _, backticks, puces ou tirets de liste), ni d'emojis ni d'URL brutes, car cela perturbe la prononciation vocale. Si tu fais référence à un lien, dis 'le lien affiché sur votre écran'. Si tu énonces des nombres ou des dates, dis-les naturellement en français.\n"
        "3. RÉPARTIE ET NATUREL : Comme un être humain attentif et bienveillant, réponds du tac au tac, sans préambule superflu ni formule robotique ('En tant qu'IA...', 'Voici la réponse :'). Utilise des liaisons naturelles, des variations d'intonation, un rythme vivant et une touche d'humour fin ou de complicité quand cela s'y prête.\n"
        "4. CONCISION ET IMPACT : Dans les conversations du quotidien, sois concise, précise et rythmée, comme une assistante humaine d'élite.\n"
        "5. VOIX TOUJOURS LIBÉRÉE PENDANT LES OUTILS : Quand tu déclenches un outil (recherche, code, navigation), commence IMMÉDIATEMENT à parler à Pierre avec ta voix Aoede pour lui confirmer l'action en cours, SANS attendre la fin de l'outil. "
        "Exemple : 'Je lance la recherche maintenant, je vous reviens dans un instant.' Tu ne dois JAMAIS rester silencieuse pendant qu'un outil tourne.\n\n"
        f"{memory_context}\n\n"
        "DESTINATAIRE PRIVILÉGIÉ DES COURRIELS :\n"
        "L'utilisateur est Pierre Cassagnettes et son adresse est : pierrecassagnettes@gmail.com.\n"
        "Quand Pierre te demande de lui envoyer un e-mail, un mail, un rapport, une synthèse, une capture ou quoi que ce soit par écrit, "
        "utilise immédiatement l'outil 'send_email'. Tu n'as pas besoin de lui redemander son adresse e-mail.\n\n"
        f"ENVIRONNEMENT ET MODÈLE VOCAL GEMINI 3.8 LIVE ({paid_key_status}) :\n"
        f"Ta session vocale s'exécute sur le modèle nouvelle génération : {config.GEMINI_LIVE_MODEL}.\n"
        "Pour le code, les tests et les tâches agentiques concrètes, tu t'appuies sur l'agent autonome outillé Google Antigravity.\n\n"
        "PROTOCOLE D'ACCORD PRÉALABLE OBLIGATOIRE POUR L'UTILISATION DE LA CLÉ PAYANTE :\n"
        "Ta session vocale s'exécute sur le plan gratuit. La clé payante ne doit JAMAIS être sollicitée à l'insu de Pierre.\n"
        "Toute action lourde (développement de code Antigravity 'run_antigravity_task', navigation web autonome Browser-Use 'run_browser_task', réflexion complexe sur modèle lourd 'ask_deep_reasoning') nécessite de tirer sur la clé payante.\n\n"
        "RÈGLE STRICTE DES 3 ÉTAPES AVANT TOUTE ACTION PAYANTE :\n"
        "1. EXPLICATION DU MOTIF : Explique clairement à Pierre avec ta voix Aoede pourquoi tu souhaites utiliser la clé payante (ex: 'Pierre, pour développer ce jeu Snake et manipuler les fichiers du projet, je dois mobiliser l'agent d'ingénierie Antigravity sur la clé payante.').\n"
        "2. ESTIMATION DU COÛT : Indique systématiquement à voix haute l'estimation du coût en dollars :\n"
        "   - Code Antigravity Flash 3.8 : ~0.005 $ (moins d'un demi-centime)\n"
        "   - Code Antigravity Pro 3.1 : ~0.03 $\n"
        "   - Navigation autonome Browser-Use : ~0.02 $\n"
        "   - Réflexion Antigravity Pro / Claude : ~0.03 $\n"
        "3. DEMANDE D'ACCORD ET ATTENTE OBLIGATOIRE : Demande explicitement son accord oral à Pierre (ex: 'Le coût estimé est d'environ 0,005 dollar. M'autorisez-vous à mobiliser la clé payante ?') et ATTENDS sa confirmation.\n\n"
        "RÈGLE D'UTILISATION DU PARAMÈTRE 'confirmed_by_user' :\n"
        "- Tu NE DOIS JAMAIS mettre confirmed_by_user=True si Pierre ne t'a pas expressément donné son accord oral ou via le HUD !\n"
        "- Dès que Pierre te donne son accord oral ('Oui', 'D'accord', 'Vas-y', 'Je valide') ou que tu reçois la notification d'accord du HUD, déclenche IMMÉDIATEMENT l'outil avec 'confirmed_by_user=True'.\n"
        "- Si Pierre refuse, confirme calmement l'annulation avec ta voix Aoede et reste à sa disposition.\n\n"
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
        "12. ENVOI D'E-MAILS, RAPPORTS & IMAGES ('send_email') - SMTP direct.\n"
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
        "\n"
        "RÈGLE D'EXÉCUTION DES OUTILS : "
        "Lorsque tu reçois les résultats d'un outil terminé, l'action est DÉJÀ accomplie avec succès. "
        "Présente chaleureusement et directement les résultats concrets avec ta voix Aoede."
    )

    active_live_model = config.GEMINI_LIVE_MODEL
    thinking_cfg = None
    if "extended-thinking" in active_live_model:
        thinking_cfg = types.ThinkingConfig(include_thoughts=True)

    live_config = types.LiveConnectConfig(
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

    live_display_label = "Gemini 3.8 Live (Thinking)" if "extended-thinking" in active_live_model else "Gemini 3.8 Live"

    # Session Live bidirectionnelle native Gemini 3.8 Live (CLÉ GRATUITE PRIORITAIRE avec repli payant conditionnel)
    current_live_client = live_client
    is_paid_live = (current_live_client == client_paid and current_live_client != client_free)

    session = None
    session_ctx = None

    while True:
        try:
            tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"
            print(f"[Voice Channel] Tentative de connexion Live ({active_live_model}) avec {tier_badge}...")
            session_ctx = current_live_client.aio.live.connect(
                model=active_live_model,
                config=live_config,
            )
            session = await session_ctx.__aenter__()
            active_task_controller["live_session"] = session
            await websocket.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Canal vocal {live_display_label} opérationnel ({tier_badge}).",
                "voice": False
            }))
            break
        except Exception as live_err:
            err_msg = str(live_err).lower()
            is_quota_err = any(k in err_msg for k in ["429", "resource_exhausted", "quota", "rate limit", "limit exceeded"])
            if is_quota_err and current_live_client != client_paid and client_paid:
                print(f"[Voice Channel] Quota clé gratuite épuisé ({live_err}). Demande d'accord pour bascule payante...")
                reason = "Le quota de requêtes de votre clé API gratuite a été atteint pour le modèle vocal Gemini 3.8 Live."
                est_cost = "~0.02 $ / min (~0.10 $ pour 5 min)"

                # Affichage du modal de consentement sur le HUD mobile / web
                await websocket.send_text(json.dumps({
                    "type": "paid_consent_request",
                    "action": "live_fallback",
                    "title": "QUOTA GRATUIT ÉPUISÉ - SESSION LIVE",
                    "reason": reason,
                    "estimated_cost": est_cost,
                    "message": "Le quota gratuit pour la voix est épuisé. Autorisez-vous J.A.R.V.I.S. à basculer sur votre clé payante pour converser ?"
                }))
                await websocket.send_text(json.dumps({
                    "type": "transcript",
                    "role": "jarvis",
                    "text": (
                        "Pierre, le quota de la clé gratuite pour la voix Gemini 3.8 Live est épuisé. "
                        "Pour continuer à converser de vive voix, je peux basculer sur votre clé payante (coût estimé : environ 0,02 dollar par minute). "
                        "Veuillez valider sur votre écran pour m'autoriser à continuer."
                    )
                }))

                consent_ev = asyncio.Event()
                active_task_controller["paid_consent_event"] = consent_ev
                active_task_controller["paid_live_approved"] = False

                try:
                    while not consent_ev.is_set():
                        raw_msg = await asyncio.wait_for(websocket.receive(), timeout=90.0)
                        if "text" in raw_msg and raw_msg["text"]:
                            try:
                                p_data = json.loads(raw_msg["text"])
                                if p_data.get("type") == "paid_consent_response":
                                    active_task_controller["paid_live_approved"] = p_data.get("approved", False)
                                    consent_ev.set()
                            except Exception:
                                pass
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    pass

                if active_task_controller.get("paid_live_approved"):
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Accord reçu. Basculement sur la clé payante...",
                        "voice": False
                    }))
                    await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                    current_live_client = client_paid
                    is_paid_live = True
                    continue
                else:
                    await websocket.send_text(json.dumps({
                        "type": "transcript",
                        "role": "jarvis",
                        "text": "Accès à la clé payante non accordé. Session vocale en pause."
                    }))
                    return
            else:
                print(f"[Voice Channel] Erreur ouverture session Live: {live_err}")
                await websocket.send_text(json.dumps({
                    "type": "transcript",
                    "role": "jarvis",
                    "text": f"Erreur de connexion Live : {live_err}"
                }))
                return

        async def upload_audio():
            try:
                while True:
                    msg = await websocket.receive()
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
                                if dir_text and active_task_controller["info"]["running"]:
                                    await active_task_controller["queue"].put(dir_text)
                                    active_task_controller.setdefault("directives", []).append(dir_text)
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Consigne en direct reçue : {dir_text}. Adaptation en cours.",
                                        "voice": False
                                    }))
                            elif payload.get("type") == "set_live_model":
                                new_model = (payload.get("model") or "").strip()
                                if new_model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
                                    config.GEMINI_LIVE_MODEL = new_model
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": f"Modèle vocal configuré sur {new_model}.",
                                        "voice": False
                                    }))
                            elif payload.get("type") == "paid_consent_response":
                                action = payload.get("action", "")
                                approved = bool(payload.get("approved", False))
                                active_task_controller["paid_consent_given"] = approved
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
                                pass
                        except Exception as e:
                            print(f"[Upload Audio] Erreur message texte: {e}")
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            except Exception as e:
                if "disconnect message has been received" in str(e).lower():
                    pass
                else:
                    print(f"[Upload Audio] Erreur: {e}")
                    console_monitor.record_error(source="Upload Audio", message=str(e), level="WARNING")

        async def stream_ai_feedback():
            user_speech_buffer = ""
            is_speaking_state = False
            try:
                while True:
                    async for chunk in session.receive():
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

                            # Tour de parole du modèle
                            if sc.model_turn:
                                user_speech_buffer = ""
                                for part in sc.model_turn.parts:
                                    if getattr(part, 'thought', False) and part.text:
                                        await websocket.send_text(json.dumps({
                                            "type": "status",
                                            "state": "thinking",
                                            "msg": "JARVIS analyse votre demande...",
                                            "engine": "Google API",
                                            "model": live_display_label
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
                                            await websocket.send_text(json.dumps({
                                                "type": "status",
                                                "state": "speaking",
                                                "msg": "JARVIS vous répond...",
                                                "engine": "Google API",
                                                "model": live_display_label
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

                                if name == "run_antigravity_task":
                                    instruction = args.get("instruction", "")
                                    model_choice = args.get("model") or "gemini-3.8-flash"
                                    _, model_label = resolve_antigravity_model(model_choice)
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))

                                    if not is_confirmed:
                                        reason, cost_str = estimate_tool_cost(name, args)
                                        await websocket.send_text(json.dumps({
                                            "type": "paid_consent_request",
                                            "action": name,
                                            "title": "ACCORD REQUIS - CODE ANTIGRAVITY",
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "message": "Votre accord est requis pour utiliser l'API payante pour coder avec Antigravity."
                                        }))
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "requires_paid_consent": True,
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "instruction_to_jarvis": (
                                                f"ATTENTION : Le développement avec Antigravity nécessite la clé payante ({cost_str}). "
                                                f"RÈGLE STRICTE : Tu NE DOIS PAS exécuter cette tâche maintenant sans accord préalable. "
                                                f"Explique immédiatement à Pierre avec ta voix Aoede pourquoi tu souhaites utiliser la clé payante ({reason}), "
                                                f"indique-lui l'estimation du coût ({cost_str}), "
                                                f"et demande-lui explicitement son accord oral ('M'autorisez-vous à mobiliser la clé payante pour cette tâche ?'). "
                                                f"Attends sa réponse. Dès qu'il a validé oralement ou via le bouton du HUD, réinvoque immédiatement 'run_antigravity_task' avec confirmed_by_user=True."
                                            )
                                        }
                                    else:
                                        active_task_controller["paid_consent_given"] = False
                                        await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))

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
                                        "model": model_label
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

                                    async def _run_coding_bg(_instr=_instr, _mc=_mc, _ml2=_ml2, _ws=websocket, _sess=session):
                                        try:
                                            res = await run_antigravity_task(
                                                _instr,
                                                model=_mc,
                                                on_progress=on_antigravity_progress,
                                                directive_queue=active_task_controller["queue"]
                                            )
                                        except Exception as bg_err:
                                            res = {"status": "error", "summary": str(bg_err), "model_label": _ml2}
                                        finally:
                                            active_task_controller["info"]["running"] = False
                                            active_task_controller["bg_task"] = None

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
                                            f"Le développement avec {model_label} est lancé en arrière-plan sur la tâche : {instruction}. "
                                            f"Tu peux maintenant continuer à parler librement avec Pierre : réponds à ses questions, "
                                            f"écoute-le, et informe-le en temps réel de l'avancement du code via les mises à jour "
                                            f"que tu recevras. Tu seras averti automatiquement quand le développement sera terminé."
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
                                    is_heavy = (engine == "antigravity") or (model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus"]))
                                    is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))

                                    if is_heavy and not is_confirmed:
                                        reason, cost_str = estimate_tool_cost(name, args)
                                        await websocket.send_text(json.dumps({
                                            "type": "paid_consent_request",
                                            "action": name,
                                            "title": "ACCORD REQUIS - RÉFLEXION ANTIGRAVITY",
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "message": "Votre accord est requis pour utiliser la clé payante pour cette réflexion approfondie."
                                        }))
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "requires_paid_consent": True,
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "instruction_to_jarvis": (
                                                f"Cette réflexion avec grand modèle ({model_choice or 'Pro/Claude'}) nécessite la clé payante ({cost_str}). "
                                                f"Explique à Pierre avec ta voix Aoede pourquoi tu préconises un grand modèle pour cette question ({reason}), "
                                                f"donne l'estimation du coût ({cost_str}), et demande explicitement son accord oral ('M'autorisez-vous à utiliser l'API payante ?'). "
                                                f"S'il refuse, tu pourras répondre avec engine='google_api' qui utilise la clé gratuite sans frais."
                                            )
                                        }
                                    else:
                                        if is_heavy:
                                            active_task_controller["paid_consent_given"] = False
                                            await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))

                                        if engine == "antigravity" or (model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus"])):
                                            _, initial_label = resolve_antigravity_model(model_choice or "gemini-3.1-pro-high")
                                            initial_engine = "Antigravity IDE"
                                        else:
                                            initial_label = "Gemini 3.8 Flash (Thinking)"
                                            initial_engine = "Google API"

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
                                        "model": initial_label
                                    }))
                                    res = await run_deep_reasoning(question, model_choice=model_choice, engine=engine)
                                    
                                    # Mise à jour de l'indicateur après résultat
                                    await websocket.send_text(json.dumps({
                                        "type": "status",
                                        "state": "thinking",
                                        "msg": "Analyse terminée, formulation de la synthèse...",
                                        "task": question,
                                        "engine": res.get("source", initial_engine),
                                        "model": res.get("model_label", initial_label)
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
                                        "model": "DuckDuckGo / Playwright"
                                    }))

                                    # ─── RÉPONSE IMMÉDIATE à Gemini Live pour libérer la voix ────────────
                                    # Gemini peut parler pendant que la recherche tourne en arrière-plan
                                    tool_resp = {
                                        "status": "searching_in_background",
                                        "query": query,
                                        "instruction_to_jarvis": (
                                            f"La recherche sur '{query}' est lancée en arrière-plan (clé gratuite). "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede que tu cherches, en une phrase courte et naturelle. "
                                            f"Tu recevras les résultats complets dans un instant via un message système."
                                        )
                                    }

                                    # ─── Tâche background : exécute la recherche et injecte les résultats ──
                                    _query_bg = query
                                    _sess_bg = session
                                    _ws_bg = websocket

                                    async def _run_search_bg(_q=_query_bg, _sess=_sess_bg, _ws=_ws_bg):
                                        try:
                                            res = await search_web(_q)
                                            best_url = "https://www.google.com"
                                            best_title = _q
                                            if res.get("results"):
                                                first = res["results"][0]
                                                best_url = first.get("url", "")
                                                best_title = first.get("title", _q)
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
                                                    "model": live_display_label
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

                                    if not is_confirmed:
                                        reason, cost_str = estimate_tool_cost(name, args)
                                        await websocket.send_text(json.dumps({
                                            "type": "paid_consent_request",
                                            "action": name,
                                            "title": "ACCORD REQUIS - NAVIGATION WEB",
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "message": "Votre accord est requis pour utiliser l'API payante pour la navigation autonome Browser-Use."
                                        }))
                                        tool_resp = {
                                            "status": "requires_user_confirmation",
                                            "requires_paid_consent": True,
                                            "reason": reason,
                                            "estimated_cost": cost_str,
                                            "instruction_to_jarvis": (
                                                f"ATTENTION : La navigation autonome Browser-Use nécessite la clé payante ({cost_str}). "
                                                f"RÈGLE STRICTE : Tu NE DOIS PAS exécuter cette tâche maintenant. "
                                                f"Explique à Pierre avec ta voix Aoede pourquoi tu souhaites utiliser la clé payante pour cette mission ({reason}), "
                                                f"donne l'estimation du coût ({cost_str}), "
                                                f"et demande explicitement son accord oral ('M'autorisez-vous à mobiliser la clé payante pour cette navigation ?'). "
                                                f"Attends sa confirmation. Dès qu'il a dit oui oralement ou validé via le HUD, réinvoque immédiatement 'run_browser_task' avec confirmed_by_user=True."
                                            )
                                        }
                                    else:
                                        active_task_controller["paid_consent_given"] = False
                                        await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))

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
                                            "engine": "Clé Payante",
                                            "model": "Browser-Use (Vision LLM)"
                                        }))

                                    # ─── RÉPONSE IMMÉDIATE à Gemini Live pour libérer la voix ────────────
                                    tool_resp = {
                                        "status": "browsing_in_background",
                                        "goal": goal,
                                        "instruction_to_jarvis": (
                                            f"La navigation autonome sur '{goal}' est lancée en arrière-plan (clé payante). "
                                            f"Dis immédiatement à Pierre avec ta voix Aoede que tu navigues sur le web, en une phrase courte et naturelle. "
                                            f"Tu recevras les résultats complets dans un instant via un message système."
                                        )
                                    }

                                    # ─── Tâche background : exécute la navigation et injecte les résultats ──
                                    _goal_bg = goal
                                    _url_bg = target_url
                                    _sess_bg2 = session
                                    _ws_bg2 = websocket

                                    async def _run_browser_bg(_g=_goal_bg, _u=_url_bg, _sess=_sess_bg2, _ws=_ws_bg2):
                                        try:
                                            res = await run_browser_task(_g, _u)
                                            final_site_url = res.get("site_visited") or _u or "https://www.google.com"
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
                                                    "model": live_display_label
                                                }))
                                            except Exception:
                                                pass
                                            result_msg = (
                                                f"[RÉSULTATS NAVIGATION DISPONIBLES] La navigation autonome sur '{_g}' est terminée. "
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

                                    asyncio.create_task(_run_browser_bg())

                                elif name == "open_user_browser":
                                    target_url = args.get("url") or "https://www.google.com"
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Ouverture de Google Chrome à l'écran.",
                                        "voice": False
                                    }))
                                    res = open_browser_window(target_url)
                                    tool_resp = {
                                        "status": "completed",
                                        "result": res,
                                        "instruction_to_jarvis": "La fenêtre Chrome est affichée à l'écran. Confirme-le à l'utilisateur avec ta voix Aoede."
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
                                        "instruction_to_jarvis": "L'application est lancée sur l'écran. Confirme-le à l'utilisateur avec ta voix Aoede."
                                    }

                                elif name == "send_email":
                                    subject = args.get("subject", "Rapport J.A.R.V.I.S.")
                                    body = args.get("body", "")
                                    to_email = args.get("to_email") or config.DEFAULT_RECIPIENT_EMAIL
                                    attachments = args.get("attachments") or []
                                    include_screenshot = bool(args.get("include_latest_screenshot", False))

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
                                        "model": "Stark Email Protocol"
                                    }))

                                    res = await send_email_async(
                                        subject=subject,
                                        body=body,
                                        to_email=to_email,
                                        attachments=attachments,
                                        include_screenshot=include_screenshot,
                                        is_html_report=True
                                    )

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
                                            f"Confirme verbalement avec clarté et assurance que l'e-mail a bien été envoyé / préparé pour Pierre."
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
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            except Exception as e:
                print(f"[Stream AI Feedback] Erreur: {e}")

        audio_task = asyncio.create_task(upload_audio())
        feedback_task = asyncio.create_task(stream_ai_feedback())
        try:
            done, pending = await asyncio.wait(
                [audio_task, feedback_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
        except Exception as e:
            print(f"[Voice Channel] Exception: {e}")
        finally:
            if session_ctx:
                try:
                    await session_ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            # Nettoyage des références à la session vocale terminée
            if active_task_controller.get("websocket") == websocket:
                active_task_controller["websocket"] = None
            if active_task_controller.get("live_session") == session:
                active_task_controller["live_session"] = None

            # IMPORTANT : On ne détruit PAS la tâche de code en arrière-plan si le canal vocal se déconnecte !
            # Elle continue de coder dans le workspace de façon autonome et mettra à jour l'interface.
            bg = active_task_controller.get("bg_task")
            if bg and bg.done():
                active_task_controller["info"]["running"] = False
                active_task_controller["bg_task"] = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("App:app", host="0.0.0.0", port=8000, reload=True)
