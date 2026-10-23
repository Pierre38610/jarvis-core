"""Unit tests for the unified Antigravity autonomous browser mission executor.

Tests:
- Autonomous navigation delegation to Antigravity agent (agy) on VPS.
- Extraction and strict validation of final URL and JSON contract.
- Automatic opening on Pierre's local PC via send_rpc_command when online.
- HUD browser link update via set_browser_link.
- Voice injection into voice_injection_queue with TOOL_RESPONSE priority.
- Fallback to legacy RPC browser loop when LEGACY_RPC_BROWSER_LOOP=true.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.browser_agent.loop import (
    BrowserTask,
    run_antigravity_browser_mission,
    run_browser_task,
    set_browser_link,
    _is_valid_final_url,
    _extract_browser_mission_json,
    _build_browser_mission_prompt,
)
from services.agentic_runner import AgentOutput
from services.voice_injection_queue import InjectionPriority, voice_injection_queue
from services.local_agent_service import local_agent_service
from core.tools.result import ToolResult


class TestUrlAndJsonHelpers:
    def test_is_valid_final_url_valid_https(self):
        assert _is_valid_final_url("https://www.sncf-connect.com/billet-train/recapitulatif?id=123") is True
        assert _is_valid_final_url("https://amazon.fr/gp/aws/cart/add.html?ASIN.1=B09XYZ&Quantity.1=1") is True

    def test_is_valid_final_url_rejects_placeholders_and_invalid(self):
        assert _is_valid_final_url("") is False
        assert _is_valid_final_url("https://...") is False
        assert _is_valid_final_url("https://example.com") is False
        assert _is_valid_final_url("not_a_url") is False
        assert _is_valid_final_url(None) is False

    def test_extract_browser_mission_json_from_markdown_block(self):
        raw = """
        Voici les résultats de ma recherche :
        ```json
        {
          "status": "ready_for_user",
          "summary_for_voice": "J'ai trouvé le train Malmö-Stockholm de 08h12 à 45€ et je t'ouvre la page de réservation sur ton PC.",
          "final_url": "https://www.sj.se/sv/kop-resa/valj-resa/Malmo-C/Stockholm-C/2026-10-15?train=SJ123",
          "options_found": [{"title": "SJ Snabbtåg 123", "price": "45€", "time": "08:12", "url": "https://www.sj.se/sv/..."}],
          "requires_user_action": "Se connecter et valider le paiement"
        }
        ```
        """
        parsed = _extract_browser_mission_json(raw)
        assert parsed is not None
        assert parsed["status"] == "ready_for_user"
        assert "08h12" in parsed["summary_for_voice"]
        assert "sj.se" in parsed["final_url"]

    def test_build_browser_mission_prompt_contains_guardrails_and_contract(self):
        task = BrowserTask(
            task_id="bt_test_build",
            goal="Trouver un train Malmö-Stockholm",
            recipe="train",
        )
        prompt = _build_browser_mission_prompt(task, recipe_text="Consignes ferroviaires")
        assert "Trouver un train Malmö-Stockholm" in prompt
        assert "GARDE-FOU" in prompt or "garde-fou" in prompt.lower()
        assert "ready_for_user" in prompt
        assert "final_url" in prompt
        assert "summary_for_voice" in prompt


@pytest.mark.asyncio
class TestAntigravityBrowserMission:
    async def test_train_mission_autonomous_flow_with_pc_online(self):
        """Vérifie le flux complet train : agy -> deep-link -> open_browser sur PC local -> HUD -> voix."""
        task = BrowserTask(
            task_id="bt_train_test",
            goal="Réserver un train Malmö - Stockholm le 15 octobre",
            recipe="train",
        )

        mock_json = {
            "status": "ready_for_user",
            "summary_for_voice": "J'ai trouvé le train Malmö-Stockholm de 08h12 à 45€ et je t'ouvre la page sur ton PC.",
            "final_url": "https://www.sj.se/sv/kop-resa/valj-resa/Malmo-C/Stockholm-C/2026-10-15?ref=deep_123",
            "options_found": [
                {"title": "SJ Snabbtåg Malmö-Stockholm", "price": "45€", "time": "08:12", "url": "https://www.sj.se/sv/..."}
            ],
            "requires_user_action": "Se connecter et valider le paiement",
        }

        agent_output = AgentOutput(
            conclusion=f"Mission accomplie.\n```json\n{json.dumps(mock_json)}\n```",
            confidence=0.98,
            sources=["https://www.sj.se/sv/..."],
            status="success",
        )

        enqueued = []
        async def mock_enqueue(text, priority, **kwargs):
            enqueued.append((text, priority, kwargs))
            return True

        with patch("services.agentic_runner.run_agentic", new_callable=AsyncMock, return_value=agent_output) as mock_agy, \
             patch("services.local_agent_service.local_agent_service.is_connected", return_value=True), \
             patch("services.local_agent_service.local_agent_service.send_rpc_command", new_callable=AsyncMock) as mock_rpc, \
             patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock) as mock_hud, \
             patch.object(voice_injection_queue, "enqueue", side_effect=mock_enqueue):

            mock_rpc.return_value = {"status": "success", "message": "Browser opened"}

            res = await run_antigravity_browser_mission(task)

            assert res["status"] == "ready_for_user"
            assert res["final_url"] == mock_json["final_url"]
            assert res["opened_on_pc"] is True
            assert task.status == "ready_for_user"

            # Vérifie l'appel RPC à l'agent local Windows de Pierre
            mock_rpc.assert_awaited_once_with(
                "open_browser",
                {"url": mock_json["final_url"], "new_window": False},
            )

            # Vérifie la mise à jour du lien dans le HUD
            mock_hud.assert_awaited_once_with(
                url=mock_json["final_url"],
                title="SJ Snabbtåg Malmö-Stockholm",
            )

            # Vérifie l'injection vocale avec priorité TOOL_RESPONSE
            assert len(enqueued) == 1
            assert enqueued[0][0] == mock_json["summary_for_voice"]
            assert enqueued[0][1] == InjectionPriority.TOOL_RESPONSE

    async def test_cart_mission_autonomous_flow_with_pc_offline(self):
        """Vérifie le flux e-commerce : si le PC est hors ligne, le lien est positionné dans le HUD et la voix annonce sans erreur RPC."""
        task = BrowserTask(
            task_id="bt_cart_test",
            goal="Préparer le panier pour un Câble HDMI 2.1 sur amazon.fr",
            recipe="cart",
        )

        mock_json = {
            "status": "ready_for_user",
            "summary_for_voice": "J'ai préparé le panier Amazon pour le câble HDMI 2.1 à 14,99€.",
            "final_url": "https://www.amazon.fr/gp/aws/cart/add.html?ASIN.1=B09XYZ123&Quantity.1=1",
            "options_found": [
                {"title": "Câble HDMI 2.1 48Gbps 2m", "price": "14,99€", "time": "En stock", "url": "https://amazon.fr/dp/B09XYZ123"}
            ],
            "requires_user_action": "Se connecter et valider le paiement",
        }

        agent_output = AgentOutput(
            conclusion=json.dumps(mock_json),
            confidence=0.95,
            status="success",
        )

        with patch("services.agentic_runner.run_agentic", new_callable=AsyncMock, return_value=agent_output), \
             patch("services.local_agent_service.local_agent_service.is_connected", return_value=False), \
             patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
             patch("services.local_agent_service.local_agent_service.send_rpc_command", new_callable=AsyncMock) as mock_rpc, \
             patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock) as mock_hud, \
             patch.object(voice_injection_queue, "enqueue", new_callable=AsyncMock) as mock_voice:

            res = await run_antigravity_browser_mission(task)

            assert res["status"] == "ready_for_user"
            assert res["opened_on_pc"] is False
            mock_rpc.assert_not_called()
            mock_hud.assert_awaited_once()
            mock_voice.assert_awaited_once()

    async def test_run_browser_task_calls_mission_and_returns_tool_result_done(self):
        """Vérifie que run_browser_task appelle run_antigravity_browser_mission et produit un ToolResult.done."""
        task = BrowserTask(task_id="bt_wrapper_test", goal="Test navigation")

        mission_out = {
            "status": "ready_for_user",
            "summary_for_voice": "Page prête sur ton PC.",
            "final_url": "https://www.trainline.fr/search/paris/lyon",
            "options_found": [],
            "requires_user_action": "Se connecter et valider le paiement",
            "opened_on_pc": True,
        }

        with patch("services.browser_agent.loop.run_antigravity_browser_mission", new_callable=AsyncMock, return_value=mission_out) as mock_mission:
            tr = await run_browser_task(task)
            assert isinstance(tr, ToolResult)
            assert tr.is_success is True
            assert tr.user_message == "Page prête sur ton PC."
            assert tr.evidence == "https://www.trainline.fr/search/paris/lyon"
            mock_mission.assert_awaited_once()

    async def test_run_browser_task_falls_back_to_legacy_rpc_when_flag_enabled(self):
        """Vérifie le repli vers _run_local_browser_loop si LEGACY_RPC_BROWSER_LOOP=true."""
        task = BrowserTask(task_id="bt_legacy_test", goal="Test legacy")

        with patch.dict("os.environ", {"LEGACY_RPC_BROWSER_LOOP": "true"}), \
             patch("services.browser_agent.loop._run_local_browser_loop", new_callable=AsyncMock) as mock_legacy, \
             patch("services.browser_agent.loop.run_antigravity_browser_mission", new_callable=AsyncMock) as mock_mission:

            mock_legacy.return_value = ToolResult.done(user_message="Succès legacy", task_id=task.task_id)

            res = await run_browser_task(task)
            assert res.is_success is True
            mock_legacy.assert_awaited_once()
            mock_mission.assert_not_called()
