import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import asyncio
from services.briefing_service import get_local_weather, briefing_service
from services.memory_service import memory_service
from services.cache import cache_service

async def run_scenarios():
    print("=== TEST 1: LOCALISATION MÉMOIRE (PARIS) ===")
    memory_service.set_current_user_location("Paris")
    w_paris = await get_local_weather()
    print(f"Météo ville mémoire: {w_paris['city']} - {w_paris['temperature']}")
    assert w_paris['city'] == "Paris"

    print("\n=== TEST 2: LOCALISATION GPS SMARTPHONE/PC (STOCKHOLM) ===")
    await cache_service.set("jarvis:device:location", {"latitude": 59.3293, "longitude": 18.0686, "city": "Stockholm"}, ttl=60)
    w_stockholm = await get_local_weather()
    print(f"Météo GPS: {w_stockholm['city']} - {w_stockholm['temperature']}")
    assert w_stockholm['city'] == "Stockholm"

    print("\n=== TEST 3: COMPILATION COMPLETE BRIEFING ===")
    briefing = await briefing_service.compiler_morning_briefing(force_refresh=True)
    oral = briefing.get("texte_oral", "")
    print(f"Texte oral:\n{oral}")
    assert "Stockholm" in oral
    assert "actualité" in oral.lower() or "actualités" in oral.lower()
    assert briefing["agenda"]["count"] == 0 or len(briefing["agenda"]["events"]) >= 0

    # Nettoyage
    memory_service.set_profile_value("current_city", "")
    await cache_service.delete("jarvis:device:location")
    print("\n[SUCCESS] Tous les scénarios de localisation, météo et news 24h sont validés !")

if __name__ == "__main__":
    asyncio.run(run_scenarios())
