"""Module de gouvernance et de contrôle d'accès aux clés API Gemini de J.A.R.V.I.S.

Politique stricte :
- GEMINI_API_KEY_FREE : gemini-3.8-live, gemini-3.8-live-extended-thinking,
  classification Tier 1 (gemini-3.8-flash, JSON, timeout 3.5s). Rien d'autre.
- GEMINI_API_KEY_PAID : clé de SECOURS uniquement, dans 2 cas précis :
  (a) Échec qualifié de la clé FREE (429, quota, erreur d'authentification, 5xx persistant après 1 nouvel essai).
  (b) Quota Antigravity CLI dépassé (agy renvoie une erreur de quota).
  Aucun autre usage. Aucun modèle Claude nulle part.
- La clé PAID n'est JAMAIS renvoyée sans consentement valide pour la tâche courante.
- Le consentement expire à la fin de la tâche (aucun consentement global silencieux).
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional, Tuple

import config


class PaidKeyConsentRequired(Exception):
    """Levée quand une opération nécessite la clé payante et qu'aucun consentement valide n'existe."""

    def __init__(
        self,
        reason: Literal["free_key_failure", "cli_quota_exceeded"],
        detail: str = "",
        purpose: str = "",
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.reason = reason
        self.detail = detail
        self.purpose = purpose
        self.task_id = task_id
        self.session_id = session_id
        self.extra = extra or {}
        msg = f"Consentement requis pour la clé payante [{reason}]: {detail}"
        super().__init__(msg)


@dataclass
class PaidConsent:
    session_id: Optional[str]
    task_id: Optional[str]
    reason: str
    scope: str = "this_task"
    granted_at: float = field(default_factory=time.time)


@dataclass
class PendingAction:
    name: str
    args: Dict[str, Any]
    reason: str
    detail: str
    purpose: str
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)


# Registre des consentements actifs (indexé par identifiant de tâche ou session)
_active_consents: Dict[str, PaidConsent] = {}

# Action en attente de confirmation de clé payante
_pending_action: Optional[PendingAction] = None


def _make_consent_key(session_id: Optional[str] = None, task_id: Optional[str] = None) -> str:
    if task_id:
        return f"task:{task_id}"
    if session_id:
        return f"session:{session_id}"
    return "current_task"


def grant_paid_consent(
    session_id: Optional[str] = None,
    reason: str = "",
    scope: str = "this_task",
    task_id: Optional[str] = None,
) -> bool:
    """Enregistre le consentement explicite de l'utilisateur pour l'usage de la clé payante."""
    key = _make_consent_key(session_id, task_id)
    _active_consents[key] = PaidConsent(
        session_id=session_id,
        task_id=task_id,
        reason=reason,
        scope=scope,
        granted_at=time.time(),
    )
    return True


def has_paid_consent(session_id: Optional[str] = None, task_id: Optional[str] = None) -> bool:
    """Vérifie si un consentement valide et non expiré existe pour cette tâche."""
    key = _make_consent_key(session_id, task_id)
    return key in _active_consents


def revoke_paid_consent(session_id: Optional[str] = None, task_id: Optional[str] = None) -> None:
    """Révoque immédiatement le consentement pour cette tâche."""
    key = _make_consent_key(session_id, task_id)
    _active_consents.pop(key, None)


def consume_paid_consent(session_id: Optional[str] = None, task_id: Optional[str] = None) -> None:
    """Consomme et expire le consentement à la fin de la tâche (garantit aucun consentement global)."""
    revoke_paid_consent(session_id, task_id)


def clear_all_consents() -> None:
    """Réinitialise tous les consentements (pour tests ou réinitialisation)."""
    _active_consents.clear()


def set_pending_action(
    name: str,
    args: Dict[str, Any],
    reason: str,
    detail: str,
    purpose: str,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Enregistre l'action dont l'exécution a été suspendue pour demande de consentement."""
    global _pending_action
    _pending_action = PendingAction(
        name=name,
        args=args,
        reason=reason,
        detail=detail,
        purpose=purpose,
        task_id=task_id,
        session_id=session_id,
        extra=extra or {},
    )


def get_pending_action() -> Optional[PendingAction]:
    """Retourne l'action en attente si présente."""
    return _pending_action


def clear_pending_action() -> None:
    """Efface l'action en attente."""
    global _pending_action
    _pending_action = None


def is_qualified_free_key_failure(error: Any, retry_count: int = 1) -> Tuple[bool, str]:
    """Détermine si l'échec de la clé gratuite qualifie pour une demande de clé payante :
    (a) 429, quota, resource_exhausted
    (b) erreur d'authentification (401, 403, api_key invalid)
    (c) 5xx persistant après au moins 1 nouvel essai (retry_count >= 1)
    """
    err_str = str(error).lower()

    # 1. Quota ou 429
    if any(k in err_str for k in ("429", "quota", "resource_exhausted", "resourceexhausted", "rate limit", "ratelimit", "too many requests")):
        return True, "Quota ou débit de la clé gratuite dépassé (429)"

    # 2. Authentification / Permissions
    if any(k in err_str for k in ("401", "403", "api_key_invalid", "unauthenticated", "permission_denied", "api key not valid")):
        return True, "Erreur d'authentification sur la clé gratuite"

    # 3. 5xx persistant après au moins 1 nouvel essai
    if retry_count >= 1 and any(k in err_str for k in ("500", "502", "503", "504", "internal server error", "service unavailable", "bad gateway")):
        return True, "Erreur serveur 5xx persistante sur la clé gratuite après nouvel essai"

    return False, ""


def get_key(
    purpose: str = "",
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    require_paid: bool = False,
    force_reason: Optional[Literal["free_key_failure", "cli_quota_exceeded"]] = None,
    failure_detail: str = "",
) -> str:
    """Retourne la clé API autorisée pour la finalité demandée.
    - Renvoie GEMINI_API_KEY_FREE par défaut.
    - Si un consentement valide existe pour cette tâche, renvoie GEMINI_API_KEY_PAID.
    - Si la clé payante est requise ou forcée sans consentement, lève PaidKeyConsentRequired.
    """
    if has_paid_consent(session_id=session_id, task_id=task_id):
        paid_key = getattr(config, "GEMINI_API_KEY_PAID", "")
        if paid_key:
            return paid_key

    if require_paid or force_reason:
        reason = force_reason or "free_key_failure"
        detail = failure_detail or ("Clé payante requise mais aucun consentement valide pour cette tâche")
        raise PaidKeyConsentRequired(
            reason=reason,
            detail=detail,
            purpose=purpose,
            task_id=task_id,
            session_id=session_id,
        )

    return getattr(config, "GEMINI_API_KEY_FREE", "") or getattr(config, "GEMINI_API_KEY", "")
