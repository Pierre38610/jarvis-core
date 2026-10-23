"""backend/tests/unit/test_check_protected_paths.py
Tests unitaires offline du script anti-régression check_protected_paths.py.
Vérifie le blocage systématique des fichiers sensibles et autorise les évolutions légitimes.
"""

import pytest
import sys
import os

from ops.scripts.check_protected_paths import (
    check_change,
    check_all_changes,
    normalize_path,
    is_env_file,
    main,
)


def test_normalize_path():
    assert normalize_path(r"backend\services\auth_service.py") == "backend/services/auth_service.py"
    assert normalize_path("./backend/auth.py") == "backend/auth.py"
    assert normalize_path(".\\ops\\deploy\\jarvis_deployer.py") == "ops/deploy/jarvis_deployer.py"
    assert normalize_path("") == ""


def test_is_env_file():
    assert is_env_file(".env") is True
    assert is_env_file(".env.local") is True
    assert is_env_file(".env.production") is True
    assert is_env_file("config/.env") is True
    assert is_env_file("backend/services/chat_service.py") is False
    assert is_env_file("backend/environment.py") is False


@pytest.mark.parametrize(
    "status,path",
    [
        ("M", "backend/services/auth_service.py"),
        ("D", "backend/services/auth_service.py"),
        ("M", "backend/auth.py"),
        ("D", "backend/auth.py"),
        ("M", "backend/services/key_gate.py"),
        ("D", "backend/services/key_gate.py"),
        ("M", "backend/core/tools/arg_validator.py"),
        ("D", "backend/core/tools/arg_validator.py"),
        ("M", "ops/deploy/jarvis_deployer.py"),
        ("D", "ops/deploy/jarvis_deployer.py"),
        ("M", ".github/workflows/ci.yml"),
        ("A", ".github/workflows/security.yml"),
        ("D", ".github/workflows/ci.yml"),
        ("M", ".env"),
        ("D", ".env.local"),
        ("M", "backend/.env"),
    ],
)
def test_protected_sensitive_files_blocked(status, path):
    """Vérifie que toute altération (M, D, A) sur les fichiers sensibles est bloquée."""
    err = check_change(status, path)
    assert err is not None
    assert "[BLOCKED]" in err


def test_test_file_deletion_blocked():
    """Vérifie que la suppression d'un test sous backend/tests/ est bloquée."""
    err = check_change("D", "backend/tests/unit/test_arg_validator.py")
    assert err is not None
    assert "[BLOCKED]" in err
    assert "Suppression non autorisée d'un fichier de test" in err

    err_root_test = check_change("D", "backend/tests/test_browser_loop.py")
    assert err_root_test is not None
    assert "[BLOCKED]" in err_root_test


@pytest.mark.parametrize(
    "status,path",
    [
        ("M", "backend/services/chat_service.py"),
        ("A", "backend/routers/dashboard_router.py"),
        ("M", "frontend/static/app.js"),
        ("M", "ops/scripts/quality_report.py"),
        ("A", "backend/tests/unit/test_new_feature.py"),
        ("M", "backend/tests/unit/test_jarvis_deployer.py"),
        ("M", "backend/tests/test_browser_loop.py"),
        ("M", "docs/ARCHITECTURE.md"),
    ],
)
def test_allowed_changes(status, path):
    """Vérifie que les évolutions standards du code ou l'ajout/modification de tests sont autorisés."""
    err = check_change(status, path)
    assert err is None


def test_check_all_changes_aggregated():
    changes = [
        ("M", "backend/services/chat_service.py"),  # Autorisé
        ("A", "backend/tests/unit/test_new.py"),    # Autorisé
        ("M", "backend/services/key_gate.py"),      # Bloqué
        ("D", "backend/tests/unit/test_old.py"),    # Bloqué
    ]
    violations = check_all_changes(changes)
    assert len(violations) == 2
    assert any("key_gate.py" in v for v in violations)
    assert any("test_old.py" in v for v in violations)


def test_main_cli_files_authorized(capsys):
    ret = main(["--files", "backend/services/chat_service.py", "frontend/static/app.js"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "[OK]" in captured.out


def test_main_cli_files_violation(capsys):
    ret = main(["--files", "backend/services/auth_service.py"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "VIOLATION" in captured.out
    assert "auth_service.py" in captured.out


def test_main_cli_deleted_files_violation(capsys):
    ret = main(["--deleted-files", "backend/tests/unit/test_sample.py"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Suppression non autorisée" in captured.out


def test_main_cli_prefixed_files(capsys):
    ret = main(["--files", "D:backend/tests/unit/test_sample.py"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "Suppression non autorisée" in captured.out
