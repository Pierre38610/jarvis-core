"""routers/browser.py
Endpoints navigateur / Kindle : extensions Chrome, Send to Kindle, profil Chrome.
"""
import os

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import auth
import config
from services.browser_service import (
    open_browser_window, send_page_to_kindle, send_file_to_kindle_web,
    check_kindle_web_status, list_installed_chrome_extensions
)
from services.download_service import list_downloaded_files
from services.email_service import send_email_async, list_outbox_emails, read_received_emails_async
from core.shared_state import active_task_controller, broadcast_jarvis_state

router = APIRouter()


class SendToKindleRequest(BaseModel):
    url: str
    title: str = ""


class SendFileToKindleRequest(BaseModel):
    file_path: str = ""
    open_browser_if_needed: bool = True


class EmailRequest(BaseModel):
    subject: str = ""
    body: str = ""
    to_email: str | None = None
    attachments: list[str] | None = None
    include_screenshot: bool = False
    is_html_report: bool = True


@router.get("/api/browser/extensions")
async def api_list_extensions(request: Request):
    """Liste toutes les extensions Google Chrome détectées (Send to Kindle, etc.)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return list_installed_chrome_extensions()


@router.post("/api/browser/send-to-kindle")
async def api_send_to_kindle(req: SendToKindleRequest, request: Request):
    """Extrait un article web et l'achemine vers la liseuse Kindle de Pierre."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    await broadcast_jarvis_state("kindle", f"Send to Kindle : {req.title or req.url}...", task=f"Kindle : {req.title or req.url}", engine="Amazon Send to Kindle", model="Send to Kindle Extension")
    try:
        res = await send_page_to_kindle(url=req.url, title=req.title, open_in_chrome=True)
    finally:
        await broadcast_jarvis_state("listening", "Prêt pour votre prochaine instruction.")
    return res


@router.post("/api/browser/send-file-to-kindle")
async def api_send_file_to_kindle(req: SendFileToKindleRequest, request: Request):
    """Dépose un fichier local sur Amazon Send to Kindle et l'envoie sur la Kindle de Pierre."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    await broadcast_jarvis_state("kindle", f"Dépôt Kindle : {os.path.basename(req.file_path)}...", task=f"Kindle : {os.path.basename(req.file_path)}", engine="Amazon Send to Kindle", model="Send to Kindle Web")
    try:
        res = await send_file_to_kindle_web(file_path=req.file_path, open_browser_if_needed=req.open_browser_if_needed)
    finally:
        await broadcast_jarvis_state("listening", "Prêt pour votre prochaine instruction.")
    return res


@router.post("/api/browser/upload-and-send-to-kindle")
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

    await broadcast_jarvis_state("kindle", f"Téléversement & envoi Kindle : {file.filename}...", task=f"Kindle : {file.filename}", engine="Amazon Send to Kindle", model="Send to Kindle Web")
    try:
        res = await send_file_to_kindle_web(file_path=file_location, open_browser_if_needed=False)
    finally:
        await broadcast_jarvis_state("listening", "Prêt pour votre prochaine instruction.")
    return res


@router.get("/api/browser/kindle-status")
async def api_kindle_status(request: Request):
    """Vérifie si la session Amazon Send to Kindle est active et connectée sur la machine."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return await check_kindle_web_status()


@router.post("/api/browser/open-kindle-login")
async def api_open_kindle_login(request: Request):
    """Ouvre Google Chrome sur la page Amazon Send to Kindle avec le profil Jarvis pour se connecter."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return open_browser_window("https://www.amazon.fr/sendtokindle", load_extensions=True)


@router.post("/api/open-chrome-profile")
async def api_open_chrome_profile(request: Request):
    """Ouvre Google Chrome avec le profil persistant de Jarvis pour que Pierre puisse se connecter à ses comptes."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    url = "https://www.google.com"
    try:
        body = await request.json()
        url = body.get("url", url)
    except Exception:
        pass
    res = open_browser_window(url)
    return {
        "status": res.get("status"),
        "message": "Chrome est ouvert avec le profil Jarvis. Connectez-vous à vos comptes depuis cette fenêtre. Jarvis réutilisera automatiquement ces sessions à chaque navigation.",
        "profile_dir": config.PROFILE_DIR if hasattr(config, "PROFILE_DIR") else "Voir config.py"
    }


@router.get("/api/downloads")
async def api_list_downloads(request: Request):
    """Retourne la liste des documents et ebooks téléchargés par J.A.R.V.I.S."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return {
        "downloads": list_downloaded_files("downloads"),
        "ebooks": list_downloaded_files("ebooks")
    }


# ─── E-mail REST endpoints ────────────────────────────────────────────────────

@router.post("/api/send-email")
async def api_send_email(req: EmailRequest, request: Request):
    """Envoie un e-mail via l'API REST de J.A.R.V.I.S."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await send_email_async(subject=req.subject, body=req.body, to_email=req.to_email, attachments=req.attachments, include_screenshot=req.include_screenshot, is_html_report=req.is_html_report)
    return res


@router.get("/api/emails/outbox")
async def api_get_outbox(request: Request):
    """Liste les e-mails archivés dans l'outbox locale."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    return {"emails": list_outbox_emails()}


@router.get("/api/emails/inbox")
async def api_get_inbox(request: Request, count: int = 5, query: str | None = None, unread_only: bool = False):
    """Récupère les e-mails reçus sur la boîte Gmail via IMAP."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)
    res = await read_received_emails_async(max_count=count, query=query, unread_only=unread_only)
    return res


@router.get("/api/emails/preview/{email_id}")
async def api_preview_email(email_id: str):
    """Affiche le rapport HTML d'un courriel généré directement dans le navigateur."""
    from fastapi.responses import FileResponse as FR
    if os.path.exists(config.EMAIL_OUTBOX_DIR):
        for fname in os.listdir(config.EMAIL_OUTBOX_DIR):
            if email_id in fname and fname.endswith(".html"):
                return FR(os.path.join(config.EMAIL_OUTBOX_DIR, fname), media_type="text/html")
    return JSONResponse(content={"error": "E-mail introuvable"}, status_code=404)
