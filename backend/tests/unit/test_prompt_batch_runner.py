"""backend/tests/unit/test_prompt_batch_runner.py
Tests unitaires pour l'orchestrateur de séries de prompts (PromptBatchRunner),
la persistance d'état, la reprise après crash, les callbacks signés Telegram
et la génération du rapport final avec la section exacte 'Ce que tu dois faire ensuite'.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.tools.dispatcher import dispatch_tool
from services.prompt_batch_runner import (
    BatchRunState,
    BatchSpec,
    PromptItem,
    PromptBatchRunner,
    save_batch_state,
    load_batch_state,
    build_batch_callback_data,
    parse_batch_callback_data,
    generate_batch_callback_signature,
    resume_prompt_batch,
    run_prompt_batch,
    BATCHES_DIR,
    BATCH_ACTION_RESUME,
    BATCH_ACTION_SKIP,
    BATCH_ACTION_ABORT,
    BATCH_ACTION_CLAUDE,
    BATCH_ACTION_ARGON,
    BATCH_ACTION_WAIT_5H,
    is_quota_exhausted_error,
)


@pytest.fixture(autouse=True)
def cleanup_batch_data():
    """Garantit l'isolation du dossier de données des batches."""
    os.makedirs(BATCHES_DIR, exist_ok=True)
    def _clean_test_files():
        if os.path.exists(BATCHES_DIR):
            for f in os.listdir(BATCHES_DIR):
                if f.startswith("test_") and f.endswith(".json"):
                    try:
                        os.remove(os.path.join(BATCHES_DIR, f))
                    except Exception:
                        pass
    _clean_test_files()
    yield
    _clean_test_files()


def test_batch_state_persistence():
    """Vérifie la sérialisation, la sauvegarde atomique et le rechargement de l'état d'un batch."""
    batch_id = f"test_batch_{int(time.time()*1000)}"
    state = BatchRunState(
        batch_id=batch_id,
        title="Test Série",
        status="running",
        current_prompt_index=1,
        total_prompts=3,
        attempt=2,
        branch_name="jarvis/batch-test",
        worktree_dir="/tmp/test_worktree",
        results=[{"prompt_id": "1", "status": "succeeded"}],
        manual_actions_collected=["Action manuelle 1"],
    )

    save_batch_state(state)
    loaded = load_batch_state(batch_id)

    assert loaded is not None
    assert loaded.batch_id == batch_id
    assert loaded.current_prompt_index == 1
    assert loaded.attempt == 2
    assert len(loaded.results) == 1
    assert loaded.manual_actions_collected == ["Action manuelle 1"]

    # Nettoyage
    fpath = os.path.join(BATCHES_DIR, f"{batch_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)


def test_telegram_callback_hmac_signature():
    """Vérifie la génération, la validation et le rejet des signatures altérées (< 64 octets)."""
    secret = "mon-secret-test-hmac"
    batch_id = "batch_alpha_123"

    cb_res = build_batch_callback_data(BATCH_ACTION_RESUME, batch_id, secret)
    assert len(cb_res.encode("utf-8")) <= 64
    assert cb_res.startswith("bpa:res:batch_alpha_123:")

    # Validation OK
    valid, action, bid, msg = parse_batch_callback_data(cb_res, secret)
    assert valid is True
    assert action == BATCH_ACTION_RESUME
    assert bid == batch_id

    # Altération de la signature -> Rejet
    tampered = cb_res[:-2] + "xx"
    valid_t, _, _, err_t = parse_batch_callback_data(tampered, secret)
    assert valid_t is False
    assert "compromise" in err_t or "invalide" in err_t

    # Action inconnue -> Rejet
    bad_action = f"bpa:foo:{batch_id}:123456789012"
    valid_b, _, _, _ = parse_batch_callback_data(bad_action, secret)
    assert valid_b is False


@pytest.mark.asyncio
async def test_prompt_batch_runner_success_flow():
    """Vérifie l'exécution séquentielle réussie de tous les prompts avec validation globale et PR."""
    prompts = [
        PromptItem(index=0, label="1", title="Étape 1", body="Ajout outil A", level="low"),
        PromptItem(index=1, label="2", title="Étape 2", body="Ajout outil B", level="medium"),
    ]
    batch_spec = BatchSpec(
        batch_id="test_batch_success_1",
        title="Batch Succès Complet",
        prompts=prompts,
        raw_content="...",
        all_manual_actions=["Vérifier la config DNS"],
    )

    runner = PromptBatchRunner(batch_spec)

    with patch("services.prompt_batch_runner.create_isolated_worktree", return_value="/tmp/mock_wt"), \
         patch("services.prompt_batch_runner.cleanup_isolated_worktree"), \
         patch("services.prompt_batch_runner._execute_single_prompt", new_callable=AsyncMock) as mock_exec, \
         patch("services.prompt_batch_runner._create_github_pr", new_callable=AsyncMock) as mock_pr, \
         patch("services.prompt_batch_runner.subprocess.run") as mock_subproc, \
         patch("services.prompt_batch_runner.send_email_async", new_callable=AsyncMock) as mock_email:

        # Chaque prompt réussit au 1er essai
        mock_exec.return_value = (True, "Validé", ["file1.py"], "gemini-3.7-flash")
        mock_pr.return_value = "https://github.com/Pierre38610/jarvis-core/pull/99"

        # Simuler pytest backend/tests/unit vert
        mock_proc_ok = MagicMock()
        mock_proc_ok.returncode = 0
        mock_proc_ok.stdout = "25 passed in 2.0s"
        mock_subproc.return_value = mock_proc_ok

        state = await runner.run()

        assert state.status == "completed"
        assert state.current_prompt_index == 2
        assert len(state.results) == 2
        assert state.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/99"
        assert mock_exec.call_count == 2
        assert mock_email.called


@pytest.mark.asyncio
async def test_prompt_batch_runner_retry_and_pause_on_3_failures():
    """Vérifie qu'un prompt est réessayé 3 fois avant de mettre le batch en pause et d'envoyer l'alerte."""
    prompts = [
        PromptItem(index=0, label="1", title="Étape Critique", body="Code complexe", level="high"),
    ]
    batch_spec = BatchSpec(
        batch_id="test_batch_retry_fail",
        title="Batch Retry Test",
        prompts=prompts,
        raw_content="...",
    )

    runner = PromptBatchRunner(batch_spec)

    with patch("services.prompt_batch_runner.create_isolated_worktree", return_value="/tmp/mock_wt"), \
         patch("services.prompt_batch_runner.cleanup_isolated_worktree"), \
         patch("services.prompt_batch_runner._execute_single_prompt", new_callable=AsyncMock) as mock_exec, \
         patch("services.prompt_batch_runner.send_batch_telegram_alert", new_callable=AsyncMock) as mock_tg, \
         patch("services.prompt_batch_runner.send_batch_email_alert", new_callable=AsyncMock) as mock_email:

        # Échec systématique
        mock_exec.return_value = (False, "SyntaxError on line 12", [], "gemini-3.1-pro")

        state = await runner.run()

        assert state.status == "paused"
        assert state.attempt == 3
        assert mock_exec.call_count == 3
        # Les alertes de pause doivent être appelées
        assert mock_tg.called
        assert mock_email.called


@pytest.mark.asyncio
async def test_resume_prompt_batch_skip_and_abort():
    """Vérifie le saut de prompt (skip) et l'annulation (abort) lors de la reprise."""
    batch_id = f"test_resume_{int(time.time()*1000)}"
    state = BatchRunState(
        batch_id=batch_id,
        title="Test Reprise",
        status="paused",
        current_prompt_index=0,
        total_prompts=2,
        attempt=3,
        branch_name="jarvis/batch-test",
        worktree_dir=None,
        results=[],
    )
    save_batch_state(state)

    # 1. Action SKIP
    res_skip = await resume_prompt_batch(batch_id, action=BATCH_ACTION_SKIP)
    assert res_skip is not None
    assert res_skip.current_prompt_index == 1
    assert len(res_skip.results) == 1
    assert res_skip.results[0]["status"] == "skipped"

    # 2. Action ABORT
    res_abort = await resume_prompt_batch(batch_id, action=BATCH_ACTION_ABORT)
    assert res_abort is not None
    assert res_abort.status == "stopped"

    # Nettoyage
    fpath = os.path.join(BATCHES_DIR, f"{batch_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)


@pytest.mark.asyncio
async def test_final_delivery_contains_exact_manual_actions_section():
    """Vérifie que la synthèse envoyée par email contient exactement '## Ce que tu dois faire ensuite'."""
    batch_spec = BatchSpec(
        batch_id="test_manual_sec",
        title="Test Actions Manuelles",
        prompts=[PromptItem(index=0, label="1", title="T1", body="B1")],
        raw_content="...",
        all_manual_actions=[
            "Configurer le token Cloudflare dans les secrets",
            "Vérifier la redirection HTTPS sur le domaine",
        ],
    )
    runner = PromptBatchRunner(batch_spec)
    runner.state = BatchRunState(
        batch_id=batch_spec.batch_id,
        title=batch_spec.title,
        status="completed",
        current_prompt_index=1,
        total_prompts=1,
        attempt=1,
        branch_name="jarvis/batch-test",
        worktree_dir=None,
        results=[{"label": "1", "title": "T1", "model_used": "flash", "duration_seconds": 12.0, "attempts": 1}],
        manual_actions_collected=batch_spec.all_manual_actions,
    )

    with patch("services.prompt_batch_runner.send_email_async", new_callable=AsyncMock) as mock_email:
        await runner._deliver_final_summary()
        assert mock_email.called
        call_kwargs = mock_email.call_args.kwargs
        email_body = call_kwargs.get("body", "")
        # Vérification stricte du titre de section
        assert "## Ce que tu dois faire ensuite" in email_body
        assert "Configurer le token Cloudflare" in email_body
        assert "Vérifier la redirection HTTPS" in email_body


@pytest.mark.asyncio
async def test_dispatcher_integration_prompt_batch():
    """Vérifie que dispatcher.py gère correctement self_improve avec batch_content."""
    raw_md = """
## Prompt 1: Test Dispatch
Body prompt 1.
"""
    with patch("services.prompt_batch_runner.run_prompt_batch", new_callable=AsyncMock) as mock_batch:
        mock_batch.return_value = {
            "batch_id": "batch_mock",
            "title": "Batch Mock",
            "status": "completed",
            "results": [{"prompt_id": "1"}],
            "pr_url": "https://github.com/mock/pr/1",
        }

        # Appel synchrone
        res = await dispatch_tool("self_improve", {"batch_content": raw_md, "sync": True})
        assert res["status"] == "done"
        assert "terminée avec succès" in res["user_message"]
        assert mock_batch.called


@pytest.mark.asyncio
async def test_quota_exhausted_immediate_pause_and_telegram_alert():
    """Vérifie qu'une erreur 429 / quota interrompt immédiatement sans retries inutiles et déclenche l'alerte Telegram sans e-mail."""
    prompts = [
        PromptItem(index=0, label="1", title="Étape Quota", body="Action", level="medium"),
    ]
    batch_spec = BatchSpec(
        batch_id="test_batch_quota_123",
        title="Batch Quota Test",
        prompts=prompts,
        raw_content="...",
    )
    runner = PromptBatchRunner(batch_spec)

    quota_err = 'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 5h20m.","error_code":429}'

    with patch("services.prompt_batch_runner.create_isolated_worktree", return_value="/tmp/mock_wt"), \
         patch("services.prompt_batch_runner.cleanup_isolated_worktree") as mock_cleanup, \
         patch("services.prompt_batch_runner._execute_single_prompt", new_callable=AsyncMock) as mock_exec, \
         patch("services.prompt_batch_runner.send_batch_quota_telegram_alert", new_callable=AsyncMock) as mock_tg_quota, \
         patch("services.prompt_batch_runner.send_batch_email_alert", new_callable=AsyncMock) as mock_email:

        mock_exec.return_value = (False, quota_err, [], "gemini-3.8-flash")

        state = await runner.run()

        # Pause immédiate dès la première détection
        assert state.status == "paused"
        assert state.attempt == 1
        assert mock_exec.call_count == 1
        # Alerte Telegram interactive envoyée, mais pas d'e-mail anxiogène
        assert mock_tg_quota.called
        assert not mock_email.called
        # Vérifier que la branche n'a pas été supprimée
        mock_cleanup.assert_called_once()
        _, kwargs = mock_cleanup.call_args
        assert kwargs.get("delete_branch") is False

    fpath = os.path.join(BATCHES_DIR, f"{batch_spec.batch_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)


@pytest.mark.asyncio
async def test_resume_prompt_batch_actions_and_scheduled_5h():
    """Vérifie les actions de reprise Telegram : Claude, Argon, attente 5h, et reprise normale."""
    batch_id = f"test_resume_actions_{int(time.time()*1000)}"
    state = BatchRunState(
        batch_id=batch_id,
        title="Test Actions Reprise",
        status="paused",
        current_prompt_index=2,
        total_prompts=9,
        attempt=3,
        branch_name="jarvis/batch-actions-test",
        worktree_dir=None,
        results=[
            {"label": "1A", "title": "Base", "status": "succeeded"},
            {"label": "1B", "title": "Scope", "status": "succeeded"},
        ],
    )
    save_batch_state(state)

    with patch("services.prompt_batch_runner._send_telegram_text", new_callable=AsyncMock):
        # 1. Action Claude
        st_cld = await resume_prompt_batch(batch_id, action=BATCH_ACTION_CLAUDE)
        assert st_cld.override_model == "claude-sonnet-5-5-high"
        assert st_cld.attempt == 1
        assert st_cld.status == "running"

        # 2. Action Argon
        st_arg = await resume_prompt_batch(batch_id, action=BATCH_ACTION_ARGON)
        assert st_arg.override_model == "gemini-4-argon-high"
        assert st_arg.attempt == 1

        # 3. Action Attente 5h
        st_5h = await resume_prompt_batch(batch_id, action=BATCH_ACTION_WAIT_5H)
        assert st_5h.status == "scheduled_resume"
        assert st_5h.scheduled_resume_time is not None
        assert st_5h.scheduled_resume_time > time.time() + 17000

    # Nettoyage
    fpath = os.path.join(BATCHES_DIR, f"{batch_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)


@pytest.mark.asyncio
async def test_batch_oral_status_reporting_and_explanation():
    """Vérifie que get_active_task_status et self_improve renvoient l'état exact du prompt et l'explication du patch."""
    batch_id = f"test_oral_{int(time.time()*1000)}"
    state = BatchRunState(
        batch_id=batch_id,
        title="Prompts d'implémentation - auto-amélioration",
        status="paused",
        current_prompt_index=2,  # Prompt 3 (0-indexed)
        total_prompts=9,
        attempt=1,
        branch_name="jarvis/batch-oral-test",
        worktree_dir=None,
        results=[
            {"label": "1A", "title": "Création branches et gouvernance", "status": "succeeded"},
            {"label": "1B", "title": "SubfolderScope", "status": "succeeded"},
            {"label": "2", "title": "CI et CODEOWNERS", "status": "succeeded"},
        ],
        last_error="Individual quota reached",
        current_prompt_title="[3] Outil self_improve, PR et gouvernance des crédits",
    )
    save_batch_state(state)

    from core.tools.dispatcher import dispatch_tool, _format_batch_status_tool_result
    res = _format_batch_status_tool_result(state)

    # Vérifications sur le contenu vocal et textuel
    assert "Prompt 3/9" in res.data["current_step"] or "prompt 3/9" in res.user_message.lower()
    assert "1A" in res.user_message and "1B" in res.user_message and "2" in res.user_message
    instruction = res.data.get("instruction_to_jarvis", "")
    assert "Aoede" in instruction
    assert "1A" in instruction and "1B" in instruction and "2" in instruction
    assert "auto-amélioration" in instruction.lower()

    # Test via l'appel d'outil self_improve
    tool_res = await dispatch_tool("self_improve", {
        "objectif": "en quoi consiste ce patch d'auto amélioration et à quel prompt en es-tu ?"
    })
    assert tool_res["status"] == "done"
    assert "prompt 3/9" in tool_res["user_message"].lower()

    # Nettoyage
    fpath = os.path.join(BATCHES_DIR, f"{batch_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)
