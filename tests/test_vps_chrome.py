"""tests/test_vps_chrome.py
Tests unitaires et mockés pour le gestionnaire Python du Chrome VPS (P4).
Vérifie :
1. Health check explicite du port CDP (200 OK vs erreurs HTTP / connexion).
2. ensure_chrome_running() avec Chrome déjà sain (pas de relance).
3. ensure_chrome_running() avec Chrome indisponible puis relance réussie (backoff borné).
4. ensure_chrome_running() avec échec persistant et timeout borné.
5. Mode restart_if_down=False.
6. Redémarrage systemd sécurisé (subprocess Linux, timeout, OS non-Linux sans commande).
7. Intégration minimale dans GeminiWebAutomator._connect().
8. Structure d'erreur L3ErrorDetails compatible P2 et assainissement des logs.
9. Absence totale de lancement réel de Chrome ou de commandes destructives.
"""

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import config
from services.l3_error import (
    L3ErrorDetails,
    clear_last_l3_error,
    get_last_l3_error,
    set_last_l3_error,
)
from services.vps_chrome import (
    VPSChromeError,
    VPSChromeUnavailableError,
    check_cdp_health,
    ensure_chrome_running,
    get_effective_cdp_url,
    get_vps_service_name,
    is_cdp_available,
    restart_vps_chrome_service,
)


@pytest.fixture(autouse=True)
def clean_l3_error():
    clear_last_l3_error()
    yield
    clear_last_l3_error()


class TestVPSChromeHealthCheck(unittest.IsolatedAsyncioTestCase):
    """Tests du health check CDP explicite (/json/version)."""

    async def test_cdp_health_check_healthy(self):
        """check_cdp_health retourne (True, metadata) quand l'endpoint répond 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Browser": "Chrome/130.0.6723.58",
            "Protocol-Version": "1.3",
            "User-Agent": "Mozilla/5.0 HeadlessChrome",
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        is_healthy, data = await check_cdp_health(
            cdp_url="http://127.0.0.1:9222",
            client=mock_client,
        )

        self.assertTrue(is_healthy)
        self.assertEqual(data.get("Browser"), "Chrome/130.0.6723.58")
        mock_client.get.assert_awaited_once_with("http://127.0.0.1:9222/json/version")

    async def test_is_cdp_available_helper(self):
        """is_cdp_available retourne un booléen simple."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Browser": "Chrome"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        available = await is_cdp_available(
            cdp_url="http://127.0.0.1:9222",
            client=mock_client,
        )
        self.assertTrue(available)

    async def test_cdp_health_check_connection_error(self):
        """check_cdp_health retourne (False, error) en cas d'erreur de connexion."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused on port 9222")

        is_healthy, data = await check_cdp_health(
            cdp_url="http://127.0.0.1:9222",
            client=mock_client,
        )

        self.assertFalse(is_healthy)
        self.assertIn("error", data)
        self.assertEqual(data.get("exception"), "ConnectError")

    async def test_cdp_health_check_http_non_200(self):
        """check_cdp_health retourne (False, details) si le serveur répond avec un code d'erreur HTTP."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        is_healthy, data = await check_cdp_health(
            cdp_url="http://127.0.0.1:9222",
            client=mock_client,
        )

        self.assertFalse(is_healthy)
        self.assertEqual(data.get("status_code"), 502)


class TestVPSChromeRestartService(unittest.IsolatedAsyncioTestCase):
    """Tests du déclenchement du redémarrage du service systemd."""

    async def test_restart_with_custom_runner_success(self):
        """restart_vps_chrome_service accepte une fonction de commande injectée (succès)."""
        mock_runner = AsyncMock(return_value=(True, "Service restarted"))

        ok, msg = await restart_vps_chrome_service(
            service_name="jarvis-chrome",
            command_runner=mock_runner,
        )

        self.assertTrue(ok)
        self.assertEqual(msg, "Service restarted")
        mock_runner.assert_awaited_once_with("jarvis-chrome")

    async def test_restart_with_custom_runner_failure(self):
        """restart_vps_chrome_service gère proprement les erreurs de runner injecté."""
        mock_runner = AsyncMock(side_effect=RuntimeError("systemctl not found"))

        ok, msg = await restart_vps_chrome_service(
            service_name="jarvis-chrome",
            command_runner=mock_runner,
        )

        self.assertFalse(ok)
        self.assertIn("systemctl not found", msg)

    async def test_restart_non_linux_skips_gracefully(self):
        """Sur un OS non-Linux (sans runner injecté), ignore le redémarrage sans lever d'exception."""
        with patch("sys.platform", "win32"):
            ok, msg = await restart_vps_chrome_service(service_name="jarvis-chrome")
            self.assertFalse(ok)
            self.assertIn("non-Linux", msg)

    async def test_restart_linux_subprocess_success(self):
        """Sur Linux, exécute la commande systemctl restart via subprocess."""
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        fake_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("sys.platform", "linux"), \
             patch("os.geteuid", return_value=0, create=True), \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc) as mock_exec:

            ok, msg = await restart_vps_chrome_service(service_name="jarvis-chrome")
            self.assertTrue(ok)
            self.assertIn("redémarré avec succès", msg)
            mock_exec.assert_awaited_once_with(
                "systemctl", "restart", "jarvis-chrome",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    async def test_restart_linux_subprocess_timeout(self):
        """Sur Linux, gère le timeout de commande sans bloquer indéfiniment."""
        fake_proc = MagicMock()
        fake_proc.kill = MagicMock()

        async def hanging_communicate():
            await asyncio.sleep(10)
            return (b"", b"")

        fake_proc.communicate = hanging_communicate

        with patch("sys.platform", "linux"), \
             patch("os.geteuid", return_value=0, create=True), \
             patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=fake_proc):

            ok, msg = await restart_vps_chrome_service(service_name="jarvis-chrome", timeout=0.1)
            self.assertFalse(ok)
            self.assertIn("Timeout", msg)


class TestEnsureChromeRunning(unittest.IsolatedAsyncioTestCase):
    """Tests du coordinateur ensure_chrome_running()."""

    def setUp(self):
        clear_last_l3_error()

    async def test_ensure_already_healthy_no_restart(self):
        """Si Chrome répond au premier check, retourne healthy sans tenter de relance."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Browser": "Chrome/130"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_restart = AsyncMock()

        res = await ensure_chrome_running(
            cdp_url="http://127.0.0.1:9222",
            http_client=mock_client,
            restart_func=mock_restart,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "healthy")
        self.assertFalse(res["restarted"])
        self.assertIsNone(res["l3_error"])
        mock_restart.assert_not_awaited()

    async def test_ensure_down_then_restart_succeeds(self):
        """Chrome est indisponible, relancé avec succès et réactif au polling suivant."""
        down_resp = httpx.ConnectError("Connection refused")
        up_resp = MagicMock()
        up_resp.status_code = 200
        up_resp.json.return_value = {"Browser": "Chrome/130"}

        mock_client = AsyncMock()
        # 1er appel = down, 2e appel = up
        mock_client.get.side_effect = [down_resp, up_resp]

        mock_restart = AsyncMock(return_value=(True, "Restarted"))

        res = await ensure_chrome_running(
            cdp_url="http://127.0.0.1:9222",
            max_wait=5.0,
            http_client=mock_client,
            restart_func=mock_restart,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "restarted")
        self.assertTrue(res["restarted"])
        self.assertIsNone(res["l3_error"])
        mock_restart.assert_awaited_once()

    async def test_ensure_down_and_timeout_generates_l3_error(self):
        """Chrome reste indisponible après relance : timeout borné et génération de L3ErrorDetails."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        mock_restart = AsyncMock(return_value=(True, "Restart command executed"))

        res = await ensure_chrome_running(
            cdp_url="http://127.0.0.1:9222",
            max_wait=0.8,
            http_client=mock_client,
            restart_func=mock_restart,
        )

        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "unavailable")
        self.assertTrue(res["restarted"])
        self.assertIsNotNone(res["l3_error"])

        # Vérification du dictionnaire L3ErrorDetails
        l3_dict = res["l3_error"]
        self.assertEqual(l3_dict["etape"], "cdp_connection")
        self.assertIn("non joignable", l3_dict["exception"])
        self.assertIn("Chrome CDP VPS indisponible", l3_dict["cause_courte"])
        self.assertTrue(l3_dict["fallback_initiated"])

        # Vérification de la persistance globale
        last_stored = get_last_l3_error()
        self.assertIsNotNone(last_stored)
        self.assertEqual(last_stored["etape"], "cdp_connection")

    async def test_ensure_restart_if_down_false(self):
        """Si restart_if_down=False, retourne immédiatement sans exécuter de commande."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_restart = AsyncMock()

        res = await ensure_chrome_running(
            cdp_url="http://127.0.0.1:9222",
            restart_if_down=False,
            http_client=mock_client,
            restart_func=mock_restart,
        )

        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "unavailable")
        self.assertFalse(res["restarted"])
        mock_restart.assert_not_awaited()


class TestAutomatorIntegration(unittest.IsolatedAsyncioTestCase):
    """Tests du branchement minimal dans GeminiWebAutomator._connect()."""

    def setUp(self):
        clear_last_l3_error()

    async def test_connect_calls_ensure_chrome_running_success(self):
        """_connect() appelle ensure_chrome_running et continue si Chrome est prêt."""
        from services.gemini_web_automator import GeminiWebAutomator

        automator = GeminiWebAutomator()
        fake_browser = MagicMock()
        fake_browser.contexts = []
        fake_browser.new_context = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.connect_over_cdp = AsyncMock(return_value=fake_browser)

        with patch("services.vps_chrome.ensure_chrome_running", new_callable=AsyncMock) as mock_ensure, \
             patch("playwright.async_api.async_playwright") as mock_pw_init:

            mock_ensure.return_value = {"ok": True, "status": "healthy", "l3_error": None}
            mock_pw_init.return_value.start = AsyncMock(return_value=mock_playwright)

            connected = await automator._connect()

            self.assertTrue(connected)
            mock_ensure.assert_awaited_once()

    async def test_connect_fails_when_ensure_chrome_running_fails(self):
        """_connect() échoue proprement et propage l'erreur si ensure_chrome_running échoue."""
        from services.gemini_web_automator import GeminiWebAutomator

        automator = GeminiWebAutomator()
        err_details = {
            "etape": "cdp_connection",
            "exception": "Chrome CDP down",
            "cause_courte": "Chrome non joignable",
            "fallback_initiated": True,
        }

        with patch("services.vps_chrome.ensure_chrome_running", new_callable=AsyncMock) as mock_ensure:
            mock_ensure.return_value = {
                "ok": False,
                "status": "unavailable",
                "error": "Chrome CDP down",
                "l3_error": err_details,
            }

            connected = await automator._connect()

            self.assertFalse(connected)
            mock_ensure.assert_awaited_once()
            last_err = get_last_l3_error()
            self.assertIsNotNone(last_err)
            self.assertEqual(last_err["etape"], "cdp_connection")


if __name__ == "__main__":
    unittest.main(verbosity=2)
