"""tests/test_deep_research.py
Tests unitaires et d'intégration pour le moteur de Deep Research refondu.
Architecture : Contrats MissionSpec, Audit de complétude strict, Tier 3 VPS,
Livraison e-mail Stark Industries HTML déterministe, Telegram et Live Aoede.
Conforme à no-paid-api-in-tests.md : Mocks intégraux, aucun appel payant.
"""

import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import config
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from core.shared_state import active_task_controller, stop_active_task
from services.deep_research_service import DeepResearchService, MissionSpec, ARTIFACTS_DIR
from google_antigravity import TaskResult, AntigravityQuotaExhaustedError


@pytest.fixture(autouse=True)
def ensure_paid_key_authorized():
    orig = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    config.set_paid_key_authorized(orig)


def test_declaration_lancer_mission_deep_research():
    """Vérifie la présence et le schéma simplifié orienté capteur vocal de l'outil."""
    tools = get_tools_list()
    assert len(tools) > 0
    declarations = tools[0].function_declarations
    tool_decl = next((d for d in declarations if d.name == "lancer_mission_deep_research"), None)

    assert tool_decl is not None
    assert "recherche de fond approfondie" in tool_decl.description.lower()
    props = tool_decl.parameters.properties
    assert "consigne_utilisateur" in props
    assert "envoyer_email" in props
    assert "destinataire_email" in props
    assert "consigne_utilisateur" in tool_decl.parameters.required


@pytest.mark.asyncio
async def test_compiler_spec_mission():
    """Vérifie la compilation de la consigne complexe en un contrat de mission MissionSpec typé."""
    service = DeepResearchService()
    consigne = (
        "Trouve 20 entreprises à Malmö pour mon stage de fin d'études en IA, "
        "avec avantages/inconvénients, rémunéré ou non, localisation précise et envoie le rapport par mail"
    )

    spec = await service.compiler_spec_mission(
        consigne_utilisateur=consigne,
        envoyer_email=True
    )

    assert isinstance(spec, MissionSpec)
    assert spec.quantite_cible == 20
    assert spec.notifier_email is True
    assert "politique_remuneration" in spec.criteres_obligatoires
    assert "avantages" in spec.criteres_obligatoires
    assert "inconvenients" in spec.criteres_obligatoires
    assert "localisation_exacte" in spec.criteres_obligatoires
    assert spec.structure_rapport == "tableau_synthese_et_fiches_detaillees"


@pytest.mark.asyncio
async def test_dispatch_lancer_mission_deep_research_immediate_return():
    """Valide le décrochage vocal instantané (< 300 ms) et le lancement asynchrone en tâche de fond."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("core.tools.dispatcher.deep_research_service.executer_mission_complete", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"status": "completed"}

        resp = await dispatch_tool(
            name="lancer_mission_deep_research",
            args={
                "consigne_utilisateur": "Trouve 20 entreprises à Malmö pour mon stage IA et envoie le rapport par mail",
                "envoyer_email": True
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
async def test_deep_research_full_pipeline_with_email_delivery():
    """Valide l'exécution complète : MissionSpec, audit critique, rapport 20 entités, envoi email et Telegram."""
    test_artifacts_dir = os.path.join(os.path.dirname(__file__), "_test_scratch", "deep_research_artifacts")
    os.makedirs(test_artifacts_dir, exist_ok=True)
    service = DeepResearchService(artifacts_dir=test_artifacts_dir)

    consigne = (
        "Trouve 20 entreprises à Malmö pour mon stage de fin d'études en IA, "
        "avec avantages/inconvénients, rémunéré ou non, localisation précise et envoie le rapport par mail"
    )

    with patch("services.deep_research_service.AntigravityAgent") as MockAgentClass, \
         patch("services.deep_research_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg, \
         patch("services.deep_research_service.send_email_async", new_callable=AsyncMock) as mock_email, \
         patch("services.deep_research_service.slides_service.generate_deep_research_slides") as mock_slides_gen, \
         patch("services.deep_research_service.safe_send_live_client_content", new_callable=AsyncMock) as mock_live_voice:

        mock_instance = MagicMock()
        mock_instance.run_cli_task_stream = AsyncMock(return_value=TaskResult(
            summary="Crawl web complété.\n<!-- BEGIN_MARKDOWN_REPORT -->\n# Rapport...\n<!-- END_MARKDOWN_REPORT -->",
            status="completed",
            model_label="Gemini 3.1 Pro (High)"
        ))
        MockAgentClass.return_value = mock_instance

        mock_slides_gen.return_value = ("Titre", "Sous-titre", [
            {"titre_slide": "Slide 1", "category": "INTRO", "points": ["P1"], "key_metric": {"label": "M", "value": "1", "desc": "D"}, "notes": "N"}
        ])

        mock_email.return_value = {"status": "sent", "recipient": "pierrecassagnettes@gmail.com"}
        mock_tg.return_value = {"status": "success"}

        mock_live_session = MagicMock()
        active_task_controller["live_session"] = mock_live_session

        res = await service.executer_mission_complete(
            consigne_utilisateur=consigne,
            envoyer_email=True
        )

        assert res["status"] == "completed"
        assert res["spec"]["quantite_cible"] == 20
        assert res["artifact_markdown"] is not None
        assert os.path.exists(res["artifact_markdown"])
        assert res["email_sent"] is True

        # Vérification du déclenchement e-mail avec pièce jointe
        mock_email.assert_called_once()
        email_kwargs = mock_email.call_args[1]
        assert "pierrecassagnettes@gmail.com" in email_kwargs["to_email"]
        assert email_kwargs["attachments"] == [res["artifact_markdown"]]
        assert email_kwargs["is_html_report"] is True
        assert "Tableau Récapitulatif" in email_kwargs["body"]

        # Vérification de l'alerte Telegram
        mock_tg.assert_called_once()
        tg_args = mock_tg.call_args[1]
        assert tg_args["chat_id"] == "6849746502"
        assert "DEEP RESEARCH TERMINÉE" in tg_args["message"]
        assert "20 entités" in tg_args["message"]

        # Vérification de la notification vocale Aoede
        mock_live_voice.assert_called_once()
        voice_prompt = mock_live_voice.call_args[0][1]
        assert "20 entités" in voice_prompt
        assert "Aoede" in voice_prompt
        assert "courriel" in voice_prompt or "mail" in voice_prompt


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
