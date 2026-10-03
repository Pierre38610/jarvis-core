"""tests/unit/test_auth_jwt.py
Tests unitaires pour services.auth_service.AuthService et auth.py.
Vérifie la génération, validation cryptographique, expiration, révocation
et migration transparente des tokens JWT sans aucun appel réseau.
"""

import os
import time
import json
import pytest
import jwt
from unittest.mock import patch, MagicMock

import config
import auth
from services.auth_service import AuthService, auth_service


@pytest.fixture
def clean_auth_service():
    """Crée une instance isolée d'AuthService avec une clé secrète dédiée."""
    service = AuthService()
    service.secret_key = "test_super_secret_jwt_key_stark_industries_qa_suite"
    service._revoked_tokens_memory = set()
    service._qr_tickets_memory = {}
    service._migrated_tokens_cache = {}
    return service


class TestJWTGenerationAndValidation:
    """Génération et validation cryptographique des tokens HS256."""

    def test_generate_token_structure(self, clean_auth_service):
        """Vérifie la présence et la cohérence de tous les claims JWT."""
        token = clean_auth_service.generate_token(
            device_id="iphone_pierre",
            device_name="iPhone 15 Pro",
            role="admin",
            custom_claims={"user_tag": "stark_prime"},
            expiry_days=30
        )
        assert isinstance(token, str)
        assert len(token) > 50

        # Décoder le token avec la clé du service
        payload = jwt.decode(token, clean_auth_service.secret_key, algorithms=["HS256"])
        assert payload["device_id"] == "iphone_pierre"
        assert payload["device_name"] == "iPhone 15 Pro"
        assert payload["role"] == "admin"
        assert payload["user_tag"] == "stark_prime"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_verify_valid_token_sync_and_async(self, clean_auth_service):
        """Un token valide est décodé et validé avec succès."""
        token = clean_auth_service.generate_token(
            device_id="device_valid",
            device_name="Valid Device"
        )

        # Synchrone
        payload_sync = clean_auth_service.verify_token_sync(token)
        assert payload_sync is not None
        assert payload_sync["device_id"] == "device_valid"

        # Asynchrone
        import asyncio
        payload_async = asyncio.run(clean_auth_service.verify_token(token))
        assert payload_async is not None
        assert payload_async["device_id"] == "device_valid"

    def test_invalid_signature_rejected(self, clean_auth_service):
        """Un token signé avec une autre clé secrète doit être immédiatement rejeté."""
        fake_payload = {
            "device_id": "hacker_device",
            "role": "admin",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "jti": "fake_jti"
        }
        forged_token = jwt.encode(fake_payload, "wrong_secret_key", algorithm="HS256")

        assert clean_auth_service.verify_token_sync(forged_token) is None

    def test_malformed_token_rejected(self, clean_auth_service):
        """Chaîne arbitraire ou corrompue rejetée."""
        assert clean_auth_service.verify_token_sync("not.a.valid.jwt.token") is None
        assert clean_auth_service.verify_token_sync("") is None
        assert clean_auth_service.verify_token_sync(None) is None

    def test_master_password_accepted_as_token(self, clean_auth_service):
        """Le mot de passe maître ACCESS_PASSWORD est accepté pour l'agent local Windows."""
        master_pwd = getattr(config, "ACCESS_PASSWORD", "test_master_pwd")
        payload = clean_auth_service.verify_token_sync(master_pwd)

        assert payload is not None
        assert payload["device_id"] == "master-local-agent"
        assert payload["role"] == "admin"


class TestJWTExpiration:
    """Gestion rigoureuse de l'expiration temporelle des tokens."""

    def test_expired_token_rejected(self, clean_auth_service):
        """Un token émis dans le passé est rejeté sans exception non gérée."""
        expired_token = clean_auth_service.generate_token(
            device_id="device_expired",
            expiry_days=-2  # Expiré il y a 2 jours
        )
        assert clean_auth_service.verify_token_sync(expired_token) is None

    @pytest.mark.asyncio
    async def test_expired_token_async_rejected(self, clean_auth_service):
        expired_token = clean_auth_service.generate_token(
            device_id="device_expired_async",
            expiry_days=-1
        )
        res = await clean_auth_service.verify_token(expired_token)
        assert res is None


class TestJWTRevocation:
    """Révocation unitaire (jti) et révocation globale par appareil (device_id)."""

    def test_revoke_token_by_jti(self, clean_auth_service):
        """La révocation d'un jti rend le token invalide immédiatement."""
        token = clean_auth_service.generate_token(
            device_id="device_to_revoke",
            device_name="Device To Revoke"
        )
        payload = clean_auth_service.verify_token_sync(token)
        assert payload is not None
        jti = payload["jti"]

        # Révocation du jti
        clean_auth_service.revoke_token_sync(jti)
        assert clean_auth_service.is_token_revoked_sync(jti) is True

        # Après révocation, verify_token_sync doit renvoyer None
        assert clean_auth_service.verify_token_sync(token) is None

    @pytest.mark.asyncio
    async def test_revoke_token_async(self, clean_auth_service):
        """Révocation asynchrone via revoke_token()."""
        token = clean_auth_service.generate_token(device_id="dev_async_rev")
        payload = await clean_auth_service.verify_token(token)
        assert payload is not None
        jti = payload["jti"]

        await clean_auth_service.revoke_token(jti)
        assert await clean_auth_service.is_token_revoked(jti) is True
        assert await clean_auth_service.verify_token(token) is None

    def test_revoke_device_blocks_all_device_tokens(self, clean_auth_service):
        """Révoquer un device_id bloque tous les tokens émis pour cet appareil."""
        token1 = clean_auth_service.generate_token(device_id="tablet_compromised")
        token2 = clean_auth_service.generate_token(device_id="tablet_compromised")

        clean_auth_service.revoke_device_sync("tablet_compromised")

        assert clean_auth_service.verify_token_sync(token1) is None
        assert clean_auth_service.verify_token_sync(token2) is None


class TestLegacyTokenMigration:
    """Migration transparente des anciens tokens authorized_devices.json vers JWT."""

    def test_transparent_migration_of_legacy_token(self, clean_auth_service):
        """Présenter un ancien token plat le convertit en JWT et supprime le token en clair."""
        import os
        scratch_dir = os.path.join(config.BASE_DIR, "tests", "_test_scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        auth_file = os.path.join(scratch_dir, "test_legacy_authorized_devices.json")
        legacy_token = "legacy_secret_device_token_xyz"
        legacy_data = {
            "tokens": {
                legacy_token: {
                    "name": "Ancien iPad Pierre",
                    "user_agent": "Mozilla/5.0 Mobile",
                    "client_ip": "192.168.1.42",
                    "created_at": "2025-01-01T00:00:00"
                }
            }
        }
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f, ensure_ascii=False)

        try:
            with patch.object(config, "AUTH_FILE", auth_file):
                # 1. Vérification avec l'ancien token
                payload = clean_auth_service.verify_token_sync(legacy_token)
                assert payload is not None
                assert payload.get("_migrated") is True
                assert "_new_token" in payload
                new_jwt = payload["_new_token"]

                # Le nouveau token est un JWT valide
                decoded = jwt.decode(new_jwt, clean_auth_service.secret_key, algorithms=["HS256"])
                assert decoded["device_name"] == "Ancien iPad Pierre"

                # 2. L'ancien token doit avoir été purgé du fichier JSON
                with open(auth_file, "r", encoding="utf-8") as f:
                    remaining = json.load(f).get("tokens", {})
                assert legacy_token not in remaining

                # 3. Le cache de migration répond lors d'appels répétés rapides
                payload_cached = clean_auth_service.verify_token_sync(legacy_token)
                assert payload_cached is not None
                assert payload_cached.get("_migrated") is True
        finally:
            if os.path.exists(auth_file):
                os.remove(auth_file)


class TestAuthFacade:
    """Vérifie la façade auth.py déléguant à auth_service."""

    def test_facade_is_device_authorized(self, test_jwt_token):
        """auth.is_device_authorized fonctionne correctement avec un JWT."""
        assert auth.is_device_authorized(test_jwt_token) is True
        assert auth.is_device_authorized("invalid_token_xyz") is False
        assert auth.is_device_authorized(None) is False

    @pytest.mark.asyncio
    async def test_facade_is_device_authorized_async(self, test_jwt_token):
        """auth.is_device_authorized_async."""
        assert await auth.is_device_authorized_async(test_jwt_token) is True
        assert await auth.is_device_authorized_async("bad_token") is False


class TestConfigAndDbRevocation:
    """Révocation par configuration et table SQLite."""

    def test_revocation_via_config_set(self, clean_auth_service):
        token = clean_auth_service.generate_token(device_id="esp32_revoked_by_config")
        assert clean_auth_service.verify_token_sync(token) is not None

        with patch.object(config, "REVOKED_DEVICE_IDS", {"esp32_revoked_by_config"}):
            assert clean_auth_service.verify_token_sync(token) is None
            assert clean_auth_service.is_token_revoked_sync("any_jti", "esp32_revoked_by_config") is True

    def test_revocation_via_sqlite_db(self, clean_auth_service):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_file = f.name

        try:
            token = clean_auth_service.generate_token(device_id="esp32_db_banned")
            assert clean_auth_service.verify_token_sync(token) is not None

            with patch.object(config, "DB_PATH", db_file):
                # Enregistrer la révocation dans la DB
                clean_auth_service.revoke_device_in_db("esp32_db_banned", reason="Device compromis")
                assert clean_auth_service.verify_token_sync(token) is None
                assert clean_auth_service.is_token_revoked_sync("any_jti", "esp32_db_banned") is True
        finally:
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                except Exception:
                    pass


class TestDeviceVoiceWSAuth:
    """Authentification stricte de l'enceinte connectée /ws/device."""

    @pytest.mark.asyncio
    async def test_rejects_without_token(self):
        from routers.device_voice import _authenticate_device_ws
        from unittest.mock import MagicMock
        ws = MagicMock()
        ws.headers = {"device-id": "74:3a:f4:c6:8e:9b"}
        ws.query_params = {}
        res = await _authenticate_device_ws(ws)
        assert res is None

    @pytest.mark.asyncio
    async def test_accepts_bearer_token(self):
        from routers.device_voice import _authenticate_device_ws
        from services.auth_service import auth_service
        from unittest.mock import MagicMock
        token = auth_service.generate_token(device_id="esp32_speaker_test", role="device", expiry_days=365)
        ws = MagicMock()
        ws.headers = {"authorization": f"Bearer {token}"}
        ws.query_params = {}
        res = await _authenticate_device_ws(ws)
        assert res is not None
        assert res.get("device_id") == "esp32_speaker_test"

    @pytest.mark.asyncio
    async def test_accepts_query_param_token_compat(self):
        from routers.device_voice import _authenticate_device_ws
        from services.auth_service import auth_service
        from unittest.mock import MagicMock
        token = auth_service.generate_token(device_id="esp32_compat", role="device", expiry_days=365)
        ws = MagicMock()
        ws.headers = {}
        ws.query_params = {"token": token}
        res = await _authenticate_device_ws(ws)
        assert res is not None
        assert res.get("device_id") == "esp32_compat"

