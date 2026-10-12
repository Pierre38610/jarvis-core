"""tests/unit/test_voice_injection_queue.py
Tests unitaires pour la file d'injection vocale prioritaire FIFO (VoiceInjectionQueue).
Vérifie :
1. L'ordonnancement strict par priorités (INTERRUPTION > TOOL_RESPONSE > PROGRESS_MILESTONE > PASSIVE_INFO).
2. L'ordre FIFO déterministe pour des messages de même priorité.
3. Le respect de la règle d'or de canal unique (suppression des doublons).
4. Le respect du verrou d'élocution (wait_until_speech_finished).
5. La purge immédiate de la file lors d'un arrêt d'urgence.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.voice_injection_queue import (
    VoiceInjectionQueue,
    InjectionPriority,
    voice_injection_queue
)
from core.shared_state import (
    active_task_controller,
    mark_action_sync_completed,
    safe_send_live_client_content
)
import config


@pytest.mark.asyncio
async def test_priority_ordering_preemption():
    """Valide que les priorités supérieures doublent les priorités inférieures dans l'ordre d'émission."""
    queue = VoiceInjectionQueue(post_delivery_delay=0.01)
    mock_session = MagicMock()
    delivered_order = []

    async def fake_send_client_content(turns, turn_complete=True):
        text = turns.parts[0].text
        delivered_order.append(text)

    mock_session.send_client_content = AsyncMock(side_effect=fake_send_client_content)
    active_task_controller["live_session"] = mock_session
    active_task_controller["speaking_active"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["estimated_speech_end"] = 0.0

    # On enfile dans un ordre mélangé
    # 1. Passive info (P4)
    # 2. Progress milestone (P3)
    # 3. Interruption (P1)
    # 4. Tool response (P2)
    await queue.enqueue("Message Passif", priority=InjectionPriority.PASSIVE_INFO, wait_if_speaking=False)
    await queue.enqueue("Jalon Intermédiaire", priority=InjectionPriority.PROGRESS_MILESTONE, wait_if_speaking=False)
    await queue.enqueue("Arrêt d'urgence !", priority=InjectionPriority.INTERRUPTION, wait_if_speaking=False)
    await queue.enqueue("Résultat Outil", priority=InjectionPriority.TOOL_RESPONSE, wait_if_speaking=False)

    # Attente que le worker traite tous les messages via join
    await queue._queue.join()

    assert len(delivered_order) == 4
    # Ordre attendu : INTERRUPTION (1), TOOL_RESPONSE (2), PROGRESS_MILESTONE (3), PASSIVE_INFO (4)
    assert delivered_order[0] == "Arrêt d'urgence !"
    assert delivered_order[1] == "Résultat Outil"
    assert delivered_order[2] == "Jalon Intermédiaire"
    assert delivered_order[3] == "Message Passif"


@pytest.mark.asyncio
async def test_fifo_ordering_within_same_priority():
    """Valide l'ordre FIFO strict entre éléments de même priorité."""
    queue = VoiceInjectionQueue(post_delivery_delay=0.01)
    mock_session = MagicMock()
    delivered_order = []

    async def fake_send(turns, turn_complete=True):
        delivered_order.append(turns.parts[0].text)

    mock_session.send_client_content = AsyncMock(side_effect=fake_send)
    active_task_controller["live_session"] = mock_session
    active_task_controller["speaking_active"] = False
    active_task_controller["client_speaking"] = False
    active_task_controller["estimated_speech_end"] = 0.0

    # Enfilage de 3 jalons de progression (tous P3)
    await queue.enqueue("Jalon 1", priority=InjectionPriority.PROGRESS_MILESTONE, wait_if_speaking=False)
    await queue.enqueue("Jalon 2", priority=InjectionPriority.PROGRESS_MILESTONE, wait_if_speaking=False)
    await queue.enqueue("Jalon 3", priority=InjectionPriority.PROGRESS_MILESTONE, wait_if_speaking=False)

    await queue._queue.join()

    assert delivered_order == ["Jalon 1", "Jalon 2", "Jalon 3"]


@pytest.mark.asyncio
async def test_single_channel_rule_blocks_enqueued_action():
    """Valide que la file bloque toute injection d'action déjà résolue de manière synchrone."""
    queue = VoiceInjectionQueue()
    mock_session = MagicMock()
    mock_session.send_client_content = AsyncMock()
    active_task_controller["live_session"] = mock_session
    active_task_controller["sync_resolved_actions"].clear()

    # Action déjà résolue
    mark_action_sync_completed("action_synchrone_test")

    success = await queue.enqueue(
        "Ce message ne doit jamais partir",
        priority=InjectionPriority.TOOL_RESPONSE,
        action_key="action_synchrone_test",
        wait_if_speaking=False,
        wait_for_completion=True
    )

    assert success is False
    mock_session.send_client_content.assert_not_called()


@pytest.mark.asyncio
async def test_clear_purges_pending_items():
    """Valide que clear() vide les éléments en attente sans les envoyer."""
    queue = VoiceInjectionQueue()
    mock_session = MagicMock()
    mock_session.send_client_content = AsyncMock()
    active_task_controller["live_session"] = mock_session
    active_task_controller["speaking_active"] = True  # Bloque l'envoi immédiat

    # On enfile des messages
    await queue.enqueue("Msg 1", priority=InjectionPriority.PASSIVE_INFO, wait_if_speaking=True)
    await queue.enqueue("Msg 2", priority=InjectionPriority.PASSIVE_INFO, wait_if_speaking=True)

    # Purge immédiate
    queue.clear()
    active_task_controller["speaking_active"] = False

    await asyncio.sleep(0.1)
    mock_session.send_client_content.assert_not_called()


def test_should_emit_milestones_threshold():
    """Vérifie le respect du seuil configurable pour les jalons vocaux."""
    queue = VoiceInjectionQueue()

    # Seuil par défaut à 90s
    orig_threshold = getattr(config, "VOCAL_MILESTONE_THRESHOLD_SECONDS", 90.0)
    config.VOCAL_MILESTONE_THRESHOLD_SECONDS = 90.0
    try:
        assert queue.should_emit_milestones(estimated_duration=30.0) is False
        assert queue.should_emit_milestones(estimated_duration=89.0) is False
        assert queue.should_emit_milestones(estimated_duration=90.0) is True
        assert queue.should_emit_milestones(estimated_duration=300.0) is True
    finally:
        config.VOCAL_MILESTONE_THRESHOLD_SECONDS = orig_threshold
