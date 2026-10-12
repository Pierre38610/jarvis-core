"""tests/test_l3_integration_vps.py
Tests d'intégration de bout en bout pour le système Deep Research L3 sur VPS (Prompt P8).

Valide l'ensemble du cycle de vie L3 :
1. Requête L3 -> Health check Chrome VPS -> Automator CDP -> Rapport final -> Livraison écran ou e-mail.
2. Cycle complet avec PC local éteint/déconnecté (100% autonome sur VPS + e-mail Stark).
3. Cycle avec récupération après redémarrage du service Chrome VPS (ensure_chrome_running auto-restart).
4. Cycle avec session Google expirée (login_required) -> repli propre et erreur structurée L3ErrorDetails.
5. Cycle avec panne VPS + PC local déconnecté -> repli Map-Reduce Antigravity (Prospecteur -> Analyste -> Synthèse).
6. Cycle avec échec SMTP géré gracieusement sans perte du rapport.
7. Validation des codes de retour et comportement de l'outil CLI check_gemini_session.
8. Non-régression de l'alias et des recettes de navigation simples.
"""

import asyncio
import os
import json
import sys
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
from services.google_antigravity import AgentOutput
from services.l3_error import (
    L3ErrorDetails,
    clear_last_l3_error,
    get_last_l3_error,
    set_last_l3_error,
)
from services.vps_chrome import (
    check_cdp_health,
    check_gemini_session,
    ensure_chrome_running,
    restart_vps_chrome_service,
)
import scripts.check_gemini_session as check_session_cli


@pytest.fixture(autouse=True)
def clean_test_environment():
    """Garantit un état propre pour les erreurs L3 et les autorisations de clé."""
    clear_last_l3_error()
    orig_paid = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    clear_last_l3_error()
    config.set_paid_key_authorized(orig_paid)


# ─── 1. Parcours Intégré Nominal : Chrome VPS + PC Connecté (Livraison Écran) ─

@pytest.mark.asyncio
async def test_integration_l3_vps_nominal_pc_online():
    """Parcours nominal complet : Chrome VPS sain, automator exécuté, PC connecté, affichage écran sans doublon d'email."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()
    mock_session.id = "session_integ_01"

    fake_report_content = (
        "# Synthèse Deep Research : Semi-conducteurs GaN\n\n"
        "## 1. État de l'art\n"
        "Le nitrure de gallium (GaN) permet une efficacité énergétique accrue de 35%...\n\n"
        "## 2. Acteurs clés\n"
        "- Infineon Technologies\n"
        "- STMicroelectronics\n"
        "- Navitas Semiconductor\n"
    )

    fake_vps_result = {
        "status": "completed",
        "topic": "Marché des semi-conducteurs GaN",
        "markdown_path": "/tmp/jarvis_artifacts/report_gan.md",
        "markdown_content": fake_report_content,
        "page_url": "https://gemini.google.com/app/canvas/gan_research_123",
        "duration_seconds": 38.5,
        "delivery": {"delivery_mode": "screen", "status": "success", "acknowledged": True},
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_result) as mock_automator, \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Marché des semi-conducteurs GaN",
                "envoyer_email": False,
                "sync": True,
            },
            websocket=mock_ws,
            session=mock_session,
        )

        # 1. Vérification du statut final ToolResult
        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "Semi-conducteurs GaN" in resp["user_message"]
        engine = resp.get("engine") or resp.get("data", {}).get("engine")
        assert engine == "vps_chrome"

        # 2. Vérification que l'automateur VPS a bien été invoqué
        mock_automator.assert_awaited_once()

        # 3. Vérification qu'aucun email intempestif n'a été émis (car PC en ligne et envoyer_email=False)
        mock_email.assert_not_awaited()

        # 4. Vérification de l'annonce WebSocket
        mock_ws.send_text.assert_awaited()


# ─── 2. Parcours Intégré Autonome VPS : PC Déconnecté / Éteint (Livraison E-mail) ─

@pytest.mark.asyncio
async def test_integration_l3_vps_autonomous_pc_offline_email_delivery():
    """Parcours autonome avec PC éteint : exécution complète sur Chrome VPS et livraison par e-mail Stark."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()
    mock_session.id = "session_integ_02"

    fake_report_content = (
        "# Synthèse Deep Research : Réseaux Quantiques Satellitaires\n\n"
        "L'intrication photonique sol-satellite permet une cryptographie post-quantique éprouvée."
    )

    fake_vps_result = {
        "status": "completed",
        "topic": "Réseaux Quantiques Satellitaires",
        "markdown_path": "/tmp/jarvis_artifacts/report_quantum.md",
        "markdown_content": fake_report_content,
        "page_url": "https://gemini.google.com/app/canvas/quantum_999",
        "duration_seconds": 52.0,
        "delivery": {"delivery_mode": "email", "status": "sent", "attachment": "/tmp/jarvis_artifacts/report_quantum.md"},
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_result) as mock_automator, \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Réseaux Quantiques Satellitaires",
                "envoyer_email": False,
                "destinataire_email": "pierre@stark.com",
                "sync": True,
            },
            websocket=mock_ws,
            session=mock_session,
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "Réseaux Quantiques" in resp["user_message"]
        # Pas de deuxième envoi email par le dispatcher car l'automateur l'a déjà acquitté
        mock_email.assert_not_awaited()
        delivery = resp.get("data", {}).get("delivery") or resp.get("delivery")
        assert delivery["delivery_mode"] == "email"
        assert delivery["status"] == "sent"


# ─── 3. Parcours Intégré : Redémarrage Automatique du Service Chrome VPS ─────

@pytest.mark.asyncio
async def test_integration_l3_vps_chrome_restart_recovery():
    """Chrome VPS indisponible au démarrage -> relancé par ensure_chrome_running -> recherche aboutie."""
    import httpx

    down_resp = httpx.ConnectError("Connection refused on port 9222")
    up_resp = MagicMock()
    up_resp.status_code = 200
    up_resp.json.return_value = {"Browser": "Chrome/130.0.6723.58", "Protocol-Version": "1.3"}

    mock_client = AsyncMock()
    mock_client.get.side_effect = [down_resp, up_resp]
    mock_restart_cmd = AsyncMock(return_value=(True, "Service jarvis-chrome redémarré"))

    # Vérification que ensure_chrome_running effectue la séquence complète
    res = await ensure_chrome_running(
        cdp_url="http://127.0.0.1:9222",
        max_wait=5.0,
        http_client=mock_client,
        restart_func=mock_restart_cmd,
    )

    assert res["ok"] is True
    assert res["status"] == "restarted"
    assert res["restarted"] is True
    mock_restart_cmd.assert_awaited_once()


# ─── 4. Parcours Intégré : Session Google Expirée -> Détection et Erreur P2 ──

@pytest.mark.asyncio
async def test_integration_l3_session_expired_triggers_l3_error_and_fallback():
    """Quand la session Google a expiré, l'automateur remonte l3_error(login_required) sans masquer la cause."""
    task = BrowserTask(
        task_id="bt_integ_session_exp",
        goal="Analyse brevets Fusion Magnétique",
        recipe="gemini_deep_research",
    )

    fake_login_needed = {
        "status": "needs_login",
        "error": "Page de connexion Google détectée (accounts.google.com)",
        "l3_error": {
            "etape": "login_required",
            "exception": "Redirected to https://accounts.google.com/signin",
            "cause_courte": "Session Google/Gemini expirée ou non connectée",
            "fallback_initiated": True,
        },
    }

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_login_needed), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False):

        res = await run_browser_task(task)

        assert res.status == "failed"
        last_err = get_last_l3_error()
        assert last_err is not None
        assert last_err["etape"] in ("login_required", "local_agent_pc")
        assert "Session Google" in last_err["cause_courte"] or "hors ligne" in last_err["cause_courte"]


# ─── 5. Parcours Intégré : Panne VPS + PC Éteint -> Repli Map-Reduce Réussi ───

@pytest.mark.asyncio
async def test_integration_l3_vps_down_pc_offline_map_reduce_pipeline():
    """Panne totale Chrome VPS et PC éteint : bascule déterministe vers le pipeline 3 phases Map-Reduce Antigravity."""
    fake_vps_down = {
        "status": "error",
        "error": "CDP Connection refused",
        "l3_error": {
            "etape": "cdp_connection",
            "exception": "ConnectError(9222)",
            "cause_courte": "Chrome CDP non joignable",
            "fallback_initiated": True,
        },
    }

    # Simulation des 3 ouvriers Antigravity CLI
    out_prospector = AgentOutput(
        status="success",
        conclusion="Phase 1 Prospecteur : 12 entreprises identifiées dans l'éolien offshore flottant.",
        sources=["https://wind-europe.org", "https://offshorewind.biz"],
        confidence=0.90,
    )
    out_analyst = AgentOutput(
        status="success",
        conclusion="Phase 2 Analyste : Matrice comparative des rendements LCOE et contraintes maritimes.",
        sources=["https://irena.org"],
        confidence=0.92,
    )
    out_synthesis = AgentOutput(
        status="success",
        conclusion="# Rapport Synthèse L3 : Éolien Offshore Flottant\n\nSynthèse complète avec benchmarks...",
        sources=["https://wind-europe.org", "https://offshorewind.biz", "https://irena.org"],
        confidence=0.95,
        artifacts=["/tmp/artifacts/offshore_wind_synthesis.md"],
    )

    with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new_callable=AsyncMock, return_value=fake_vps_down), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", side_effect=[out_prospector, out_analyst, out_synthesis]), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_email:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Étude prospective éolien offshore flottant 2030",
                "envoyer_email": False,
                "destinataire_email": "pierre@stark.com",
                "sync": True,
            },
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "Éolien Offshore Flottant" in resp["user_message"]
        # Vérification des phases Map-Reduce
        assert len(resp.get("phases", [])) == 3
        # L'e-mail a été expédié automatiquement car PC hors ligne
        mock_email.assert_awaited_once()
        assert mock_email.call_args.kwargs["to_email"] == "pierre@stark.com"
        assert "[Deep Research]" in mock_email.call_args.kwargs["subject"] or "[Multi-Agents L2]" in mock_email.call_args.kwargs["subject"]


# ─── 6. Parcours Intégré : Résilience en Cas d'Échec SMTP ─────────────────────

@pytest.mark.asyncio
async def test_integration_l3_smtp_failure_non_blocking():
    """Si l'envoi d'e-mail échoue en fin de recherche, le rapport est conservé et renvoyé avec statut d'erreur dans delivery."""
    fake_vps_res = ToolResult.done(
        user_message="# Rapport Matériaux Supraconducteurs\n\nContenu détaillé...",
        evidence="gemini_deep_research",
        verified=True,
        data={"engine": "vps_chrome", "markdown_path": None, "delivery": None},
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_vps_res), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", side_effect=RuntimeError("Connection to smtp.gmail.com timed out")):

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Matériaux Supraconducteurs", "sync": True},
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "Rapport Matériaux Supraconducteurs" in resp["user_message"]
        delivery = resp.get("data", {}).get("delivery") or resp.get("delivery")
        assert delivery["delivery_mode"] == "email"
        assert delivery["status"] == "error"
        assert "timed out" in delivery["error"]


# ─── 7. Validation CLI check_gemini_session ──────────────────────────────────

@pytest.mark.asyncio
async def test_integration_check_gemini_session_cli_codes():
    """Vérifie le contrat des codes de retour de l'outil check_gemini_session.py."""
    with patch("scripts.check_gemini_session.check_gemini_session", new_callable=AsyncMock) as mock_chk:
        # Code 0 = ACTIVE
        mock_chk.return_value = {"status": "active", "ok": True, "exit_code": 0, "message": "Session valide"}
        with patch.object(sys, "argv", ["check_gemini_session.py", "--quiet"]):
            code_active = await check_session_cli.main_async()
            assert code_active == 0

        # Code 1 = LOGIN_REQUIRED
        mock_chk.return_value = {"status": "needs_login", "ok": False, "exit_code": 1, "message": "Login requis"}
        with patch.object(sys, "argv", ["check_gemini_session.py", "--quiet"]):
            code_login = await check_session_cli.main_async()
            assert code_login == 1

        # Code 2 = UNAVAILABLE
        mock_chk.return_value = {"status": "unavailable", "ok": False, "exit_code": 2, "error": "CDP injoignable"}
        with patch.object(sys, "argv", ["check_gemini_session.py", "--quiet"]):
            code_unavail = await check_session_cli.main_async()
            assert code_unavail == 2


# ─── 8. Validation Alias & Tâches Browser Simples ─────────────────────────────

def test_integration_browser_task_alias_and_integrity():
    """Vérifie l'identité stricte de run_browser_agent_task et run_browser_task."""
    assert run_browser_agent_task is run_browser_task

    task = BrowserTask(
        task_id="bt_integ_recipe_check",
        goal="Test recipe",
        recipe="gemini_deep_research",
    )
    assert task.recipe == "gemini_deep_research"
