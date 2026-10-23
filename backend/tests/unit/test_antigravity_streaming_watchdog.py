"""Tests unitaires pour le streaming de logs temps réel et le Watchdog anti-blocage Antigravity CLI."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.shared_state import (
    ACTIVE_AGY_LOGS,
    append_agy_log,
    get_agy_task_telemetry,
    mark_agy_task_status,
    register_agy_task,
)
from google_antigravity import (
    AntigravityAgent,
    AntigravityQuotaExhaustedError,
    _agy_watchdog_loop,
    STALL_THRESHOLD_S,
)


@pytest.fixture(autouse=True)
def clean_agy_logs():
    """Nettoie le registre des logs agy avant et après chaque test."""
    ACTIVE_AGY_LOGS.clear()
    yield
    ACTIVE_AGY_LOGS.clear()


def test_register_and_telemetry():
    """Vérifie l'enregistrement initial d'une tâche et la récupération de télémétrie."""
    entry = register_agy_task(
        task_id="task_test_1",
        goal="Audit de sécurité",
        model="Gemini 3.8 Flash (High)",
        effort="high",
    )
    assert entry["task_id"] == "task_test_1"
    assert entry["goal"] == "Audit de sécurité"
    assert entry["model"] == "Gemini 3.8 Flash (High)"
    assert entry["effort"] == "high"
    assert entry["status"] == "running"
    assert entry["current_step"] == "Démarrage de la tâche"
    assert len(entry["log_lines"]) == 0
    assert entry["error_detected"] is None

    # Télémétrie ciblée
    telemetry = get_agy_task_telemetry("task_test_1")
    assert telemetry["task_id"] == "task_test_1"
    assert isinstance(telemetry["log_lines"], list)

    # Télémétrie globale
    all_telemetry = get_agy_task_telemetry()
    assert "task_test_1" in all_telemetry


def test_append_agy_log_and_current_step():
    """Vérifie l'ajout de logs, l'horodatage et la déduction de current_step."""
    task_id = "task_test_2"
    register_agy_task(task_id, goal="Analyse de logs", model="Flash", effort="low")

    # Log stdout
    append_agy_log(task_id, "Exploration du répertoire backend", stream="stdout")
    t1 = get_agy_task_telemetry(task_id)
    assert len(t1["log_lines"]) == 1
    assert t1["log_lines"][0] == "[STDOUT] Exploration du répertoire backend"
    assert t1["current_step"] == "Exploration du répertoire backend"

    # Ligne non-informative (ne doit pas écraser current_step)
    append_agy_log(task_id, "{", stream="stdout")
    t2 = get_agy_task_telemetry(task_id)
    assert len(t2["log_lines"]) == 2
    assert t2["current_step"] == "Exploration du répertoire backend"

    # Log stderr
    append_agy_log(task_id, "Vérification des dépendances", stream="stderr")
    t3 = get_agy_task_telemetry(task_id)
    assert len(t3["log_lines"]) == 3
    assert t3["log_lines"][2] == "[STDERR] Vérification des dépendances"
    assert t3["current_step"] == "Vérification des dépendances"


def test_stalled_transition_resumes_on_log():
    """Vérifie qu'une tâche marquée stalled repasse en running dès réception de nouveau log."""
    task_id = "task_test_3"
    register_agy_task(task_id)
    mark_agy_task_status(task_id, "stalled", error="Silencieuse")
    assert get_agy_task_telemetry(task_id)["status"] == "stalled"

    append_agy_log(task_id, "Nouveau paquet émis", stream="stdout")
    assert get_agy_task_telemetry(task_id)["status"] == "running"


@pytest.mark.asyncio
async def test_watchdog_detects_stall():
    """Vérifie que le watchdog passe le statut à 'stalled' si aucun octet depuis > 60s."""
    task_id = "task_stall"
    register_agy_task(task_id)
    # Simuler un silence de 65 secondes
    ACTIVE_AGY_LOGS[task_id]["last_output_at"] = time.monotonic() - 65.0

    mock_proc = AsyncMock()
    is_done_event = asyncio.Event()
    timed_out_flag = [False]

    # Exécution d'une passe de watchdog avec check_interval=0.01
    watchdog_task = asyncio.create_task(
        _agy_watchdog_loop(
            proc=mock_proc,
            task_id=task_id,
            timeout=300.0,
            start_time=time.monotonic() - 65.0,
            is_done_event=is_done_event,
            timed_out_flag=timed_out_flag,
            check_interval=0.01,
        )
    )

    # Laisser le watchdog s'exécuter
    await asyncio.sleep(0.05)
    is_done_event.set()
    await watchdog_task

    telemetry = get_agy_task_telemetry(task_id)
    assert telemetry["status"] == "stalled"
    assert "Silencieuse" in (telemetry["error_detected"] or "")


@pytest.mark.asyncio
async def test_watchdog_triggers_timeout_and_kills_process():
    """Vérifie que le watchdog tue proprement le sous-processus si le timeout est dépassé."""
    task_id = "task_timeout"
    register_agy_task(task_id)

    mock_proc = AsyncMock()
    mock_proc.terminate = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    mock_proc.returncode = None

    is_done_event = asyncio.Event()
    timed_out_flag = [False]

    # Simuler un démarrage il y a 100s avec un timeout de 10s
    start_time = time.monotonic() - 100.0

    watchdog_task = asyncio.create_task(
        _agy_watchdog_loop(
            proc=mock_proc,
            task_id=task_id,
            timeout=10.0,
            start_time=start_time,
            is_done_event=is_done_event,
            timed_out_flag=timed_out_flag,
            check_interval=0.01,
        )
    )

    await asyncio.sleep(0.05)
    await watchdog_task

    assert timed_out_flag[0] is True
    mock_proc.terminate.assert_called()
    mock_proc.kill.assert_called()
    telemetry = get_agy_task_telemetry(task_id)
    assert telemetry["status"] == "timeout"


@pytest.mark.asyncio
async def test_antigravity_agent_streaming_and_quota_detection():
    """Vérifie la détection immédiate de quota dans le flux et l'enregistrement dans ACTIVE_AGY_LOGS."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.terminate = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    stdout_reader = AsyncMock()
    stdout_reader.readline = AsyncMock(side_effect=[b"Demarrage analyse...\n", b""])
    stderr_reader = AsyncMock()
    stderr_reader.readline = AsyncMock(side_effect=[b"429 ResourceExhausted: Quota exceeded for model\n", b""])

    mock_proc.stdout = stdout_reader
    mock_proc.stderr = stderr_reader

    agent = AntigravityAgent(
        workspace="./test_ws",
        model="gemini-3.8-flash",
        effort="high",
        timeout_seconds=30,
        task_id="task_quota_test",
    )

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "OK", "/mock/bin/agy")):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(AntigravityQuotaExhaustedError):
                await agent.run_cli_task_stream("Test quota immédiat")

    telemetry = get_agy_task_telemetry("task_quota_test")
    assert telemetry["status"] == "failed"
    assert "Quota" in (telemetry["error_detected"] or "")
