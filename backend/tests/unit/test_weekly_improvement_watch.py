"""backend/tests/unit/test_weekly_improvement_watch.py
Tests unitaires pour le moteur de veille d'auto-améliorations J.A.R.V.I.S. (weekly_improvement_watch.py).
"""

import asyncio
import json
import os
import shutil
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agentic_runner import (
    AgentOutput,
    CrossCheckResult,
    L2ExecutionResult,
)
from services.console_monitor import console_monitor
from services.metrics_service import metrics_service
from services.self_improvement_telegram import ImprovementProposal
from services.weekly_improvement_watch import (
    ImprovementWatchProposal,
    InternalSignalsCollector,
    L2ImprovementFormulator,
    WeeklyImprovementWatchScheduler,
    WeeklyImprovementWatchService,
    WeeklyImprovementWatchStore,
    validate_technical_proposal,
    generate_and_send_technical_improvements,
)

TEST_SCRATCH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_test_scratch"))
os.makedirs(TEST_SCRATCH, exist_ok=True)


@pytest.fixture(autouse=True)
def clean_state():
    """Nettoie l'état avant et après chaque test."""
    console_monitor.clear()
    yield
    console_monitor.clear()


# ─── Tests du Modèle et Dataclass ───────────────────────────────────────────
def test_improvement_watch_proposal_model():
    prop = ImprovementWatchProposal(
        proposal_id="watch_prop_123",
        title="Optimiser vector_memory cache",
        target_subfolder="backend/services",
        recommended_complexity="low",
        rationale="Latence p95 de 1500ms observée",
        ready_to_run_prompt="Refactoriser le cache LRU dans backend/services/memory.py",
        targeted_tests=["backend/tests/unit/test_memory.py"],
    )

    assert prop.proposal_id == "watch_prop_123"
    assert prop.fingerprint != ""
    assert prop.status == "proposed"

    d = prop.to_dict()
    assert d["title"] == "Optimiser vector_memory cache"
    assert d["targeted_tests"] == ["backend/tests/unit/test_memory.py"]

    rebuilt = ImprovementWatchProposal.from_dict(d)
    assert rebuilt.proposal_id == prop.proposal_id
    assert rebuilt.fingerprint == prop.fingerprint

    # Conversion vers format Telegram
    tg_prop = prop.to_telegram_proposal()
    assert isinstance(tg_prop, ImprovementProposal)
    assert tg_prop.proposal_id == prop.proposal_id
    assert tg_prop.subfolder == "backend/services"
    assert "Rationale" in tg_prop.diff_summary
    assert "Prompt prêt" in tg_prop.diff_summary


def test_fingerprint_deterministic():
    fp1 = ImprovementWatchProposal.compute_fingerprint("backend/services", "Optimisation Cache")
    fp2 = ImprovementWatchProposal.compute_fingerprint("backend/services ", "optimisation cache")
    assert fp1 == fp2


# ─── Tests du Store et Déduplication ────────────────────────────────────────
def test_watch_store_save_and_deduplicate():
    storage_file = os.path.join(TEST_SCRATCH, f"test_proposals_{int(time.time()*1000)}.json")
    try:
        store = WeeklyImprovementWatchStore(storage_path=storage_file)

        prop = ImprovementWatchProposal(
            proposal_id="p1",
            title="Fix Timeout",
            target_subfolder="backend/tools",
            recommended_complexity="low",
            rationale="Timeout logs",
            ready_to_run_prompt="Fix timeout in tools",
            targeted_tests=["backend/tests/unit/test_tools.py"],
        )

        store.save(prop)
        assert store.get("p1") is not None
        assert len(store.list_all()) == 1
        assert len(store.list_active()) == 1

        # Déduplication
        assert store.is_duplicate(prop.fingerprint, cooldown_days=7.0) is True
        assert store.is_duplicate("other_fingerprint", cooldown_days=7.0) is False

        # Rechargement depuis le fichier
        store2 = WeeklyImprovementWatchStore(storage_path=storage_file)
        assert store2.get("p1") is not None
        assert store2.get("p1").title == "Fix Timeout"
    finally:
        if os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except Exception:
                pass


# ─── Tests du Collecteur de Signaux Internes ─────────────────────────────────
@pytest.mark.asyncio
async def test_internal_signals_collector():
    collector = InternalSignalsCollector()

    # 1. Signaux Console
    console_monitor.record_error(source="browser_agent", message="Timeout navigation", level="ERROR")
    console_monitor.record_error(source="browser_agent", message="Element not found", level="WARNING")
    console_monitor.record_error(source="auth_service", message="Invalid token", level="ERROR")

    sig_console = collector.collect_console_signals()
    assert sig_console["total_recent_errors"] >= 3
    assert sig_console["errors_by_source"].get("browser_agent") == 2

    # 2. Signaux Télémétrie
    metrics_service.record_to_memory(
        tool_name="slow_search_tool",
        status="success",
        latency_ms=2500.0,
    )
    metrics_service.record_to_memory(
        tool_name="failing_fetch_tool",
        status="failure",
        latency_ms=300.0,
    )
    metrics_service.record_claimed_success_without_verification("unverified_tool")

    sig_telemetry = await collector.collect_telemetry_signals()
    assert sig_telemetry["claimed_success_without_verification"] >= 1
    assert any(t["tool_name"] == "slow_search_tool" for t in sig_telemetry["slow_tools"])
    assert any(t["tool_name"] == "failing_fetch_tool" for t in sig_telemetry["failing_tools"])

    # 3. Contrats d'architecture
    sig_arch = collector.collect_architecture_contracts()
    assert "backend" in sig_arch["subfolders"]
    assert "frontend" in sig_arch["subfolders"]

    # 4. Agrégation globale
    all_sig = await collector.collect_all_signals()
    assert "console" in all_sig
    assert "telemetry" in all_sig
    assert "architecture" in all_sig


# ─── Tests du Formulateur L2 Parallèle ───────────────────────────────────────
@pytest.mark.asyncio
async def test_l2_formulator_fallback():
    formulator = L2ImprovementFormulator()

    signals = {
        "console": {
            "total_recent_errors": 5,
            "errors_by_source": {"browser_agent": 4, "server": 1},
            "sample_patterns": ["[browser_agent] Timeout navigation"],
        },
        "telemetry": {
            "slow_tools": [{"tool_name": "heavy_search", "p95_latency_ms": 2400.0, "failures": 0}],
            "failing_tools": [{"tool_name": "db_sync", "failure_rate": 0.2, "failures": 3}],
            "claimed_success_without_verification": 2,
        },
        "architecture": {
            "subfolders": {"backend": {}, "frontend": {}},
        },
    }

    # Simulation sans LLM (repli déterministe)
    proposals = formulator._generate_rule_based_fallback(signals)
    assert 1 <= len(proposals) <= 3
    assert any("db_sync" in p.title or "db_sync" in p.rationale for p in proposals)
    assert any(p.recommended_complexity in ("low", "medium", "high") for p in proposals)
    assert all(len(p.ready_to_run_prompt) > 20 for p in proposals)


@pytest.mark.asyncio
async def test_l2_formulator_with_mocked_runner():
    formulator = L2ImprovementFormulator()

    mock_json = json.dumps([
        {
            "title": "Optimisation du cache de recherche",
            "target_subfolder": "backend/services",
            "recommended_complexity": "low",
            "rationale": "Latence p95 observée à 3100ms",
            "ready_to_run_prompt": "Ajouter un cache LRU sur le service de recherche",
            "targeted_tests": ["backend/tests/unit/test_search.py"],
        },
        {
            "title": "Fiabilisation des callbacks Telegram",
            "target_subfolder": "backend/services",
            "recommended_complexity": "medium",
            "rationale": "Erreurs réseau intermittentes",
            "ready_to_run_prompt": "Ajouter un retry avec backoff exponentiel dans self_improvement_telegram.py",
            "targeted_tests": ["backend/tests/unit/test_self_improvement_telegram.py"],
        }
    ])

    mock_agent_output = AgentOutput(
        conclusion=f"Voici les propositions retenues :\n```json\n{mock_json}\n```",
        confidence=0.95,
        status="success",
        worker_id="proposal_synthesizer",
    )

    mock_exec_result = L2ExecutionResult(
        status="completed",
        quality_gate_passed=True,
        successful_agents=[mock_agent_output],
        synthesis=mock_agent_output,
        cross_check=CrossCheckResult(passed=True, agreement_score=1.0),
    )

    with patch("services.weekly_improvement_watch.run_l2_parallel_agents", new=AsyncMock(return_value=mock_exec_result)):
        proposals = await formulator.formulate_proposals(signals={})
        assert len(proposals) == 2
        assert proposals[0].title == "Optimisation du cache de recherche"
        assert proposals[0].target_subfolder == "backend/services"
        assert proposals[0].recommended_complexity == "low"
        assert proposals[1].title == "Fiabilisation des callbacks Telegram"


# ─── Tests du Service Central et Workflow 1-Clic ────────────────────────────
@pytest.mark.asyncio
async def test_weekly_improvement_watch_service_scan_and_dispatch():
    storage_file = os.path.join(TEST_SCRATCH, f"watch_service_{int(time.time()*1000)}.json")
    try:
        store = WeeklyImprovementWatchStore(storage_path=storage_file)

        mock_telegram = MagicMock()
        mock_telegram.send_proposal = AsyncMock(return_value=(True, 42, "OK"))

        mock_formulator = MagicMock()
        sample_prop = ImprovementWatchProposal(
            proposal_id="prop_sample_1",
            title="Optimisation Cache",
            target_subfolder="backend/services",
            recommended_complexity="low",
            rationale="Latence p95 élevée",
            ready_to_run_prompt="Optimiser cache",
            targeted_tests=["backend/tests/unit/test_cache.py"],
        )
        mock_formulator.formulate_proposals = AsyncMock(return_value=[sample_prop])

        service = WeeklyImprovementWatchService(
            store=store,
            telegram_adapter_instance=mock_telegram,
            formulator=mock_formulator,
        )

        # Lancement d'un cycle complet de scan
        proposals = await service.run_scan()

        assert len(proposals) == 1
        assert mock_telegram.send_proposal.call_count == 1

        # Vérification de la persistance
        stored = store.list_all()
        assert len(stored) == 1

        # Deuxième scan immédiat : les propositions doivent être dédupliquées
        mock_telegram.send_proposal.reset_mock()
        proposals_second_run = await service.run_scan()
        assert len(proposals_second_run) == 0
        assert mock_telegram.send_proposal.call_count == 0
    finally:
        if os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_weekly_improvement_watch_one_click_approval():
    storage_file = os.path.join(TEST_SCRATCH, f"approval_{int(time.time()*1000)}.json")
    try:
        store = WeeklyImprovementWatchStore(storage_path=storage_file)

        mock_runner = AsyncMock()
        mock_telegram = MagicMock()

        service = WeeklyImprovementWatchService(
            store=store,
            telegram_adapter_instance=mock_telegram,
            self_improve_runner=mock_runner,
        )

        prop = ImprovementWatchProposal(
            proposal_id="watch_prop_approved",
            title="Renforcer browser_agent",
            target_subfolder="backend/services/browser_agent",
            recommended_complexity="medium",
            rationale="Timeouts répétés",
            ready_to_run_prompt="Améliorer la résilience du browser_agent",
            targeted_tests=["backend/tests/unit/test_browser_agent.py"],
        )
        store.save(prop)

        # Pierre clique sur ✅ Approuver dans Telegram
        tg_prop = prop.to_telegram_proposal()
        await service.on_telegram_proposal_approved(tg_prop)

        # Laisser le temps à la tâche en arrière-plan de s'exécuter
        await asyncio.sleep(0.05)

        assert mock_runner.call_count == 1
        call_kwargs = mock_runner.call_args[1]
        assert call_kwargs["target_subfolder"] == "backend/services/browser_agent"
        assert call_kwargs["goal"] == "Améliorer la résilience du browser_agent"
        assert call_kwargs["complexity"] == "medium"
        assert call_kwargs["create_pr"] is True

        # Vérifier la mise à jour du statut dans le store
        updated = store.get("watch_prop_approved")
        assert updated.status in ("approved", "running", "completed")
    finally:
        if os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except Exception:
                pass


# ─── Tests du Cycle de Vie du Scheduler ─────────────────────────────────────
@pytest.mark.asyncio
async def test_scheduler_lifecycle():
    storage_file = os.path.join(TEST_SCRATCH, f"scheduler_{int(time.time()*1000)}.json")
    try:
        store = WeeklyImprovementWatchStore(storage_path=storage_file)

        mock_telegram = MagicMock()
        mock_telegram.send_proposal = AsyncMock(return_value=(True, 10, "OK"))

        mock_formulator = MagicMock()
        mock_formulator.formulate_proposals = AsyncMock(return_value=[])

        service = WeeklyImprovementWatchService(
            store=store,
            telegram_adapter_instance=mock_telegram,
            formulator=mock_formulator,
            interval_seconds=0.1,
        )

        assert not service.is_running
        started = service.start()
        assert started is True
        assert service.is_running is True

        # Démarrage idempotent (ne doit pas relancer une seconde tâche)
        assert service.start() is False

        # Laisser la boucle faire un scan
        await asyncio.sleep(0.05)

        stopped = service.stop()
        assert stopped is True
        assert service.is_running is False
        assert service.stop() is False
    finally:
        if os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except Exception:
                pass


# ─── Tests Anti-Coaching & Pipeline Complet generate_and_send_technical_improvements ─
def test_rejects_personal_lifestyle_proposals_and_already_implemented_tools():
    """Vérifie qu'une proposition 'Faire plus de sport' ou un outil déjà dans CAPABILITIES_LEDGER.md est rejetée."""
    # 1. Proposition de coaching sportif / lifestyle -> rejet immédiat
    sport_prop = ImprovementWatchProposal(
        proposal_id="bad_sport_1",
        title="Faire plus de sport et boire de l'eau",
        target_subfolder="backend/services",
        recommended_complexity="low",
        rationale="Faire une séance de sport quotidienne améliore la santé.",
        ready_to_run_prompt="Rappeler à Pierre de faire du sport.",
        targeted_tests=[],
    )
    ok_sport, reason_sport = validate_technical_proposal(sport_prop)
    assert ok_sport is False
    assert "anti-coaching" in reason_sport.lower() or "sport" in reason_sport.lower()

    # 2. Proposition recréant un outil déjà implémenté dans CAPABILITIES_LEDGER.md -> rejet immédiat
    dup_tool_prop = ImprovementWatchProposal(
        proposal_id="bad_dup_tool",
        title="Créer l'outil control_spotify pour écouter de la musique",
        target_subfolder="backend/core/tools",
        recommended_complexity="medium",
        rationale="Permettre à Jarvis de contrôler Spotify.",
        ready_to_run_prompt="Créer control_spotify dans declarations.py",
        targeted_tests=["backend/tests/unit/test_spotify.py"],
    )
    ok_dup, reason_dup = validate_technical_proposal(dup_tool_prop)
    assert ok_dup is False
    assert "control_spotify" in reason_dup or "déjà implémenté" in reason_dup.lower()

    # 3. Proposition technique valide sur le code de Jarvis -> acceptée
    valid_tech_prop = ImprovementWatchProposal(
        proposal_id="good_tech_1",
        title="Ajout d'un disjoncteur adaptatif sur les appels HTTP de browser_agent",
        target_subfolder="backend/services/browser_agent",
        recommended_complexity="medium",
        rationale="Réduit les timeouts lors des pics de latence CDP.",
        ready_to_run_prompt="Implémenter un circuit-breaker asynchrone dans backend/services/browser_agent/runner.py",
        targeted_tests=["backend/tests/unit/test_antigravity_task_engine.py"],
    )
    ok_valid, _ = validate_technical_proposal(valid_tech_prop)
    assert ok_valid is True


@pytest.mark.asyncio
async def test_generate_and_send_technical_improvements_end_to_end():
    """Vérifie l'exécution de bout en bout de generate_and_send_technical_improvements et l'envoi Telegram."""
    storage_file = os.path.join(TEST_SCRATCH, f"gen_tech_{int(time.time()*1000)}.json")
    try:
        store = WeeklyImprovementWatchStore(storage_path=storage_file)
        mock_telegram = MagicMock()
        mock_telegram.send_proposal = AsyncMock(return_value=(True, 777, "OK"))

        # Le formulateur retourne 1 proposition lifestyle (qui doit être filtrée) et 2 vraies propositions techniques
        bad_prop = ImprovementWatchProposal(
            proposal_id="p_bad_sport",
            title="Programme de méditation et sommeil",
            target_subfolder="backend/services",
            recommended_complexity="low",
            rationale="Mieux dormir",
            ready_to_run_prompt="Coaching sommeil",
        )
        good_prop_1 = ImprovementWatchProposal(
            proposal_id="p_good_1",
            title="Cache sémantique Redis sur les requêtes search_web répétées",
            target_subfolder="backend/services",
            recommended_complexity="medium",
            rationale="Réduction de 80% de la latence sur les requêtes identiques",
            ready_to_run_prompt="Ajouter un cache TTL 30m dans backend/services/web_search.py",
            targeted_tests=["backend/tests/unit/test_web_search.py"],
        )
        good_prop_2 = ImprovementWatchProposal(
            proposal_id="p_good_2",
            title="Support du reply Telegram pour modifier un prompt d'auto-amélioration",
            target_subfolder="backend/services",
            recommended_complexity="medium",
            rationale="Permet d'éditer un prompt directement en répondant au message Telegram",
            ready_to_run_prompt="Étendre fetch_telegram_updates_sync dans self_improvement_telegram.py",
            targeted_tests=["backend/tests/unit/test_self_improvement_telegram.py"],
        )

        mock_formulator = MagicMock()
        mock_formulator.formulate_proposals = AsyncMock(return_value=[bad_prop, good_prop_1, good_prop_2])

        service = WeeklyImprovementWatchService(
            store=store,
            telegram_adapter_instance=mock_telegram,
            formulator=mock_formulator,
        )

        res = await generate_and_send_technical_improvements(
            focus_area="backend/services",
            count=2,
            trigger_source="manual",
            service_instance=service,
        )

        assert res["status"] == "ok"
        assert res["count"] == 2
        assert res["sent_count"] == 2
        assert res["sent_message_ids"] == [777, 777]
        assert len(res["rejected_proposals"]) == 1
        assert "méditation" in res["rejected_proposals"][0]["title"]
        assert mock_telegram.send_proposal.call_count == 2
    finally:
        if os.path.exists(storage_file):
            try:
                os.remove(storage_file)
            except Exception:
                pass
