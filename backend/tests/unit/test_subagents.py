"""tests/unit/test_subagents.py
Tests unitaires pour la gestion de la constellation de sous-agents orbitaux Antigravity.
Vérifie le cycle de vie dans SupervisionService et la diffusion WebSocket via shared_state.
"""

import json
import pytest
from unittest.mock import AsyncMock

from services.supervision_service import SupervisionService
from core import shared_state


class TestSupervisionServiceSubagents:
    """Vérifie les méthodes de gestion du cycle de vie des sous-agents dans SupervisionService."""

    def test_spawn_and_retrieve_subagent(self):
        service = SupervisionService()
        agent = service.spawn_subagent(
            agent_id="test_worker_1",
            name="Alpha Coder",
            role="coder",
            activity="coding",
            task="Génération du script Python",
            model="Gemini 2.5 Pro"
        )
        assert agent["id"] == "test_worker_1"
        assert agent["name"] == "Alpha Coder"
        assert agent["role"] == "coder"
        assert agent["activity"] == "coding"
        assert agent["status"] == "active"
        assert agent["progress"] == 0

        active = service.get_active_subagents()
        assert len(active) == 1
        assert active[0]["id"] == "test_worker_1"

    def test_update_subagent_activity_and_progress(self):
        service = SupervisionService()
        service.spawn_subagent(
            agent_id="test_worker_2",
            name="Beta Critic",
            role="critic",
            activity="thinking",
            task="Analyse de cohérence"
        )

        updated = service.update_subagent(
            agent_id="test_worker_2",
            activity="browsing",
            task="Recherche documentation",
            progress=65
        )
        assert updated is not None
        assert updated["activity"] == "browsing"
        assert updated["task"] == "Recherche documentation"
        assert updated["progress"] == 65

    def test_complete_and_clear_subagents(self):
        service = SupervisionService()
        service.spawn_subagent("w1", "Worker 1", "coder")
        service.spawn_subagent("w2", "Worker 2", "prospector")

        assert len(service.get_active_subagents()) == 2

        # Complete w1
        completed = service.complete_subagent("w1", summary="Script généré avec succès")
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["progress"] == 100
        assert "completed_at" in completed

        # Only w2 is active
        active = service.get_active_subagents()
        assert len(active) == 1
        assert active[0]["id"] == "w2"

        # Clear all
        service.clear_subagents()
        assert len(service.get_active_subagents()) == 0

    def test_overview_includes_subagents(self):
        service = SupervisionService()
        service.spawn_subagent("w_overview", "Observer", "critic", "thinking")

        overview = service.get_full_overview()
        assert "subagents" in overview
        assert len(overview["subagents"]) == 1
        assert overview["subagents"][0]["id"] == "w_overview"


@pytest.mark.asyncio
class TestSharedStateSubagentsBroadcast:
    """Vérifie la diffusion des messages WebSocket pour les sous-agents orbitaux."""

    async def test_spawn_subagent_broadcast(self):
        mock_ws = AsyncMock()
        shared_state.active_task_controller["websocket"] = mock_ws

        try:
            agent = await shared_state.spawn_subagent(
                agent_id="orb_test_1",
                name="Scribe Satellite",
                role="coder",
                activity="coding",
                task="Création de fichier",
                model="Antigravity 2.0"
            )
            assert agent["id"] == "orb_test_1"

            # Vérifie qu'un message JSON subagent_spawn a été envoyé au WS
            calls = [json.loads(call.args[0]) for call in mock_ws.send_text.call_args_list if call.args]
            spawn_msg = next((m for m in calls if m.get("type") == "subagent_spawn"), None)
            assert spawn_msg is not None
            assert spawn_msg["agent"]["id"] == "orb_test_1"
            assert spawn_msg["agent"]["activity"] == "coding"
        finally:
            await shared_state.clear_all_subagents()
            shared_state.active_task_controller["websocket"] = None

    async def test_update_and_complete_subagent_broadcast(self):
        mock_ws = AsyncMock()
        shared_state.active_task_controller["websocket"] = mock_ws

        try:
            await shared_state.spawn_subagent("orb_test_2", "Critic Orb", "critic", "thinking")
            mock_ws.send_text.reset_mock()

            # Update
            await shared_state.update_subagent("orb_test_2", activity="synthesis", progress=80)
            calls = [json.loads(call.args[0]) for call in mock_ws.send_text.call_args_list if call.args]
            update_msg = next((m for m in calls if m.get("type") == "subagent_update"), None)
            assert update_msg is not None
            assert update_msg["id"] == "orb_test_2"
            assert update_msg["activity"] == "synthesis"
            assert update_msg["progress"] == 80

            mock_ws.send_text.reset_mock()

            # Complete
            await shared_state.complete_subagent("orb_test_2", summary="Critique achevée")
            calls = [json.loads(call.args[0]) for call in mock_ws.send_text.call_args_list if call.args]
            done_msg = next((m for m in calls if m.get("type") == "subagent_done"), None)
            assert done_msg is not None
            assert done_msg["id"] == "orb_test_2"
            assert done_msg["summary"] == "Critique achevée"
        finally:
            await shared_state.clear_all_subagents()
            shared_state.active_task_controller["websocket"] = None
