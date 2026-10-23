"""backend/tests/unit/test_antigravity_task_engine.py
Validation unitaire du moteur d'exécution et de télémétrie des tâches Antigravity CLI.
Couvre l'enregistrement de télémétrie, le streaming temps réel, l'interdiction stricte de --thinking,
la désérialisation JSON robuste, la détection des dépassements de quota et la gestion des sous-agents.
"""

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.shared_state import (
    ACTIVE_AGY_LOGS,
    append_agy_log,
    get_agy_task_telemetry,
    mark_agy_task_status,
    register_agy_task,
    spawn_subagent,
    update_subagent,
    complete_subagent,
    active_task_controller,
)
from google_antigravity import (
    _sanitize_secrets,
    AntigravityQuotaExhaustedError,
    _agy_watchdog_loop,
    find_antigravity_binary,
)
from services.agentic_runner import (
    _build_command,
    _try_parse_json_candidate,
    _clean_text_for_json,
    _is_quota_error,
    AgentOutput,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Nettoie le registre des logs agy avant et après chaque test."""
    ACTIVE_AGY_LOGS.clear()
    yield
    ACTIVE_AGY_LOGS.clear()


# ─── 1. Registre de Télémétrie & Logs ─────────────────────────────────────────
def test_task_registration_and_telemetry():
    """Vérifie l'enregistrement et la restitution de télémétrie."""
    entry = register_agy_task(
        task_id="engine_task_1",
        goal="Audit de performance",
        model="gemini-3.8-flash",
        effort="medium",
    )
    assert entry["task_id"] == "engine_task_1"
    assert entry["goal"] == "Audit de performance"
    assert entry["model"] == "gemini-3.8-flash"
    assert entry["effort"] == "medium"
    assert entry["status"] == "running"
    assert entry["current_step"] == "Démarrage de la tâche"

    # Récupération de télémétrie ciblée
    telem = get_agy_task_telemetry("engine_task_1")
    assert telem["task_id"] == "engine_task_1"
    assert isinstance(telem["log_lines"], list)

    # Récupération globale
    all_telem = get_agy_task_telemetry()
    assert "engine_task_1" in all_telem


def test_append_log_and_step_deduction():
    """Vérifie l'ajout de lignes de logs et la mise à jour de current_step."""
    task_id = "engine_task_2"
    register_agy_task(task_id, goal="Analyse de logs", model="gemini-3.7-flash", effort="low")

    append_agy_log(task_id, "Lecture du fichier backend/core/tools/declarations.py", stream="stdout")
    telem = get_agy_task_telemetry(task_id)
    assert len(telem["log_lines"]) == 1
    assert "[STDOUT] Lecture du fichier" in telem["log_lines"][0]
    assert "Lecture du fichier" in telem["current_step"]

    # Changement de statut
    mark_agy_task_status(task_id, "completed")
    telem_after = get_agy_task_telemetry(task_id)
    assert telem_after["status"] == "completed"


# ─── 2. Règle Stricte Anti-Flag '--thinking' ─────────────────────────────────
def test_build_command_rejects_thinking_flag():
    """Vérifie que l'utilisation du flag '--thinking' lève une exception stricte."""
    with pytest.raises(ValueError, match="--thinking"):
        _build_command(role="coder", prompt="Corriger le bug", model="gemini-3.8-flash", effort="--thinking")

    with pytest.raises(ValueError, match="--thinking"):
        _build_command(role="coder", prompt="prompt avec --thinking flag", model="gemini-3.8-flash", effort="low")


def test_build_command_standard_valid():
    """Vérifie la construction normale de la commande sans flag interdit."""
    cmd = _build_command(role="analyst", prompt="Faire un rapport", model="gemini-3.8-flash", effort="medium")
    assert isinstance(cmd, list)
    assert "-p" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert not any("--thinking" in arg for arg in cmd)


# ─── 3. Sécurité & Nettoyage des Secrets ──────────────────────────────────────
def test_sanitize_secrets_redaction():
    """Vérifie la censure stricte des clés API et tokens dans les logs."""
    sample = "Exception: Error with key AIzaSyD1234567890abcdefghijklmnopqrstuv and sk-1234567890abcdefghij"
    cleaned = _sanitize_secrets(sample)
    assert "AIza" not in cleaned
    assert "sk-" not in cleaned
    assert "[REDACTED_GEMINI_KEY]" in cleaned or "[REDACTED_API_KEY]" in cleaned or "[REDACTED" in cleaned


# ─── 4. Parsing JSON Résilient ───────────────────────────────────────────────
def test_clean_text_and_json_parsing():
    """Vérifie le nettoyage ANSI et l'extraction de JSON."""
    raw_terminal = "\x1B[32m{\"conclusion\": \"Analyse terminée\", \"sources\": [\"doc.py\"]}\x1B[0m"
    cleaned = _clean_text_for_json(raw_terminal)
    assert "\x1B" not in cleaned

    parsed = _try_parse_json_candidate(cleaned)
    assert parsed is not None
    assert parsed.get("conclusion") == "Analyse terminée"


def test_is_quota_error_detection():
    """Vérifie la détection des erreurs de quota 429 / ResourceExhausted."""
    assert _is_quota_error("Error 429: ResourceExhausted quota exceeded", exit_code=1) is True
    assert _is_quota_error("Normal output with exit code 0", exit_code=0) is False


# ─── 5. Gestion des Sous-Agents ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_subagent_lifecycle():
    """Vérifie le cycle de vie complet d'un sous-agent Antigravity."""
    agent_id = "test_subagent_42"
    mock_ws = AsyncMock()
    active_task_controller["websocket"] = mock_ws
    try:
        agent = await spawn_subagent(
            agent_id=agent_id,
            name="Sous-Agent Test",
            role="Code Reviewer",
            activity="thinking",
            task="Revue de code",
            model="gemini-3.8-flash",
        )
        assert agent["id"] == agent_id
        assert agent["name"] == "Sous-Agent Test"

        # Update
        updated = await update_subagent(agent_id, activity="coding", task="Écriture des patchs")
        assert updated is not None

        # Complete
        completed = await complete_subagent(agent_id, summary="Revue terminée avec succès")
        assert completed is not None
    finally:
        active_task_controller["websocket"] = None
