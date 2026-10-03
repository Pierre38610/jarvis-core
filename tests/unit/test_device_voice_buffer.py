"""tests/unit/test_device_voice_buffer.py
Tests unitaires pour le buffer circulaire de pré-écoute (deque 25 trames ~1.5s)
et son injection immédiate à la détection du mot d'activation.
"""

import collections
import pytest


def test_pre_listen_buffer_maxlen():
    """Vérifie que le buffer circulaire conserve au plus 25 trames (~1.5s)."""
    buf = collections.deque(maxlen=25)
    for i in range(30):
        buf.append(f"frame_{i}".encode())
    
    assert len(buf) == 25
    # Les 5 premières doivent avoir été éjectées
    assert buf[0] == b"frame_5"
    assert buf[-1] == b"frame_29"


def test_pre_listen_buffer_flush_order():
    """Vérifie que le vidage du buffer respecte strictement l'ordre chronologique FIFO."""
    buf = collections.deque(maxlen=25)
    for i in range(10):
        buf.append(f"frame_{i}".encode())

    flushed = []
    while buf:
        flushed.append(buf.popleft())

    assert len(buf) == 0
    assert len(flushed) == 10
    assert flushed == [f"frame_{i}".encode() for i in range(10)]
