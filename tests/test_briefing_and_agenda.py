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
    assert "agenda_gerer_evenement" in funcs, "agenda_gerer_evenement manquant"
    assert "creer_rappel_push" in funcs, "creer_rappel_push manquant"
    assert "demander_morning_briefing" in funcs, "demander_morning_briefing manquant"
    print(f"[OK] 3 nouveaux outils déclarés : agenda_gerer_evenement, creer_rappel_push, demander_morning_briefing.")

    print("\n=== 3. TEST AUTOMATION WEBHOOK MAPPING ===")
    assert ACTION_WEBHOOK_MAPPING["agenda_gerer_evenement"] == "agenda-event"
    assert ACTION_WEBHOOK_MAPPING["creer_rappel_push"] == "schedule-push-reminder"
    p_agenda = build_agenda_payload("creer", "Déjeuner Stark", "2026-09-26T12:30:00")
    assert p_agenda["action"] == "creer" and p_agenda["titre"] == "Déjeuner Stark"
    p_reminder = build_reminder_payload("Prendre les clés", "dans 20 min")
    assert p_reminder["message"] == "Prendre les clés"
    print("[OK] Mapping et payloads n8n validés.")

    print("\n=== 4. TEST BRIEFING SERVICE ===")
    # Test météo locale fallback
    weather = await get_local_weather("Grenoble")
    assert "city" in weather and "temperature" in weather and "condition" in weather
    print(f"[OK] Météo : {weather['city']} - {weather['temperature']} ({weather['condition']})")

    # Test compilation briefing
    briefing = await briefing_service.compiler_morning_briefing(force_refresh=True)
    assert briefing["status"] == "success"
    assert "texte_oral" in briefing
    assert len(briefing["texte_oral"]) > 50
    print(f"[OK] Discours Aoede généré ({len(briefing['texte_oral'])} car) :\n     \"{briefing['texte_oral']}\"")

    # Test lecture cache Redis / mémoire
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
