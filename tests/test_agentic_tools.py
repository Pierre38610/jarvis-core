"""tests/test_agentic_tools.py
Tests unitaires et d'intégration pour le câblage agentique dans le dispatcher Gemini Live.
Vérifie :
1. Déclarations des outils agentiques et filtrage si le CLI agy n'est pas prêt.
2. Routage vers run_agentic avec les bons paramètres (rôle, prompt, modèle agy validé, effort).
3. Modèles validés sur VPS : flash = "flash", pro = "pro".
4. Cycles multi-phases de deep research : Prospecteur (flash/medium) -> Analyste (pro/high) -> Synthèse (pro/medium).
5. Supervision des sous-agents (spawn/update/complete) avec modèle, effort et durée.
6. Restitution systématique au format ToolResult strict (status, verified).

Conforme à no-paid-api-in-tests.md : 100% mocks, aucun appel API payant.
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.tools.declarations import (
    AGENTIC_TOOL_NAMES,
    filter_agentic_tools,
    get_tools_list,
    get_tools_list_for_session,
)
from core.tools.dispatcher import dispatch_tool
from services.google_antigravity import (
    MODEL_FLASH,
    MODEL_PRO,
    AgentOutput,
)


@pytest.fixture(autouse=True)
def mock_websocket_and_session():
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_sess = AsyncMock()
    mock_sess.id = "test_live_session_123"
    return mock_ws, mock_sess


# ─── 1. Tests des Déclarations & Filtrage Session ────────────────────────────

def test_declarations_contain_agentic_tools():
    """Vérifie la présence et la clarté incitative des déclarations d'outils agentiques."""
    tools = get_tools_list(include_agentic=True)
    assert len(tools) > 0
    decl_names = [d.name for d in tools[0].function_declarations]

    for name in ("run_agentic_task", "run_agent_task", "ask_deep_reasoning", "launch_deep_research"):
        assert name in decl_names, f"L'outil {name} doit être présent dans les déclarations."

    # Vérification des descriptions proactives et concises
    decl_map = {d.name: d for d in tools[0].function_declarations}
    for tool_name in ("run_agentic_task", "ask_deep_reasoning", "launch_deep_research"):
        decl = decl_map[tool_name]
        desc = decl.description.lower()
        assert "initiative" in desc, f"La description de {tool_name} doit inciter à l'usage proactif."


def test_declarations_filter_when_agentic_disabled():
    """Vérifie le retrait effectif des outils agentiques lorsque include_agentic est False."""
    tools = get_tools_list(include_agentic=False)
    decl_names = [d.name for d in tools[0].function_declarations]
    for name in AGENTIC_TOOL_NAMES:
        assert name not in decl_names, f"{name} ne doit pas être présent quand include_agentic=False"


@pytest.mark.asyncio
async def test_get_tools_list_for_session_adapts_to_cli_ready():
    """Vérifie que la session retire les outils agentiques si verify_antigravity_cli_ready() échoue."""
    with patch("services.google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready:
        # Cas 1 : CLI indisponible -> outils agentiques retirés
        mock_ready.return_value = (False, "Binaire agy introuvable", None)
        tools_unavailable = await get_tools_list_for_session()
        names_unavail = [d.name for d in tools_unavailable[0].function_declarations]
        assert "run_agentic_task" not in names_unavail
        assert "ask_deep_reasoning" not in names_unavail
        assert "launch_deep_research" not in names_unavail

        # Cas 2 : CLI opérationnel -> outils agentiques présents
        mock_ready.return_value = (True, "Antigravity CLI opérationnel", "/usr/local/bin/agy")
        tools_available = await get_tools_list_for_session()
        names_avail = [d.name for d in tools_available[0].function_declarations]
        assert "run_agentic_task" in names_avail
        assert "run_agent_task" in names_avail
        assert "ask_deep_reasoning" in names_avail
        assert "launch_deep_research" in names_avail


# ─── 2. Test Priorité 1 : Appel Live → run_agentic → ToolResult ─────────────

@pytest.mark.asyncio
async def test_run_agentic_task_live_to_toolresult(mock_websocket_and_session):
    """Priorité 1 : simule un appel d'outil Live → run_agentic (agy mocké) → ToolResult (status, verified)."""
    mock_ws, mock_sess = mock_websocket_and_session

    mock_output = AgentOutput(
        conclusion="Audit d'architecture validé : 0 vulnérabilité détectée.",
        confidence=0.98,
        sources=["code/core.py", "security_rules.md"],
        open_questions=[],
        artifacts=["audit_report.json"],
        model="flash",
        effort="medium",
        status="success",
        raw_output='{"conclusion": "Audit validé"}',
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready, \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_run, \
         patch("core.tools.dispatcher.spawn_subagent", new_callable=AsyncMock) as mock_spawn, \
         patch("core.tools.dispatcher.update_subagent", new_callable=AsyncMock) as mock_update, \
         patch("core.tools.dispatcher.complete_subagent", new_callable=AsyncMock) as mock_complete:

        mock_ready.return_value = (True, "Antigravity CLI opérationnel", "/bin/agy")
        mock_run.return_value = mock_output

        # Appel Live via le dispatcher
        tool_args = {
            "objectif": "Vérifier la conformité de sécurité",
            "contexte": "Codebase Python FastAPI",
            "livrable_attendu": "Rapport structuré",
            "model_override": "flash",
            "effort_override": "medium",
        }
        res = await dispatch_tool(
            name="run_agentic_task",
            args=tool_args,
            websocket=mock_ws,
            session=mock_sess,
        )

        # 1. Vérification du routage vers run_agentic avec les bons paramètres
        assert mock_run.called
        run_kwargs = mock_run.call_args.kwargs
        assert run_kwargs["model"] == MODEL_FLASH  # "flash"
        assert run_kwargs["effort"] == "medium"
        assert "Vérifier la conformité de sécurité" in run_kwargs["prompt"]
        assert "Codebase Python FastAPI" in run_kwargs["prompt"]
        assert "Rapport structuré" in run_kwargs["prompt"]

        # 2. Vérification de la supervision (spawn, update, complete)
        assert mock_spawn.called
        assert mock_spawn.call_args.kwargs["model"] == MODEL_FLASH
        assert mock_update.called
        assert mock_complete.called
        comp_summary = mock_complete.call_args.kwargs["summary"]
        assert "flash" in comp_summary
        assert "medium" in comp_summary

        # 3. Vérification du contrat ToolResult retourné au modèle Live
        assert res["status"] == "done"
        assert res["verified"] is True
        assert res["user_message"] == "Audit d'architecture validé : 0 vulnérabilité détectée."
        assert "flash" in res["evidence"]
        assert "medium" in res["evidence"]
        assert res["conclusion"] == "Audit d'architecture validé : 0 vulnérabilité détectée."


@pytest.mark.asyncio
async def test_run_agent_task_alias_direct(mock_websocket_and_session):
    """Vérifie que l'alias direct 'run_agent_task' fonctionne de manière identique."""
    mock_ws, mock_sess = mock_websocket_and_session
    mock_output = AgentOutput(
        conclusion="Action autonome réalisée.",
        confidence=0.92,
        model="pro",
        effort="high",
        status="success",
        raw_output="{}",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready, \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_run, \
         patch("core.tools.dispatcher.spawn_subagent", new_callable=AsyncMock), \
         patch("core.tools.dispatcher.update_subagent", new_callable=AsyncMock), \
         patch("core.tools.dispatcher.complete_subagent", new_callable=AsyncMock):

        mock_ready.return_value = (True, "OK", "/bin/agy")
        mock_run.return_value = mock_output

        res = await dispatch_tool(
            name="run_agent_task",
            args={"objectif": "Mission avec paramètres par défaut"},
            websocket=mock_ws,
            session=mock_sess,
        )

        assert mock_run.called
        run_kwargs = mock_run.call_args.kwargs
        assert run_kwargs["model"] == MODEL_PRO  # "pro" par défaut
        assert run_kwargs["effort"] == "high"    # "high" par défaut
        assert res["status"] == "done"
        assert res["verified"] is True


# ─── 3. Test ask_deep_reasoning via run_agentic ─────────────────────────────

@pytest.mark.asyncio
async def test_ask_deep_reasoning_routing(mock_websocket_and_session):
    """Vérifie le routage de ask_deep_reasoning vers run_agentic avec supervision et ToolResult."""
    mock_ws, mock_sess = mock_websocket_and_session
    mock_output = AgentOutput(
        conclusion="L'option B est la plus optimale selon l'analyse critique.",
        confidence=0.96,
        model="pro",
        effort="high",
        status="success",
        raw_output="{}",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready, \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_run, \
         patch("core.tools.dispatcher.spawn_subagent", new_callable=AsyncMock) as mock_spawn, \
         patch("core.tools.dispatcher.complete_subagent", new_callable=AsyncMock) as mock_complete:

        mock_ready.return_value = (True, "OK", "/bin/agy")
        mock_run.return_value = mock_output

        res = await dispatch_tool(
            name="ask_deep_reasoning",
            args={"question": "Quel trade-off choisir entre A et B ?", "model_override": "pro", "effort_override": "high"},
            websocket=mock_ws,
            session=mock_sess,
        )

        assert mock_run.called
        kwargs = mock_run.call_args.kwargs
        assert kwargs["role"] == "reasoning"
        assert kwargs["model"] == MODEL_PRO
        assert kwargs["effort"] == "high"
        assert res["status"] == "done"
        assert res["verified"] is True
        assert "L'option B" in res["user_message"]
        assert mock_spawn.called
        assert mock_complete.called


# ─── 4. Test launch_deep_research en 3 phases ────────────────────────────────

@pytest.mark.asyncio
async def test_launch_deep_research_three_phases(mock_websocket_and_session):
    """Vérifie les 3 phases de launch_deep_research :
    Phase 1 : Prospecteur (flash/medium)
    Phase 2 : Analyste (pro/high)
    Phase 3 : Synthèse (pro/medium)
    """
    mock_ws, mock_sess = mock_websocket_and_session

    out_p = AgentOutput(
        conclusion="15 entreprises du secteur quantique répertoriées.",
        confidence=0.90,
        sources=["nature.com", "arxiv.org"],
        model="flash",
        effort="medium",
        status="success",
    )
    out_a = AgentOutput(
        conclusion="Triangulation terminée, 3 leaders identifiés avec brevets solides.",
        confidence=0.95,
        sources=["patent_office.gov"],
        open_questions=["Financement série B ?"],
        model="pro",
        effort="high",
        status="success",
    )
    out_s = AgentOutput(
        conclusion="Synthèse exécutive : Opportunités d'investissement dans le calcul quantique.",
        confidence=0.94,
        artifacts=["synthese_quantique.md"],
        model="pro",
        effort="medium",
        status="success",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready, \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_run, \
         patch("core.tools.dispatcher.spawn_subagent", new_callable=AsyncMock) as mock_spawn, \
         patch("core.tools.dispatcher.complete_subagent", new_callable=AsyncMock) as mock_complete:

        mock_ready.return_value = (True, "OK", "/bin/agy")
        mock_run.side_effect = [out_p, out_a, out_s]

        res = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Étude du marché quantique européen", "sync": True},
            websocket=mock_ws,
            session=mock_sess,
        )

        # 3 appels consécutifs à run_agentic
        assert mock_run.call_count == 3

        call_p, call_a, call_s = mock_run.call_args_list

        # Phase 1 : Prospecteur flash/medium
        assert call_p.kwargs["role"] == "prospector"
        assert call_p.kwargs["model"] == MODEL_FLASH
        assert call_p.kwargs["effort"] == "medium"

        # Phase 2 : Analyste pro/high
        assert call_a.kwargs["role"] == "critic"
        assert call_a.kwargs["model"] == MODEL_PRO
        assert call_a.kwargs["effort"] == "high"

        # Phase 3 : Synthèse pro/medium
        assert call_s.kwargs["role"] == "synthesis"
        assert call_s.kwargs["model"] == MODEL_PRO
        assert call_s.kwargs["effort"] == "medium"

        # Supervision pour les 3 phases
        assert mock_spawn.call_count == 3
        assert mock_complete.call_count == 3

        # Résultat ToolResult
        assert res["status"] == "done"
        assert res["verified"] is True
        assert "Synthèse exécutive" in res["user_message"]
        assert len(res["sources"]) == 3  # sources cumulées


# ─── 5. Test d'indisponibilité du CLI agy ───────────────────────────────────

@pytest.mark.asyncio
async def test_agentic_tool_fails_if_cli_not_ready(mock_websocket_and_session):
    """Vérifie que l'outil renvoie immédiatement un ToolResult failed sans exécuter run_agentic."""
    mock_ws, mock_sess = mock_websocket_and_session

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock) as mock_ready, \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock) as mock_run:

        mock_ready.return_value = (False, "Binaire agy introuvable sur le VPS", None)

        res = await dispatch_tool(
            name="run_agentic_task",
            args={"objectif": "Tâche impossible sans binaire"},
            websocket=mock_ws,
            session=mock_sess,
        )

        assert not mock_run.called
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "Binaire agy introuvable" in res["error_hint"]
