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


def test_search_router_structured_navigation_l2():
    """Les requêtes de navigation web structurée doivent router vers L2 (browser_task)."""
    nav_queries = [
        "Ajoute ce produit au panier sur Amazon",
        "Réserve un billet de train sur SNCF Connect",
        "Connecte-toi à mon espace client et télécharge la facture",
        "Remplis le formulaire de contact sur le site",
        "Va sur https://example.com/login et valide",
    ]
    for query in nav_queries:
        decision = route_search_intent(query)
        assert decision.level == "L2", f"Query '{query}' did not route to L2"
        assert decision.tool == "browser_task"
        assert decision.tier == 2
        assert decision.effort == "medium"
        assert decision.timeout == 120
        assert "gemini-2.5-flash" in decision.model_name


def test_search_router_deep_research_l3():
    """Les études de fond et recherches multi-sources doivent router vers L3 (launch_deep_research)."""
    deep_queries = [
        "Fais une analyse approfondie du marché des réacteurs nucléaires SMR",
        "Cartographie exhaustive de l'écosystème IA en Europe avec rapport complet",
        "Étude de marché comparative sur les néobanques françaises",
        "État de l'art sur les architectures transformer pour la robotique",
    ]
    for query in deep_queries:
        decision = route_search_intent(query)
        assert decision.level == "L3", f"Query '{query}' did not route to L3"
        assert decision.tool == "launch_deep_research"
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

    # Override L3 prioritaire
    override_l3_queries = [
        "Analyse en profondeur la situation politique au Japon",
        "Prends tout ton temps pour examiner les bilans financiers de Tesla",
        "Deep research sur les batteries solides",
    ]
    for query in override_l3_queries:
        decision = route_search_intent(query)
        assert decision.level == "L3"
        assert decision.tool == "launch_deep_research"
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
            args={"consigne": topic},
        )
        assert result.get("evidence") == "idempotent_dedup"
        assert "déjà en cours" in result.get("user_message", "")
    finally:
        release_search_lock(topic)
        release_search_lock(topic)
