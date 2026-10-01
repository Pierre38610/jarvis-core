"""services/llm_router.py
Routeur LLM unifié pour J.A.R.V.I.S.

Règles de gouvernance :
- Les deux modèles Live (standard: gemini-3.8-live, thinking: gemini-3.8-live-extended-thinking)
  utilisent impérativement la clé FREE.
- La clé PAID n'intervient qu'en secours qualifié, via key_gate (avec consentement vocal obligatoire).
- Intégration transparente de LiveModePolicy pour l'arbitrage voice_mode et needs_agentic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import config
from services.live_mode_policy import (
    LiveModePolicy,
    get_policy,
    decide as policy_decide,
    VOICE_MODE_STANDARD,
    VOICE_MODE_THINKING,
    LIVE_MODEL_STANDARD,
    LIVE_MODEL_THINKING,
)
from services.key_gate import (
    get_key,
    has_paid_consent,
    PaidKeyConsentRequired,
    is_qualified_free_key_failure,
)

logger = logging.getLogger("jarvis.llm_router")


def get_live_model_and_key(
    voice_mode: str = VOICE_MODE_STANDARD,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    require_paid: bool = False,
    force_reason: Optional[str] = None,
    failure_detail: str = "",
) -> Tuple[str, str]:
    """Sélectionne le modèle Live et récupère la clé API conforme à la gouvernance.

    - voice_mode == "thinking" -> "gemini-3.8-live-extended-thinking"
    - voice_mode == "standard" -> "gemini-3.8-live"
    - Clé : FREE par défaut. PAID uniquement en secours si le consentement est validé.
    """
    model_name = (
        LIVE_MODEL_THINKING
        if voice_mode == VOICE_MODE_THINKING
        else LIVE_MODEL_STANDARD
    )

    api_key = get_key(
        purpose=f"live_{voice_mode}",
        session_id=session_id,
        task_id=task_id,
        require_paid=require_paid,
        force_reason=force_reason,
        failure_detail=failure_detail,
    )

    return model_name, api_key


class LLMRouter:
    """Routeur central des interactions LLM et sessions Gemini Live."""

    def __init__(self, policy: Optional[LiveModePolicy] = None):
        self.policy = policy or LiveModePolicy()

    def decide(
        self,
        transcript: str = "",
        plan_active: Any = 0,
        recent_failures: int = 0,
        tier_hint: int = 1,
        force_agentic: Optional[bool] = None,
        task_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Évalue la politique de mode Live pour le tour courant."""
        return self.policy.decide(
            transcript=transcript,
            plan_active=plan_active,
            recent_failures=recent_failures,
            tier_hint=tier_hint,
            force_agentic=force_agentic,
            task_kind=task_kind,
        )

    def route(
        self,
        transcript: str = "",
        plan_active: Any = 0,
        recent_failures: int = 0,
        tier_hint: int = 1,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        require_paid: bool = False,
        force_reason: Optional[str] = None,
        failure_detail: str = "",
        force_agentic: Optional[bool] = None,
        task_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calcule la route complète : mode vocal, modèle Live, clé API et besoin agentique."""
        decision = self.decide(
            transcript=transcript,
            plan_active=plan_active,
            recent_failures=recent_failures,
            tier_hint=tier_hint,
            force_agentic=force_agentic,
            task_kind=task_kind,
        )

        voice_mode = decision["voice_mode"]
        model_name, api_key = get_live_model_and_key(
            voice_mode=voice_mode,
            session_id=session_id,
            task_id=task_id,
            require_paid=require_paid,
            force_reason=force_reason,
            failure_detail=failure_detail,
        )

        return {
            "voice_mode": voice_mode,
            "model_name": model_name,
            "api_key": api_key,
            "needs_agentic": decision["needs_agentic"],
            "task_kind": decision["task_kind"],
            "reason": decision["reason"],
        }


# Router singleton par défaut
default_router = LLMRouter()


def route(
    transcript: str = "",
    plan_active: Any = 0,
    recent_failures: int = 0,
    tier_hint: int = 1,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    require_paid: bool = False,
    force_reason: Optional[str] = None,
    failure_detail: str = "",
    force_agentic: Optional[bool] = None,
    task_kind: Optional[str] = None,
) -> Dict[str, Any]:
    """Point d'entrée fonctionnel du routeur LLM."""
    policy = get_policy(session_id)
    router = LLMRouter(policy=policy)
    return router.route(
        transcript=transcript,
        plan_active=plan_active,
        recent_failures=recent_failures,
        tier_hint=tier_hint,
        session_id=session_id,
        task_id=task_id,
        require_paid=require_paid,
        force_reason=force_reason,
        failure_detail=failure_detail,
        force_agentic=force_agentic,
        task_kind=task_kind,
    )


def decide(
    transcript: str = "",
    plan_active: Any = 0,
    recent_failures: int = 0,
    tier_hint: int = 1,
    force_agentic: Optional[bool] = None,
    task_kind: Optional[str] = None,
    session_id: Optional[str] = None,
    speech_state: Any = None,
) -> Dict[str, Any]:
    """Exposition directe de la décision de mode pour commodité d'import."""
    return policy_decide(
        transcript=transcript,
        plan_active=plan_active,
        recent_failures=recent_failures,
        tier_hint=tier_hint,
        force_agentic=force_agentic,
        task_kind=task_kind,
        session_id=session_id,
        speech_state=speech_state,
    )


def resolve_live_fallback(
    current_model: str,
    error: Optional[Any] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    standard_already_failed: bool = False,
) -> Dict[str, Any]:
    """Gère la cascade de repli en direct :
    1. Échec de la clé FREE sur modèle thinking : repli d'abord sur Live standard FREE.
    2. Si le standard FREE échoue aussi : PaidKeyConsentRequired("free_key_failure").
    3. Si consentement accordé : bascule sur Live avec clé PAID.
    """
    is_thinking = "extended-thinking" in (current_model or "")

    # Étape 1 : Si on était en thinking avec clé FREE et que le standard n'a pas encore échoué
    if is_thinking and not standard_already_failed:
        free_key = get_key(
            purpose="live_standard_fallback",
            session_id=session_id,
            task_id=task_id,
            require_paid=False,
        )
        return {
            "model_name": LIVE_MODEL_STANDARD,
            "voice_mode": VOICE_MODE_STANDARD,
            "api_key": free_key,
            "is_paid": False,
            "action": "fallback_to_standard_free",
            "message": "Repli sur Gemini Live standard en clé gratuite.",
        }

    # Étape 2 : Le standard FREE a échoué (ou on y était déjà) -> exige consentement payant
    if not has_paid_consent(session_id=session_id, task_id=task_id):
        raise PaidKeyConsentRequired(
            reason="free_key_failure",
            detail=f"Échec de la clé gratuite sur {current_model} (standard FREE indisponible)",
            purpose="live_standard_paid",
            session_id=session_id,
            task_id=task_id,
        )

    # Étape 3 : Consentement présent -> clé payante autorisée
    paid_key = get_key(
        purpose="live_paid_consent",
        session_id=session_id,
        task_id=task_id,
        require_paid=True,
    )
    return {
        "model_name": LIVE_MODEL_STANDARD,
        "voice_mode": VOICE_MODE_STANDARD,
        "api_key": paid_key,
        "is_paid": True,
        "action": "fallback_to_standard_paid",
        "message": "Bascule sur Gemini Live standard avec clé payante autorisée.",
    }

