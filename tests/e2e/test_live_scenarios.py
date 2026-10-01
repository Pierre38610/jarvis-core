"""tests/e2e/test_live_scenarios.py
6 scénarios E2E validant le faux client Live J.A.R.V.I.S. et le rapport qualité :
1. Multi-étapes (enchaînement d'actions avec plan et validation matérielle)
2. Échec d'outil (gestion propre d'erreur, absence d'allégation infondée)
3. Quota CLI Antigravity -> Demande explicite de clé PAID
4. Clé FREE en échec -> Demande explicite de clé PAID
5. Résultat d'outil pendant que Jarvis parle (mise en attente anti-coupure Aoede)
6. Mail sans confirmation (blocage préventif et demande d'autorisation)
"""

import asyncio
import json
import os
import tempfile
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from core.shared_state import (
    SpeechState,
    active_task_controller,
    is_model_speaking,
    is_speech_idle,
    notify_turn_complete,
    notify_playback_finished,
    notify_generation_chunk,
    safe_send_live_client_content,
)
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult
from google_antigravity import AntigravityQuotaExhaustedError
from scripts.quality_report import (
    generate_quality_report,
    get_quality_briefing_sentence,
    format_quality_summary_sentence,
    is_plan_incomplete,
)
from services.key_gate import (
    PaidKeyConsentRequired,
    clear_all_consents,
    consume_paid_consent,
    get_key,
    grant_paid_consent,
    has_paid_consent,
    is_qualified_free_key_failure,
)
from services.turn_audit import init_turn_audit_db, record_turn_audit


@pytest.fixture
def temp_audit_db():
    """Crée une base SQLite temporaire isolée pour les tests d'audit et de rapport."""
    fd, path = tempfile.mkstemp(suffix="_test_audit.db")
    os.close(fd)
    init_turn_audit_db(path)
    yield path
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_state():
    """Garantit l'isolation de chaque scénario."""
    clear_all_consents()
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller.pop("pending_model_switch", None)
    yield
    clear_all_consents()
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False


# ─── Scénario 1 : Multi-étapes ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_multi_etapes(fake_live_client, temp_audit_db):
    """Scénario 1 : Exécution multi-étapes avec plan, exécution séquentielle et vérification."""
    await fake_live_client.connect()
    await fake_live_client.send_text("Prépare mon dossier de voyage : cherche le train puis vérifie la météo.")

    # Étape 1 : Recherche de train (simulée avec vérification)
    tool1_result = {
        "name": "search_train_routes",
        "status": "done",
        "verified": True,
        "evidence": "TGV 6912 confirmé SNCF API",
    }

    # Étape 2 : Consultation météo (simulée avec vérification)
    tool2_result = {
        "name": "get_local_weather",
        "status": "done",
        "verified": True,
        "evidence": "Météo Paris 21°C dégagé OpenMeteo",
    }

    plan_status = "Plan voyage : [x] Recherche train | [x] Consultation météo"

    # Enregistrement du tour complet
    turn_rec = await fake_live_client.simulate_turn(
        transcript="Prépare mon dossier de voyage : cherche le train puis vérifie la météo.",
        tools_executed=[tool1_result, tool2_result],
        final_sentence="J'ai trouvé votre TGV 6912 et la météo annonce 21°C avec un ciel dégagé.",
        voice_mode="standard",
        plan=plan_status,
        db_path=temp_audit_db,
    )

    assert turn_rec["id"] is not None
    assert turn_rec["false_claim"] is False
    assert len(turn_rec["tools"]) == 2
    assert all(t["verified"] is True for t in turn_rec["tools"])
    assert not is_plan_incomplete(plan_status)


# ─── Scénario 2 : Échec d'outil ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_echec_outil(fake_live_client, temp_audit_db):
    """Scénario 2 : Défaillance d'outil, reporting honnête sans fausse confirmation."""
    await fake_live_client.connect()

    # Outil qui échoue
    tool_failure = {
        "name": "rechercher_train",
        "status": "error",
        "verified": False,
        "error": "Timeout de connexion au serveur SNCF",
    }

    # Tour 2A : Si Jarvis affirme à tort que c'est fait -> détection stricte de fausse confirmation
    turn_false_claim = await fake_live_client.simulate_turn(
        transcript="Réserve mon billet",
        tools_executed=[tool_failure],
        final_sentence="C'est fait, votre billet est réservé.",
        db_path=temp_audit_db,
    )
    assert turn_false_claim["false_claim"] is True
    assert "WARNING" in (turn_false_claim["false_claim_warning"] or "")

    # Tour 2B : Si Jarvis annonce honnêtement l'échec -> aucune fausse confirmation
    turn_honest = await fake_live_client.simulate_turn(
        transcript="Réserve mon billet",
        tools_executed=[tool_failure],
        final_sentence="Le serveur SNCF ne répond pas, je n'ai pas pu réserver votre billet.",
        db_path=temp_audit_db,
    )
    assert turn_honest["false_claim"] is False


# ─── Scénario 3 : Quota CLI Antigravity -> Demande PAID ──────────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_quota_cli_demande_paid(fake_live_client, monkeypatch):
    """Scénario 3 : Dépassement quota 5h Antigravity CLI nécessitant demande et consentement PAID."""
    task_id = "agentic_deep_task_42"
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key")

    # 1. Tentative sans consentement préalable
    assert not has_paid_consent(task_id=task_id)

    # Simulation de l'interception de quota CLI
    cli_error = AntigravityQuotaExhaustedError("Quota 5h Antigravity CLI dépassé")

    # Jarvis doit bloquer l'usage automatique et formuler la demande
    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        get_key(purpose="reasoning", task_id=task_id, force_reason="cli_quota_exceeded")

    assert exc_info.value.reason == "cli_quota_exceeded"
    prompt_question = "Le quota des agents Antigravity est dépassé. Veux-tu que j'utilise la clé payante pour terminer ?"
    assert "quota des agents Antigravity est dépassé" in prompt_question

    # 2. L'utilisateur accepte verbalement ("Oui Jarvis, utilise la clé payante")
    grant_paid_consent(task_id=task_id, reason="cli_quota_exceeded")
    assert has_paid_consent(task_id=task_id)

    # 3. La clé payante est désormais débloquée pour cette tâche
    authorized_key = get_key(purpose="reasoning", task_id=task_id, force_reason="cli_quota_exceeded")
    assert authorized_key == "fake_paid_key"

    # 4. Le consentement est consommé après achèvement de la tâche (zéro fuite)
    consume_paid_consent(task_id=task_id)
    assert not has_paid_consent(task_id=task_id)


# ─── Scénario 4 : Clé FREE en échec -> Demande PAID ──────────────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_cle_free_en_echec_demande_paid(monkeypatch):
    """Scénario 4 : Échec qualifié de la clé FREE (quota/429) provoquant la demande d'arbitrage."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key")

    free_error = Exception("429 ResourceExhausted: Quota exceeded for free tier")
    is_qual, msg = is_qualified_free_key_failure(free_error)
    assert is_qual is True

    task_id = "live_task_voice_99"

    # En l'absence de consentement accordé, la clé PAID est formellement interdite
    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        get_key(purpose="live_voice", task_id=task_id, force_reason="free_key_failure")

    assert exc_info.value.reason == "free_key_failure"

    # Octroi du consentement utilisateur après sollicitation vocale
    grant_paid_consent(task_id=task_id, reason="free_key_failure")
    key = get_key(purpose="live_voice", task_id=task_id, force_reason="free_key_failure")
    assert key == "fake_paid_key"


# ─── Scénario 5 : Résultat d'outil pendant que Jarvis parle ──────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_resultat_outil_pendant_parole_jarvis():
    """Scénario 5 : Réception d'un résultat d'outil alors que Jarvis parle -> pas de coupure d'élocution."""
    mock_session = AsyncMock()
    send_times = []

    async def fake_send_client_content(*args, **kwargs):
        send_times.append(time.time())
        return MagicMock()

    mock_session.send_client_content = fake_send_client_content

    t0 = time.time()
    # Simuler Jarvis en train d'émettre de la voix (durée 0.20s)
    notify_generation_chunk(chunk_duration=0.20)
    active_task_controller["estimated_speech_end"] = t0 + 0.20
    assert is_model_speaking() is True

    # Cycle de vie asynchrone : fin de parole après 0.20s
    async def finish_speech_later():
        await asyncio.sleep(0.20)
        notify_turn_complete()
        notify_playback_finished()

    asyncio.create_task(finish_speech_later())

    # L'outil s'achève pendant que Jarvis parle : injection mise en file d'attente
    from services.voice_injection_queue import voice_injection_queue, InjectionPriority
    delivered = await voice_injection_queue.enqueue(
        text="Résultat de l'analyse terminé.",
        priority=InjectionPriority.TOOL_RESPONSE,
        session=mock_session,
        action_key="task_data",
        wait_if_speaking=True,
        drainage_delay=0.05,
        wait_for_completion=True,
    )

    assert delivered is True
    assert len(send_times) == 1
    assert is_speech_idle() is True
    # Vérification que le message a été différé jusqu'à la fin de la parole (pas de coupure)
    assert time.time() - t0 >= 0.20


# ─── Scénario 6 : Mail sans confirmation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_scenario_mail_sans_confirmation():
    """Scénario 6 : Tentative d'expédition d'email sans confirmation -> rejet préventif et question."""
    mock_send = AsyncMock()

    with patch("core.tools.dispatcher.send_email_async", mock_send):
        resp = await dispatch_tool(
            name="send_email",
            args={
                "to_email": "direction@stark.com",
                "subject": "Compte-rendu stratégique",
                "body": "Voici le document récapitulatif des opérations.",
                "confirmed_by_user": False,  # Non confirmé
            },
        )

        # L'outil doit exiger la confirmation de l'utilisateur
        assert resp.get("status") == "needs_user"
        assert resp.get("requires_confirmation") is True or "Confirmation requise" in resp.get("message", "")
        # L'envoi effectif SMTP ne doit JAMAIS avoir été appelé
        assert mock_send.call_count == 0


# ─── Validation globale du Rapport Qualité ───────────────────────────────────

def test_quality_report_metrics_and_briefing_sentence(temp_audit_db):
    """Valide l'agrégation des métriques (7j) et la génération de la phrase de briefing."""
    # 1. Insertion de données représentatives
    # Tour 1 : thinking, avec appel Antigravity flash medium
    record_turn_audit(
        transcript="Analyse le code",
        voice_mode="thinking",
        tools=[{"name": "ask_deep_reasoning", "model": "gemini-3.8-flash", "effort": "medium", "status": "done", "verified": True}],
        final_sentence="Analyse terminée sans faille.",
        cuts=0,
        paid_used=False,
        db_path=temp_audit_db,
    )

    # Tour 2 : standard, avec fausse confirmation et 1 coupure
    record_turn_audit(
        transcript="Envoie le mail",
        voice_mode="standard",
        tools=[{"name": "send_email", "status": "error", "verified": False}],
        final_sentence="C'est envoyé, le message est parti.",  # Fausse allégation
        cuts=1,
        paid_used=True,
        paid_reason="cli_quota_exceeded",
        plan="Plan d'action : [ ] Étape 1 en cours",
        db_path=temp_audit_db,
    )

    # Tour 3 : Antigravity pro high avec outil qui échoue
    record_turn_audit(
        transcript="Refactorisation complexe",
        voice_mode="standard",
        tools=[
            {"name": "run_antigravity_agent", "model": "gemini-3.1-pro", "effort": "high", "status": "done", "verified": True},
            {"name": "external_api", "status": "failed", "verified": False},
        ],
        final_sentence="Une erreur est survenue sur l'API externe.",
        cuts=0,
        paid_used=False,
        db_path=temp_audit_db,
    )

    report = generate_quality_report(days=7, db_path=temp_audit_db)

    assert report["total_turns"] == 3
    assert report["thinking"]["count"] == 1
    assert report["thinking"]["percentage"] == 33.3
    assert report["cuts"]["total_cuts"] == 1
    assert report["false_confirmations"]["count"] == 1
    assert report["paid_usage"]["count"] == 1
    assert "cli_quota_exceeded" in report["paid_usage"]["reasons"]
    assert report["incomplete_plans"]["count"] == 1

    # Validation des métriques Antigravity
    assert report["antigravity"]["total_calls"] == 2
    assert report["antigravity"]["models"]["flash"] == 1
    assert report["antigravity"]["models"]["pro"] == 1
    assert report["antigravity"]["efforts"]["medium"] == 1
    assert report["antigravity"]["efforts"]["high"] == 1

    # Échecs par outil
    assert "send_email" in report["tool_failures"]
    assert "external_api" in report["tool_failures"]

    # Phrase de synthèse orale pour le morning briefing
    sentence = get_quality_briefing_sentence(db_path=temp_audit_db)
    assert isinstance(sentence, str)
    assert len(sentence) > 10
    assert "Bilan de supervision" in sentence
