"""backend/tests/unit/test_prompt_batch_parser.py
Tests unitaires pour le parser de séries de prompts (parse_prompt_batch_markdown)
et la validation sécurisée des chemins (validate_safe_batch_path).
"""

import os
import tempfile
import pytest

from services.prompt_batch_runner import (
    parse_prompt_batch_markdown,
    validate_safe_batch_path,
    load_batch_from_file,
    BatchSpec,
    PromptItem,
)
from services.self_improvement_service import REPO_ROOT


SAMPLE_VALID_MARKDOWN = """# Refactorisation Complète du Module Analytics

## Prompt 1: Nettoyage et typage strict (low)
CONTRAINTES D'ÉCONOMIE DE TOKENS — LIS UNIQUEMENT :
- backend/services/analytics.py
- backend/core/shared_state.py

Ajouter les annotations de type strictes Python 3.12+ sur les fonctions publiques.

COMMANDES DE VALIDATION EXACTES :
pytest backend/tests/unit/test_analytics.py -q

À FAIRE PAR L'UTILISATEUR :
- Vérifier les identifiants tiers dans le dashboard cloud

---

## Prompt 2: Ajout des métriques de rétention (high)
FICHIERS À LIRE :
- backend/services/analytics.py
- backend/services/metrics_service.py

Connecter le calcul de rétention au module metrics_service.

ACTIONS MANUELLES :
- Activer la clé API analytics sur la console de test
"""


def test_parse_valid_markdown_basic():
    """Vérifie le découpage des prompts, titres, niveaux et métadonnées."""
    spec: BatchSpec = parse_prompt_batch_markdown(SAMPLE_VALID_MARKDOWN)

    assert spec.title == "Refactorisation Complète du Module Analytics"
    assert len(spec.prompts) == 2

    p1 = spec.prompts[0]
    assert p1.label == "1"
    assert "Nettoyage et typage strict" in p1.title
    assert p1.level == "low"
    assert "backend/services/analytics.py" in p1.read_only_files
    assert "backend/core/shared_state.py" in p1.read_only_files
    assert p1.validation_command is not None
    assert "test_analytics.py" in p1.validation_command
    assert len(p1.manual_actions) == 1
    assert "Vérifier les identifiants" in p1.manual_actions[0]

    p2 = spec.prompts[1]
    assert p2.label == "2"
    assert "Ajout des métriques" in p2.title
    assert p2.level == "high"
    assert "backend/services/metrics_service.py" in p2.read_only_files
    assert len(p2.manual_actions) == 1
    assert "Activer la clé API" in p2.manual_actions[0]

    assert len(spec.all_manual_actions) == 2


def test_parse_sub_prompts_1a_1b():
    """Vérifie la prise en compte des indices alphanumériques (1A, 1B)."""
    md = """
### PROMPT 1A: Préparation de la base
NIVEAU : medium
Créer la table SQLite.

### PROMPT 1B: Migration des données
EFFORT : high
Migrer les anciens tuples.
"""
    spec = parse_prompt_batch_markdown(md)
    assert len(spec.prompts) == 2
    assert spec.prompts[0].label == "1A"
    assert spec.prompts[0].level == "medium"
    assert spec.prompts[1].label == "1B"
    assert spec.prompts[1].level == "high"


def test_parse_empty_content_raises_error():
    """Vérifie le rejet d'un contenu markdown vide."""
    with pytest.raises(ValueError, match="vide"):
        parse_prompt_batch_markdown("   \n\t  ")


def test_parse_no_prompts_raises_error():
    """Vérifie le rejet d'un document markdown sans en-tête de prompt."""
    with pytest.raises(ValueError, match="Aucun prompt détecté"):
        parse_prompt_batch_markdown("# Titre Seul\n\nDu texte sans en-tête de prompt.")


def test_parse_empty_prompt_body_raises_error():
    """Vérifie le rejet d'un prompt sans consigne."""
    md = """
## Prompt 1: Titre seul sans corps
## Prompt 2: Deuxième prompt
Ici il y a du texte.
"""
    with pytest.raises(ValueError, match="est vide"):
        parse_prompt_batch_markdown(md)


def test_parse_duplicate_prompt_numbers_raises_error():
    """Vérifie le rejet d'identifiants de prompts en double."""
    md = """
## Prompt 1: Première étape
Corps du prompt 1.

## Prompt 1: Doublon
Corps du doublon.
"""
    with pytest.raises(ValueError, match="en double"):
        parse_prompt_batch_markdown(md)


def test_validate_safe_batch_path_within_repo():
    """Vérifie l'acceptation d'un fichier au sein de REPO_ROOT ou downloads/."""
    # Test avec un fichier existant dans le dépôt
    arch_file = os.path.join(REPO_ROOT, "backend", "ARCHITECTURE.md")
    safe = validate_safe_batch_path(arch_file)
    assert os.path.isabs(safe)
    assert os.path.exists(safe)


def test_validate_safe_batch_path_traversal_rejected():
    """Vérifie le blocage des tentatives de traversée de répertoire hors périmètre."""
    with pytest.raises(PermissionError, match="hors périmètre"):
        validate_safe_batch_path("../../Windows/System32/drivers/etc/hosts")


def test_validate_safe_batch_path_nonexistent_raises():
    """Vérifie le rejet d'un fichier introuvable."""
    with pytest.raises(FileNotFoundError):
        validate_safe_batch_path("downloads/nonexistent_batch_xyz123.md")


def test_load_batch_from_file_roundtrip():
    """Vérifie le chargement direct d'un fichier temporaire de batch."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write(SAMPLE_VALID_MARKDOWN)
        f_path = f.name

    try:
        spec = load_batch_from_file(f_path)
        assert len(spec.prompts) == 2
        assert spec.source_file == os.path.abspath(f_path)
    finally:
        if os.path.exists(f_path):
            os.remove(f_path)
