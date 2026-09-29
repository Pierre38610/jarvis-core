"""tests/test_agentic_dispatcher.py
Test unitaire et d'intégration mockée pour le Hub Central d'Orchestration Agentique (AgenticDispatcher).
Conforme à la règle no-paid-api-in-tests.md : Zéro appel API payante, mocks complets.
"""

import os
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import config
from services.agentic_dispatcher import agentic_dispatcher, AgenticMissionType
from core.tools.dispatcher import dispatch_tool


@pytest.fixture(autouse=True)
def ensure_paid_key_authorized():
    orig = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    config.set_paid_key_authorized(orig)


@pytest.mark.asyncio
async def test_launch_agentic_mission_returns_immediately():
    """Valide que launch_agentic_mission démarre la tâche en arrière-plan et répond immédiatement."""
    with patch("services.agentic_dispatcher.AntigravityAgent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_cli_task_stream = AsyncMock(return_value=MagicMock(
            status="completed",
            summary="# RAPPORT TRAJET MALMÖ - KIRUNA\n\nSJ Nattåg couchette recommandé."
        ))
        MockAgent.return_value = mock_agent_instance

        res = await agentic_dispatcher.launch_agentic_mission(
            mission_type="transport_optimizer",
            goal="Comparer les trajets Malmö - Kiruna",
            context={"origine": "Malmö", "destination": "Kiruna"},
            notify_voice=False,
            notify_telegram=False
        )

        assert res["status"] == "launched_in_background"
        assert "mission_id" in res
        assert res["mission_type"] == "transport_optimizer"
        assert "instruction_to_jarvis" in res


@pytest.mark.asyncio
async def test_domain_prompt_building():
    """Valide la génération des prompts Système 2 spécialisés pour chaque domaine."""
    domains = [
        "transport_optimizer",
        "spreadsheet_modeler",
        "system_healing",
        "email_drafting",
        "book_curation",
        "morning_briefing",
        "memory_consolidation",
        "doc_sync"
    ]
    for d in domains:
        prompt, filename = agentic_dispatcher._build_domain_prompt(
            mission_type=d,
            goal=f"Objectif test pour {d}",
            context={"test_key": "test_val"}
        )
        assert len(prompt) > 50
        assert "SYSTÈME 2 - ANTIGRAVITY" in prompt
        assert filename is not None


@pytest.mark.asyncio
async def test_tool_dispatcher_rechercher_train_agentic():
    """Valide que dispatch_tool('rechercher_train') appelle rechercher_trajet avec optimiser_avec_agent=True."""
    mock_ws = AsyncMock()
    with patch("services.transport_service.transport_service.rechercher_itineraires", new_callable=AsyncMock) as mock_trajet:
        mock_trajet.return_value = {
            "status": "success",
            "country": "se",
            "primary_deep_link": "https://www.trainline.com/test",
            "best_option": {"departure_time": "18:00", "arrival_time": "09:30"},
            "agent_optimization_launched": True
        }

        res = await dispatch_tool(
            name="rechercher_train",
            args={"origine": "Malmö", "destination": "Kiruna", "date_depart": "demain", "optimiser_avec_agent": True},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )

        assert res["status"] in ("success", "done")
        assert res.get("agent_optimization_launched") is True
        mock_trajet.assert_called_once()
        assert mock_trajet.call_args[1].get("optimiser_avec_agent") is True


@pytest.mark.asyncio
async def test_tool_dispatcher_generer_fichier_tableur_agentic():
    """Valide que dispatch_tool('generer_fichier_tableur') déclenche generer_modele_tableur_avance."""
    mock_ws = AsyncMock()
    with patch("services.automation.generer_modele_tableur_avance", new_callable=AsyncMock) as mock_tableur:
        res = await dispatch_tool(
            name="generer_fichier_tableur",
            args={"nom_fichier": "budget_stark.xlsx", "modele_avance_agent": True, "description": "Modèle financier complet"},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )

        assert res["status"] in ("lance_en_arriere_plan", "started")
        assert res["nom_fichier"] == "budget_stark.xlsx"
        assert "spreadsheet_modeler" in res["engine"]


@pytest.mark.asyncio
async def test_tool_dispatcher_agentic_extensions():
    """Valide les 3 nouveaux outils agentiques : triage_et_brouillon_email, curation_livre_synthese, auto_guerison_systeme."""
    mock_ws = AsyncMock()

    # 1. triage_et_brouillon_email
    with patch("services.email_service.read_received_emails_async", new_callable=AsyncMock) as mock_read:
        mock_read.return_value = {"emails": [{"subject": "Offre R&D Inria", "from": "inria@gouv.fr", "body": "Bienvenue"}]}
        with patch("services.email_service.analyser_et_preparer_brouillon_agent", new_callable=AsyncMock):
            res_mail = await dispatch_tool(
                name="triage_et_brouillon_email",
                args={"query": "Inria", "consigne": "Accepter le stage"},
                websocket=mock_ws,
                session=MagicMock(),
                is_paid_live=False,
                live_display_label="Gemini Flash"
            )
            assert res_mail["status"] in ("lance_en_arriere_plan", "started")
            assert "Inria" in res_mail["subject"]

    # 2. curation_livre_synthese
    with patch("services.download_service.generer_synthese_lecture_agent", new_callable=AsyncMock):
        res_curation = await dispatch_tool(
            name="curation_livre_synthese",
            args={"titre_livre": "Deep Learning with Python"},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )
        assert res_curation["status"] in ("lance_en_arriere_plan", "started")
        assert res_curation["titre_livre"] == "Deep Learning with Python"

    # 3. auto_guerison_systeme
    with patch("services.agentic_dispatcher.agentic_dispatcher.launch_agentic_mission", new_callable=AsyncMock):
        res_heal = await dispatch_tool(
            name="auto_guerison_systeme",
            args={"motif": "Erreur 500 sur /ws"},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )
        assert res_heal["status"] in ("lance_en_arriere_plan", "started")
        assert "Erreur 500" in res_heal["motif"]
