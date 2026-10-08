"""tests/unit/test_version_sync.py
Tests unitaires vérifiant l'alignement central de la version et le bon fonctionnement de /api/version.
"""
import pytest
from httpx import AsyncClient, ASGITransport
import config
from App import app
from sync_deploy import sync_and_verify_versions


@pytest.mark.asyncio
async def test_get_version_endpoint():
    """Vérifie que l'endpoint /api/version renvoie la version déclarée dans config.APP_VERSION."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["version"] == getattr(config, "APP_VERSION", "5.93.0")
        assert "J.A.R.V.I.S." in data["app"]


def test_sync_and_verify_versions_dry():
    """Vérifie que sync_and_verify_versions renvoie bien la version courante."""
    ver = sync_and_verify_versions()
    assert ver == config.APP_VERSION
