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

from services.search_router import (
    SearchRoutingDecision,
    route_search_intent,
    acquire_search_lock,
    release_search_lock,
    is_search_in_progress,
)

__all__ = [
    "ModelInfo",
    "ModelRegistry",
    "model_registry",
    "RoutingDecision",
    "select_model",
    "SearchRoutingDecision",
    "route_search_intent",
    "acquire_search_lock",
    "release_search_lock",
    "is_search_in_progress",
    "AntigravityQuotaExhaustedError",
    "ModelCooldownManager",
    "cooldown_manager",
    "is_quota_error",
    "execute_with_fallback",
    "build_prompt",
    "parse_agent_response",
    "STANDARD_JSON_SCHEMA"
]
