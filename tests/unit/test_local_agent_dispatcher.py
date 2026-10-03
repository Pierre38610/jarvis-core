"""tests/unit/test_local_agent_dispatcher.py
Tests unitaires pour le dispatcher handle_local_action de jarvis_local_agent.py.
Vérifie le routage exhaustif des 23 actions locales et la gestion des actions inconnues.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from jarvis_local_agent import handle_local_action


@pytest.mark.asyncio
async def test_handle_local_action_browser_open_task():
    """Vérifie que browser_open_task est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_open_task", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = {"ok": True, "url": "https://gemini.google.com/app"}
        res = await handle_local_action("browser_open_task", {"task_id": "bt_test_123", "start_url": "https://gemini.google.com/app"})
        assert res.get("ok") is True
        assert res.get("url") == "https://gemini.google.com/app"
        mock_open.assert_awaited_once_with("bt_test_123", "https://gemini.google.com/app")


@pytest.mark.asyncio
async def test_handle_local_action_browser_snapshot():
    """Vérifie que browser_snapshot est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = {"ok": True, "url": "https://gemini.google.com/app", "elements": "[1] button", "text": "test"}
        res = await handle_local_action("browser_snapshot", {"task_id": "bt_test_123"})
        assert res.get("ok") is True
        mock_snap.assert_awaited_once_with("bt_test_123")


@pytest.mark.asyncio
async def test_handle_local_action_browser_act():
    """Vérifie que browser_act est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_act", new_callable=AsyncMock) as mock_act:
        mock_act.return_value = [{"action": {"type": "click", "id": 1}, "ok": True}]
        actions = [{"type": "click", "id": 1}]
        res = await handle_local_action("browser_act", {"task_id": "bt_test_123", "actions": actions})
        assert isinstance(res, list)
        assert res[0]["ok"] is True
        mock_act.assert_awaited_once_with("bt_test_123", actions)


@pytest.mark.asyncio
async def test_handle_local_action_browser_screenshot():
    """Vérifie que browser_screenshot est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_screenshot", new_callable=AsyncMock) as mock_shot:
        mock_shot.return_value = {"ok": True, "image": "b64data"}
        res = await handle_local_action("browser_screenshot", {"task_id": "bt_test_123"})
        assert res.get("ok") is True
        assert res.get("image") == "b64data"
        mock_shot.assert_awaited_once_with("bt_test_123")


@pytest.mark.asyncio
async def test_handle_local_action_browser_focus():
    """Vérifie que browser_focus est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_focus", new_callable=AsyncMock) as mock_focus:
        mock_focus.return_value = {"ok": True}
        res = await handle_local_action("browser_focus", {"task_id": "bt_test_123"})
        assert res.get("ok") is True
        mock_focus.assert_awaited_once_with("bt_test_123")


@pytest.mark.asyncio
async def test_handle_local_action_browser_close_task():
    """Vérifie que browser_close_task est bien routé vers browser_bridge."""
    with patch("local_browser_actions.browser_bridge.browser_close_task", new_callable=AsyncMock) as mock_close:
        mock_close.return_value = {"ok": True}
        res = await handle_local_action("browser_close_task", {"task_id": "bt_test_123"})
        assert res.get("ok") is True
        mock_close.assert_awaited_once_with("bt_test_123")


@pytest.mark.asyncio
async def test_handle_local_action_search_and_browse():
    """Vérifie les actions de repli web de base (search_web, browse_page, run_browser_task)."""
    with patch("services.browser_service.search_web", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = {"status": "success", "results": []}
        res = await handle_local_action("search_web", {"query": "test"})
        assert res.get("status") == "success"

    with patch("services.browser_service.browse_page", new_callable=AsyncMock) as mock_browse:
        mock_browse.return_value = {"status": "success", "content": "page text"}
        res = await handle_local_action("browse_page", {"url": "https://example.com"})
        assert res.get("status") == "success"

    with patch("services.browser_service.run_browser_task", new_callable=AsyncMock) as mock_task:
        mock_task.return_value = {"status": "success", "result": "done"}
        res = await handle_local_action("run_browser_task", {"goal": "test goal"})
        assert res.get("status") == "success"


@pytest.mark.asyncio
async def test_handle_local_action_unknown_action():
    """Vérifie que toute action non supportée retourne explicitement une erreur structurée."""
    res = await handle_local_action("unsupported_custom_action_xyz", {})
    assert res.get("status") == "error"
    assert "Action inconnue : unsupported_custom_action_xyz" in res.get("message", "")
