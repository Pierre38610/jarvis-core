"""tests/test_gemini_web_automator.py
Tests unitaires pour services/gemini_web_automator.py
Couvre :
  - Persistance et mise à jour de UIMapManager (dérive UI)
  - Logique de click_with_verification avec mock Playwright (coordonnées OK & dérive)
  - Polling de fin de recherche (_wait_for_research_completion)
  - Sélection de mode de livraison (écran vs email)
  - Interface non-bloquante de GeminiDeepResearchEngine.launch()
"""

import asyncio
import json
import os
import sys
import time
import tempfile
import unittest
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

# Ajouter le répertoire racine au sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de mocks
# ──────────────────────────────────────────────────────────────────────────────

def make_locator_mock(count: int = 0, bounding_box: Optional[Dict] = None) -> MagicMock:
    """Crée un mock Playwright Locator avec count() et bounding_box() configurables."""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    locator.bounding_box = AsyncMock(return_value=bounding_box)
    locator.click = AsyncMock(return_value=None)
    locator.fill = AsyncMock(return_value=None)
    locator.type = AsyncMock(return_value=None)
    locator.first = locator  # .first retourne le même mock
    return locator


def make_page_mock(
    selector_counts: Optional[Dict[str, int]] = None,
    bounding_boxes: Optional[Dict[str, Dict]] = None,
) -> MagicMock:
    """Crée un mock Playwright Page avec locator() configurable par sélecteur."""
    selector_counts = selector_counts or {}
    bounding_boxes = bounding_boxes or {}

    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.url = "https://gemini.google.com/app"
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock(return_value=None)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock(return_value=None)
    page.keyboard.type = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock(return_value=None)
    page.goto = AsyncMock(return_value=None)
    page.content = AsyncMock(return_value="<html><body>Rapport Deep Research</body></html>")
    page.evaluate = AsyncMock(return_value="")
    page.title = AsyncMock(return_value="Gemini Deep Research")

    def get_locator(selector: str):
        count = selector_counts.get(selector, 0)
        bb = bounding_boxes.get(selector)
        return make_locator_mock(count=count, bounding_box=bb)

    page.locator = MagicMock(side_effect=get_locator)
    return page


# ──────────────────────────────────────────────────────────────────────────────
# Tests UIMapManager
# ──────────────────────────────────────────────────────────────────────────────

class TestUIMapManager(unittest.TestCase):
    """Tests de la persistance et de la mise à jour des coordonnées."""

    def setUp(self):
        """Crée un fichier JSON temporaire pour chaque test."""
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        initial_data = {
            "_last_updated": None,
            "_layout_version": 1,
            "actions": {
                "deep_research_button": {
                    "x": 120,
                    "y": 720,
                    "fallback_selectors": [
                        "[aria-label*='Deep Research' i]",
                        "button:has-text('Deep Research')",
                    ],
                    "validation": {
                        "selector": "[aria-label*='Deep Research' i][aria-pressed='true']",
                    },
                }
            },
        }
        json.dump(initial_data, self.tmp, ensure_ascii=False, indent=2)
        self.tmp.close()

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def _make_manager(self):
        from services.gemini_web_automator import UIMapManager
        return UIMapManager(path=self.tmp.name)

    def test_load_existing_coordinates(self):
        """UIMapManager charge correctement les coordonnées mémorisées."""
        manager = self._make_manager()
        action = manager.get_action("deep_research_button")
        self.assertEqual(action["x"], 120)
        self.assertEqual(action["y"], 720)

    def test_get_fallback_selectors(self):
        """get_fallback_selectors retourne la liste des sélecteurs de repli."""
        manager = self._make_manager()
        selectors = manager.get_fallback_selectors("deep_research_button")
        self.assertIsInstance(selectors, list)
        self.assertGreater(len(selectors), 0)
        self.assertIn("[aria-label*='Deep Research' i]", selectors)

    def test_get_validation_selector(self):
        """get_validation_selector retourne le sélecteur de confirmation d'état."""
        manager = self._make_manager()
        sel = manager.get_validation_selector("deep_research_button")
        self.assertIn("Deep Research", sel)

    def test_update_coordinates_persists(self):
        """update_coordinates met à jour les coordonnées et sauvegarde sur le disque."""
        manager = self._make_manager()
        manager.update_coordinates("deep_research_button", 250.7, 830.3)

        # Recharge depuis disque
        manager2 = self._make_manager()
        action = manager2.get_action("deep_research_button")
        self.assertEqual(action["x"], 251)  # arrondi
        self.assertEqual(action["y"], 830)

    def test_update_coordinates_increments_version(self):
        """La version de layout est incrémentée à chaque correction de coordonnées."""
        manager = self._make_manager()
        old_version = manager._data.get("_layout_version", 1)
        manager.update_coordinates("deep_research_button", 300, 800)
        self.assertEqual(manager._data.get("_layout_version"), old_version + 1)

    def test_get_action_unknown_returns_empty(self):
        """get_action retourne un dict vide pour une action inconnue."""
        manager = self._make_manager()
        action = manager.get_action("nonexistent_action")
        self.assertEqual(action, {})

    def test_update_creates_new_action_entry(self):
        """update_coordinates crée l'entrée si l'action n'existe pas encore."""
        manager = self._make_manager()
        manager.update_coordinates("new_button", 500, 600)
        action = manager.get_action("new_button")
        self.assertEqual(action["x"], 500)
        self.assertEqual(action["y"], 600)


# ──────────────────────────────────────────────────────────────────────────────
# Tests GeminiWebAutomator – click_with_verification
# ──────────────────────────────────────────────────────────────────────────────

class TestClickWithVerification(unittest.IsolatedAsyncioTestCase):
    """Tests de la logique de clic robuste avec auto-réparation."""

    def _make_automator(self, ui_map_path: str):
        from services.gemini_web_automator import GeminiWebAutomator, UIMapManager
        automator = GeminiWebAutomator()
        automator.ui_map = UIMapManager(path=ui_map_path)
        return automator

    async def asyncSetUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        data = {
            "_layout_version": 1,
            "actions": {
                "test_button": {
                    "x": 100,
                    "y": 200,
                    "fallback_selectors": ["button.test-btn", "[aria-label='Test']"],
                    "validation": {"selector": ".test-active"},
                }
            },
        }
        json.dump(data, self.tmp, ensure_ascii=False)
        self.tmp.close()
        self.automator = self._make_automator(self.tmp.name)

    async def asyncTearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    async def test_click_success_at_memorized_coords(self):
        """Si le sélecteur de validation apparaît après le clic, retourne True."""
        page = make_page_mock(selector_counts={".test-active": 1})
        page.wait_for_selector = AsyncMock(return_value=MagicMock())
        self.automator._page = page

        result = await self.automator.click_with_verification("test_button", verify_timeout=1.0)
        self.assertTrue(result)
        page.mouse.click.assert_awaited_once_with(100, 200)

    async def test_click_drift_detected_dom_fallback_success(self):
        """Si la validation échoue aux coordonnées mémorisées, le repli DOM réussit et met à jour les coordonnées."""
        # La validation échoue sur les premières tentatives (wait_for_selector lève une exception)
        call_count = {"n": 0}

        async def mock_wait_for_selector(selector, state=None, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("Element not found at memorized coords")
            return MagicMock()

        page = make_page_mock(
            selector_counts={
                "button.test-btn": 1,
                ".test-active": 1,
            },
            bounding_boxes={"button.test-btn": {"x": 300, "y": 400, "width": 120, "height": 40}},
        )
        page.wait_for_selector = AsyncMock(side_effect=mock_wait_for_selector)
        self.automator._page = page

        result = await self.automator.click_with_verification("test_button", verify_timeout=1.0)
        self.assertTrue(result)

        # Vérifie que les coordonnées ont été mises à jour
        action = self.automator.ui_map.get_action("test_button")
        self.assertEqual(action["x"], 360)  # 300 + 120/2
        self.assertEqual(action["y"], 420)  # 400 + 40/2

    async def test_click_all_fallbacks_fail_returns_false(self):
        """Si tous les sélecteurs de repli échouent, retourne False."""
        async def always_raise(*args, **kwargs):
            raise Exception("Not found")

        page = make_page_mock(selector_counts={})  # tous à 0
        page.wait_for_selector = AsyncMock(side_effect=always_raise)
        page.mouse.click = AsyncMock(side_effect=always_raise)
        self.automator._page = page

        result = await self.automator.click_with_verification("test_button", verify_timeout=0.1)
        self.assertFalse(result)

    async def test_click_no_validation_selector_accepts_click(self):
        """Si aucun sélecteur de validation n'est défini, le clic est accepté sans vérification."""
        import json
        tmp2 = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        data = {
            "actions": {
                "no_validation_btn": {
                    "x": 50,
                    "y": 50,
                    "fallback_selectors": [],
                    "validation": {"selector": ""},
                }
            }
        }
        json.dump(data, tmp2, ensure_ascii=False)
        tmp2.close()

        from services.gemini_web_automator import UIMapManager
        self.automator.ui_map = UIMapManager(path=tmp2.name)

        page = make_page_mock()
        self.automator._page = page

        result = await self.automator.click_with_verification("no_validation_btn")
        self.assertTrue(result)
        page.mouse.click.assert_awaited_once_with(50, 50)
        os.unlink(tmp2.name)


# ──────────────────────────────────────────────────────────────────────────────
# Tests de polling de fin de recherche
# ──────────────────────────────────────────────────────────────────────────────

class TestResearchCompletionPolling(unittest.IsolatedAsyncioTestCase):
    """Tests du polling non-bloquant de détection de fin de recherche."""

    def _make_automator_with_page(self, page):
        from services.gemini_web_automator import GeminiWebAutomator, UIMapManager
        automator = GeminiWebAutomator()

        # Injecte un UI map minimal
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        data = {
            "actions": {
                "research_completion": {
                    "fallback_selectors": ["model-response", ".final-response"],
                    "absence_selectors": [".spinner", ".thinking"],
                    "validation": {"selector": "model-response"},
                }
            }
        }
        json.dump(data, tmp, ensure_ascii=False)
        tmp.close()
        automator.ui_map = UIMapManager(path=tmp.name)
        automator._page = page
        self._tmp_path = tmp.name
        return automator

    async def asyncTearDown(self):
        try:
            os.unlink(self._tmp_path)
        except Exception:
            pass

    async def test_polling_detects_completion(self):
        """Le polling retourne True dès que les spinners disparaissent et la réponse est présente."""
        call_seq = {"n": 0}

        def mock_locator(selector):
            call_seq["n"] += 1
            # Après le 3e appel : spinner disparaît, réponse présente
            if call_seq["n"] <= 2:
                if ".spinner" in selector or ".thinking" in selector:
                    return make_locator_mock(count=1)
                return make_locator_mock(count=0)
            else:
                if ".spinner" in selector or ".thinking" in selector:
                    return make_locator_mock(count=0)
                return make_locator_mock(count=1)

        page = make_page_mock()
        page.locator = MagicMock(side_effect=mock_locator)

        automator = self._make_automator_with_page(page)

        # Accélère le polling pour le test
        import services.gemini_web_automator as mod
        original_interval = mod.RESEARCH_POLL_INTERVAL
        mod.RESEARCH_POLL_INTERVAL = 0.05

        try:
            result = await asyncio.wait_for(
                automator._wait_for_research_completion(),
                timeout=5.0
            )
        finally:
            mod.RESEARCH_POLL_INTERVAL = original_interval

        self.assertTrue(result)

    async def test_polling_timeout_returns_false(self):
        """Le polling retourne False après le délai maximum."""
        page = make_page_mock(selector_counts={".spinner": 1})  # spinner toujours présent

        automator = self._make_automator_with_page(page)

        import services.gemini_web_automator as mod
        orig_poll = mod.RESEARCH_POLL_INTERVAL
        orig_max = mod.RESEARCH_MAX_WAIT
        mod.RESEARCH_POLL_INTERVAL = 0.05
        mod.RESEARCH_MAX_WAIT = 0.2  # timeout très court pour le test

        try:
            result = await asyncio.wait_for(
                automator._wait_for_research_completion(),
                timeout=5.0
            )
        finally:
            mod.RESEARCH_POLL_INTERVAL = orig_poll
            mod.RESEARCH_MAX_WAIT = orig_max

        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests de livraison conditionnelle
# ──────────────────────────────────────────────────────────────────────────────

class TestDeliveryRouting(unittest.IsolatedAsyncioTestCase):
    """Tests du routage livrable selon l'état de connexion du PC."""

    def _make_automator(self):
        from services.gemini_web_automator import GeminiWebAutomator, UIMapManager
        automator = GeminiWebAutomator()
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"actions": {}}, tmp)
        tmp.close()
        automator.ui_map = UIMapManager(path=tmp.name)
        self._tmp_path = tmp.name
        return automator

    async def asyncTearDown(self):
        try:
            os.unlink(self._tmp_path)
        except Exception:
            pass

    async def test_deliver_to_screen_when_pc_online(self):
        """_deliver_result appelle _deliver_to_screen si le PC est connecté."""
        automator = self._make_automator()

        with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
             patch.object(automator, "_deliver_to_screen", new_callable=AsyncMock) as mock_screen, \
             patch.object(automator, "_deliver_by_email", new_callable=AsyncMock) as mock_email:
            mock_screen.return_value = {"delivery_mode": "screen", "status": "success"}
            await automator._deliver_result("https://gemini.google.com/canvas/xxx", None, "IA médicale")
            mock_screen.assert_awaited_once()
            mock_email.assert_not_awaited()

    async def test_deliver_by_email_when_pc_offline(self):
        """_deliver_result appelle _deliver_by_email si le PC est hors ligne."""
        automator = self._make_automator()

        with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
             patch.object(automator, "_deliver_to_screen", new_callable=AsyncMock) as mock_screen, \
             patch.object(automator, "_deliver_by_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = {"delivery_mode": "email", "status": "sent"}
            await automator._deliver_result(None, "/tmp/snapshot.html", "IA médicale")
            mock_email.assert_awaited_once()
            mock_screen.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────────────
# Tests de l'interface non-bloquante GeminiDeepResearchEngine
# ──────────────────────────────────────────────────────────────────────────────

class TestGeminiDeepResearchEngine(unittest.IsolatedAsyncioTestCase):
    """Tests de l'interface non-bloquante de GeminiDeepResearchEngine."""

    def _make_engine(self):
        from services.gemini_web_automator import GeminiDeepResearchEngine
        return GeminiDeepResearchEngine()

    async def test_launch_returns_immediately(self):
        """launch() retourne immédiatement {status: launched_in_background}."""
        engine = self._make_engine()

        # Mock le run_deep_research pour éviter d'appeler le vrai CDP
        async def mock_run(*args, **kwargs):
            await asyncio.sleep(10)  # simule une longue recherche
            return {"status": "completed"}

        with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new=mock_run):
            start = time.time()
            result = await engine.launch(topic="Intelligence artificielle médicale")
            elapsed = time.time() - start

        self.assertLess(elapsed, 1.0, "launch() doit retourner en moins de 1 seconde")
        self.assertEqual(result["status"], "launched_in_background")
        self.assertIn("topic", result)

        # Nettoyage : annule la tâche de fond
        if engine._current_task and not engine._current_task.done():
            engine._current_task.cancel()
            try:
                await engine._current_task
            except asyncio.CancelledError:
                pass

    async def test_launch_blocks_duplicate(self):
        """launch() refuse de démarrer une 2e recherche si une est déjà en cours."""
        engine = self._make_engine()

        async def mock_run(*args, **kwargs):
            await asyncio.sleep(10)
            return {"status": "completed"}

        with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new=mock_run):
            await engine.launch(topic="Sujet A")
            result2 = await engine.launch(topic="Sujet B")

        self.assertEqual(result2["status"], "already_running")

        if engine._current_task and not engine._current_task.done():
            engine._current_task.cancel()
            try:
                await engine._current_task
            except asyncio.CancelledError:
                pass

    async def test_is_running_false_by_default(self):
        """is_running() retourne False lorsqu'aucune recherche n'est en cours."""
        engine = self._make_engine()
        self.assertFalse(engine.is_running())

    async def test_is_running_true_during_task(self):
        """is_running() retourne True pendant l'exécution d'une recherche."""
        engine = self._make_engine()

        async def mock_run(*args, **kwargs):
            await asyncio.sleep(10)
            return {"status": "completed"}

        with patch("services.gemini_web_automator.GeminiWebAutomator.run_deep_research", new=mock_run):
            await engine.launch(topic="Test running state")
            self.assertTrue(engine.is_running())

        if engine._current_task and not engine._current_task.done():
            engine._current_task.cancel()
            try:
                await engine._current_task
            except asyncio.CancelledError:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Test d'intégration : launch_deep_research_gemini_web (via deep_research_service)
# ──────────────────────────────────────────────────────────────────────────────

class TestLaunchDeepResearchGeminiWeb(unittest.IsolatedAsyncioTestCase):
    """Teste le point d'entrée unifié dans deep_research_service.py."""

    async def test_delegates_to_browser_agent_recipe(self):
        """launch_deep_research_gemini_web() délègue au Browser Agent local (recipe gemini_deep_research)."""
        from services.deep_research_service import launch_deep_research_gemini_web

        fake_browser_res = MagicMock()
        fake_browser_res.is_success = True
        fake_browser_res.to_dict.return_value = {"status": "done", "recipe": "gemini_deep_research"}

        with patch("services.browser_agent.loop.run_browser_task",
                   new_callable=AsyncMock, return_value=fake_browser_res) as mock_run:
            result = await launch_deep_research_gemini_web("IA spatiale")

        self.assertEqual(result["status"], "success")
        self.assertTrue(str(result["task_id"]).startswith("bt_dr_"))
        mock_run.assert_awaited_once()
        called_task = mock_run.await_args.args[0]
        self.assertEqual(called_task.recipe, "gemini_deep_research")
        self.assertEqual(called_task.goal, "IA spatiale")

    async def test_legacy_engine_flag(self):
        """use_legacy_engine=True retourne legacy_engine sans appeler GeminiWebAutomator."""
        from services.deep_research_service import launch_deep_research_gemini_web

        with patch("services.gemini_web_automator.gemini_deep_research_engine.launch",
                   new_callable=AsyncMock) as mock_launch:
            result = await launch_deep_research_gemini_web("Test", use_legacy_engine=True)

        self.assertEqual(result["status"], "legacy_engine")
        mock_launch.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
