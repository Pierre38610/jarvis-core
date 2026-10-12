"""Shim racine pour fallback_handler."""
from services.model_routing.fallback_handler import (
    AntigravityQuotaExhaustedError,
    ModelCooldownManager,
    cooldown_manager,
    is_quota_error,
    execute_with_fallback
)

__all__ = [
    "AntigravityQuotaExhaustedError",
    "ModelCooldownManager",
    "cooldown_manager",
    "is_quota_error",
    "execute_with_fallback"
]
