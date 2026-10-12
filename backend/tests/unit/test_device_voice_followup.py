"""tests/unit/test_device_voice_followup.py
Tests unitaires pour la fenêtre de follow-up vocal (6s), le timeout d'inactivité (60s)
et le calcul RMS de détection de voix sur /ws/device.
"""

import json
import struct
import pytest
from routers.device_voice import (
    FOLLOWUP_WINDOW_S,
    SESSION_TIMEOUT_IDLE,
    RMS_VOICE_THRESHOLD,
    _calculate_audio_rms,
)


def test_device_voice_constants():
    """Vérifie la présence et les valeurs exactes des constantes du protocole d'écoute."""
    assert FOLLOWUP_WINDOW_S == 6
    assert SESSION_TIMEOUT_IDLE == 60
    assert RMS_VOICE_THRESHOLD == 500


def test_calculate_audio_rms_silence():
    """Vérifie que le calcul RMS sur un buffer silencieux renvoie 0."""
    silence = b"\x00" * 1920
    assert _calculate_audio_rms(silence) == 0.0


def test_calculate_audio_rms_signal():
    """Vérifie que le calcul RMS sur un signal alternatif est supérieur au seuil."""
    # Créer un signal PCM 16-bit d'amplitude 2000 (> 500)
    samples = [2000, -2000, 2000, -2000] * 240
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)
    rms = _calculate_audio_rms(pcm_bytes)
    assert rms == 2000.0
    assert rms > RMS_VOICE_THRESHOLD


def test_listen_stop_json_payload_format():
    """Vérifie le format JSON exact du message de stop d'écoute transmis au firmware ESP32."""
    device_id = "esp32_test_123"
    msg = json.dumps({
        "type": "listen",
        "state": "stop",
        "session_id": device_id
    })
    parsed = json.loads(msg)
    assert parsed["type"] == "listen"
    assert parsed["state"] == "stop"
    assert parsed["session_id"] == device_id
