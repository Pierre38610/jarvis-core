"""tests/test_workspace_service.py
Validation unitaire et d'étanchéité de WorkspaceService (accès lecture seule à _anti_gravity).
Règle : Zéro appel API Gemini dans les tests (tout est simulé ou local).
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import AsyncMock, patch

from services.workspace_service import (
    WorkspaceService,
    is_path_safe,
    is_binary_file,
    ANTI_GRAVITY_ROOT,
)
from core.tools.dispatcher import dispatch_tool


import shutil

TEST_TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_workspace_sandbox")

@pytest.fixture
def temp_workspace():
    """Crée un espace temporaire sous le workspace simulant _anti_gravity."""
    if os.path.exists(TEST_TMP_DIR):
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
    os.makedirs(TEST_TMP_DIR, exist_ok=True)
    tmpdir = TEST_TMP_DIR
    try:
        # Création arborescence
        stages_dir = os.path.join(tmpdir, "Stages", "Scintil")
        os.makedirs(stages_dir, exist_ok=True)
        with open(os.path.join(stages_dir, "rapport.md"), "w", encoding="utf-8") as f:
            f.write("# Rapport Scintil\nStage en photonique intégrée.\nLigne 3.\nLigne 4.\n")

        micro_saas = os.path.join(tmpdir, "Micro-SaaS")
        os.makedirs(micro_saas, exist_ok=True)
        with open(os.path.join(micro_saas, "app.py"), "w", encoding="utf-8") as f:
            f.write("def run():\n    print('Hello Micro-SaaS')\n")

        # Dossiers à ignorer
        git_dir = os.path.join(tmpdir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        with open(os.path.join(git_dir, "config"), "w") as f:
            f.write("git config")

        node_dir = os.path.join(tmpdir, "node_modules")
        os.makedirs(node_dir, exist_ok=True)
        with open(os.path.join(node_dir, "package.json"), "w") as f:
            f.write("{}")

        # Fichier sensible à bloquer
        with open(os.path.join(tmpdir, ".env"), "w") as f:
            f.write("SECRET_KEY=12345")

        with open(os.path.join(tmpdir, "id_rsa"), "w") as f:
            f.write("PRIVATE KEY")

        # Fichier binaire
        with open(os.path.join(tmpdir, "image.png"), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        yield tmpdir
    finally:
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)


def test_path_safety(temp_workspace):
    """Vérifie l'interdiction de path traversal et l'exclusion des fichiers sensibles."""
    # Chemin normal
    safe, msg = is_path_safe(os.path.join(temp_workspace, "Stages"), temp_workspace)
    assert safe is True

    # Tentative d'évasion path traversal
    outside = os.path.join(temp_workspace, "..", "autre_chose")
    safe, msg = is_path_safe(outside, temp_workspace)
    assert safe is False
    assert "Accès interdit" in msg

    # Fichier sensible .env
    env_file = os.path.join(temp_workspace, ".env")
    safe, msg = is_path_safe(env_file, temp_workspace)
    assert safe is False
    assert "Accès refusé" in msg

    # Fichier sensible id_rsa
    rsa_file = os.path.join(temp_workspace, "id_rsa")
    safe, msg = is_path_safe(rsa_file, temp_workspace)
    assert safe is False


def test_binary_detection(temp_workspace):
    """Vérifie la détection fiable des fichiers binaires."""
    png_file = os.path.join(temp_workspace, "image.png")
    assert is_binary_file(png_file) is True

    text_file = os.path.join(temp_workspace, "Stages", "Scintil", "rapport.md")
    assert is_binary_file(text_file) is False


@pytest.mark.asyncio
async def test_list_directory(temp_workspace):
    """Vérifie l'exploration du répertoire en ignorant node_modules, .git, et fichiers sensibles."""
    svc = WorkspaceService(root_dir=temp_workspace)
    res = await svc.list_directory("", depth=2)

    assert res["status"] == "success"
    names = [it["name"] for it in res["items"]]

    # Doit contenir les dossiers et fichiers légitimes
    assert "Stages" in names
    assert "Micro-SaaS" in names

    # Ne doit PAS contenir .git ni node_modules
    assert ".git" not in names
    assert "node_modules" not in names

    # Ne doit PAS contenir les fichiers sensibles
    assert ".env" not in names
    assert "id_rsa" not in names


@pytest.mark.asyncio
async def test_read_file(temp_workspace):
    """Vérifie la lecture paginée d'un fichier textuel légitime."""
    svc = WorkspaceService(root_dir=temp_workspace)
    res = await svc.read_file("Stages/Scintil/rapport.md", max_lines=2, offset_line=1)

    assert res["status"] == "success"
    assert res["total_lines"] == 4
    assert res["lines_shown"] == 2
    assert "Rapport Scintil" in res["content"]


@pytest.mark.asyncio
async def test_read_binary_file(temp_workspace):
    """Vérifie que la lecture d'un fichier binaire retourne le statut adéquat sans crasher."""
    svc = WorkspaceService(root_dir=temp_workspace)
    res = await svc.read_file("image.png")

    assert res["status"] == "binary_file"
    assert "binaire" in res["message"].lower()


@pytest.mark.asyncio
async def test_search_files(temp_workspace):
    """Vérifie la recherche textuelle (grep) dans l'arborescence."""
    svc = WorkspaceService(root_dir=temp_workspace)
    res = await svc.search_files(query="photonique")

    assert res["status"] == "success"
    assert res["matches_count"] >= 1
    assert any("photonique" in m["snippet"].lower() for m in res["matches"])


def test_strict_read_only_contract():
    """Garantie absolue : aucune méthode d'écriture ou de modification sur WorkspaceService."""
    svc = WorkspaceService()
    forbidden_prefixes = ["write", "create", "delete", "remove", "update", "modify", "save", "patch"]
    for attr in dir(svc):
        for prefix in forbidden_prefixes:
            assert not attr.startswith(prefix), f"Méthode interdite trouvée sur WorkspaceService : {attr}"


@pytest.mark.asyncio
async def test_dispatcher_workspace_tools(temp_workspace):
    """Vérifie le bon routage des outils list_workspace_files, read_workspace_file, search_workspace_files par dispatcher."""
    with patch("services.workspace_service.workspace_service.root_dir", temp_workspace), \
         patch("services.workspace_service.workspace_service.is_available_locally", return_value=True):

        # 1. list_workspace_files
        res_list = await dispatch_tool("list_workspace_files", {"relative_path": ""})
        assert res_list.get("status") in ("done", "success")

        # 2. read_workspace_file
        res_read = await dispatch_tool("read_workspace_file", {"file_path": "Stages/Scintil/rapport.md"})
        assert res_read.get("status") in ("done", "success")

        # 3. search_workspace_files
        res_search = await dispatch_tool("search_workspace_files", {"query": "Micro-SaaS"})
        assert res_search.get("status") in ("done", "success")
