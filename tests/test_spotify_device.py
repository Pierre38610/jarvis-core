"""tests/test_spotify_device.py
Tests unitaires mockés hors-ligne pour la sélection d'appareil Spotify,
l'enregistrement de la préférence par défaut et le ducking intelligent du volume.
Aucun appel API réel ou payant (Règle d'or de test).
"""
import pytest
import sqlite3
import os
import gc
from unittest.mock import AsyncMock, MagicMock, patch

from services.spotify_service import SpotifyService


@pytest.fixture
def spotify_svc():
    """Crée une instance de SpotifyService utilisant une base SQLite de test isolée."""
    svc = SpotifyService()
    db_file = os.path.join(os.path.dirname(__file__), "test_spotify_unit.db")
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass

    with patch("services.spotify_service.DB_PATH", db_file):
        svc._ensure_db()
        yield svc

    gc.collect()
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass


# ─── TESTS APPAREIL PAR DÉFAUT & VALIDATION DE L'ARGUMENT ───────────────────────

@pytest.mark.asyncio
async def test_set_default_device_missing_argument(spotify_svc):
    """set_default_device doit renvoyer une erreur explicite si device est absent ou vide."""
    # Aucun argument
    res1 = await spotify_svc.set_default_device(None)
    assert res1["status"] == "error"
    assert "spécifier l'appareil" in res1["message"]

    # Chaîne vide ou espaces
    res2 = await spotify_svc.set_default_device("   ")
    assert res2["status"] == "error"
    assert "spécifier l'appareil" in res2["message"]


@pytest.mark.asyncio
async def test_set_default_device_success_and_persistence(spotify_svc):
    """set_default_device enregistre la préférence dans SQLite et get_default_device la restitue."""
    # Par défaut sur base neuve (seed 'telephone')
    def_dev = await spotify_svc.get_default_device()
    assert def_dev == "telephone"

    # Enregistrement d'un nouvel appareil
    res = await spotify_svc.set_default_device("ordinateur")
    assert res["status"] == "success"
    assert "ordinateur" in res["message"]

    # Vérification lecture
    updated_dev = await spotify_svc.get_default_device()
    assert updated_dev == "ordinateur"


# ─── TESTS SÉLECTION DE PÉRIPHÉRIQUE (_pick_device) ───────────────────────────

@pytest.mark.asyncio
async def test_pick_device_oral_hint_priority(spotify_svc):
    """Un indice oral explicite doit prévaloir sur l'appareil actif et la préférence."""
    spotify_svc.get_active_device = AsyncMock(return_value={"id": "active_pc_1", "name": "PC Pierre"})
    spotify_svc.resolve_device = AsyncMock(return_value={"id": "speaker_living_room", "name": "Salon"})

    dev_id, err = await spotify_svc._pick_device(hint="enceinte")
    assert dev_id == "speaker_living_room"
    assert err is None


@pytest.mark.asyncio
async def test_pick_device_active_device_when_no_hint(spotify_svc):
    """Si aucun indice oral n'est fourni et qu'un appareil joue déjà, il est conservé."""
    spotify_svc.get_active_device = AsyncMock(return_value={"id": "active_echo", "name": "Echo Salon"})

    dev_id, err = await spotify_svc._pick_device(hint=None)
    assert dev_id == "active_echo"
    assert err is None


@pytest.mark.asyncio
async def test_pick_device_phone_preference_present(spotify_svc):
    """Si la préférence est 'telephone' et qu'il est présent sur Connect, on le sélectionne."""
    spotify_svc.get_active_device = AsyncMock(return_value=None)
    spotify_svc.get_default_device = AsyncMock(return_value="telephone")
    spotify_svc.resolve_device = AsyncMock(return_value={"id": "pixel_phone_id", "name": "Pixel 8"})

    dev_id, err = await spotify_svc._pick_device(hint=None)
    assert dev_id == "pixel_phone_id"
    assert err is None


@pytest.mark.asyncio
async def test_pick_device_phone_preference_absent_no_silent_pc_switch(spotify_svc):
    """CONSIGNE STRICTE : Si la préférence est Smartphone et qu'il est absent,
    renvoyer une erreur explicite invitant à ouvrir l'app, sans basculer silencieusement sur le PC."""
    spotify_svc.get_active_device = AsyncMock(return_value=None)
    spotify_svc.get_default_device = AsyncMock(return_value="telephone")
    # Téléphone introuvable sur Connect
    spotify_svc.resolve_device = AsyncMock(return_value=None)

    # Même si le PC ou l'agent local est connecté, NE PAS basculer sur le PC !
    with patch("services.local_agent_service.local_agent_service.is_connected", return_value=True):
        dev_id, err = await spotify_svc._pick_device(hint=None)
        assert dev_id is None
        assert err is not None
        assert "téléphone" in err.lower()
        assert "ouvre l'application spotify" in err.lower()


# ─── TESTS DUCKING DU VOLUME ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duck_volume_supports_volume_false(spotify_svc):
    """Le ducking doit être ignoré si l'appareil ne supporte pas le contrôle du volume."""
    spotify_svc.get_playback_state = AsyncMock(return_value={
        "is_playing": True,
        "device": {"id": "chromecast_1", "name": "TV", "supports_volume": False, "volume_percent": 100}
    })
    spotify_svc.set_volume = AsyncMock()

    res = await spotify_svc.duck_volume()
    assert res["status"] == "skipped"
    assert "non supporté" in res["message"]
    spotify_svc.set_volume.assert_not_called()
    assert spotify_svc._ducking_active is False


@pytest.mark.asyncio
async def test_duck_volume_saves_real_volume_and_once_per_turn(spotify_svc):
    """Le ducking sauvegarde le volume réel (pas 100%), applique la baisse et ne baisse qu'une fois par tour."""
    spotify_svc.get_playback_state = AsyncMock(return_value={
        "is_playing": True,
        "device": {"id": "pc_dev", "name": "PC", "supports_volume": True, "volume_percent": 70}
    })
    spotify_svc.set_volume = AsyncMock()

    # Première baisse
    res1 = await spotify_svc.duck_volume()
    assert res1["status"] == "ducked"
    assert res1["original_volume"] == 70
    assert res1["duck_volume"] == 17  # int(70 * 0.25)
    assert spotify_svc._ducking_active is True
    assert spotify_svc._volume_before_duck == 70

    spotify_svc.set_volume.assert_called_once_with(17, device_id="pc_dev")

    # Deuxième appel pendant le même tour de parole -> doit être ignoré
    res2 = await spotify_svc.duck_volume()
    assert res2["status"] == "skipped"
    assert "déjà actif" in res2["message"]
    # set_volume n'a toujours été appelé qu'une seule fois
    assert spotify_svc.set_volume.call_count == 1


@pytest.mark.asyncio
async def test_restore_volume_to_real_saved_volume(spotify_svc):
    """restore_volume rétablit le volume réel d'origine (70%) si l'utilisateur n'y a pas touché."""
    spotify_svc._ducking_active = True
    spotify_svc._volume_before_duck = 70
    spotify_svc._duck_target_volume = 17
    spotify_svc._ducked_device_id = "pc_dev"

    # Volume au moment de la restauration est toujours le volume baissé (17%)
    spotify_svc.get_playback_state = AsyncMock(return_value={
        "is_playing": True,
        "device": {"id": "pc_dev", "volume_percent": 17}
    })
    spotify_svc.set_volume = AsyncMock()

    res = await spotify_svc.restore_volume()
    assert res["status"] == "restored"
    assert res["restored_volume"] == 70
    spotify_svc.set_volume.assert_called_once_with(70, device_id="pc_dev")
    assert spotify_svc._ducking_active is False
    assert spotify_svc._volume_before_duck is None


@pytest.mark.asyncio
async def test_restore_volume_skipped_if_user_changed_volume(spotify_svc):
    """CONSIGNE STRICTE : Si l'utilisateur a changé le volume entre-temps, ne pas restaurer."""
    spotify_svc._ducking_active = True
    spotify_svc._volume_before_duck = 70
    spotify_svc._duck_target_volume = 17
    spotify_svc._ducked_device_id = "pc_dev"

    # L'utilisateur a augmenté le volume manuellement à 50% pendant que Jarvis parlait
    spotify_svc.get_playback_state = AsyncMock(return_value={
        "is_playing": True,
        "device": {"id": "pc_dev", "volume_percent": 50}
    })
    spotify_svc.set_volume = AsyncMock()

    res = await spotify_svc.restore_volume()
    assert res["status"] == "skipped"
    assert "modifié manuellement" in res["message"]
    # set_volume ne doit PAS avoir été appelé
    spotify_svc.set_volume.assert_not_called()
    assert spotify_svc._ducking_active is False
    assert spotify_svc._volume_before_duck is None


# ─── TESTS TITRES LIKÉS & CONCISION SPOTIFY ─────────────────────────────────

@pytest.mark.asyncio
async def test_is_liked_query():
    """Vérifie la détection des expressions orales désignant les titres likés."""
    from services.spotify_service import _is_liked_query
    assert _is_liked_query("mes titres likés") is True
    assert _is_liked_query("titres likes") is True
    assert _is_liked_query("mes likes") is True
    assert _is_liked_query("mes coups de coeur") is True
    assert _is_liked_query("mes morceaux likés") is True
    assert _is_liked_query("liked songs") is True
    assert _is_liked_query("joue bohemian rhapsody") is False
    assert _is_liked_query("") is False


@pytest.mark.asyncio
async def test_play_liked_tracks_success(spotify_svc):
    """Vérifie le lancement de la lecture des titres likés avec uris."""
    spotify_svc._pick_device = AsyncMock(return_value=("phone_1", None))
    spotify_svc.get_liked_tracks = AsyncMock(return_value=[
        {"name": "Song 1", "artist": "Artist 1", "uri": "spotify:track:1", "id": "1"},
        {"name": "Song 2", "artist": "Artist 2", "uri": "spotify:track:2", "id": "2"},
    ])
    spotify_svc.transfer_playback = AsyncMock()
    spotify_svc.play = AsyncMock()
    spotify_svc._save_device = AsyncMock()
    spotify_svc._verify = AsyncMock(return_value=True)
    spotify_svc.get_devices = AsyncMock(return_value=[{"id": "phone_1", "name": "Pixel"}])

    res = await spotify_svc.play_liked_tracks()
    assert res["status"] == "done"
    assert res["verified"] is True
    assert res["message"] == "Ok"
    spotify_svc.play.assert_called_once_with(
        device_id="phone_1", uris=["spotify:track:1", "spotify:track:2"]
    )


@pytest.mark.asyncio
async def test_control_next_concise_and_verified(spotify_svc):
    """Vérifie que l'action next renvoie un résultat direct, concis et vérifié."""
    spotify_svc._pick_device = AsyncMock(return_value=("phone_1", None))
    spotify_svc.next_track = AsyncMock()
    spotify_svc.now_playing = AsyncMock(return_value={"track_name": "New Song", "artist": "Singer"})

    res = await spotify_svc.control("next")
    assert res["status"] == "done"
    assert res["verified"] is True
    assert res["message"] == "Ok"
    assert "Titre suivant" in res["evidence"]


@pytest.mark.asyncio
async def test_control_play_liked_query_routing(spotify_svc):
    """Vérifie que play avec query='lance mes titres likés' est automatiquement routé vers play_liked_tracks."""
    spotify_svc.play_liked_tracks = AsyncMock(return_value={
        "status": "done", "verified": True, "message": "Ok", "evidence": "Liked tracks"
    })
    res = await spotify_svc.control("play", query="lance mes titres likés")
    assert res["status"] == "done"
    spotify_svc.play_liked_tracks.assert_called_once()

