"""tests/test_try_browser_task.py
Test du script scripts/try_browser_task.py en mode mocké (zéro appel externe / zéro coût API).
"""

import asyncio
import io
import sys
from unittest.mock import AsyncMock, patch
import pytest

from scripts.try_browser_task import main


@pytest.mark.asyncio
async def test_try_browser_task_full_mock_run(monkeypatch):
    """Vérifie le bon déroulement de bout en bout du script try_browser_task avec instrumentation."""
    test_argv = [
        "try_browser_task.py",
        "--goal", "Acheter un livre Python",
        "--start-url", "https://books.example.com",
    ]
    monkeypatch.setattr(sys, "argv", test_argv)

    # Simulation RPC
    rpc_calls = []

    async def mock_execute_command(action: str, timeout: float = 30.0, **params):
        rpc_calls.append((action, params))
        if action == "browser_open_task":
            return {"ok": True, "url": "https://books.example.com"}
        elif action == "browser_snapshot":
            count = len([c for c in rpc_calls if c[0] == "browser_snapshot"])
            if count == 1:
                return {
                    "ok": True,
                    "url": "https://books.example.com",
                    "title": "Books Store",
                    "elements": ['[1] button "Search"'],
                    "text": "Catalogue de livres",
                }
            elif count == 2:
                return {
                    "ok": True,
                    "url": "https://books.example.com/python-book",
                    "title": "Livre Python",
                    "elements": ['[2] text "Livre Python trouvé"'],
                    "text": "Livre Python 29€",
                }
            return {
                "ok": True,
                "url": "https://books.example.com/python-book",
                "title": "Livre Python",
                "elements": ['[2] text "Livre Python trouvé"'],
                "text": "Livre Python 29€",
            }
        elif action == "browser_act":
            return [{"action": params.get("actions", [{}])[0], "ok": True}]
        elif action == "browser_screenshot":
            return {"ok": True, "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}
        elif action == "browser_focus":
            return {"ok": True}
        return {"ok": True}

    # Simulation agy CLI
    agy_calls = []

    async def mock_call_agy(prompt: str, model: str, timeout: float) -> str:
        agy_calls.append(prompt)
        if "Tu pilotes un navigateur" in prompt:
            count = len(agy_calls)
            if count == 1:
                return '{"thought": "Je clique sur recherche", "actions": [{"type": "click", "id": 1}], "need_screenshot": true, "done": false}'
            else:
                return '{"thought": "Le livre est trouvé", "actions": [], "need_screenshot": false, "done": true, "result": "Livre trouvé"}'
        elif "Tu es un vérificateur" in prompt:
            return '{"ok": true, "reason": "Le livre Python est bien visible"}'
        return '{"ok": false}'

    captured_out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)

    with patch("services.local_agent_service.local_agent_service.execute_command", side_effect=mock_execute_command), \
         patch("services.browser_agent.cli_brain._call_agy", side_effect=mock_call_agy):
        await main()

    output = captured_out.getvalue()
    assert "DÉMARRAGE DU TEST MANUEL BROWSER AGENT" in output
    assert "Brain Décision" in output
    assert "Brain Verify" in output
    assert "BILAN FINAL DE LA TÂCHE DE NAVIGATION" in output
    assert "Statut             : done" in output
    assert "Nombre d'étapes    : 1" in output
    assert "Appels CLI agy     : 3" in output
    assert "Captures d'écran   : 1" in output
