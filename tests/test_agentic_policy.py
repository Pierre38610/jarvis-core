"""Tests unitaires pour la politique de choix des modèles et validation Antigravity.
"""

import pytest
from services.antigravity_models import (
    MODEL_FLASH,
    MODEL_PRO,
    EFFORT_LOW,
    EFFORT_MEDIUM,
    EFFORT_HIGH,
    choose_model_and_effort,
    validate_model_and_effort,
)
from services.agentic_runner import _build_command


def test_choose_model_and_effort_light_tasks():
    # léger -> flash / low
    model, effort = choose_model_and_effort("tâche légère de mise en forme", "low")
    assert model == MODEL_FLASH
    assert effort == EFFORT_LOW

    model, effort = choose_model_and_effort("quick check", "medium")
    assert model == MODEL_FLASH
    assert effort == EFFORT_LOW


def test_choose_model_and_effort_writing_and_comparison():
    # rédaction/comparaison -> flash/medium ou flash/high selon complexité
    model, effort = choose_model_and_effort("rédaction d'un compte rendu", "medium")
    assert model == MODEL_FLASH
    assert effort == EFFORT_MEDIUM

    model, effort = choose_model_and_effort("comparaison de benchmarks", "high")
    assert model == MODEL_FLASH
    assert effort == EFFORT_HIGH


def test_choose_model_and_effort_deep_and_architectural_tasks():
    # décision, recherche multi-source, débogage profond, architecture -> pro / high
    tasks = [
        ("décision technique sur la stack", "medium"),
        ("recherche multi-source sur les microservices", "low"),
        ("débogage profond d'une fuite mémoire", "medium"),
        ("architecture du pipeline de streaming audio", "high"),
    ]
    for task, complexity in tasks:
        model, effort = choose_model_and_effort(task, complexity)
        assert model == MODEL_PRO, f"Échec pour la tâche {task}"
        assert effort == EFFORT_HIGH, f"Échec d'effort pour la tâche {task}"


def test_validate_model_and_effort_valid_inputs():
    m, e = validate_model_and_effort("flash", "low")
    assert m == "flash"
    assert e == "low"

    m, e = validate_model_and_effort("PRO", "HIGH")
    assert m == "pro"
    assert e == "high"


def test_validate_model_and_effort_invalid_inputs():
    with pytest.raises(ValueError, match="Modèle.*invalide"):
        validate_model_and_effort("gpt-4", "low")

    with pytest.raises(ValueError, match="Effort.*invalide"):
        validate_model_and_effort("flash", "ultra")


def test_command_builder_rejects_thinking_flag():
    # Vérification que --thinking déclenche une exception
    with pytest.raises(ValueError, match="--thinking.*interdite"):
        _build_command("architect", "prompt", "flash", "low --thinking")
