import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from core.shared_state import (
    active_task_controller,
    wait_until_speech_finished,
    safe_send_live_client_content,
    mark_action_sync_completed,
    is_action_sync_completed,
)
from core.tools.dispatcher import dispatch_tool
from services.unified_memory import unified_memory_manager
from routers.voice import _build_system_instruction


class TestVoiceFluidityPrompt:
    def test_prompt_contains_anti_repetition_and_fluid_rules(self):
        prompt = config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
        assert "ANTI-RÉPÉTITION" in prompt
        assert "ZÉRO RÉPÉTITION" in prompt
        assert "c'est bon c'est terminé" in prompt
        # Verify old robotic order is removed
        assert "ANNONCE SYSTÉMATIQUE DU LANCEMENT DES ACTIONS" not in prompt
        assert "SANS attendre la fin de l'outil" not in prompt

    def test_prompt_anti_tics_directives(self):
        prompt = config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
        assert "Bannis les amorces robotiques et répétitives" in prompt
        assert "verbe d'action" in prompt
        assert "C'est noté" in prompt

    @pytest.mark.asyncio
    async def test_unified_memory_anti_tics_guidelines(self):
        live_prompt = await unified_memory_manager.build_live_context_prompt()
        assert "Bannis formellement toute amorce robotique" in live_prompt
        assert "verbe d'action" in live_prompt

    @pytest.mark.asyncio
    async def test_voice_router_system_instruction_includes_fluidity(self):
        instruction = await _build_system_instruction()
        assert "Bannis les amorces robotiques" in instruction
        assert "verbe d'action" in instruction


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
        active_task_controller["sync_resolved_actions"].clear()

        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        success = await safe_send_live_client_content(
            mock_session,
            "Pierre, ton train est bien réservé !",
            wait_if_speaking=False
        )
        assert success is True
        mock_session.send_client_content.assert_called_once()


class TestSingleChannelRule:
    @pytest.mark.asyncio
    async def test_single_channel_rule_blocks_duplicate_client_content(self):
        active_task_controller["speaking_active"] = False
        active_task_controller["client_speaking"] = False
        active_task_controller["estimated_speech_end"] = 0.0
        active_task_controller["sync_resolved_actions"].clear()

        # Mark action as completed synchronously
        mark_action_sync_completed("launch_app")
        assert is_action_sync_completed("launch_app") is True

        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        # Attempt to inject client content for the sync action should be blocked
        success = await safe_send_live_client_content(
            mock_session,
            "C'est bon, application lancée !",
            action_key="launch_app",
            wait_if_speaking=False
        )
        assert success is False
        mock_session.send_client_content.assert_not_called()

        # An async action key not in sync_resolved_actions should pass
        success_async = await safe_send_live_client_content(
            mock_session,
            "Pierre, ta présentation est prête !",
            action_key="generer_presentation",
            wait_if_speaking=False
        )
        assert success_async is True
        mock_session.send_client_content.assert_called_once()


class TestSynchronousQuickTools:
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

        assert res.get("status") in ("success", "done")
        assert res.get("action") == "rechercher_train"
        assert "instruction_to_jarvis" in res
        assert res.get("status") not in ("lance_en_arriere_plan", "launched_in_background", "started")
        assert "Paris" in res.get("instruction_to_jarvis")

    @pytest.mark.asyncio
    async def test_launch_app_returns_synchronously(self):
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        with patch("services.system_service.launch_application", return_value={"status": "success", "app": "code", "pid": 1234}):
            res = await dispatch_tool(
                name="launch_app",
                args={"app_name": "code"},
                websocket=mock_ws,
                session=mock_session,
                is_paid_live=False,
                live_display_label="Gemini 3.8 Flash"
            )
            assert res.get("status") in ("success", "completed", "done")
            assert res.get("status") not in ("lance_en_arriere_plan", "launched_in_background", "started")
            assert "instruction_to_jarvis" in res

    @pytest.mark.asyncio
    async def test_get_status_returns_synchronously(self):
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        res = await dispatch_tool(
            name="get_status",
            args={},
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Flash"
        )
        assert res.get("status") in ("success", "completed", "done")
        assert res.get("status") not in ("lance_en_arriere_plan", "launched_in_background", "started")

    @pytest.mark.asyncio
    async def test_open_browser_returns_synchronously(self):
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        with patch("services.browser_service.open_browser_window", return_value={"status": "success", "url": "https://google.com"}):
            res = await dispatch_tool(
                name="open_browser",
                args={"url": "https://google.com"},
                websocket=mock_ws,
                session=mock_session,
                is_paid_live=False,
                live_display_label="Gemini 3.8 Flash"
            )
            assert res.get("status") in ("success", "completed", "done")
            assert res.get("status") not in ("lance_en_arriere_plan", "launched_in_background", "started")


class TestHeavyAsyncTasks:
    @pytest.mark.asyncio
    async def test_generer_presentation_returns_background_status(self):
        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()
        mock_session = MagicMock()
        mock_session.send_client_content = AsyncMock()

        res = await dispatch_tool(
            name="generer_presentation",
            args={"titre": "Stratégie IA", "sujet": "IA 2026"},
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Flash"
        )
        assert res.get("status") in ("lance_en_arriere_plan", "launched_in_background", "started")
        assert res.get("action") == "generer_presentation"
