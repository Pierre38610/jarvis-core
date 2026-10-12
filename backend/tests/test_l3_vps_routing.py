"""tests/test_l3_vps_routing.py
Tests unitaires et d'intégration pour le routage L3 autonome sur VPS (P6).

Vérifie :
1. Routage direct vers Chrome VPS (automator) comme premier chemin L3, sans dépendre du PC local.
2. Succès L3 avec PC éteint quand Chrome VPS et session Gemini sont disponibles.
3. Ordre strict des replis : Chrome VPS -> Agent local PC si disponible -> Map-Reduce Antigravity.
4. Détection propre et rapide du PC hors ligne sans retarder le repli.
5. Préservation des erreurs structurées L3ErrorDetails (P2) à chaque étape.
6. Compatibilité stricte de l'alias `run_browser_agent_task = run_browser_task`.
7. Livraison e-mail et conservation des artefacts en cas de succès VPS.
8. Non-régression des tâches browser simples non L3.
"""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import config
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult
from services.browser_agent.loop import (
    BrowserTask,
    run_browser_task,
    run_browser_agent_task,
)
from services.l3_error import (
    L3ErrorDetails,
    clear_last_l3_error,
    get_last_l3_error,
    set_last_l3_error,
)


@pytest.fixture(autouse=True)
def clean_l3_errors():
    clear_last_l3_error()
    yield
    clear_last_l3_error()


# ─── 1. Premier Chemin : Chrome VPS Réussi (PC Déconnecté) ───────────────────

@pytest.mark.asyncio
async def test_l3_routing_vps_success_when_pc_offline():
    """L3 réussit de manière 100% autonome sur Chrome VPS même avec le PC local éteint/déconnecté."""
    task = BrowserTask(
        task_id="bt_vps_first_01",
        goal="Analyse prospective des semi-conducteurs à Munich",
        recipe="gemini_deep_research",
    )

    fake_vps_res = {
        "status": "completed",
        "topic": "Analyse prospective des semi-conducteurs à Munich",
        "markdown_path": "/tmp/artifacts/report_munich.md",
        "markdown_content": "# Rapport Semi-conducteurs Munich\n\n1. Entité 1...",
        "page_url": "https://gemini.google.com/app/canvas/123",
        "duration_seconds": 45,
        "delivery": {"delivery_mode": "email", "status": "sent"},
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_res) as mock_dr, \
         patch("services.browser_agent.loop._call_rpc", new_callable=AsyncMock) as mock_rpc, \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False):

        res = await run_browser_task(task)

        # 1. Vérification du résultat ToolResult
        assert res.status == "done"
        assert res.verified is True
        assert "Rapport Semi-conducteurs Munich" in res.user_message
        assert res.data.get("engine") == "vps_chrome"
        assert res.data.get("markdown_path") == "/tmp/artifacts/report_munich.md"

        # 2. Vérification que l'automator VPS a été appelé en premier
        mock_dr.assert_awaited_once_with(
            topic="Analyse prospective des semi-conducteurs à Munich",
            task_id="bt_vps_first_01",
        )

        # 3. Vérification qu'aucun RPC vers le PC local n'a été émis
        mock_rpc.assert_not_awaited()


# ─── 2. Repli : VPS Indisponible puis Agent Local PC Réussi ──────────────────

@pytest.mark.asyncio
async def test_l3_routing_vps_fails_then_local_pc_agent_succeeds():
    """Quand Chrome VPS est indisponible, bascule sur l'agent local PC si disponible."""
    task = BrowserTask(
        task_id="bt_vps_fail_local_ok",
        goal="Recherche IA quantique",
        recipe="gemini_deep_research",
    )

    fake_vps_fail = {
        "status": "error",
        "error": "Chrome CDP VPS non joignable (port 9222)",
        "l3_error": {
            "etape": "cdp_connection",
            "exception": "Connection refused",
            "cause_courte": "Chrome CDP non joignable",
            "fallback_initiated": True,
        },
    }

    # Simulation des étapes de l'agent local PC
    async def mock_local_rpc(action: str, timeout: float = 30.0, **params):
        if action == "browser_open_task":
            return {"ok": True}
        elif action == "browser_snapshot":
            return {
                "ok": True,
                "url": "https://gemini.google.com/app",
                "text": "Rapport quantique final terminé.",
                "elements": [],
            }
        elif action == "browser_focus":
            return {"ok": True}
        elif action == "browser_act":
            return [{"action": {"type": "extract"}, "ok": True, "text": "Rapport local extrait avec succès"}]
        return {"ok": True}

    async def mock_brain_decide(*args, **kwargs):
        return {
            "thought": "Extraction finale",
            "actions": [{"type": "extract"}],
            "done": True,
            "result": "Rapport local extrait avec succès",
        }

    async def mock_brain_verify(*args, **kwargs):
        return {"ok": True, "reason": "Rapport complet extrait sur le PC local"}

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_fail), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("services.browser_agent.loop._call_rpc", side_effect=mock_local_rpc) as mock_rpc, \
         patch("services.browser_agent.cli_brain.decide", side_effect=mock_brain_decide), \
         patch("services.browser_agent.cli_brain.verify", side_effect=mock_brain_verify):

        res = await run_browser_task(task)

        assert res.status == "done"
        assert res.verified is True
        assert "Rapport complet extrait" in res.evidence or "Rapport local" in res.user_message
        # Vérifier que le RPC vers l'agent local a bien été exécuté
        assert mock_rpc.called


# ─── 3. Repli : VPS et PC Local Indisponibles puis Map-Reduce Réussi ──────────

@pytest.mark.asyncio
async def test_l3_routing_vps_and_local_offline_then_map_reduce_fallback():
    """Quand VPS et PC local sont indisponibles, le dispatcher bascule proprement vers Map-Reduce."""
    fake_vps_fail = {
        "status": "error",
        "error": "Chrome CDP non joignable",
        "l3_error": {
            "etape": "cdp_connection",
            "exception": "Connection refused",
            "cause_courte": "Chrome CDP VPS indisponible",
            "fallback_initiated": True,
        },
    }

    from services.google_antigravity import AgentOutput

    mock_p = AgentOutput(status="success", conclusion="Prospection achevée", sources=["https://s1.org"], confidence="0.9")
    mock_a = AgentOutput(status="success", conclusion="Analyse achevée", sources=["https://s1.org"], confidence="0.95")
    mock_s = AgentOutput(status="success", conclusion="Synthèse Map-Reduce finale", sources=["https://s1.org"], confidence="0.95")

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_fail), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock, side_effect=[mock_p, mock_a, mock_s]):

        resp = await dispatch_tool(
            name="browser_task",
            args={"goal": "Recherche cybersécurité", "recipe": "gemini_deep_research", "sync": True},
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "[Repli CLI]" in resp["user_message"]
        assert "Synthèse Map-Reduce finale" in resp["user_message"]
        assert resp.get("fallback_used") is True
        assert len(resp.get("phases", {})) == 3


# ─── 4. Détection Propre et Rapide du PC Hors Ligne ───────────────────────────

@pytest.mark.asyncio
async def test_l3_routing_fast_pc_offline_detection():
    """Vérifie que la détection du PC hors ligne est immédiate et produit L3ErrorDetails avec etape='local_agent_pc'."""
    task = BrowserTask(
        task_id="bt_pc_offline_fast",
        goal="Test offline fast",
        recipe="gemini_deep_research",
    )

    fake_vps_fail = {
        "status": "error",
        "error": "CDP down",
        "l3_error": {"etape": "cdp_connection", "cause_courte": "CDP inaccessible"},
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_fail), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("services.browser_agent.loop._call_rpc", new_callable=AsyncMock) as mock_rpc:

        res = await run_browser_task(task)

        assert res.status == "failed"
        assert res.error_hint == "pc_offline"
        assert task.status == "failed"
        assert task.last_error is not None
        assert task.last_error["etape"] == "local_agent_pc"
        assert "hors ligne" in task.last_error["cause_courte"].lower()

        # Aucun RPC local ne doit être tenté si le PC est hors ligne
        mock_rpc.assert_not_awaited()


# ─── 5. Conservation des Erreurs Détaillées (P2) ─────────────────────────────

@pytest.mark.asyncio
async def test_l3_error_details_preserved_in_last_error_and_result():
    """Vérifie qu'une erreur détaillée VPS (ex: session requise) est stockée et disponible pour diagnostic."""
    task = BrowserTask(
        task_id="bt_err_diag",
        goal="Test diagnostic error",
        recipe="gemini_deep_research",
    )

    fake_vps_login_needed = {
        "status": "needs_login",
        "error": "Connexion Google requise",
        "l3_error": {
            "etape": "login_required",
            "exception": "Redirected to accounts.google.com",
            "cause_courte": "Session Google expirée",
            "fallback_initiated": True,
        },
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_login_needed), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False):

        res = await run_browser_task(task)

        assert res.status == "failed"
        last_err = get_last_l3_error()
        assert last_err is not None
        assert last_err["etape"] in ("login_required", "local_agent_pc")


# ─── 6. Compatibilité de l'Alias run_browser_agent_task ───────────────────────

def test_alias_run_browser_agent_task_is_identical():
    """Vérifie que l'alias run_browser_agent_task pointe exactement sur run_browser_task."""
    assert run_browser_agent_task is run_browser_task


# ─── 7. Expédition E-mail si Demandée lors du Succès VPS ──────────────────────

@pytest.mark.asyncio
async def test_l3_email_delivery_on_vps_success():
    """Vérifie que le dispatcher déclenche l'envoi d'e-mail avec pièce jointe lors d'un succès VPS."""
    fake_vps_res = ToolResult.done(
        user_message="# Rapport Synthèse VPS\n\nContenu détaillé...",
        evidence="gemini_deep_research (VPS Chrome CDP)",
        verified=True,
        data={"markdown_path": "/tmp/downloads/report_test.md"},
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_vps_res) as mock_agent, \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:

        resp = await dispatch_tool(
            name="browser_task",
            args={
                "goal": "Recherche robotique",
                "recipe": "gemini_deep_research",
                "envoyer_email": True,
                "destinataire_email": "pierre@stark.com",
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        mock_agent.assert_awaited_once()
        mock_email.assert_awaited_once()
        email_kwargs = mock_email.await_args.kwargs
        assert email_kwargs.get("to_email") == "pierre@stark.com"
        assert "[Deep Research]" in email_kwargs.get("subject", "")
        assert email_kwargs.get("body") == "# Rapport Synthèse VPS\n\nContenu détaillé..."


# ─── 8. Préservation des Tâches Browser Simples Non-L3 ────────────────────────

@pytest.mark.asyncio
async def test_non_l3_browser_task_routes_to_local_loop():
    """Les tâches avec recipe!=gemini_deep_research continuent d'utiliser la boucle locale ordinaire."""
    task = BrowserTask(
        task_id="bt_simple_cart",
        goal="Ajouter au panier",
        recipe="cart",
        start_url="https://shop.example.com",
    )

    with patch("services.browser_agent.loop._run_local_browser_loop", new_callable=AsyncMock) as mock_local_loop, \
         patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock) as mock_automator:

        mock_local_loop.return_value = ToolResult.done(user_message="Panier validé", verified=True)

        res = await run_browser_task(task)

        assert res.status == "done"
        mock_local_loop.assert_awaited_once_with(task, notify=None)
        mock_automator.assert_not_awaited()
