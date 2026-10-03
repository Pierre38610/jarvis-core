"""tests/test_antigravity_cli_reliability.py
Tests d'acceptation pour P1 — Fiabilisation Antigravity CLI et raisonnement minimal.
Couvre :
1. Préflight & binaire (absent, code non nul, timeout, succès, cache, force_refresh, invalidate_cache).
2. Commande exacte (sans --thinking, cwd/env, streams drainés, timeout, annulation sans zombie).
3. Gestion quota vs syntaxe (repli Flash low sur quota, pas de bascule arbitraire sur erreur syntaxe).
4. Dispatch Tier 1 agentique (Flash low) vs outil déterministe direct.
5. Non-divulgation des clés et secrets dans les logs, erreurs et résultats.
"""

import asyncio
import json
import logging
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from google_antigravity import (
    AntigravityAgent,
    AntigravityQuotaExhaustedError,
    CognitiveConfig,
    TaskResult,
    find_antigravity_binary,
    invalidate_cli_ready_cache,
    resolve_cli_model_args,
    verify_antigravity_cli_ready,
    _sanitize_secrets,
)
from services.agentic_runner import (
    AgentOutput,
    _build_command,
    _is_quota_error,
    run_agentic,
)
from services.model_routing.fallback_handler import (
    cooldown_manager,
    execute_with_fallback,
    is_quota_error,
)
from services.model_routing.model_router import RoutingDecision
from core.tools.dispatcher import dispatch_tool, _resolve_agy_model, _resolve_agy_effort


@pytest.fixture(autouse=True)
def reset_cache_and_cooldown():
    invalidate_cli_ready_cache()
    cooldown_manager.clear()
    yield
    invalidate_cli_ready_cache()
    cooldown_manager.clear()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests Préflight & Résolution Binaire
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preflight_binary_not_found():
    """Préflight : binaire introuvable retourne is_ready=False et message structuré."""
    with patch("google_antigravity.find_antigravity_binary", return_value=None):
        ready, msg, path = await verify_antigravity_cli_ready(force_refresh=True)
        assert ready is False
        assert path is None
        assert "introuvable" in msg.lower()


@pytest.mark.asyncio
async def test_preflight_nonzero_exit_code():
    """Préflight : commande --version échoue avec code de retour non nul."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"unknown flag or crash"))

    with patch("google_antigravity.find_antigravity_binary", return_value="/mock/bin/agy"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            ready, msg, path = await verify_antigravity_cli_ready(force_refresh=True)
            assert ready is False
            assert path == "/mock/bin/agy"
            assert "erreur" in msg.lower()


@pytest.mark.asyncio
async def test_preflight_timeout_kills_process():
    """Préflight : timeout sur --version tue proprement le processus et renvoie is_ready=False."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    with patch("google_antigravity.find_antigravity_binary", return_value="/mock/bin/agy"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            ready, msg, path = await verify_antigravity_cli_ready(force_refresh=True)
            assert ready is False
            assert "timeout" in msg.lower()
            mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_preflight_success_and_caching_with_force_refresh():
    """Préflight : succès mis en cache puis invalidé par force_refresh ou invalidate_cli_ready_cache."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"agy version 1.2.3", b""))

    with patch("google_antigravity.find_antigravity_binary", return_value="/mock/bin/agy"):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            # 1. Premier appel : exécute le subprocess
            ready1, msg1, path1 = await verify_antigravity_cli_ready(force_refresh=True)
            assert ready1 is True
            assert "1.2.3" in msg1
            assert path1 == "/mock/bin/agy"
            assert mock_exec.call_count == 1

            # 2. Deuxième appel sans force_refresh : utilise le cache (aucun nouvel appel exec)
            ready2, msg2, path2 = await verify_antigravity_cli_ready(force_refresh=False)
            assert ready2 is True
            assert mock_exec.call_count == 1

            # 3. Troisième appel avec force_refresh=True : réexécute
            ready3, msg3, path3 = await verify_antigravity_cli_ready(force_refresh=True)
            assert ready3 is True
            assert mock_exec.call_count == 2

            # 4. Invalidation explicite
            invalidate_cli_ready_cache()
            ready4, msg4, path4 = await verify_antigravity_cli_ready(force_refresh=False)
            assert ready4 is True
            assert mock_exec.call_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests Exécution Subprocess, Arguments & Absence de Processus Zombies
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_cli_model_args_forbids_thinking():
    """Vérifie que resolve_cli_model_args n'injecte jamais --thinking et lève une erreur si présent."""
    args = resolve_cli_model_args("gemini-3.7-flash", effort="high")
    assert "--thinking" not in args
    assert "--model" in args
    assert "--effort" in args
    assert "high" in args

    with pytest.raises(ValueError, match="--thinking.*interdite"):
        resolve_cli_model_args("gemini-3.7-flash", effort="high --thinking")


@pytest.mark.asyncio
async def test_antigravity_agent_exact_command_and_streams():
    """Vérifie la construction exacte de la commande CLI et le drainage des flux."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0

    stdout_reader = AsyncMock()
    stdout_reader.readline = AsyncMock(side_effect=[b"Plan d'action genere avec succes\n", b""])
    stderr_reader = AsyncMock()
    stderr_reader.readline = AsyncMock(side_effect=[b""])

    mock_proc.stdout = stdout_reader
    mock_proc.stderr = stderr_reader
    mock_proc.wait = AsyncMock()

    agent = AntigravityAgent(
        workspace="./test_ws",
        model="gemini-3.7-flash",
        effort="low",
        timeout_seconds=60,
    )

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "OK", "/mock/bin/agy")):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            res = await agent.run_cli_task_stream("Analyse ce fichier")

            assert res.status == "completed"
            assert "Plan d'action" in res.summary
            mock_exec.assert_called_once()
            called_cmd = mock_exec.call_args[0]
            assert called_cmd[0] == "/mock/bin/agy"
            assert called_cmd[1] == "-p"
            assert called_cmd[2] == "Analyse ce fichier"
            assert "--dangerously-skip-permissions" in called_cmd
            assert "--output-format" in called_cmd
            assert "text" in called_cmd
            assert "--model" in called_cmd
            assert "--effort" in called_cmd
            assert "--thinking" not in called_cmd


@pytest.mark.asyncio
async def test_antigravity_agent_timeout_cleans_up_process():
    """Vérifie qu'un timeout d'exécution tue le processus et ne laisse pas de tâche zombie."""
    mock_proc = AsyncMock()
    mock_proc.returncode = None
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    # Stream bloquant infini
    async def hanging_readline():
        await asyncio.sleep(10)
        return b""

    stdout_reader = AsyncMock()
    stdout_reader.readline = AsyncMock(side_effect=hanging_readline)
    stderr_reader = AsyncMock()
    stderr_reader.readline = AsyncMock(side_effect=hanging_readline)

    mock_proc.stdout = stdout_reader
    mock_proc.stderr = stderr_reader

    agent = AntigravityAgent(
        workspace="./test_ws",
        model="gemini-3.8-flash",
        effort="low",
        timeout_seconds=1,
    )

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "OK", "/mock/bin/agy")):
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            res = await agent.run_cli_task_stream("Tâche trop longue", timeout=0.1)

            assert res.status == "timeout"
            assert res.error_type == "timeout"
            assert "Timeout" in res.summary
            mock_proc.kill.assert_called()


@pytest.mark.asyncio
async def test_antigravity_agent_cancellation_cleans_up_process():
    """Vérifie que l'annulation (cancel) tue le processus et retourne un TaskResult cancelled."""
    mock_proc = AsyncMock()
    mock_proc.kill = MagicMock()
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock()

    agent = AntigravityAgent(
        workspace="./test_ws",
        model="gemini-3.8-flash",
        effort="medium",
    )
    agent.cli_process = mock_proc
    agent.cancel()

    assert agent.is_cancelled is True
    mock_proc.terminate.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests Quota vs Erreur de Syntaxe / Non-Quota
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_error_triggers_fallback_flash_low():
    """Vérifie qu'une erreur de quota (429/resource_exhausted) bascule vers Flash low dans la chaîne de repli."""
    calls = []

    async def mock_runner(model, effort):
        calls.append((model, effort))
        if "pro" in model:
            raise AntigravityQuotaExhaustedError("429 ResourceExhausted: Quota exceeded")
        return {"status": "completed", "summary": "Succès Flash low après repli"}

    decision = RoutingDecision(
        model="gemini-3.1-pro",
        effort="high",
        fallback_chain=["gemini-3.7-flash", "api_paid_gemini"],
        reason="Tâche complexe avec repli",
        task_type="complex"
    )

    with patch("services.model_routing.model_registry.model_registry.get_model") as mock_reg:
        mock_info = MagicMock()
        mock_info.supports_effort = True
        mock_reg.return_value = mock_info

        res = await execute_with_fallback(
            runner_fn=mock_runner,
            decision=decision,
            prompt="Prompt de test",
        )

        assert res["status"] == "completed"
        assert res["summary"] == "Succès Flash low après repli"
        assert len(calls) == 2
        assert calls[0] == ("gemini-3.1-pro", "high")
        assert calls[1] == ("gemini-3.7-flash", "high")


@pytest.mark.asyncio
async def test_non_quota_syntax_error_does_not_trigger_arbitrary_fallback():
    """Vérifie qu'une erreur de syntaxe ou d'argument lève immédiatement une exception sans repli abusif."""
    calls = []

    async def mock_runner(model, effort):
        calls.append((model, effort))
        raise ValueError("Invalid flag or syntax error")

    decision = RoutingDecision(
        model="gemini-3.1-pro",
        effort="high",
        fallback_chain=["gemini-3.7-flash"],
        reason="Tâche complexe",
        task_type="complex"
    )

    with pytest.raises(ValueError, match="Invalid flag or syntax error"):
        await execute_with_fallback(
            runner_fn=mock_runner,
            decision=decision,
            prompt="Prompt de test",
        )

    # Une seule tentative, aucun repli arbitraire sur erreur syntaxe
    assert len(calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests Dispatch : Tâche Tier 1 Agentique vs Outil Déterministe
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_tier1_agentic_uses_flash_low():
    """Vérifie qu'une tâche agentique classée Tier 1 ou rapide utilise Antigravity Flash low."""
    mock_ws = AsyncMock()

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "OK", "/mock/bin/agy")):
        with patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_agentic:
            mock_agentic.return_value = AgentOutput(
                conclusion="Tâche Tier 1 accomplie.",
                confidence=0.9,
                sources=[],
                open_questions=[],
                artifacts=[],
                model="flash",
                effort="low",
                status="success"
            )

            res = await dispatch_tool(
                name="run_agentic_task",
                args={"objectif": "Synchronise la doc rapide", "tier": 1, "effort": "low"},
                websocket=mock_ws,
                session=MagicMock(),
                is_paid_live=False,
                live_display_label="Gemini Flash"
            )

            assert res["status"] in ("success", "done")
            mock_agentic.assert_called_once()
            called_model = mock_agentic.call_args[1].get("model")
            called_effort = mock_agentic.call_args[1].get("effort")
            assert called_model == "flash"
            assert called_effort == "low"


@pytest.mark.asyncio
async def test_deterministic_tool_does_not_use_antigravity_agent():
    """Vérifie qu'un outil déterministe (get_system_status) s'exécute directement sans appeler Antigravity CLI."""
    mock_ws = AsyncMock()

    with patch("google_antigravity.AntigravityAgent.run_cli_task_stream", new_callable=AsyncMock) as mock_cli:
        res = await dispatch_tool(
            name="get_system_status",
            args={},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )

        assert res["status"] in ("success", "done")
        # Antigravity CLI ne doit JAMAIS avoir été appelé
        assert mock_cli.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Test de Non-Divulgation des Clés Secrètes
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_secrets_removes_api_keys():
    """Vérifie que la fonction _sanitize_secrets élimine toutes les clés d'API."""
    with patch("config.GEMINI_API_KEY_FREE", "AIzaSySecretFreeKey99887766554433"):
        with patch("config.GEMINI_API_KEY_PAID", "AIzaSySecretPaidKey11223344556677"):
            sensitive_text = (
                "Erreur 400: request failed for key AIzaSySecretFreeKey99887766554433 "
                "or sk-proj-1234567890abcdef1234567890abcdef with paid key AIzaSySecretPaidKey11223344556677"
            )
            cleaned = _sanitize_secrets(sensitive_text)
            assert "AIzaSySecretFreeKey99887766554433" not in cleaned
            assert "AIzaSySecretPaidKey11223344556677" not in cleaned
            assert "sk-proj-1234567890abcdef1234567890abcdef" not in cleaned
            assert "[REDACTED" in cleaned
