"""tests/conftest.py
Fixtures réutilisables et configuration globale des tests pour J.A.R.V.I.S.
Garantit l'absence totale d'appels réseau réels ou de requêtes API payantes.
"""

import os
import sys
import socket
import pytest
from unittest.mock import MagicMock, AsyncMock

# Ajouter la racine du projet dans le PYTHONPATH
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config
import auth
from services.auth_service import auth_service
from services.cache import CacheService


# ─── 1. Garde-fou Anti-Réseau Externe (Règle Absolue) ───────────────────────────

@pytest.fixture(autouse=True)
def guard_no_external_network(monkeypatch):
    """Interdit toute tentative de connexion réseau externe non-locale.
    Seules les connexions sur localhost (127.0.0.1 / ::1 / 0.0.0.0) sont autorisées.
    """
    orig_connect = socket.socket.connect

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, (tuple, list)) else address
        if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0", "testserver"):
            raise RuntimeError(
                f"[GUARD_VIOLATION] Appel réseau externe interdit vers {address} détecté dans les tests unitaires !"
            )
        return orig_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture(autouse=True)
def mock_global_cache_service():
    """Désactive toute tentative de connexion réseau pour le singleton global cache_service."""
    from services.cache import cache_service
    cache_service._is_connected = False
    cache_service._client = None
    orig_get_client = cache_service.get_client
    cache_service.get_client = AsyncMock(return_value=None)
    yield cache_service
    cache_service.get_client = orig_get_client


# ─── 2. Fixture Gestion des Clés d'API ──────────────────────────────────────────

@pytest.fixture
def fake_api_keys(monkeypatch):
    """Fournit des clés d'API simulées et restaure l'état d'origine après le test."""
    orig_free = getattr(config, "GEMINI_API_KEY_FREE", "")
    orig_paid = getattr(config, "GEMINI_API_KEY_PAID", "")
    orig_has_paid = getattr(config, "HAS_PAID_API_KEY", False)

    fake_free = "fake_gemini_free_key_for_tests_12345"
    fake_paid = "fake_gemini_paid_key_for_tests_67890"

    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", fake_free)
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", fake_paid)
    monkeypatch.setattr(config, "HAS_PAID_API_KEY", True)

    import google_antigravity
    monkeypatch.setattr(google_antigravity, "GEMINI_API_KEY_FREE", fake_free)
    monkeypatch.setattr(google_antigravity, "GEMINI_API_KEY_PAID", fake_paid)

    import services.reasoning_service as rs
    monkeypatch.setattr(rs, "GEMINI_API_KEY_FREE", fake_free)
    monkeypatch.setattr(rs, "GEMINI_API_KEY_PAID", fake_paid)

    yield {
        "free": fake_free,
        "paid": fake_paid,
    }


@pytest.fixture
def paid_key_gate():
    """Permet de contrôler le verrou physique paid_key_authorized avec restauration garantie."""
    orig_state = config.is_paid_key_authorized()

    class GateController:
        def lock(self):
            config.set_paid_key_authorized(False)

        def unlock(self):
            config.set_paid_key_authorized(True)

        @property
        def is_unlocked(self):
            return config.is_paid_key_authorized()

    controller = GateController()
    controller.lock()  # Verrouillé par défaut pour la sécurité financière
    yield controller
    config.set_paid_key_authorized(orig_state)


# ─── 3. Fixtures Authentification & JWT ────────────────────────────────────────

@pytest.fixture
def test_jwt_token():
    """Génère un token JWT valide signé par AuthService pour les tests."""
    token = auth_service.generate_token(
        device_id="test-qa-device-id",
        device_name="QA Unit Test Device",
        role="admin",
        custom_claims={"qa": True}
    )
    return token


@pytest.fixture
def test_expired_jwt_token():
    """Génère un token JWT expiré pour valider le rejet."""
    token = auth_service.generate_token(
        device_id="expired-qa-device",
        device_name="Expired Device",
        role="admin",
        expiry_days=-1  # Émis dans le passé
    )
    return token


# ─── 4. Fixture Client FastAPI (TestClient) ───────────────────────────────────

@pytest.fixture
def test_client():
    """Client FastAPI TestClient non authentifié."""
    from starlette.testclient import TestClient
    from App import app
    return TestClient(app)


@pytest.fixture
def authenticated_client(test_jwt_token):
    """Client FastAPI TestClient authentifié avec token de device valide."""
    from starlette.testclient import TestClient
    from App import app
    client = TestClient(app, cookies={"jarvis_device_token": test_jwt_token})
    return client


# ─── 5. Fixture Mock Gemini Live ──────────────────────────────────────────────

@pytest.fixture
def mock_gemini_live():
    """Simulateur d'événements et de session Gemini Live."""
    class MockGeminiLiveSession:
        def __init__(self):
            self.sent_texts = []
            self.sent_audios = []
            self.is_connected = True

        async def send(self, data, end_of_turn=False):
            self.sent_texts.append({"data": data, "end_of_turn": end_of_turn})

        async def send_audio_chunk(self, pcm_bytes):
            self.sent_audios.append(pcm_bytes)

        async def receive(self):
            # Événement simulé de réponse textuelle/audio
            yield {
                "serverContent": {
                    "modelTurn": {
                        "parts": [
                            {"text": "Bonjour Pierre, comment puis-je vous aider aujourd'hui ?"}
                        ]
                    }
                }
            }

        async def close(self):
            self.is_connected = False

    return MockGeminiLiveSession()


# ─── 6. Fixture CacheService Isolé ────────────────────────────────────────────

@pytest.fixture
def isolated_cache_service():
    """Instance de CacheService isolée en mémoire sans connexion Redis réelle."""
    service = CacheService(host="127.0.0.1", port=9999, password="test")
    # Forcer la non-connexion Redis
    service._is_connected = False
    service._client = None
    return service
