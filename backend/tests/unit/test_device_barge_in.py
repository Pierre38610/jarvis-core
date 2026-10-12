"""tests/unit/test_device_barge_in.py
Validation du mécanisme de barge-in ESP32 /ws/device et de la fonction centralisée handle_user_barge_in.
Vérifie :
1. Réception d'un signal abort / barge_in pendant MODEL_SPEAKING -> pacer.abort appelé.
2. Transition immédiate vers l'état USER_SPEAKING.
3. Préservation des injections de fond non prioritaires dans VoiceInjectionQueue (non perdues, rejouées à IDLE).
4. Journalisation et qualification métrique SPEECH_CUT reason=user_barge_in source=esp32.
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
    notify_generation_chunk,
    notify_turn_complete,
    notify_playback_finished,
    notify_user_speaking,
    active_task_controller,
    handle_user_barge_in,
)
from services.voice_injection_queue import (
    VoiceInjectionQueue,
    InjectionPriority,
    voice_injection_queue,
)
from services.metrics_service import metrics_service


@pytest.fixture(autouse=True)
def reset_state():
    """Réinitialise les états globaux avant et après chaque test."""
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["estimated_speech_end"] = 0.0
    active_task_controller["last_playback_finished_time"] = 0.0
    voice_injection_queue.reset()
    metrics_service._user_barge_in_cuts = 0
    metrics_service._internal_speech_cuts = 0
    yield
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    voice_injection_queue.reset()
    metrics_service._user_barge_in_cuts = 0
    metrics_service._internal_speech_cuts = 0


@pytest.mark.asyncio
async def test_handle_user_barge_in_during_model_speaking():
    """Vérifie que l'appel de handle_user_barge_in pendant MODEL_SPEAKING coupe le pacer et passe à USER_SPEAKING."""
    # 1. Simuler Jarvis en train de parler
    notify_generation_chunk(chunk_duration=2.0)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING
    assert is_speech_idle() is False

    # 2. Mock du pacer
    mock_pacer = MagicMock()
    mock_pacer.abort = AsyncMock()
    speaking_state = {"active": True}
    out_pcm_buffer = bytearray(b"12345678")
    mock_ws = AsyncMock()

    # 3. Déclenchement du barge-in ESP32
    await handle_user_barge_in(
        session=None,
        source="esp32",
        reason="device_abort_wake_word_detected",
        pacer=mock_pacer,
        speaking_state=speaking_state,
        out_pcm_buffer=out_pcm_buffer,
        websocket=mock_ws,
        device_id="esp32_speaker_waveshare",
    )

    # 4. Vérifications
    mock_pacer.abort.assert_awaited_once()
    assert speaking_state["active"] is False
    assert len(out_pcm_buffer) == 0
    assert get_speech_state() == SpeechState.USER_SPEAKING
    assert active_task_controller["client_speaking"] is True
    assert is_speech_idle() is False

    # 5. Vérifier la métrique SPEECH_CUT
    assert metrics_service._user_barge_in_cuts >= 1


@pytest.mark.asyncio
async def test_pending_injection_preserved_during_barge_in():
    """Vérifie qu'une injection vocale non prioritaire en attente est préservée lors du barge-in et livrée après IDLE."""
    # 1. Simuler modèle en train de parler
    notify_generation_chunk(chunk_duration=1.5)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING

    mock_session = AsyncMock()

    # 2. Enfiler une injection non prioritaire
    success = await voice_injection_queue.enqueue(
        text="Rappel : votre réunion commence dans 5 minutes.",
        priority=InjectionPriority.PASSIVE_INFO,
        session=mock_session,
        drainage_delay=0.1,
    )
    assert success is True

    # 3. Interruption / barge-in de l'utilisateur sur l'ESP32
    mock_pacer = MagicMock()
    mock_pacer.abort = AsyncMock()
    await handle_user_barge_in(
        session=mock_session,
        source="esp32",
        reason="device_barge_in",
        pacer=mock_pacer,
    )

    # 4. L'état doit être USER_SPEAKING et l'injection ne doit pas encore avoir été livrée (en attente d'IDLE)
    assert get_speech_state() == SpeechState.USER_SPEAKING
    assert is_speech_idle() is False
    mock_session.send_client_content.assert_not_awaited()

    # 5. L'utilisateur termine de parler -> transition vers IDLE
    notify_user_speaking(False)
    assert get_speech_state() == SpeechState.IDLE
    assert is_speech_idle() is True

    # 6. Attendre la livraison de l'injection par le worker (après sas de respiration)
    await asyncio.sleep(0.6)
    mock_session.send_client_content.assert_awaited_once()
