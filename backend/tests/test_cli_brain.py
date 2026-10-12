"""Tests unitaires pour le module services.browser_agent.cli_brain."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from google_antigravity import AntigravityAgent, TaskResult
from services.browser_agent.cli_brain import decide, verify


@pytest.mark.asyncio
async def test_decide_parasite_text_parsing_ok():
    """(a) Vérifie qu'un JSON entouré de texte parasite et markdown est correctement extrait et validé."""
    parasite_output = (
        "Bonjour Pierre, voici l'analyse de l'écran :\n"
        "```json\n"
        "{\n"
        '  "thought": "Je clique sur le bouton de recherche.",\n'
        '  "actions": [{"type": "click", "id": 42}],\n'
        '  "need_screenshot": false,\n'
        '  "done": false,\n'
        '  "result": "",\n'
        '  "handoff": null\n'
        "}\n"
        "```\n"
        "J'attends le prochain snapshot pour continuer."
    )

    with patch.object(
        AntigravityAgent,
        "run_cli_task_stream",
        new_callable=AsyncMock,
        return_value=TaskResult(summary=parasite_output, status="completed"),
    ) as mock_cli:
        snapshot = {
            "url": "https://example.com",
            "title": "Example Domain",
            "elements": ['[42] button "Rechercher"'],
            "text": "Bienvenue sur le site",
        }
        res = await decide(
            goal="Cliquer sur rechercher",
            recipe_text=None,
            memory_hint=None,
            snapshot=snapshot,
            history=[],
        )

        assert mock_cli.call_count == 1
        assert res["thought"] == "Je clique sur le bouton de recherche."
        assert res["actions"] == [{"type": "click", "id": 42}]
        assert res["done"] is False
        assert res["need_screenshot"] is False
        assert "error" not in res


@pytest.mark.asyncio
async def test_decide_two_invalid_responses_returns_error_invalid_json():
    """(b) Vérifie qu'après deux réponses invalides d'agy, decide renvoie l'erreur invalid_json."""
    invalid_1 = "Je n'ai pas pu formater correctement ma réponse en JSON."
    invalid_2 = "Toujours du texte libre sans aucune accolade."

    mock_run = AsyncMock(
        side_effect=[
            TaskResult(summary=invalid_1, status="completed"),
            TaskResult(summary=invalid_2, status="completed"),
        ]
    )

    with patch.object(AntigravityAgent, "run_cli_task_stream", mock_run):
        snapshot = {
            "url": "https://example.com",
            "title": "Example Domain",
            "elements": [],
            "text": "",
        }
        res = await decide(
            goal="Naviguer",
            recipe_text=None,
            memory_hint=None,
            snapshot=snapshot,
            history=[],
        )

        assert mock_run.call_count == 2
        assert res == {"actions": [], "done": False, "error": "invalid_json"}


@pytest.mark.asyncio
async def test_decide_retry_success():
    """Vérifie qu'un échec au premier tour suivi d'un JSON valide au réessai réussit."""
    invalid_1 = "Pas du json"
    valid_2 = '{"thought":"Rattrapé","actions":[{"type":"wait","seconds":5}],"need_screenshot":false,"done":false,"result":"","handoff":null}'

    mock_run = AsyncMock(
        side_effect=[
            TaskResult(summary=invalid_1, status="completed"),
            TaskResult(summary=valid_2, status="completed"),
        ]
    )

    with patch.object(AntigravityAgent, "run_cli_task_stream", mock_run):
        snapshot = {"url": "https://test.com", "title": "Test", "elements": [], "text": ""}
        res = await decide(
            goal="Attendre",
            recipe_text=None,
            memory_hint=None,
            snapshot=snapshot,
            history=[],
        )

        assert mock_run.call_count == 2
        assert res["thought"] == "Rattrapé"
        assert res["actions"] == [{"type": "wait", "seconds": 5}]
        assert res["done"] is False


@pytest.mark.asyncio
async def test_verify_parasite_and_invalid_fallback():
    """Vérifie le parsing et le comportement de fallback pour verify."""
    # Cas succès avec parasite
    valid_output = 'Réflexion préalable... {"ok": true, "reason": "Panier validé"} Fin du rapport.'
    with patch.object(
        AntigravityAgent,
        "run_cli_task_stream",
        new_callable=AsyncMock,
        return_value=TaskResult(summary=valid_output, status="completed"),
    ):
        v_res = await verify("Acheter billet", "Panier non vide", {"url": "", "title": "", "elements": [], "text": ""})
        assert v_res == {"ok": True, "reason": "Panier validé"}

    # Cas double échec
    mock_fail = AsyncMock(
        side_effect=[
            TaskResult(summary="KO 1", status="completed"),
            TaskResult(summary="KO 2", status="completed"),
        ]
    )
    with patch.object(AntigravityAgent, "run_cli_task_stream", mock_fail):
        v_fail = await verify("Acheter billet", "Panier non vide", {"url": "", "title": "", "elements": [], "text": ""})
        assert v_fail == {"ok": False, "reason": "invalid_json"}
