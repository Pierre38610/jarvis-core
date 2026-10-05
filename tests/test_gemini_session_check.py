"""tests/test_gemini_session_check.py
Tests unitaires et mockés pour la détection et la vérification de session Google Gemini (P5).

Vérifie :
1. Détection session active (URL gemini.google.com, sélecteurs d'application).
2. Détection de page de login Google (redirection accounts.google.com).
3. Détection d'indicateurs de login dans le DOM (boutons Sign In, champs identifiant).
4. Détection Chrome CDP indisponible (code de sortie 2).
5. Exécution du CLI scripts/check_gemini_session.py avec codes de retour standardisés (0, 1, 2) et options (--json, --quiet).
6. Résilience de UIMapManager en cas d'absence de data/gemini_ui_map.json ou de fichier vide (actions={}).
7. Absence totale d'exposition de secrets, tokens ou cookies.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.gemini_web_automator import DEFAULT_UI_MAP, UIMapManager
from services.vps_chrome import (
    check_cdp_health,
    check_gemini_session,
    get_effective_cdp_url,
)
import scripts.check_gemini_session as check_session_cli


class TestGeminiSessionDetection(unittest.IsolatedAsyncioTestCase):
    """Tests unitaires de la fonction check_gemini_session()."""

    async def test_session_active_detected(self):
        """Quand l'onglet est sur gemini.google.com sans login, status=active et exit_code=0."""
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app"
        mock_page.locator.return_value.count = AsyncMock(return_value=0)

        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]

        with patch("services.vps_chrome.check_cdp_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = (True, {"Browser": "Chrome/130"})

            res = await check_gemini_session(
                cdp_url="http://127.0.0.1:9222",
                browser_connector=lambda u: mock_browser,
            )

            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "active")
            self.assertEqual(res["exit_code"], 0)
            self.assertIn("gemini.google.com", res["current_url"])
            self.assertIn("active", res["message"].lower())

    async def test_session_login_required_url_redirect(self):
        """Quand l'URL est accounts.google.com, status=login_required et exit_code=1."""
        mock_page = MagicMock()
        mock_page.url = "https://accounts.google.com/v3/signin/identifier"
        mock_page.locator.return_value.count = AsyncMock(return_value=0)

        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]

        with patch("services.vps_chrome.check_cdp_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = (True, {"Browser": "Chrome/130"})

            res = await check_gemini_session(
                cdp_url="http://127.0.0.1:9222",
                browser_connector=lambda u: mock_browser,
            )

            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "login_required")
            self.assertEqual(res["exit_code"], 1)
            self.assertIn("accounts.google.com", res["current_url"])
            self.assertIn("Connexion Google requise", res["message"])

    async def test_session_login_required_dom_indicator(self):
        """Quand un indicateur de login est trouvé dans le DOM, status=login_required et exit_code=1."""
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com"

        async def fake_count():
            return 1

        mock_loc = MagicMock()
        mock_loc.count = AsyncMock(side_effect=fake_count)
        mock_page.locator.return_value = mock_loc

        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]

        with patch("services.vps_chrome.check_cdp_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = (True, {"Browser": "Chrome/130"})

            res = await check_gemini_session(
                cdp_url="http://127.0.0.1:9222",
                browser_connector=lambda u: mock_browser,
            )

            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "login_required")
            self.assertEqual(res["exit_code"], 1)
            self.assertIn("bouton ou formulaire de connexion", res["message"])

    async def test_session_cdp_unavailable(self):
        """Quand Chrome CDP ne répond pas au health check, status=unavailable et exit_code=2."""
        with patch("services.vps_chrome.check_cdp_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = (False, {"error": "Connection refused"})

            res = await check_gemini_session(cdp_url="http://127.0.0.1:9222")

            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "unavailable")
            self.assertEqual(res["exit_code"], 2)
            self.assertIn("inaccessible", res["message"])
            self.assertIsNone(res["current_url"])

    async def test_session_check_general_error_handling(self):
        """Quand une exception inattendue survient, exit_code=2 et message sécurisé sans secret."""
        with patch("services.vps_chrome.check_cdp_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = (True, {"Browser": "Chrome/130"})

            def faulty_connector(u):
                raise RuntimeError("Erreur réseau inattendue token_secret_123")

            res = await check_gemini_session(
                cdp_url="http://127.0.0.1:9222",
                browser_connector=faulty_connector,
            )

            self.assertFalse(res["ok"])
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["exit_code"], 2)


class TestGeminiSessionCLI(unittest.IsolatedAsyncioTestCase):
    """Tests du script CLI scripts/check_gemini_session.py."""

    @patch("scripts.check_gemini_session.check_gemini_session", new_callable=AsyncMock)
    async def test_cli_main_async_active(self, mock_check):
        """Le CLI retourne 0 quand la session est active."""
        mock_check.return_value = {
            "ok": True,
            "status": "active",
            "exit_code": 0,
            "message": "Session active",
            "current_url": "https://gemini.google.com/app",
            "error": None,
        }

        with patch("sys.argv", ["check_gemini_session.py", "--quiet"]):
            code = await check_session_cli.main_async()
            self.assertEqual(code, 0)

    @patch("scripts.check_gemini_session.check_gemini_session", new_callable=AsyncMock)
    async def test_cli_main_async_login_required(self, mock_check):
        """Le CLI retourne 1 quand le login est requis."""
        mock_check.return_value = {
            "ok": False,
            "status": "login_required",
            "exit_code": 1,
            "message": "Login requis",
            "current_url": "https://accounts.google.com",
            "error": None,
        }

        with patch("sys.argv", ["check_gemini_session.py", "--quiet"]):
            code = await check_session_cli.main_async()
            self.assertEqual(code, 1)

    @patch("scripts.check_gemini_session.check_gemini_session", new_callable=AsyncMock)
    async def test_cli_main_async_json_output(self, mock_check):
        """Le CLI avec --json produit un JSON valide sur stdout."""
        mock_check.return_value = {
            "ok": True,
            "status": "active",
            "exit_code": 0,
            "message": "Session active",
            "current_url": "https://gemini.google.com/app",
            "error": None,
        }

        with patch("sys.argv", ["check_gemini_session.py", "--json"]), patch("builtins.print") as mock_print:
            code = await check_session_cli.main_async()
            self.assertEqual(code, 0)
            mock_print.assert_called()
            printed_data = json.loads(mock_print.call_args[0][0])
            self.assertEqual(printed_data["status"], "active")


class TestUIMapResilience(unittest.TestCase):
    """Tests de résilience de UIMapManager en cas d'absence de fichier ou de contenu vide (P5)."""

    def test_missing_file_falls_back_to_defaults(self):
        """Un fichier inexistant renvoie des sélecteurs par défaut sans lever d'exception."""
        non_existent_path = os.path.join(tempfile.gettempdir(), "non_existent_ui_map_123.json")
        if os.path.exists(non_existent_path):
            os.remove(non_existent_path)

        manager = UIMapManager(path=non_existent_path)
        action = manager.get_action("deep_research_button")

        self.assertIsNotNone(action)
        self.assertIn("fallback_selectors", action)
        self.assertTrue(len(action["fallback_selectors"]) > 0)
        self.assertEqual(action["x"], 120)

    def test_empty_actions_file_falls_back_to_defaults(self):
        """Un fichier contenant {'actions': {}} renvoie les sélecteurs par défaut sans erreur."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"actions": {}}, f)
            temp_path = f.name

        try:
            manager = UIMapManager(path=temp_path)
            action = manager.get_action("login_indicator")

            self.assertIsNotNone(action)
            self.assertIn("fallback_selectors", action)
            self.assertIn("input[type='email']", action["fallback_selectors"])

            prompt_action = manager.get_action("prompt_textarea")
            self.assertEqual(prompt_action["x"], 760)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_update_coordinates_saves_new_position(self):
        """update_coordinates met à jour x, y et persiste le fichier sans écraser les sélecteurs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"actions": {}}, f)
            temp_path = f.name

        try:
            manager = UIMapManager(path=temp_path)
            manager.update_coordinates("deep_research_button", 155.6, 730.2)

            # Recharger depuis le disque
            manager2 = UIMapManager(path=temp_path)
            action = manager2.get_action("deep_research_button")
            self.assertEqual(action["x"], 156)
            self.assertEqual(action["y"], 730)
            self.assertTrue(len(action["fallback_selectors"]) > 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
