"""Test unitaire pour services.cache.CacheService (sans appel API externe).
Vérifie le bon fonctionnement du cache (mémoire fallback et interface Redis),
la gestion du TTL, la présence des devices et le Pub/Sub.
"""

import asyncio
import time
import unittest
from services.cache import CacheService, cache_service


class TestCacheService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Utiliser une instance dédiée pour isoler les tests
        self.cache = CacheService(host="127.0.0.1", port=6379, password="test")

    async def asyncTearDown(self):
        await self.cache.close()

    async def test_set_and_get_basic(self):
        """Vérifie le stockage et la restitution de chaînes et de nombres."""
        await self.cache.set("test:greeting", "hello jarvis")
        val = await self.cache.get("test:greeting")
        self.assertEqual(val, "hello jarvis")

        await self.cache.set("test:count", 42)
        count = await self.cache.get("test:count")
        self.assertEqual(count, 42)

    async def test_set_and_get_dict(self):
        """Vérifie la sérialisation/désérialisation automatique des dictionnaires."""
        payload = {"agent": "Jarvis", "version": 2.0, "active": True}
        await self.cache.set("test:dict", payload)
        retrieved = await self.cache.get("test:dict")
        self.assertEqual(retrieved, payload)

    async def test_ttl_expiration(self):
        """Vérifie qu'une clé avec TTL expire après la durée spécifiée."""
        await self.cache.set("test:ephemeral", "short-lived", ttl=1)
        self.assertTrue(await self.cache.exists("test:ephemeral"))
        self.assertEqual(await self.cache.get("test:ephemeral"), "short-lived")

        # Attendre l'expiration
        await asyncio.sleep(1.1)
        self.assertFalse(await self.cache.exists("test:ephemeral"))
        self.assertIsNone(await self.cache.get("test:ephemeral"))

    async def test_delete_and_exists(self):
        """Vérifie la suppression et la vérification d'existence."""
        await self.cache.set("test:to_delete", "goodbye")
        self.assertTrue(await self.cache.exists("test:to_delete"))
        
        deleted = await self.cache.delete("test:to_delete")
        self.assertTrue(deleted)
        self.assertFalse(await self.cache.exists("test:to_delete"))
        self.assertIsNone(await self.cache.get("test:to_delete"))

    async def test_device_presence(self):
        """Vérifie la gestion de l'état de présence d'un device (ex: pc_status)."""
        ok = await self.cache.set_device_presence(
            device_name="pc_pierre",
            status="online",
            ttl=300,
            metadata={"battery": 95, "ip": "192.168.1.50"}
        )
        self.assertTrue(ok)

        presence = await self.cache.get_device_presence("pc_pierre")
        self.assertIsNotNone(presence)
        self.assertEqual(presence["device"], "pc_pierre")
        self.assertEqual(presence["status"], "online")
        self.assertEqual(presence["metadata"]["battery"], 95)

        all_devices = await self.cache.get_all_devices_presence()
        self.assertIn("pc_pierre", all_devices)

    async def test_check_connection_non_blocking(self):
        """Vérifie que check_connection ne lève jamais d'exception fatale."""
        is_ready = await self.cache.check_connection(timeout=0.5)
        # Peut être True si Redis local tourne, ou False sinon, mais ne doit pas crasher
        self.assertIsInstance(is_ready, bool)

    async def test_publish_safe(self):
        """Vérifie que publish ne crashe pas en mode local."""
        subscribers = await self.cache.publish("jarvis:test:channel", {"msg": "hello"})
        self.assertIsInstance(subscribers, int)


if __name__ == "__main__":
    unittest.main()
