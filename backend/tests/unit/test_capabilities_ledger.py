"""backend/tests/unit/test_capabilities_ledger.py
Tests unitaires pour le registre de capacités CAPABILITIES_LEDGER.md et les fonctions
de vérification associées dans backend/services/architecture_service.py.
"""

import os
import pytest

from services.architecture_service import (
    get_capabilities_ledger_summary,
    verify_capability_not_already_implemented,
    _resolve_repo_root,
)


def test_capabilities_ledger_file_exists_and_has_4_sections():
    """Vérifie que CAPABILITIES_LEDGER.md existe à la racine et contient les 4 sections obligatoires."""
    repo_root = _resolve_repo_root()
    ledger_path = os.path.join(repo_root, "CAPABILITIES_LEDGER.md")
    assert os.path.exists(ledger_path), f"CAPABILITIES_LEDGER.md introuvable dans {repo_root}"

    content = get_capabilities_ledger_summary()
    assert len(content) > 500

    required_sections = [
        "## 1. CAPACITÉS IMPLÉMENTÉES & OPÉRATIONNELLES (NE JAMAIS REPROPOSER)",
        "## 2. LIMITES TECHNIQUES CONNUES & GOULETS D'ÉTRANGLEMENT",
        "## 3. HISTORIQUE DES AUTO-AMÉLIORATIONS APPLIQUÉES",
        "## 4. BACKLOG TECHNIQUE & AXES D'INGÉNIERIE PRIORITAIRES",
    ]
    for sec in required_sections:
        assert sec in content, f"Section obligatoire manquante dans CAPABILITIES_LEDGER.md : {sec}"


def test_verify_capability_detects_already_implemented_tools():
    """Vérifie que verify_capability_not_already_implemented rejette un outil déjà existant."""
    # 1. Tentative de recréer un outil existant (control_spotify ou search_web)
    ok_dup1, msg_dup1 = verify_capability_not_already_implemented(
        "Créer l'outil control_spotify pour piloter la musique",
        ["backend/core/tools/declarations.py"],
    )
    assert ok_dup1 is False
    assert "control_spotify" in msg_dup1

    ok_dup2, msg_dup2 = verify_capability_not_already_implemented(
        "Ajouter l'outil `launch_phone_navigation` pour Google Maps",
        ["backend/services/navigation_service.py"],
    )
    assert ok_dup2 is False
    assert "launch_phone_navigation" in msg_dup2

    # 2. Proposition d'amélioration technique nouvelle ou d'optimisation -> autorisée
    ok_new, msg_new = verify_capability_not_already_implemented(
        "Implémenter un cache sémantique Redis TTL 30m pour les recherches L2",
        ["backend/services/agentic_runner.py"],
    )
    assert ok_new is True

    # 3. Optimisation d'un outil existant (avec verbe d'optimisation/résilience) -> autorisée
    ok_opt, _ = verify_capability_not_already_implemented(
        "Optimisation de la résilience et du cache de search_web",
        ["backend/services/web_search.py"],
    )
    assert ok_opt is True
