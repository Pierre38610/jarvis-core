"""services/spotify_service.py
Client complet de la Web API Spotify pour J.A.R.V.I.S.

OAuth 2.0 Authorization Code + PKCE cote VPS.
Tokens stockes chiffres (Fernet, cle derivee de JWT_SECRET_KEY) dans SQLite.
Access token en cache Redis avec TTL. Refresh auto avant expiration et sur 401.
Verrou asyncio anti-refresh concurrent.
Gestion robuste : 429 (Retry-After), 401 (refresh+retry 1x), 404, 403.
Resolution floue d appareil : alias SQLite + type + nom exact.
Lancement auto Spotify sur PC via agent local (spotify_launch RPC).
Verification post-action (GET /me/player) avant verified=True.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from cryptography.fernet import Fernet

import config
from services.cache import cache_service
from services.console_monitor import console_monitor

logger = logging.getLogger("SpotifyService")

# ── Constantes ────────────────────────────────────────────────────────────────
SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_AUTH = "https://accounts.spotify.com"

SPOTIFY_SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "user-library-modify",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-follow-read",
    "user-follow-modify",
    "user-read-private",
    "user-read-email",
    "streaming",
])

REDIS_TOKEN_KEY = "jarvis:spotify:access_token"
REDIS_TTL_BUFFER = 60          # refresh 60s avant expiration
PC_POLL_INTERVAL = 2.0         # secondes entre chaque poll /devices
PC_POLL_MAX = 7                # 7 x 2s = 14s max
FUZZY_THRESHOLD = 0.72
FUZZY_AUTO_ACCEPT = 0.85
DURATION_DELTA_MAX = 3.0

DB_PATH = config.DB_PATH


# ── Chiffrement Fernet ────────────────────────────────────────────────────────

def _derive_fernet_key() -> bytes:
    """Derive une cle Fernet 32-octets depuis JWT_SECRET_KEY via SHA-256."""
    secret = (os.environ.get("JWT_SECRET_KEY") or getattr(config, "JWT_SECRET_KEY", "")).encode()
    if not secret:
        secret = b"jarvis_spotify_fallback_not_secure"
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


_FERNET: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        _FERNET = Fernet(_derive_fernet_key())
    return _FERNET


def _encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


# ── Normalisation / similarite ────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Minuscules, sans accents, sans suffixes parasites, sans ponctuation."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(
        r"\s*[-–]\s*(remaster(ed)?|live|acoustic|remix|edit|version|radio|single).*",
        "", text, flags=re.I
    )
    text = re.sub(r"\s*\(feat\..*?\)", "", text, flags=re.I)
    text = re.sub(r"\s*ft\..*", "", text, flags=re.I)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _similarity(a: str, b: str) -> float:
    """Score de similarite [0,1] entre deux chaines normalisees."""
    try:
        from rapidfuzz.fuzz import token_sort_ratio
        return token_sort_ratio(_normalize(a), _normalize(b)) / 100.0
    except ImportError:
        def _bigrams(s: str):
            s = _normalize(s)
            return set(s[i:i + 2] for i in range(len(s) - 1))
        bg_a, bg_b = _bigrams(a), _bigrams(b)
        if not bg_a or not bg_b:
            return 0.0
        return len(bg_a & bg_b) / len(bg_a | bg_b)


# ── Service principal ─────────────────────────────────────────────────────────

class SpotifyService:
    """Client Web API Spotify complet pour J.A.R.V.I.S."""

    def __init__(self) -> None:
        self._client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        self._client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
        self._redirect_uri = os.environ.get(
            "SPOTIFY_REDIRECT_URI",
            "https://jarvis.signalcraftapps.com/api/media/spotify/callback",
        ).strip()
        self._refresh_lock = asyncio.Lock()
        self._db_ready = False

    @property
    def client_id(self) -> str:
        cid = os.environ.get("SPOTIFY_CLIENT_ID", "").strip() or getattr(config, "SPOTIFY_CLIENT_ID", "").strip() or self._client_id
        if not cid:
            # Rechargement de secours depuis le fichier .env si non chargé
            try:
                from dotenv import load_dotenv
                env_file = os.path.join(config.BASE_DIR, ".env")
                if os.path.exists(env_file):
                    load_dotenv(env_file, override=True)
                    cid = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
            except Exception:
                pass
        return cid

    @property
    def client_secret(self) -> str:
        csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip() or getattr(config, "SPOTIFY_CLIENT_SECRET", "").strip() or self._client_secret
        if not csec:
            try:
                from dotenv import load_dotenv
                env_file = os.path.join(config.BASE_DIR, ".env")
                if os.path.exists(env_file):
                    load_dotenv(env_file, override=True)
                    csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
            except Exception:
                pass
        return csec

    @property
    def redirect_uri(self) -> str:
        return (
            os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()
            or getattr(config, "SPOTIFY_REDIRECT_URI", "").strip()
            or self._redirect_uri
            or "https://jarvis.signalcraftapps.com/api/media/spotify/callback"
        )

    # ── Init DB ───────────────────────────────────────────────────────────────

    # Schema inline — pas de dépendance fichier externe (fonctionne même si db/spotify_schema.sql absent du VPS)
    _SCHEMA_SQL = (
        "CREATE TABLE IF NOT EXISTS spotify_tokens ("
        "id INTEGER PRIMARY KEY DEFAULT 1,"
        "access_token_enc TEXT NOT NULL,"
        "refresh_token_enc TEXT NOT NULL,"
        "expires_at REAL NOT NULL,"
        "scope TEXT NOT NULL DEFAULT '',"
        "token_type TEXT NOT NULL DEFAULT 'Bearer',"
        "spotify_user_id TEXT NOT NULL DEFAULT '',"
        "display_name TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ");"
        "CREATE TABLE IF NOT EXISTS spotify_device_aliases ("
        "alias TEXT PRIMARY KEY,"
        "device_type TEXT,"
        "device_name_pattern TEXT"
        ");"
        "INSERT OR IGNORE INTO spotify_device_aliases (alias, device_type, device_name_pattern) VALUES"
        " ('pc','Computer',NULL),('ordi','Computer',NULL),('ordinateur','Computer',NULL),"
        " ('portable','Computer',NULL),('laptop','Computer',NULL),"
        " ('telephone','Smartphone',NULL),('tel','Smartphone',NULL),('mobile','Smartphone',NULL),"
        " ('phone','Smartphone',NULL),('enceinte','Speaker',NULL),('speaker','Speaker',NULL),"
        " ('sono','Speaker',NULL),('tv','TV',NULL),('tele','TV',NULL);"
        "CREATE TABLE IF NOT EXISTS migration_state ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "run_id TEXT NOT NULL DEFAULT '',"
        "source_playlist TEXT NOT NULL DEFAULT '',"
        "deezer_track_id INTEGER NOT NULL,"
        "deezer_title TEXT NOT NULL DEFAULT '',"
        "deezer_artist TEXT NOT NULL DEFAULT '',"
        "deezer_album TEXT NOT NULL DEFAULT '',"
        "deezer_isrc TEXT NOT NULL DEFAULT '',"
        "deezer_duration_s REAL NOT NULL DEFAULT 0,"
        "spotify_track_id TEXT NOT NULL DEFAULT '',"
        "spotify_title TEXT NOT NULL DEFAULT '',"
        "spotify_artist TEXT NOT NULL DEFAULT '',"
        "confidence_score REAL NOT NULL DEFAULT 0.0,"
        "duration_delta_s REAL NOT NULL DEFAULT 0.0,"
        "match_method TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL DEFAULT 'pending',"
        "error_msg TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "updated_at TEXT NOT NULL DEFAULT (datetime('now'))"
        ");"
        "CREATE INDEX IF NOT EXISTS idx_migration_run_id ON migration_state (run_id);"
        "CREATE INDEX IF NOT EXISTS idx_migration_playlist ON migration_state (source_playlist);"
        "CREATE INDEX IF NOT EXISTS idx_migration_status ON migration_state (status);"
    )

    def _ensure_db(self) -> None:
        if self._db_ready:
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executescript(self._SCHEMA_SQL)
            conn.commit()
            conn.close()
            self._db_ready = True
            logger.info("[Spotify] Tables SQLite initialisées (spotify_tokens, migration_state).")
        except Exception as exc:
            logger.warning(f"[Spotify] Erreur init DB : {exc}")

    # ── OAuth / PKCE ──────────────────────────────────────────────────────────

    @staticmethod
    def generate_pkce_pair() -> Tuple[str, str]:
        """Retourne (code_verifier, code_challenge) pour le flux PKCE."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return verifier, challenge

    def build_auth_url(self, state: str, code_challenge: str) -> str:
        """Construit l URL Spotify authorize (PKCE)."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SPOTIFY_SCOPES,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        }
        return f"{SPOTIFY_AUTH}/authorize?" + urllib.parse.urlencode(params)

    async def exchange_code(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """Echange le code PKCE contre des tokens."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SPOTIFY_AUTH}/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code != 200:
            raise ValueError(f"Token exchange failed {resp.status_code}: {resp.text}")
        return resp.json()

    async def save_tokens(self, token_data: Dict[str, Any]) -> None:
        """Persiste les tokens chiffres (SQLite) et l access token dans Redis."""
        self._ensure_db()
        now = time.time()
        expires_at = now + token_data.get("expires_in", 3600) - REDIS_TTL_BUFFER
        acc_enc = _encrypt(token_data["access_token"])
        ref_enc = _encrypt(token_data.get("refresh_token", ""))
        scope = token_data.get("scope", "")

        user_id = display_name = ""
        try:
            profile = await self._api_get("/me", token=token_data["access_token"])
            user_id = profile.get("id", "")
            display_name = profile.get("display_name", "")
        except Exception:
            pass

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT OR REPLACE INTO spotify_tokens
               (id, access_token_enc, refresh_token_enc, expires_at, scope,
                spotify_user_id, display_name, updated_at)
               VALUES (1,?,?,?,?,?,?,?)""",
            (acc_enc, ref_enc, expires_at, scope, user_id, display_name,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

        try:
            ttl = max(60, int(expires_at - now))
            await cache_service.set(REDIS_TOKEN_KEY, token_data["access_token"], ttl=ttl)
        except Exception:
            pass

    def _load_tokens_db(self) -> Optional[Dict[str, Any]]:
        """Charge la ligne de tokens depuis SQLite (synchrone)."""
        self._ensure_db()
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT access_token_enc, refresh_token_enc, expires_at, scope, "
                "display_name, spotify_user_id FROM spotify_tokens WHERE id=1"
            ).fetchone()
            conn.close()
            if not row:
                return None
            return {
                "access_token_enc": row[0],
                "refresh_token_enc": row[1],
                "expires_at": row[2],
                "scope": row[3],
                "display_name": row[4],
                "spotify_user_id": row[5],
            }
        except Exception:
            return None

    async def _refresh(self) -> str:
        """Rafraichit l access token. Thread-safe via asyncio.Lock."""
        async with self._refresh_lock:
            # Double-check : un autre appel peut avoir rafraichi pendant l attente
            try:
                cached = await cache_service.get(REDIS_TOKEN_KEY)
                if cached:
                    return cached
            except Exception:
                pass

            row = self._load_tokens_db()
            if not row:
                raise ValueError("no_tokens")
            refresh_token = _decrypt(row["refresh_token_enc"])

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{SPOTIFY_AUTH}/api/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self.client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                raise ValueError(f"Refresh failed {resp.status_code}: {resp.text}")

            data = resp.json()
            now = time.time()
            expires_at = now + data.get("expires_in", 3600) - REDIS_TTL_BUFFER
            acc_enc = _encrypt(data["access_token"])
            new_ref = data.get("refresh_token")
            ref_enc = _encrypt(new_ref) if new_ref else row["refresh_token_enc"]

            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE spotify_tokens SET access_token_enc=?, refresh_token_enc=?, "
                "expires_at=?, updated_at=? WHERE id=1",
                (acc_enc, ref_enc, expires_at, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()

            try:
                ttl = max(60, int(expires_at - now))
                await cache_service.set(REDIS_TOKEN_KEY, data["access_token"], ttl=ttl)
            except Exception:
                pass

            return data["access_token"]

    async def _get_token(self) -> str:
        """Retourne un access token valide. Leve ValueError('no_tokens') si non connecte."""
        try:
            cached = await cache_service.get(REDIS_TOKEN_KEY)
            if cached:
                return cached
        except Exception:
            pass

        row = self._load_tokens_db()
        if not row:
            raise ValueError("no_tokens")

        now = time.time()
        if row["expires_at"] > now + 30:
            tok = _decrypt(row["access_token_enc"])
            try:
                ttl = max(60, int(row["expires_at"] - now))
                await cache_service.set(REDIS_TOKEN_KEY, tok, ttl=ttl)
            except Exception:
                pass
            return tok

        return await self._refresh()

    def is_authenticated(self) -> bool:
        """Verifie rapidement (sans reseau) si des tokens sont en base."""
        return self._load_tokens_db() is not None

    def get_user_info(self) -> Dict[str, Any]:
        row = self._load_tokens_db()
        if not row:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "display_name": row.get("display_name", ""),
            "spotify_user_id": row.get("spotify_user_id", ""),
            "scope": row.get("scope", ""),
        }

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    async def _get(self, path: str, token: Optional[str] = None,
                   params: Optional[Dict] = None, _retry: bool = True) -> Dict[str, Any]:
        if token is None:
            token = await self._get_token()
        url = f"{SPOTIFY_API}{path}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"}, params=params or {})

        if r.status_code == 401 and _retry:
            try:
                await cache_service.delete(REDIS_TOKEN_KEY)
            except Exception:
                pass
            return await self._get(path, token=await self._refresh(), params=params, _retry=False)
        if r.status_code == 429:
            ra = int(r.headers.get("Retry-After", "2"))
            logger.warning(f"[Spotify 429] GET {path} — attente {ra}s")
            await asyncio.sleep(ra)
            return await self._get(path, token=token, params=params, _retry=_retry)
        if r.status_code == 404:
            raise ValueError("not_found")
        if r.status_code == 403:
            body = r.json() if r.content else {}
            raise ValueError(f"forbidden:{body.get('error', {}).get('reason', '')}")
        if r.status_code == 204:
            return {}
        r.raise_for_status()
        return r.json() if r.content else {}

    # Alias interne expose pour save_tokens -> profil utilisateur
    _api_get = _get

    async def _put(self, path: str, body: Optional[Dict] = None,
                   params: Optional[Dict] = None, _retry: bool = True) -> Dict[str, Any]:
        token = await self._get_token()
        url = f"{SPOTIFY_API}{path}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.put(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body or {}, params=params or {},
            )
        if r.status_code == 401 and _retry:
            try:
                await cache_service.delete(REDIS_TOKEN_KEY)
            except Exception:
                pass
            return await self._put(path, body=body, params=params, _retry=False)
        if r.status_code == 429:
            ra = int(r.headers.get("Retry-After", "2"))
            await asyncio.sleep(ra)
            return await self._put(path, body=body, params=params, _retry=_retry)
        if r.status_code == 404:
            raise ValueError("not_found")
        if r.status_code == 403:
            body_j = r.json() if r.content else {}
            raise ValueError(f"forbidden:{body_j.get('error', {}).get('reason', '')}")
        if r.status_code in (200, 204):
            return r.json() if r.content else {}
        r.raise_for_status()
        return {}

    async def _post(self, path: str, body: Optional[Any] = None,
                    params: Optional[Dict] = None, _retry: bool = True) -> Dict[str, Any]:
        token = await self._get_token()
        url = f"{SPOTIFY_API}{path}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body, params=params or {},
            )
        if r.status_code == 401 and _retry:
            try:
                await cache_service.delete(REDIS_TOKEN_KEY)
            except Exception:
                pass
            return await self._post(path, body=body, params=params, _retry=False)
        if r.status_code == 429:
            ra = int(r.headers.get("Retry-After", "2"))
            await asyncio.sleep(ra)
            return await self._post(path, body=body, params=params, _retry=_retry)
        if r.status_code in (200, 201, 204):
            return r.json() if r.content else {}
        r.raise_for_status()
        return {}

    async def _delete(self, path: str, body: Optional[Any] = None,
                      _retry: bool = True) -> Dict[str, Any]:
        token = await self._get_token()
        url = f"{SPOTIFY_API}{path}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.request(
                "DELETE", url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
        if r.status_code == 401 and _retry:
            try:
                await cache_service.delete(REDIS_TOKEN_KEY)
            except Exception:
                pass
            return await self._delete(path, body=body, _retry=False)
        if r.status_code == 429:
            ra = int(r.headers.get("Retry-After", "2"))
            await asyncio.sleep(ra)
            return await self._delete(path, body=body, _retry=_retry)
        if r.status_code in (200, 204):
            return r.json() if r.content else {}
        r.raise_for_status()
        return {}

    async def _paginate(self, path: str, params: Optional[Dict] = None,
                        key: str = "items", limit: int = 50) -> List[Dict]:
        """Charge toutes les pages via le champ 'next'."""
        results: List[Dict] = []
        p = dict(params or {})
        p["limit"] = limit
        p["offset"] = 0
        while True:
            data = await self._get(path, params=p)
            page = data.get(key) or data.get("items") or []
            results.extend(page)
            nxt = data.get("next")
            if not nxt:
                break
            qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(nxt).query))
            p["offset"] = int(qs.get("offset", p["offset"] + limit))
        return results

    # ── Appareils ─────────────────────────────────────────────────────────────

    async def get_devices(self) -> List[Dict[str, Any]]:
        data = await self._get("/me/player/devices")
        return data.get("devices", [])

    def _resolve_alias(self, hint: str) -> Optional[str]:
        """Retourne device_type depuis la table spotify_device_aliases (SQLite)."""
        self._ensure_db()
        key = _normalize(hint)
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT device_type FROM spotify_device_aliases WHERE alias=?", (key,)
            ).fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None

    async def resolve_device(self, hint: str) -> Optional[Dict[str, Any]]:
        """Resout un hint libre vers un appareil Spotify reel."""
        if not hint:
            return None
        devices = await self.get_devices()
        if not devices:
            return None
        hint_n = _normalize(hint)
        # 1. Exact
        for d in devices:
            if _normalize(d.get("name", "")) == hint_n:
                return d
        # 2. Alias SQLite -> type
        alias_type = self._resolve_alias(hint)
        if alias_type:
            for d in devices:
                if d.get("type", "").lower() == alias_type.lower():
                    return d
        # 3. Sous-chaine
        for d in devices:
            if hint_n in _normalize(d.get("name", "")):
                return d
        return None

    def _is_pc_hint(self, hint: str) -> bool:
        alias_type = self._resolve_alias(hint)
        if alias_type == "Computer":
            return True
        return any(k in _normalize(hint) for k in ["pc", "ordi", "portable", "laptop", "computer"])

    async def get_active_device(self) -> Optional[Dict[str, Any]]:
        for d in await self.get_devices():
            if d.get("is_active"):
                return d
        return None

    async def _last_device_id(self) -> Optional[str]:
        try:
            return await cache_service.get("jarvis:spotify:last_device")
        except Exception:
            return None

    async def _save_device(self, device_id: str) -> None:
        try:
            await cache_service.set("jarvis:spotify:last_device", device_id, ttl=604800)
        except Exception:
            pass

    async def _pick_device(self, hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Retourne (device_id, error_msg) selon la priorite :
        hint specifie > actif > dernier utilise > PC auto > demande.
        """
        if hint:
            resolved = await self.resolve_device(hint)
            if resolved:
                return resolved["id"], None
            if self._is_pc_hint(hint):
                pc_id = await self._launch_pc_spotify()
                if pc_id:
                    return pc_id, None
                return None, (
                    "Je n arrive pas a joindre Spotify sur ton PC. "
                    "Ouvre Spotify manuellement et redemande-moi."
                )
            return None, (
                f"Ton {hint} n est pas visible dans Spotify Connect. "
                "Ouvre l appli Spotify dessus et redemande-moi."
            )

        active = await self.get_active_device()
        if active:
            return active["id"], None

        last = await self._last_device_id()
        if last:
            devs = await self.get_devices()
            if any(d["id"] == last for d in devs):
                return last, None

        from services.local_agent_service import local_agent_service
        if local_agent_service.is_connected():
            devs = await self.get_devices()
            for d in devs:
                if d.get("type") == "Computer":
                    return d["id"], None
            pc_id = await self._launch_pc_spotify()
            if pc_id:
                return pc_id, None

        return None, "Sur quel appareil veux-tu ecouter ? (pc, telephone, enceinte...)"

    async def _launch_pc_spotify(self, uri: Optional[str] = None) -> Optional[str]:
        """
        Lance Spotify sur PC via RPC spotify_launch, attend jusqu a 14s.
        Retourne device_id si detecte, None sinon.
        """
        from services.local_agent_service import local_agent_service
        if not local_agent_service.is_connected():
            return None
        try:
            res = await local_agent_service.execute_command(
                "spotify_launch", timeout=5.0, uri=uri or ""
            )
            if res.get("status") == "error":
                return None
        except Exception:
            return None
        for _ in range(PC_POLL_MAX):
            await asyncio.sleep(PC_POLL_INTERVAL)
            try:
                devs = await self.get_devices()
                pc = next((d for d in devs if d.get("type") == "Computer"), None)
                if pc:
                    return pc["id"]
            except Exception:
                pass
        return None

    async def transfer_playback(self, device_id: str, play: bool = True) -> None:
        await self._put("/me/player", body={"device_ids": [device_id], "play": play})

    # ── Verification post-action ──────────────────────────────────────────────

    async def _verify(self, device_id: Optional[str] = None,
                      is_playing: bool = True) -> bool:
        try:
            await asyncio.sleep(0.8)
            state = await self._get("/me/player")
            if not state:
                return False
            if is_playing and not state.get("is_playing", False):
                return False
            if device_id:
                cur = (state.get("device") or {}).get("id", "")
                if cur != device_id:
                    return False
            return True
        except Exception:
            return False

    # ── Etat courant ──────────────────────────────────────────────────────────

    async def now_playing(self) -> Dict[str, Any]:
        try:
            state = await self._get("/me/player")
        except ValueError as e:
            if "no_tokens" in str(e):
                return {"authenticated": False}
            raise
        if not state:
            return {"is_playing": False, "nothing_playing": True}
        item = state.get("item") or {}
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        album = item.get("album") or {}
        images = album.get("images", [])
        cover_url = images[0]["url"] if images else ""
        prog_ms = state.get("progress_ms", 0)
        dur_ms = item.get("duration_ms", 0)
        dev = state.get("device") or {}
        return {
            "is_playing": state.get("is_playing", False),
            "track_name": item.get("name", ""),
            "artist": artists,
            "album": album.get("name", ""),
            "cover_url": cover_url,
            "progress_ms": prog_ms,
            "duration_ms": dur_ms,
            "progress_pct": round(prog_ms / dur_ms * 100, 1) if dur_ms else 0,
            "device_name": dev.get("name", ""),
            "device_type": dev.get("type", ""),
            "device_id": dev.get("id", ""),
            "volume_percent": dev.get("volume_percent", 0),
            "shuffle": state.get("shuffle_state", False),
            "repeat": state.get("repeat_state", "off"),
            "spotify_uri": item.get("uri", ""),
        }

    # ── Controles ─────────────────────────────────────────────────────────────

    async def play(self, device_id: Optional[str] = None,
                   context_uri: Optional[str] = None,
                   uris: Optional[List[str]] = None,
                   offset: Optional[int] = None) -> None:
        body: Dict[str, Any] = {}
        if context_uri:
            body["context_uri"] = context_uri
            if offset is not None:
                body["offset"] = {"position": offset}
        elif uris:
            body["uris"] = uris
        params = {"device_id": device_id} if device_id else {}
        await self._put("/me/player/play", body=body, params=params)

    async def pause(self, device_id: Optional[str] = None) -> None:
        params = {"device_id": device_id} if device_id else {}
        await self._put("/me/player/pause", params=params)

    async def next_track(self, device_id: Optional[str] = None) -> None:
        params = {"device_id": device_id} if device_id else {}
        await self._post("/me/player/next", params=params)

    async def previous_track(self, device_id: Optional[str] = None) -> None:
        params = {"device_id": device_id} if device_id else {}
        await self._post("/me/player/previous", params=params)

    async def seek(self, position_ms: int, device_id: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"position_ms": position_ms}
        if device_id:
            params["device_id"] = device_id
        await self._put("/me/player/seek", params=params)

    async def set_volume(self, pct: int, device_id: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"volume_percent": max(0, min(100, pct))}
        if device_id:
            params["device_id"] = device_id
        await self._put("/me/player/volume", params=params)

    async def set_shuffle(self, enabled: bool, device_id: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"state": str(enabled).lower()}
        if device_id:
            params["device_id"] = device_id
        await self._put("/me/player/shuffle", params=params)

    async def set_repeat(self, state: str, device_id: Optional[str] = None) -> None:
        """state: 'off' | 'track' | 'context'"""
        params: Dict[str, Any] = {"state": state}
        if device_id:
            params["device_id"] = device_id
        await self._put("/me/player/repeat", params=params)

    # ── File d attente ────────────────────────────────────────────────────────

    async def queue_add(self, uri: str, device_id: Optional[str] = None) -> None:
        params: Dict[str, Any] = {"uri": uri}
        if device_id:
            params["device_id"] = device_id
        await self._post("/me/player/queue", params=params)

    async def get_queue(self) -> Dict[str, Any]:
        data = await self._get("/me/player/queue")
        return {
            "currently_playing": data.get("currently_playing"),
            "queue": [
                {"name": t.get("name"),
                 "artist": ", ".join(a["name"] for a in t.get("artists", [])),
                 "uri": t.get("uri")}
                for t in data.get("queue", [])[:20]
            ],
        }

    # ── Recherche ─────────────────────────────────────────────────────────────

    async def search(self, query: str, stype: str = "track",
                     limit: int = 10) -> Dict[str, Any]:
        return await self._get("/search", params={"q": query, "type": stype,
                                                   "limit": limit, "market": "FR"})

    async def find_best_track(self, query: str,
                              artist: Optional[str] = None) -> Optional[Dict[str, Any]]:
        q = f"track:{query} artist:{artist}" if artist else query
        data = await self.search(q, "track", 10)
        tracks = (data.get("tracks") or {}).get("items", [])
        if not tracks:
            return None

        def score(t: Dict) -> float:
            sim = _similarity(t.get("name", ""), query)
            return sim * 0.7 + (t.get("popularity", 0) / 100.0) * 0.3

        return max(tracks, key=score)

    async def find_track_by_isrc(self, isrc: str) -> Optional[Dict[str, Any]]:
        data = await self.search(f"isrc:{isrc}", "track", 1)
        items = (data.get("tracks") or {}).get("items", [])
        return items[0] if items else None

    # ── Lecture intelligente ──────────────────────────────────────────────────

    async def play_query(self, query: str, stype: str = "track",
                         device_hint: Optional[str] = None) -> Dict[str, Any]:
        """Recherche et lance la lecture du meilleur resultat."""
        device_id, needs_msg = await self._pick_device(device_hint)
        if needs_msg:
            return {"status": "needs_user", "needs_user": True, "message": needs_msg}

        context_uri: Optional[str] = None
        uris: Optional[List[str]] = None
        label = query

        if stype in ("liked", "loved"):
            liked = await self._get("/me/tracks", params={"limit": 20, "market": "FR"})
            uris = [item["track"]["uri"] for item in liked.get("items", [])]
            label = "mes titres likes"

        elif stype == "track":
            track = await self.find_best_track(query)
            if not track:
                return {"status": "not_found", "message": f"'{query}' introuvable sur Spotify."}
            uris = [track["uri"]]
            label = f"{track['name']} — {', '.join(a['name'] for a in track.get('artists', []))}"

        elif stype == "artist":
            data = await self.search(query, "artist", 1)
            items = (data.get("artists") or {}).get("items", [])
            if not items:
                return {"status": "not_found", "message": f"Artiste '{query}' introuvable."}
            context_uri = items[0]["uri"]
            label = items[0]["name"]

        elif stype == "album":
            data = await self.search(query, "album", 1)
            items = (data.get("albums") or {}).get("items", [])
            if not items:
                return {"status": "not_found", "message": f"Album '{query}' introuvable."}
            context_uri = items[0]["uri"]
            label = f"{items[0]['name']} — {', '.join(a['name'] for a in items[0].get('artists', []))}"

        elif stype == "playlist":
            data = await self.search(query, "playlist", 5)
            items = (data.get("playlists") or {}).get("items", [])
            if not items:
                return {"status": "not_found", "message": f"Playlist '{query}' introuvable."}
            best = max(items, key=lambda p: _similarity(p.get("name", ""), query))
            context_uri = best["uri"]
            label = best["name"]

        elif stype == "episode":
            data = await self.search(query, "episode", 1)
            items = (data.get("episodes") or {}).get("items", [])
            if not items:
                return {"status": "not_found", "message": f"Episode '{query}' introuvable."}
            uris = [items[0]["uri"]]
            label = items[0]["name"]

        await self.transfer_playback(device_id, play=False)
        await asyncio.sleep(0.5)
        await self.play(device_id=device_id, context_uri=context_uri, uris=uris)
        await self._save_device(device_id)
        verified = await self._verify(device_id)

        devs = await self.get_devices()
        dev_name = next((d["name"] for d in devs if d["id"] == device_id), "l appareil")

        return {
            "status": "done",
            "verified": verified,
            "track_label": label,
            "device_name": dev_name,
            "message": f"C est parti — {label} sur {dev_name}.",
        }

    # ── Biblioteque ───────────────────────────────────────────────────────────

    async def like_current_track(self) -> Dict[str, Any]:
        np = await self.now_playing()
        uri = np.get("spotify_uri", "")
        if not uri:
            return {"status": "failed", "message": "Aucune lecture en cours."}
        track_id = uri.split(":")[-1]
        await self._put("/me/tracks", params={"ids": track_id})
        return {"status": "done", "verified": True,
                "message": f"{np.get('track_name', 'Le titre')} ajoute a tes likes."}

    async def unlike_current_track(self) -> Dict[str, Any]:
        np = await self.now_playing()
        uri = np.get("spotify_uri", "")
        if not uri:
            return {"status": "failed", "message": "Aucune lecture en cours."}
        track_id = uri.split(":")[-1]
        await self._delete("/me/tracks", body={"ids": [track_id]})
        return {"status": "done", "verified": True,
                "message": f"{np.get('track_name', 'Le titre')} retire de tes likes."}

    async def save_album(self, album_id: str) -> Dict[str, Any]:
        await self._put("/me/albums", params={"ids": album_id})
        return {"status": "done", "verified": True, "message": "Album sauvegarde."}

    async def follow_artist(self, artist_id: str) -> Dict[str, Any]:
        await self._put("/me/following", body={"ids": [artist_id]}, params={"type": "artist"})
        return {"status": "done", "verified": True, "message": "Artiste suivi."}

    async def unfollow_artist(self, artist_id: str) -> Dict[str, Any]:
        await self._delete("/me/following", body={"ids": [artist_id]})
        return {"status": "done", "verified": True, "message": "Artiste non suivi."}

    async def get_liked_tracks(self, limit: int = 50) -> List[Dict[str, Any]]:
        items = await self._paginate("/me/tracks", params={"market": "FR"}, limit=limit)
        return [
            {
                "name": (item.get("track") or {}).get("name", ""),
                "artist": ", ".join(
                    a["name"] for a in (item.get("track") or {}).get("artists", [])
                ),
                "uri": (item.get("track") or {}).get("uri", ""),
                "id": (item.get("track") or {}).get("id", ""),
            }
            for item in items if item.get("track")
        ]

    # ── Playlists ─────────────────────────────────────────────────────────────

    async def get_user_playlists(self) -> List[Dict[str, Any]]:
        items = await self._paginate("/me/playlists", limit=50)
        return [
            {
                "id": p["id"], "name": p["name"], "uri": p["uri"],
                "track_count": p.get("tracks", {}).get("total", 0),
                "public": p.get("public", False),
            }
            for p in items
        ]

    async def create_playlist(self, name: str, description: str = "",
                              public: bool = False) -> Dict[str, Any]:
        info = self.get_user_info()
        user_id = info.get("spotify_user_id", "")
        if not user_id:
            profile = await self._get("/me")
            user_id = profile["id"]
        data = await self._post(
            f"/users/{user_id}/playlists",
            body={"name": name, "description": description, "public": public},
        )
        return {"id": data["id"], "uri": data["uri"], "name": data["name"]}

    async def add_tracks_to_playlist(self, playlist_id: str,
                                     uris: List[str]) -> Dict[str, Any]:
        """Ajoute des tracks par paquets de 100."""
        for i in range(0, len(uris), 100):
            await self._post(f"/playlists/{playlist_id}/tracks",
                             body={"uris": uris[i:i + 100]})
        return {"status": "done", "added": len(uris)}

    async def remove_tracks_from_playlist(self, playlist_id: str,
                                          uris: List[str]) -> Dict[str, Any]:
        await self._delete(f"/playlists/{playlist_id}/tracks",
                           body={"tracks": [{"uri": u} for u in uris]})
        return {"status": "done", "removed": len(uris)}

    async def add_current_to_playlist(self, playlist_name: str) -> Dict[str, Any]:
        np = await self.now_playing()
        uri = np.get("spotify_uri", "")
        if not uri:
            return {"status": "failed", "message": "Aucune lecture en cours."}
        playlists = await self.get_user_playlists()
        best = max(playlists, key=lambda p: _similarity(p["name"], playlist_name), default=None)
        if not best or _similarity(best["name"], playlist_name) < 0.5:
            return {"status": "not_found", "message": f"Playlist '{playlist_name}' introuvable."}
        await self.add_tracks_to_playlist(best["id"], [uri])
        return {"status": "done", "verified": True,
                "message": f"{np.get('track_name', 'Le titre')} ajoute a '{best['name']}'."}

    # ── Decouverte ────────────────────────────────────────────────────────────

    async def get_top_tracks(self, time_range: str = "medium_term",
                             limit: int = 20) -> List[Dict]:
        data = await self._get("/me/top/tracks",
                               params={"time_range": time_range, "limit": limit})
        return [
            {"name": t["name"],
             "artist": ", ".join(a["name"] for a in t.get("artists", [])),
             "uri": t["uri"]}
            for t in data.get("items", [])
        ]

    async def get_top_artists(self, time_range: str = "medium_term",
                              limit: int = 20) -> List[Dict]:
        data = await self._get("/me/top/artists",
                               params={"time_range": time_range, "limit": limit})
        return [{"name": a["name"], "uri": a["uri"]} for a in data.get("items", [])]

    async def get_recently_played(self, limit: int = 20) -> List[Dict]:
        data = await self._get("/me/player/recently-played", params={"limit": limit})
        return [
            {
                "name": item["track"]["name"],
                "artist": ", ".join(a["name"] for a in item["track"].get("artists", [])),
                "played_at": item.get("played_at", ""),
                "uri": item["track"]["uri"],
            }
            for item in data.get("items", [])
        ]

    async def get_artist_top_tracks(self, artist_query: str) -> List[Dict]:
        data = await self.search(artist_query, "artist", 1)
        artists = (data.get("artists") or {}).get("items", [])
        if not artists:
            return []
        top = await self._get(f"/artists/{artists[0]['id']}/top-tracks",
                              params={"market": "FR"})
        return [
            {"name": t["name"], "uri": t["uri"],
             "artist": ", ".join(a["name"] for a in t.get("artists", []))}
            for t in top.get("tracks", [])
        ]

    async def build_style_queue(self, artist_query: str,
                                device_hint: Optional[str] = None) -> Dict[str, Any]:
        """Lance une file 'dans le style de X' (top tracks de X + tops utilisateur)."""
        device_id, needs_msg = await self._pick_device(device_hint)
        if needs_msg:
            return {"status": "needs_user", "needs_user": True, "message": needs_msg}

        top = await self.get_artist_top_tracks(artist_query)
        if not top:
            return {"status": "not_found", "message": f"Artiste '{artist_query}' introuvable."}

        uris = [t["uri"] for t in top[:10]]
        try:
            user_tops = await self.get_top_tracks("short_term", 10)
            for t in user_tops:
                if t["uri"] not in uris:
                    uris.append(t["uri"])
        except Exception:
            pass

        await self.transfer_playback(device_id, play=False)
        await asyncio.sleep(0.5)
        await self.play(device_id=device_id, uris=uris[:20])
        await self._save_device(device_id)
        verified = await self._verify(device_id)

        return {
            "status": "done",
            "verified": verified,
            "message": f"File dans le style de '{artist_query}' lancee ({len(uris[:20])} titres).",
        }

    # ── Point d entree unifie (dispatcher) ───────────────────────────────────

    async def control(
        self,
        action: str,
        query: str = "",
        search_type: str = "track",
        device: Optional[str] = None,
        volume: Optional[int] = None,
        volume_delta: Optional[int] = None,
        position_ms: Optional[int] = None,
        state: Optional[str] = None,
        playlist_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Point d entree pour le dispatcher (outil control_spotify)."""

        def _needs_user_no_tokens() -> Dict[str, Any]:
            host = os.environ.get("CLOUDFLARE_HOSTNAME", "jarvis.signalcraftapps.com")
            url = f"https://{host}/api/media/spotify/login"
            return {
                "status": "needs_user",
                "needs_user": True,
                "auth_url": url,
                "message": f"Spotify non connecte. Authentifie-toi ici : {url}",
            }

        try:
            if action == "now_playing":
                return await self.now_playing()

            elif action in ("play", "resume"):
                if query:
                    return await self.play_query(query, search_type, device_hint=device)
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.play(device_id=dev_id)
                verified = await self._verify(dev_id)
                return {"status": "done", "verified": verified, "message": "Lecture reprise."}

            elif action == "pause":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.pause(device_id=dev_id)
                verified = await self._verify(dev_id, is_playing=False)
                return {"status": "done", "verified": verified, "message": "Pause."}

            elif action == "next":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.next_track(device_id=dev_id)
                await asyncio.sleep(1.2)
                np = await self.now_playing()
                return {"status": "done", "verified": True,
                        "message": f"Suivant : {np.get('track_name','')} — {np.get('artist','')}."}

            elif action == "previous":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.previous_track(device_id=dev_id)
                await asyncio.sleep(1.2)
                np = await self.now_playing()
                return {"status": "done", "verified": True,
                        "message": f"Precedent : {np.get('track_name','')} — {np.get('artist','')}."}

            elif action == "seek":
                if position_ms is None:
                    return {"status": "failed", "message": "position_ms manquant."}
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.seek(position_ms, device_id=dev_id)
                return {"status": "done", "verified": True,
                        "message": f"Position : {position_ms // 1000}s."}

            elif action == "volume":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                if volume is not None:
                    target = volume
                elif volume_delta is not None:
                    cur_dev = await self.get_active_device()
                    cur_vol = (cur_dev or {}).get("volume_percent", 50)
                    target = max(0, min(100, cur_vol + volume_delta))
                else:
                    return {"status": "failed", "message": "volume ou volume_delta manquant."}
                await self.set_volume(target, device_id=dev_id)
                return {"status": "done", "verified": True, "message": f"Volume a {target}%."}

            elif action == "shuffle":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                enabled = state.lower() in ("true", "on", "1") if state else True
                await self.set_shuffle(enabled, device_id=dev_id)
                return {"status": "done", "verified": True,
                        "message": f"Aleatoire {'active' if enabled else 'desactive'}."}

            elif action == "repeat":
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                rstate = state or "context"
                await self.set_repeat(rstate, device_id=dev_id)
                return {"status": "done", "verified": True, "message": f"Repetition : {rstate}."}

            elif action == "queue_add":
                if not query:
                    return {"status": "failed", "message": "Titre a ajouter manquant."}
                track = await self.find_best_track(query)
                if not track:
                    return {"status": "not_found", "message": f"'{query}' introuvable."}
                dev_id, msg = await self._pick_device(device)
                if msg:
                    return {"status": "needs_user", "needs_user": True, "message": msg}
                await self.queue_add(track["uri"], device_id=dev_id)
                label = f"{track['name']} — {', '.join(a['name'] for a in track.get('artists', []))}"
                return {"status": "done", "verified": True, "message": f"{label} ajoute a la file."}

            elif action == "get_queue":
                return await self.get_queue()

            elif action == "list_devices":
                devs = await self.get_devices()
                return {"status": "done", "devices": devs,
                        "message": f"{len(devs)} appareil(s) Spotify Connect."}

            elif action == "transfer":
                if not device:
                    return {"status": "failed", "message": "Appareil cible manquant."}
                resolved = await self.resolve_device(device)
                if not resolved:
                    if self._is_pc_hint(device):
                        pc_id = await self._launch_pc_spotify()
                        if pc_id:
                            await self.transfer_playback(pc_id, play=True)
                            verified = await self._verify(pc_id)
                            return {"status": "done", "verified": verified,
                                    "message": "Lecture transferee sur ton PC."}
                    return {"status": "needs_user", "needs_user": True,
                            "message": f"Appareil '{device}' introuvable. Ouvre Spotify dessus."}
                await self.transfer_playback(resolved["id"], play=True)
                await self._save_device(resolved["id"])
                verified = await self._verify(resolved["id"])
                return {"status": "done", "verified": verified,
                        "message": f"Lecture transferee sur {resolved['name']}."}

            elif action == "like":
                return await self.like_current_track()

            elif action == "unlike":
                return await self.unlike_current_track()

            elif action == "add_to_playlist":
                if not playlist_name:
                    return {"status": "failed", "message": "Nom de playlist manquant."}
                return await self.add_current_to_playlist(playlist_name)

            elif action == "create_playlist":
                if not (query or playlist_name):
                    return {"status": "failed", "message": "Nom de playlist manquant."}
                name = query or playlist_name or ""
                result = await self.create_playlist(
                    name, description="Playlist creee par J.A.R.V.I.S."
                )
                return {"status": "done", "verified": True,
                        "message": f"Playlist '{result['name']}' creee.", **result}

            elif action == "search":
                results = await self.search(query, search_type, 5)
                key = search_type + "s"
                items = (results.get(key) or {}).get("items", [])
                return {"status": "done", "results": items[:5], "count": len(items)}

            elif action == "top":
                time_range = state or "medium_term"
                if search_type == "artist":
                    items = await self.get_top_artists(time_range, 10)
                else:
                    items = await self.get_top_tracks(time_range, 10)
                return {"status": "done", "items": items, "time_range": time_range}

            elif action == "recent":
                return {"status": "done", "items": await self.get_recently_played(20)}

            elif action == "follow_artist":
                if not query:
                    return {"status": "failed", "message": "Nom d artiste manquant."}
                data = await self.search(query, "artist", 1)
                items = (data.get("artists") or {}).get("items", [])
                if not items:
                    return {"status": "not_found", "message": f"Artiste '{query}' introuvable."}
                return await self.follow_artist(items[0]["id"])

            elif action == "save_album":
                if not query:
                    return {"status": "failed", "message": "Nom d album manquant."}
                data = await self.search(query, "album", 1)
                items = (data.get("albums") or {}).get("items", [])
                if not items:
                    return {"status": "not_found", "message": f"Album '{query}' introuvable."}
                return await self.save_album(items[0]["id"])

            else:
                return {"status": "failed", "message": f"Action inconnue : {action}"}

        except ValueError as exc:
            err = str(exc)
            if "no_tokens" in err:
                return _needs_user_no_tokens()
            if "forbidden:PREMIUM_REQUIRED" in err:
                return {"status": "failed", "message": "Cette action requiert Spotify Premium."}
            logger.error(f"[Spotify] control({action}) ValueError : {err}")
            console_monitor.log_exception(exc, context=f"SpotifyService.control({action})")
            return {"status": "failed", "message": f"Erreur Spotify : {err}"}
        except Exception as exc:
            logger.error(f"[Spotify] control({action}) Exception : {exc}")
            console_monitor.log_exception(exc, context=f"SpotifyService.control({action})")
            return {"status": "failed", "message": f"Erreur inattendue : {exc}"}


# Singleton
spotify_service = SpotifyService()
