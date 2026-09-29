"""tests/test_task_planner.py
Tests unitaires du planificateur multi-etapes de J.A.R.V.I.S.
100% hors-ligne (zero appel API). Conforme a la regle no-paid-api-in-tests.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.task_planner import (
    needs_planning,
    Plan,
    PlanStep,
    get_plan_status,
    mark_plan_step,
    update_step_with_tool_result,
    build_continuation_prompt,
    build_final_report_prompt,
    get_plan_hud_payload,
    set_active_plan,
    get_active_plan,
    clear_active_plan,
    STEP_STATUSES,
)
import services.task_planner as tp


# ─── Helpers ------------------------------------------------------------------

def _make_plan(n_steps=3) -> Plan:
    steps = [
        PlanStep(id=str(i+1), description=f"Etape {i+1}", tool_candidate="search_web")
        for i in range(n_steps)
    ]
    return Plan(plan_id="test-plan", utterance="test utterance", steps=steps)


@pytest.fixture(autouse=True)
def reset_plan():
    """Remet le plan global a None avant chaque test."""
    clear_active_plan()
    yield
    clear_active_plan()


# ─── needs_planning() ---------------------------------------------------------

def test_single_verb_no_connector_returns_false():
    assert needs_planning("Ouvre Chrome") is False


def test_simple_question_returns_false():
    assert needs_planning("Quelle heure est-il ?") is False


def test_two_action_verbs_triggers_planning():
    assert needs_planning("Cherche le train Paris-Lyon et envoie-moi les details par mail") is True


def test_connector_plus_one_verb_triggers_planning():
    assert needs_planning("Lance la musique puis mets le volume a fond") is True


def test_long_utterance_with_connector_triggers_planning():
    utterance = "Cherche le prochain train Paris-Lyon, ajoute-le a mon agenda et envoie-moi les details par mail s'il te plait"
    assert needs_planning(utterance) is True


def test_empty_utterance_returns_false():
    assert needs_planning("") is False
    assert needs_planning(None) is False


def test_three_distinct_verbs_triggers_planning():
    assert needs_planning("Cherche, telecharge et envoie le document") is True


# ─── get_plan_status() sans plan actif ----------------------------------------

def test_get_plan_status_no_active_plan():
    result = get_plan_status()
    assert result["has_plan"] is False
    assert result["pending_count"] == 0
    assert result["status"] == "done"


# ─── get_plan_status() avec plan actif ----------------------------------------

def test_get_plan_status_with_active_plan():
    plan = _make_plan(3)
    set_active_plan(plan)
    result = get_plan_status()
    assert result["has_plan"] is True
    assert result["pending_count"] == 3
    assert result["total_steps"] == 3
    assert result["is_complete"] is False
    assert result["status"] == "done"
    assert result["verified"] is True


def test_get_plan_status_after_all_done():
    plan = _make_plan(2)
    for s in plan.steps:
        s.status = "done"
    set_active_plan(plan)
    result = get_plan_status()
    assert result["is_complete"] is True
    assert result["pending_count"] == 0
    assert result["done_count"] == 2


# ─── mark_plan_step() ---------------------------------------------------------

def test_mark_plan_step_no_plan():
    result = mark_plan_step("1", "done")
    assert result["status"] == "failed"


def test_mark_plan_step_invalid_status():
    set_active_plan(_make_plan(2))
    result = mark_plan_step("1", "invalid_status")
    assert result["status"] == "failed"
    assert "invalide" in result["user_message"].lower() or "invalid" in result.get("error_hint", "").lower()


def test_mark_plan_step_unknown_id():
    set_active_plan(_make_plan(2))
    result = mark_plan_step("99", "done")
    assert result["status"] == "failed"


def test_mark_plan_step_success():
    plan = _make_plan(2)
    set_active_plan(plan)
    result = mark_plan_step("1", "done", note="Test OK")
    assert result["status"] == "done"
    assert plan.steps[0].status == "done"
    assert plan.steps[0].note == "Test OK"


def test_mark_plan_step_all_steps_complete_sets_completed_at():
    plan = _make_plan(2)
    set_active_plan(plan)
    mark_plan_step("1", "done")
    mark_plan_step("2", "done")
    assert plan.is_complete() is True
    assert plan.completed_at > 0


def test_mark_plan_step_skipped():
    plan = _make_plan(3)
    set_active_plan(plan)
    result = mark_plan_step("2", "skipped", note="Non applicable")
    assert result["status"] == "done"
    assert plan.steps[1].status == "skipped"


# ─── update_step_with_tool_result() -------------------------------------------

def test_update_step_with_done_result():
    plan = _make_plan(2)
    set_active_plan(plan)
    update_step_with_tool_result("1", {"status": "done", "verified": True, "evidence": "mail_id_123"})
    assert plan.steps[0].status == "done"
    assert plan.steps[0].tool_result["evidence"] == "mail_id_123"


def test_update_step_with_failed_result():
    plan = _make_plan(2)
    set_active_plan(plan)
    update_step_with_tool_result("1", {"status": "failed", "error_hint": "SMTP timeout"})
    assert plan.steps[0].status == "failed"


def test_update_step_with_started_result_marks_running():
    plan = _make_plan(2)
    set_active_plan(plan)
    update_step_with_tool_result("1", {"status": "started"})
    assert plan.steps[0].status == "running"


def test_update_step_no_plan_is_noop():
    # Ne doit pas lever d'exception
    update_step_with_tool_result("1", {"status": "done"})


def test_update_step_marks_plan_complete_when_all_resolved():
    plan = _make_plan(2)
    set_active_plan(plan)
    update_step_with_tool_result("1", {"status": "done"})
    update_step_with_tool_result("2", {"status": "failed"})
    assert plan.is_complete() is True
    assert plan.completed_at > 0


# ─── build_continuation_prompt() ---------------------------------------------

def test_build_continuation_prompt_with_pending():
    plan = _make_plan(3)
    plan.steps[0].status = "done"
    msg = build_continuation_prompt(plan, done_count=1)
    assert "PLAN EN COURS" in msg
    assert "Etape 2" in msg or "2" in msg
    assert len(msg) > 20


def test_build_continuation_prompt_all_done_returns_empty():
    plan = _make_plan(2)
    for s in plan.steps:
        s.status = "done"
    msg = build_continuation_prompt(plan, done_count=2)
    assert msg == ""


def test_build_continuation_prompt_includes_tool_hint():
    plan = _make_plan(2)
    plan.steps[0].status = "done"
    plan.steps[1].tool_candidate = "send_email"
    msg = build_continuation_prompt(plan, done_count=1)
    assert "send_email" in msg


# ─── build_final_report_prompt() ---------------------------------------------

def test_build_final_report_prompt():
    plan = _make_plan(2)
    plan.steps[0].status = "done"
    plan.steps[1].status = "failed"
    plan.steps[1].note = "SMTP error"
    msg = build_final_report_prompt(plan)
    assert "PLAN TERMINE" in msg
    assert "Etape 1" in msg or "fait" in msg
    assert "echec" in msg or "failed" in msg.lower()


# ─── get_plan_hud_payload() ---------------------------------------------------

def test_get_plan_hud_payload_no_plan():
    result = get_plan_hud_payload()
    assert result == {"plan_active": False}


def test_get_plan_hud_payload_with_plan():
    plan = _make_plan(3)
    plan.steps[0].status = "done"
    set_active_plan(plan)
    result = get_plan_hud_payload()
    assert result["plan_active"] is True
    assert result["total"] == 3
    assert result["done"] == 1
    assert result["pending"] == 2
    assert len(result["steps"]) == 3


# ─── Plan.checklist_text() et final_report() ---------------------------------

def test_checklist_text_shows_all_statuses():
    plan = _make_plan(3)
    plan.steps[0].status = "done"
    plan.steps[1].status = "failed"
    plan.steps[2].status = "pending"
    text = plan.checklist_text()
    assert "Etape 1" in text
    assert "Etape 2" in text
    assert "Etape 3" in text


def test_final_report_all_done():
    plan = _make_plan(2)
    for s in plan.steps:
        s.status = "done"
    report = plan.final_report()
    assert "fait" in report
    assert report.endswith(".")


# ─── decompose() - mock strict sans appel API ---------------------------------

@pytest.mark.asyncio
async def test_decompose_skips_simple_utterance():
    """Une consigne simple ne doit pas declencher le planificateur."""
    result = await tp.decompose("Ouvre Chrome")
    assert result is None
    assert get_active_plan() is None


@pytest.mark.asyncio
async def test_decompose_multi_action_mocked():
    """Simule la reponse Gemini Flash pour une consigne multi-actions."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "steps": [
            {"id": "1", "description": "Chercher train Paris-Lyon", "tool_candidate": "search_train_routes", "depends_on": [], "verification": "Horaires trouves"},
            {"id": "2", "description": "Ajouter a l'agenda", "tool_candidate": "manage_calendar_event", "depends_on": ["1"], "verification": "Evenement cree"},
            {"id": "3", "description": "Envoyer details par mail", "tool_candidate": "send_email", "depends_on": ["1"], "verification": "Mail envoye"},
        ]
    })

    import config
    config.GEMINI_API_KEY_FREE = "fake_key_for_test"

    with patch("google.genai.Client") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        mock_instance.models.generate_content.return_value = mock_response

        utterance = "Cherche le prochain train Paris-Lyon, ajoute-le a mon agenda et envoie-moi les details par mail"
        plan = await tp.decompose(utterance, timeout=4.0)

    assert plan is not None
    assert len(plan.steps) == 3
    assert plan.steps[0].tool_candidate == "search_train_routes"
    assert plan.steps[1].tool_candidate == "manage_calendar_event"
    assert plan.steps[2].tool_candidate == "send_email"
    assert plan.steps[0].status == "pending"
    assert get_active_plan() is plan
    # Nettoyage
    clear_active_plan()
    config.GEMINI_API_KEY_FREE = ""


@pytest.mark.asyncio
async def test_decompose_timeout_returns_none():
    """Un timeout de decomposition ne doit jamais lever d'exception."""
    import config
    config.GEMINI_API_KEY_FREE = "fake_key_for_test"

    with patch("google.genai.Client") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        # Simule un timeout en levant asyncio.TimeoutError dans wait_for
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await tp.decompose(
                "Cherche le train et envoie un mail et ajoute a l'agenda",
                timeout=0.001
            )
    assert result is None
    config.GEMINI_API_KEY_FREE = ""


@pytest.mark.asyncio
async def test_decompose_api_error_returns_none():
    """Une erreur API ne doit jamais lever d'exception vers l'appelant."""
    import config
    config.GEMINI_API_KEY_FREE = "fake_key"

    with patch("google.genai.Client") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        mock_instance.models.generate_content.side_effect = RuntimeError("API Error")
        result = await tp.decompose("Cherche le train et envoie un mail")

    assert result is None
    config.GEMINI_API_KEY_FREE = ""


# ─── Declarations tools -------------------------------------------------------

def test_declarations_include_get_plan_status():
    from core.tools.declarations import get_tools_list
    tools = get_tools_list()
    all_names = []
    for t in tools:
        for d in t.function_declarations:
            all_names.append(d.name)
    assert "get_plan_status" in all_names, f"get_plan_status absent de {all_names}"


def test_declarations_include_mark_plan_step():
    from core.tools.declarations import get_tools_list
    tools = get_tools_list()
    all_names = []
    for t in tools:
        for d in t.function_declarations:
            all_names.append(d.name)
    assert "mark_plan_step" in all_names, f"mark_plan_step absent de {all_names}"


def test_mark_plan_step_declaration_has_required_params():
    from core.tools.declarations import get_tools_list
    tools = get_tools_list()
    mark_decl = None
    for t in tools:
        for d in t.function_declarations:
            if d.name == "mark_plan_step":
                mark_decl = d
                break
    assert mark_decl is not None
    required = mark_decl.parameters.required or []
    assert "step_id" in required
    assert "status" in required
