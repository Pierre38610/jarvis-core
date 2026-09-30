"""routers/spotify.py
Endpoints Spotify pour J.A.R.V.I.S.

Routes :
  GET  /api/media/spotify/login           -> redirect Spotify authorize (PKCE)
  GET  /api/media/spotify/callback        -> echange code, stockage tokens
  GET  /api/media/spotify/auth-status     -> {authenticated, display_name}
  GET  /api/media/spotify/status          -> etat courant du lecteur (poll HUD)
  POST /api/media/spotify/control         -> passerelle directe (frontend / tests)
  GET  /api/media/spotify/migration/status -> etat migration Deezer->Spotify
  POST /api/media/spotify/migration/start  -> lance la migration en arriere-plan
"""

import logging
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

import auth
from services.spotify_service import spotify_service
from services.cache import cache_service

logger = logging.getLogger("SpotifyRouter")

router = APIRouter()

# Duree de vie de l etat anti-CSRF dans Redis (10 minutes)
_STATE_TTL = 600


# ── Helpers auth ─────────────────────────────────────────────────────────────

def _is_authorized(request: Request) -> bool:
    token = (
        request.query_params.get("token")
        or request.cookies.get("jarvis_device_token")
    )
    return bool(token and auth.is_device_authorized(token))


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"authorized": False, "message": "Acces non autorise"},
    )


# ── OAuth ─────────────────────────────────────────────────────────────────────

@router.get("/api/media/spotify/login")
async def spotify_login(request: Request):
    """Redirige vers la page d autorisation Spotify (PKCE + state anti-CSRF Redis)."""
    if not _is_authorized(request):
        return _unauthorized()

    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = spotify_service.generate_pkce_pair()

    # Stocker verifier + state dans Redis (TTL 10 min)
    try:
        await cache_service.set(
            f"jarvis:spotify:pkce:{state}",
            code_verifier,
            ttl=_STATE_TTL,
        )
    except Exception as exc:
        logger.warning(f"[Spotify] Redis indisponible pour PKCE state : {exc}")
        # Fallback memoire (moins securise mais fonctionnel)
        _PKCE_MEMORY_FALLBACK[state] = code_verifier

    auth_url = spotify_service.build_auth_url(state, code_challenge)
    return RedirectResponse(url=auth_url)


# Fallback memoire si Redis est down lors du login
_PKCE_MEMORY_FALLBACK: dict = {}


@router.get("/api/media/spotify/callback")
async def spotify_callback(request: Request):
    """
    Endpoint de retour OAuth Spotify.
    Echange le code contre des tokens et les persiste.
    Ne requiert PAS de token JWT (c est un redirect externe).
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Spotify a refuse l autorisation : {error}"},
        )

    if not code or not state:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "code ou state manquant dans le callback."},
        )

    # Recuperer le code_verifier PKCE
    code_verifier = None
    try:
        code_verifier = await cache_service.get(f"jarvis:spotify:pkce:{state}")
        if code_verifier:
            await cache_service.delete(f"jarvis:spotify:pkce:{state}")
    except Exception:
        pass

    if not code_verifier:
        code_verifier = _PKCE_MEMORY_FALLBACK.pop(state, None)

    if not code_verifier:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "State PKCE invalide ou expire. Recommence la connexion.",
            },
        )

    try:
        token_data = await spotify_service.exchange_code(code, code_verifier)
        await spotify_service.save_tokens(token_data)
    except Exception as exc:
        logger.error(f"[Spotify] Erreur echange code : {exc}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Erreur lors de l echange du code : {exc}"},
        )

    info = spotify_service.get_user_info()
    display_name = info.get("display_name", "Utilisateur Spotify")

    # Rediriger vers le HUD apres connexion reussie
    return RedirectResponse(url="/?spotify_connected=1")


# ── Status et controle ────────────────────────────────────────────────────────

@router.get("/api/media/spotify/auth-status")
async def spotify_auth_status(request: Request):
    """Indique si Spotify est connecte et quel utilisateur."""
    if not _is_authorized(request):
        return _unauthorized()
    info = spotify_service.get_user_info()
    return JSONResponse(content=info)


@router.get("/api/media/spotify/status")
async def spotify_status(request: Request):
    """
    Etat temps reel du lecteur Spotify (pour poll HUD toutes les 3-5s).
    Retourne now_playing enrichi ou {is_playing: false} si rien ne joue.
    """
    if not _is_authorized(request):
        return _unauthorized()
    try:
        state = await spotify_service.now_playing()
        return JSONResponse(content=state)
    except Exception as exc:
        logger.warning(f"[Spotify] /status erreur : {exc}")
        return JSONResponse(content={"is_playing": False, "error": str(exc)})


@router.post("/api/media/spotify/control")
async def spotify_control(request: Request):
    """
    Passerelle directe pour le frontend / tests (sans passer par Gemini Live).
    Body JSON : {action, query, search_type, device, volume, volume_delta,
                  position_ms, state, playlist_name}
    """
    if not _is_authorized(request):
        return _unauthorized()
    try:
        body = await request.json()
    except Exception:
        body = {}

    result = await spotify_service.control(
        action=body.get("action", "now_playing"),
        query=body.get("query", ""),
        search_type=body.get("search_type", "track"),
        device=body.get("device"),
        volume=body.get("volume"),
        volume_delta=body.get("volume_delta"),
        position_ms=body.get("position_ms"),
        state=body.get("state"),
        playlist_name=body.get("playlist_name"),
    )
    return JSONResponse(content=result)


# ── Migration ─────────────────────────────────────────────────────────────────

@router.get("/api/media/spotify/migration/status")
async def migration_status(request: Request):
    """Retourne l etat courant de la migration Deezer->Spotify."""
    if not _is_authorized(request):
        return _unauthorized()
    try:
        from services.deezer_migration_service import deezer_migration_service
        status = deezer_migration_service.get_status()
        return JSONResponse(content=status)
    except ImportError:
        return JSONResponse(
            content={"status": "not_available",
                     "message": "Service de migration non initialise."}
        )
    except Exception as exc:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})


@router.post("/api/media/spotify/migration/start")
async def migration_start(request: Request):
    """Lance la migration Deezer->Spotify en arriere-plan."""
    if not _is_authorized(request):
        return _unauthorized()
    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        import asyncio
        from services.deezer_migration_service import deezer_migration_service

        dry_run = body.get("dry_run", False)
        run_id = body.get("run_id", "")

        asyncio.create_task(
            deezer_migration_service.run(dry_run=dry_run, run_id=run_id)
        )
        return JSONResponse(content={
            "status": "started",
            "dry_run": dry_run,
            "message": "Migration Deezer->Spotify lancee en arriere-plan.",
        })
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service de migration non disponible."},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )
