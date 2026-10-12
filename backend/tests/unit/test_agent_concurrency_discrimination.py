import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from core.shared_state import active_task_controller
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from routers.voice import _build_system_instruction, format_jarvis_system_instruction


@pytest.mark.asyncio
async def test_system_instruction_includes_agent_concurrency_discrimination():
    """Vérifie que l'instruction système construite pour Gemini Live contient la règle de discrimination multitâche."""
    instruction = await _build_system_instruction()
    assert "GESTION DU MULTITÂCHE ET INDÉPENDANCE DES DEMANDES PENDANT L'EXÉCUTION D'AGENTS CLI" in instruction
    assert "Demande indépendante" in instruction
    assert "guide_active_task" in instruction
    assert "Directive explicite pour l'agent de fond" in instruction


def test_template_includes_multitasking_discrimination_rule():
    """Vérifie que le gabarit Stark JARVIS_SYSTEM_INSTRUCTION_TEMPLATE contient les consignes de discrimination."""
    template = config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
    assert "RÈGLE FONDAMENTALE DE DISCRIMINATION DES DEMANDES EN MULTITÂCHE" in template
    assert "SI LA DEMANDE N'A RIEN À VOIR" in template
    assert "SI ET SEULEMENT SI l'utilisateur demande EXPLICITEMENT" in template
    assert "NE TRANSMETS JAMAIS cette demande aux agents en arrière-plan" in template


def test_guide_active_task_tool_declaration_strict_scope():
    """Vérifie que la déclaration de guide_active_task interdit formellement les demandes indépendantes."""
    tools = get_tools_list(include_agentic=True)
    guide_decl = None
    for tool in tools:
        if hasattr(tool, "function_declarations") and tool.function_declarations:
            for fd in tool.function_declarations:
                if fd.name == "guide_active_task":
                    guide_decl = fd
                    break

    assert guide_decl is not None, "guide_active_task doit être déclaré"
    desc = guide_decl.description
    assert "À UTILISER STRICTEMENT ET UNIQUEMENT QUAND" in desc
    assert "INTERDICTION FORMELLE D'UTILISER QUAND" in desc
    assert "control_spotify" in desc
    assert "search_web" in desc


@pytest.mark.asyncio
async def test_guide_active_task_fails_when_no_running_task():
    """Vérifie que l'appel de guide_active_task sans tâche en cours retourne un échec explicite."""
    mock_ws = AsyncMock()
    # S'assurer qu'aucune tâche n'est active
    active_task_controller["info"]["running"] = False
    active_task_controller["bg_task"] = None
    active_task_controller["browser_bg_task"] = None
    active_task_controller["deep_research_bg_task"] = None

    res = await dispatch_tool(
        name="guide_active_task",
        args={"directive": "ajoute une fonction de log"},
        websocket=mock_ws,
    )

    assert res.get("status") == "failed"
    assert "Aucune tâche ou agent" in res.get("user_message", "")


@pytest.mark.asyncio
async def test_guide_active_task_anti_confusion_guard_for_spotify():
    """Vérifie que le guard anti-confusion intercepte les commandes musicales envoyées par erreur à guide_active_task."""
    mock_ws = AsyncMock()
    active_task_controller["info"]["running"] = True

    res = await dispatch_tool(
        name="guide_active_task",
        args={"directive": "mets de la musique sur spotify"},
        websocket=mock_ws,
    )

    assert res.get("status") == "failed"
    assert "control_spotify" in res.get("user_message", "")


@pytest.mark.asyncio
async def test_guide_active_task_success_for_valid_code_directive():
    """Vérifie qu'une consigne de code valide est bien transmise à l'agent quand une tâche tourne."""
    mock_ws = AsyncMock()
    active_task_controller["info"]["running"] = True
    active_task_controller["queue"] = asyncio.Queue()
    active_task_controller["directives"] = []

    res = await dispatch_tool(
        name="guide_active_task",
        args={"directive": "ajoute un test unitaire pour la fonction calculate_score"},
        websocket=mock_ws,
    )

    assert res.get("status") == "done"
    assert res.get("verified") is True
    assert "ajoute un test unitaire" in res.get("user_message", "")
    queued = await active_task_controller["queue"].get()
    assert queued == "ajoute un test unitaire pour la fonction calculate_score"
