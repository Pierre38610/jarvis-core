"""tests/unit/test_voice_multisession.py
Tests unitaires pour la gestion multi-sessions WebSocket et la diffusion broadcast.
Vérifie que plusieurs clients (/ws) reçoivent les mises à jour et que la déconnexion de l'un n'affecte pas l'autre.
"""

import json
import pytest
from unittest.mock import AsyncMock

from core import shared_state
from routers.device_voice import push_speak_to_device, _DEVICE_SESSIONS


@pytest.mark.asyncio
class TestMultiSessionWebSocket:
    """Vérifie le comportement multi-sessions de active_task_controller et broadcast_supervision."""

    async def test_broadcast_to_multiple_ws_sessions(self):
        mock_ws_pc = AsyncMock()
        mock_ws_phone = AsyncMock()

        shared_state.active_task_controller["ws_sessions"] = {
            "ws_pc_123": mock_ws_pc,
            "ws_phone_456": mock_ws_phone,
        }

        try:
            await shared_state.broadcast_supervision()

            # Vérifie que les deux WebSockets ont reçu supervision_update
            assert mock_ws_pc.send_text.called
            assert mock_ws_phone.send_text.called

            msg_pc = json.loads(mock_ws_pc.send_text.call_args[0][0])
            msg_phone = json.loads(mock_ws_phone.send_text.call_args[0][0])

            assert msg_pc["type"] == "supervision_update"
            assert msg_phone["type"] == "supervision_update"
        finally:
            shared_state.active_task_controller["ws_sessions"].clear()

    async def test_push_speak_preferred_device(self):
        mock_ws_device = AsyncMock()
        _DEVICE_SESSIONS["esp32_salon"] = {
            "websocket": mock_ws_device,
            "ip": "192.168.1.50",
            "device_id": "esp32_salon"
        }
        shared_state.active_task_controller["preferred_device_id"] = "esp32_salon"

        try:
            # Appel sans device_id explicite -> utilise preferred_device_id
            success = await push_speak_to_device("", "Bonjour Pierre")
            assert success is True
            assert mock_ws_device.send_text.called
            sent = json.loads(mock_ws_device.send_text.call_args[0][0])
            assert sent["type"] == "push_speak"
            assert sent["text"] == "Bonjour Pierre"
        finally:
            _DEVICE_SESSIONS.clear()
            shared_state.active_task_controller["preferred_device_id"] = None
