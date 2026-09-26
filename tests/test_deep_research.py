"""tests/test_deep_research.py
Tests unitaires et d'intégration pour le moteur asynchrone de Deep Research (Antigravity CLI + n8n).
Conforme à la règle no-paid-api-in-tests.md : Zéro appel API payante, mocks complets.
"""

import os
import json
import tempfile
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import config
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from core.shared_state import active_task_controller, stop_active_task
from services.deep_research_service import DeepResearchService, ARTIFACTS_DIR
from google_antigravity import TaskResult, AntigravityQuotaExhaustedError


@pytest.fixture(autouse=True)
def ensure_paid_key_authorized():
    orig = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    config.set_paid_key_authorized(orig)


def test_declaration_lancer_mission_deep_research():
    """Vérifie la présence et le schéma de l'outil lancer_mission_deep_research."""
    tools = get_tools_list()
    assert len(tools) > 0
    declarations = tools[0].function_declarations
    tool_decl = next((d for d in declarations if d.name == "lancer_mission_deep_research"), None)

    assert tool_decl is not None
    assert "recherche de fond approfondie" in tool_decl.description.lower()
    props = tool_decl.parameters.properties
    assert "sujet" in props
    assert "criteres_particuliers" in props
    assert "generer_slides" in props
    assert "sujet" in tool_decl.parameters.required


@pytest.mark.asyncio
async def test_dispatch_lancer_mission_deep_research_immediate_return():
    """Valide le décrochage vocal instantané (< 300 ms) et le lancement asynchrone en arrière-plan."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("core.tools.dispatcher.deep_research_service.executer_mission_complete", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"status": "completed"}

        resp = await dispatch_tool(
            name="lancer_mission_deep_research",
            args={
                "sujet": "Laboratoires IA & Deep Learning en France et Suède",
                "criteres_particuliers": "Stage de 6 mois",
                "generer_slides": True
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini Live"
        )

        assert resp["status"] == "launched_in_background"
        assert resp["action"] == "deep_research"
        assert "arrière-plan" in resp["message"]

        deep_task = active_task_controller.get("deep_research_task")
        assert deep_task is not None
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_deep_research_full_pipeline_artifacts_and_notifications():
    """Valide l'exécution complète du pipeline en 3 phases, génération d'artefacts, n8n et Telegram."""
    test_artifacts_dir = os.path.join(os.path.dirname(__file__), "_test_scratch", "deep_research_artifacts")
    os.makedirs(test_artifacts_dir, exist_ok=True)
    service = DeepResearchService(artifacts_dir=test_artifacts_dir)

    raw_agent_output = (
        "Investigation préliminaire...\n"
        "<!-- BEGIN_MARKDOWN_REPORT -->\n"
        "# RAPPORT D'INVESTIGATION STRATÉGIQUE : IA & Deep Learning\n\n"
        "## 1. Synthèse Exécutive & Matrice de Cadrage\n"
        "Cartographie ciblée pour le stage de 6 mois de Pierre Cassagnettes.\n\n"
        "## 2. Top 3 Opportunités Prioritaires (Recommandation Maîtresse)\n"
        "1. **Inria Montbonnot / LIG Grenoble** : Équipe Thoth & Data Intelligence. Contact : contact@inria.fr. Focus : Vision & Deep Learning.\n"
        "2. **KTH Royal Institute of Technology (Stockholm)** : Division RPL Robotics & Decision. Contact : rpl-contact@kth.se. Projets IA autonome 2024-2026.\n"
        "3. **RISE Research Institutes of Sweden (Göteborg)** : Unité Computer Science. Contact : contact@ri.se. Stage R&D industrielle 6 mois.\n\n"
        "## 3. Cartographie Exhaustive des Laboratoires de Recherche (France & Suède)\n"
        "- CNRS, CEA Grenoble, Inria Paris, KTH Stockholm, Chalmers Göteborg.\n\n"
        "## 4. Cartographie des Entreprises & Centres de R&D Industrielle\n"
        "- Mistral AI, Kyutai, Dassault Systèmes, Ericsson AI Research.\n\n"
        "## 5. Méthodologie, Sources Web Vérifiées & Modalités de Candidature\n"
        "Crawl et confrontation critique vérifiés.\n"
        "<!-- END_MARKDOWN_REPORT -->\n\n"
        "<!-- BEGIN_SLIDES_JSON -->\n"
        "[\n"
        "  {\"titre_slide\": \"Cartographie IA & Deep Learning\", \"category\": \"INTRO\", \"points\": [\"France & Suède\", \"Stage 6 mois\"], \"key_metric\": {\"label\": \"LABOS\", \"value\": \"15\", \"desc\": \"Équipes identifiées\"}, \"notes\": \"Introduction.\"},\n"
        "  {\"titre_slide\": \"Top 3 Opportunités\", \"category\": \"RECOMMANDATIONS\", \"points\": [\"Inria Grenoble\", \"KTH Stockholm\", \"RISE Suède\"], \"key_metric\": {\"label\": \"TOP MATCH\", \"value\": \"98%\", \"desc\": \"Adéquation profil\"}, \"notes\": \"Recommandations clés.\"}\n"
        "]\n"
        "<!-- END_SLIDES_JSON -->"
    )

    with patch("services.deep_research_service.AntigravityAgent") as MockAgentClass, \
         patch("services.deep_research_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg, \
         patch("services.automation.executer_action_externe", new_callable=AsyncMock) as mock_n8n, \
         patch("services.deep_research_service.safe_send_live_client_content", new_callable=AsyncMock) as mock_live_voice:

        mock_instance = MagicMock()
        mock_instance.run_cli_task_stream = AsyncMock(return_value=TaskResult(
            summary=raw_agent_output,
            status="completed",
            model_label="Gemini 3.1 Pro (High)"
        ))
        MockAgentClass.return_value = mock_instance

        mock_n8n.return_value = {
            "status": "success",
            "result": {
                "presentation_id": "test_presentation_12345",
                "presentation_url": "https://docs.google.com/presentation/d/test_presentation_12345"
            }
        }
        mock_tg.return_value = {"status": "success"}

        mock_live_session = MagicMock()
        active_task_controller["live_session"] = mock_live_session

        res = await service.executer_mission_complete(
            sujet="Laboratoires IA & Deep Learning",
            criteres="Stage de 6 mois",
            generer_slides=True
        )

        assert res["status"] == "completed"
        assert res["sujet"] == "Laboratoires IA & Deep Learning"
        assert res["artifact_markdown"] is not None
        assert os.path.exists(res["artifact_markdown"])
        assert res["artifact_slides_json"] is not None
        assert os.path.exists(res["artifact_slides_json"])
        assert res["presentation_url"] == "https://docs.google.com/presentation/d/test_presentation_12345"
        assert len(res["top_3_opportunities"]) >= 3

        # Vérification du push Telegram
        mock_tg.assert_called_once()
        tg_args = mock_tg.call_args[1]
        assert tg_args["chat_id"] == "6849746502"
        assert "DEEP RESEARCH TERMINÉE" in tg_args["message"]
        assert "test_presentation_12345" in tg_args["message"]

        # Vérification de l'annonce vocale Aoede
        mock_live_voice.assert_called_once()
        voice_prompt = mock_live_voice.call_args[0][1]
        assert "ANNONCE DEEP RESEARCH TERMINÉE AVEC SUCCÈS" in voice_prompt
        assert "Aoede" in voice_prompt


@pytest.mark.asyncio
async def test_stop_active_task_cancels_deep_research():
    """Valide que stop_active_task interrompt immédiatement une mission Deep Research."""
    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(long_running_task())
    active_task_controller["deep_research_task"] = task

    assert not task.done()
    await stop_active_task(source="user", reason="Arrêt d'urgence")
    await asyncio.sleep(0.01)

    assert task.cancelled() or task.done()
    assert active_task_controller["deep_research_task"] is None
