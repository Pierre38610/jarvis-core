"""Services Google Antigravity : exportations unifiées pour le routage cognitif,
les paliers d'exécution, la détection de quota et l'exécuteur agentique.
"""

from typing import Tuple

# Import et réexportation de l'implémentation racine google_antigravity
try:
    from google_antigravity import (
        AntigravityAgent,
        AntigravityQuotaExhaustedError,
        CognitiveConfig,
        TaskResult,
        find_antigravity_binary,
        is_stop_directive,
        resolve_antigravity_model,
        resolve_cognitive_tier,
        verify_antigravity_cli_ready,
    )
except ImportError:
    # Définition de sécurité si import direct
    class AntigravityQuotaExhaustedError(Exception):
        """Levée quand le quota 5h est atteint sur Antigravity CLI."""
        pass

# Import et réexportation des modèles et du runner agentique
from services.antigravity_models import (
    AGY_BINARY_PATH,
    IS_AGY_AVAILABLE,
    MODEL_FLASH,
    MODEL_PRO,
    VALID_EFFORTS,
    VALID_MODELS,
    choose_model_and_effort,
    validate_model_and_effort,
)
from services.agentic_runner import (
    AgentOutput,
    run_agentic,
)

__all__ = [
    "AntigravityAgent",
    "AntigravityQuotaExhaustedError",
    "CognitiveConfig",
    "TaskResult",
    "find_antigravity_binary",
    "is_stop_directive",
    "resolve_antigravity_model",
    "resolve_cognitive_tier",
    "verify_antigravity_cli_ready",
    "AGY_BINARY_PATH",
    "IS_AGY_AVAILABLE",
    "MODEL_FLASH",
    "MODEL_PRO",
    "VALID_EFFORTS",
    "VALID_MODELS",
    "choose_model_and_effort",
    "validate_model_and_effort",
    "AgentOutput",
    "run_agentic",
]


async def is_antigravity_cli_ready_for_session() -> bool:
    """Vérifie si le CLI Antigravity est prêt pour inclure les outils agentiques dans la session Live."""
    ready, _, _ = await verify_antigravity_cli_ready()
    return ready

