"""Shim racine pour model_router."""
from services.model_routing.model_router import (
    RoutingDecision,
    select_model
)

__all__ = ["RoutingDecision", "select_model"]
