"""Shim racine pour model_registry."""
from services.model_routing.model_registry import (
    ModelInfo,
    ModelRegistry,
    model_registry,
    DEFAULT_MODELS
)

__all__ = ["ModelInfo", "ModelRegistry", "model_registry", "DEFAULT_MODELS"]
