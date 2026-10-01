"""Tests unitaires pour services/key_gate.py et la gouvernance des clés API Gemini.

Exigences testées :
1. Clé FREE par défaut.
2. Refus strict de la clé PAID sans consentement explicite.
3. 2 raisons distinctes d'éligibilité (free_key_failure et cli_quota_exceeded).
4. Expiration stricte du consentement à la fin de la tâche (zéro persistance globale).
5. Reprise automatique après acceptation (confirm_paid_key oui -> succès et expiration, non -> failed).
Règle : AUCUN appel API Gemini payant (usage exclusif de mocks).
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import config
from services.key_gate import (
    PaidKeyConsentRequired,
    get_key,
    grant_paid_consent,
    has_paid_consent,
    revoke_paid_consent,
    consume_paid_consent,
    clear_all_consents,
    set_pending_action,
    get_pending_action,
    clear_pending_action,
    is_qualified_free_key_failure,
)
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult


@pytest.fixture(autouse=True)
def cleanup_key_gate():
    """Garantit l'isolation de chaque test en réinitialisant les consentements et actions en attente."""
    clear_all_consents()
    clear_pending_action()
    yield
    clear_all_consents()
    clear_pending_action()


def test_free_key_by_default(monkeypatch):
    """1. Vérifie que la clé FREE est renvoyée par défaut."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key_123")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key_456")

    key = get_key(purpose="live_voice")
    assert key == "fake_free_key_123"

    key_task = get_key(purpose="reasoning", task_id="task_abc")
    assert key_task == "fake_free_key_123"


def test_refusal_without_consent(monkeypatch):
    """2. Vérifie qu'en l'absence de consentement, la clé PAID n'est jamais renvoyée et lève PaidKeyConsentRequired."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key_123")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key_456")

    assert not has_paid_consent(task_id="task_without_consent")

    # Si require_paid est demandé sans consentement, une exception est levée
    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        get_key(purpose="heavy_task", task_id="task_without_consent", require_paid=True)

    assert exc_info.value.reason in ("free_key_failure", "cli_quota_exceeded")
    assert "fake_paid_key_456" not in str(exc_info.value)


def test_two_distinct_reasons(monkeypatch):
    """3. Vérifie les 2 raisons distinctes (free_key_failure et cli_quota_exceeded)."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key_123")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key_456")

    # Raison A : Échec qualifié de la clé gratuite (ex: 429 quota dépassé)
    is_qual_429, detail_429 = is_qualified_free_key_failure("ResourceExhausted 429: quota exceeded")
    assert is_qual_429 is True
    assert "429" in detail_429 or "Quota" in detail_429

    with pytest.raises(PaidKeyConsentRequired) as exc_a:
        get_key(
            purpose="test_a",
            force_reason="free_key_failure",
            failure_detail=detail_429,
        )
    assert exc_a.value.reason == "free_key_failure"
    assert "Quota" in exc_a.value.detail or "429" in exc_a.value.detail

    # Raison B : Quota Antigravity CLI dépassé
    with pytest.raises(PaidKeyConsentRequired) as exc_b:
        get_key(
            purpose="antigravity_cli",
            force_reason="cli_quota_exceeded",
            failure_detail="Quota Antigravity CLI dépassé",
        )
    assert exc_b.value.reason == "cli_quota_exceeded"
    assert "Antigravity CLI" in exc_b.value.detail


def test_consent_expiration(monkeypatch):
    """4. Vérifie l'expiration stricte du consentement à la fin de la tâche (aucun consentement global)."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key_123")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key_456")

    task_1 = "task_uuid_100"
    task_2 = "task_uuid_200"

    # Consentement accordé pour task_1
    grant_paid_consent(task_id=task_1, reason="free_key_failure", scope="this_task")
    assert has_paid_consent(task_id=task_1) is True
    assert has_paid_consent(task_id=task_2) is False

    # task_1 a bien accès à la clé payante
    assert get_key(task_id=task_1) == "fake_paid_key_456"
    # task_2 reste sur la clé gratuite (pas de fuite globale)
    assert get_key(task_id=task_2) == "fake_free_key_123"

    # Fin de la tâche task_1 -> consommation du consentement
    consume_paid_consent(task_id=task_1)
    assert has_paid_consent(task_id=task_1) is False

    # Après expiration, task_1 redevient strictement gratuite
    assert get_key(task_id=task_1) == "fake_free_key_123"
    with pytest.raises(PaidKeyConsentRequired):
        get_key(task_id=task_1, require_paid=True)


@pytest.mark.asyncio
async def test_dispatcher_intercepts_and_confirms_paid_key(monkeypatch):
    """5. Vérifie l'interception dans dispatcher et la reprise après confirm_paid_key."""
    import core.tools.dispatcher as disp_mod
    real_execute = disp_mod._execute_dispatch_tool

    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key_123")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key_456")

    # Cas A : Interception de cli_quota_exceeded -> status='needs_user'
    async def mock_exec_cli(name, args, **kwargs):
        if name == "ask_deep_reasoning":
            raise PaidKeyConsentRequired(
                reason="cli_quota_exceeded",
                detail="Quota 5h Antigravity CLI dépassé",
                purpose="ask_deep_reasoning",
                task_id="task_cli_test"
            )
        return await real_execute(name, args, **kwargs)

    with patch("core.tools.dispatcher._execute_dispatch_tool", side_effect=mock_exec_cli):
        res = await dispatch_tool(
            name="ask_deep_reasoning",
            args={"question": "Optimisation complexe", "model": "gemini-3.1-pro-high"}
        )

        assert res["status"] == "needs_user"
        assert "Le quota des agents Antigravity est dépassé" in res["user_message"]
        assert "Veux-tu que j'utilise la clé payante pour terminer ?" in res["user_message"]
        assert get_pending_action() is not None
        assert get_pending_action().name == "ask_deep_reasoning"

        # Cas B : Pierre refuse l'utilisation de la clé payante (accept=False) -> status='failed'
        res_refusal = await dispatch_tool("confirm_paid_key", {"accept": False})
        assert res_refusal["status"] == "failed"
        assert "refusée" in res_refusal["user_message"]
        assert get_pending_action() is None
        assert has_paid_consent(task_id="task_cli_test") is False

    # Cas C : Pierre accepte l'utilisation de la clé payante (accept=True) -> reprise et expiration
    async def mock_exec_resume(name, args, **kwargs):
        if name == "test_action":
            if not has_paid_consent(task_id="task_resume_test"):
                raise PaidKeyConsentRequired(
                    reason="free_key_failure",
                    detail="429 Resource Exhausted",
                    purpose="test_action",
                    task_id="task_resume_test"
                )
            return {
                "status": "done",
                "verified": True,
                "user_message": "Action terminée avec succès sur clé payante de secours."
            }
        return await real_execute(name, args, **kwargs)

    with patch("core.tools.dispatcher._execute_dispatch_tool", side_effect=mock_exec_resume):
        res_suspend = await dispatch_tool("test_action", {"param": 42})
        assert res_suspend["status"] == "needs_user"
        assert "La clé gratuite a échoué" in res_suspend["user_message"]
        assert "Veux-tu que j'utilise la clé payante pour terminer ?" in res_suspend["user_message"]
        assert get_pending_action() is not None

        # Pierre dit OUI : confirm_paid_key accorde le consentement, relance test_action, puis expire
        res_confirm = await dispatch_tool("confirm_paid_key", {"accept": True})
        assert res_confirm["status"] == "done"
        assert res_confirm["verified"] is True
        assert "Action terminée avec succès" in res_confirm["user_message"]

        # Le consentement a bien expiré à la fin de la tâche
        assert has_paid_consent(task_id="task_resume_test") is False
        assert get_pending_action() is None
