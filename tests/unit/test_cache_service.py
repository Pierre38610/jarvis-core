"""tests/unit/test_cache_service.py
Tests unitaires pour services.cache.CacheService.
Vérifie la sérialisation, le TTL, la gestion de présence et le basculement
automatique vers la mémoire vive (fallback dict) en cas de déconnexion Redis.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.cache import CacheService


class TestCacheSerialization:
    """Vérifie la sérialisation et la désérialisation interne des différents types de données."""

    def test_serialize_deserialize_primitives(self):
        # Chaîne de caractères
        assert CacheService._serialize("hello world") == "hello world"
        assert CacheService._deserialize("hello world") == "hello world"

        # Nombres
        assert CacheService._serialize(100) == "100"
        assert CacheService._serialize(3.1415) == "3.1415"

    def test_serialize_deserialize_complex_structures(self):
        # Dictionnaire imbriqué
        data = {
            "agent": "JARVIS",
            "active": True,
            "version": 2.5,
            "devices": ["desktop", "mobile_hud"],
            "stats": {"requests": 42, "latency_ms": 12.8}
        }
        serialized = CacheService._serialize(data)
        assert isinstance(serialized, str)
        deserialized = CacheService._deserialize(serialized)
        assert deserialized == data

        # Liste de dictionnaires
        items = [{"id": 1, "task": "analyse"}, {"id": 2, "task": "déploiement"}]
        serialized_items = CacheService._serialize(items)
        assert CacheService._deserialize(serialized_items) == items


@pytest.mark.asyncio
class TestCacheServiceFallbackMemory:
    """Vérifie le fonctionnement autonome du cache en mode mémoire vive (Redis déconnecté)."""

    @pytest.fixture
    def memory_cache(self):
        """Crée une instance avec Redis explicitement inaccessible."""
        cache = CacheService(host="127.0.0.1", port=9999, password="invalid")
        cache._is_connected = False
        cache._client = None
        cache.get_client = AsyncMock(return_value=None)
        return cache

    async def test_set_and_get_in_memory(self, memory_cache):
        """Stockage et récupération en mémoire fallback."""
        success = await memory_cache.set("jarvis:test_key", {"status": "operational", "code": 200})
        assert success is True

        # Vérification dans le fallback mémoire direct
        assert "jarvis:test_key" in memory_cache._memory_fallback
        val, expire_at = memory_cache._memory_fallback["jarvis:test_key"]
        assert val == {"status": "operational", "code": 200}
        assert expire_at is None

        # Récupération via get
        retrieved = await memory_cache.get("jarvis:test_key")
        assert retrieved == {"status": "operational", "code": 200}

    async def test_get_non_existent_key_returns_default(self, memory_cache):
        """Clé inexistante renvoie la valeur par défaut spécifiée."""
        res = await memory_cache.get("non_existent_key", default="fallback_val")
        assert res == "fallback_val"

        res_none = await memory_cache.get("unknown_key")
        assert res_none is None

    async def test_exists_and_delete(self, memory_cache):
        """Vérifie exists() et delete() en mémoire."""
        await memory_cache.set("temp_key", "temporary_data")
        assert await memory_cache.exists("temp_key") is True

        deleted = await memory_cache.delete("temp_key")
        assert deleted is True
        assert await memory_cache.exists("temp_key") is False
        assert await memory_cache.get("temp_key") is None

    async def test_ttl_expiration_in_memory(self, memory_cache):
        """Vérifie que les clés avec TTL expirent et sont automatiquement nettoyées."""
        # TTL court de 1 seconde
        await memory_cache.set("ephemeral_token", "secret123", ttl=1)
        assert await memory_cache.exists("ephemeral_token") is True
        assert await memory_cache.get("ephemeral_token") == "secret123"

        # Simuler l'avancée du temps dans le fallback mémoire sans bloquer inutilement
        val, _ = memory_cache._memory_fallback["ephemeral_token"]
        memory_cache._memory_fallback["ephemeral_token"] = (val, time.time() - 5.0)

        # Dès que le temps est dépassé, get et exists doivent constater l'expiration
        assert await memory_cache.exists("ephemeral_token") is False
        assert await memory_cache.get("ephemeral_token") is None
        assert "ephemeral_token" not in memory_cache._memory_fallback

    async def test_device_presence_management(self, memory_cache):
        """Gestion complète de l'état de présence d'un device (ex: 'pc_status')."""
        ok = await memory_cache.set_device_presence(
            device_name="windows_pc_pierre",
            status="online",
            ttl=300,
            metadata={"battery": 100, "ip": "192.168.1.100"}
        )
        assert ok is True

        presence = await memory_cache.get_device_presence("windows_pc_pierre")
        assert presence is not None
        assert presence["device"] == "windows_pc_pierre"
        assert presence["status"] == "online"
        assert presence["metadata"]["battery"] == 100

        all_devices = await memory_cache.get_all_devices_presence()
        assert "windows_pc_pierre" in all_devices
        assert all_devices["windows_pc_pierre"]["status"] == "online"

    async def test_device_presence_expiration(self, memory_cache):
        """Vérifie qu'un heartbeat expiré n'apparaît plus dans get_all_devices_presence."""
        await memory_cache.set_device_presence("tablet_stark", "online", ttl=2)
        
        # Simuler l'expiration
        k = "jarvis:presence:tablet_stark"
        val, _ = memory_cache._memory_fallback[k]
        memory_cache._memory_fallback[k] = (val, time.time() - 10.0)

        all_devices = await memory_cache.get_all_devices_presence()
        assert "tablet_stark" not in all_devices
        assert await memory_cache.get_device_presence("tablet_stark") is None

    async def test_publish_safe_when_disconnected(self, memory_cache):
        """Publish ne lève aucune exception et retourne 0 lorsque Redis est déconnecté."""
        subscribers = await memory_cache.publish("jarvis:events:status", {"event": "ping"})
        assert subscribers == 0

    async def test_listen_channel_safe_when_disconnected(self, memory_cache):
        """L'écoute de canal se termine immédiatement sans blocage si Redis est hors ligne."""
        messages = []
        async for msg in memory_cache.listen_channel("jarvis:events:system"):
            messages.append(msg)
        assert messages == []


@pytest.mark.asyncio
class TestCacheServiceRedisFailover:
    """Vérifie la résilience et le basculement instantané lors des pannes Redis simulées."""

    async def test_failover_on_redis_set_exception(self):
        """Si client.set lève une exception réseau, CacheService bascule sur la mémoire sans planter."""
        cache = CacheService()
        
        # Mock d'un client Redis qui échoue
        mock_client = AsyncMock()
        mock_client.set.side_effect = ConnectionError("Connexion Redis perdue!")
        cache._client = mock_client
        cache._is_connected = True

        with patch.object(cache, "get_client", return_value=mock_client):
            # L'opération doit réussir grâce au fallback
            ok = await cache.set("resilience_key", "val_preserved", ttl=60)
            assert ok is True
            # Le client doit être marqué déconnecté
            assert cache._is_connected is False
            # La valeur doit être présente dans le fallback mémoire
            assert "resilience_key" in cache._memory_fallback

    async def test_failover_on_redis_get_exception(self):
        """Si client.get lève une exception, CacheService lit depuis la mémoire locale."""
        cache = CacheService()
        cache._memory_fallback["cached_item"] = ("local_secret", None)

        mock_client = AsyncMock()
        mock_client.get.side_effect = TimeoutError("Redis ne répond pas")
        cache._client = mock_client
        cache._is_connected = True

        with patch.object(cache, "get_client", return_value=mock_client):
            val = await cache.get("cached_item")
            assert val == "local_secret"
            assert cache._is_connected is False

    async def test_check_connection_never_crashes(self):
        """check_connection retourne False sans lever d'exception si Redis est injoignable."""
        cache = CacheService()
        with patch.object(cache, "get_client", side_effect=Exception("Socket refuse")):
            ready = await cache.check_connection(timeout=0.1)
            assert ready is False
            assert cache.is_connected is False
