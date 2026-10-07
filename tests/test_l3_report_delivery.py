"""tests/test_l3_report_delivery.py
Tests unitaires et d'intégration pour la livraison du rapport Deep Research L3 (Prompt P7).
Vérifie :
1. Livraison sur PC connecté (écran / session WebSocket).
2. Livraison automatique par e-mail si PC déconnecté / absent.
3. Livraison par e-mail si explicitement demandée (envoyer_email=True).
4. Bascule de l'écran vers l'e-mail si l'affichage écran échoue.
5. Gestion robuste des pannes d'envoi d'e-mail (sans plantage, logs utiles).
6. Non-duplication des e-mails.
7. Préservation des métadonnées (sources, confiance, artefacts, détails d'erreur).
"""

import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import config
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult
from services.google_antigravity import AgentOutput


@pytest.fixture(autouse=True)
def ensure_paid_key_authorized():
    orig = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    config.set_paid_key_authorized(orig)


# ──────────────────────────────────────────────────────────────────────────────
# Tests Automator Delivery Routing (_deliver_result, screen vs email)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_automator_deliver_to_screen_when_pc_online():
    """Vérifie que l'automator ouvre le rapport à l'écran si le PC est connecté."""
    from services.gemini_web_automator import GeminiWebAutomator

    automator = GeminiWebAutomator()
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_deliver_to_screen", new_callable=AsyncMock) as mock_screen, \
         patch.object(automator, "_deliver_by_email", new_callable=AsyncMock) as mock_email:
        mock_screen.return_value = {"delivery_mode": "screen", "status": "success", "acknowledged": True}
        res = await automator._deliver_result(
            page_url="https://gemini.google.com/canvas/123",
            snapshot_path=None,
            topic="IA médicale",
            filepath_md="/tmp/report.md",
        )
        mock_screen.assert_awaited_once()
        mock_email.assert_not_awaited()
        assert res["delivery_mode"] == "screen"
        assert res["status"] == "success"


@pytest.mark.asyncio
async def test_automator_deliver_by_email_when_pc_offline():
    """Vérifie que l'automator bascule automatiquement sur l'e-mail si le PC est hors ligne."""
    from services.gemini_web_automator import GeminiWebAutomator

    automator = GeminiWebAutomator()
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch.object(automator, "_deliver_to_screen", new_callable=AsyncMock) as mock_screen, \
         patch.object(automator, "_deliver_by_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = {"delivery_mode": "email", "status": "sent", "attachment": "/tmp/report.md"}
        res = await automator._deliver_result(
            page_url="https://gemini.google.com/canvas/123",
            snapshot_path=None,
            topic="IA médicale",
            filepath_md="/tmp/report.md",
        )
        mock_screen.assert_not_awaited()
        mock_email.assert_awaited_once_with("/tmp/report.md", "IA médicale")
        assert res["delivery_mode"] == "email"
        assert res["status"] == "sent"


@pytest.mark.asyncio
async def test_automator_screen_failure_falls_back_to_email():
    """Vérifie que si l'affichage écran échoue, l'automator bascule proprement sur l'e-mail."""
    from services.gemini_web_automator import GeminiWebAutomator

    automator = GeminiWebAutomator()
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch.object(automator, "_deliver_to_screen", new_callable=AsyncMock) as mock_screen, \
         patch.object(automator, "_deliver_by_email", new_callable=AsyncMock) as mock_email:
        mock_screen.return_value = {"delivery_mode": "screen", "status": "error", "acknowledged": False, "error": "timeout"}
        mock_email.return_value = {"delivery_mode": "email", "status": "sent", "attachment": "/tmp/report.md"}

        res = await automator._deliver_result(
            page_url=None,
            snapshot_path=None,
            topic="Biotech",
            filepath_md="/tmp/report.md",
        )
        mock_screen.assert_awaited_once()
        mock_email.assert_awaited_once_with("/tmp/report.md", "Biotech")
        assert res["delivery_mode"] == "email"
        assert res["status"] == "sent"
        assert res.get("fallback_from_screen") is True


@pytest.mark.asyncio
async def test_automator_deliver_by_email_failure_handling():
    """Vérifie qu'un échec de l'envoi d'e-mail est capturé sans planter l'automator."""
    from services.gemini_web_automator import GeminiWebAutomator

    automator = GeminiWebAutomator()
    with patch("services.email_service.send_email_async", side_effect=RuntimeError("SMTP connection refused")):
        res = await automator._deliver_by_email("/tmp/nonexistent.md", "Sujet test")
        assert res["delivery_mode"] == "email"
        assert res["status"] == "error"
        assert "SMTP connection refused" in res["error"]


# ──────────────────────────────────────────────────────────────────────────────
# Tests Dispatcher L3 Delivery (Browser Path)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_browser_success_pc_online_no_extra_email():
    """Quand le browser réussit et le PC est connecté (sans demande explicite d'email), aucun e-mail supplémentaire n'est envoyé."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()
    fake_browser_res = ToolResult.done(
        user_message="Rapport L3 complet",
        evidence="gemini_deep_research",
        verified=True,
        data={
            "engine": "vps_chrome",
            "status": "completed",
            "markdown_path": "/tmp/dr_report.md",
            "delivery": {"delivery_mode": "screen", "status": "success"},
        },
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Recherche sur les batteries solides",
                "envoyer_email": False,
                "sync": True,
            },
            websocket=mock_ws,
            session=mock_session,
        )

    assert resp["status"] == "done"
    mock_send_email.assert_not_awaited()
    # Le WebSocket doit avoir reçu une annonce de fin si le PC est en ligne
    mock_ws.send_text.assert_awaited()


@pytest.mark.asyncio
async def test_dispatcher_browser_success_pc_offline_sends_email():
    """Quand le browser réussit mais le PC est hors ligne (et aucun e-mail n'a encore été envoyé), le dispatcher envoie l'e-mail."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()
    fake_browser_res = ToolResult.done(
        user_message="Rapport L3 complet",
        evidence="gemini_deep_research",
        verified=True,
        data={
            "engine": "vps_chrome",
            "status": "completed",
            "markdown_path": None,
            "delivery": None,
        },
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Recherche sur les batteries solides",
                "envoyer_email": False,
                "destinataire_email": "test@example.com",
                "sync": True,
            },
            websocket=mock_ws,
            session=mock_session,
        )

    assert resp["status"] == "done"
    mock_send_email.assert_awaited_once()
    assert mock_send_email.call_args.kwargs["to_email"] == "test@example.com"
    delivery = resp.get("delivery") or resp.get("data", {}).get("delivery")
    assert delivery["delivery_mode"] == "email"
    assert delivery["status"] == "sent"


@pytest.mark.asyncio
async def test_dispatcher_browser_no_duplicate_email_if_already_sent():
    """Vérifie que si l'automator a déjà envoyé un e-mail, le dispatcher n'en renvoie pas un second."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()
    fake_browser_res = ToolResult.done(
        user_message="Rapport L3 complet",
        evidence="gemini_deep_research",
        verified=True,
        data={
            "engine": "vps_chrome",
            "status": "completed",
            "markdown_path": "/tmp/dr_report.md",
            "delivery": {"delivery_mode": "email", "status": "sent"},
        },
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Recherche quantique",
                "envoyer_email": True,
                "sync": True,
            },
            websocket=mock_ws,
            session=mock_session,
        )

    assert resp["status"] == "done"
    mock_send_email.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────────────
# Tests Dispatcher L3 Delivery (Map-Reduce Fallback Path)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_map_reduce_success_pc_online():
    """Quand le repli Map-Reduce réussit avec PC connecté (sans email forcé), la livraison est marquée 'screen'."""
    failed_browser_res = ToolResult.failed(
        user_message="Chrome VPS indisponible",
        error_hint="vps_offline",
    )
    out_p = AgentOutput(status="success", conclusion="Données prospecteur", confidence=0.85, sources=["https://source1.com"])
    out_a = AgentOutput(status="success", conclusion="Analyse critique", confidence=0.90, sources=["https://source2.com"])
    out_s = AgentOutput(status="success", conclusion="# Synthèse finale L3\nRapport complet", confidence=0.95, artifacts=["/tmp/rapport.md"])

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=failed_browser_res), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", side_effect=[out_p, out_a, out_s]), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Étude de marché FinTech",
                "envoyer_email": False,
                "sync": True,
            },
        )

    assert resp["status"] == "done"
    delivery = resp.get("delivery") or resp.get("data", {}).get("delivery")
    assert delivery["delivery_mode"] == "screen"
    assert delivery["status"] == "success"
    sources = resp.get("sources") or resp.get("data", {}).get("sources")
    assert len(sources) == 2
    artifacts = resp.get("artifacts") or resp.get("data", {}).get("artifacts")
    assert "/tmp/rapport.md" in artifacts
    mock_email.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatcher_map_reduce_success_pc_offline_delivers_email():
    """Quand le repli Map-Reduce réussit mais le PC est hors ligne, le rapport est envoyé par e-mail."""
    failed_browser_res = ToolResult.failed(
        user_message="Chrome VPS indisponible",
        error_hint="vps_offline",
    )
    out_p = AgentOutput(status="success", conclusion="Données prospecteur", confidence=0.85, sources=["https://source1.com"])
    out_a = AgentOutput(status="success", conclusion="Analyse critique", confidence=0.90, sources=["https://source2.com"])
    out_s = AgentOutput(status="success", conclusion="# Synthèse finale L3\nRapport complet", confidence=0.92, artifacts=["/tmp/rapport.md"])

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=failed_browser_res), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", side_effect=[out_p, out_a, out_s]), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Étude de marché FinTech",
                "envoyer_email": False,
                "destinataire_email": "pierre@example.com",
                "sync": True,
            },
        )

    assert resp["status"] == "done"
    mock_email.assert_awaited_once()
    assert mock_email.call_args.kwargs["to_email"] == "pierre@example.com"
    delivery = resp.get("delivery") or resp.get("data", {}).get("delivery")
    assert delivery["delivery_mode"] == "email"
    assert delivery["status"] == "sent"


@pytest.mark.asyncio
async def test_dispatcher_map_reduce_email_failure_handled_gracefully():
    """Quand l'envoi d'e-mail échoue en fin de Map-Reduce, le rapport est quand même retourné avec statut d'erreur email dans data."""
    failed_browser_res = ToolResult.failed(
        user_message="Chrome VPS indisponible",
        error_hint="vps_offline",
    )
    out_p = AgentOutput(status="success", conclusion="Données prospecteur", confidence=0.85, sources=["https://source1.com"])
    out_a = AgentOutput(status="success", conclusion="Analyse critique", confidence=0.90, sources=["https://source2.com"])
    out_s = AgentOutput(status="success", conclusion="# Synthèse finale L3\nRapport complet", confidence=0.90, artifacts=[])

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=failed_browser_res), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", side_effect=[out_p, out_a, out_s]), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", side_effect=RuntimeError("Mail server down")):
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Étude aérospatiale",
                "sync": True,
            },
        )

    assert resp["status"] == "done"
    assert "# Synthèse finale L3\nRapport complet" in resp["user_message"]
    delivery = resp.get("delivery") or resp.get("data", {}).get("delivery")
    assert delivery["delivery_mode"] == "email"
    assert delivery["status"] == "error"
    assert "Mail server down" in delivery["error"]
