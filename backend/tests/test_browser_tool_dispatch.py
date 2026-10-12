"""tests/test_browser_tool_dispatch.py
Tests unitaires pour le dispatcheur de l'outil browser_task et browser_task_status.
Vérifie la non-bloquance (< 200 ms), l'accusé de réception, la gestion des priorités vocales
et l'annulation par stop_current_action.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.tools.dispatcher import dispatch_tool, _execute_dispatch_tool
from core.tools.result import ToolResult
from core.shared_state import active_task_controller
from services.browser_agent.loop import BrowserTask, TASKS as BROWSER_TASKS
from services.voice_injection_queue import InjectionPriority, voice_injection_queue


@pytest.mark.asyncio
async def test_browser_task_dispatch_under_200ms():
    """Vérifie que le dispatch de browser_task rend la main en moins de 200 ms

    quand run_browser_task est mocké avec un sleep de 5 s.
    """
    mock_ws = AsyncMock()
    mock_session = MagicMock()

    async def mock_slow_run_browser_task(task, notify=None):
        await asyncio.sleep(5.0)
        return ToolResult.done(
            user_message="Navigation terminée avec succès.",
            task_id=task.task_id,
            verified=True,
        )

    with patch("core.tools.dispatcher.run_browser_agent_task", side_effect=mock_slow_run_browser_task), \
         patch("services.browser_agent.loop.run_browser_task", side_effect=mock_slow_run_browser_task):
        t0 = time.perf_counter()
        # Test 1 : Appel direct au dispatcheur interne (contrat raw dict)
        raw_res = await _execute_dispatch_tool(
            name="browser_task",
            args={
                "goal": "Rechercher un vol pour Rome le 12 octobre",
                "start_url": "https://google.com",
                "recipe": "cart",
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini Flash",
        )
        elapsed_raw = time.perf_counter() - t0

        # Vérification du contrat direct : status launched_in_background
        assert elapsed_raw < 0.200, f"Le dispatch brut a pris {elapsed_raw:.3f}s (> 0.200s)"
        assert raw_res.get("status") == "launched_in_background"
        assert "task_id" in raw_res

        # Test 2 : Appel via dispatch_tool public
        t1 = time.perf_counter()
        res = await dispatch_tool(
            name="browser_task",
            args={
                "goal": "Rechercher un vol pour Rome le 12 octobre",
                "start_url": "https://google.com",
                "recipe": "cart",
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini Flash",
        )
        elapsed = time.perf_counter() - t1

        # Nettoyage de la tâche d'arrière-plan
        bg_task = active_task_controller.get("browser_bg_task")
        if bg_task and not bg_task.done():
            bg_task.cancel()

    # 1. Vérification du timing < 200 ms
    assert elapsed < 0.200, f"Le dispatch a pris trop de temps : {elapsed:.3f}s (attendu < 0.200s)"

    # 2. Vérification de la réponse immédiate
    assert isinstance(res, dict)
    assert res.get("status") in ("launched_in_background", "started")
    assert "task_id" in res
    assert res.get("goal") == "Rechercher un vol pour Rome le 12 octobre"

    # 3. Vérification de l'enregistrement de la tâche
    task_id = res["task_id"]
    assert task_id in BROWSER_TASKS
    task = BROWSER_TASKS[task_id]
    assert task.goal == "Rechercher un vol pour Rome le 12 octobre"
    assert task.start_url == "https://google.com"
    assert task.recipe == "cart"


@pytest.mark.asyncio
async def test_browser_task_status_dispatch():
    """Vérifie que browser_task_status retourne les infos d'une tâche ou de toutes les tâches."""
    test_task = BrowserTask(
        task_id="bt_status_test_123",
        goal="Tester le statut",
        status="running",
        steps=3,
    )
    BROWSER_TASKS[test_task.task_id] = test_task

    mock_ws = AsyncMock()
    mock_session = MagicMock()

    # Interrogation directe
    raw_one = await _execute_dispatch_tool(
        name="browser_task_status",
        args={"task_id": "bt_status_test_123"},
        websocket=mock_ws,
        session=mock_session,
        is_paid_live=False,
        live_display_label="Gemini Flash",
    )
    assert raw_one.get("task_id") == "bt_status_test_123"
    assert raw_one.get("status") == "running"
    assert raw_one.get("steps") == 3

    # Interrogation via dispatch_tool
    res_one = await dispatch_tool(
        name="browser_task_status",
        args={"task_id": "bt_status_test_123"},
        websocket=mock_ws,
        session=mock_session,
    )
    assert res_one.get("task_id") == "bt_status_test_123"
    assert res_one.get("status") in ("running", "started")
    assert res_one.get("steps") == 3

    # Interrogation de toutes les tâches
    res_all = await dispatch_tool(
        name="browser_task_status",
        args={},
        websocket=mock_ws,
        session=mock_session,
    )
    assert res_all.get("status") in ("success", "done")
    tasks_list = res_all.get("tasks", [])
    assert any(t.get("task_id") == "bt_status_test_123" for t in tasks_list)


@pytest.mark.asyncio
async def test_stop_current_action_cancels_browser_tasks():
    """Vérifie que stop_current_action déclenche le cancel_event de toutes les BrowserTask actives."""
    test_task = BrowserTask(
        task_id="bt_cancel_test_456",
        goal="Tâche à annuler",
        status="running",
    )
    BROWSER_TASKS[test_task.task_id] = test_task
    assert not test_task.cancel_event.is_set()

    mock_ws = AsyncMock()
    mock_session = MagicMock()

    # Test direct
    raw_res = await _execute_dispatch_tool(
        name="stop_current_action",
        args={"reason": "Arrêt demandé pour test"},
        websocket=mock_ws,
        session=mock_session,
        is_paid_live=False,
        live_display_label="Gemini Flash",
    )
    assert raw_res.get("status") == "stopped"
    assert test_task.cancel_event.is_set()
    assert test_task.status == "cancelled"

    # Réinitialisation pour test dispatch_tool
    test_task_2 = BrowserTask(
        task_id="bt_cancel_test_789",
        goal="Deuxième tâche à annuler",
        status="running",
    )
    BROWSER_TASKS[test_task_2.task_id] = test_task_2

    res = await dispatch_tool(
        name="stop_current_action",
        args={"reason": "Arrêt via dispatch_tool"},
        websocket=mock_ws,
        session=mock_session,
    )
    assert res.get("status") in ("stopped", "done")
    assert test_task_2.cancel_event.is_set()
    assert test_task_2.status == "cancelled"


@pytest.mark.asyncio
async def test_browser_task_voice_injection_priority_and_result():
    """Vérifie les priorités de VoiceInjectionQueue (PROGRESS_MILESTONE, INTERRUPTION, TOOL_RESPONSE)."""
    enqueued_items = []

    async def mock_enqueue(text, priority=None, **kwargs):
        enqueued_items.append((text, priority, kwargs))
        return True

    mock_ws = AsyncMock()
    mock_session = MagicMock()

    async def mock_run_agent(task, notify=None):
        if notify:
            # Jalon de progression -> PROGRESS_MILESTONE
            await notify("Recherche en cours sur le site...")
            # Handoff intervention -> INTERRUPTION
            await notify("Une intervention (captcha) est requise.")
        return ToolResult.done(
            user_message="Navigation terminée : billet trouvé à 45€.",
            task_id=task.task_id,
            verified=True,
        )

    with patch("core.tools.dispatcher.run_browser_agent_task", side_effect=mock_run_agent), \
         patch("services.browser_agent.loop.run_browser_task", side_effect=mock_run_agent), \
         patch.object(voice_injection_queue, "enqueue", side_effect=mock_enqueue):
        res = await dispatch_tool(
            name="browser_task",
            args={"goal": "Trouver un billet"},
            websocket=mock_ws,
            session=mock_session,
        )
        assert res.get("status") in ("launched_in_background", "started")
        assert "task_id" in res

        # Attendre que le background worker termine
        for _ in range(50):
            if len(enqueued_items) >= 3:
                break
            await asyncio.sleep(0.05)

    # Vérification des messages injectés
    assert len(enqueued_items) == 3
    # 1er message : jalon de progression
    assert enqueued_items[0][0] == "Recherche en cours sur le site..."
    assert enqueued_items[0][1] == InjectionPriority.PROGRESS_MILESTONE

    # 2eme message : handoff
    assert enqueued_items[1][0] == "Une intervention (captcha) est requise."
    assert enqueued_items[1][1] == InjectionPriority.INTERRUPTION

    # 3eme message : résultat final
    assert enqueued_items[2][0] == "Navigation terminée : billet trouvé à 45€."
    assert enqueued_items[2][1] == InjectionPriority.TOOL_RESPONSE


@pytest.mark.asyncio
async def test_prepare_web_cart_or_checkout_delegates_to_browser_task():
    """Vérifie que prepare_web_cart_or_checkout route vers browser_task avec recipe=cart."""
    mock_ws = AsyncMock()
    mock_session = MagicMock()

    async def mock_run_agent(task, notify=None):
        return ToolResult.done(
            user_message="Panier préparé avec succès.",
            task_id=task.task_id,
            verified=True,
        )

    with patch("core.tools.dispatcher.run_browser_agent_task", side_effect=mock_run_agent), \
         patch("services.browser_agent.loop.run_browser_task", side_effect=mock_run_agent):
        res = await dispatch_tool(
            name="prepare_web_cart_or_checkout",
            args={"product_or_service": "Câble HDMI 2.1", "merchant_url": "https://amazon.fr"},
            websocket=mock_ws,
            session=mock_session,
        )
        assert res.get("status") in ("launched_in_background", "started")
        task_id = res.get("task_id")
        assert task_id in BROWSER_TASKS
        task = BROWSER_TASKS[task_id]
        assert task.recipe == "cart"
        assert "Câble HDMI 2.1" in task.goal
        assert task.start_url == "https://amazon.fr"


@pytest.mark.asyncio
async def test_open_train_booking_delegates_to_browser_task():
    """Vérifie que open_train_booking / reserver_billet_train_local route vers browser_task avec recipe=train."""
    mock_ws = AsyncMock()
    mock_session = MagicMock()

    async def mock_run_agent(task, notify=None):
        return ToolResult.done(
            user_message="Réservation prête.",
            task_id=task.task_id,
            verified=True,
        )

    with patch("core.tools.dispatcher.run_browser_agent_task", side_effect=mock_run_agent), \
         patch("services.browser_agent.loop.run_browser_task", side_effect=mock_run_agent):
        res = await dispatch_tool(
            name="open_train_booking",
            args={"origine": "Paris", "destination": "Lyon", "date_depart": "2026-10-15"},
            websocket=mock_ws,
            session=mock_session,
        )
        assert res.get("status") in ("launched_in_background", "started")
        task_id = res.get("task_id")
        assert task_id in BROWSER_TASKS
        task = BROWSER_TASKS[task_id]
        assert task.recipe == "train"
        assert "Paris" in task.goal and "Lyon" in task.goal


@pytest.mark.asyncio
async def test_search_train_routes_no_deep_link_opened():
    """Vérifie que search_train_routes renvoie les infos orales sans ouvrir de navigateur."""
    mock_ws = AsyncMock()
    mock_session = MagicMock()

    mock_routes = {
        "status": "success",
        "best_option": {
            "heure_depart": "14:00",
            "heure_arrivee": "18:30",
            "type_train": "SJ Snabbtåg",
            "duree": "4h30",
            "prix": "495 SEK",
        },
        "primary_deep_link": "https://www.omio.fr/trains/malmo-stockholm",
        "primary_title": "Train Malmö → Stockholm",
        "is_multi_segment": False,
    }

    with patch("services.transport_service.transport_service.rechercher_itineraires", new_callable=AsyncMock) as mock_rech, \
         patch("services.supervision_service.supervision_service.track_browser_window") as mock_track:
        mock_rech.return_value = mock_routes
        res = await dispatch_tool(
            name="search_train_routes",
            args={"origine": "Malmö", "destination": "Stockholm", "date_depart": "2026-10-15"},
            websocket=mock_ws,
            session=mock_session,
        )

        assert res.get("status") in ("success", "done")
        assert mock_track.call_count == 0
        instruction = res.get("instruction_to_jarvis", "")
        assert "affiché sur ton écran" not in instruction
        assert "ouvert directement" not in instruction


@pytest.mark.asyncio
async def test_launch_deep_research_browser_agent_success():
    """Vérifie que launch_deep_research utilise le BrowserTask gemini_deep_research si succès."""
    mock_ws = AsyncMock()
    mock_session = MagicMock()

    async def mock_run_agent(task, notify=None):
        task.status = "completed"
        return ToolResult.done(
            user_message="Rapport Deep Research complet sur l'informatique quantique.",
            task_id=task.task_id,
            verified=True,
        )

    with patch("core.tools.dispatcher.run_browser_agent_task", side_effect=mock_run_agent), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock), \
         patch("services.local_agent_service.is_pc_connected_async", return_value=True):
        res = await dispatch_tool(
            name="browser_task",
            args={"goal": "Recherche approfondie L3 quantique", "recipe": "gemini_deep_research", "sync": True},
            websocket=mock_ws,
            session=mock_session,
        )

        assert res.get("status") in ("success", "done")
        assert "Rapport Deep Research" in str(res.get("user_message", ""))

