"""backend/tests/unit/test_self_improvement_service.py
Tests unitaires pour le service d'auto-amélioration et d'auto-refactorisation autonome de Jarvis.
Vérifie le résolveur de sous-dossiers, la sélection dynamique des modèles, le confinement,
les portes de validation, la gouvernance (kill switch, quotas, journal) et le cycle de vie du worktree.
"""

import asyncio
import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.tools.dispatcher import dispatch_tool
from services.self_improvement_service import (
    SubfolderScope,
    SelfImprovementResult,
    resolve_subfolder_scope,
    resolve_live_agy_model,
    is_kill_switch_active,
    set_kill_switch,
    check_quota_available,
    record_run_in_journal,
    review_diff,
    _run_local_validation_gate,
    run_self_improvement,
    KILL_SWITCH_FILE,
    JOURNAL_FILE,
    MAX_RUNS_PER_DAY,
    MAX_RUNS_PER_WEEK,
)
from core.shared_state import ACTIVE_AGY_LOGS, active_task_controller


@pytest.fixture(autouse=True)
def cleanup_environment():
    """Garantit l'état propre du kill switch, des logs et du journal avant et après chaque test."""
    if os.path.exists(KILL_SWITCH_FILE):
        try:
            os.remove(KILL_SWITCH_FILE)
        except Exception:
            pass
    ACTIVE_AGY_LOGS.clear()

    # Sauvegarde et isolation du journal de quota pour les tests
    orig_journal = None
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                orig_journal = f.read()
            os.remove(JOURNAL_FILE)
        except Exception:
            pass

    yield

    if os.path.exists(KILL_SWITCH_FILE):
        try:
            os.remove(KILL_SWITCH_FILE)
        except Exception:
            pass
    ACTIVE_AGY_LOGS.clear()

    # Restauration du journal d'origine
    if orig_journal is not None:
        try:
            with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
                f.write(orig_journal)
        except Exception:
            pass
    elif os.path.exists(JOURNAL_FILE):
        try:
            os.remove(JOURNAL_FILE)
        except Exception:
            pass


# ─── 1. Résolveur de Sous-Dossier & Tests Ciblés ────────────────────────────
def test_resolve_subfolder_scope_with_explicit_hints():
    """Vérifie la résolution du périmètre via un indice de cible explicite."""
    # Test browser_agent
    scope_browser = resolve_subfolder_scope("Améliorer la vitesse", target_hint="backend/services/browser_agent")
    assert scope_browser.subfolder == "backend/services/browser_agent"
    assert "backend/services/browser_agent" in scope_browser.allowed_subdirs
    assert any("test_antigravity_task_engine.py" in t for t in scope_browser.targeted_test_files)
    assert scope_browser.architecture_file.endswith("ARCHITECTURE.md")

    # Test model_routing
    scope_routing = resolve_subfolder_scope("Ajuster les replis", target_hint="backend/services/model_routing")
    assert scope_routing.subfolder == "backend/services/model_routing"
    assert "backend/services/model_routing" in scope_routing.allowed_subdirs
    assert any("test_model_routing.py" in t for t in scope_routing.targeted_test_files)

    # Test tools
    scope_tools = resolve_subfolder_scope("Ajouter un outil", target_hint="backend/core/tools")
    assert scope_tools.subfolder == "backend/core/tools"
    assert "backend/core/tools" in scope_tools.allowed_subdirs

    # Test frontend
    scope_frontend = resolve_subfolder_scope("Mettre à jour le HUD", target_hint="frontend/static")
    assert scope_frontend.subfolder == "frontend/static"
    assert "frontend/static" in scope_frontend.allowed_subdirs


def test_resolve_subfolder_scope_heuristic_by_goal():
    """Vérifie la détection heuristique automatique par mots-clés du goal."""
    scope_browser = resolve_subfolder_scope("Corriger le bug de scraping dans le navigateur et playwright")
    assert scope_browser.subfolder == "backend/services/browser_agent"

    scope_tools = resolve_subfolder_scope("Déclarer une nouvelle fonction dans declarations et dispatcher")
    assert scope_tools.subfolder == "backend/core/tools"

    scope_deploy = resolve_subfolder_scope("Mettre à jour le script de sync_deploy et systemd sur oracle vps")
    assert scope_deploy.subfolder == "ops/deploy"

    # Repli inconnu
    scope_unknown = resolve_subfolder_scope("Quelque chose de complètement abstrait sans mot-clé")
    assert scope_unknown.subfolder == "backend/services"


# ─── 2. Sélection Dynamique des Modèles Antigravity ─────────────────────────
def test_resolve_live_agy_model_tiers():
    """Vérifie le mapping dynamique des complexités vers les modèles et efforts."""
    # Low -> Flash rapide + low
    model_low, effort_low = resolve_live_agy_model(complexity="low")
    assert "flash" in model_low.lower()
    assert effort_low == "low"
    assert "--thinking" not in model_low
    assert "--thinking" not in (effort_low or "")

    # Medium -> Flash récent + medium
    model_med, effort_med = resolve_live_agy_model(complexity="medium")
    assert "flash" in model_med.lower()
    assert effort_med == "medium"
    assert "--thinking" not in model_med

    # High -> Modèle Gemini 3 uniquement (gemini-3.8-flash ou gemini-3.1-pro), JAMAIS Claude ni Argon
    model_high, effort_high = resolve_live_agy_model(complexity="high")
    assert not any(k in model_high.lower() for k in ["sonnet", "opus", "claude", "argon"])
    assert any(k in model_high.lower() for k in ["flash", "pro", "gemini"])
    assert effort_high in ("high", None)
    assert "--thinking" not in model_high

    # Override explicite (choix Telegram) -> autorisé
    model_ov, effort_ov = resolve_live_agy_model(override_model="claude-sonnet-5-5-high")
    assert "claude" in model_ov.lower()
    assert effort_ov == "high"


# ─── 3. Gouvernance : Kill Switch & Quotas ──────────────────────────────────
def test_kill_switch_lifecycle():
    """Vérifie l'activation et la désactivation du kill switch persistant."""
    assert not is_kill_switch_active()
    set_kill_switch(True)
    assert is_kill_switch_active()
    assert os.path.exists(KILL_SWITCH_FILE)

    set_kill_switch(False)
    assert not is_kill_switch_active()
    assert not os.path.exists(KILL_SWITCH_FILE)


@pytest.mark.asyncio
async def test_run_self_improvement_blocked_by_kill_switch():
    """Vérifie le blocage immédiat de l'auto-amélioration lorsque le kill switch est actif."""
    set_kill_switch(True)
    res = await run_self_improvement(goal="Refactoriser un module")
    assert res.status == "blocked_kill_switch"
    assert "Kill Switch" in res.user_message


def test_quota_limits():
    """Vérifie le calcul des plafonds de runs journaliers et hebdomadaires."""
    with patch("services.self_improvement_service._load_journal") as mock_load:
        now = time.time()
        # 1. Quota vide
        mock_load.return_value = []
        ok, msg = check_quota_available()
        assert ok is True

        # 2. Quota journalier dépassé (10 runs récents)
        mock_load.return_value = [{"timestamp": now - 100} for _ in range(MAX_RUNS_PER_DAY)]
        ok, msg = check_quota_available()
        assert ok is False
        assert "quotidien" in msg

        # 3. Quota hebdomadaire dépassé (30 runs récents)
        mock_load.return_value = [{"timestamp": now - (2 * 86400)} for _ in range(MAX_RUNS_PER_WEEK)]
        ok, msg = check_quota_available()
        assert ok is False
        assert "hebdomadaire" in msg


# ─── 4. Revue de Diff & Portes de Sécurité ───────────────────────────────────
def test_review_diff():
    """Vérifie la détection de risques ou d'anomalies dans le diff."""
    # Diff vide
    ok, msg = review_diff("", "Optimisation")
    assert ok is False
    assert "vide" in msg

    # Diff suspect (eval)
    suspicious_diff = "+++ b/service.py\n+ eval(user_input)"
    ok, msg = review_diff(suspicious_diff, "Refactor")
    assert ok is False
    assert "suspect" in msg

    # Diff valide
    valid_diff = "--- a/service.py\n+++ b/service.py\n@@ -1,2 +1,3 @@\n+def new_helper():\n+    return 42\n"
    ok, msg = review_diff(valid_diff, "Ajout d'un helper")
    assert ok is True
    assert "validé" in msg


def test_validation_gate_confinement():
    """Vérifie le rejet d'un diff modifiant un fichier hors de allowed_subdirs."""
    scope = SubfolderScope(
        subfolder="backend/core/tools",
        allowed_subdirs=["backend/core/tools", "backend/core"],
        architecture_file="backend/ARCHITECTURE.md",
        targeted_test_files=[],
    )

    with patch("services.self_improvement_service._get_git_modified_files") as mock_mod:
        # Modification interdite dans frontend/
        mock_mod.return_value = [("M", "frontend/static/index.html")]
        ok, msg = _run_local_validation_gate("/fake/worktree", scope)
        assert ok is False
        assert "Violation de confinement" in msg

        # Modification autorisée dans backend/core/tools
        mock_mod.return_value = [("M", "backend/core/tools/declarations.py")]
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            ok, msg = _run_local_validation_gate("/fake/worktree", scope)
            assert ok is True


def test_validation_gate_blocks_protected_files():
    """Vérifie le rejet absolu de modifications sur des fichiers critiques protégés."""
    scope = SubfolderScope(
        subfolder="backend/services",
        allowed_subdirs=["backend/services"],
        architecture_file="backend/ARCHITECTURE.md",
        targeted_test_files=[],
    )

    with patch("services.self_improvement_service._get_git_modified_files") as mock_mod:
        # Tentative de modification de backend/services/auth_service.py
        mock_mod.return_value = [("M", "backend/services/auth_service.py")]
        ok, msg = _run_local_validation_gate("/fake/worktree", scope)
        assert ok is False
        assert "Violation des fichiers protégés" in msg


# ─── 5. Exécution Isolée & Nettoyage du Git Worktree ─────────────────────────
@pytest.mark.asyncio
async def test_run_self_improvement_full_loop_success():
    """Valide l'exécution complète d'une auto-amélioration réussie avec nettoyage du worktree."""
    with patch("services.self_improvement_service.create_isolated_worktree", return_value="/fake/wt") as mock_create, \
         patch("services.self_improvement_service.cleanup_isolated_worktree") as mock_cleanup, \
         patch("services.self_improvement_service._run_agy_process", new_callable=AsyncMock, return_value=(0, "Success", "")) as mock_proc, \
         patch("services.self_improvement_service._run_local_validation_gate", return_value=(True, "OK")), \
         patch("services.self_improvement_service.review_diff", return_value=(True, "Diff clean")), \
         patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="diff content")), \
         patch("services.self_improvement_service._create_github_pr", new_callable=AsyncMock, return_value="https://github.com/Pierre38610/jarvis-core/pull/99"):

        res = await run_self_improvement(
            goal="Optimiser la sélection des modèles",
            target_subfolder="backend/services/model_routing",
            complexity="medium",
            create_pr=True,
        )

        assert res.status == "success"
        assert res.iterations_count == 1
        assert res.pr_url == "https://github.com/Pierre38610/jarvis-core/pull/99"
        assert mock_create.called
        assert mock_cleanup.called
        assert mock_proc.called


# ─── 6. Routage Dispatcher de l'Outil self_improve ───────────────────────────
@pytest.mark.asyncio
async def test_dispatcher_self_improve_sync_execution():
    """Vérifie le dispatching synchrone de l'outil self_improve vers ToolResult.done."""
    mock_result = SelfImprovementResult(
        status="success",
        goal="Corriger le dispatcher",
        subfolder_scope=None,
        model_used="gemini-3.8-flash",
        effort_used="medium",
        iterations_count=1,
        branch_name="jarvis/fix-dispatcher-1234",
        pr_url="https://github.com/Pierre38610/jarvis-core/pull/42",
        diff_summary="+ new code",
        user_message="Auto-amélioration réussie.",
        duration_seconds=15.2,
    )

    with patch("services.self_improvement_service.run_self_improvement", new_callable=AsyncMock, return_value=mock_result):
        resp = await dispatch_tool(
            name="self_improve",
            args={
                "objectif": "Corriger le dispatcher",
                "sous_dossier_cible": "backend/core/tools",
                "sync": True,
            },
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        assert "Auto-amélioration réussie" in resp["user_message"]
        assert resp.get("pr_url") == "https://github.com/Pierre38610/jarvis-core/pull/42"


@pytest.mark.asyncio
async def test_dispatcher_self_improve_background_execution():
    """Vérifie le dispatching asynchrone (mode tâche de fond non-bloquante pour la voix Live)."""
    with patch("services.self_improvement_service.run_self_improvement", new_callable=AsyncMock) as mock_service:
        resp = await dispatch_tool(
            name="self_improve",
            args={
                "objectif": "Refonte du HUD mobile",
                "sous_dossier_cible": "frontend/static",
                "sync": False,
            },
        )

        assert resp["status"] == "started"
        assert "lancée en tâche de fond" in resp["user_message"]
        assert active_task_controller["bg_task"] is not None


@pytest.mark.asyncio
async def test_dispatcher_self_improve_propose_mode_triggers_technical_watch():
    """Vérifie que l'appel à self_improve en mode 'propose' déclenche generate_and_send_technical_improvements en tâche de fond."""
    with patch(
        "services.weekly_improvement_watch.generate_and_send_technical_improvements",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.return_value = {"status": "ok", "count": 3, "sent_count": 3}

        resp = await dispatch_tool(
            name="self_improve",
            args={
                "mode": "propose",
                "objectif": "Envoie-moi des propositions d'auto-amélioration sur Telegram",
                "sous_dossier_cible": "backend/services",
                "sync": False,
            },
        )

        assert resp["status"] == "started"
        assert "CAPABILITIES_LEDGER.md" in resp["user_message"] or "Telegram" in resp["user_message"]
        assert active_task_controller["bg_task"] is not None
        await active_task_controller["bg_task"]
        assert mock_gen.called
        assert mock_gen.call_args.kwargs.get("focus_area") == "backend/services"


# ─── 7. Validation de ensure_git_repository & Robustesse Worktree ─────────────
def test_ensure_git_repository_creates_git_if_missing(tmp_path):
    """Vérifie que ensure_git_repository initialise un dépôt Git si .git est absent."""
    from services.self_improvement_service import ensure_git_repository

    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="Jarvis Autonomous Agent")
        ensure_git_repository(str(fake_repo))

        calls = [c[0][0] for c in mock_sub.call_args_list]
        assert ["git", "init"] in calls
        assert ["git", "branch", "-M", "main"] in calls
        assert ["git", "remote", "add", "origin", "https://github.com/Pierre38610/jarvis-core.git"] in calls


def test_ensure_git_repository_prunes_if_git_exists(tmp_path):
    """Vérifie que ensure_git_repository nettoie les worktrees si .git existe déjà."""
    from services.self_improvement_service import ensure_git_repository

    fake_repo = tmp_path / "fake_repo_existing"
    fake_repo.mkdir()
    (fake_repo / ".git").mkdir()

    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(returncode=0, stdout="Jarvis Autonomous Agent")
        ensure_git_repository(str(fake_repo))

        calls = [c[0][0] for c in mock_sub.call_args_list]
        assert ["git", "worktree", "prune"] in calls
        assert ["git", "init"] not in calls
