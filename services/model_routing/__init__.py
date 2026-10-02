"""Package de routage intelligent, registre de modèles et résilience quota pour Antigravity CLI."""

from services.model_routing.model_registry import ModelInfo, ModelRegistry, model_registry
from services.model_routing.model_router import RoutingDecision, select_model
from services.model_routing.fallback_handler import (
    AntigravityQuotaExhaustedError,
    ModelCooldownManager,
    cooldown_manager,
    is_quota_error,
    execute_with_fallback
)
from services.model_routing.prompt_builder import (
    build_prompt,
    parse_agent_response,
    STANDARD_JSON_SCHEMA
)

__all__ = [
    "ModelInfo",
    "ModelRegistry",
    "model_registry",
    "RoutingDecision",
    "select_model",
    "AntigravityQuotaExhaustedError",
    "ModelCooldownManager",
    "cooldown_manager",
    "is_quota_error",
    "execute_with_fallback",
    "build_prompt",
    "parse_agent_response",
    "STANDARD_JSON_SCHEMA"
]
