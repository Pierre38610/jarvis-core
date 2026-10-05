"""tests/test_l3_error_propagation.py
Tests unitaires et d'intégration pour la capture, structuration et propagation des erreurs L3 (P2).
Vérifie :
1. Structure d'erreur L3 stable (étape, exception, traceback court, capture écran, cause courte).
2. Assainissement des secrets (clés API, tokens, cookies, mots de passe).
3. Stockage de la dernière erreur L3 (get_last_l3_error, gemini_deep_research_engine).
4. Propagation depuis browser_open_task et GeminiWebAutomator jusqu'au dispatcher.
5. Remplacement de l'erreur générique par un message utilisateur explicite (étape + cause + repli).
6. Préservation des chemins de succès et du repli Map-Reduce.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult
from services.browser_agent.loop import BrowserTask, run_browser_task
from services.gemini_web_automator import (
    GeminiWebAutomator,
    gemini_deep_research_engine,
)
from services.l3_error import (
    L3ErrorDetails,
    get_last_l3_error,
    set_last_l3_error,
    clear_last_l3_error,
    sanitize_error_text,
)
from services.voice_injection_queue import voice_injection_queue


@pytest.fixture(autouse=True)
def clean_last_error():
    clear_last_l3_error()
    yield
    clear_last_l3_error()


# ─── 1. Structure L3ErrorDetails et Assainissement ───────────────────────────

def test_l3_error_details_structure_and_aliases():
    """Vérifie la structure minimale requise et les alias de compatibilité."""
    err = L3ErrorDetails(
        etape="cdp_connection",
        exception="Connection refused on port 9222",
        traceback_court="Traceback (most recent call last):\n  File ...",
        capture_ecran="/tmp/shots/error.jpg",
        cause_courte="Chrome CDP injoignable",
        fallback_initiated=True,
    )

    data = err.to_dict()
    assert data["etape"] == "cdp_connection"
    assert data["step"] == "cdp_connection"
    assert data["exception"] == "Connection refused on port 9222"
    assert data["error"] == "Connection refused on port 9222"
    assert "Traceback" in data["traceback_court"]
    assert data["short_traceback"] == data["traceback_court"]
    assert data["capture_ecran"] == "/tmp/shots/error.jpg"
    assert data["screenshot_path"] == "/tmp/shots/error.jpg"
    assert data["cause_courte"] == "Chrome CDP injoignable"
    assert data["fallback_initiated"] is True
    assert "Échec à l'étape 'cdp_connection'" in data["user_message"]
    assert "repli en cours" in data["user_message"]


def test_l3_error_sanitizes_secrets():
    """Vérifie que les clés d'API, tokens et cookies sont purgés."""
    dirty_text = (
        "Error with AIzaSyD9ExampleSecretKey1234567890 and Bearer eyJhbGciOiJIUzI1NiJ9.test.token "
        "and cookie: session=secret_cookie_val; password='my_super_secret_pwd'"
    )
    clean = sanitize_error_text(dirty_text)
    assert "AIza" not in clean
    assert "[REDACTED_GEMINI_KEY]" in clean
    assert "eyJhbGci" not in clean
    assert "[REDACTED_TOKEN]" in clean
    assert "secret_cookie_val" not in clean
    assert "[REDACTED_COOKIE]" in clean
    assert "my_super_secret_pwd" not in clean
    assert "[REDACTED]" in clean

    err = L3ErrorDetails(
        etape="api_call",
        exception=dirty_text,
        traceback_court="File app.py\n  key = 'AIzaSyD9ExampleSecretKey1234567890'",
    )
    assert "AIza" not in err.exception
    assert "AIza" not in err.traceback_court


def test_global_and_engine_error_storage():
    """Vérifie le stockage et la récupération sûre de la dernière erreur L3."""
    err = L3ErrorDetails(
        etape="prompt_fill",
        exception="Input box not interactable",
        cause_courte="Champ de prompt introuvable",
    )
    set_last_l3_error(err)

    stored = get_last_l3_error()
    assert stored is not None
    assert stored["etape"] == "prompt_fill"
    assert stored["cause_courte"] == "Champ de prompt introuvable"
    assert gemini_deep_research_engine.get_last_l3_error()["etape"] == "prompt_fill"


# ─── 2. Propagation depuis BrowserTask & run_browser_task ────────────────────

@pytest.mark.asyncio
async def test_browser_task_open_failure_propagates_l3_error():
    """Vérifie que l'échec d'ouverture browser_open_task remplit last_error et ToolResult."""
    task = BrowserTask(task_id="bt_test_open_fail", goal="Test mission L3", recipe="gemini_deep_research")

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value={"status": "error", "error": "VPS down"}), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("services.browser_agent.loop._call_rpc", new_callable=AsyncMock) as mock_rpc:
        mock_rpc.return_value = {"ok": False, "status": "pc_offline", "error": "PC local déconnecté"}

        res = await run_browser_task(task)

    assert res.status == "failed"
    assert task.status == "failed"
    assert task.last_error is not None
    assert task.last_error["etape"] == "browser_open_task"
    assert "PC local déconnecté" in task.last_error["exception"]

    assert "l3_error" in res.data
    assert res.data["l3_error"]["etape"] == "browser_open_task"
    assert get_last_l3_error()["etape"] == "browser_open_task"


# ─── 3. Propagation dans GeminiWebAutomator ──────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_web_automator_step_failures_record_l3_error():
    """Vérifie que chaque étape d'échec de l'automateur capture et stocke L3ErrorDetails."""
    automator = GeminiWebAutomator()

    # 1. Échec connexion CDP
    with patch.object(automator, "_connect", new_callable=AsyncMock, return_value=False), \
         patch.object(automator, "_capture_screenshot", new_callable=AsyncMock, return_value="/tmp/shots/cdp.jpg"):
        res1 = await automator.run_deep_research("Test CDP failure")
        assert res1["status"] == "error"
        assert res1["l3_error"]["etape"] == "cdp_connection"
        assert res1["l3_error"]["capture_ecran"] == "/tmp/shots/cdp.jpg"
        assert get_last_l3_error()["etape"] == "cdp_connection"

    # 2. Session Google requise
    with patch.object(automator, "_connect", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_navigate_to_gemini", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_check_login_state", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_capture_screenshot", new_callable=AsyncMock, return_value="/tmp/shots/login.jpg"), \
         patch.object(automator, "_inject_voice_milestone", new_callable=AsyncMock):
        res2 = await automator.run_deep_research("Test login needed")
        assert res2["status"] == "needs_login"
        assert res2["l3_error"]["etape"] == "login_required"
        assert get_last_l3_error()["etape"] == "login_required"

    # 3. Échec saisie du sujet
    with patch.object(automator, "_connect", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_navigate_to_gemini", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_check_login_state", new_callable=AsyncMock, return_value=False), \
         patch.object(automator, "_select_deep_research_mode", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_fill_prompt", new_callable=AsyncMock, return_value=False), \
         patch.object(automator, "_capture_screenshot", new_callable=AsyncMock, return_value="/tmp/shots/fill.jpg"), \
         patch.object(automator, "_inject_voice_milestone", new_callable=AsyncMock):
        res3 = await automator.run_deep_research("Test fill fail")
        assert res3["status"] == "error"
        assert res3["l3_error"]["etape"] == "prompt_fill"
        assert get_last_l3_error()["etape"] == "prompt_fill"


# ─── 4. Propagation jusqu'au Dispatcher & Repli Map-Reduce ────────────────────

@pytest.mark.asyncio
async def test_dispatcher_propagates_l3_error_on_browser_failure_and_triggers_fallback():
    """Vérifie que l'échec du Browser Agent est capturé, journalisé et déclenche le repli Map-Reduce."""
    mock_browser_res = ToolResult.failed(
        user_message="Impossible de démarrer la navigation : Chrome CDP non joignable",
        error_hint="cdp_offline",
        data={
            "l3_error": {
                "etape": "cdp_connection",
                "exception": "Connection refused",
                "cause_courte": "Chrome CDP non joignable",
                "fallback_initiated": True,
            }
        },
    )

    from services.google_antigravity import AgentOutput

    mock_prospector = AgentOutput(
        status="success",
        conclusion="Prospection terminée avec 5 sources",
        sources=["https://source1.com"],
        confidence="0.9",
    )
    mock_analyst = AgentOutput(
        status="success",
        conclusion="Analyse critique validée",
        sources=["https://source1.com"],
        confidence="0.95",
        open_questions=[],
    )
    mock_synthesis = AgentOutput(
        status="success",
        conclusion="Rapport final de synthèse Deep Research",
        sources=["https://source1.com"],
        confidence="0.95",
        artifacts=["report.md"],
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=mock_browser_res) as mock_b_agent, \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock, side_effect=[mock_prospector, mock_analyst, mock_synthesis]):

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Étude spatiale", "sync": True},
            websocket=None,
            session=None,
        )

        mock_b_agent.assert_awaited_once()
        assert resp["status"] == "done"
        assert "Rapport final de synthèse Deep Research" in resp["user_message"]
        assert resp["verified"] is True
        assert len(resp["phases"]) == 3


@pytest.mark.asyncio
async def test_dispatcher_bg_failure_injects_step_and_cause_without_generic_error():
    """Vérifie que le message vocal et les logs d'échec L3 contiennent l'étape et la cause courte."""
    mock_browser_res = ToolResult.failed(
        user_message="PC offline",
        error_hint="pc_offline",
        data={
            "l3_error": {
                "etape": "browser_open_task",
                "exception": "PC local déconnecté",
                "cause_courte": "PC local injoignable",
            }
        }
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=mock_browser_res), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(False, "CLI agy indisponible", None)), \
         patch.object(voice_injection_queue, "enqueue", new_callable=AsyncMock) as mock_voice_enqueue, \
         patch("core.tools.dispatcher.safe_send_live_client_content", new_callable=AsyncMock) as mock_live_content:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Recherche quantique"},
            websocket=None,
            session=MagicMock(),
        )

        assert resp["status"] == "started"
        # Laisser la tâche d'arrière-plan s'exécuter
        await asyncio.sleep(0.1)

        # Vérification injection vocale
        mock_voice_enqueue.assert_awaited()
        voice_kwargs = mock_voice_enqueue.await_args.kwargs
        voice_text = voice_kwargs.get("text", "")

        assert "Erreur interne lors de la recherche" not in voice_text
        assert "étape 'cli_verification'" in voice_text or "cli_verification" in str(voice_kwargs.get("metadata"))
        assert "indisponible" in voice_text.lower() or "cli" in voice_text.lower()

        # Vérification safe_send_live_client_content
        mock_live_content.assert_awaited()
        live_text = mock_live_content.await_args.args[1]
        assert "[EXCEPTION RECHERCHE L3]" in live_text
        assert "cli_verification" in live_text
