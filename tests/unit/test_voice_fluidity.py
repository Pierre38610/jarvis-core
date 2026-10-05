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
from routers.voice import _build_system_instruction, _build_switch_context_prompt, _establish_live_session


class TestVoiceFluidityPrompt:
    @pytest.mark.asyncio
    async def test_prompt_contains_anti_repetition_and_fluid_rules(self):
        """Les règles d'élocution naturelle sont composées par routers/voice.py (_build_system_instruction)."""
        instruction = await _build_system_instruction()
        assert "ANTI-TICS VERBAUX" in instruction
        assert "Bannis les amorces robotiques et répétitives" in instruction
        # Verify old robotic order is removed
        assert "ANNONCE SYSTÉMATIQUE DU LANCEMENT DES ACTIONS" not in instruction
        assert "SANS attendre la fin de l'outil" not in instruction

    @pytest.mark.asyncio
    async def test_prompt_anti_tics_directives(self):
        instruction = await _build_system_instruction()
        assert "Bannis les amorces robotiques et répétitives" in instruction
        assert "verbe d'action" in instruction
        assert "C'est noté" in instruction

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

    @pytest.mark.asyncio
    async def test_prompt_contains_dreams_and_morning_rule(self):
        instruction = await _build_system_instruction()
        assert "INTERDICTION PROACTIVE SUR LES RÊVES" in instruction
        assert "Ne pose JAMAIS de ta propre initiative de question sur la nuit" in instruction
        assert "COMPORTEMENT STRICTEMENT INTEMPOREL" in instruction
        assert "qu'est-ce qu'on fait ce matin" in instruction
        assert "save_memory" in instruction
        assert "send_email" in instruction

    @pytest.mark.asyncio
    async def test_unified_memory_dreams_guidelines(self):
        live_prompt = await unified_memory_manager.build_live_context_prompt()
        assert "Ne pose JAMAIS de questions proactives sur les rêves" in live_prompt
        assert "Comportement strictement intemporel" in live_prompt
        assert "qu'est-ce qu'on fait ce matin" in live_prompt

    @pytest.mark.asyncio
    async def test_build_switch_context_prompt_with_pending_query(self):
        prompt = await _build_switch_context_prompt(
            recent_turns=[{"role": "user", "text": "Ancien message"}],
            announcement_phrase="",
            pending_user_query="Résous cette énigme complexe en L3"
        )
        assert "Résous cette énigme complexe en L3" in prompt
        assert "exécute DIRECTEMENT et immédiatement son ordre" in prompt
        assert "de quoi s'occupe-t-on" in prompt.lower()  # in the prohibition (ne dis JAMAIS 'de quoi s'occupe-t-on')
        assert "sans aucune formule d'attente générique" in prompt

    @pytest.mark.asyncio
    async def test_establish_live_session_nominal(self):
        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        mock_client = MagicMock()
        mock_client.aio.live.connect.return_value = mock_ctx

        s_ctx, session = await _establish_live_session("gemini-3.8-live", mock_client)
        assert s_ctx is mock_ctx
        assert session is mock_session
        mock_client.aio.live.connect.assert_called_once()
        call_kwargs = mock_client.aio.live.connect.call_args[1]
        assert call_kwargs["model"] == "gemini-3.8-live"
        live_cfg = call_kwargs["config"]
        assert live_cfg.system_instruction is not None
        assert len(live_cfg.system_instruction.parts) > 0
        assert "ANTI-TICS VERBAUX" in live_cfg.system_instruction.parts[0].text

    @pytest.mark.asyncio
    async def test_establish_live_session_with_custom_instruction(self):
        mock_session = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session

        mock_client = MagicMock()
        mock_client.aio.live.connect.return_value = mock_ctx

        custom_text = "CUSTOM SYSTEM INSTRUCTION TEST"
        s_ctx, session = await _establish_live_session("gemini-3.8-live", mock_client, system_instruction_text=custom_text)
        assert session is mock_session
        call_kwargs = mock_client.aio.live.connect.call_args[1]
        live_cfg = call_kwargs["config"]
        assert live_cfg.system_instruction.parts[0].text == custom_text


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
            args={"titre": "Stratégie IA", "sujet": "IA 2026", "consignes": "Présenter la stratégie IA 2026 de Stark Industries"},
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Flash"
        )
        assert res.get("status") in ("lance_en_arriere_plan", "launched_in_background", "started")
        assert res.get("action") == "generer_presentation"
