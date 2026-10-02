"""tests/test_browser_loop.py
Tests unitaires pour la boucle de navigation Browser Agent Jarvis (loop.py).
Mocks stricts de RPC local et Antigravity CLI pour garantir zéro appel externe et zéro coût.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.tools.result import ToolResult
from services.browser_agent.guards import check_action
from services.browser_agent.loop import BrowserTask, run_browser_task
from services.browser_agent import site_memory


@pytest.mark.asyncio
async def test_scenario_two_steps_then_done_and_verify_ok():
    """(a) Scénario de 2 étapes puis done et verify OK -> status done."""
    task = BrowserTask(
        task_id="task_test_a",
        goal="Acheter un t-shirt et vérifier le panier",
        start_url="https://shop.example.com",
    )

    # Simulation des RPCs renvoyés par l'agent local
    snapshot_step1 = {
        "ok": True,
        "url": "https://shop.example.com",
        "title": "Shop Home",
        "elements": ['[10] link "T-shirts"', '[11] button "Contact"'],
        "text": "Catalogue de vêtements",
    }
    snapshot_step2 = {
        "ok": True,
        "url": "https://shop.example.com/tshirts",
        "title": "T-shirts",
        "elements": ['[20] button "Ajouter au panier"'],
        "text": "T-shirt noir 19€",
    }
    snapshot_verify = {
        "ok": True,
        "url": "https://shop.example.com/cart",
        "title": "Panier",
        "elements": ['[30] text "1 article au panier"'],
        "text": "Total 19€",
    }

    rpc_calls = []

    async def mock_execute_command(action: str, timeout: float = 30.0, **params):
        rpc_calls.append((action, params))
        if action == "browser_open_task":
            return {"ok": True}
        elif action == "browser_snapshot":
            # 1er snapshot = step 1, 2eme snapshot = step 2, 3eme snapshot = verif
            if len([c for c in rpc_calls if c[0] == "browser_snapshot"]) == 1:
                return snapshot_step1
            elif len([c for c in rpc_calls if c[0] == "browser_snapshot"]) == 2:
                return snapshot_step2
            else:
                return snapshot_verify
        elif action == "browser_act":
            return [{"action": a, "ok": True} for a in params.get("actions", [])]
        elif action == "browser_focus":
            return {"ok": True}
        elif action == "browser_close_task":
            return {"ok": True}
        return {"ok": True}

    # Simulation des décisions du brain
    brain_calls = []

    async def mock_decide(*args, **kwargs):
        call_num = len(brain_calls) + 1
        brain_calls.append((args, kwargs))
        if call_num == 1:
            return {
                "thought": "Je navigue vers les t-shirts",
                "actions": [{"type": "click", "id": 10}],
                "need_screenshot": False,
                "done": False,
                "result": "",
                "handoff": None,
            }
        else:
            return {
                "thought": "J'ajoute au panier et c'est terminé",
                "actions": [{"type": "click", "id": 20}],
                "need_screenshot": False,
                "done": True,
                "result": "Article ajouté au panier avec succès",
                "handoff": None,
            }

    async def mock_verify(goal: str, success_criteria: str, snapshot: dict):
        return {"ok": True, "reason": "T-shirt bien présent dans le panier"}

    with patch("services.browser_agent.loop._call_rpc", side_effect=mock_execute_command), \
         patch("services.browser_agent.cli_brain.decide", side_effect=mock_decide), \
         patch("services.browser_agent.cli_brain.verify", side_effect=mock_verify), \
         patch("services.browser_agent.site_memory.save_success") as mock_save_success:

        result = await run_browser_task(task)

        assert task.status == "done"
        assert isinstance(result, ToolResult)
        assert result.status == "done"
        assert result.verified is True
        assert "T-shirt bien présent dans le panier" in result.evidence
        assert mock_save_success.called

        # Vérifier que browser_focus a bien été appelé à la fin
        focus_calls = [c for c in rpc_calls if c[0] == "browser_focus"]
        assert len(focus_calls) >= 1


@pytest.mark.asyncio
async def test_scenario_payment_button_triggers_ready_for_user_and_no_click_sent():
    """(b) Le brain veut cliquer sur [3] button "Passer la commande" -> ready_for_user, et aucun clic envoyé."""
    task = BrowserTask(
        task_id="task_test_b",
        goal="Acheter un livre",
        start_url="https://books.example.com/checkout",
    )

    snapshot_checkout = {
        "ok": True,
        "url": "https://books.example.com/checkout",
        "title": "Passer commande",
        "elements": [
            '[2] text "Total: 30€"',
            '[3] button "Passer la commande"',
        ],
        "text": "Récapitulatif de votre commande",
    }

    rpc_actions_sent = []

    async def mock_execute_command(action: str, timeout: float = 30.0, **params):
        if action == "browser_act":
            rpc_actions_sent.extend(params.get("actions", []))
            return [{"action": a, "ok": True} for a in params.get("actions", [])]
        elif action == "browser_snapshot":
            return snapshot_checkout
        return {"ok": True}

    async def mock_decide(*args, **kwargs):
        return {
            "thought": "Tout est prêt, je passe la commande",
            "actions": [{"type": "click", "id": 3}],
            "need_screenshot": False,
            "done": False,
            "result": "",
            "handoff": None,
        }

    with patch("services.browser_agent.loop._call_rpc", side_effect=mock_execute_command) as mock_rpc, \
         patch("services.browser_agent.cli_brain.decide", side_effect=mock_decide):

        result = await run_browser_task(task)

        # Vérification clé : le statut doit être 'ready_for_user'
        assert task.status == "ready_for_user"
        # AUCUN clic ne doit avoir été envoyé au navigateur
        assert len(rpc_actions_sent) == 0

        # ToolResult retourné
        assert isinstance(result, ToolResult)
        assert result.status == "needs_user"
        assert result.data.get("status") == "ready_for_user"
        assert "C'est prêt" in result.user_message

        # browser_focus doit être appelé
        focus_called = any(
            call.args[0] == "browser_focus" or call.kwargs.get("action") == "browser_focus"
            for call in mock_rpc.call_args_list
        )
        assert focus_called


@pytest.mark.asyncio
async def test_guards_check_action_all_rules():
    """Vérifie unitairement les règles de sécurité S5 dans guards.check_action."""
    snapshot_elements = [
        '[1] link "Accueil"',
        '[2] button "Ajouter au panier"',
        '[3] button "Passer la commande"',
        '[4] button "Payer 25€"',
        '[5] input[password] placeholder="Mot de passe"',
        '[6] input[text] placeholder="Numéro de carte"',
        '[7] input[text] name="cvv"',
        '[8] input[text] placeholder="IBAN"',
    ]

    # Clic normal autorisé
    allowed, _ = check_action({"type": "click", "id": 2}, snapshot_elements)
    assert allowed is True

    # Clics de commande ou paiement refusés
    allowed, reason = check_action({"type": "click", "id": 3}, snapshot_elements)
    assert allowed is False
    assert "payment" in reason

    allowed, reason = check_action({"type": "click", "id": 4}, snapshot_elements)
    assert allowed is False
    assert "payment" in reason

    # Saisies sensibles refusées
    allowed, reason = check_action({"type": "type", "id": 5, "text": "secret123"}, snapshot_elements)
    assert allowed is False
    assert "sensitive" in reason

    allowed, reason = check_action({"type": "type", "id": 6, "text": "4970 0000"}, snapshot_elements)
    assert allowed is False
    assert "sensitive" in reason

    allowed, reason = check_action({"type": "type", "id": 7, "text": "123"}, snapshot_elements)
    assert allowed is False
    assert "sensitive" in reason

    # goto http(s) autorisé, javascript: refusé
    allowed, _ = check_action({"type": "goto", "url": "https://example.com"}, snapshot_elements)
    assert allowed is True

    allowed, reason = check_action({"type": "goto", "url": "javascript:alert(1)"}, snapshot_elements)
    assert allowed is False
    assert "goto" in reason


import shutil
import pathlib

def test_site_memory_load_hint_and_save_success():
    """Vérifie le chargement d'indice et la sauvegarde atomique dans site_memory."""
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_scratch", "site_mem_test")
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    orig = site_memory.SITE_MEMORY_DIR
    try:
        site_memory.SITE_MEMORY_DIR = test_dir
        domain = "testshop.com"
        # Sauvegarde de 2 succès
        assert site_memory.save_success(domain, "recherche livre python", ["ouvrir recherche", "taper python", "cliquer loupe"]) is True
        assert site_memory.save_success(domain, "recherche chaussure running", ["cliquer sport", "choisir running"]) is True

        # Recherche d'indice avec mots communs
        hint = site_memory.load_hint(domain, "je veux trouver un livre python pas cher")
        assert "recherche livre python" in hint
        assert "taper python" in hint
        assert len(hint) <= 600

        # Sauvegarde de plus de 20 entrées pour tester la limite
        for i in range(25):
            site_memory.save_success(domain, f"goal_{i}", [f"step_{i}"])

        hint_new = site_memory.load_hint(domain, "goal_24")
        assert "goal_24" in hint_new

        # Vérification fichier json atomique
        import json
        with open(pathlib.Path(test_dir) / f"{domain}.json", "r", encoding="utf-8") as f:
            entries = json.load(f)
        assert len(entries) == 20
    finally:
        site_memory.SITE_MEMORY_DIR = orig
        shutil.rmtree(test_dir, ignore_errors=True)




