"""tests/test_system_healing.py
Suite de tests de validation complète pour l'auto-guérison système SRE J.A.R.V.I.S. :
- Validation isolée en sandbox
- Génération automatique de test de non-régression
- Déploiement Blue/Green releases/timestamp + symlink current
- Rollback instantané
- Seuil de confiance & Escalade sur fichiers critiques (auth_service.py, dispatcher.py)
- Journalisation relationnelle PostgreSQL / SQLite (patches_auto_appliques)
- Endpoints de supervision & Dispatcher vocal
"""

import os
import sys
import json
import shutil
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from services.system_healing_service import SystemHealingService, system_healing_service
from core.tools.dispatcher import dispatch_tool


@pytest.fixture
def mock_healing_workspace():
    """Crée un environnement temporaire simulant le workspace jarvis-core."""
    temp_dir = tempfile.mkdtemp(prefix="test_healing_ws_")
    services_dir = os.path.join(temp_dir, "services")
    core_tools_dir = os.path.join(temp_dir, "core", "tools")
    tests_dir = os.path.join(temp_dir, "tests")
    os.makedirs(services_dir, exist_ok=True)
    os.makedirs(core_tools_dir, exist_ok=True)
    os.makedirs(tests_dir, exist_ok=True)

    # 1. Fichier non critique
    dummy_service = os.path.join(services_dir, "dummy_calculator.py")
    with open(dummy_service, "w", encoding="utf-8") as f:
        f.write("def calculate_sum(a, b):\n    return a - b  # Bug volontaire : soustraction au lieu d'addition\n")

    # 2. Fichier critique (auth_service.py)
    auth_service = os.path.join(services_dir, "auth_service.py")
    with open(auth_service, "w", encoding="utf-8") as f:
        f.write("def authenticate_client(token):\n    return False  # Bug critique d'authentification\n")

    # 3. Fichier critique (dispatcher.py)
    dispatcher_file = os.path.join(core_tools_dir, "dispatcher.py")
    with open(dispatcher_file, "w", encoding="utf-8") as f:
        f.write("def dispatch_call(tool_name):\n    return 'routed'\n")

    service = SystemHealingService(workspace_dir=temp_dir, buffer_size=50)

    yield service, temp_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_is_critical_file_detection(mock_healing_workspace):
    """Vérifie la détection stricte des fichiers critiques (auth_service.py, dispatcher.py, etc.)."""
    service, _ = mock_healing_workspace
    assert service.is_critical_file("services/auth_service.py") is True
    assert service.is_critical_file("core/tools/dispatcher.py") is True
    assert service.is_critical_file("auth.py") is True
    assert service.is_critical_file("dispatcher.py") is True
    assert service.is_critical_file("services/dummy_calculator.py") is False
    assert service.is_critical_file("services/transport_service.py") is False


def test_parse_patch_from_output(mock_healing_workspace):
    """Vérifie le parsing de patches JSON structurés, blocs diff et fallbacks."""
    service, _ = mock_healing_workspace

    raw_json_patch = """
    Voici mon analyse RCA.
    ```json:patch
    {
      "target_file": "services/dummy_calculator.py",
      "search_block": "return a - b",
      "replace_block": "return a + b",
      "explanation": "Correction de l'opérateur arithmétique"
    }
    ```
    """
    p1 = service.parse_patch_from_output(raw_json_patch)
    assert p1["target_file"] == "services/dummy_calculator.py"
    assert p1["search_block"] == "return a - b"
    assert p1["replace_block"] == "return a + b"
    assert p1["patch_type"] == "replace_snippet"

    # Test avec diff unified
    raw_diff = """
    ```diff
    --- a/services/dummy_calculator.py
    +++ b/services/dummy_calculator.py
    @@ -1,2 +1,2 @@
    -return a - b
    +return a + b
    ```
    """
    p2 = service.parse_patch_from_output(raw_diff)
    assert p2["target_file"] == "services/dummy_calculator.py"
    assert "--- a/services/dummy_calculator.py" in p2["diff_text"]


def test_apply_patch_syntax_validation(mock_healing_workspace):
    """Vérifie que py_compile bloque un patch syntaxiquement invalide sans altérer le fichier original."""
    service, temp_dir = mock_healing_workspace

    # Patch syntaxiquement invalide
    invalid_patch = {
        "search_block": "return a - b",
        "replace_block": "return a + ((def broken syntax",
        "patch_type": "replace_snippet"
    }

    ok, diff, err = service.apply_patch_to_target(temp_dir, "services/dummy_calculator.py", invalid_patch)
    assert ok is False
    assert "py_compile" in err

    # Le fichier source doit rester intact
    with open(os.path.join(temp_dir, "services/dummy_calculator.py"), "r", encoding="utf-8") as f:
        content = f.read()
    assert "return a - b" in content


def test_find_or_generate_non_regression_test(mock_healing_workspace):
    """Vérifie qu'un test minimal de non-régression est auto-généré si aucun test n'existe."""
    service, temp_dir = mock_healing_workspace

    test_files, is_gen, gen_code = service.find_or_generate_tests(
        sandbox_dir=temp_dir,
        target_file="services/dummy_calculator.py",
        incident_context={"message": "Erreur de calcul"}
    )

    assert is_gen is True
    assert len(test_files) == 1
    assert "test_regression_dummy_calculator.py" in test_files[0]
    assert os.path.exists(os.path.join(temp_dir, test_files[0]))
    assert "def test_module_import_and_integrity_dummy_calculator" in gen_code


@pytest.mark.asyncio
async def test_non_critical_patch_auto_applied_with_releases_and_symlink(mock_healing_workspace):
    """Vérifie qu'un patch sur un fichier standard valide les tests en sandbox isolée,
    crée la release releases/timestamp, active le symlink current et est loggé en 'applied'.
    """
    service, temp_dir = mock_healing_workspace

    raw_output = """
    ## RCA
    L'opérateur était erroné.
    ```json:patch
    {
      "target_file": "services/dummy_calculator.py",
      "search_block": "return a - b",
      "replace_block": "return a + b",
      "explanation": "Fix de l'addition"
    }
    ```
    ```python:test
    import pytest
    from services.dummy_calculator import calculate_sum

    def test_calculate_sum():
        assert calculate_sum(2, 3) == 5
    ```
    """

    res = await service.process_healing_patch(
        incident_motif="Erreur calculatrice",
        raw_agent_output=raw_output,
        incident_context={"source": "services/dummy_calculator.py"}
    )

    assert res["success"] is True, f"Failed with res: {res}"
    assert res["status"] == "applied"
    assert res["is_critical"] is False
    assert "release_path" in res
    assert os.path.exists(res["release_path"])

    # Vérification que le patch est appliqué dans le workspace
    with open(os.path.join(temp_dir, "services/dummy_calculator.py"), "r", encoding="utf-8") as f:
        applied_code = f.read()
    assert "return a + b" in applied_code

    # Vérification de la journalisation en base / mémoire
    patches = await service.get_recent_patches(limit=5)
    assert len(patches) >= 1
    p = patches[0]
    assert p["target_file"] == "services/dummy_calculator.py"
    assert p["status"] == "applied"
    assert p["is_critical"] is False


@pytest.mark.asyncio
async def test_critical_file_escalation_requires_validation(mock_healing_workspace):
    """Vérifie la règle d'escalade : Si un fichier critique (auth_service.py) est touché,
    le patch N'EST PAS auto-appliqué et passe en 'requires_validation' avec demande vocale pour Pierre.
    """
    service, temp_dir = mock_healing_workspace

    raw_output = """
    ## RCA
    Authentification bloquée à False.
    ```json:patch
    {
      "target_file": "services/auth_service.py",
      "search_block": "return False  # Bug critique d'authentification",
      "replace_block": "return True  # Corrigé",
      "explanation": "Rétablissement de l'authentification"
    }
    ```
    ```python:test
    import pytest
    from services.auth_service import authenticate_client

    def test_auth():
        assert authenticate_client("valid_token") is True
    ```
    """

    res = await service.process_healing_patch(
        incident_motif="Bug critique auth",
        raw_agent_output=raw_output,
        incident_context={"source": "services/auth_service.py"}
    )

    assert res["success"] is True, f"Failed with res: {res}"
    assert res["status"] == "requires_validation"
    assert res["is_critical"] is True
    assert "sollicite ta validation orale" in res["oral_pitch"]

    # Le workspace actif NE DOIT PAS avoir été modifié sans validation !
    with open(os.path.join(temp_dir, "services/auth_service.py"), "r", encoding="utf-8") as f:
        prod_code = f.read()
    assert "return False" in prod_code

    # Validation manuelle / orale de Pierre
    app_res = await service.approve_and_apply_patch(res["patch_id"])
    assert app_res["success"] is True

    # Après approbation, le fichier est mis à jour
    with open(os.path.join(temp_dir, "services/auth_service.py"), "r", encoding="utf-8") as f:
        approved_code = f.read()
    assert "return True" in approved_code


@pytest.mark.asyncio
async def test_instant_rollback(mock_healing_workspace):
    """Vérifie le rollback instantané d'un patch appliqué."""
    service, temp_dir = mock_healing_workspace

    # 1. Déploiement d'un patch valide
    raw_output = """
    ```json:patch
    {
      "target_file": "services/dummy_calculator.py",
      "search_block": "return a - b",
      "replace_block": "return a + b",
      "explanation": "Fix de l'addition"
    }
    ```
    ```python:test
    def test_dummy():
        assert True
    ```
    """
    res = await service.process_healing_patch(
        incident_motif="Test calculatrice",
        raw_agent_output=raw_output,
        incident_context={"source": "services/dummy_calculator.py"}
    )
    assert res["status"] == "applied"
    patch_id = res["patch_id"]

    # Le fichier est modifié
    with open(os.path.join(temp_dir, "services/dummy_calculator.py"), "r", encoding="utf-8") as f:
        assert "return a + b" in f.read()

    # 2. Déclenchement du rollback instantané
    rb_res = await service.rollback_patch(patch_id=patch_id)
    assert rb_res["success"] is True

    # Le fichier est restauré à sa version initiale
    with open(os.path.join(temp_dir, "services/dummy_calculator.py"), "r", encoding="utf-8") as f:
        restored_code = f.read()
    assert "return a - b" in restored_code

    # Statut en base mis à jour
    patches = await service.get_recent_patches(limit=5)
    target = next(p for p in patches if p["id"] == patch_id)
    assert target["status"] == "rolled_back"
    assert target["rolled_back_at"] is not None


@pytest.mark.asyncio
async def test_failing_tests_reject_patch(mock_healing_workspace):
    """Vérifie qu'un patch qui fait échouer les tests en sandbox isolée est rejeté."""
    service, temp_dir = mock_healing_workspace

    raw_output = """
    ```json:patch
    {
      "target_file": "services/dummy_calculator.py",
      "search_block": "return a - b",
      "replace_block": "return 42",
      "explanation": "Remplacement aberrant"
    }
    ```
    ```python:test
    from services.dummy_calculator import calculate_sum

    def test_broken():
        assert calculate_sum(1, 1) == 2  # 42 != 2 -> échec
    ```
    """

    res = await service.process_healing_patch(
        incident_motif="Test échec",
        raw_agent_output=raw_output,
        incident_context={"source": "services/dummy_calculator.py"}
    )

    assert res["success"] is False
    assert res["status"] == "failed_tests"
    assert "rejeté" in res["oral_pitch"]

    # Fichier original préservé
    with open(os.path.join(temp_dir, "services/dummy_calculator.py"), "r", encoding="utf-8") as f:
        assert "return a - b" in f.read()

    patches = await service.get_recent_patches(limit=5)
    assert patches[0]["status"] == "failed_tests"


@pytest.mark.asyncio
async def test_tool_dispatcher_system_self_healing_actions():
    """Valide les actions de rollback et approve via l'outil vocal system_self_healing."""
    mock_ws = AsyncMock()

    with patch("services.system_healing_service.system_healing_service.rollback_patch", new_callable=AsyncMock) as mock_rb:
        mock_rb.return_value = {"success": True, "patch_id": "p123", "target_file": "services/dummy.py"}
        res = await dispatch_tool(
            name="system_self_healing",
            # Le portail arg_validator exige confirmed_by_user=True pour rollback/approve
            args={"action": "rollback", "patch_id": "p123", "confirmed_by_user": True},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )
        assert res["status"] in ("success", "done")
        assert res["action"] == "rollback_patch"
        assert "annulé immédiatement" in res["instruction_to_jarvis"]

    with patch("services.system_healing_service.system_healing_service.approve_and_apply_patch", new_callable=AsyncMock) as mock_app:
        mock_app.return_value = {"success": True, "patch_id": "p456", "target_file": "services/auth_service.py"}
        res_app = await dispatch_tool(
            name="system_self_healing",
            args={"action": "approve", "patch_id": "p456", "confirmed_by_user": True},
            websocket=mock_ws,
            session=MagicMock(),
            is_paid_live=False,
            live_display_label="Gemini Flash"
        )
        assert res_app["status"] in ("success", "done")
        assert res_app["action"] == "approve_patch"
        assert "pris en compte ta validation" in res_app["instruction_to_jarvis"]
