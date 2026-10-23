"""backend/tests/e2e/test_self_improvement_circuit.py
Test E2E dry-run validant l'intégralité du circuit d'auto-amélioration autonome :
1. Scénario 1 (Auto-amélioration unitaire ciblée) :
   - Simulation d'une proposition issue de `weekly_improvement_watch` ciblant `backend/services/browser_agent`
   - Résolution du sous-dossier, du contrat d'architecture et des tests unitaires ciblés (`resolve_subfolder_scope`)
   - Sélection dynamique du modèle Antigravity / effort (`resolve_live_agy_model`)
   - Streaming en direct des logs de l'agent dans `ACTIVE_AGY_LOGS`
   - Création de PR simulée, notification Telegram avec boutons signés HMAC
   - Refus de merge automatique par défaut (`check_auto_merge_policy` -> AUTO_MERGE_ENABLED=false)
   - Déploiement Blue/Green simulé dans `tmp_path` avec bascule de symlink et rollback automatique sur anomalie
2. Scénario 2 (Batch de 2 prompts via `prompt_batch_runner`) :
   - Parsing d'un fichier Markdown de 2 prompts (Prompt 1 `low`, Prompt 2 `high`)
   - Arrêt propre au Prompt 2 après 3 essais infructueux
   - Envoi de l'alerte Email + Telegram avec la section 'Ce que tu dois faire ensuite' et boutons de contrôle
   - Reprise exacte au Prompt 2 après simulation d'un clic sur 'reprendre' et achèvement réussi avec PR
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.shared_state import ACTIVE_AGY_LOGS, append_agy_log
from ops.deploy.jarvis_deployer import (
    DeployerConfig,
    DeployerEngine,
    HealthChecker,
    ServiceManager,
)
from services.model_routing.model_registry import get_registry
from services.prompt_batch_runner import (
    BATCH_ACTION_ABORT,
    BATCH_ACTION_RESUME,
    BATCH_ACTION_SKIP,
    BatchRunState,
    BatchSpec,
    PromptBatchRunner,
    PromptItem,
    build_batch_callback_data,
    load_batch_from_file,
    parse_batch_callback_data,
    parse_prompt_batch_markdown,
    resume_prompt_batch,
    save_batch_state,
)
from services.self_improvement_service import (
    SubfolderScope,
    _create_github_pr,
    _run_agy_process,
    resolve_live_agy_model,
    resolve_subfolder_scope,
    review_diff,
    run_self_improvement,
)
from services.self_improvement_telegram import (
    ACTION_APPROVE,
    ACTION_EDIT,
    ACTION_REJECT,
    ImprovementProposal,
    SelfImprovementTelegramAdapter,
    build_inline_keyboard,
    check_auto_merge_policy,
)
from services.weekly_improvement_watch import ImprovementWatchProposal


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 1 : Auto-amélioration unitaire ciblée (Veille L2 -> PR -> Blue/Green)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_scenario_1_self_improvement_targeted_subfolder_flow(tmp_path):
    """Valide de bout en bout le circuit d'auto-amélioration unitaire ciblée :
    - Veille hebdomadaire L2 -> proposition ciblant backend/services/browser_agent
    - Résolution de périmètre et contrat d'architecture
    - Sélection dynamique du modèle
    - Streaming direct dans ACTIVE_AGY_LOGS
    - PR simulée & notification Telegram avec boutons
    - Refus de merge automatique par défaut
    - Déploiement Blue/Green avec auto-rollback sur anomalie
    """
    # 1. Simulation d'une proposition issue de weekly_improvement_watch
    watch_proposal = ImprovementWatchProposal(
        proposal_id="prop_watch_e2e_001",
        title="Amélioration résilience navigation web CDP",
        target_subfolder="backend/services/browser_agent",
        recommended_complexity="medium",
        rationale="Fiabiliser la capture des sélecteurs dynamiques et timeouts sur Playwright CDP",
        ready_to_run_prompt="Optimiser la gestion du timeout et des erreurs de connexion CDP dans browser_agent/loop.py",
        targeted_tests=["backend/tests/test_browser_loop.py"],
    )

    # 2. Vérification de la résolution du sous-dossier et confinement
    scope = resolve_subfolder_scope(
        goal=watch_proposal.ready_to_run_prompt,
        target_hint=watch_proposal.target_subfolder,
    )
    assert scope.subfolder == "backend/services/browser_agent"
    assert "backend/services/browser_agent" in scope.allowed_subdirs
    assert scope.architecture_file in ("backend/ARCHITECTURE.md", "ARCHITECTURE_COMPLETE_JARVIS.md")
    assert any("test_browser_loop" in t for t in scope.targeted_test_files)

    # 3. Vérification de la sélection dynamique du modèle Antigravity
    # Vérifie que le registre dynamique est interrogé
    registry = get_registry()
    assert registry is not None
    model_low, effort_low = resolve_live_agy_model("low")
    assert effort_low == "low"
    assert "flash" in model_low.lower()

    model_med, effort_med = resolve_live_agy_model(watch_proposal.recommended_complexity)
    assert effort_med == "medium"
    assert "flash" in model_med.lower()

    model_high, effort_high = resolve_live_agy_model("high")
    assert effort_high in ("high", None)
    assert any(k in model_high.lower() for k in ("pro", "sonnet"))

    # 4. Exécution mockée offline de run_self_improvement avec capture des logs dans ACTIVE_AGY_LOGS
    mock_worktree = tmp_path / "mock_worktree"
    mock_worktree.mkdir(parents=True, exist_ok=True)
    (mock_worktree / "backend").mkdir(parents=True, exist_ok=True)

    captured_task_ids = []

    async def mock_run_agy(cmd, cwd, task_id, timeout=360.0):
        captured_task_ids.append(task_id)
        # Simulation d'événements streaming agy vers ACTIVE_AGY_LOGS
        append_agy_log(task_id, "agy: Analyse statique du code de browser_agent...", stream="stdout")
        append_agy_log(task_id, "agy: Application du patch correctif sur loop.py", stream="stdout")
        append_agy_log(task_id, "agy: Exécution des tests ciblés passée avec succès", stream="stdout")
        return 0, "agy execution completed", ""

    # Mock du client HTTP Telegram pour valider les boutons et payloads
    mock_tg_http = AsyncMock()
    mock_tg_http.post = AsyncMock(return_value=MagicMock(
        status_code=200,
        json=MagicMock(return_value={"ok": True, "result": {"message_id": 998877}})
    ))
    tg_adapter = SelfImprovementTelegramAdapter(
        bot_token="test_bot_token_12345",
        chat_id="6849746502",
        hmac_secret="secret_hmac_e2e_key",
        http_client=mock_tg_http,
    )

    with patch("services.self_improvement_service.check_quota_available", return_value=(True, "Quota OK")), \
         patch("services.self_improvement_service.is_kill_switch_active", return_value=False), \
         patch("services.self_improvement_service.create_isolated_worktree", return_value=str(mock_worktree)), \
         patch("services.self_improvement_service.cleanup_isolated_worktree"), \
         patch("services.self_improvement_service._run_agy_process", side_effect=mock_run_agy), \
         patch("services.self_improvement_service._run_local_validation_gate", return_value=(True, "Validation OK")), \
         patch("services.self_improvement_service.review_diff", return_value=(True, "Diff conforme")), \
         patch("services.self_improvement_service.subprocess.run", return_value=MagicMock(returncode=0, stdout="+ patch browser_agent")), \
         patch("services.self_improvement_service._create_github_pr", new_callable=AsyncMock) as mock_pr:

        mock_pr.return_value = "https://github.com/Pierre38610/jarvis-core/pull/77"

        res = await run_self_improvement(
            goal=watch_proposal.ready_to_run_prompt,
            target_subfolder=watch_proposal.target_subfolder,
            complexity=watch_proposal.recommended_complexity,
            create_pr=True,
            telegram_adapter=tg_adapter,
        )

        assert res.status == "success"
        assert res.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/77"
        assert res.subfolder_scope.subfolder == "backend/services/browser_agent"

        # Vérification que les logs ont bien remonté en direct dans ACTIVE_AGY_LOGS
        assert len(captured_task_ids) > 0
        task_id = captured_task_ids[0]
        assert task_id in ACTIVE_AGY_LOGS
        logs_stream = list(ACTIVE_AGY_LOGS[task_id].get("log_lines", []))
        assert any("Analyse statique du code de browser_agent" in msg for msg in logs_stream)
        assert any("Application du patch correctif" in msg for msg in logs_stream)

    # 5. Vérification de la notification Telegram et des 3 boutons signés HMAC
    assert mock_tg_http.post.called
    tg_call_args = mock_tg_http.post.call_args.kwargs
    tg_json = tg_call_args.get("json", {})
    assert tg_json.get("chat_id") == "6849746502"
    assert "Proposition d'Auto-Amélioration" in tg_json.get("text", "")
    assert "browser_agent" in tg_json.get("text", "")

    # Vérification des boutons inline
    reply_markup = tg_json.get("reply_markup", {})
    inline_kb = reply_markup.get("inline_keyboard", [[]])[0]
    button_texts = [b.get("text", "") for b in inline_kb]
    button_cbs = [b.get("callback_data", "") for b in inline_kb]
    assert any("Approuver" in t for t in button_texts)
    assert any("Rejeter" in t for t in button_texts)
    assert any("Modifier" in t for t in button_texts)
    assert any(ACTION_APPROVE in cb for cb in button_cbs)

    # 6. Vérification du refus de merge automatique par défaut
    dummy_proposal = ImprovementProposal(
        proposal_id="prop_merge_check",
        goal=watch_proposal.ready_to_run_prompt,
        subfolder="backend/services/browser_agent",
        model_used=model_med,
        diff_summary="+ def test(): pass",
        diff_line_count=20,
        pytest_results="1 test passed",
        tests_passed=True,
        branch_name="jarvis/feat-test",
        pr_url="https://github.com/Pierre38610/jarvis-core/pull/77",
        modified_files=["backend/services/browser_agent/loop.py"],
    )
    can_auto_merge, merge_reason = check_auto_merge_policy(dummy_proposal)
    assert can_auto_merge is False
    assert "désactivé par défaut" in merge_reason or "AUTO_MERGE_ENABLED=false" in merge_reason

    # 7. Déploiement Blue/Green simulé dans tmp_path avec rollback automatique sur anomalie
    deploy_root = tmp_path / "jarvis_deploy"
    workspace_dir = tmp_path / "jarvis_src"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "backend").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "backend" / "app_dummy.py").write_text("print('version 1.0')", encoding="utf-8")

    mock_cmd_runner = MagicMock(return_value=(0, "active", ""))
    deployer_cfg = DeployerConfig.from_env(
        deploy_root_override=str(deploy_root),
        workspace_override=str(workspace_dir),
        dry_run=False,
    )
    deployer_engine = DeployerEngine(
        config=deployer_cfg,
        command_runner=mock_cmd_runner,
        dry_run=False,
    )

    # Étape 7a : Première release stable (Blue)
    deployer_engine.health_checker.check_http = AsyncMock(return_value=(True, 25.0, "HTTP 200 OK"))
    deployer_engine.health_checker.check_websocket = AsyncMock(return_value=(True, "Port WS OK"))
    deployer_engine.health_checker.check_cdp = AsyncMock(return_value=(True, "CDP OK"))
    deployer_engine.health_checker.check_tool_contracts = AsyncMock(return_value=(True, "Contrats OK"))
    deployer_engine.config.monitor_duration_sec = 0.5
    deployer_engine.config.monitor_interval_sec = 0.2

    dep1 = await deployer_engine.trigger_deployment(run_sync=True)
    assert dep1["status"] == "succeeded"
    initial_release_dir = deployer_engine.release_manager.get_current_release_dir()
    assert initial_release_dir is not None

    # Étape 7b : Deuxième release avec injection d'anomalie (Green défectueuse -> HTTP 500)
    (workspace_dir / "backend" / "app_dummy.py").write_text("print('version 2.0 defective')", encoding="utf-8")
    deployer_engine.health_checker.check_http = AsyncMock(return_value=(False, 120.0, "HTTP 500 Internal Error"))

    dep2 = await deployer_engine.trigger_deployment(run_sync=True)
    assert dep2["status"] == "rolled_back"
    assert "500" in (dep2.get("rollback_reason") or "") or "Erreur" in (dep2.get("rollback_reason") or "")

    # Vérification que le symlink 'current' a été automatiquement restauré vers initial_release_dir
    current_after_rollback = deployer_engine.release_manager.get_current_release_dir()
    assert current_after_rollback == initial_release_dir


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 2 : Batch de 2 prompts via PromptBatchRunner (Pause, Alerte & Reprise)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_scenario_2_prompt_batch_runner_pause_alert_and_resume(tmp_path):
    """Valide de bout en bout l'exécution d'un batch de 2 prompts :
    - Parse un mini-fichier Markdown avec 2 prompts :
      Prompt 1 `low` : succès immédiat
      Prompt 2 `high` : échec après 3 essais
    - Pause propre au Prompt 2, émission d'alertes Telegram + Email avec boutons et section manuelle
    - Clic simulé sur le bouton 'reprendre' et achèvement réussi avec PR et synthèse finale
    """
    batches_dir = tmp_path / "prompt_batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    # 1. Création d'un mini-fichier Markdown conforme
    md_content = """# Série d'Auto-Amélioration SRE Stark

## Prompt 1: Optimisation Cache Locale (low)
LIS UNIQUEMENT :
backend/services/cache.py

ACTIONS MANUELLES :
- Vérifier la connexion Redis locale
- Contrôler l'usage RAM

Optimiser la purge mémoire et les expirations TTL dans cache.py.

## Prompt 2: Refonte Sécurisée Authentification (high)
LIS UNIQUEMENT :
backend/services/auth_service.py

ACTIONS MANUELLES :
- Rotation des clés secrètes HMAC

Renforcer la vérification cryptographique des signatures JWT et interdire les algorithmes non signés.
"""
    batch_file = tmp_path / "batch_test_sre.md"
    batch_file.write_text(md_content, encoding="utf-8")

    # 2. Parsing du markdown et validation des métadonnées extraites
    batch_spec = parse_prompt_batch_markdown(md_content, source_file=str(batch_file))
    assert batch_spec.title == "Série d'Auto-Amélioration SRE Stark"
    assert len(batch_spec.prompts) == 2

    p1 = batch_spec.prompts[0]
    assert p1.label == "1"
    assert p1.level == "low"
    assert "backend/services/cache.py" in p1.read_only_files
    assert any("Vérifier la connexion Redis" in act for act in p1.manual_actions)

    p2 = batch_spec.prompts[1]
    assert p2.label == "2"
    assert p2.level == "high"
    assert "backend/services/auth_service.py" in p2.read_only_files

    assert len(batch_spec.all_manual_actions) >= 2
    assert any("Vérifier la connexion Redis" in act for act in batch_spec.all_manual_actions)

    # 3. Exécution avec PromptBatchRunner
    mock_worktree = tmp_path / "mock_batch_wt"
    mock_worktree.mkdir(parents=True, exist_ok=True)

    # Simulation d'exécution : Prompt 1 réussit du 1er coup, Prompt 2 échoue 3 fois
    exec_call_count = {"p1": 0, "p2": 0}

    async def mock_execute_single_prompt(prompt, worktree_dir, task_id, feedback_section=""):
        if prompt.label == "1":
            exec_call_count["p1"] += 1
            return True, "Validation Prompt 1 OK", ["backend/services/cache.py"], "gemini-3.7-flash"
        elif prompt.label == "2":
            exec_call_count["p2"] += 1
            return False, "SyntaxError: invalid syntax in auth_service.py", [], "gemini-3.1-pro"
        return False, "Prompt inconnu", [], "unknown"

    telegram_secret = "test_batch_secret_key_456"

    with patch("services.prompt_batch_runner.BATCHES_DIR", str(batches_dir)), \
         patch("services.prompt_batch_runner.create_isolated_worktree", return_value=str(mock_worktree)), \
         patch("services.prompt_batch_runner.cleanup_isolated_worktree"), \
         patch("services.prompt_batch_runner._execute_single_prompt", side_effect=mock_execute_single_prompt), \
         patch("services.prompt_batch_runner.subprocess.run", return_value=MagicMock(returncode=0)), \
         patch("services.prompt_batch_runner.send_batch_telegram_alert", new_callable=AsyncMock) as mock_tg_alert, \
         patch("services.prompt_batch_runner.send_batch_email_alert", new_callable=AsyncMock) as mock_email_alert:

        runner = PromptBatchRunner(batch_spec, telegram_secret=telegram_secret)
        paused_state = await runner.run()

        # 4. Vérification de la pause propre au Prompt 2 après 3 essais
        assert paused_state.status == "paused"
        assert paused_state.current_prompt_index == 1  # 0-indexed : Prompt 2
        assert paused_state.attempt == 3
        assert exec_call_count["p1"] == 1
        assert exec_call_count["p2"] == 3
        assert len(paused_state.results) == 1  # Seul le Prompt 1 a été validé

        # 5. Vérification des alertes Telegram et Email émises
        assert mock_tg_alert.called
        assert mock_email_alert.called

        tg_call_args = mock_tg_alert.call_args.args
        assert tg_call_args[0].batch_id == batch_spec.batch_id
        assert tg_call_args[1].label == "2"
        assert "SyntaxError" in tg_call_args[2]

        email_call_args = mock_email_alert.call_args.args
        assert email_call_args[0].batch_id == batch_spec.batch_id
        assert email_call_args[1].label == "2"

        # 6. Vérification de la structure des callbacks signés HMAC (Reprendre / Ignorer / Annuler)
        cb_res = build_batch_callback_data(BATCH_ACTION_RESUME, batch_spec.batch_id, telegram_secret)
        cb_skp = build_batch_callback_data(BATCH_ACTION_SKIP, batch_spec.batch_id, telegram_secret)
        cb_abt = build_batch_callback_data(BATCH_ACTION_ABORT, batch_spec.batch_id, telegram_secret)

        assert len(cb_res.encode("utf-8")) <= 64
        assert len(cb_skp.encode("utf-8")) <= 64
        assert len(cb_abt.encode("utf-8")) <= 64

        valid_res, act_res, b_id_res, _ = parse_batch_callback_data(cb_res, telegram_secret)
        assert valid_res is True
        assert act_res == BATCH_ACTION_RESUME
        assert b_id_res == batch_spec.batch_id

        # 7. Simulation du clic sur 'Reprendre' après correction
        # Le Prompt 2 réussit désormais au premier essai de reprise
        async def mock_execute_resumed(prompt, worktree_dir, task_id, feedback_section=""):
            if prompt.label == "2":
                return True, "Correction validée", ["backend/services/auth_service.py"], "gemini-3.1-pro"
            return True, "OK", [], "gemini-3.7-flash"

        with patch("services.prompt_batch_runner._execute_single_prompt", side_effect=mock_execute_resumed), \
             patch("services.prompt_batch_runner._create_github_pr", new_callable=AsyncMock) as mock_pr_batch, \
             patch("services.prompt_batch_runner.send_email_async", new_callable=AsyncMock) as mock_final_email:

            mock_pr_batch.return_value = "https://github.com/Pierre38610/jarvis-core/pull/88"

            resumed_state = await resume_prompt_batch(batch_spec.batch_id, action=BATCH_ACTION_RESUME)

            # 8. Vérification de l'achèvement complet du batch
            assert resumed_state is not None
            assert resumed_state.status == "completed"
            assert resumed_state.current_prompt_index == 2
            assert len(resumed_state.results) == 2
            assert resumed_state.results[0]["status"] == "succeeded"
            assert resumed_state.results[1]["status"] == "succeeded"
            assert resumed_state.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/88"

            # Vérification de l'e-mail de synthèse finale avec la section obligatoire
            assert mock_final_email.called
            final_email_body = mock_final_email.call_args.kwargs.get("body", "")
            assert "## Ce que tu dois faire ensuite" in final_email_body
            assert "Vérifier la connexion Redis locale" in final_email_body
            assert "Rotation des clés secrètes HMAC" in final_email_body
            assert "https://github.com/Pierre38610/jarvis-core/pull/88" in final_email_body
