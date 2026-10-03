"""Tests unitaires pour l'exécuteur agentique (services/agentic_runner.py)
avec simulation complète des sous-processus sans aucun appel API payante.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch

from services.agentic_runner import (
    AgentOutput,
    run_agentic,
    _build_command,
)
from services.key_gate import PaidKeyConsentRequired, grant_paid_consent


@pytest.fixture(autouse=True)
def clean_consent():
    """Nettoie le registre de consentement avant chaque test."""
    from services.key_gate import clear_all_consents
    clear_all_consents()
    yield
    clear_all_consents()


@pytest.mark.asyncio
async def test_run_agentic_success():
    valid_json = json.dumps({
        "conclusion": "Architecture validée avec succès.",
        "confidence": 0.95,
        "sources": ["main.py", "config.py"],
        "open_questions": [],
        "artifacts": ["schema.json"]
    })

    mock_exec = AsyncMock(return_value=(0, valid_json, ""))

    result = await run_agentic(
        role="architect",
        prompt="Valide l'architecture",
        model="pro",
        effort="high",
        custom_exec_fn=mock_exec,
    )

    assert result.status == "success"
    assert result.conclusion == "Architecture validée avec succès."
    assert result.confidence == 0.95
    assert result.sources == ["main.py", "config.py"]
    assert result.open_questions == []
    assert result.artifacts == ["schema.json"]
    assert mock_exec.call_count == 1


@pytest.mark.asyncio
async def test_run_agentic_invalid_model_fails_before_exec():
    mock_exec = AsyncMock()

    with pytest.raises(ValueError, match="Modèle.*invalide"):
        await run_agentic(
            role="architect",
            prompt="Test",
            model="unsupported-model",
            effort="high",
            custom_exec_fn=mock_exec,
        )

    # Le subprocess ne doit jamais avoir été appelé
    assert mock_exec.call_count == 0


@pytest.mark.asyncio
async def test_run_agentic_rejects_thinking_flag():
    with pytest.raises(ValueError, match="--thinking.*interdite"):
        _build_command("architect", "prompt", "pro", "high --thinking")


@pytest.mark.asyncio
async def test_run_agentic_pro_timeout_fallback_to_flash_high():
    # Premier appel en 'pro' : TimeoutError
    # Repli unique automatique en 'flash/high' : succès
    valid_fallback_json = json.dumps({
        "conclusion": "Synthèse obtenue via repli flash/high",
        "confidence": 0.8,
        "sources": ["doc.md"],
        "open_questions": ["questions"],
        "artifacts": []
    })

    calls = []

    async def mock_exec(cmd, timeout):
        calls.append(cmd)
        if "--model" in cmd and "pro" in cmd[cmd.index("--model") + 1]:
            raise asyncio.TimeoutError("Timeout pro")
        return 0, valid_fallback_json, ""

    result = await run_agentic(
        role="architect",
        prompt="Tâche complexe",
        model="pro",
        effort="high",
        custom_exec_fn=mock_exec,
    )

    assert result.status == "success"
    assert result.model == "flash"
    assert result.effort == "high"
    assert result.conclusion == "Synthèse obtenue via repli flash/high"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_run_agentic_timeout_after_fallback_fails():
    async def mock_exec(cmd, timeout):
        raise asyncio.TimeoutError("Timeout persistant")

    result = await run_agentic(
        role="architect",
        prompt="Tâche complexe",
        model="pro",
        effort="high",
        custom_exec_fn=mock_exec,
    )

    assert result.status == "failed"
    assert "Timeout" in result.error


@pytest.mark.asyncio
async def test_run_agentic_json_retry_success():
    # Premier appel : texte brut sans JSON
    # Deuxième appel (relance) : JSON valide
    valid_json = json.dumps({
        "conclusion": "Conclusion après relance",
        "confidence": 0.9,
        "sources": [],
        "open_questions": [],
        "artifacts": []
    })

    responses = [
        (0, "Voici mon rapport textuel sans le JSON demandé...", ""),
        (0, valid_json, "")
    ]

    async def mock_exec(cmd, timeout):
        return responses.pop(0)

    result = await run_agentic(
        role="writer",
        prompt="Rédige une note",
        model="flash",
        effort="medium",
        custom_exec_fn=mock_exec,
    )

    assert result.status == "success"
    assert result.conclusion == "Conclusion après relance"


@pytest.mark.asyncio
async def test_run_agentic_json_retry_fails_after_one_attempt():
    # Deux réponses sans JSON valide -> résultat failed
    responses = [
        (0, "Réponse textuelle 1", ""),
        (0, "Réponse textuelle 2 toujours sans format JSON", "")
    ]

    async def mock_exec(cmd, timeout):
        return responses.pop(0)

    result = await run_agentic(
        role="writer",
        prompt="Rédige une note",
        model="flash",
        effort="medium",
        custom_exec_fn=mock_exec,
    )

    assert result.status == "failed"
    assert "JSON" in result.error


@pytest.mark.asyncio
async def test_run_agentic_quota_exhausted_raises_paid_key_consent_required():
    mock_exec = AsyncMock(return_value=(1, "", "Error 429: ResourceExhausted Quota exceeded on agy CLI"))

    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        await run_agentic(
            role="researcher",
            prompt="Recherche",
            model="flash",
            effort="low",
            session_id="session-123",
            task_id="task-456",
            custom_exec_fn=mock_exec,
        )

    assert exc_info.value.reason == "cli_quota_exceeded"
    assert exc_info.value.session_id == "session-123"
    assert exc_info.value.task_id == "task-456"


@pytest.mark.asyncio
async def test_run_agentic_quota_exhausted_with_consent_executes_paid_api_once():
    mock_exec = AsyncMock(return_value=(1, "", "Error 429: ResourceExhausted"))

    valid_paid_json = json.dumps({
        "conclusion": "Réponse exécutée via API Gemini Paid",
        "confidence": 1.0,
        "sources": ["api_paid"],
        "open_questions": [],
        "artifacts": []
    })

    mock_paid_api = AsyncMock(return_value=valid_paid_json)

    # Accorder le consentement préalable
    grant_paid_consent(session_id="session-123", task_id="task-456")

    with patch("config.GEMINI_API_KEY_PAID", "AIzaSyFakePaidKey123"):
        result = await run_agentic(
            role="researcher",
            prompt="Recherche sous quota",
            model="pro",
            effort="high",
            session_id="session-123",
            task_id="task-456",
            custom_exec_fn=mock_exec,
            execute_paid_api_fn=mock_paid_api,
        )

    assert result.status == "success"
    assert result.conclusion == "Réponse exécutée via API Gemini Paid"
    assert result.effort == "paid_api"
    # L'API payante ne doit avoir été exécutée qu'une seule fois
    assert mock_paid_api.call_count == 1
