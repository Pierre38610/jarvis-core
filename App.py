"""J.A.R.V.I.S. Core Server - Stark Industries AI Assistant
Architecture modulaire FastAPI : chaque domaine fonctionnel est isolé dans son propre module.

Structure :
- core/shared_state.py     : État global, clients Gemini, helpers broadcast
- core/tools/declarations.py : FunctionDeclarations Gemini Live
- core/tools/dispatcher.py   : Dispatch de chaque outil vers le service métier
- routers/voice.py         : WebSocket /ws  (Gemini Live full-duplex)
- routers/local_agent.py   : WebSocket /ws/local-agent + /api/local-agent/status
- routers/chat.py          : /api/chat/*
- routers/media.py         : /api/media/deezer/* (legacy) + /api/media/spotify/*
- routers/browser.py       : /api/browser/*, /api/downloads, /api/emails/*
- routers/supervision.py   : /api/supervision/*, /api/task/*
- routers/settings.py      : /api/live-model, /api/settings/*, /api/paid-consent
"""

import os

os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import auth
from services.cache import cache_service
from services.memory import vector_memory
from services.console_monitor import console_monitor

# ─── Routeurs modulaires ──────────────────────────────────────────────────────
from routers import voice, local_agent, chat, media, browser, supervision, settings, briefing, transport, spotify as spotify_router

app = FastAPI(title="J.A.R.V.I.S. Core Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
_downloads_dir = getattr(config, "DOWNLOADS_DIR", os.path.join(config.BASE_DIR, "downloads"))
os.makedirs(_downloads_dir, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=_downloads_dir), name="downloads")

# ─── Enregistrement de tous les routeurs ─────────────────────────────────────
app.include_router(voice.router)
app.include_router(local_agent.router)
app.include_router(chat.router)
app.include_router(media.router)
app.include_router(browser.router)
app.include_router(supervision.router)
app.include_router(settings.router)
app.include_router(briefing.router)
app.include_router(transport.router)
app.include_router(spotify_router.router)


# ─── Cycle de vie de l'application ───────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialise les services au lancement de J.A.R.V.I.S."""
    # 1. Vérification non bloquante de la connectivité Redis
    try:
        redis_ok = await cache_service.check_connection(timeout=1.5)
        if redis_ok:
            print(f"[Startup] [Cache/Redis] Connecté avec succès à {config.REDIS_HOST}:{config.REDIS_PORT}")
        else:
            print("[Startup] [Cache/Redis] Non disponible ou hors ligne - Mode dégradé local actif")
    except Exception as e:
        print(f"[Startup] [Cache/Redis] Avertissement initialisation cache : {e}")

    # 2. Mémoire vectorielle long-terme (Qdrant + PostgreSQL + fastembed)
    try:
        mem_ok = await vector_memory.init()
        if mem_ok:
            print("[Startup] [Memory] Service vectoriel long-terme opérationnel")
        else:
            print("[Startup] [Memory] Service vectoriel en mode dégradé (Qdrant/PostgreSQL peut-être hors ligne)")
    except Exception as e:
        print(f"[Startup] [Memory] Avertissement initialisation mémoire vectorielle : {e}")

    # 3. Service Spotify (init tables SQLite + validation tokens en cache)
    try:
        from services.spotify_service import spotify_service
        spotify_service._ensure_db()
        auth_status = spotify_service.get_user_info()
        if auth_status.get("authenticated"):
            print(f"[Startup] [Spotify] Connecte en tant que : {auth_status.get('display_name', 'Utilisateur')}")
        else:
            print("[Startup] [Spotify] Non authentifie — va sur /api/media/spotify/login")
    except Exception as e:
        print(f"[Startup] [Spotify] Avertissement initialisation : {e}")

    # 4. Synchronisation et amorçage du profil de candidature de Pierre
    try:
        from services.user_profile_service import user_profile_service
        sync_res = user_profile_service.sync_to_sqlite()
        print(f"[Startup] [UserProfile] Profil de Pierre synchronisé : {sync_res}")
    except Exception as e:
        print(f"[Startup] [UserProfile] Avertissement synchro profil Pierre : {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Arrête proprement les connexions et serveurs satellites."""
    try:
        await cache_service.close()
    except Exception:
        pass

    try:
        await vector_memory.close()
    except Exception:
        pass

    # Spotify : aucun cleanup necessaire (tokens persistes en DB)


# ─── Routes racines et authentification ──────────────────────────────────────

@app.get("/")
async def serve_ui():
    """Sert l'interface HUD mobile Stark Industries."""
    index_file = os.path.join(config.STATIC_DIR, "index.html")
    return FileResponse(index_file)


from typing import Optional
from services.auth_service import auth_service


class AuthRequest(BaseModel):
    password: str


class QRAuthRequest(BaseModel):
    ticket: str


class RevokeRequest(BaseModel):
    token_id: Optional[str] = None
    device_id: Optional[str] = None


@app.post("/api/auth")
async def authenticate_device(req: AuthRequest, request: Request, response: Response):
    """Vérifie le mot de passe maître et génère un jeton permanent d'appareil signé (JWT)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    token = auth_service.verify_and_generate_token(req.password, client_ip, user_agent)

    if token:
        response.set_cookie(
            key="jarvis_device_token",
            value=token,
            max_age=315360000,  # 10 ans de persistance cookie
            httponly=False,
            samesite="lax",
            secure=True
        )
        return {"status": "ok", "token": token}
    return JSONResponse(
        content={"status": "error", "message": "Mot de passe incorrect"},
        status_code=401
    )


@app.get("/api/auth-qr")
async def generate_qr_ticket_endpoint(request: Request):
    """Génère un ticket unique de pairage QR Code avec un TTL court (5 minutes) géré dans Redis."""
    client_ip = request.client.host if request.client else "unknown"
    ticket = await auth_service.create_qr_ticket(ttl=300, client_ip=client_ip)
    return {
        "status": "ok",
        "ticket": ticket,
        "expires_in": 300,
        "message": "Ticket QR de pairage unique émis (valide 5 minutes)."
    }


@app.post("/api/auth-qr")
async def authenticate_via_qr(req: QRAuthRequest, request: Request, response: Response):
    """Enregistre l'appareil sans mot de passe après scan d'un ticket QR valide (usage unique, TTL 5 min)."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    token = await auth_service.redeem_qr_ticket(req.ticket, client_ip, user_agent)
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
async def verify_device(request: Request, response: Response):
    """Vérifie si le terminal possède un jeton d'enregistrement valide (JWT ou migration transparente)."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if not token:
        return JSONResponse(content={"authorized": False}, status_code=401)

    payload = await auth_service.verify_token(token)
    if payload:
        resp_data = {
            "authorized": True,
            "device_id": payload.get("device_id"),
            "device_name": payload.get("device_name"),
            "role": payload.get("role")
        }
        # Rétrocompatibilité : si un ancien token en clair a été migré
        new_jwt = payload.get("_new_token")
        if new_jwt:
            resp_data["migrated"] = True
            resp_data["token"] = new_jwt
            resp_data["new_token"] = new_jwt
            response.set_cookie(
                key="jarvis_device_token",
                value=new_jwt,
                max_age=315360000,
                httponly=False,
                samesite="lax",
                secure=True
            )
        return resp_data

    return JSONResponse(content={"authorized": False}, status_code=401)


@app.post("/api/auth/revoke")
async def revoke_device_or_token(req: RevokeRequest, request: Request):
    """Révoque immédiatement un token JWT ou un appareil via Redis."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    payload = await auth_service.verify_token(token)
    if not payload:
        return JSONResponse(content={"authorized": False, "message": "Accès non autorisé"}, status_code=401)

    target_token = req.token_id or payload.get("jti")
    target_device = req.device_id

    if target_token:
        await auth_service.revoke_token(target_token)
    if target_device:
        await auth_service.revoke_device(target_device)

    return {"status": "ok", "message": "Révocation effectuée avec succès"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("App:app", host="0.0.0.0", port=8000, reload=True)
