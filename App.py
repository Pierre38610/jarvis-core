"""J.A.R.V.I.S. Core Server - Stark Industries AI Assistant
Architecture modulaire FastAPI : chaque domaine fonctionnel est isolé dans son propre module.

Structure :
- core/shared_state.py     : État global, clients Gemini, helpers broadcast
- core/tools/declarations.py : FunctionDeclarations Gemini Live
- core/tools/dispatcher.py   : Dispatch de chaque outil vers le service métier
- routers/voice.py         : WebSocket /ws  (Gemini Live full-duplex)
- routers/local_agent.py   : WebSocket /ws/local-agent + /api/local-agent/status
- routers/chat.py          : /api/chat/*
- routers/media.py         : /api/media/deezer/*
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
from routers import voice, local_agent, chat, media, browser, supervision, settings

app = FastAPI(title="J.A.R.V.I.S. Core Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# ─── Enregistrement de tous les routeurs ─────────────────────────────────────
app.include_router(voice.router)
app.include_router(local_agent.router)
app.include_router(chat.router)
app.include_router(media.router)
app.include_router(browser.router)
app.include_router(supervision.router)
app.include_router(settings.router)


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

    # 3. Bridge Deezer
    try:
        from deezer_bridge import deezer_controller
        await deezer_controller.start()
    except Exception as e:
        print(f"[Deezer Startup] Erreur lancement bridge : {e}")


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

    try:
        from deezer_bridge import deezer_controller
        await deezer_controller.stop()
    except Exception:
        pass


# ─── Routes racines et authentification ──────────────────────────────────────

@app.get("/")
async def serve_ui():
    """Sert l'interface HUD mobile Stark Industries."""
    index_file = os.path.join(config.STATIC_DIR, "index.html")
    return FileResponse(index_file)


class AuthRequest(BaseModel):
    password: str


class QRAuthRequest(BaseModel):
    ticket: str


@app.post("/api/auth")
async def authenticate_device(req: AuthRequest, request: Request, response: Response):
    """Vérifie le mot de passe maître et génère un jeton permanent d'appareil."""
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


@app.post("/api/auth-qr")
async def authenticate_via_qr(req: QRAuthRequest, request: Request, response: Response):
    """Enregistre l'appareil sans mot de passe après scan d'un QR code valide."""
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
    """Vérifie si le terminal possède un jeton d'enregistrement valide."""
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    if auth.is_device_authorized(token):
        return {"authorized": True}
    return JSONResponse(content={"authorized": False}, status_code=401)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("App:app", host="0.0.0.0", port=8000, reload=True)
