"""tests/unit/test_paid_key_gate.py
Tests unitaires exhaustifs pour le verrou physique économique (paid_key_authorized).
Prouve formellement qu'aucune requête payante ne peut être initiée lorsque
l'interrupteur utilisateur est désactivé.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from google_antigravity import resolve_antigravity_model, AntigravityAgent
from services.reasoning_service import run_deep_reasoning
from services.supervision_service import supervision_service


@pytest.fixture(autouse=True)
def preserve_paid_key_state():
    """Garantit la restauration de l'état original de paid_key_authorized après chaque test."""
    orig = config.is_paid_key_authorized()
    yield
    config.set_paid_key_authorized(orig)


class TestConfigPaidKeyGate:
    """Vérifie l'impossibilité physique d'obtenir la clé payante au niveau du module config."""

    def test_gate_locked_returns_empty_key(self, fake_api_keys):
        """Lorsque le verrou est désactivé, get_effective_paid_key() renvoie une chaîne vide."""
        config.set_paid_key_authorized(False)
        assert config.is_paid_key_authorized() is False
        assert config.get_effective_paid_key() == ""
        assert config.is_paid_key_active() is False

    def test_gate_unlocked_returns_paid_key_when_configured(self, fake_api_keys):
        """Lorsque le verrou est activé, la clé payante devient effective."""
        config.set_paid_key_authorized(True)
        assert config.is_paid_key_authorized() is True
        assert config.get_effective_paid_key() == fake_api_keys["paid"]
        assert config.is_paid_key_active() is True


class TestAntigravityPaidKeyGate:
    """Vérifie que l'agent Antigravity refuse catégoriquement toute clé payante si le verrou est fermé."""

    def test_model_resolution_forces_free_key_when_locked(self, fake_api_keys):
        """La résolution de modèle pour un modèle lourd bascule sur la clé gratuite si non autorisé."""
        config.set_paid_key_authorized(False)
        target, label = resolve_antigravity_model("gemini-3.1-pro-high")
        assert target.endpoint.api_key == fake_api_keys["free"]
        assert target.endpoint.api_key != fake_api_keys["paid"]

    def test_agent_initialization_refuses_paid_key_when_locked(self, fake_api_keys):
        """Même si une clé payante est expressément injectée à l'instanciation, l'agent la rejette."""
        import os
        workspace_dir = os.path.join(config.BASE_DIR, "tmp_test")
        os.makedirs(workspace_dir, exist_ok=True)
        config.set_paid_key_authorized(False)
        agent = AntigravityAgent(
            workspace=workspace_dir,
            api_key=fake_api_keys["paid"],
            allowed_tools=[]
        )
        assert agent.api_key != fake_api_keys["paid"]
        assert agent.api_key == fake_api_keys["free"]

    def test_agent_accepts_paid_key_only_when_unlocked(self, fake_api_keys):
        """L'agent n'utilise la clé payante que si l'utilisateur l'a activée."""
        import os
        workspace_dir = os.path.join(config.BASE_DIR, "tmp_test")
        os.makedirs(workspace_dir, exist_ok=True)
        config.set_paid_key_authorized(True)
        agent = AntigravityAgent(
            workspace=workspace_dir,
            api_key=fake_api_keys["paid"],
            allowed_tools=[]
        )
        assert agent.api_key == fake_api_keys["paid"]


@pytest.mark.asyncio
class TestReasoningServicePaidKeyGate:
    """Vérifie le blocage préalable et l'exigence de la case à cocher pour les modèles lourds."""

    async def test_run_deep_reasoning_heavy_model_blocked_when_locked(self, fake_api_keys):
        """run_deep_reasoning pour modèle lourd exige l'interrupteur coché."""
        config.set_paid_key_authorized(False)

        res = await run_deep_reasoning(
            question="Résous ce problème mathématique complexe",
            model_choice="gemini-3.1-pro-high"
        )

        assert res.get("status") == "requires_user_confirmation"
        assert res.get("requires_paid_consent") is True
        assert res.get("requires_checkbox") is True


class TestSupervisionServiceGateState:
    """Vérifie la fidélité de la supervision système et télémétrie par rapport au verrou."""

    def test_supervision_overview_reflects_locked_gate(self):
        config.set_paid_key_authorized(False)
        overview = supervision_service.get_full_overview()
        assert overview["paid_key_authorized"] is False
        assert overview["api_keys"]["paid_key"]["authorized"] is False
        assert "VERROUILLÉE" in overview["api_keys"]["paid_key"]["status_label"]

    def test_supervision_overview_reflects_unlocked_gate(self):
        config.set_paid_key_authorized(True)
        overview = supervision_service.get_full_overview()
        assert overview["paid_key_authorized"] is True
        assert overview["api_keys"]["paid_key"]["authorized"] is True
        assert "AUTORISÉE" in overview["api_keys"]["paid_key"]["status_label"]


class TestRestApiPaidKeyEndpoints:
    """Vérifie les endpoints REST FastAPI gérant le verrou économique."""

    def test_get_and_post_paid_key_endpoint(self, authenticated_client):
        # 1. Verrouiller via POST
        res_post_lock = authenticated_client.post("/api/settings/paid-key", json={"authorized": False})
        assert res_post_lock.status_code == 200
        assert res_post_lock.json()["authorized"] is False
        assert config.is_paid_key_authorized() is False

        # 2. Vérifier via GET
        res_get = authenticated_client.get("/api/settings/paid-key")
        assert res_get.status_code == 200
        assert res_get.json()["authorized"] is False

        # 3. Déverrouiller via POST
        res_post_unlock = authenticated_client.post("/api/settings/paid-key", json={"authorized": True})
        assert res_post_unlock.status_code == 200
        assert res_post_unlock.json()["authorized"] is True
        assert config.is_paid_key_authorized() is True

    def test_post_paid_consent_denial(self, authenticated_client):
        """Vérifie le refus utilisateur via /api/paid-consent."""
        res = authenticated_client.post(
            "/api/paid-consent",
            json={"approved": False, "action": "antigravity"}
        )
        assert res.status_code == 200
        from core.shared_state import active_task_controller
        assert active_task_controller.get("paid_consent_given") is False
