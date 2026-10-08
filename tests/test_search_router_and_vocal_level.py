# -*- coding: utf-8 -*-
"""
Tests unitaires pour le routeur de recherche déterministe et la détection
du niveau cognitif vocal L1/L2/L3 (P2).
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from services.search_router import (
    SearchRoutingDecision,
    route_search_intent,
    acquire_search_lock,
    release_search_lock,
    is_search_in_progress,
    clear_all_search_locks,
)
from services.live_mode_policy import (
    detect_vocal_cognitive_level,
    LiveModePolicy,
    decide,
)
from services.model_routing.model_router import (
    select_model,
    TASK_TYPE_MAPPING,
)


@pytest.fixture(autouse=True)
def cleanup_locks():
    clear_all_search_locks()
    yield
    clear_all_search_locks()


# ─── 1. Tests Routeur de Recherche Déterministe ───────────────────────────────

def test_search_router_ambiguous_defaults_to_l1():
    """Une requête ambiguë ou courte doit toujours router vers L1 (search_web)."""
    ambiguous_queries = [
        "Quelle heure est-il à Tokyo ?",
        "Météo Paris",
        "Qui a gagné le match hier ?",
        "Prix du Bitcoin",
        "Python asyncio documentation",
    ]
    for query in ambiguous_queries:
        decision = route_search_intent(query)
        assert isinstance(decision, SearchRoutingDecision)
        assert decision.level == "L1", f"Query '{query}' did not route to L1"
        assert decision.tool == "search_web"
        assert decision.tier == 1
        assert decision.effort == "low"
        assert decision.timeout == 15
        assert "gemini-2.5-flash" in decision.model_name
        assert decision.reason != ""


def test_search_router_multi_agent_cli_l2():
    """Les requêtes de comparatif et analyse multi-sources doivent router vers L2 (launch_deep_research)."""
    l2_queries = [
        "Fais une analyse tactique et comparative des solutions CRM",
        "Compare en détail les frameworks React et Vue",
        "Analyse multi-sources sur les coûts de l'énergie en Europe",
        "Fais un benchmark technique des bases vectorielles",
    ]
    for query in l2_queries:
        decision = route_search_intent(query)
        assert decision.level == "L2", f"Query '{query}' did not route to L2"
        assert decision.tool == "launch_deep_research"
        assert decision.tool != "browser_task"
        assert decision.tier == 2
        assert decision.effort == "medium"
        assert decision.timeout == 120
        assert "gemini-2.5-flash" in decision.model_name


def test_search_router_deep_research_l3():
    """Les études de fond et recherches approfondies doivent router vers L3 (browser_task avec recipe gemini_deep_research)."""
    deep_queries = [
        "Fais une analyse approfondie du marché des réacteurs nucléaires SMR",
        "Cartographie exhaustive de l'écosystème IA en Europe avec rapport complet",
        "Étude de marché comparative sur les néobanques françaises",
        "État de l'art sur les architectures transformer pour la robotique",
    ]
    for query in deep_queries:
        decision = route_search_intent(query)
        assert decision.level == "L3", f"Query '{query}' did not route to L3"
        assert decision.tool == "browser_task"
        assert decision.tool != "launch_deep_research"
        assert decision.recipe == "gemini_deep_research"
        assert decision.tier == 3
        assert decision.effort == "high"
        assert decision.timeout == 600
        assert "gemini-2.5-pro" in decision.model_name


def test_search_router_vocal_overrides():
    """Les modificateurs vocaux explicites priment sur le contenu textuel."""
    # Override L1 prioritaire même si le sujet semble large
    override_l1_queries = [
        "Fais vite, donne-moi les dernières avancées sur la fusion nucléaire",
        "Passe rapide : qui est le CEO d'OpenAI ?",
        "En 2 secondes, résume la situation",
    ]
    for query in override_l1_queries:
        decision = route_search_intent(query)
        assert decision.level == "L1"
        assert decision.tool == "search_web"
        assert decision.is_override is True
        assert decision.tier == 1

    # Override L2 tactique multi-agent CLI
    override_l2_queries = [
        "Fais une analyse tactique de la situation",
        "Passe au niveau deux pour comparer",
    ]
    for query in override_l2_queries:
        decision = route_search_intent(query)
        assert decision.level == "L2"
        assert decision.tool == "launch_deep_research"
        assert decision.tool != "browser_task"
        assert decision.tier == 2
        assert decision.is_override is True

    # Override L3 prioritaire -> browser_task (gemini_deep_research)
    override_l3_queries = [
        "Analyse en profondeur la situation politique au Japon",
        "Prends tout ton temps pour examiner les bilans financiers de Tesla",
        "Deep research sur les batteries solides",
    ]
    for query in override_l3_queries:
        decision = route_search_intent(query)
        assert decision.level == "L3"
        assert decision.tool == "browser_task"
        assert decision.tool != "launch_deep_research"
        assert decision.recipe == "gemini_deep_research"
        assert decision.is_override is True
        assert decision.tier == 3


# ─── 2. Tests Détection Niveau Cognitif Vocal ─────────────────────────────────

def test_detect_vocal_cognitive_level_defaults_to_l1():
    """Par défaut et en cas d'ambiguïté, la détection vocale retourne L1."""
    res = detect_vocal_cognitive_level("Bonjour Jarvis, que penses-tu de la météo ?")
    assert res["level"] == 1
    assert res["level_name"] == "L1"
    assert "Défaut L1" in res["reason"] or "L1" in res["reason"] or "fait direct" in res["reason"]
    assert "search_web" in res["recommended_tools"]


def test_detect_vocal_cognitive_level_overrides():
    """Détection des différents modificateurs vocaux."""
    # L1 Overrides
    l1_cases = [
        "Fais vite Jarvis",
        "En rapide s'il te plaît",
        "En 2 secondes",
        "Flash info rapide",
    ]
    for text in l1_cases:
        res = detect_vocal_cognitive_level(text)
        assert res["level"] == 1
        assert res["level_name"] == "L1"
        assert "search_web" in res["recommended_tools"]

    # L2 Overrides / Navigation
    l2_cases = [
        "Fais une analyse tactique de l'incident",
        "Ajoute cet article à mon panier",
        "Réserve une table pour 2",
    ]
    for text in l2_cases:
        res = detect_vocal_cognitive_level(text)
        assert res["level"] == 2
        assert res["level_name"] == "L2"
        assert "browser_task" in res["recommended_tools"]

    # L3 Overrides / Profondeur
    l3_cases = [
        "Analyse en profondeur ce problème",
        "Prends tout ton temps pour chercher",
        "Fais une étude de fond exhaustive",
        "Lance une recherche approfondie",
        "Fais une recherche de niveau 3",
        "Recherche niveau 3 sur l'IA quantique",
        "Lance une recherche L3",
    ]
    for text in l3_cases:
        res = detect_vocal_cognitive_level(text)
        assert res["level"] == 3
        assert res["level_name"] == "L3"
        assert "launch_deep_research" in res["recommended_tools"]


# ─── 3. Tests LiveModePolicy & ModelRouter ────────────────────────────────────

def test_live_mode_policy_decide_propagation():
    """Vérifie que LiveModePolicy intègre cognitive_level et recommended_tools."""
    policy = LiveModePolicy()
    
    # 1. Requête standard -> L1
    res_l1 = policy.decide(transcript="Quel est le cours de l'or ?")
    assert res_l1["cognitive_level"] == 1
    assert res_l1["cognitive_level_name"] == "L1"
    assert "search_web" in res_l1["recommended_tools"]
    assert "flash" in res_l1["model_tier"]

    # 2. Requête profonde -> L3
    res_l3 = policy.decide(transcript="Analyse en profondeur l'impact des taux d'intérêt")
    assert res_l3["cognitive_level"] == 3
    assert res_l3["cognitive_level_name"] == "L3"
    assert "launch_deep_research" in res_l3["recommended_tools"]
    assert "pro" in res_l3["model_tier"]


def test_model_router_task_mapping_and_overrides():
    """Vérifie la mise à jour des mappings de tâches et des surcharges dans model_router."""
    assert TASK_TYPE_MAPPING.get("search_web") == "simple"
    assert TASK_TYPE_MAPPING.get("browser_task") == "medium"
    assert TASK_TYPE_MAPPING.get("launch_deep_research") == "complex"

    # Override rapide
    sel_fast = select_model("Fais vite : donne le score du match")
    assert sel_fast.tier == 1

    # Override recherche approfondie
    sel_deep = select_model("Fais une analyse en profondeur du marché")
    assert sel_deep.tier == 3


# ─── 4. Tests Idempotence & Verrous Anti-Double Lancement ─────────────────────

def test_search_idempotency_locking():
    """Vérifie le fonctionnement de l'acquisition et de la libération des verrous."""
    query = "Histoire de la conquête spatiale"
    
    assert is_search_in_progress(query) is False
    
    # Premier verrouillage réussi
    assert acquire_search_lock(query) is True
    assert is_search_in_progress(query) is True
    
    # Deuxième tentative identique (même normalisée avec ponctuation/espaces) doit être rejetée
    assert acquire_search_lock(query) is False
    assert acquire_search_lock("  histoire de la conquête spatiale!  ") is False
    
    # Libération
    release_search_lock(query)
    assert is_search_in_progress(query) is False
    
    # Ré-acquisition possible
    assert acquire_search_lock(query) is True
    release_search_lock(query)


@pytest.mark.asyncio
async def test_dispatcher_search_web_idempotency():
    """Vérifie que dispatcher.dispatch_tool_call intercepte un appel concurrent dupliqué."""
    from core.tools.dispatcher import dispatch_tool_call
    
    query = "Calcul vitesse de la lumière"
    
    # Simuler un verrou actif
    acquire_search_lock(query)
    
    try:
        # L'appel à search_web doit retourner immédiatement la réponse dédoublonnée
        result = await dispatch_tool_call(
            name="search_web",
            args={"query": query},
        )
        assert result.get("status") == "done"
        assert result.get("evidence") == "idempotent_dedup"
        assert "déjà en cours" in result.get("user_message", "")
    finally:
        release_search_lock(query)


@pytest.mark.asyncio
async def test_dispatcher_launch_deep_research_idempotency():
    """Vérifie que launch_deep_research gère l'idempotence."""
    from core.tools.dispatcher import dispatch_tool_call
    
    topic = "Cartographie quantique avancée"
    acquire_search_lock(topic)
    
    try:
        result = await dispatch_tool_call(
            name="launch_deep_research",
            args={"consigne": topic, "sync": True},
        )
        assert result.get("evidence") == "idempotent_dedup"
        assert "déjà en cours" in result.get("user_message", "")
    finally:
        release_search_lock(topic)
        release_search_lock(topic)


def test_search_router_regex_l3_variations():
    """Vérifie que toutes les formulations de niveau 3 (L3, niveau 3, tier 3, etc.) routent vers L3 (browser_task avec recipe gemini_deep_research)."""
    l3_phrases = [
        "Fais une recherche de niveau 3 sur les supraconducteurs",
        "Lance une recherche L3 sur le graphène",
        "Cherche en niveau trois les entreprises de robotique",
        "Deep research sur les semi-conducteurs",
        "Palier 3 : cartographie IA",
        "Fais un L3 s'il te plaît",
        "recherche de nievau 3 sur l'espace",
        "lance une recherche nievau 3",
        "recherche l3",
        "recherche approfondie l3",
    ]
    for q in l3_phrases:
        decision = route_search_intent(q)
        assert decision.level == "L3", f"Phrase '{q}' did not route to L3"
        assert decision.tool == "browser_task"
        assert decision.tool != "launch_deep_research"
        assert decision.recipe == "gemini_deep_research"
        assert decision.is_override is True


@pytest.mark.asyncio
async def test_dispatcher_browser_task_executes_l3_when_l3_requested():
    """Vérifie que browser_task traite directement la recherche L3 avec recipe gemini_deep_research."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult

    fake_browser_res = ToolResult.done(
        user_message="Synthèse L3",
        evidence="recipe gemini_deep_research",
        verified=True,
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res) as mock_browser, \
         patch("services.local_agent_service.is_pc_connected", return_value=True):
        resp = await dispatch_tool(
            name="browser_task",
            args={"goal": "Fais une recherche de niveau 3 sur les entreprises de Malmö", "sync": True},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "done"
        mock_browser.assert_awaited_once()
        task = mock_browser.await_args.kwargs.get("task") or mock_browser.await_args.args[0]
        assert task.recipe == "gemini_deep_research"


@pytest.mark.asyncio
async def test_dispatcher_browser_task_handles_recipe_gemini_deep_research():
    """Vérifie que browser_task avec recipe='gemini_deep_research' exécute la recherche web L3."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult

    fake_browser_res = ToolResult.done(
        user_message="Synthèse recette",
        evidence="recipe gemini_deep_research",
        verified=True,
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res) as mock_browser, \
         patch("services.local_agent_service.is_pc_connected", return_value=True):
        resp = await dispatch_tool(
            name="browser_task",
            args={"goal": "Entreprises spatiales", "recipe": "gemini_deep_research", "sync": True},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "done"
        mock_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_search_web_redirects_to_l3():
    """Vérifie que search_web redirige automatiquement vers browser_task (gemini_deep_research) pour une requête L3."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult

    fake_browser_res = ToolResult.done(
        user_message="Synthèse L3",
        evidence="recipe gemini_deep_research",
        verified=True,
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res) as mock_browser, \
         patch("services.local_agent_service.is_pc_connected", return_value=True):
        resp = await dispatch_tool(
            name="search_web",
            args={"query": "Recherche de niveau 3 sur l'IA quantique", "sync": True},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "done"
        mock_browser.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatcher_ask_deep_reasoning_redirects_l3_research_to_deep_research():
    """Une demande de recherche L3 ne doit pas retomber sur le pipeline de raisonnement L2."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult

    fake_browser_res = ToolResult.done(
        user_message="Synthèse L3",
        evidence="recipe gemini_deep_research",
        verified=True,
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res) as mock_browser:
        resp = await dispatch_tool(
            name="ask_deep_reasoning",
            args={"question": "Fais une recherche de niveau 3 sur l'IA quantique", "sync": True},
            websocket=None,
            session=None,
        )

    assert resp["status"] == "done"
    mock_browser.assert_awaited_once()
    task = mock_browser.await_args.kwargs.get("task") or mock_browser.await_args.args[0]
    assert task.recipe == "gemini_deep_research"


@pytest.mark.asyncio
async def test_dispatcher_exposes_sanitized_execution_error_detail():
    """Le retour vocal doit contenir le motif technique, sans exposer de secret."""
    from core.tools.dispatcher import dispatch_tool

    with patch(
        "core.tools.dispatcher._execute_dispatch_tool",
        new_callable=AsyncMock,
        side_effect=RuntimeError("connexion refusée vers le serveur de recherche"),
    ):
        resp = await dispatch_tool(
            name="test_tool",
            args={},
            websocket=None,
            session=None,
        )

    assert resp["status"] == "failed"
    assert "connexion refusée" in resp["user_message"]
    assert "serveur de recherche" in resp["user_message"]
    assert resp["error_hint"] == resp["user_message"].split(" : ", 1)[1]


@pytest.mark.asyncio
async def test_dispatcher_launch_deep_research_non_blocking_returns_started():
    """Vérifie que launch_deep_research retourne instantanément ToolResult.started (non-bloquant)."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult
    from core.shared_state import active_task_controller

    fake_browser_res = ToolResult.done(
        user_message="Synthèse L3 rapide",
        evidence="recipe gemini_deep_research",
        verified=True,
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=fake_browser_res) as mock_browser:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Étude prospective non bloquante"},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "started"
        assert "niveau 2" in resp["user_message"].lower() or "analyse multi-agents" in resp["user_message"].lower()
        assert active_task_controller.get("deep_research_bg_task") is not None
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_dispatcher_launch_deep_research_bg_failure_injects_voice():
    """Vérifie que l'échec en tâche de fond de launch_deep_research injecte une explication vocale claire."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult
    from services.voice_injection_queue import voice_injection_queue

    failed_res = ToolResult.failed(
        user_message="Antigravity CLI n'est pas disponible sur le serveur VPS.",
        error_hint="cli_not_ready",
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=ToolResult.failed("PC offline", "pc_offline")), \
         patch("services.local_agent_service.is_pc_connected", return_value=False), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(False, "cli_not_ready", None)), \
         patch.object(voice_injection_queue, "enqueue", new_callable=AsyncMock) as mock_enqueue:
        resp = await dispatch_tool(
            name="launch_deep_research",
            args={"consigne": "Test échec vocal"},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "started"
        # Attendre l'exécution de la tâche de fond
        await asyncio.sleep(0.1)
        mock_enqueue.assert_awaited()
        call_kwargs = mock_enqueue.await_args.kwargs
        assert "n'a pas pu aboutir" in call_kwargs.get("text", "") or "échoué" in call_kwargs.get("text", "")


@pytest.mark.asyncio
async def test_dispatcher_browser_task_l3_fallback_announces_repli_cli():
    """Si la recherche web L3 échoue, browser_task bascule sur le CLI et annonce explicitement [Repli CLI]."""
    from core.tools.dispatcher import dispatch_tool
    from core.tools.result import ToolResult
    from services.google_antigravity import AgentOutput

    mock_agent_out = AgentOutput(
        status="success",
        conclusion="Synthèse CLI de secours",
        sources=["https://example.com"],
        confidence="high",
    )

    with patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock, return_value=ToolResult.failed("Navigation web échouée", "web_timeout")), \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock, return_value=mock_agent_out), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True):
        resp = await dispatch_tool(
            name="browser_task",
            args={"goal": "Thèse sur la supraconductivité", "recipe": "gemini_deep_research", "sync": True},
            websocket=None,
            session=None,
        )
        assert resp["status"] == "done"
        assert "[Repli CLI]" in resp["user_message"]
        assert resp.get("fallback_used") is True
        assert resp.get("cli_fallback") is True
        assert resp.get("web_search_failed") is True


def test_search_router_extracts_target_pages():
    """Vérifie que route_search_intent extrait correctement le nombre de pages demandé."""
    cases = [
        ("Fais un rapport L2 de 5 pages sur l'IA générative", 5),
        ("Rédige une analyse tactique de 10 pages sur l'énergie", 10),
        ("Rapport pdf de 3 pages comparant AWS et GCP", 3),
        ("Document latex de 4 pages sur la cybersécurité", 4),
        ("Analyse de 1 page sur le marché", 1),
    ]
    for query, expected_pages in cases:
        decision = route_search_intent(query)
        assert decision.level == "L2", f"Query '{query}' did not route to L2"
        assert decision.tool == "launch_deep_research"
        assert decision.target_pages == expected_pages, f"Query '{query}' expected {expected_pages} pages, got {decision.target_pages}"


@pytest.mark.asyncio
async def test_dispatcher_launch_deep_research_handles_target_pages():
    """Vérifie que launch_deep_research transmet target_pages au pipeline L2."""
    from core.tools.dispatcher import dispatch_tool
    from services.latex_report_service import LatexReportResult

    fake_latex_res = LatexReportResult(
        success=True,
        pdf_path="/tmp/workspace/reports/rapport_l2.pdf",
        md_path="/tmp/workspace/reports/rapport_l2.md",
        tex_path="/tmp/workspace/reports/rapport_l2.tex",
        user_notice="Rapport PDF généré avec succès.",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher._execute_cli_map_reduce_pipeline", new_callable=AsyncMock) as mock_pipeline:
        
        from core.tools.result import ToolResult
        mock_pipeline.return_value = ToolResult.done(
            user_message="Rapport L2 5 pages généré.",
            verified=True,
            evidence="Rapport PDF compilé",
        )

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Étude tactique sur les semi-conducteurs",
                "target_pages": 5,
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        mock_pipeline.assert_awaited_once()
        _, kwargs = mock_pipeline.call_args
        assert kwargs.get("target_pages") == 5



