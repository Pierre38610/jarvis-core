import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from unittest.mock import AsyncMock, patch
from services.deezer_migration_service import deezer_migration_service

async def test_migration():
    mock_tracks = [
        {
            "deezer_track_id": 101,
            "deezer_title": "Get Lucky",
            "deezer_artist": "Daft Punk",
            "deezer_album": "Random Access Memories",
            "deezer_isrc": "FRUM71300001",
            "deezer_duration_s": 248.0,
            "source_playlist": "Coups de Coeur",
        },
        {
            "deezer_track_id": 102,
            "deezer_title": "Rare Unknown Indie Song",
            "deezer_artist": "Unknown Artist",
            "deezer_album": "Indie Album",
            "deezer_isrc": "",
            "deezer_duration_s": 180.0,
            "source_playlist": "Coups de Coeur",
        }
    ]

    async def mock_isrc(isrc):
        if isrc == "FRUM71300001":
            return {
                "id": "sp_get_lucky",
                "uri": "spotify:track:sp_get_lucky",
                "name": "Get Lucky (feat. Pharrell Williams)",
                "artists": [{"name": "Daft Punk"}, {"name": "Pharrell Williams"}],
                "duration_ms": 248000
            }
        return None

    async def mock_search(q, stype="track", limit=5):
        if "Daft Punk" in q:
            return {
                "tracks": {
                    "items": [{
                        "id": "sp_get_lucky",
                        "uri": "spotify:track:sp_get_lucky",
                        "name": "Get Lucky",
                        "artists": [{"name": "Daft Punk"}],
                        "duration_ms": 248000
                    }]
                }
            }
        return {"tracks": {"items": []}}

    with patch("services.spotify_service.spotify_service.find_track_by_isrc", side_effect=mock_isrc), \
         patch("services.spotify_service.spotify_service.search", side_effect=mock_search), \
         patch("services.briefing_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg:

        report = await deezer_migration_service.run(
            dry_run=True,
            run_id="test_run_001",
            tracks=mock_tracks
        )

        assert report["status"] == "completed", f"Status should be completed: {report}"
        assert report["summary"]["total_deezer_tracks"] == 2
        assert report["summary"]["matched_auto"] == 1
        assert report["summary"]["not_found_count"] == 1
        assert len(report["not_found"]) == 1
        assert report["not_found"][0]["deezer_track_id"] == 102
        assert mock_tg.called
        print("ALL TESTS PASSED! Report summary:", report["summary"])

if __name__ == "__main__":
    asyncio.run(test_migration())
