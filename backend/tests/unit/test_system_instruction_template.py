import pytest
import config
from routers.voice import format_jarvis_system_instruction
from core.tools.declarations import get_tools_list


def test_format_jarvis_system_instruction_dummy_values_no_key_error():
    """Vérifie que le formatage du template avec des valeurs factices ne lève pas de KeyError et injecte correctement les variables."""
    formatted = format_jarvis_system_instruction(
        template=config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE,
        current_datetime="2026-10-01 12:00:00",
        memory_context="Mémoire factice utilisateur.",
        active_plan_status="Étape 1/2 en cours.",
        active_subagents_status="Agent test actif.",
    )
    assert "Date et heure : 2026-10-01 12:00:00" in formatted
    assert "Mémoire factice utilisateur." in formatted
    assert "Étape 1/2 en cours." in formatted
    assert "Agent test actif." in formatted


def test_format_jarvis_system_instruction_empty_defaults_to_aucun():
    """Vérifie que des variables vides ou None sont remplacées par 'Aucun' sans KeyError."""
    formatted = format_jarvis_system_instruction(
        template=config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE,
        current_datetime=None,
        memory_context="",
        active_plan_status="   ",
        active_subagents_status=None,
    )
    assert "Date et heure : Aucun" in formatted
    assert "Mémoire et contexte utilisateur :\nAucun" in formatted
    assert "Plan en cours :\nAucun" in formatted
    assert "Agents Antigravity en cours :\nAucun" in formatted


def test_live_tools_declaration_includes_run_agent_task_and_confirm_paid_key():
    """Vérifie que run_agent_task et confirm_paid_key sont bien déclarés dans les outils Live."""
    tools = get_tools_list(include_agentic=True)
    function_declarations = []
    for tool in tools:
        if hasattr(tool, "function_declarations") and tool.function_declarations:
            for fd in tool.function_declarations:
                function_declarations.append(fd.name)

    assert "run_agent_task" in function_declarations, "run_agent_task doit être déclaré dans les outils Live"
    assert "confirm_paid_key" in function_declarations, "confirm_paid_key doit être déclaré dans les outils Live"
