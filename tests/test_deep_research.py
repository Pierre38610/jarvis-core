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
    tool_decl = next((d for d in declarations if d.name in ("lancer_mission_deep_research", "launch_deep_research")), None)

    assert tool_decl is not None
    assert "recherche de fond" in tool_decl.description.lower()
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
    """Valide le décrochage vocal instantané (< 300 ms) et le lancement asynchrone lorsque le CLI est opérationnel."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "Antigravity CLI opérationnel", "/home/opc/.local/bin/agy")), \
         patch("core.tools.dispatcher.deep_research_service.executer_mission_complete", new_callable=AsyncMock) as mock_exec:
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

        assert resp["status"] in ("launched_in_background", "started")
        assert resp["action"] == "deep_research"
        assert "arrière-plan" in resp["message"] or "arrière-plan" in resp.get("user_message", "")

        deep_task = active_task_controller.get("deep_research_task")
        assert deep_task is not None
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_dispatch_lancer_mission_deep_research_fails_robustly_if_cli_unavailable():
    """Vérifie que la mission deep research n'est JAMAIS déclarée lancée si Antigravity CLI n'est pas opérationnel."""
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(False, "Binaire 'agy' introuvable", None)):
        resp = await dispatch_tool(
            name="lancer_mission_deep_research",
            args={
                "consigne_utilisateur": "Prospection à Munich",
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini Live"
        )

        assert resp["status"] in ("error", "failed")
        assert resp.get("error") == "Antigravity CLI indisponible" or "Antigravity" in str(resp.get("error_hint", ""))
        assert "Ne prétends SURTOUT PAS" in resp.get("instruction_to_jarvis", "") or "indisponible" in str(resp.get("user_message", "")).lower()


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

        # Vérification des jalons vocaux intermédiaires et de la livraison finale
        assert mock_live_voice.call_count == 5
        prompts = [call[0][1] for call in mock_live_voice.call_args_list]
        assert any("SPÉCIFICATION" in p for p in prompts)
        assert any("MAP" in p for p in prompts)
        assert any("REDUCE" in p for p in prompts)
        assert any("QUALITY GATE" in p for p in prompts)

        final_prompt = prompts[-1]
        assert "20 entités" in final_prompt
        assert "Aoede" in final_prompt
        assert "courriel" in final_prompt or "mail" in final_prompt


@pytest.mark.asyncio
async def test_deep_research_quality_gate_failure_explicitly_reported():
    """Valide que si le Quality Gate échoue après ses 2 itérations de relance,
    le livrable final (vocal + rapport écrit) signale explicitement que la cible n'a pas été
    pleinement atteinte, plutôt que de livrer silencieusement un résultat partiel comme complet."""
    test_artifacts_dir = os.path.join(os.path.dirname(__file__), "_test_scratch", "deep_research_qg_failure")
    os.makedirs(test_artifacts_dir, exist_ok=True)
    service = DeepResearchService(artifacts_dir=test_artifacts_dir)

    consigne = "Trouve 20 entreprises à Malmö pour mon stage IA"

    from services.deep_research_service import NormalizedEntity

    # On simule un ouvrier qui ne retourne qu'une seule entité conforme malgré les relances
    entities_partielles = [
        NormalizedEntity(
            nom="Malmö Autonomous Systems",
            localisation_exacte="Västra Hamnen, Malmö",
            description_activite="IA appliquée et robotique de pointe",
            politique_remuneration="Oui (Rémunéré standard)",
            avantages="Équipe d'élite",
            inconvenients="Rythme soutenu",
            contact="careers@malmoauto.se",
            source_worker="Ouvrier 1",
            domaine_expertise="IA"
        )
    ]

    with patch.object(service, "_executer_ouvrier_map", new_callable=AsyncMock) as mock_worker, \
         patch("services.deep_research_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg, \
         patch("services.deep_research_service.send_email_async", new_callable=AsyncMock) as mock_email, \
         patch("services.deep_research_service.slides_service.generate_deep_research_slides") as mock_slides_gen, \
         patch("services.deep_research_service.safe_send_live_client_content", new_callable=AsyncMock) as mock_live_voice:

        mock_worker.return_value = entities_partielles
        mock_slides_gen.return_value = ("Titre", "Sous-titre", [])
        mock_live_session = MagicMock()
        active_task_controller["live_session"] = mock_live_session

        res = await service.executer_mission_complete(
            consigne_utilisateur=consigne,
            envoyer_email=True
        )

        # 1. Vérification du statut de non-complétude explicite
        assert res["status"] == "completed"
        assert res["quality_gate_passed"] is False
        assert res["target_fully_reached"] is False
        assert len(res["motifs_rejet"]) > 0

        # 2. Vérification du rapport écrit : présence du bandeau d'alerte Quality Gate
        with open(res["artifact_markdown"], "r", encoding="utf-8") as f:
            md_content = f.read()
        assert "AVERTISSEMENT DU CONTRÔLE QUALITÉ" in md_content
        assert "CIBLE NON PLEINEMENT ATTEINTE" in md_content
        assert "Cible non pleinement atteinte" in md_content

        # 3. Vérification de la restitution vocale Aoede : consigne explicite d'alerte
        prompts = [call[0][1] for call in mock_live_voice.call_args_list]
        final_prompt = prompts[-1]
        assert "CIBLE NON PLEINEMENT ATTEINTE" in final_prompt
        assert "pas pleinement atteinte" in final_prompt

        # 4. Vérification de l'alerte Telegram
        assert any("CIBLE NON PLEINEMENT ATTEINTE" in call[1]["message"] for call in mock_tg.call_args_list)

        # 5. Vérification de l'objet de l'e-mail
        assert any("Cible partielle" in call[1]["subject"] for call in mock_email.call_args_list)



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


@pytest.mark.asyncio
async def test_geographic_override_strict_sao_paulo():
    """Vérifie l'override géographique absolu : zéro contamination mémoire (Grenoble/Paris/Suède) pour São Paulo."""
    test_artifacts_dir = os.path.join(os.path.dirname(__file__), "_test_scratch", "deep_research_artifacts_sp")
    os.makedirs(test_artifacts_dir, exist_ok=True)
    service = DeepResearchService(artifacts_dir=test_artifacts_dir)

    consigne = (
        "Trouve 20 entreprises à São Paulo, Brésil pour mon stage de fin d'études en IA, "
        "avec politique de rémunération, avantages, inconvénients, localisation exacte et contact"
    )

    with patch("services.deep_research_service.AntigravityAgent") as MockAgentClass, \
         patch("services.deep_research_service.briefing_service.send_telegram_alert", new_callable=AsyncMock), \
         patch("services.deep_research_service.send_email_async", new_callable=AsyncMock), \
         patch("services.deep_research_service.slides_service.generate_deep_research_slides") as mock_slides_gen, \
         patch("services.deep_research_service.safe_send_live_client_content", new_callable=AsyncMock):

        mock_instance = MagicMock()
        mock_instance.run_cli_task_stream = AsyncMock(return_value=TaskResult(
            summary="Crawl web complété.\n<!-- BEGIN_MARKDOWN_REPORT -->\n# Rapport...\n<!-- END_MARKDOWN_REPORT -->",
            status="completed",
            model_label="Gemini 3.1 Pro (High)"
        ))
        MockAgentClass.return_value = mock_instance
        mock_slides_gen.return_value = ("Titre", "Sous-titre", [{"titre_slide": "S1"}])

        res = await service.executer_mission_complete(
            consigne_utilisateur=consigne,
            envoyer_email=False
        )

        assert res["status"] == "completed"
        assert res["spec"]["quantite_cible"] == 20
        assert "São Paulo" in res["spec"]["zone_geographique_stricte"]

        # Vérification des exclusions mémoire calculées
        exclusions = res["spec"]["exclusion_geographique"]
        assert "Grenoble" in exclusions
        assert "Paris" in exclusions
        assert "France" in exclusions
        assert "Stockholm" in exclusions
        assert "Suède" in exclusions

        # Vérification du livrable Markdown
        with open(res["artifact_markdown"], "r", encoding="utf-8") as f:
            md_content = f.read()

        # RÈGLE D'OR : ZÉRO CONTAMINATION MÉMOIRE DANS LES ENTITÉS DU RAPPORT
        assert "| 20 |" in md_content
        assert "### 20." in md_content
        fiches_section = md_content.split("## 2. Tableau Récapitulatif")[1].split("## 5. Méthodologie")[0]

        for forbidden in ["Grenoble", "Paris", "Lyon", "Stockholm", "Malmö", "France", "Suède"]:
            assert forbidden.lower() not in fiches_section.lower()

        assert "são paulo" in fiches_section.lower() or "brésil" in fiches_section.lower()


@pytest.mark.asyncio
async def test_quality_gate_closed_loop_and_criteria_completeness():
    """Valide l'audit qualité fermé (rejet des fiches hors zone / incomplètes et complétude à 100%)."""
    service = DeepResearchService()
    spec = MissionSpec(
        sujet="Cybersécurité & IA",
        quantite_cible=5,
        zone_geographique_stricte="Munich, Allemagne",
        exclusion_geographique=["Grenoble", "Paris", "France", "Stockholm", "Suède"],
        criteres_obligatoires=["description_activite", "politique_remuneration", "avantages", "inconvenients", "localisation_exacte", "contact"]
    )

    from services.deep_research_service import NormalizedEntity

    # Échantillon avec une entité hors zone (Paris), une entité incomplète (sans salaire), et des valides
    entities_sample = [
        NormalizedEntity(nom="Munich AI Lab", localisation_exacte="Maxvorstadt, Munich, Allemagne", description_activite="Recherche IA", politique_remuneration="Oui (2200 €)", avantages="Top", inconvenients="Sélectif", contact="hr@munich.de"),
        NormalizedEntity(nom="Paris Rogue Entity", localisation_exacte="Paris, France", description_activite="Hors zone", politique_remuneration="Oui", avantages="A", inconvenients="B", contact="c@p.fr"),
        NormalizedEntity(nom="Incomplete Munich Entity", localisation_exacte="Schwabing, Munich, Allemagne", description_activite="Tech", politique_remuneration="N/A", avantages="A", inconvenients="B", contact="c@m.de"),
        NormalizedEntity(nom="Siemens Munich Tech", localisation_exacte="Garching, Munich, Allemagne", description_activite="Applied AI", politique_remuneration="Oui (2000 €)", avantages="Moyens", inconvenients="Grand groupe", contact="jobs@siemens.de")
    ]

    est_conforme, valides, motifs = service._auditer_qualite(entities_sample, spec)
    assert est_conforme is False
    assert len(valides) == 2  # Seules les 2 entités valides et conformes sont retenues
    assert any("Paris" in m for m in motifs)
    assert any("politique_remuneration" in m for m in motifs)
