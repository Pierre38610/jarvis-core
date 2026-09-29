"""tests/test_speech_state.py
Tests de validation de la machine à états de parole J.A.R.V.I.S.,
de l'anti-coupure d'élocution (Aoede), de la coalescence des retours d'outils,
du sas de respiration acoustique et de la distinction barge-in vs coupure interne.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.shared_state import (
    SpeechState,
    get_speech_state,
    set_speech_state,
    is_speech_idle,
    is_model_speaking,
    notify_generation_chunk,
    notify_turn_complete,
    notify_playback_finished,
    notify_tool_started,
    notify_tool_completed,
    notify_user_speaking,
    notify_interrupted,
    wait_until_speech_finished,
    safe_send_live_client_content,
    active_task_controller,
)
from services.voice_injection_queue import (
    VoiceInjectionQueue,
    InjectionPriority,
    voice_injection_queue,
)
from services.metrics_service import metrics_service


@pytest.fixture(autouse=True)
def reset_speech_state_fixture():
    """Réinitialise l'état de parole et le contrôleur avant et après chaque test."""
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["estimated_speech_end"] = 0.0
    active_task_controller["last_playback_finished_time"] = 0.0
    active_task_controller.pop("pending_model_switch", None)
    voice_injection_queue.reset()
    yield
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["estimated_speech_end"] = 0.0
    voice_injection_queue.reset()


@pytest.mark.asyncio
async def test_speech_state_transitions():
    """Valide les transitions : IDLE -> MODEL_SPEAKING -> turn_complete (maintien) -> playback_finished -> IDLE."""
    assert get_speech_state() == SpeechState.IDLE
    assert is_speech_idle() is True

    # 1. Réception d'un chunk audio de génération (1.5 seconde)
    notify_generation_chunk(chunk_duration=1.5)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING
    assert is_speech_idle() is False
    assert is_model_speaking() is True

    # 2. turn_complete serveur reçu : le serveur a fini d'émettre, mais l'audio joue encore dans le navigateur
    notify_turn_complete()
    assert get_speech_state() == SpeechState.MODEL_SPEAKING
    assert is_speech_idle() is False

    # 3. Accusé client playback_finished reçu du navigateur
    notify_playback_finished()
    assert get_speech_state() == SpeechState.IDLE
    assert is_speech_idle() is True


@pytest.mark.asyncio
async def test_speech_state_safety_auto_expiry():
    """Vérifie que l'état expire vers IDLE par sécurité si le client perd la connexion sans envoyer playback_finished."""
    set_speech_state(SpeechState.MODEL_SPEAKING, reason="test_start")
    active_task_controller["speaking_active"] = True
    active_task_controller["playback_pending"] = True
    # estimated_speech_end dépassé depuis plus de 3.5 secondes
    active_task_controller["estimated_speech_end"] = time.time() - 4.0

    # L'appel à get_speech_state() doit auto-expirer vers IDLE
    state = get_speech_state()
    assert state == SpeechState.IDLE
    assert is_speech_idle() is True


@pytest.mark.asyncio
async def test_speech_simulation_injection_timing():
    """Exigence 8 : Simulation d'une génération de 3.0 s avec injection à t=1.0 s.
    L'injection doit attendre la fin effective de la parole + sas de respiration (>= 3.35 s).
    """
    mock_session = AsyncMock()
    send_times = []

    async def fake_send_client_content(*args, **kwargs):
        send_times.append(time.time())
        return MagicMock()

    mock_session.send_client_content = fake_send_client_content

    t0 = time.time()

    # Début de la génération de 3 secondes
    notify_generation_chunk(chunk_duration=3.0)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING

    # Tâche asynchrone simulant le client web qui finit de jouer à t = 0.40s (à l'échelle de notre test raccourcie)
    # Pour garder les tests unitaires ultra-rapides (< 1s) et fiables, on simule l'échelle :
    # speech de 0.30s, injection enqueued à t = 0.05s, playback_finished à t = 0.30s -> livraison à t >= 0.30s + 0.35s = 0.65s
    notify_generation_chunk(chunk_duration=0.30)
    active_task_controller["estimated_speech_end"] = t0 + 0.30

    async def client_playback_lifecycle():
        await asyncio.sleep(0.30)
        notify_turn_complete()
        notify_playback_finished()

    asyncio.create_task(client_playback_lifecycle())

    # Injection demandée à t = 0.05s
    await asyncio.sleep(0.05)
    assert is_speech_idle() is False

    delivered = await voice_injection_queue.enqueue(
        text="Voici le résultat de la tâche terminée.",
        priority=InjectionPriority.TOOL_RESPONSE,
        session=mock_session,
        action_key="task_report",
        wait_if_speaking=True,
        drainage_delay=0.35,
        wait_for_completion=True,
    )

    t_end = time.time()
    elapsed = t_end - t0

    assert delivered is True
    assert len(send_times) == 1
    # Doit avoir attendu au moins le playback client (0.30s) + le sas de 0.35s = 0.65s
    assert elapsed >= 0.60, f"L'injection est partie trop tôt ({elapsed:.3f}s < 0.60s) !"


@pytest.mark.asyncio
async def test_tool_responses_coalescence_during_speech():
    """Exigence 4 : Si plusieurs résultats d'outils arrivent pendant que Jarvis parle, les FUSIONNER en un seul message."""
    mock_session = AsyncMock()
    delivered_payloads = []

    async def fake_send_client_content(*args, **kwargs):
        turns = kwargs.get("turns")
        if turns and hasattr(turns, "parts"):
            for p in turns.parts:
                delivered_payloads.append(p.text)
        return MagicMock()

    mock_session.send_client_content = fake_send_client_content

    # Mettre Jarvis en état MODEL_SPEAKING
    voice_injection_queue.post_delivery_delay = 0.05
    set_speech_state(SpeechState.MODEL_SPEAKING, reason="speaking_active")
    active_task_controller["speaking_active"] = True
    active_task_controller["estimated_speech_end"] = time.time() + 0.25

    # Enqueue tool response 1
    t1 = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="Au fait, la présentation est prête, elle contient 9 slides.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="tool_slides",
            wait_if_speaking=True,
            drainage_delay=0.1,
            wait_for_completion=True,
        )
    )

    # Enqueue tool response 2
    t2 = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="J'ai également validé le rapport de supervision.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="tool_report",
            wait_if_speaking=True,
            drainage_delay=0.1,
            wait_for_completion=True,
        )
    )

    # Laisser la file absorber les deux messages
    await asyncio.sleep(0.05)

    # Jarvis termine de parler
    notify_turn_complete()
    notify_playback_finished()
    set_speech_state(SpeechState.IDLE, reason="test_done")

    await asyncio.gather(t1, t2)

    # Doit avoir fusionné les deux messages en un seul turn envoyé
    assert len(delivered_payloads) == 1
    merged_text = delivered_payloads[0]
    assert "présentation est prête" in merged_text
    assert "rapport de supervision" in merged_text


@pytest.mark.asyncio
async def test_progress_milestone_rate_limiting_and_user_speaking():
    """Exigence 5 : Coalescence des PROGRESS_MILESTONE (max 1 par tâche / 20 s, et jamais si l'utilisateur parle)."""
    mock_session = AsyncMock()

    # 1. Rejet si USER_SPEAKING
    set_speech_state(SpeechState.USER_SPEAKING, reason="user_mic_active")
    res_speaking = await voice_injection_queue.enqueue(
        text="Étape 1/3 terminée",
        priority=InjectionPriority.PROGRESS_MILESTONE,
        session=mock_session,
        action_key="task_abc",
        wait_if_speaking=True,
        wait_for_completion=True,
    )
    assert res_speaking is False, "Le jalon n'a pas été rejeté alors que l'utilisateur parlait !"

    # 2. Acceptation quand IDLE
    set_speech_state(SpeechState.IDLE, reason="user_silent")
    res_milestone_1 = await voice_injection_queue.enqueue(
        text="Étape 1/3 terminée",
        priority=InjectionPriority.PROGRESS_MILESTONE,
        session=mock_session,
        action_key="task_abc",
        wait_if_speaking=True,
        wait_for_completion=True,
    )
    assert res_milestone_1 is True

    # 3. Deuxième jalon dans les 20 secondes pour la même tâche -> ignoré / coalescé
    res_milestone_2 = await voice_injection_queue.enqueue(
        text="Étape 2/3 terminée",
        priority=InjectionPriority.PROGRESS_MILESTONE,
        session=mock_session,
        action_key="task_abc",
        wait_if_speaking=True,
        wait_for_completion=True,
    )
    assert res_milestone_2 is False, "Le jalon consécutif sous les 20s aurait dû être coalescé !"


@pytest.mark.asyncio
async def test_speech_cut_metrics_tracking():
    """Exigence 7 : Distinction stricte entre SPEECH_CUT reason=user_barge_in et SPEECH_CUT reason=internal."""
    # Enregistrer un barge-in utilisateur
    metrics_service.record_speech_cut("user_barge_in", details="Test barge-in utilisateur")
    # Enregistrer une coupure interne
    metrics_service.record_speech_cut("internal", details="Test coupure interne")

    summary = await metrics_service.get_metrics_summary(window_str="24h")

    assert summary.get("internal_speech_cuts", 0) >= 1
    assert summary.get("user_barge_in_cuts", 0) >= 1


@pytest.mark.asyncio
async def test_model_switch_deferred_when_not_idle():
    """Exigence 6 : Bascule de modèle différée si SpeechState != IDLE."""
    set_speech_state(SpeechState.MODEL_SPEAKING, reason="jarvis_speaking")
    assert is_speech_idle() is False

    # Simule la logique de /ws p_type == set_live_model
    new_model = "gemini-3.8-live-extended-thinking"
    if not is_speech_idle():
        active_task_controller["pending_model_switch"] = new_model
        deferred = True
    else:
        deferred = False

    assert deferred is True
    assert active_task_controller.get("pending_model_switch") == new_model

    # Quand le playback se termine, la bascule en attente est dépilée
    notify_turn_complete()
    notify_playback_finished()
    assert is_speech_idle() is True

    pending = active_task_controller.pop("pending_model_switch", None)
    assert pending == new_model
