"""tests/unit/test_antigravity_first_routing.py
Validation unitaire du paradigme Antigravity-First (Mode Task) :
1. Présence des directives Antigravity-First dans JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
2. Richesse des descriptions d'outils run_agentic_task, run_agent_task et browser_task
3. Détection et classification automatique des livrables (site web, powerpoint, pptx, pdf, dossier, comparatif, panier, billet)
"""

import pytest
import config
from core.tools.declarations import get_tools_list
from services.live_mode_policy import detect_vocal_cognitive_level, _detect_agentic_need


def test_system_instruction_antigravity_first_directive():
    """Vérifie la présence intégrale de la directive PARADIGME ANTIGRAVITY-FIRST (MODE TASK)."""
    template = config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
    assert "PARADIGME ANTIGRAVITY-FIRST (MODE TASK)" in template
    assert "armée d'agents autonomes Antigravity" in template
    assert "browser_task" in template
    assert "run_agentic_task" in template
    assert "launch_deep_research" in template
    assert "get_active_task_status(include_logs=True)" in template
    assert "voix Aoede" in template


def test_tool_declarations_antigravity_first():
    """Vérifie que les déclarations incitent à formuler un objectif riche destiné aux agents Antigravity."""
    tools = get_tools_list(include_agentic=True)
    tool_map = {}
    for t in tools:
        if hasattr(t, "function_declarations") and t.function_declarations:
            for fd in t.function_declarations:
                tool_map[fd.name] = fd

    assert "run_agentic_task" in tool_map
    assert "run_agent_task" in tool_map
    assert "browser_task" in tool_map

    # run_agentic_task
    agentic_decl = tool_map["run_agentic_task"]
    assert "Antigravity-First" in agentic_decl.description
    props = agentic_decl.parameters.properties
    assert "objectif" in props
    assert "auto-suffisant" in props["objectif"].description
    assert "Pierre" in props["objectif"].description

    # run_agent_task
    agent_decl = tool_map["run_agent_task"]
    assert "Antigravity-First" in agent_decl.description
    props_agent = agent_decl.parameters.properties
    assert "auto-suffisant" in props_agent["objectif"].description

    # browser_task
    browser_decl = tool_map["browser_task"]
    assert "Antigravity-First" in browser_decl.description
    props_browser = browser_decl.parameters.properties
    assert "goal" in props_browser
    assert "auto-suffisant" in props_browser["goal"].description
    assert "Pierre" in props_browser["goal"].description


@pytest.mark.parametrize("query,expected_keyword", [
    ("Crée-moi un site web pour mon nouveau projet SaaS", "site web"),
    ("Fais-moi une présentation powerpoint pour demain", "powerpoint"),
    ("Génère un pptx récapitulatif des résultats", "pptx"),
    ("Exporte le rapport complet en pdf s'il te plaît", "pdf"),
    ("Monte un dossier d'analyse sur le concurrent", "dossier"),
    ("Fais un comparatif détaillé des prix d'abonnements", "comparatif"),
    ("Ajoute cet écran à mon panier", "panier"),
    ("Trouve un billet de train pour Paris vendredi", "billet"),
])
def test_detect_vocal_cognitive_level_classifies_deliverables_to_agentic(query, expected_keyword):
    """Vérifie que toute demande de création de livrable est automatiquement classée en délégation agentique L2."""
    res = detect_vocal_cognitive_level(query)
    assert res["level"] >= 2, f"La requête '{query}' doit être classée au moins en L2"
    rec_tools = res["recommended_tools"]
    assert ("run_agentic_task" in rec_tools) or ("browser_task" in rec_tools), (
        f"Les outils recommandés doivent contenir run_agentic_task ou browser_task pour '{query}'"
    )

    # Vérification également du besoin agentique indépendant
    is_agentic, mission_kind = _detect_agentic_need(query)
    assert is_agentic is True, f"La requête '{query}' doit être identifiée comme mission agentique"
