import sys
import os
import unittest

# Ensure jarvis-core is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import config
from google_antigravity import resolve_antigravity_model, AntigravityAgent
from services.reasoning_service import run_deep_reasoning
from services.supervision_service import supervision_service

class TestPaidKeyAuthorization(unittest.TestCase):

    def setUp(self):
        # Save previous state
        self.original_auth = config.is_paid_key_authorized()

    def tearDown(self):
        # Restore previous state
        config.set_paid_key_authorized(self.original_auth)

    def test_config_persistence(self):
        """Test that set_paid_key_authorized persists across calls"""
        config.set_paid_key_authorized(False)
        self.assertFalse(config.is_paid_key_authorized())
        self.assertEqual(config.get_effective_paid_key(), "")
        self.assertFalse(config.is_paid_key_active())

        config.set_paid_key_authorized(True)
        self.assertTrue(config.is_paid_key_authorized())
        if config.GEMINI_API_KEY_PAID:
            self.assertEqual(config.get_effective_paid_key(), config.GEMINI_API_KEY_PAID)
            self.assertTrue(config.is_paid_key_active())

    def test_antigravity_model_resolution_when_unauthorized(self):
        """When unauthorized, paid key cannot be resolved for heavy models"""
        config.set_paid_key_authorized(False)
        
        # Heavy model endpoint should resolve with free key
        target, label = resolve_antigravity_model("gemini-3.1-pro-high")
        self.assertEqual(target.endpoint.api_key, config.GEMINI_API_KEY_FREE)

        # Antigravity agent cannot use paid key if unauthorized
        agent = AntigravityAgent(
            workspace="./tmp_test",
            api_key=config.GEMINI_API_KEY_PAID or "fake_paid_key_xyz",
            allowed_tools=[]
        )
        self.assertNotEqual(agent.api_key, "fake_paid_key_xyz")
        self.assertEqual(agent.api_key, config.GEMINI_API_KEY_FREE)

    def test_deep_reasoning_unauthorized_blocks_heavy_models(self):
        """When unauthorized, run_deep_reasoning with heavy model returns requires_checkbox"""
        config.set_paid_key_authorized(False)
        
        res = asyncio.run(run_deep_reasoning(
            question="Analyse l'architecture du projet",
            model_choice="gemini-3.1-pro-high"
        ))
        self.assertEqual(res.get("status"), "requires_user_confirmation")
        self.assertTrue(res.get("requires_checkbox"))
        self.assertIn("coche", res.get("message", "").lower())

    def test_supervision_overview_reflects_toggle(self):
        """Supervision overview must accurately reflect the checkbox state"""
        config.set_paid_key_authorized(False)
        overview_locked = supervision_service.get_full_overview()
        self.assertFalse(overview_locked["paid_key_authorized"])
        self.assertFalse(overview_locked["api_keys"]["paid_key"]["authorized"])
        self.assertIn("VERROUILLÉE", overview_locked["api_keys"]["paid_key"]["status_label"])

        config.set_paid_key_authorized(True)
        overview_auth = supervision_service.get_full_overview()
        self.assertTrue(overview_auth["paid_key_authorized"])
        self.assertTrue(overview_auth["api_keys"]["paid_key"]["authorized"])
        self.assertIn("AUTORISÉE", overview_auth["api_keys"]["paid_key"]["status_label"])

    def test_rest_api_endpoints(self):
        """Test GET and POST /api/settings/paid-key"""
        from starlette.testclient import TestClient
        import auth
        from App import app

        test_token = "test_token_paid_key_check"
        auth.save_authorized_device(test_token, {"name": "TestDevice"})

        client = TestClient(app, cookies={"jarvis_device_token": test_token})

        # 1. Set to false via POST
        res = client.post("/api/settings/paid-key", json={"authorized": False})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertFalse(data["authorized"])
        self.assertFalse(config.is_paid_key_authorized())

        # 2. Check via GET
        res_get = client.get("/api/settings/paid-key")
        self.assertEqual(res_get.status_code, 200)
        self.assertFalse(res_get.json()["authorized"])

        # 3. Set to true via POST
        res_post = client.post("/api/settings/paid-key", json={"authorized": True})
        self.assertEqual(res_post.status_code, 200)
        self.assertTrue(res_post.json()["authorized"])
        self.assertTrue(config.is_paid_key_authorized())

if __name__ == "__main__":
    unittest.main()

