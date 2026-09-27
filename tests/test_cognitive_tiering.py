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

@pytest.mark.asyncio
async def test_resolve_tier_1_static_missions():
    """Vérifie que les missions simples ciblent le Tier 1 (3.8-flash low)."""
    for mission in ["doc_sync", "book_curation", "email_simple", "log_check", "documentation"]:
        cfg = await resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 1
        assert "flash" in cfg.model.lower()
        assert cfg.thinking_level == "low"
        assert cfg.timeout_seconds <= 120
        assert cfg.is_override is False


@pytest.mark.asyncio
async def test_resolve_tier_2_tactical_missions():
    """Vérifie que les missions intermédiaires ciblent le Tier 2 (3.8-flash high)."""
    for mission in ["transport_optimizer", "spreadsheet_modeler", "email_analysis", "email_drafting", "memory_consolidation"]:
        cfg = await resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 2
        assert "flash" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.timeout_seconds == 300
        assert cfg.is_override is False


@pytest.mark.asyncio
async def test_resolve_tier_3_heavy_missions():
    """Vérifie que les missions de haute ingénierie ciblent le Tier 3 (3.1-pro high)."""
    for mission in ["deep_research", "system_healing", "code_refactoring", "healing"]:
        cfg = await resolve_cognitive_tier(mission_type=mission)
        assert cfg.tier == 3
        assert "pro" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.timeout_seconds >= 600
        assert cfg.is_override is False


@pytest.mark.asyncio
async def test_resolve_free_query_defaults_to_tier_2_via_classifier():
    """Une requête ouverte simple classifiée en Tier 2 adopte le Tier 2."""
    with patch("services.reasoning_service.classify_query_tier_with_llm", new_callable=AsyncMock) as mock_cls:
        mock_cls.return_value = {"tier": 2, "reason": "Requête d'organisation courante"}
        query = "Jarvis, peux-tu me préparer un plan pour ranger mon bureau ce week-end ?"
        cfg = await resolve_cognitive_tier(query=query)
        assert cfg.tier == 2
        assert "flash" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.is_override is False
        assert cfg.reason == "Requête d'organisation courante"


@pytest.mark.asyncio
async def test_resolve_free_query_targets_tier_3_via_classifier():
    """Une requête complexe classifiée en Tier 3 mobilisera le Tier 3."""
    with patch("services.reasoning_service.classify_query_tier_with_llm", new_callable=AsyncMock) as mock_cls:
        mock_cls.return_value = {"tier": 3, "reason": "Audit d'architecture et concurrence asynchrone"}
        query = (
            "Peux-tu faire un audit complet de l'architecture du routeur voice.py ? "
            "Il y a un bug de concurrence asynchrone délicat dans la gestion des WebSockets : "
            "```python\nasync def handler():\n    await queue.get()\n```"
        )
        cfg = await resolve_cognitive_tier(query=query)
        assert cfg.tier == 3
        assert "pro" in cfg.model.lower()
        assert cfg.thinking_level == "high"
        assert cfg.is_override is False
        assert cfg.reason == "Audit d'architecture et concurrence asynchrone"


@pytest.mark.asyncio
async def test_explicit_overrides_priority_over_classifier():
    """Les consignes explicites de vitesse ou d'effort doivent surcharger le classifieur sans l'appeler."""
    with patch("services.reasoning_service.classify_query_tier_with_llm", new_callable=AsyncMock) as mock_cls:
        # 1. intensite_reflexion rapide force Tier 1 même sur un sujet complexe
        cfg1 = await resolve_cognitive_tier(
            query="Refactorise tout le serveur FastAPI immédiatement",
            intensite_reflexion="rapide"
        )
        assert cfg1.tier == 1
        assert cfg1.is_override is True

        # 2. intensite_reflexion approfondie force Tier 3 même sur un sujet anodin
        cfg2 = await resolve_cognitive_tier(
            query="Dis-moi bonjour",
            intensite_reflexion="approfondie"
        )
        assert cfg2.tier == 3
        assert cfg2.is_override is True

        # 3. Instruction orale rapide dans la requête
        cfg3 = await resolve_cognitive_tier(
            query="Fais une passe rapide avec Flash sur cette fonction",
        )
        assert cfg3.tier == 1
        assert cfg3.is_override is True

        # 4. Instruction orale approfondie dans la requête
        cfg4 = await resolve_cognitive_tier(
            query="Prends tout ton temps et réfléchis au maximum pour analyser ce problème",
        )
        assert cfg4.tier == 3
        assert cfg4.is_override is True

        # Le classifieur LLM ne doit JAMAIS avoir été appelé car les overrides sont prioritaires
        assert mock_cls.call_count == 0


def test_resolve_cli_model_args_contains_effort_and_model():
    """Vérifie que la résolution des drapeaux CLI injecte --model et --effort, et bannit strictement --thinking."""
    cfg = CognitiveConfig(model="gemini-3.8-flash", thinking_level="high", tier=2, timeout_seconds=300)
    args = resolve_cli_model_args(cfg)
    assert "--model" in args
    assert any("gemini-3.8-flash" in a for a in args)
    assert "--effort" in args
    assert "high" in args
    assert "--thinking" not in args


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
    Vérifie que lorsque confirmed_by_user=True et que le pré-vol CLI est validé,
    dispatch_tool lance la tâche d'arrière-plan avec le modèle et le palier cognitif résolus.
    """
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "Antigravity CLI opérationnel", "/home/opc/.local/bin/agy")), \
         patch("services.reasoning_service.run_deep_reasoning", new_callable=AsyncMock) as mock_run:
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


@pytest.mark.asyncio
async def test_dispatch_tool_ask_deep_reasoning_fails_robustly_if_cli_unavailable():
    """
    Vérifie le garde-fou inviolable de robustesse : si le binaire Antigravity CLI n'est pas opérationnel
    sur le système, dispatch_tool REFUSE catégoriquement de déclarer que les agents sont lancés
    et renvoie une erreur explicite avec consigne claire pour Aoede.
    """
    mock_ws = AsyncMock()
    mock_session = AsyncMock()

    with patch("google_antigravity.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(False, "Binaire 'agy' introuvable sur le système", None)):
        res = await dispatch_tool(
            name="ask_deep_reasoning",
            args={
                "question": "Analyse approfondie critique",
                "confirmed_by_user": True,
                "intensite_reflexion": "approfondie",
            },
            websocket=mock_ws,
            session=mock_session,
            is_paid_live=False,
            live_display_label="Gemini 3.8 Live",
        )

        assert res.get("status") == "error"
        assert res.get("error") == "Antigravity CLI indisponible"
        assert "introuvable" in res.get("details", "").lower()
        assert "Ne prétends SURTOUT PAS" in res.get("instruction_to_jarvis", "")


@pytest.mark.asyncio
async def test_antigravity_agent_returns_error_when_binary_missing():
    """Vérifie que run_cli_task_stream renvoie status='error' et error_type='binary_not_found' sans binaire."""
    with patch("google_antigravity.find_antigravity_binary", return_value=None):
        agent = AntigravityAgent(model="gemini-3.8-flash-high")
        task_res = await agent.run_cli_task_stream("Prompt test")
        assert task_res.status == "error"
        assert task_res.error_type == "binary_not_found"
        assert "introuvable" in task_res.summary.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Validation de la Table de Log PostgreSQL et du Verrou de Clé Payante
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tier_routing_log_recorded_on_investigation():
    """Vérifie que run_autonomous_investigation journalise l'arbitrage dans tier_routing_log."""
    engine = AutonomousReasoningEngine()

    with patch("google_antigravity.AntigravityAgent.run_cli_task_stream", new_callable=AsyncMock) as mock_cli:
        mock_cli.return_value = TaskResult(summary="Investigation réussie", status="completed", model_label="Gemini 3.8 Flash (High)")
        with patch("services.memory.log_tier_routing", new_callable=AsyncMock) as mock_log:
            await engine.run_autonomous_investigation(
                goal="Optimiser les requêtes SQL",
                model="gemini-3.8-flash-high",
                chosen_tier=2,
                reason="Requête tactique",
                is_override=False
            )
            # Attend le déclenchement de la coroutine de log en tâche de fond
            await asyncio.sleep(0.05)
            assert mock_log.call_count == 1
            call_kwargs = mock_log.call_args.kwargs
            assert call_kwargs["chosen_tier"] == 2
            assert call_kwargs["final_tier"] == 2
            assert call_kwargs["fallback_occurred"] is False
            assert call_kwargs["override_manuel"] is False
            assert call_kwargs["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_fallback_does_not_consume_paid_key_silently():
    """Vérifie que lors d'un repli 429, si l'encoche payante est décochée,
    le modèle Tier 2 utilise impérativement GEMINI_API_KEY_FREE et jamais la clé payante.
    """
    engine = AutonomousReasoningEngine()
    import config
    from config import GEMINI_API_KEY_FREE

    # Simule l'encoche payante décochée
    with patch("config.is_paid_key_authorized", return_value=False):
        with patch("config.get_effective_paid_key", return_value=""):
            call_agents = []

            class FakeAgent:
                def __init__(self, workspace, model, api_key, **kwargs):
                    self.workspace = workspace
                    self.model = model
                    self.api_key = api_key
                    self.model_label = model
                    call_agents.append(self)

                async def run_cli_task_stream(self, prompt, **kwargs):
                    if len(call_agents) == 1:
                        raise AntigravityQuotaExhaustedError("Quota saturé")
                    return TaskResult(summary="OK", status="completed", model_label="Gemini 3.8 Flash (High)")

            with patch("services.reasoning_service.AntigravityAgent", side_effect=FakeAgent):
                with patch("services.memory.log_tier_routing", new_callable=AsyncMock) as mock_log:
                    await engine.run_autonomous_investigation(
                        goal="Débogage critique",
                        model="gemini-3.1-pro-high",
                        allow_quota_fallback=True,
                        chosen_tier=3,
                        reason="Test audit",
                        is_override=False
                    )
                    await asyncio.sleep(0.05)

                    assert len(call_agents) == 2
                    # L'agent Tier 2 de fallback DOIT impérativement avoir la clé gratuite
                    assert call_agents[1].api_key == GEMINI_API_KEY_FREE
                    assert call_agents[1].model == "gemini-3.8-flash-high"
                    # Et le log doit enregistrer le fallback 429
                    assert mock_log.call_count == 1
                    assert mock_log.call_args.kwargs["fallback_occurred"] is True
                    assert mock_log.call_args.kwargs["chosen_tier"] == 3
                    assert mock_log.call_args.kwargs["final_tier"] == 2
