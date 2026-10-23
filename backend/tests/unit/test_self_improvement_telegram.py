"""backend/tests/unit/test_self_improvement_telegram.py
Tests unitaires pour l'adaptateur Telegram interactif d'auto-amélioration et de PRs.
Vérifie :
1. Les signatures HMAC des callbacks et la limitation stricte à 64 octets.
2. La persistance SQLite, la reprise d'état après redémarrage et la déduplication atomique des doubles clics.
3. La politique de merge sécurisée (AUTO_MERGE_ENABLED désactivé par défaut, seuil < 150 lignes,
   tests unitaires verts, protection des fichiers critiques, revue second modèle).
4. Le formateur HTML Telegram et la construction des boutons inline.
5. Le traitement complet des callbacks (approuver, rejeter, modifier) et l'injection dans run_self_improvement.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from services.self_improvement_telegram import (
    ACTION_APPROVE,
    ACTION_EDIT,
    ACTION_REJECT,
    STATE_APPROVED,
    STATE_EDIT_REQUESTED,
    STATE_FAILED,
    STATE_MERGED,
    STATE_MERGING,
    STATE_PROPOSED,
    STATE_REJECTED,
    ImprovementProposal,
    ProposalStore,
    SelfImprovementTelegramAdapter,
    build_callback_data,
    build_inline_keyboard,
    evaluate_merge_policy,
    format_telegram_report,
    generate_callback_signature,
    generate_proposal_id,
    parse_callback_data,
    verify_callback_signature,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def temp_db_path():
    """Fournit un chemin de base SQLite temporaire isolé dans le workspace."""
    import uuid
    repo_root = getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    data_dir = os.path.join(repo_root, "data", "test_runs")
    os.makedirs(data_dir, exist_ok=True)
    db_file = os.path.join(data_dir, f"test_prop_{uuid.uuid4().hex[:8]}.db")
    yield db_file
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass
    if os.path.exists(data_dir) and not os.listdir(data_dir):
        try:
            os.rmdir(data_dir)
        except Exception:
            pass


@pytest.fixture
def isolated_store(temp_db_path):
    """Fournit une instance isolée de ProposalStore sur fichier temporaire."""
    return ProposalStore(db_path=temp_db_path)


@pytest.fixture
def sample_proposal():
    """Génère une proposition type pour les tests."""
    return ImprovementProposal(
        proposal_id="prop_test_123456",
        goal="Corriger une fuite mémoire dans le dispatcher",
        subfolder="backend/core/tools",
        model_used="gemini-3.8-flash",
        diff_summary="--- a/dispatcher.py\n+++ b/dispatcher.py\n@@ -1,2 +1,3 @@\n+cache.clear()\n",
        diff_line_count=12,
        pytest_results="3 tests ciblés passés avec succès",
        tests_passed=True,
        branch_name="jarvis/fix-dispatcher-1234",
        modified_files=["backend/core/tools/dispatcher.py"],
        pr_url="https://github.com/Pierre38610/jarvis-core/pull/77",
        status=STATE_PROPOSED,
        second_model_reviewed=True,
        second_model_name="claude-3-7-sonnet",
    )


# ─── 1. Signatures HMAC & Callbacks Compacts (< 64 octets) ───────────────────
def test_hmac_signatures_and_length():
    """Vérifie la validité des signatures HMAC et la contrainte de taille Telegram."""
    secret = "mon-secret-hmac-test-123"
    prop_id = generate_proposal_id()
    assert prop_id.startswith("prop_")
    assert len(prop_id) >= 10

    # Signature pour chaque action
    for act in (ACTION_APPROVE, ACTION_REJECT, ACTION_EDIT):
        sig = generate_callback_signature(act, prop_id, secret)
        assert len(sig) == 12
        assert verify_callback_signature(act, prop_id, sig, secret) is True

        # Rejet en cas de secret ou action erronée
        assert verify_callback_signature(act, prop_id, sig, "autre-secret") is False
        assert verify_callback_signature("autre_action", prop_id, sig, secret) is False

        # Vérification callback_data <= 64 octets
        cb_data = build_callback_data(act, prop_id, secret)
        assert len(cb_data.encode("utf-8")) <= 64
        assert cb_data.startswith(f"si:{act}:{prop_id}:")

        # Parsing réussi
        valid, parsed_act, parsed_id, msg = parse_callback_data(cb_data, secret)
        assert valid is True
        assert parsed_act == act
        assert parsed_id == prop_id
        assert msg == "OK"


def test_parse_callback_data_malformed():
    """Vérifie le rejet des payloads malformés ou altérés."""
    secret = "secret-test"
    # Format incorrect
    valid, _, _, msg = parse_callback_data("invalid:payload", secret)
    assert valid is False
    assert "Format" in msg

    # Action inconnue
    valid, _, _, msg = parse_callback_data("si:unknown:prop_123:sig123456789", secret)
    assert valid is False
    assert "inconnue" in msg

    # Signature invalide
    valid, _, _, msg = parse_callback_data("si:app:prop_123:000000000000", secret)
    assert valid is False
    assert "HMAC" in msg


# ─── 2. Persistance SQLite, Reprise & Déduplication ──────────────────────────
def test_proposal_store_crud_and_reload(isolated_store, temp_db_path, sample_proposal):
    """Vérifie l'écriture, la lecture et la reprise après redémarrage."""
    isolated_store.save(sample_proposal)

    # Lecture directe
    loaded = isolated_store.get(sample_proposal.proposal_id)
    assert loaded is not None
    assert loaded.goal == sample_proposal.goal
    assert loaded.status == STATE_PROPOSED
    assert loaded.modified_files == ["backend/core/tools/dispatcher.py"]
    assert loaded.tests_passed is True

    # Réouverture nouvelle instance (simulation redémarrage serveur)
    reloaded_store = ProposalStore(db_path=temp_db_path)
    active_proposals = reloaded_store.list_active()
    assert len(active_proposals) == 1
    assert active_proposals[0].proposal_id == sample_proposal.proposal_id


def test_proposal_store_atomic_transitions_and_deduplication(isolated_store, sample_proposal):
    """Vérifie les transitions d'état et la déduplication des doubles clics."""
    isolated_store.save(sample_proposal)
    prop_id = sample_proposal.proposal_id

    # 1. Premier clic 'Approuver' : transition proposed -> approved réussie
    ok, updated, msg = isolated_store.transition_status(
        proposal_id=prop_id,
        from_states=[STATE_PROPOSED],
        to_state=STATE_APPROVED,
    )
    assert ok is True
    assert updated.status == STATE_APPROVED

    # 2. Deuxième clic 'Approuver' immédiat (double clic) : dédupliqué sans erreur
    ok2, updated2, msg2 = isolated_store.transition_status(
        proposal_id=prop_id,
        from_states=[STATE_PROPOSED],
        to_state=STATE_APPROVED,
    )
    assert ok2 is False
    assert "déjà enregistrée" in msg2
    assert updated2.status == STATE_APPROVED

    # 3. Transition interdite (depuis approved directement vers edit_requested sans repasser par proposed)
    ok3, updated3, msg3 = isolated_store.transition_status(
        proposal_id=prop_id,
        from_states=[STATE_PROPOSED],
        to_state=STATE_EDIT_REQUESTED,
    )
    assert ok3 is False
    assert "Transition invalide" in msg3


# ─── 3. Politique de Merge Sécurisée (AUTO_MERGE_ENABLED) ─────────────────────
def test_evaluate_merge_policy_disabled_by_default(sample_proposal):
    """Vérifie le blocage du merge automatique quand AUTO_MERGE_ENABLED=False."""
    # Désactivé par défaut
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=False)
    assert allowed is False
    assert "désactivé par défaut" in reason


def test_evaluate_merge_policy_size_limit(sample_proposal):
    """Vérifie le rejet d'un patch >= 150 lignes même si AUTO_MERGE_ENABLED=True."""
    sample_proposal.diff_line_count = 150
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is False
    assert "trop volumineux" in reason

    sample_proposal.diff_line_count = 149
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is True


def test_evaluate_merge_policy_failing_tests(sample_proposal):
    """Vérifie le rejet si les tests ne sont pas passés."""
    sample_proposal.tests_passed = False
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is False
    assert "tests unitaires" in reason


def test_evaluate_merge_policy_blocks_protected_paths(sample_proposal):
    """Vérifie le rejet absolu si un chemin protégé (ex: auth_service.py) est touché."""
    sample_proposal.modified_files = ["backend/services/auth_service.py"]
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is False
    assert "protégé" in reason


def test_evaluate_merge_policy_requires_second_model(sample_proposal):
    """Vérifie l'obligation d'une revue indépendante par un second modèle."""
    sample_proposal.second_model_reviewed = False
    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is False
    assert "second modèle" in reason


def test_evaluate_merge_policy_all_green(sample_proposal):
    """Valide l'auto-merge quand toutes les 5 conditions sont réunies."""
    sample_proposal.diff_line_count = 45
    sample_proposal.tests_passed = True
    sample_proposal.modified_files = ["backend/core/tools/new_helper.py"]
    sample_proposal.second_model_reviewed = True

    allowed, reason = evaluate_merge_policy(sample_proposal, auto_merge_enabled=True)
    assert allowed is True
    assert "validée avec succès" in reason


# ─── 4. Mise en Forme Telegram & Clavier Inline ──────────────────────────────
def test_format_telegram_report_and_buttons(sample_proposal):
    """Vérifie la structure HTML du rapport et le clavier inline."""
    html_text = format_telegram_report(sample_proposal)
    assert "Proposition d'Auto-Amélioration" in html_text
    assert "backend/core/tools" in html_text
    assert "gemini-3.8-flash" in html_text
    assert "https://github.com/Pierre38610/jarvis-core/pull/77" in html_text
    assert "<pre>" in html_text

    secret = "secret-key-42"
    keyboard = build_inline_keyboard(sample_proposal.proposal_id, secret)
    buttons = keyboard["inline_keyboard"][0]
    assert len(buttons) == 3
    assert buttons[0]["text"] == "✅ Approuver"
    assert buttons[1]["text"] == "❌ Rejeter"
    assert buttons[2]["text"] == "✏️ Modifier"
    for b in buttons:
        assert b["callback_data"].startswith("si:")


# ─── 5. Adaptateur Telegram, Mock HTTP & Traitement Callback ─────────────────
@pytest.mark.asyncio
async def test_telegram_adapter_send_proposal_with_mock_client(isolated_store, sample_proposal):
    """Vérifie l'expédition de la proposition via un client HTTP mocké sans réseau."""
    mock_http = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 9988}}
    mock_http.post.return_value = mock_resp

    adapter = SelfImprovementTelegramAdapter(
        bot_token="fake_bot_token_123",
        chat_id="fake_chat_id_456",
        hmac_secret="test_secret",
        store=isolated_store,
        http_client=mock_http,
    )

    success, msg_id, status_msg = await adapter.send_proposal(sample_proposal)
    assert success is True
    assert msg_id == 9988
    assert mock_http.post.called

    # Vérification que le message_id a bien été persisté en base
    saved = isolated_store.get(sample_proposal.proposal_id)
    assert saved.telegram_message_id == 9988


@pytest.mark.asyncio
async def test_telegram_adapter_handle_approve_with_auto_merge(isolated_store, sample_proposal):
    """Vérifie le traitement du callback 'Approuver' avec fusion automatique autorisée."""
    mock_http = AsyncMock()
    # Mock send editMessageText and GitHub API merge
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_http.post.return_value = mock_resp

    isolated_store.save(sample_proposal)

    adapter = SelfImprovementTelegramAdapter(
        bot_token="mock_tok",
        chat_id="fake_chat_id",
        hmac_secret="test_secret",
        auto_merge_enabled=True,  # Active pour tester la branche
        store=isolated_store,
        http_client=mock_http,
    )

    cb_approve = build_callback_data(ACTION_APPROVE, sample_proposal.proposal_id, "test_secret")
    res = await adapter.handle_callback_query(cb_approve, user_id="fake_chat_id")

    assert res["status"] == "success"
    assert res["action"] == "approved"
    assert res["merge_allowed"] is True
    assert res["proposal"]["status"] == STATE_MERGED


@pytest.mark.asyncio
async def test_telegram_adapter_handle_reject_and_edit(isolated_store, sample_proposal):
    """Vérifie les callbacks de rejet et de demande de modification."""
    mock_http = AsyncMock()
    mock_http.post.return_value = MagicMock(status_code=200)

    # 1. Rejet
    isolated_store.save(sample_proposal)
    adapter = SelfImprovementTelegramAdapter(
        bot_token="mock_tok",
        chat_id="user_123",
        hmac_secret="sec_key",
        store=isolated_store,
        http_client=mock_http,
    )

    cb_reject = build_callback_data(ACTION_REJECT, sample_proposal.proposal_id, "sec_key")
    res_rej = await adapter.handle_callback_query(cb_reject, user_id="user_123", feedback="Code inutile")
    assert res_rej["status"] == "success"
    assert res_rej["action"] == "rejected"
    assert res_rej["proposal"]["status"] == STATE_REJECTED
    assert res_rej["proposal"]["rejection_reason"] == "Code inutile"

    # 2. Demande de modification sur une nouvelle proposition
    sample_proposal.proposal_id = "prop_edit_789"
    sample_proposal.status = STATE_PROPOSED
    isolated_store.save(sample_proposal)

    cb_edit = build_callback_data(ACTION_EDIT, sample_proposal.proposal_id, "sec_key")
    res_edit = await adapter.handle_callback_query(cb_edit, user_id="user_123", feedback="Ajouter des logs")
    assert res_edit["status"] == "success"
    assert res_edit["action"] == "edit_requested"
    assert res_edit["proposal"]["status"] == STATE_EDIT_REQUESTED
    assert res_edit["proposal"]["edit_feedback"] == "Ajouter des logs"


@pytest.mark.asyncio
async def test_telegram_adapter_rejects_unauthorized_user(isolated_store, sample_proposal):
    """Vérifie le refus si le user_id ne correspond pas à l'administrateur configuré."""
    isolated_store.save(sample_proposal)
    adapter = SelfImprovementTelegramAdapter(
        bot_token="tok",
        chat_id="admin_id_real",
        hmac_secret="sec_key",
        store=isolated_store,
    )
    cb_approve = build_callback_data(ACTION_APPROVE, sample_proposal.proposal_id, "sec_key")
    res = await adapter.handle_callback_query(cb_approve, user_id="intruder_user_999")
    assert res["status"] == "forbidden"


# ─── 6. Injection dans run_self_improvement ─────────────────────────────────
@pytest.mark.asyncio
async def test_run_self_improvement_calls_injected_telegram_adapter():
    """Vérifie que run_self_improvement expédie bien la proposition si un adaptateur est injecté."""
    from services.self_improvement_service import run_self_improvement

    mock_telegram = AsyncMock()
    mock_telegram.send_proposal = AsyncMock(return_value=(True, 1234, "OK"))

    with patch("services.self_improvement_service.check_quota_available", return_value=(True, "Quota OK")), \
         patch("services.self_improvement_service.create_isolated_worktree", return_value="/fake/wt"), \
         patch("services.self_improvement_service.cleanup_isolated_worktree"), \
         patch("services.self_improvement_service._run_agy_process", new_callable=AsyncMock, return_value=(0, "Success", "")), \
         patch("services.self_improvement_service._run_local_validation_gate", return_value=(True, "OK")), \
         patch("services.self_improvement_service.review_diff", return_value=(True, "Diff clean")), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="diff content")), \
         patch("services.self_improvement_service._create_github_pr", new_callable=AsyncMock, return_value="https://github.com/Pierre38610/jarvis-core/pull/88"):

        res = await run_self_improvement(
            goal="Test notification Telegram",
            target_subfolder="backend/core/tools",
            complexity="low",
            create_pr=True,
            telegram_adapter=mock_telegram,
        )

        assert res.status == "success"
        assert mock_telegram.send_proposal.called
        called_prop = mock_telegram.send_proposal.call_args[0][0]
        assert called_prop.goal == "Test notification Telegram"
        assert called_prop.subfolder == "backend/core/tools"
        assert called_prop.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/88"
