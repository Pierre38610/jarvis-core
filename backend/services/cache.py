"""J.A.R.V.I.S. Cache & Real-time State Service - Stark Industries
Architecture : Cache Redis asynchrone (redis.asyncio) avec fallback mémoire local.
Fonctionnalités :
- Cache clé/valeur avec TTL et sérialisation automatique JSON.
- Gestion temps réel de l'état de présence des devices (ex: "pc_status", smartphone, tablettes).
- Système Pub/Sub asynchrone pour la diffusion d'événements et synchronisation inter-modules.
- Dégradation gracieuse : l'application ne plante jamais si Redis est temporairement inaccessible.
"""

import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, Union, Dict, List, AsyncGenerator, Callable

import config

# Import optionnel et sécurisé de redis.asyncio
try:
    import redis.asyncio as aioredis
    from redis.exceptions import RedisError, ConnectionError, TimeoutError
    HAS_REDIS_LIB = True
except ImportError:
    aioredis = None
    RedisError = Exception
    ConnectionError = Exception
    TimeoutError = Exception
    HAS_REDIS_LIB = False


class CacheService:
    """Service de gestion du cache distribué Redis et de la présence des équipements."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        db: Optional[int] = None,
    ):
        self.host = host or getattr(config, "REDIS_HOST", "127.0.0.1")
        self.port = int(port or getattr(config, "REDIS_PORT", 6379))
        self.password = password if password is not None else getattr(config, "REDIS_PASSWORD", "")
        self.db = int(db or getattr(config, "REDIS_DB", 0))

        self._client: Optional[Any] = None
        self._is_connected: bool = False
        self._lock = asyncio.Lock()

        # Fallback mémoire local en mode dégradé (sans Redis)
        # Format: key -> (value, expire_at_timestamp_or_None)
        self._memory_fallback: Dict[str, tuple[Any, Optional[float]]] = {}
        self._last_connect_attempt: float = 0.0
        self._connect_retry_cooldown: float = 15.0  # Cooldown avant de retenter la connexion Redis si indisponible

    @property
    def is_connected(self) -> bool:
        """Indique si la connexion Redis est actuellement active et saine."""
        return self._is_connected and self._client is not None

    async def get_client(self) -> Optional[Any]:
        """Retourne ou instancie le client Redis asynchrone avec pool de connexion."""
        if not HAS_REDIS_LIB:
            return None

        if self._client is not None and self._is_connected:
            return self._client

        # Si un échec de connexion a eu lieu récemment, on bascule directement sur le fallback local
        if time.time() - self._last_connect_attempt < self._connect_retry_cooldown:
            return None

        async with self._lock:
            if self._client is not None and self._is_connected:
                return self._client

            if time.time() - self._last_connect_attempt < self._connect_retry_cooldown:
                return None

            self._last_connect_attempt = time.time()
            try:
                self._client = aioredis.Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password if self.password else None,
                    db=self.db,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    retry_on_timeout=False,
                )
                # Test de communication (ping) rapide avec timeout
                await asyncio.wait_for(self._client.ping(), timeout=0.8)
                self._is_connected = True
                return self._client
            except Exception:
                self._is_connected = False
                self._client = None
                return None

    async def check_connection(self, timeout: float = 2.0) -> bool:
        """Vérifie la disponibilité de Redis de manière non-bloquante avec timeout court.
        Utilisé au démarrage du backend Jarvis.
        """
        if not HAS_REDIS_LIB:
            print("[Cache/Redis] Bibliothèque Python 'redis' non installée. Mode mémoire local actif.")
            self._is_connected = False
            return False

        try:
            client = await asyncio.wait_for(self.get_client(), timeout=timeout)
            if client is not None:
                pong = await asyncio.wait_for(client.ping(), timeout=timeout)
                self._is_connected = bool(pong)
                return self._is_connected
        except (asyncio.TimeoutError, ConnectionError, RedisError, Exception) as e:
            self._is_connected = False
            # Ne pas lever d'erreur pour ne pas bloquer le démarrage de Jarvis
            return False

        self._is_connected = False
        return False

    async def close(self) -> None:
        """Ferme proprement la connexion Redis et libère les sockets."""
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.aclose()
                except Exception:
                    pass
                self._client = None
                self._is_connected = False

    # ─── 1. Cache Clé / Valeur avec TTL ───────────────────────────────────────

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Enregistre une valeur dans le cache avec un TTL optionnel en secondes.
        Sérialise automatiquement les dictionnaires, listes et types structurés en JSON.
        """
        # Sérialisation intelligente
        val_str = self._serialize(value)

        # Tentative Redis
        client = await self.get_client()
        if client and self._is_connected:
            try:
                if ttl and ttl > 0:
                    await client.set(key, val_str, ex=ttl)
                else:
                    await client.set(key, val_str)
                return True
            except Exception as e:
                self._is_connected = False

        # Fallback mémoire locale
        expire_at = (time.time() + ttl) if (ttl and ttl > 0) else None
        self._memory_fallback[key] = (value, expire_at)
        return True

    async def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur du cache. Désérialise automatiquement si c'est du JSON.
        Retourne `default` si la clé est inexistante ou expirée.
        """
        client = await self.get_client()
        if client and self._is_connected:
            try:
                raw = await client.get(key)
                if raw is None:
                    return default
                return self._deserialize(raw)
            except Exception:
                self._is_connected = False

        # Fallback mémoire locale
        if key in self._memory_fallback:
            val, expire_at = self._memory_fallback[key]
            if expire_at is not None and time.time() > expire_at:
                del self._memory_fallback[key]
                return default
            return val

        return default

    async def delete(self, key: str) -> bool:
        """Supprime une clé du cache Redis et du fallback mémoire."""
        success = False
        client = await self.get_client()
        if client and self._is_connected:
            try:
                await client.delete(key)
                success = True
            except Exception:
                self._is_connected = False

        if key in self._memory_fallback:
            del self._memory_fallback[key]
            success = True

        return success

    async def exists(self, key: str) -> bool:
        """Vérifie si une clé existe et n'a pas expiré."""
        client = await self.get_client()
        if client and self._is_connected:
            try:
                return bool(await client.exists(key))
            except Exception:
                self._is_connected = False

        if key in self._memory_fallback:
            _, expire_at = self._memory_fallback[key]
            if expire_at is not None and time.time() > expire_at:
                del self._memory_fallback[key]
                return False
            return True

        return False

    # ─── 2. Gestion de l'état de présence d'un device (ex: "pc_status") ───────

    async def set_device_presence(
        self,
        device_name: str,
        status: Union[str, Dict[str, Any]],
        ttl: int = 300,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Enregistre l'état de présence d'un appareil (ex: 'pc_status', 'smartphone', 'vps').
        - ttl : Durée de validité du heartbeat en secondes (par défaut 300s = 5 min).
        - Notifie automatiquement les écouteurs via le canal Pub/Sub `jarvis:events:presence`.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        presence_data = {
            "device": device_name,
            "status": status,
            "last_seen": now_iso,
            "ttl": ttl,
            "metadata": metadata or {},
        }

        key = f"jarvis:presence:{device_name}"
        ok = await self.set(key, presence_data, ttl=ttl)

        # Diffusion de l'événement en temps réel
        await self.publish("jarvis:events:presence", presence_data)
        return ok

    async def get_device_presence(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Récupère l'état de présence actuel d'un device.
        Retourne None si le heartbeat a expiré ou si le device n'est pas enregistré.
        """
        key = f"jarvis:presence:{device_name}"
        res = await self.get(key, default=None)
        if isinstance(res, dict):
            return res
        return None

    # Alias pratique
    get_device_status = get_device_presence

    async def get_all_devices_presence(self) -> Dict[str, Any]:
        """Retourne la liste et l'état de tous les appareils actuellement actifs."""
        devices = {}
        prefix = "jarvis:presence:"

        client = await self.get_client()
        if client and self._is_connected:
            try:
                cursor = 0
                while True:
                    cursor, keys = await client.scan(cursor=cursor, match=f"{prefix}*", count=100)
                    for k in keys:
                        dev_name = k.replace(prefix, "")
                        dev_data = await self.get(k)
                        if dev_data:
                            devices[dev_name] = dev_data
                    if cursor == 0:
                        break
                return devices
            except Exception:
                self._is_connected = False

        # Fallback mémoire
        now = time.time()
        for k, (val, expire_at) in list(self._memory_fallback.items()):
            if k.startswith(prefix):
                if expire_at is not None and now > expire_at:
                    del self._memory_fallback[k]
                    continue
                dev_name = k.replace(prefix, "")
                devices[dev_name] = val

        return devices

    # ─── 3. Système Pub / Sub basique ─────────────────────────────────────────

    async def publish(self, channel: str, message: Any) -> int:
        """Publie un message sur un canal Redis.
        Retourne le nombre de clients abonnés ayant reçu le message.
        """
        client = await self.get_client()
        if client and self._is_connected:
            try:
                payload = self._serialize(message)
                return await client.publish(channel, payload)
            except Exception:
                self._is_connected = False
        return 0

    async def listen_channel(
        self,
        channel: str
    ) -> AsyncGenerator[Any, None]:
        """Générateur asynchrone pour consommer les messages d'un canal Redis.
        Désérialise automatiquement le contenu JSON reçu.
        """
        client = await self.get_client()
        if not client or not self._is_connected:
            return

        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if msg and msg.get("type") == "message":
                    data = msg.get("data")
                    yield self._deserialize(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

    # ─── Utilitaires internes ─────────────────────────────────────────────────

    @staticmethod
    def _serialize(value: Any) -> str:
        """Sérialise une valeur en chaîne de caractères (JSON si structuré)."""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, default=str, ensure_ascii=False)
        except Exception:
            return str(value)

    @staticmethod
    def _deserialize(raw: Any) -> Any:
        """Désérialise une chaîne de caractères en objet Python si JSON valide."""
        if not isinstance(raw, str):
            return raw
        # Si c'est un format JSON probable
        trimmed = raw.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
            try:
                return json.loads(trimmed)
            except Exception:
                pass
        return raw


# Instance singleton globale pour tout le backend Jarvis
cache_service = CacheService()
