"""
Tests exhaustifs pour le Routage Cognitif Dynamique en 3 Paliers (Tiering)
et la Gestion Quota-Aware avec Bascule Automatique (Dégradation Gracieuse)
pour Antigravity CLI dans J.A.R.V.I.S.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from google_antigravity import (
    CognitiveConfig,
    resolve_cognitive_tier,
    resolve_cli_model_args,
    COGNITIVE_TIER_1,
    COGNITIVE_TIER_2,
    COGNITIVE_TIER_3,
    AntigravityQuotaExhaustedError,
    TaskResult,
    AntigravityAgent,
)
from services.reasoning_service import (
    AutonomousReasoningEngine,
    reasoning_engine,
)
from services.agentic_dispatcher import agentic_dispatcher
from core.tools.dispatcher import dispatch_tool


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validation de la Résolution des Tiers Cognitifs
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_tier_1_static_missions():
    """Vérifie que les missions simples ciblent le Tier 1 (3.8-flash low)."""
    for mission in ["doc_sync", "book_curation", "email_simple", "log_check", "documentation"]:
        cfg = resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 1
        assert "flash" in cfg.model.lower()
        assert cfg.thinking_level == "low"
        assert cfg.timeout_seconds <= 120


def test_resolve_tier_2_tactical_missions():
    """Vérifie que les missions intermédiaires ciblent le Tier 2 (3.8-flash high)."""
    for mission in ["transport_optimizer", "spreadsheet_modeler", "email_analysis", "email_drafting", "memory_consolidation"]:
        cfg = resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 2
        assert "flash" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.timeout_seconds == 300


def test_resolve_tier_3_heavy_missions():
    """Vérifie que les missions de haute ingénierie ciblent le Tier 3 (3.1-pro high)."""
    for mission in ["deep_research", "system_healing", "code_refactoring", "healing"]:
        cfg = resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 3
        assert "pro" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.timeout_seconds >= 600


def test_resolve_free_query_defaults_to_tier_2_to_preserve_quota():
    """Une requête ouverte simple sans mission_type ni code lourd doit adopter le Tier 2."""
    query = "Jarvis, peux-tu me préparer un plan pour ranger mon bureau ce week-end ?"
    cfg = resolve_cognitive_tier(query=query)
    assert cfg.tier == 2
    assert "flash" in cfg.model.lower()
    assert cfg.thinking_level == "high"


def test_resolve_free_query_with_complexity_heuristic_targets_tier_3():
    """Une requête avec code ou mots-clés d'architecture complexes doit mobiliser le Tier 3."""
    query = (
        "Peux-tu faire un audit complet de l'architecture du routeur voice.py ? "
        "Il y a un bug de concurrence asynchrone délicat dans la gestion des WebSockets : "
        "```python\nasync def handler():\n    await queue.get()\n```"
    )
    cfg = resolve_cognitive_tier(query=query)
    assert cfg.tier == 3
    assert "pro" in cfg.model.lower()
    assert cfg.thinking_level == "high"


def test_explicit_overrides_priority():
    """Les consignes explicites de vitesse ou d'effort doivent surcharger les heuristiques."""
    # 1. intensite_reflexion rapide force Tier 1 même sur un sujet complexe
    cfg1 = resolve_cognitive_tier(
        query="Refactorise tout le serveur FastAPI immédiatement",
        intensite_reflexion="rapide"
    )
    assert cfg1.tier == 1

    # 2. intensite_reflexion approfondie force Tier 3 même sur un sujet anodin
    cfg2 = resolve_cognitive_tier(
        query="Dis-moi bonjour",
        intensite_reflexion="approfondie"
    )
    assert cfg2.tier == 3

    # 3. Instruction orale rapide dans la requête
    cfg3 = resolve_cognitive_tier(
        query="Fais une passe rapide avec Flash sur cette fonction",
    )
    assert cfg3.tier == 1

    # 4. Instruction orale approfondie dans la requête
    cfg4 = resolve_cognitive_tier(
        query="Prends tout ton temps et réfléchis au maximum pour analyser ce problème",
    )
    assert cfg4.tier == 3


def test_resolve_cli_model_args_contains_thinking_and_model():
    """Vérifie que la résolution des drapeaux CLI injecte --model et --thinking."""
    cfg = CognitiveConfig(model="gemini-3.8-flash", thinking_level="high", tier=2, timeout_seconds=300)
    args = resolve_cli_model_args(cfg)
    assert "--model" in args
    assert any("gemini-3.8-flash" in a for a in args)
    assert "--thinking" in args
    assert "high" in args


# ─────────────────────────────────────────────────────────────────────────────
# 2. Validation de la Résilience Quota (Dégradation Gracieuse sur Erreur 429)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reasoning_engine_quota_429_graceful_fallback():
    """
    Simule une erreur 429 / ResourceExhausted sur 3.1 Pro dans run_autonomous_investigation.
    Le moteur doit basculer automatiquement sur Tier 2 (3.8-flash-high) et réussir la mission.
    """
    engine = AutonomousReasoningEngine()

    call_count = 0

    async def mock_run_cli_task_stream(self, prompt, on_progress=None, directive_queue=None):
        nonlocal call_count
        call_count += 1
        # Premier appel (Tier 3 - gemini-3.1-pro) sature le quota
        if call_count == 1:
            raise AntigravityQuotaExhaustedError("Quota 5h épuisé sur gemini-3.1-pro (HTTP 429 ResourceExhausted)")
        # Deuxième appel (Tier 2 - gemini-3.8-flash) réussit
        return TaskResult(
            summary="# Rapport Résilient Flash\nExécution réussie sur Gemini 3.8 Flash High.",
            status="completed",
            model_label="Gemini 3.8 Flash (High)"
        )

    with patch.object(AntigravityAgent, "run_cli_task_stream", mock_run_cli_task_stream), \
         patch("services.supervision_service.supervision_service.record_event") as mock_record, \
         patch("services.briefing_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg:

        # Lancer avec un prompt complexe (qui cible Tier 3)
        res = await engine.run_autonomous_investigation(
            goal="Refactorisation de fond de l'architecture du serveur avec audit approfondi",
            model="gemini-3.1-pro-high",
            allow_quota_fallback=True,
        )

        # Vérifier que le résultat est un succès
        assert res["status"] == "completed"
        assert "Rapport Résilient Flash" in res["full_output"]
        assert call_count == 2

        # Vérifier que l'alerte supervision a été émise
        assert mock_record.called
        event_args = mock_record.call_args[0]
        assert event_args[0] == "QUOTA_FALLBACK"


@pytest.mark.asyncio
async def test_agentic_dispatcher_quota_429_graceful_fallback():
    """
    Simule une erreur 429 sur une mission agentique système (system_healing, Tier 3).
    L'agentic_dispatcher doit basculer sur Tier 2 et notifier Pierre sans planter.
    """
    call_count = 0

    async def mock_run_cli_task_stream(self, prompt, on_progress=None, directive_queue=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise AntigravityQuotaExhaustedError("Quota glissant 5h dépassé sur Gemini Pro")
        return TaskResult(
            summary="Patch appliqué avec succès via repli Gemini 3.8 Flash High.",
            status="completed",
            model_label="Gemini 3.8 Flash (High)"
        )

    with patch.object(AntigravityAgent, "run_cli_task_stream", mock_run_cli_task_stream), \
         patch("services.briefing_service.briefing_service.send_telegram_alert", new_callable=AsyncMock) as mock_tg, \
         patch("services.agentic_dispatcher.safe_send_live_client_content", new_callable=AsyncMock) as mock_voice:

        launch_res = await agentic_dispatcher.launch_agentic_mission(
            mission_type="system_healing",
            goal="Corriger le crash de concurrence sur le websocket",
            context={"file": "routers/voice.py"},
        )

        assert launch_res["status"] == "launched_in_background"
        mission_id = launch_res["mission_id"]

        state = agentic_dispatcher.get_mission_status(mission_id)
        assert state is not None

        # Laisser la tâche asynchrone s'exécuter
        if state.get("async_task"):
            await state["async_task"]

        assert state["status"] == "completed"
        assert call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validation de l'Outil ask_deep_reasoning dans dispatch_tool
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_tool_ask_deep_reasoning_requires_confirmation_with_tier():
    """
    Vérifie que dispatch_tool sur ask_deep_reasoning résout le bon cognitive_tier
    dans la réponse d'attente de confirmation utilisateur.
    """
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    # Requête rapide -> Tier 1
    res1 = await dispatch_tool(
        name="ask_deep_reasoning",
        args={"question": "Inspecte rapidement ces logs", "intensite_reflexion": "rapide"},
        websocket=mock_ws,
        session=mock_session,
        is_paid_live=False,
        live_display_label="Gemini 3.8 Live",
    )
    assert res1.get("status") == "requires_user_confirmation"
    assert res1.get("cognitive_tier") == 1

    # Requête de fond -> Tier 3
    res2 = await dispatch_tool(
        name="ask_deep_reasoning",
        args={"question": "Refactorisation complète et audit d'architecture", "intensite_reflexion": "approfondie"},
        websocket=mock_ws,
        session=mock_session,
        is_paid_live=False,
        live_display_label="Gemini 3.8 Live",
    )
    assert res2.get("status") == "requires_user_confirmation"
    assert res2.get("cognitive_tier") == 3


@pytest.mark.asyncio
async def test_dispatch_tool_ask_deep_reasoning_confirmed_launches_bg_task():
    """
    Vérifie que lorsque confirmed_by_user=True, dispatch_tool lance la tâche d'arrière-plan
    avec le modèle et le palier cognitif résolus.
    """
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("services.reasoning_service.run_deep_reasoning", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {
            "status": "completed",
            "summary": "Analyse tactique achevée.",
            "artifact_filename": "rapport.md"
        }

        res = await dispatch_tool(
            name="ask_deep_reasoning",
            args={
                "question": "Modélisation de formule de marge",
                "confirmed_by_user": True,
                "intensite_reflexion": "tactique",
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Live",
        )

        assert res.get("status") == "launched_in_background"
        assert "Antigravity" in res.get("engine", "")
