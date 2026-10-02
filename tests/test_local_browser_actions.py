"""tests/test_local_browser_actions.py
Tests unitaires pour BrowserBridge et ses actions de navigation.
Mocke entièrement Playwright pour garantir aucun appel réseau ou externe.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from local_browser_actions import BrowserBridge


@pytest.fixture
def bridge():
    return BrowserBridge()


@pytest.mark.asyncio
async def test_browser_act_stops_at_first_error(bridge):
    """Vérifie que browser_act exécute les actions dans l'ordre
    et s'arrête immédiatement à la première erreur survenue.
    """
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)

    # 1ère action click réussit, 2ème échoue, 3ème ne doit pas être appelée
    call_counts = {"click_calls": 0}

    async def mock_click(selector, timeout=8000):
        call_counts["click_calls"] += 1
        if selector == '[data-jarvis-id="2"]':
            raise RuntimeError("Element not interactable")
        return None

    mock_page.click = AsyncMock(side_effect=mock_click)
    mock_page.wait_for_load_state = AsyncMock(return_value=None)

    task_id = "test_task_error"
    bridge._tasks[task_id] = mock_page

    actions = [
        {"type": "click", "id": 1},
        {"type": "click", "id": 2},
        {"type": "click", "id": 3},
    ]

    results = await bridge.browser_act(task_id, actions)

    # Doit avoir 2 résultats : le 1er réussi, le 2ème en échec
    assert len(results) == 2
    assert results[0]["ok"] is True
    assert results[0]["action"]["id"] == 1

    assert results[1]["ok"] is False
    assert results[1]["action"]["id"] == 2
    assert "Element not interactable" in results[1]["error"]

    # Le 3ème clic ne doit jamais avoir été exécuté
    assert call_counts["click_calls"] == 2


@pytest.mark.asyncio
async def test_browser_act_all_action_types(bridge):
    """Vérifie l'exécution des différents types d'actions (click, type, select, scroll, goto, wait, back, extract)."""
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.click = AsyncMock(return_value=None)
    mock_page.fill = AsyncMock(return_value=None)
    mock_page.press = AsyncMock(return_value=None)
    mock_page.select_option = AsyncMock(return_value=None)
    mock_page.evaluate = AsyncMock(side_effect=[
        None,  # scroll
        "Contenu principal extrait"  # extract
    ])
    mock_page.goto = AsyncMock(return_value=None)
    mock_page.wait_for_timeout = AsyncMock(return_value=None)
    mock_page.go_back = AsyncMock(return_value=None)
    mock_page.wait_for_load_state = AsyncMock(return_value=None)

    task_id = "test_task_full"
    bridge._tasks[task_id] = mock_page

    actions = [
        {"type": "click", "id": 10},
        {"type": "type", "id": 11, "text": "Paris", "enter": True},
        {"type": "select", "id": 12, "value": "FR"},
        {"type": "scroll", "direction": "down"},
        {"type": "goto", "url": "https://example.com"},
        {"type": "wait", "seconds": 2},
        {"type": "back"},
        {"type": "extract"},
    ]

    results = await bridge.browser_act(task_id, actions)

    assert len(results) == 8
    assert all(r["ok"] is True for r in results)

    # Vérifications des appels Playwright
    mock_page.click.assert_awaited_once_with('[data-jarvis-id="10"]', timeout=8000)
    mock_page.fill.assert_awaited_once_with('[data-jarvis-id="11"]', "Paris", timeout=8000)
    mock_page.press.assert_awaited_once_with('[data-jarvis-id="11"]', "Enter", timeout=8000)
    mock_page.select_option.assert_awaited_once_with('[data-jarvis-id="12"]', value="FR", timeout=8000)
    mock_page.goto.assert_awaited_once_with("https://example.com", wait_until="domcontentloaded", timeout=8000)
    mock_page.wait_for_timeout.assert_awaited_once_with(2000.0)
    mock_page.go_back.assert_awaited_once_with(timeout=8000)

    # Vérification extract
    assert results[7]["text"] == "Contenu principal extrait"


@pytest.mark.asyncio
async def test_browser_focus_and_close_task(bridge):
    """Vérifie que browser_focus appelle bring_to_front et browser_close_task oublie la page sans la fermer."""
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.bring_to_front = AsyncMock(return_value=None)
    mock_page.close = AsyncMock()

    task_id = "task_focus_close"
    bridge._tasks[task_id] = mock_page

    focus_res = await bridge.browser_focus(task_id)
    assert focus_res["ok"] is True
    mock_page.bring_to_front.assert_awaited_once()

    close_res = await bridge.browser_close_task(task_id)
    assert close_res["ok"] is True
    # Oublie la page sans fermer l'onglet
    assert task_id not in bridge._tasks
    mock_page.close.assert_not_called()


@pytest.mark.asyncio
async def test_browser_snapshot(bridge):
    """Vérifie que browser_snapshot évalue le JS et renvoie le dictionnaire enrichi."""
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    fake_snapshot = {
        "url": "https://example.com",
        "title": "Example Domain",
        "elements": '[1] button "Valider"',
        "text": "Texte de la page"
    }
    mock_page.evaluate = AsyncMock(return_value=fake_snapshot)

    task_id = "task_snapshot"
    bridge._tasks[task_id] = mock_page

    snapshot = await bridge.browser_snapshot(task_id)
    assert snapshot["ok"] is True
    assert snapshot["url"] == "https://example.com"
    assert snapshot["title"] == "Example Domain"
    assert snapshot["elements"] == '[1] button "Valider"'
    assert snapshot["text"] == "Texte de la page"


@pytest.mark.asyncio
async def test_browser_screenshot(bridge):
    """Vérifie la capture JPEG qualité 60 en base64."""
    mock_page = AsyncMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.screenshot = AsyncMock(return_value=b"fake_jpeg_data")

    task_id = "task_shot"
    bridge._tasks[task_id] = mock_page

    shot = await bridge.browser_screenshot(task_id)
    assert shot["ok"] is True
    assert "image" in shot
    assert "screenshot" in shot
    mock_page.screenshot.assert_awaited_once_with(type="jpeg", quality=60, full_page=False)
