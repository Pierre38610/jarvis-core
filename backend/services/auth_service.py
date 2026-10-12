"""services/auth_service.py
Service d'authentification cryptographique de J.A.R.V.I.S. - Stark Industries.

Spécifications d'ingénierie de sécurité :
1. Tokens JWT signés (HMAC-SHA256 / HS256) contenant :
   - device_id, device_name, role, issued_at, expires_at (et claims standard jti, iat, exp).
2. Clé secrète cryptographique forte `JWT_SECRET_KEY` configurée dans `.env`,
   avec génération automatique au premier démarrage si absente.
3. Révocation rapide & Blacklist via Redis (`jarvis:revoked_tokens:{token_id}` et `{device_id}`)
   avec repli sécurisé sur un set local en mémoire si Redis est hors service.
4. Rétrocompatibilité & Transition fluide :
   - Migration transparente des anciens tokens en clair issus de `authorized_devices.json`
     vers des JWT signés, avec suppression immédiate de l'ancien token en clair.
5. Gestion des QR Tickets de pairage à usage unique avec TTL court (5 minutes / 300 s)
   gérés dans Redis et en mémoire locale de secours.
"""

import os
import sys
import json
import time
import secrets
import re
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, Set, Union

import jwt
from jwt.exceptions import PyJWTError, ExpiredSignatureError, InvalidTokenError

import config
from services.cache import cache_service


class AuthService:
    """Service d'authentification unifié et de sécurité pour J.A.R.V.I.S."""

    def __init__(self):
        # Initialisation de la clé secrète (lecture .env ou auto-génération)
        self.secret_key = self._get_or_create_jwt_secret()

        # Durée de validité par défaut des tokens JWT (90 jours)
        self.token_expiry_days = int(getattr(config, "JWT_EXPIRATION_DAYS", 90))

        # TTL des tickets de pairage QR Code (5 minutes = 300 s)
        self.qr_ticket_ttl = 300

        # Set local en mémoire pour le fallback de révocation si Redis est indisponible
        self._revoked_tokens_memory: Set[str] = set()

        # Cache local mémoire de secours pour les QR tickets (ticket -> (data, expire_at))
        self._qr_tickets_memory: Dict[str, Tuple[Dict[str, Any], float]] = {}

        # Cache de transition de migration (old_token -> (new_jwt, expire_at))
        # Permet d'éviter les race conditions si un client envoie plusieurs requêtes simultanées
        self._migrated_tokens_cache: Dict[str, Tuple[str, float]] = {}

        # Verrou asynchrone
        self._lock = asyncio.Lock()

    # ─── 1. Gestion de la clé secrète JWT_SECRET_KEY ──────────────────────────

    def _get_or_create_jwt_secret(self) -> str:
        """Récupère JWT_SECRET_KEY depuis les variables d'environnement ou .env.
        Si absente, génère une clé cryptographique forte (64 octets urlsafe)
        et la persiste automatiquement dans .env.
        """
        # 1. Vérification os.environ et getattr config
        secret = os.environ.get("JWT_SECRET_KEY", "").strip()
        if not secret:
            secret = getattr(config, "JWT_SECRET_KEY", "").strip()

        # 2. Vérification directe dans le fichier .env
        env_path = os.path.join(config.BASE_DIR, ".env")
        if not secret and os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("JWT_SECRET_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                secret = val
                                break
            except Exception as e:
                print(f"[AuthService] Erreur lecture .env pour JWT_SECRET_KEY: {e}")

        # 3. Si trouvée, propagation globale
        if secret:
            os.environ["JWT_SECRET_KEY"] = secret
            setattr(config, "JWT_SECRET_KEY", secret)
            return secret

        # 4. Génération automatique d'une clé sécurisée (64 octets urlsafe = 86 caractères)
        new_secret = secrets.token_urlsafe(64)
        os.environ["JWT_SECRET_KEY"] = new_secret
        setattr(config, "JWT_SECRET_KEY", new_secret)

        # 5. Persistance dans le fichier .env
        try:
            content = ""
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()

            if "JWT_SECRET_KEY=" in content:
                content = re.sub(r"JWT_SECRET_KEY=.*", f"JWT_SECRET_KEY={new_secret}", content)
            else:
                if content and not content.endswith("\n"):
                    content += "\n"
                content += (
                    "\n# Clé secrète cryptographique pour signature JWT (J.A.R.V.I.S. Auth Service)\n"
                    f"JWT_SECRET_KEY={new_secret}\n"
                )

            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("[AuthService] Clé cryptographique forte JWT_SECRET_KEY générée et persistée dans .env.")
        except Exception as e:
            print(f"[AuthService] Avertissement: Impossible d'écrire JWT_SECRET_KEY dans .env: {e}")

        return new_secret

    # ─── 2. Génération de tokens JWT ──────────────────────────────────────────

    def generate_token(
        self,
        device_id: str,
        device_name: str = "Authorized Device",
        role: str = "admin",
        custom_claims: Optional[Dict[str, Any]] = None,
        expiry_days: Optional[int] = None,
    ) -> str:
        """Génère un token JWT signé en HS256 contenant :
        - device_id
        - device_name
        - role
        - issued_at
        - expires_at
        - standard claims: jti, iat, exp
        """
        now = datetime.now(timezone.utc)
        days = expiry_days if expiry_days is not None else self.token_expiry_days
        expires = now + timedelta(days=days)

        issued_at_ts = int(now.timestamp())
        expires_at_ts = int(expires.timestamp())
        token_id = secrets.token_hex(16)

        payload: Dict[str, Any] = {
            "device_id": device_id,
            "device_name": device_name,
            "role": role,
            "issued_at": issued_at_ts,
            "expires_at": expires_at_ts,
            "iat": issued_at_ts,
            "exp": expires_at_ts,
            "jti": token_id,
        }

        if custom_claims:
            for k, v in custom_claims.items():
                if k not in payload:
                    payload[k] = v

        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    # ─── 3. Mécanisme de Révocation / Blacklist (Redis + Fallback Mémoire) ────

    async def revoke_token(self, token_id: str, ttl: Optional[int] = None) -> bool:
        """Révoque un token JWT par son identifiant unique `jti` ou `token_id`.
        Écrit dans Redis sous `jarvis:revoked_tokens:{token_id}` et met à jour
        le fallback mémoire local.
        """
        self._revoked_tokens_memory.add(token_id)
        redis_ttl = ttl or (self.token_expiry_days * 86400)
        key = f"jarvis:revoked_tokens:{token_id}"
        data = {
            "revoked_at": int(time.time()),
            "token_id": token_id,
        }
        try:
            return await cache_service.set(key, data, ttl=redis_ttl)
        except Exception:
            # Fallback local actif
            return True

    def revoke_token_sync(self, token_id: str) -> bool:
        """Version synchrone de révocation (met à jour le set mémoire)."""
        self._revoked_tokens_memory.add(token_id)
        key = f"jarvis:revoked_tokens:{token_id}"
        # Mise à jour du fallback mémoire de cache_service si présent
        cache_service._memory_fallback[key] = ({"revoked_at": int(time.time()), "token_id": token_id}, None)
        return True

    async def revoke_device(self, device_id: str, ttl: Optional[int] = None) -> bool:
        """Révoque tous les accès associés à un `device_id` spécifique."""
        self._revoked_tokens_memory.add(device_id)
        redis_ttl = ttl or (self.token_expiry_days * 86400)
        key = f"jarvis:revoked_tokens:{device_id}"
        data = {
            "revoked_at": int(time.time()),
            "device_id": device_id,
        }
        try:
            return await cache_service.set(key, data, ttl=redis_ttl)
        except Exception:
            return True

    def revoke_device_sync(self, device_id: str) -> bool:
        """Version synchrone de révocation d'un device."""
        self._revoked_tokens_memory.add(device_id)
        key = f"jarvis:revoked_tokens:{device_id}"
        cache_service._memory_fallback[key] = ({"revoked_at": int(time.time()), "device_id": device_id}, None)
        return True

    def _is_device_revoked_config_or_db(self, device_id: Optional[str]) -> bool:
        """Vérifie si le device_id est révoqué dans config.REVOKED_DEVICE_IDS ou dans la base SQLite."""
        if not device_id:
            return False
        # 1. Vérification dans la configuration (REVOKED_DEVICE_IDS)
        revoked_config = getattr(config, "REVOKED_DEVICE_IDS", set())
        if device_id in revoked_config:
            return True
        # 2. Vérification dans la base de données SQLite locale (table revoked_devices)
        db_path = getattr(config, "DB_PATH", "")
        if db_path and os.path.exists(db_path):
            try:
                import sqlite3
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS revoked_devices ("
                        "device_id TEXT PRIMARY KEY, "
                        "revoked_at TEXT NOT NULL, "
                        "reason TEXT DEFAULT ''"
                        ")"
                    )
                    cursor.execute("SELECT 1 FROM revoked_devices WHERE device_id = ?", (device_id,))
                    if cursor.fetchone():
                        return True
            except Exception:
                pass
        return False

    def revoke_device_in_db(self, device_id: str, reason: str = "") -> bool:
        """Enregistre un device_id révoqué dans la base SQLite locale et le cache mémoire."""
        self._revoked_tokens_memory.add(device_id)
        db_path = getattr(config, "DB_PATH", "")
        if db_path:
            try:
                import sqlite3
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS revoked_devices ("
                        "device_id TEXT PRIMARY KEY, "
                        "revoked_at TEXT NOT NULL, "
                        "reason TEXT DEFAULT ''"
                        ")"
                    )
                    now_str = datetime.now(timezone.utc).isoformat()
                    cursor.execute(
                        "INSERT OR REPLACE INTO revoked_devices (device_id, revoked_at, reason) VALUES (?, ?, ?)",
                        (device_id, now_str, reason)
                    )
                    conn.commit()
                    return True
            except Exception as e:
                print(f"[AuthService] Erreur révocation SQLite device {device_id}: {e}")
        return False

    async def is_token_revoked(self, token_id: str, device_id: Optional[str] = None) -> bool:
        """Vérifie si le token ou le device est dans la blacklist Redis, mémoire, config ou BDD."""
        # 0. Vérification config / SQLite
        if self._is_device_revoked_config_or_db(device_id):
            return True

        # 1. Vérification instantanée dans le set local mémoire
        if token_id in self._revoked_tokens_memory:
            return True
        if device_id and device_id in self._revoked_tokens_memory:
            return True

        # 2. Vérification dans le fallback mémoire de cache_service
        if f"jarvis:revoked_tokens:{token_id}" in cache_service._memory_fallback:
            return True
        if device_id and f"jarvis:revoked_tokens:{device_id}" in cache_service._memory_fallback:
            return True

        # 3. Vérification dans Redis
        try:
            if await cache_service.exists(f"jarvis:revoked_tokens:{token_id}"):
                return True
            if device_id and await cache_service.exists(f"jarvis:revoked_tokens:{device_id}"):
                return True
        except Exception:
            # En cas de coupure temporaire de Redis, on s'appuie sur le fallback mémoire
            pass

        return False

    def is_token_revoked_sync(self, token_id: str, device_id: Optional[str] = None) -> bool:
        """Vérification synchrone de révocation via config, BDD SQLite, set mémoire et cache."""
        if self._is_device_revoked_config_or_db(device_id):
            return True
        if token_id in self._revoked_tokens_memory:
            return True
        if device_id and device_id in self._revoked_tokens_memory:
            return True
        if f"jarvis:revoked_tokens:{token_id}" in cache_service._memory_fallback:
            return True
        if device_id and f"jarvis:revoked_tokens:{device_id}" in cache_service._memory_fallback:
            return True
        return False

    # ─── 4. Rétrocompatibilité & Transition fluide (Migration transparente) ────

    def load_legacy_authorized_devices(self) -> Dict[str, Any]:
        """Charge les terminaux autorisés de l'ancien fichier JSON plat."""
        if os.path.exists(config.AUTH_FILE):
            try:
                with open(config.AUTH_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("tokens", {})
            except Exception as e:
                print(f"[AuthService] Erreur lecture authorized_devices.json: {e}")
                return {}
        return {}

    def save_legacy_authorized_devices(self, tokens: Dict[str, Any]):
        """Écrit les tokens restants dans authorized_devices.json."""
        try:
            with open(config.AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump({"tokens": tokens}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[AuthService] Erreur écriture authorized_devices.json: {e}")

    def migrate_legacy_token(self, old_token: str) -> Optional[Tuple[Dict[str, Any], str]]:
        """Migration transparente :
        Si un ancien token issu de authorized_devices.json est présenté,
        le valide une dernière fois, émet un nouveau token JWT en réponse,
        et supprime l'ancien identifiant en clair du fichier JSON.
        """
        now_ts = time.time()

        # 1. Vérification dans le cache de migration récente (pour requêtes concurrentes)
        if old_token in self._migrated_tokens_cache:
            new_jwt, exp = self._migrated_tokens_cache[old_token]
            if now_ts < exp:
                try:
                    payload = jwt.decode(new_jwt, self.secret_key, algorithms=["HS256"])
                    payload["_migrated"] = True
                    payload["_new_token"] = new_jwt
                    return payload, new_jwt
                except Exception:
                    pass

        # 2. Lecture de authorized_devices.json
        legacy_tokens = self.load_legacy_authorized_devices()
        if old_token not in legacy_tokens:
            return None

        # 3. Récupération des informations existantes de l'appareil
        device_info = legacy_tokens[old_token] or {}
        device_id = secrets.token_hex(16)
        device_name = (
            device_info.get("name")
            or device_info.get("device_name")
            or ("Mobile HUD" if "Mobile" in device_info.get("user_agent", "") else "Appareil Pierre (Migré)")
        )

        # 4. Émission du nouveau token JWT
        new_jwt = self.generate_token(
            device_id=device_id,
            device_name=device_name,
            role="admin",
            custom_claims={
                "client_ip": device_info.get("client_ip", "unknown"),
                "user_agent": device_info.get("user_agent", "unknown"),
                "migrated_from_legacy": True,
                "legacy_created_at": device_info.get("created_at", ""),
            },
        )

        # 5. Suppression immédiate de l'ancien token en clair
        del legacy_tokens[old_token]
        self.save_legacy_authorized_devices(legacy_tokens)

        # 6. Mise en cache de la migration pour une fenêtre de 10 minutes
        self._migrated_tokens_cache[old_token] = (new_jwt, now_ts + 600)

        print(
            f"[AuthService] [*] Migration transparente reussie : Ancien token '{old_token[:8]}...' "
            f"converti en JWT pour l'appareil '{device_name}'. Token en clair supprime de authorized_devices.json."
        )

        payload = jwt.decode(new_jwt, self.secret_key, algorithms=["HS256"])
        payload["_migrated"] = True
        payload["_new_token"] = new_jwt
        return payload, new_jwt

    # ─── 5. Vérification de Token (verify_token) ───────────────────────────────

    async def verify_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Vérifie un token (JWT ou token historique à migrer).
        1. Mot de passe maître (compatibilité agent local PC Windows).
        2. Décodage JWT HS256 + vérification d'expiration.
        3. Vérification de la blacklist Redis / mémoire.
        4. Si non-JWT : tentative de migration transparente depuis authorized_devices.json.
        Retourne le payload décodé (avec potentiellement `_migrated` et `_new_token`) ou None.
        """
        if not token:
            return None

        # 1. Vérification mot de passe maître direct (Agent local PC Windows)
        if token == config.ACCESS_PASSWORD:
            now_ts = int(time.time())
            return {
                "device_id": "master-local-agent",
                "device_name": "PC Windows Local Agent",
                "role": "admin",
                "issued_at": now_ts,
                "expires_at": now_ts + 315360000,
                "iat": now_ts,
                "exp": now_ts + 315360000,
                "jti": "master_pwd_token",
            }

        # 2. Décodage JWT
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            token_id = payload.get("jti") or payload.get("token_id", "")
            device_id = payload.get("device_id", "")

            # 3. Vérification Blacklist
            if await self.is_token_revoked(token_id, device_id):
                return None

            return payload

        except (ExpiredSignatureError, InvalidTokenError, PyJWTError, Exception):
            # Le token n'est pas un JWT valide ou a expiré : tentative de migration transparente
            migration_result = self.migrate_legacy_token(token)
            if migration_result:
                payload, _ = migration_result
                return payload

        return None

    def verify_token_sync(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Version synchrone de `verify_token` avec vérification mémoire/fallback."""
        if not token:
            return None

        if token == config.ACCESS_PASSWORD:
            now_ts = int(time.time())
            return {
                "device_id": "master-local-agent",
                "device_name": "PC Windows Local Agent",
                "role": "admin",
                "issued_at": now_ts,
                "expires_at": now_ts + 315360000,
                "iat": now_ts,
                "exp": now_ts + 315360000,
                "jti": "master_pwd_token",
            }

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            token_id = payload.get("jti") or payload.get("token_id", "")
            device_id = payload.get("device_id", "")

            if self.is_token_revoked_sync(token_id, device_id):
                return None

            return payload

        except (ExpiredSignatureError, InvalidTokenError, PyJWTError, Exception):
            migration_result = self.migrate_legacy_token(token)
            if migration_result:
                payload, _ = migration_result
                return payload

        return None

    async def is_device_authorized(self, token: Optional[str]) -> bool:
        """Helper booléen asynchrone."""
        res = await self.verify_token(token)
        return res is not None

    def is_device_authorized_sync(self, token: Optional[str]) -> bool:
        """Helper booléen synchrone (utilisé par les routeurs existants)."""
        res = self.verify_token_sync(token)
        return res is not None

    # ─── 6. Authentification par Mot de Passe Maître ──────────────────────────

    def verify_and_generate_token(
        self,
        password: str,
        client_ip: str = "unknown",
        user_agent: str = "unknown",
        device_name: str = "Authorized Device",
    ) -> Optional[str]:
        """Vérifie le mot de passe maître et génère un jeton JWT signé."""
        if password == config.ACCESS_PASSWORD:
            device_id = secrets.token_hex(16)
            name = device_name
            if "Mobile" in user_agent:
                name = "Mobile HUD (Pierre)"
            elif "Windows" in user_agent:
                name = "PC Windows HUD (Pierre)"

            token = self.generate_token(
                device_id=device_id,
                device_name=name,
                role="admin",
                custom_claims={
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "registered_via": "password",
                },
            )
            return token
        return None

    # ─── 7. Maintien du QR Code (Tickets à usage unique avec TTL Redis) ───────

    async def create_qr_ticket(self, ttl: int = 300, client_ip: str = "unknown") -> str:
        """Génère un ticket unique de pairage QR Code avec un TTL court (5 minutes)
        géré dans Redis et dans le fallback mémoire.
        """
        ticket = secrets.token_urlsafe(32)
        now_ts = time.time()
        expire_at = now_ts + ttl

        ticket_data = {
            "ticket": ticket,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "expires_at": expire_at,
        }

        # 1. Enregistrement mémoire local
        self._qr_tickets_memory[ticket] = (ticket_data, expire_at)

        # 2. Enregistrement Redis
        key = f"jarvis:qr_ticket:{ticket}"
        try:
            await cache_service.set(key, ticket_data, ttl=ttl)
        except Exception:
            pass

        return ticket

    def create_qr_ticket_sync(self, ttl: int = 300, client_ip: str = "unknown") -> str:
        """Version synchrone pour les appelants comme `tunnel_launcher.py`."""
        ticket = secrets.token_urlsafe(32)
        now_ts = time.time()
        expire_at = now_ts + ttl

        ticket_data = {
            "ticket": ticket,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "expires_at": expire_at,
        }

        self._qr_tickets_memory[ticket] = (ticket_data, expire_at)
        key = f"jarvis:qr_ticket:{ticket}"
        cache_service._memory_fallback[key] = (ticket_data, expire_at)
        return ticket

    async def redeem_qr_ticket(
        self,
        ticket: str,
        client_ip: str = "unknown",
        user_agent: str = "unknown",
        device_name: str = "Mobile HUD (QR)",
    ) -> Optional[str]:
        """Valide et consomme un ticket QR Code à usage unique (TTL 5 minutes).
        Supprime le ticket immédiatement de Redis et de la mémoire pour empêcher
        toute réutilisation, puis émet un JWT signé pour l'appareil.
        """
        if not ticket:
            return None

        key = f"jarvis:qr_ticket:{ticket}"
        ticket_found = False

        # 1. Recherche dans Redis
        try:
            data = await cache_service.get(key)
            if data:
                ticket_found = True
                await cache_service.delete(key)
        except Exception:
            pass

        # 2. Recherche dans le fallback mémoire si non trouvé ou si Redis est hors-ligne
        now_ts = time.time()
        if not ticket_found and ticket in self._qr_tickets_memory:
            data, exp = self._qr_tickets_memory[ticket]
            if now_ts <= exp:
                ticket_found = True
            del self._qr_tickets_memory[ticket]

        if ticket in self._qr_tickets_memory:
            del self._qr_tickets_memory[ticket]

        # 3. Si le ticket est valide et non expiré : émission d'un token JWT signé
        if ticket_found:
            device_id = secrets.token_hex(16)
            name = device_name
            if "Mobile" in user_agent:
                name = "Smartphone Pierre (QR Code)"
            elif "Windows" in user_agent:
                name = "PC Windows (QR Code)"

            token = self.generate_token(
                device_id=device_id,
                device_name=name,
                role="admin",
                custom_claims={
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "registered_via": "qr_code",
                },
            )
            print(f"[AuthService] [*] Ticket QR valide et consomme avec succes. Emission JWT pour '{name}'.")
            return token

        return None

    def redeem_qr_ticket_sync(
        self,
        ticket: str,
        client_ip: str = "unknown",
        user_agent: str = "unknown",
        device_name: str = "Mobile HUD (QR)",
    ) -> Optional[str]:
        """Version synchrone de la consommation du ticket QR."""
        if not ticket:
            return None

        now_ts = time.time()
        ticket_found = False

        key = f"jarvis:qr_ticket:{ticket}"
        if key in cache_service._memory_fallback:
            val, exp = cache_service._memory_fallback[key]
            if exp is None or now_ts <= exp:
                ticket_found = True
            del cache_service._memory_fallback[key]

        if ticket in self._qr_tickets_memory:
            data, exp = self._qr_tickets_memory[ticket]
            if now_ts <= exp:
                ticket_found = True
            del self._qr_tickets_memory[ticket]

        if ticket_found:
            device_id = secrets.token_hex(16)
            token = self.generate_token(
                device_id=device_id,
                device_name=device_name,
                role="admin",
                custom_claims={
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "registered_via": "qr_code",
                },
            )
            return token

        return None


# Instance singleton globale pour J.A.R.V.I.S.
auth_service = AuthService()
