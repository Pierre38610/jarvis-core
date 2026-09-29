import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def run_tests():
    print("=== 1. TEST IMPORTS ===")
    import config
    import App
    from core.tools.declarations import get_tools_list
    from services.briefing_service import briefing_service, get_local_weather
    from services.automation import ACTION_WEBHOOK_MAPPING, build_agenda_payload, build_reminder_payload
    from services.cache import cache_service
    print("[OK] Imports réussis.")

    print("\n=== 2. TEST DECLARATIONS ===")
    tools = get_tools_list()
    funcs = {f.name: f for t in tools for f in t.function_declarations}
    assert "manage_calendar_event" in funcs or "agenda_gerer_evenement" in funcs, "manage_calendar_event manquant"
    assert "create_push_reminder" in funcs or "creer_rappel_push" in funcs, "create_push_reminder manquant"
    assert "get_morning_briefing" in funcs or "demander_morning_briefing" in funcs, "get_morning_briefing manquant"
    print(f"[OK] 3 outils déclarés : manage_calendar_event, create_push_reminder, get_morning_briefing.")

    print("\n=== 3. TEST AUTOMATION WEBHOOK MAPPING & ANTI-CREATION ===")
    assert ACTION_WEBHOOK_MAPPING["agenda_gerer_evenement"] == "agenda-event"
    assert ACTION_WEBHOOK_MAPPING["creer_rappel_push"] == "schedule-push-reminder"
    p_agenda = build_agenda_payload("creer", "Déjeuner Stark", "2026-09-26T12:30:00")
    assert p_agenda["action"] == "creer" and p_agenda["titre"] == "Déjeuner Stark"
    p_reminder = build_reminder_payload("Prendre les clés", "dans 20 min")
    assert p_reminder["message"] == "Prendre les clés"

    # Test que la consultation d'agenda via executer_action_externe ne déclenche pas de webhook de création
    from services.automation import executer_action_externe
    consult_res = await executer_action_externe("agenda-event", {"action": "consulter"})
    assert consult_res.get("status") == "success"
    assert "events" in consult_res.get("result", {}) or "events" in consult_res
    print("[OK] Mapping, payloads et sécurité anti-création agenda validés.")

    print("\n=== 4. TEST BRIEFING SERVICE, METEO POSITION/MEMOIRE & NEWS 24H ===")
    from services.briefing_service import get_top_news_24h
    from services.memory_service import memory_service

    # Test localisation mémoire
    mem_loc = memory_service.get_current_user_location()
    assert "city" in mem_loc
    print(f"[OK] Localisation mémoire détectée : {mem_loc['city']} (source: {mem_loc.get('source')})")

    # Test météo avec ville
    weather = await get_local_weather("Grenoble")
    assert "city" in weather and "temperature" in weather and "condition" in weather
    print(f"[OK] Météo : {weather['city']} - {weather['temperature']} ({weather['condition']})")

    # Test météo avec coordonnées GPS directes
    weather_gps = await get_local_weather(latitude=45.1885, longitude=5.7245)
    assert "city" in weather_gps and "temperature" in weather_gps
    print(f"[OK] Météo GPS : {weather_gps['city']} - {weather_gps['temperature']}")

    # Test actualités 24h
    news_res = await get_top_news_24h(limit=3)
    assert news_res.get("status") == "success"
    assert "items" in news_res and len(news_res["items"]) > 0
    print(f"[OK] Actualités 24h ({len(news_res['items'])} news) : {news_res['items'][0]['title'][:60]}...")

    # Test compilation briefing matinal complet
    briefing = await briefing_service.compiler_morning_briefing(force_refresh=True)
    assert briefing["status"] == "success"
    assert "texte_oral" in briefing
    assert len(briefing["texte_oral"]) > 50
    assert "actualites" in briefing or "news" in briefing
    print(f"[OK] Discours Aoede généré ({len(briefing['texte_oral'])} car) :\n     \"{briefing['texte_oral']}\"")

    # Test lecture cache Redis
    cached = await cache_service.get(briefing_service.CACHE_KEY)
    assert cached is not None and cached.get("texte_oral") == briefing["texte_oral"]
    print(f"[OK] Clé cache Redis '{briefing_service.CACHE_KEY}' vérifiée avec succès.")

    print("\n=== 5. TEST N8N WORKFLOWS JSON FILE ===")
    with open("docs/n8n_workflows/time_and_briefing.json", "r", encoding="utf-8") as f:
        wf = json.load(f)
    wf_ids = [w["id"] for w in wf]
    assert "jarvis-morning-briefing-cron" in wf_ids
    assert "jarvis-schedule-push-reminder" in wf_ids
    assert "jarvis-agenda-event" in wf_ids
    print(f"[OK] 3 workflows n8n vérifiés dans docs/n8n_workflows/time_and_briefing.json : {wf_ids}")

    print("\n>>> TOUS LES TESTS SONT PASSÉS AVEC SUCCÈS (COMPILE_OK) <<<")

if __name__ == "__main__":
    asyncio.run(run_tests())

