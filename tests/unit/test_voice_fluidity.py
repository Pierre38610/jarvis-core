import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

import config
from core.shared_state import (
    active_task_controller,
    wait_until_speech_finished,
    safe_send_live_client_content,
)
from core.tools.dispatcher import dispatch_tool


class TestVoiceFluidityPrompt:
    def test_prompt_contains_anti_repetition_and_fluid_rules(self):
        prompt = config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
        assert "ANTI-RÉPÉTITION" in prompt
        assert "ZÉRO RÉPÉTITION" in prompt
        assert "c'est bon c'est terminé" in prompt
        # Verify old robotic order is removed
        assert "ANNONCE SYSTÉMATIQUE DU LANCEMENT DES ACTIONS" not in prompt
        assert "SANS attendre la fin de l'outil" not in prompt


class TestSpeechGatingAndSafety:
    @pytest.mark.asyncio
    async def test_wait_until_speech_finished_waits_for_active_speech(self):
        active_task_controller["speaking_active"] = True
        active_task_controller["estimated_speech_end"] = time.time() + 0.15

        t0 = time.time()

        async def clear_speech():
            await asyncio.sleep(0.1)
            active_task_controller["speaking_active"] = False
            active_task_controller["estimated_speech_end"] = 0.0

        asyncio.create_task(clear_speech())
        await wait_until_speech_finished(timeout=1.0)
        assert time.time() - t0 >= 0.08

    @pytest.mark.asyncio
    async def test_safe_send_live_client_content_sends_content(self):
        active_task_controller["speaking_active"] = False
        active_task_controller["client_speaking"] = False
        active_task_controller["estimated_speech_end"] = 0.0

        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        success = await safe_send_live_client_content(
            mock_session,
            "Pierre, ton train est bien réservé !",
            wait_if_speaking=False
        )
        assert success is True
        mock_session.send_client_content.assert_called_once()


class TestSynchronousTrainSearch:
    @pytest.mark.asyncio
    async def test_rechercher_train_returns_direct_result_without_bg_speech_cut(self):
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        res = await dispatch_tool(
            name="rechercher_train",
            args={
                "origine": "Paris",
                "destination": "Lyon",
                "date_depart": "demain"
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Flash"
        )

        assert res.get("status") == "success"
        assert res.get("action") == "rechercher_train"
        assert "instruction_to_jarvis" in res
        # Direct result without kicking off a background task that cuts off speech
        assert res.get("status") != "lance_en_arriere_plan"
        assert "Paris" in res.get("instruction_to_jarvis")
