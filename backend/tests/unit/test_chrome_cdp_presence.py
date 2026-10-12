"""Unit tests for Chrome CDP persistent piloting, presence detection and dynamic vocal arbitration."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.local_agent_service import local_agent_service, is_pc_connected, is_pc_connected_async
from services.system_service import is_local_pc_online
from core.tools.declarations import get_tools_list


class TestPresenceHelpers:
    def test_is_pc_connected_offline_when_no_websocket(self):
        local_agent_service._ws = None
        assert is_pc_connected() is False
        assert is_local_pc_online() is False

    def test_is_pc_connected_online_when_websocket_active(self):
        mock_ws = MagicMock()
        local_agent_service._ws = mock_ws
        try:
            assert is_pc_connected() is True
            assert is_local_pc_online() is True
        finally:
            local_agent_service._ws = None

    @pytest.mark.asyncio
    async def test_is_pc_connected_async_checks_redis_when_ws_none(self):
        local_agent_service._ws = None
        with patch("services.cache.cache_service.get_device_presence", new_callable=AsyncMock) as mock_presence:
            mock_presence.return_value = {"status": {"online": True}}
            res = await is_pc_connected_async()
            assert res is True

            mock_presence.return_value = {"status": {"online": False}}
            res_false = await is_pc_connected_async()
            assert res_false is False


class TestDeclarationsSchema:
    def test_tools_contain_execution_target(self):
        tools = get_tools_list()
        found_tools = {}
        for tool in tools:
            for decl in getattr(tool, "function_declarations", []):
                if decl.name in ("run_browser_task", "interact_web_page", "prepare_web_cart_or_checkout"):
                    props = decl.parameters.properties
                    assert "execution_target" in props, f"Missing execution_target in {decl.name}"
                    exec_prop = props["execution_target"]
                    assert "vps_headless" in exec_prop.enum
                    assert "local_chrome_cdp" in exec_prop.enum
                    found_tools[decl.name] = True

        assert "run_browser_task" in found_tools
        assert "interact_web_page" in found_tools
        assert "prepare_web_cart_or_checkout" in found_tools


class TestBrowserServiceCDPRouting:
    @pytest.mark.asyncio
    async def test_run_browser_task_routes_to_local_chrome_cdp_when_online(self):
        from services.browser_service import run_browser_task

        local_agent_service._ws = MagicMock()
        mock_cdp_response = {
            "status": "success",
            "url": "https://www.google.com",
            "title": "Google",
            "result_summary": "Recherche effectuée sur Chrome physique.",
            "screenshot_path": "/static/latest_screenshot.jpg"
        }

        try:
            with patch.object(local_agent_service, "send_command", new_callable=AsyncMock) as mock_cmd:
                mock_cmd.return_value = mock_cdp_response
                res = await run_browser_task(
                    goal="Rechercher des billets sur la Fnac",
                    url="https://www.fnac.com",
                    execution_target="local_chrome_cdp"
                )

                assert res["status"] == "success"
                assert res["execution_target"] == "local_chrome_cdp"
                mock_cmd.assert_called_once()
                action, payload = mock_cmd.call_args[0][0], mock_cmd.call_args[0][1]
                assert action == "execute_cdp_browser_action"
                assert payload["url"] == "https://www.fnac.com"
        finally:
            local_agent_service._ws = None

    @pytest.mark.asyncio
    async def test_run_browser_task_falls_back_to_vps_headless_when_offline(self):
        from services.browser_service import run_browser_task

        local_agent_service._ws = None  # PC offline

        with patch("services.browser_service._notify_live_fallback", new_callable=AsyncMock) as mock_notify, \
             patch("services.browser_service._attempt_browser_use", new_callable=AsyncMock) as mock_attempt:

            mock_attempt.return_value = {
                "status": "success",
                "summary": "Navigation exécutée en tâche de fond sur le VPS."
            }

            res = await run_browser_task(
                goal="Chercher un livre",
                url="https://www.amazon.fr",
                execution_target="local_chrome_cdp"
            )

            assert res["status"] == "success"
            mock_notify.assert_called_once()
            assert "secours" in mock_notify.call_args[0][0]
            mock_attempt.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_browser_task_falls_back_to_vps_headless_on_cdp_timeout_or_error(self):
        from services.browser_service import run_browser_task

        local_agent_service._ws = MagicMock()

        try:
            with patch.object(local_agent_service, "send_command", new_callable=AsyncMock) as mock_cmd, \
                 patch("services.browser_service._notify_live_fallback", new_callable=AsyncMock) as mock_notify, \
                 patch("services.browser_service._attempt_browser_use", new_callable=AsyncMock) as mock_attempt:

                mock_cmd.return_value = {
                    "status": "timeout",
                    "message": "Votre PC n'a pas répondu dans le délai imparti."
                }
                mock_attempt.return_value = {
                    "status": "success",
                    "summary": "Navigation exécutée sur VPS Cloud après timeout local."
                }

                res = await run_browser_task(
                    goal="Test timeout",
                    url="https://example.com",
                    execution_target="local_chrome_cdp"
                )

                assert res["status"] == "success"
                mock_notify.assert_called_once()
                mock_attempt.assert_called_once()
        finally:
            local_agent_service._ws = None

    @pytest.mark.asyncio
    async def test_interact_web_page_cdp_routing_and_fallback(self):
        from services.browser_service import interact_web_page

        local_agent_service._ws = MagicMock()
        try:
            with patch.object(local_agent_service, "send_command", new_callable=AsyncMock) as mock_cmd:
                mock_cmd.return_value = {
                    "status": "success",
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "performed_actions": ["Clic sur #submit"]
                }

                res = await interact_web_page(
                    url="https://example.com",
                    action="click",
                    selector="#submit",
                    execution_target="local_chrome_cdp"
                )

                assert res["status"] == "success"
                mock_cmd.assert_called_once()
        finally:
            local_agent_service._ws = None


class TestVoiceSystemInstructionArbitration:
    @pytest.mark.asyncio
    async def test_build_system_instruction_contains_arbitration_rule(self):
        from routers.voice import _build_system_instruction

        local_agent_service._ws = None
        instruction = await _build_system_instruction()

        assert "RÈGLE D'ARBITRAGE DE NAVIGATION ET PILOTAGE CHROME LOCAL" in instruction
        assert "execution_target='vps_headless'" in instruction
        assert "execution_target='local_chrome_cdp'" in instruction
        assert "Ton PC est allumé Pierre" in instruction
        assert "HORS-LIGNE" in instruction

        local_agent_service._ws = MagicMock()
        try:
            instruction_online = await _build_system_instruction()
            assert "EN LIGNE" in instruction_online
        finally:
            local_agent_service._ws = None
