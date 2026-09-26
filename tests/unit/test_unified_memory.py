"""tests/unit/test_unified_memory.py
Tests unitaires pour services.unified_memory.UnifiedMemoryManager.
Valide l'orchestration hybride SQLite + Qdrant, la déduplication des données
de profil, le fallback relationnel en cas d'indisponibilité vectorielle et la
génération du prompt contextuel pour Gemini Live.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.unified_memory import UnifiedMemoryManager


@pytest.fixture
def memory_manager():
    """Instance fraîche de UnifiedMemoryManager."""
    return UnifiedMemoryManager()


@pytest.mark.asyncio
class TestUnifiedMemoryMemorize:
    """Tests de la méthode memorize() : distinction faits généraux vs données profil immuables."""

    async def test_memorize_profile_immutable_by_keyword(self, memory_manager):
        """Une information de profil (ex: 'Pointure 42') ne doit être stockée que dans SQLite."""
        with patch("services.unified_memory.sqlite_memory") as mock_sqlite, \
             patch("services.unified_memory.vector_memory") as mock_vector:

            mock_sqlite.add_memory.return_value = {"id": 101, "fact": "Pointure : 43", "category": "profil_immuable"}
            mock_vector.save_memory = AsyncMock()

            res = await memory_manager.memorize("Ma pointure est 43", category="général")

            # Doit être persisté dans SQLite avec la catégorie profil_immuable
            mock_sqlite.add_memory.assert_called_once_with("Ma pointure est 43", category="profil_immuable")
            assert res["status"] == "success"
            assert res["category"] == "profil_immuable"
            assert "dédupliqué" in res.get("message", "").lower()

            # La synchronisation vectorielle NE DOIT PAS être appelée
            mock_vector.save_memory.assert_not_called()

    async def test_memorize_profile_immutable_by_category(self, memory_manager):
        """Catégorie 'contact' ou 'profil' classée automatiquement en profil immuable."""
        with patch("services.unified_memory.sqlite_memory") as mock_sqlite, \
             patch("services.unified_memory.vector_memory") as mock_vector:

            mock_sqlite.add_memory.return_value = {"id": 102, "fact": "pierre@example.com", "category": "profil_immuable"}
            mock_vector.save_memory = AsyncMock()

            res = await memory_manager.memorize("pierre@example.com", category="contact")

            mock_sqlite.add_memory.assert_called_once_with("pierre@example.com", category="profil_immuable")
            assert res["category"] == "profil_immuable"
            mock_vector.save_memory.assert_not_called()

    async def test_memorize_general_fact_triggers_vector_sync(self, memory_manager):
        """Un fait général standard est stocké dans SQLite et synchronisé dans Qdrant de manière asynchrone."""
        with patch("services.unified_memory.sqlite_memory") as mock_sqlite, \
             patch("services.unified_memory.vector_memory") as mock_vector:

            mock_sqlite.add_memory.return_value = {"id": 200, "fact": "Préfère le café noir sans sucre", "category": "préférence"}
            mock_vector._ready = True
            mock_vector.save_memory = AsyncMock()

            res = await memory_manager.memorize("Préfère le café noir sans sucre", category="préférence", importance=2)

            assert res["status"] == "success"
            assert res["id"] == 200
            assert res["category"] == "préférence"
            mock_sqlite.add_memory.assert_called_once_with("Préfère le café noir sans sucre", category="préférence")

            # Attendre que la tâche de fond asyncio s'exécute
            await asyncio.sleep(0.05)

            mock_vector.save_memory.assert_called_once_with(
                "Préfère le café noir sans sucre",
                category="préférence",
                importance=2,
                metadata={"sqlite_id": 200}
            )

    async def test_async_vector_sync_when_vector_not_ready(self, memory_manager):
        """Si Qdrant n'est pas prêt, la synchro vectorielle s'interrompt sans lever d'erreur."""
        with patch("services.unified_memory.vector_memory") as mock_vector:
            mock_vector._ready = False
            mock_vector.save_memory = AsyncMock()

            # Appel direct à la méthode de synchronisation
            await memory_manager._async_vector_sync("Fait de test", "général", 1, {"sqlite_id": 1})
            mock_vector.save_memory.assert_not_called()

    async def test_async_vector_sync_handles_exception_gracefully(self, memory_manager):
        """Une exception lors de l'appel vectoriel ne propage pas d'erreur fatale."""
        with patch("services.unified_memory.vector_memory") as mock_vector:
            mock_vector._ready = True
            mock_vector.save_memory = AsyncMock(side_effect=Exception("Qdrant connexion timeout"))

            # Ne doit pas lever d'exception
            await memory_manager._async_vector_sync("Fait", "général", 1, {})


@pytest.mark.asyncio
class TestUnifiedMemoryRecall:
    """Tests de la recherche sémantique avec dégradation automatique vers SQLite."""

    async def test_recall_qdrant_success(self, memory_manager):
        """Lorsque Qdrant est disponible et renvoie des souvenirs, ils sont retournés directement."""
        mock_results = [
            {"id": "vec-1", "content": "Adore coder en Python", "category": "préférence", "score": 0.92},
            {"id": "vec-2", "content": "Utilise l'IDE Antigravity", "category": "projet", "score": 0.88},
        ]

        with patch("services.unified_memory.vector_memory") as mock_vector, \
             patch("services.unified_memory.sqlite_memory") as mock_sqlite:

            mock_vector._ready = True
            mock_vector.search_relevant_memories = AsyncMock(return_value=mock_results)

            results = await memory_manager.recall("Python", limit=5)

            assert len(results) == 2
            assert results[0]["content"] == "Adore coder en Python"
            mock_vector.search_relevant_memories.assert_called_once_with("Python", limit=5)
            mock_sqlite.search_memories.assert_not_called()

    async def test_recall_fallback_to_sqlite_when_qdrant_not_ready(self, memory_manager):
        """Si Qdrant n'est pas prêt, bascule automatiquement sur la recherche textuelle SQLite."""
        sqlite_mock_results = [
            {"id": 10, "fact": "Rappelle-toi d'acheter du pain", "category": "tâche", "date": "2026-09-26T10:00:00"}
        ]

        with patch("services.unified_memory.vector_memory") as mock_vector, \
             patch("services.unified_memory.sqlite_memory") as mock_sqlite:

            mock_vector._ready = False
            mock_sqlite.search_memories.return_value = sqlite_mock_results

            results = await memory_manager.recall("pain", limit=3)

            assert len(results) == 1
            assert results[0]["id"] == "10"
            assert results[0]["content"] == "Rappelle-toi d'acheter du pain"
            assert results[0]["category"] == "tâche"
            assert results[0]["score"] is None
            mock_sqlite.search_memories.assert_called_once_with("pain", limit=3)

    async def test_recall_fallback_to_sqlite_when_qdrant_returns_empty(self, memory_manager):
        """Si Qdrant renvoie une liste vide, tentative de secours dans SQLite."""
        sqlite_mock_results = [
            {"id": 11, "fact": "Note de secours", "category": "général", "date": "2026-09-26T10:00:00"}
        ]

        with patch("services.unified_memory.vector_memory") as mock_vector, \
             patch("services.unified_memory.sqlite_memory") as mock_sqlite:

            mock_vector._ready = True
            mock_vector.search_relevant_memories = AsyncMock(return_value=[])
            mock_sqlite.search_memories.return_value = sqlite_mock_results

            results = await memory_manager.recall("recherche", limit=5)

            assert len(results) == 1
            assert results[0]["content"] == "Note de secours"
            mock_sqlite.search_memories.assert_called_once_with("recherche", limit=5)

    async def test_recall_handles_sqlite_exception(self, memory_manager):
        """Si SQLite échoue également, recall retourne une liste vide sans crasher."""
        with patch("services.unified_memory.vector_memory") as mock_vector, \
             patch("services.unified_memory.sqlite_memory") as mock_sqlite:

            mock_vector._ready = False
            mock_sqlite.search_memories.side_effect = Exception("Erreur disque SQLite")

            results = await memory_manager.recall("test")
            assert results == []


@pytest.mark.asyncio
class TestUnifiedMemoryContextPrompt:
    """Tests de construction du prompt contextuel pour la session Gemini Live."""

    async def test_build_live_context_nominal(self, memory_manager):
        """Construction nominale combinant le profil utilisateur et le contexte vectoriel."""
        fake_profile = {
            "first_name": "Pierre",
            "full_name": "Pierre Cassagnettes",
            "email": "pierre@stark.ai",
            "address": "10 Rue des Développeurs",
            "zip_code": "75001",
            "city": "Paris"
        }

        with patch.object(memory_manager, "get_user_profile", return_value=fake_profile), \
             patch("services.unified_memory.vector_memory") as mock_vector:

            mock_vector._ready = True
            mock_vector.build_memory_context_for_session = AsyncMock(
                return_value="SOUVENIRS IMPORTANTS :\n- Projet Jarvis Core en cours"
            )

            prompt = await memory_manager.build_live_context_prompt()

            assert "UTILISATEUR PRINCIPAL : Pierre" in prompt
            assert "Email : pierre@stark.ai" in prompt
            assert "10 Rue des Développeurs 75001 Paris" in prompt
            assert "Projet Jarvis Core en cours" in prompt

    async def test_build_live_context_fallback_sqlite(self, memory_manager):
        """Repli sur SQLite si vector_memory n'est pas initialisé."""
        fake_profile = {
            "first_name": "Pierre",
            "full_name": "Pierre Cassagnettes",
            "email": "pierre@stark.ai",
        }

        with patch.object(memory_manager, "get_user_profile", return_value=fake_profile), \
             patch("services.unified_memory.vector_memory") as mock_vector, \
             patch("services.unified_memory.sqlite_memory") as mock_sqlite:

            mock_vector._ready = False
            mock_sqlite.build_system_memory_context.return_value = "CONTEXTE SQLITE LOCAL"

            prompt = await memory_manager.build_live_context_prompt()

            assert "UTILISATEUR PRINCIPAL : Pierre" in prompt
            assert "CONTEXTE SQLITE LOCAL" in prompt


@pytest.mark.asyncio
class TestVectorMemoryServiceQdrantCompat:
    """Vérifie la compatibilité de VectorMemoryService avec les versions récentes de QdrantClient (query_points)."""

    async def test_search_relevant_memories_with_query_points(self):
        from services.memory import VectorMemoryService
        vms = VectorMemoryService()
        vms._embed_model = MagicMock()
        vms._embed_model.embed.return_value = [[0.1] * 384]

        # Mock QdrantClient avec query_points (qdrant-client >= 1.10)
        mock_qdrant = MagicMock(spec=["query_points"])
        mock_point = MagicMock()
        mock_point.id = "uuid-1234"
        mock_point.payload = {"content": "Bitcoin rareté absolue", "category": "fait", "created_at": "2026-09-26T14:00:00"}
        mock_point.score = 0.95

        mock_resp = MagicMock()
        mock_resp.points = [mock_point]
        mock_qdrant.query_points.return_value = mock_resp
        vms._qdrant = mock_qdrant

        results = await vms.search_relevant_memories("Bitcoin", limit=5)
        assert len(results) == 1
        assert results[0]["content"] == "Bitcoin rareté absolue"
        assert results[0]["score"] == 0.95
        assert results[0]["id"] == "uuid-1234"

    async def test_search_relevant_memories_with_legacy_search(self):
        from services.memory import VectorMemoryService
        vms = VectorMemoryService()
        vms._embed_model = MagicMock()
        vms._embed_model.embed.return_value = [[0.1] * 384]

        # Mock QdrantClient legacy avec search
        mock_qdrant = MagicMock(spec=["search"])
        mock_scored = MagicMock()
        mock_scored.id = "uuid-legacy"
        mock_scored.payload = {"content": "Souvenir legacy", "category": "fait", "created_at": "2026-09-26T14:00:00"}
        mock_scored.score = 0.88
        mock_qdrant.search.return_value = [mock_scored]
        vms._qdrant = mock_qdrant

        results = await vms.search_relevant_memories("Legacy", limit=5)
        assert len(results) == 1
        assert results[0]["content"] == "Souvenir legacy"
        assert results[0]["score"] == 0.88

