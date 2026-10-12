"""tests/unit/test_injection_no_self_interrupt.py
Tests unitaires validant l'anti-auto-interruption de J.A.R.V.I.S. :
1. Résultat d'outil arrivé pendant MODEL_SPEAKING -> non envoyé tant que playback_finished n'a pas eu lieu, envoyé >= 350 ms après.
2. Deux résultats pendant la parole -> une seule injection regroupée (coalescence).
3. INTERRUPTION pendant MODEL_SPEAKING -> passe immédiatement sans attendre.
4. Device : pacer drained -> IDLE ; sans signal -> timeout de sécurité (20s) libère la file.
5. L'utilisateur parle pendant le sas -> injection repoussée jusqu'à la fin de la parole utilisateur + sas.
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
    notify_interrupted,
    wait_until_speech_idle,
    active_task_controller,
    safe_send_live_client_content,
)
from services.voice_injection_queue import (
    VoiceInjectionQueue,
    InjectionPriority,
    voice_injection_queue,
)
from routers.device_voice import DeviceAudioPacer


@pytest.fixture(autouse=True)
def reset_state_fixture():
    """Réinitialise l'état partagé et la file d'injection avant chaque test."""
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["awaiting_tool_response"] = False
    active_task_controller["estimated_speech_end"] = 0.0
    active_task_controller["last_playback_finished_time"] = 0.0
    active_task_controller["last_turn_complete_time"] = 0.0
    active_task_controller["last_user_speaking_end_time"] = 0.0
    active_task_controller["last_audio_chunk_time"] = 0.0
    active_task_controller["sync_resolved_actions"].clear()
    voice_injection_queue.reset()
    yield
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["playback_pending"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["awaiting_tool_response"] = False
    voice_injection_queue.reset()


@pytest.mark.asyncio
async def test_tool_result_during_model_speaking_waits_for_playback_and_sas():
    """1. Résultat d'outil arrivé pendant MODEL_SPEAKING -> non envoyé tant que playback_finished n'a pas eu lieu, envoyé >=350 ms après."""
    mock_session = MagicMock()
    send_times = []

    async def fake_send_client_content(*args, **kwargs):
        send_times.append(time.time())
        return MagicMock()

    mock_session.send_client_content = AsyncMock(side_effect=fake_send_client_content)
    active_task_controller["live_session"] = mock_session

    t0 = time.time()
    # Modèle commence à parler
    notify_generation_chunk(chunk_duration=0.20)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING
    assert is_speech_idle() is False

    # Tâche simulant la fin de génération (turn_complete) à t=0.15s et fin de playback à t=0.25s
    async def simulate_playback():
        await asyncio.sleep(0.15)
        notify_turn_complete()
        await asyncio.sleep(0.10)
        notify_playback_finished()

    asyncio.create_task(simulate_playback())

    # Injection enqueued à t=0.05s pendant que le modèle parle
    await asyncio.sleep(0.05)
    enqueue_task = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="Résultat d'analyse météo terminé.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="weather_analysis",
            wait_if_speaking=True,
            drainage_delay=0.35,
            wait_for_completion=True,
        )
    )

    # Vérification à t=0.20s : le playback n'est pas fini, aucune injection ne doit avoir été envoyée
    await asyncio.sleep(0.15)
    assert len(send_times) == 0, "L'injection a été envoyée avant playback_finished !"

    # Attente de la livraison finale
    delivered = await enqueue_task
    assert delivered is True
    assert len(send_times) == 1

    # Horodatage de livraison >= playback_finished (t0 + 0.25s) + sas (0.35s) = t0 + 0.60s
    delivery_time = send_times[0] - t0
    assert delivery_time >= 0.55, f"Livraison trop précoce ({delivery_time:.3f}s < 0.55s)"


@pytest.mark.asyncio
async def test_two_results_during_speech_coalesced_into_single_injection():
    """2. Deux résultats pendant la parole -> une seule injection regroupée."""
    mock_session = MagicMock()
    delivered_texts = []

    async def fake_send(turns, turn_complete=True):
        delivered_texts.append(turns.parts[0].text)

    mock_session.send_client_content = AsyncMock(side_effect=fake_send)
    active_task_controller["live_session"] = mock_session

    # Jarvis parle
    notify_generation_chunk(chunk_duration=0.30)
    assert is_speech_idle() is False

    # Deux tâches de fond finissent pendant son élocution
    t1 = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="Recherche web terminée : 3 sources trouvées.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="search_bg_1",
            wait_if_speaking=True,
            drainage_delay=0.1,
            wait_for_completion=True,
        )
    )
    t2 = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="Génération des graphiques validée.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="charts_bg_2",
            wait_if_speaking=True,
            drainage_delay=0.1,
            wait_for_completion=True,
        )
    )

    await asyncio.sleep(0.05)
    # Jarvis termine de parler
    notify_turn_complete()
    notify_playback_finished()

    await asyncio.gather(t1, t2)

    # Doit avoir fusionné les deux résultats en un seul envoi
    assert len(delivered_texts) == 1
    merged = delivered_texts[0]
    assert "Recherche web terminée" in merged
    assert "Génération des graphiques validée" in merged


@pytest.mark.asyncio
async def test_interruption_during_model_speaking_passes_immediately():
    """3. INTERRUPTION pendant MODEL_SPEAKING -> passe immédiatement."""
    mock_session = MagicMock()
    sent_items = []

    async def fake_send(turns, turn_complete=True):
        sent_items.append((time.time(), turns.parts[0].text))

    mock_session.send_client_content = AsyncMock(side_effect=fake_send)
    active_task_controller["live_session"] = mock_session

    # Jarvis parle longuement
    notify_generation_chunk(chunk_duration=5.0)
    assert get_speech_state() == SpeechState.MODEL_SPEAKING

    t0 = time.time()
    # Interruption prioritaire (barge-in d'arrêt)
    success = await voice_injection_queue.emit_interruption(
        text="[ARRÊT D'URGENCE] Stop tout !",
        session=mock_session,
        wait_if_speaking=False,
    )

    assert success is True
    assert len(sent_items) == 1
    latency = sent_items[0][0] - t0
    # L'interruption doit passer sans délai (< 100ms)
    assert latency < 0.15, f"L'interruption a pris trop de temps ({latency:.3f}s)"
    assert "[ARRÊT D'URGENCE]" in sent_items[0][1]


@pytest.mark.asyncio
async def test_device_pacer_drained_and_safety_timeout():
    """4. Device : pacer drained -> IDLE ; sans signal -> timeout de sécurité libère la file."""
    # Partie A : Pacer régulé avec drain
    mock_ws = AsyncMock()
    pacer = DeviceAudioPacer(websocket=mock_ws, device_id="test_esp32")
    assert pacer.drained.is_set() is True

    # Pacer reçoit une trame
    await pacer.put_frame(b"\x00" * 80)
    assert pacer.drained.is_set() is False

    # Attente que le pacer vide sa file
    await pacer.wait_drained()
    assert pacer.drained.is_set() is True
    await pacer.abort()

    # Partie B : Timeout de sécurité (20s) quand aucun signal de fin n'arrive
    mock_session = MagicMock()
    mock_session.send_client_content = AsyncMock()
    active_task_controller["live_session"] = mock_session

    # Modèle a émis un chunk il y a 22 secondes et turn_complete a été appelé mais playback_pending reste True
    notify_generation_chunk(chunk_duration=1.0)
    active_task_controller["last_audio_chunk_time"] = time.time() - 22.0
    notify_turn_complete()
    assert active_task_controller.get("playback_pending") is True

    # L'appel à wait_until_speech_idle doit détecter le dépassement des 20s et forcer IDLE
    with patch("core.shared_state.logger.warning") as mock_warn:
        is_idle = await wait_until_speech_idle(timeout=1.0, sas_delay=0.01)
        assert is_idle is True
        assert get_speech_state() == SpeechState.IDLE
        mock_warn.assert_called()
        assert any("PLAYBACK_FINISHED_TIMEOUT" in str(c) for c in mock_warn.call_args_list)


@pytest.mark.asyncio
async def test_user_speaking_during_sas_postpones_injection():
    """5. L'utilisateur parle pendant le sas -> injection repoussée."""
    mock_session = MagicMock()
    send_times = []

    async def fake_send(turns, turn_complete=True):
        send_times.append(time.time())

    mock_session.send_client_content = AsyncMock(side_effect=fake_send)
    active_task_controller["live_session"] = mock_session

    # Fin de parole initiale
    notify_turn_complete()
    notify_playback_finished()
    assert is_speech_idle() is True

    t0 = time.time()
    # On enfile une injection avec sas de 0.35s
    enqueue_task = asyncio.create_task(
        voice_injection_queue.enqueue(
            text="Rapport de tâche d'arrière-plan.",
            priority=InjectionPriority.TOOL_RESPONSE,
            session=mock_session,
            action_key="bg_report",
            wait_if_speaking=True,
            drainage_delay=0.35,
            wait_for_completion=True,
        )
    )

    # À t=0.10s (pendant le sas de 0.35s), l'utilisateur prend la parole !
    await asyncio.sleep(0.10)
    notify_user_speaking(True)
    assert get_speech_state() == SpeechState.USER_SPEAKING

    # L'utilisateur parle pendant 0.20s
    await asyncio.sleep(0.20)
    assert len(send_times) == 0, "L'injection est partie pendant que l'utilisateur parlait !"

    # L'utilisateur s'arrête de parler à t=0.30s
    notify_user_speaking(False)

    # Attente que l'injection parte après le nouveau sas de 0.35s
    delivered = await enqueue_task
    assert delivered is True
    assert len(send_times) == 1

    # Temps total >= 0.10s + 0.20s + 0.35s = 0.65s
    total_elapsed = send_times[0] - t0
    assert total_elapsed >= 0.60, f"L'injection n'a pas attendu la fin de la parole utilisateur ({total_elapsed:.3f}s < 0.60s)"
