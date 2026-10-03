"""tests/unit/test_mobile_bridge.py
Tests unitaires pour le pont mobile MacroDroid (services/mobile_bridge_service.py)
et son intégration dans le dispatcher et Spotify Connect.
Garantit l'absence totale de fuite de secrets dans les logs et le respect des contrats ToolResult.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import config
from core.tools.dispatcher import dispatch_tool
from services.mobile_bridge_service import BridgeResult, mobile_bridge_service
from services.spotify_service import spotify_service


@pytest.fixture(autouse=True)
def setup_mobile_config(monkeypatch):
    """Configure un device ID de test par défaut."""
    monkeypatch.setattr(config, "MACRODROID_DEVICE_ID", "test_device_uuid_12345")
    monkeypatch.setattr(config, "MACRODROID_BASE_URL", "https://ask.macrodroid.com")


# ─── 1. Succès 200 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_trigger_success_200(monkeypatch):
    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service._trigger("Jarvis_spotify")
    assert res.ok is True
    assert res.status == 200
    assert res.reason == "ok"
    assert mock_client.get.call_count == 1


# ─── 2. Timeout puis retry OK ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_timeout_then_retry_ok(monkeypatch):
    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_client.get = AsyncMock(side_effect=[httpx.TimeoutException("timeout"), mock_resp])
    mock_client.is_closed = False

    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service._trigger("Jarvis_spotify")
    assert res.ok is True
    assert res.status == 200
    assert res.reason == "ok"
    assert mock_client.get.call_count == 2


# ─── 3. 404 → failed (sans retry) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_404_failed_no_retry(monkeypatch):
    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=404, is_success=False)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service._trigger("Jarvis_spotify")
    assert res.ok is False
    assert res.status == 404
    assert res.reason == "HTTP 404"
    assert mock_client.get.call_count == 1


# ─── 4. DEVICE_ID vide → failed sans appel réseau ────────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_empty_device_id_no_network(monkeypatch):
    monkeypatch.setattr(config, "MACRODROID_DEVICE_ID", "")
    mock_client = AsyncMock()
    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service._trigger("Jarvis_spotify")
    assert res.ok is False
    assert res.status is None
    assert res.reason == "pont mobile non configuré"
    assert mock_client.get.called is False


# ─── 5. params "Gare de Malmö" correctement encodés + mode transmis ───────────

@pytest.mark.asyncio
async def test_mobile_bridge_launch_maps_params_and_mode(monkeypatch):
    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service.launch_maps_navigation(destination="Gare de Malmö", mode="walking")
    assert res.ok is True
    mock_client.get.assert_called_once()
    called_url, called_kwargs = mock_client.get.call_args
    assert called_url[0] == "https://ask.macrodroid.com/test_device_uuid_12345/Jarvis maps"
    assert called_kwargs.get("params") == {"dest": "Gare de Malmö", "mode": "walking"}


# ─── 6. mode invalide → driving ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_launch_maps_invalid_mode_defaults_driving(monkeypatch):
    mock_client = AsyncMock()
    mock_resp = MagicMock(status_code=200, is_success=True)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.is_closed = False

    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    res = await mobile_bridge_service.launch_maps_navigation(destination="Paris", mode="teleportation")
    assert res.ok is True
    _, called_kwargs = mock_client.get.call_args
    assert called_kwargs.get("params") == {"dest": "Paris", "mode": "driving"}


# ─── 7. destination vide → failed ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_launch_phone_navigation_empty_destination():
    res = await dispatch_tool("launch_phone_navigation", {"destination": "   "})
    assert res.get("status") == "failed"
    assert res.get("verified") is False
    assert "destination manquante" in res.get("error_hint", "")


# ─── 8. nav OK → done verified=False ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_launch_phone_navigation_success(monkeypatch):
    mock_trigger = AsyncMock(return_value=BridgeResult(ok=True, status=200, reason="ok"))
    monkeypatch.setattr(mobile_bridge_service, "launch_maps_navigation", mock_trigger)

    res = await dispatch_tool("launch_phone_navigation", {"destination": "Gare de Lyon", "mode": "transit"})
    assert res.get("status") == "done"
    assert res.get("verified") is False
    assert res.get("evidence") == "macrodroid_2xx"
    assert "Gare de Lyon" in res.get("user_message", "")


# ─── 9. control_spotify phone : déjà visible → pas de réveil ───────────────────

@pytest.mark.asyncio
async def test_control_spotify_phone_already_visible_no_wake(monkeypatch):
    phone_dev = {"id": "phone_s24_id", "name": "Samsung S24", "type": "Smartphone", "is_active": False}
    monkeypatch.setattr(spotify_service, "get_devices", AsyncMock(return_value=[phone_dev]))
    
    mock_wake = AsyncMock()
    monkeypatch.setattr(mobile_bridge_service, "wake_spotify_on_phone", mock_wake)
    
    mock_transfer = AsyncMock()
    monkeypatch.setattr(spotify_service, "transfer_playback", mock_transfer)
    monkeypatch.setattr(spotify_service, "_verify", AsyncMock(return_value=True))

    res = await spotify_service.control(action="transfer", device="telephone")
    assert res.get("status") == "done"
    assert mock_wake.called is False
    mock_transfer.assert_called_once_with("phone_s24_id", play=True)


# ─── 10. absent puis visible au 3e poll → transfer appelé ─────────────────────

@pytest.mark.asyncio
async def test_control_spotify_phone_visible_at_3rd_poll(monkeypatch):
    phone_dev = {"id": "phone_s24_id", "name": "Samsung S24", "type": "Smartphone", "is_active": False}
    
    mock_get_devices = AsyncMock(side_effect=[[], [], [], [phone_dev], [phone_dev], [phone_dev]])
    monkeypatch.setattr(spotify_service, "get_devices", mock_get_devices)

    mock_wake = AsyncMock(return_value=BridgeResult(ok=True, status=200, reason="ok"))
    monkeypatch.setattr(mobile_bridge_service, "wake_spotify_on_phone", mock_wake)

    mock_transfer = AsyncMock()
    monkeypatch.setattr(spotify_service, "transfer_playback", mock_transfer)
    monkeypatch.setattr(spotify_service, "_verify", AsyncMock(return_value=True))

    res = await spotify_service.control(action="transfer", device="phone")
    assert res.get("status") == "done"
    assert mock_wake.called is True
    mock_transfer.assert_called_once_with("phone_s24_id", play=True)


# ─── 11. jamais visible → failed ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_control_spotify_phone_never_visible_failed(monkeypatch):
    monkeypatch.setattr(spotify_service, "get_devices", AsyncMock(return_value=[]))
    mock_wake = AsyncMock(return_value=BridgeResult(ok=True, status=200, reason="ok"))
    monkeypatch.setattr(mobile_bridge_service, "wake_spotify_on_phone", mock_wake)

    res = await spotify_service.control(action="transfer", device="s24")
    assert res.get("status") == "failed"
    assert res.get("error_hint") == "ton téléphone n'apparaît pas sur Spotify Connect"


# ─── 12. DEVICE_ID absent de tous les logs (caplog) ───────────────────────────

@pytest.mark.asyncio
async def test_mobile_bridge_device_id_absent_from_logs(monkeypatch, caplog):
    secret_uuid = "ULTRA_SECRET_MACRODROID_UUID_99999"
    monkeypatch.setattr(config, "MACRODROID_DEVICE_ID", secret_uuid)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(status_code=200, is_success=True))
    mock_client.is_closed = False
    monkeypatch.setattr(mobile_bridge_service, "_get_client", lambda: mock_client)

    with caplog.at_level(logging.DEBUG):
        await mobile_bridge_service.launch_maps_navigation(destination="Marseille", mode="driving")
        await mobile_bridge_service.wake_spotify_on_phone()

    assert secret_uuid not in caplog.text
    assert "ULTRA_SECRET" not in caplog.text
