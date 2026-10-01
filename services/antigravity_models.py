"""Définition des modèles, niveaux d'effort et politique de choix pour Google Antigravity.
"""

import shutil
from typing import Tuple, Set

# Détection de la disponibilité locale du binaire CLI agy
# Signalement : agy est indisponible localement sur cet environnement (Windows).
# Les constantes par défaut sont appliquées avec validation à l'exécution.
AGY_BINARY_PATH = shutil.which("agy")
IS_AGY_AVAILABLE = AGY_BINARY_PATH is not None

# Modèles supportés par le CLI agy
MODEL_FLASH = "flash"
MODEL_PRO = "pro"

VALID_MODELS: Set[str] = {MODEL_FLASH, MODEL_PRO}

# Niveaux d'effort acceptés par --effort
EFFORT_LOW = "low"
EFFORT_MEDIUM = "medium"
EFFORT_HIGH = "high"

VALID_EFFORTS: Set[str] = {EFFORT_LOW, EFFORT_MEDIUM, EFFORT_HIGH}


def validate_model_and_effort(model: str, effort: str) -> Tuple[str, str]:
    """Valide les paramètres model et effort.
    
    Lève ValueError si l'une des valeurs n'est pas conforme.
    """
    m = (model or "").strip().lower()
    e = (effort or "").strip().lower()

    if m not in VALID_MODELS:
        raise ValueError(f"Modèle '{model}' invalide pour agy. Modèles acceptés : {sorted(list(VALID_MODELS))}")

    if e not in VALID_EFFORTS:
        raise ValueError(f"Effort '{effort}' invalide pour agy. Niveaux acceptés : {sorted(list(VALID_EFFORTS))}")

    return m, e


def choose_model_and_effort(task_kind: str, complexity: str = "medium") -> Tuple[str, str]:
    """Sélectionne le modèle et le niveau d'effort appropriés selon la tâche et sa complexité.
    
    Règles :
    - léger -> flash / low
    - rédaction / comparaison -> flash / medium ou high (selon complexité)
    - décision, recherche multi-source, débogage profond, architecture -> pro / high
    """
    t = (task_kind or "").strip().lower()
    c = (complexity or "").strip().lower()

    # Tâches lourdes et critiques : décision, recherche multi-source, débogage profond, architecture
    pro_keywords = {
        "decision", "décision",
        "recherche multi-source", "multisource", "recherche",
        "debogage profond", "débogage profond", "debogage", "débogage", "debug",
        "architecture", "system_design"
    }
    if any(k in t for k in pro_keywords) or c in {"deep", "critique", "critical"}:
        return MODEL_PRO, EFFORT_HIGH

    # Tâches de rédaction et comparaison : flash / medium ou high
    writing_keywords = {"redaction", "rédaction", "comparaison", "draft", "synthèse", "synthese", "comparatif"}
    if any(k in t for k in writing_keywords):
        if c in {"high", "complexe", "eleve", "élevé"}:
            return MODEL_FLASH, EFFORT_HIGH
        return MODEL_FLASH, EFFORT_MEDIUM

    # Tâches légères ou rapides : flash / low
    light_keywords = {"leger", "léger", "light", "quick", "simple", "routine", "formatage"}
    if any(k in t for k in light_keywords) or c in {"low", "leger", "léger", "faible"}:
        return MODEL_FLASH, EFFORT_LOW

    # Repli par défaut selon complexité
    if c in {"high", "complexe", "eleve", "élevé"}:
        return MODEL_FLASH, EFFORT_HIGH
    return MODEL_FLASH, EFFORT_MEDIUM
