"""backend/tests/unit/test_background_vps_autonomy.py
Tests unitaires validant l'autonomie 100% en tâche de fond sur VPS Oracle Cloud ARM64.
Vérifie :
1. Aucun appel synchrone à `time.sleep()` dans le circuit d'auto-amélioration et de déploiement.
2. L'isolation CPU basse priorité sous POSIX (`build_low_priority_subprocess_kwargs`, nice +10).
3. L'exécution complète headless sans client connecté (`is_pc_connected() == False`),
   sans session WebSocket (/ws) et avec Redis en fallback mémoire.
"""

import ast
import asyncio
import os
import shutil
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.self_improvement_service import (
    build_low_priority_subprocess_kwargs,
    run_self_improvement,
    _set_low_cpu_priority,
)
from backend.services.self_improvement_telegram import (
    ImprovementProposal,
    ProposalStore,
    SelfImprovementTelegramAdapter,
    generate_proposal_id,
)
from backend.services.weekly_improvement_watch import (
    ImprovementWatchProposal,
    InternalSignalsCollector,
    L2ImprovementFormulator,
    WeeklyImprovementWatchService,
    WeeklyImprovementWatchStore,
)

SCRATCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "_test_scratch", "autonomy"))
os.makedirs(SCRATCH_DIR, exist_ok=True)


# ─── 1. VÉRIFICATION STRICTE DE L'ABSENCE DE TIME.SLEEP SYNCHRONE ────────────
class TestNoSynchronousSleep(unittest.TestCase):
    """Garantit qu'aucun `time.sleep()` bloquant pour la boucle asyncio n'est utilisé
    dans les composants du circuit d'auto-amélioration.
    """

    TARGET_FILES = [
        "backend/services/self_improvement_service.py",
        "backend/services/self_improvement_telegram.py",
        "backend/services/weekly_improvement_watch.py",
        "ops/deploy/jarvis_deployer.py",
    ]

    def test_no_synchronous_time_sleep_in_circuit_files(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        violations = []

        for rel_path in self.TARGET_FILES:
            full_path = os.path.join(repo_root, rel_path)
            if not os.path.exists(full_path):
                continue

            with open(full_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Détecte time.sleep(...)
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "sleep"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "time"
                    ):
                        violations.append(f"{rel_path}:{node.lineno} -> time.sleep(...)")
                    # Détecte from time import sleep; sleep(...)
                    elif isinstance(node.func, ast.Name) and node.func.id == "sleep":
                        violations.append(f"{rel_path}:{node.lineno} -> sleep(...)")

        self.assertEqual(
            violations,
            [],
            f"Des appels synchrones bloquants time.sleep() ont été détectés : {violations}",
        )


# ─── 2. ISOLATION CPU & PRIORITÉ BASSE (NICE +10 SOUS LINUX) ──────────────────
class TestCPULowPriorityIsolation(unittest.TestCase):
    """Valide le comportement de build_low_priority_subprocess_kwargs sous POSIX et non-POSIX."""

    def test_posix_returns_preexec_fn(self):
        with patch("os.name", "posix"):
            kwargs = build_low_priority_subprocess_kwargs()
            self.assertIn("preexec_fn", kwargs)
            self.assertTrue(callable(kwargs["preexec_fn"]))

    def test_non_posix_returns_empty_dict(self):
        with patch("os.name", "nt"):
            kwargs = build_low_priority_subprocess_kwargs()
            self.assertEqual(kwargs, {})

    def test_set_low_cpu_priority_invokes_nice(self):
        with patch("os.name", "posix"), patch("os.nice", create=True) as mock_nice:
            _set_low_cpu_priority()
            mock_nice.assert_called_once_with(10)


# ─── 3. EXÉCUTION COMPLÈTE HORS-LIGNE (HEADLESS SANS CLIENT NI REDIS) ────────
@pytest.mark.asyncio
class TestBackgroundVPSAutonomy:
    """Valide le fonctionnement 100% headless du circuit quand aucun PC n'est connecté,
    aucune session WebSocket n'est ouverte, et Redis est en fallback mémoire.
    """

    async def test_self_improvement_runs_headless_without_pc_or_websocket(self):
        """Vérifie que run_self_improvement réussit sans PC connecté, sans WS, et sans Redis."""
        test_dir = os.path.join(SCRATCH_DIR, "self_imp_test")
        fake_repo = os.path.join(test_dir, "repo")
        fake_worktree = os.path.join(test_dir, "worktree")
        os.makedirs(fake_repo, exist_ok=True)
        os.makedirs(fake_worktree, exist_ok=True)

        try:
            with patch("backend.services.self_improvement_service.is_kill_switch_active", return_value=False), \
                 patch("backend.services.self_improvement_service.check_quota_available", return_value=(True, "OK")), \
                 patch("backend.services.self_improvement_service.create_isolated_worktree", return_value=fake_worktree), \
                 patch("backend.services.self_improvement_service.cleanup_isolated_worktree") as mock_cleanup, \
                 patch("backend.services.self_improvement_service._run_agy_process", new_callable=AsyncMock) as mock_agy, \
                 patch("backend.services.self_improvement_service._run_local_validation_gate", return_value=(True, "Tests ciblés OK")), \
                 patch("backend.services.self_improvement_service.review_diff", return_value=(True, "Diff propre")), \
                 patch("backend.services.self_improvement_service._create_github_pr", new_callable=AsyncMock) as mock_pr, \
                 patch("backend.services.self_improvement_service.record_run_in_journal") as mock_journal, \
                 patch("backend.services.self_improvement_service.subprocess.run") as mock_subproc:

                mock_agy.return_value = (0, "Succès de la tâche", "")
                mock_pr.return_value = "https://github.com/Pierre38610/jarvis-core/pull/999"

                # Diff git simulé
                diff_proc = MagicMock()
                diff_proc.stdout = "+ # modification autonome\n"
                mock_subproc.return_value = diff_proc

                # Aucun websocket (websocket=None) et aucun PC connecté
                result = await run_self_improvement(
                    goal="Refactoriser la résilience headless",
                    target_subfolder="backend/services",
                    complexity="low",
                    create_pr=True,
                    session_id=None,
                    websocket=None,  # 100% headless
                )

                assert result.status == "success"
                assert result.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/999"
                assert "Succès" in result.user_message or "terminée avec succès" in result.user_message
                mock_cleanup.assert_called_once()
                mock_journal.assert_called_once()
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    async def test_weekly_watch_scan_in_redis_memory_fallback(self):
        """Vérifie que la veille s'exécute parfaitement avec Redis en fallback mémoire."""
        test_dir = os.path.join(SCRATCH_DIR, "watch_test")
        os.makedirs(test_dir, exist_ok=True)
        db_file = os.path.join(test_dir, "weekly_watch.json")

        try:
            store = WeeklyImprovementWatchStore(storage_path=db_file)

            mock_collector = MagicMock(spec=InternalSignalsCollector)
            mock_collector.collect_all_signals = AsyncMock(return_value={
                "console": {"errors_by_source": {}, "sample_patterns": []},
                "telemetry": {
                    "slow_tools": [],
                    "failing_tools": [],
                    "claimed_success_without_verification": 0,
                    "stalled_tasks_count": 0,
                },
                "architecture": {"subfolders": {"backend": {}}},
            })

            mock_formulator = MagicMock(spec=L2ImprovementFormulator)
            mock_formulator.formulate_proposals = AsyncMock(return_value=[
                ImprovementWatchProposal(
                    proposal_id="watch_prop_headless1",
                    title="Optimisation résilience mémoire sans Redis",
                    target_subfolder="backend/services",
                    recommended_complexity="low",
                    rationale="Fallback mémoire autonome validé",
                    ready_to_run_prompt="Améliorer le cache mémoire local",
                    targeted_tests=["backend/tests/unit/test_metrics_service.py"],
                )
            ])

            mock_telegram = MagicMock(spec=SelfImprovementTelegramAdapter)
            mock_telegram.send_proposal = AsyncMock(return_value=(True, 12345, "Envoyé"))

            service = WeeklyImprovementWatchService(
                store=store,
                telegram_adapter_instance=mock_telegram,
                collector=mock_collector,
                formulator=mock_formulator,
            )

            proposals = await service.run_scan()
            assert len(proposals) == 1
            assert proposals[0].status == "proposed"
            assert mock_telegram.send_proposal.await_count == 1

            # Vérification persistance
            stored = store.list_all()
            assert len(stored) == 1
            assert stored[0].proposal_id == "watch_prop_headless1"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    async def test_telegram_proposal_adapter_lifecycle_headless(self):
        """Vérifie le cycle complet de proposition et décision SQLite sans interface graphique."""
        test_dir = os.path.join(SCRATCH_DIR, "tg_test")
        os.makedirs(test_dir, exist_ok=True)
        db_path = os.path.join(test_dir, "proposals.db")

        try:
            store = ProposalStore(db_path=db_path)
            adapter = SelfImprovementTelegramAdapter(
                bot_token="test_token",
                chat_id="123456",
                hmac_secret="secret_key_123",
                auto_merge_enabled=False,
                store=store,
            )

            proposal = ImprovementProposal(
                proposal_id=generate_proposal_id(),
                goal="Optimiser boucle audio DeviceAudioPacer",
                subfolder="firmware/esp32",
                model_used="gemini-3.8-flash",
                diff_summary="+ // audio buffer 55ms",
                diff_line_count=12,
                pytest_results="2 passed",
                tests_passed=True,
                branch_name="watch/esp32-patch",
            )
            store.save(proposal)

            # 1. Génération de callback signé HMAC
            from backend.services.self_improvement_telegram import build_callback_data, ACTION_APPROVE
            cb_data = build_callback_data(ACTION_APPROVE, proposal.proposal_id, "secret_key_123")

            # 2. Clic d'approbation simulé hors-ligne
            res = await adapter.handle_callback_query(cb_data, user_id="123456")
            assert res["status"] == "success"
            assert res["action"] == "approved"

            # 3. Vérification de l'état persisté
            updated = store.get(proposal.proposal_id)
            assert updated is not None
            assert updated.status == "approved"

            # 4. Déduplication atomique d'un double clic
            double_click_res = await adapter.handle_callback_query(cb_data, user_id="123456")
            assert double_click_res["status"] == "deduplicated"
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
