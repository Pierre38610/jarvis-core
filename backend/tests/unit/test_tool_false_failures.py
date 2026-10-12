"""tests/unit/test_tool_false_failures.py
Tests unitaires validant que l'échec d'une vérification ne transforme JAMAIS
une action réussie en échec ('status': 'failed').
"""

import asyncio
import smtplib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from core.tools.result import ToolResult, normalize_result
from core.tools.dispatcher import dispatch_tool
from services.spotify_service import SpotifyService, spotify_service
from services.email_service import send_email, verify_email_in_sent_box


@pytest.mark.asyncio
async def test_spotify_next_verified_on_second_poll():
    """Spotify next : 204 + /me/player à jour au 2e poll → done verified=True."""
    service = SpotifyService()

    # Mock _pick_device
    service._pick_device = AsyncMock(return_value=("mock_device_1", None))
    # Mock next_track -> 204 No Content
    service.next_track = AsyncMock(return_value=None)

    # Simulation now_playing avant l'appel (piste 1)
    before_np = {
        "spotify_uri": "spotify:track:11111",
        "track_name": "Track Old",
    }
    # Simulation now_playing après vérification (piste 2)
    after_np = {
        "spotify_uri": "spotify:track:22222",
        "track_name": "Track New",
    }

    # 1er poll : ancien état (piste 1), 2e poll : nouvel état (piste 2)
    poll_states = [
        {"item": {"uri": "spotify:track:11111"}},
        {"item": {"uri": "spotify:track:22222"}},
    ]
    poll_index = 0

    async def mock_get(path, *args, **kwargs):
        nonlocal poll_index
        if path == "/me/player":
            if poll_index < len(poll_states):
                res = poll_states[poll_index]
                poll_index += 1
                return res
            return {"item": {"uri": "spotify:track:22222"}}
        return {}

    service._get = AsyncMock(side_effect=mock_get)

    async def mock_now_playing():
        if poll_index == 0:
            return before_np
        return after_np

    service.now_playing = AsyncMock(side_effect=mock_now_playing)

    # Réduire le délai de sleep pour le test
    with patch("asyncio.sleep", AsyncMock(return_value=None)):
        result = await service.control(action="next")

    assert result["status"] == "done"
    assert result["verified"] is True
    assert "Track New" in result["evidence"] or result.get("track_name") == "Track New"


@pytest.mark.asyncio
async def test_spotify_play_exception_during_verify_not_failed():
    """Spotify play : 204 + /me/player qui lève une exception → done verified=False (PAS failed)."""
    service = SpotifyService()
    service._pick_device = AsyncMock(return_value=("mock_device_1", None))
    service.play = AsyncMock(return_value=None)  # 204 No Content

    # La vérification /me/player lève une exception (ex: réseau, timeout)
    service._get = AsyncMock(side_effect=RuntimeError("Transient /me/player network error"))

    with patch("asyncio.sleep", AsyncMock(return_value=None)):
        result = await service.control(action="play")

    # L'action a été acceptée (204) : l'échec de vérification ne doit PAS donner status='failed'
    assert result["status"] == "done"
    assert result["verified"] is False
    assert result["evidence"] == "api_2xx_accepted"
    assert result["status"] != "failed"


@pytest.mark.asyncio
async def test_spotify_404_no_active_device_failed_with_error_hint():
    """Spotify 404 NO_ACTIVE_DEVICE → failed avec error_hint lisible."""
    service = SpotifyService()
    service._pick_device = AsyncMock(return_value=("mock_device_1", None))
    # Simuler le rejet 404 NO_ACTIVE_DEVICE lors de play
    service.play = AsyncMock(side_effect=ValueError("aucun appareil Spotify actif"))

    result = await service.control(action="play")

    assert result["status"] == "failed"
    assert result["verified"] is False
    assert result["error_hint"] == "aucun appareil Spotify actif"
    assert "aucun appareil" in result["message"].lower()


@pytest.mark.asyncio
async def test_spotify_401_then_204_after_refresh():
    """Spotify 401 puis 204 après refresh de token → done."""
    service = SpotifyService()
    service._get_token = AsyncMock(return_value="expired_token")
    service._refresh = AsyncMock(return_value="valid_refreshed_token")

    # Simulation d'un client httpx qui renvoie 401 au premier appel puis 204
    call_count = 0

    class MockHttpxClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def post(self, url, headers=None, json=None, params=None):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 1:
                mock_resp.status_code = 401
                mock_resp.content = b'{"error": "The access token expired"}'
            else:
                mock_resp.status_code = 204
                mock_resp.content = b""
            return mock_resp

    with patch("httpx.AsyncClient", return_value=MockHttpxClient()):
        res = await service._post("/me/player/next")

    assert res == {}
    assert call_count == 2
    assert service._refresh.called


@pytest.mark.asyncio
async def test_email_smtp_ok_imap_timeout_done_verified_false():
    """Email : SMTP OK + IMAP timeout → done verified=False (jamais failed)."""
    # 1. Mock de l'envoi SMTP (succès sans exception)
    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_instance.send_message.return_value = {}  # Aucun destinataire refusé
        mock_smtp.return_value = mock_instance

        # 2. Mock de la vérification IMAP qui timeout
        with patch("services.email_service.verify_email_in_sent_box", AsyncMock(
            return_value=(False, "smtp_accepted message_id=<test1234@jarvis>", None)
        )):
            res = await dispatch_tool(
                name="send_email",
                args={
                    "subject": "Rapport Test",
                    "body": "Contenu du test",
                    "to_email": "pierrecassagnettes@gmail.com",
                    "confirmed_by_user": True,
                }
            )

    assert res["status"] == "done"
    assert res["verified"] is False
    assert "smtp_accepted" in res["evidence"]
    assert res["status"] != "failed"


@pytest.mark.asyncio
async def test_email_smtp_exception_failed():
    """Email : SMTPException → failed."""
    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_instance.send_message.side_effect = smtplib.SMTPException("Authentication failed")
        mock_smtp.return_value = mock_instance

        res = await dispatch_tool(
            name="send_email",
            args={
                "subject": "Rapport Test",
                "body": "Contenu du test",
                "to_email": "pierrecassagnettes@gmail.com",
                "confirmed_by_user": True,
            }
        )

    assert res["status"] == "failed"
    assert res["verified"] is False


def test_normalize_result_legacy_sent_maps_to_done():
    """normalize_result({"status":"sent"}) → done."""
    raw = {"status": "sent", "message_id": "<abc-123@jarvis>", "user_message": "Email envoyé."}
    normalized = normalize_result("send_email", raw)

    assert isinstance(normalized, ToolResult)
    assert normalized.status == "done"
    assert normalized.is_success is True
    assert normalized.evidence == "<abc-123@jarvis>"


def test_normalize_result_unknown_status_maps_to_done_not_failed():
    """normalize_result avec un statut inconnu ne doit JAMAIS générer 'failed'."""
    raw = {"status": "unrecognized_custom_status_xyz", "data": "test_data"}
    normalized = normalize_result("custom_tool", raw)

    assert normalized.status == "done"
    assert normalized.verified is False
    assert normalized.status != "failed"
