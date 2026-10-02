"""Gestionnaire de repli résilient (Fallback Handler) en cas de quota dépassé.
Assure la cascade : Claude (CLI) -> Gemini (CLI) -> API Gemini Clé PAID (si autorisée) -> Erreur claire.
Gère les cooldowns par modèle, préserve les prompts et garantit l'inviolabilité de la clé payante.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

import config
from services.model_routing.model_registry import model_registry
from services.model_routing.model_router import RoutingDecision

logger = logging.getLogger("jarvis.fallback_handler")


class AntigravityQuotaExhaustedError(Exception):
    """Levée quand le quota est atteint sur les modèles CLI et API disponibles."""
    pass


class ModelCooldownManager:
    """Gestionnaire de mise en pause temporaire (cooldown) des modèles ayant épuisé leur quota."""

    def __init__(self, default_cooldown_seconds: float = 300.0):
        self.default_cooldown_seconds = default_cooldown_seconds
        self._cooldowns: Dict[str, float] = {}

    def mark_exhausted(self, model_name: str, duration: Optional[float] = None) -> None:
        """Place un modèle en cooldown pour une durée déterminée."""
        dur = duration or self.default_cooldown_seconds
        self._cooldowns[model_name] = time.time() + dur
        logger.warning(f"Modèle '{model_name}' placé en cooldown pour {dur}s suite à quota saturé.")

    def is_in_cooldown(self, model_name: str) -> bool:
        """Indique si un modèle est actuellement sous cooldown."""
        exp = self._cooldowns.get(model_name, 0.0)
        return time.time() < exp

    def reset_cooldown(self, model_name: str) -> None:
        """Réinitialise le cooldown d'un modèle."""
        self._cooldowns.pop(model_name, None)

    def clear(self) -> None:
        """Efface tous les cooldowns."""
        self._cooldowns.clear()


cooldown_manager = ModelCooldownManager()


def is_quota_error(error: Union[Exception, str, int, None]) -> bool:
    """Détecte de manière exhaustive si une erreur est due à un quota / rate limit (429 / RESOURCE_EXHAUSTED).
    Ne matche JAMAIS les erreurs de syntaxe, timeouts ou erreurs logicielles internes.
    """
    if error is None:
        return False

    if isinstance(error, AntigravityQuotaExhaustedError):
        return True

    # Code numérique
    if isinstance(error, int):
        return error in (429, 8)

    # Objets Exception
    if isinstance(error, Exception):
        code = getattr(error, "code", None) or getattr(error, "status_code", None)
        if code in (429, 8):
            return True
        err_str = f"{type(error).__name__}: {str(error)}".lower()
    else:
        err_str = str(error).lower()

    quota_keywords = [
        "429",
        "quota",
        "resource_exhausted",
        "resourceexhausted",
        "rate limit",
        "ratelimit",
        "too many requests",
        "limit exceeded",
        "quotaexceeded",
        "quota 5h",
        "exhausted"
    ]
    return any(k in err_str for k in quota_keywords)


async def execute_with_fallback(
    runner_fn: Callable[[str, Optional[str]], Coroutine[Any, Any, Any]],
    decision: RoutingDecision,
    prompt: str,
    on_fallback: Optional[Callable[[str, str, str], Coroutine[Any, Any, None]]] = None
) -> Any:
    """Exécute une tâche avec bascule automatique de modèle en cas d'erreur de quota.
    
    Args:
        runner_fn: Fonction asynchrone acceptant (model_name, effort) et exécutant la tâche.
        decision: Objet RoutingDecision contenant le modèle initial et la chaîne de repli.
        prompt: Le prompt complet à soumettre.
        on_fallback: Callback optionnel appelé lors d'une bascule : on_fallback(old_model, new_model, reason).
    """
    attempt_chain = [decision.model] + [m for m in decision.fallback_chain if m != decision.model]
    last_quota_error: Optional[Exception] = None

    for i, target_model in enumerate(attempt_chain):
        # 1. Vérifier si le modèle est en cooldown
        if cooldown_manager.is_in_cooldown(target_model):
            logger.info(f"Modèle '{target_model}' ignoré car actuellement en période de cooldown quota.")
            continue

        # 2. Cas spécifique de l'API Paid Gemini en bout de chaîne
        if target_model == "api_paid_gemini":
            if not config.is_paid_key_authorized():
                logger.warning("Repli API Paid requis mais clé payante non autorisée par Pierre. Arrêt de la chaîne.")
                raise AntigravityQuotaExhaustedError(
                    "Quota épuisé sur l'ensemble des modèles CLI disponibles. "
                    "L'accès à la clé payante n'étant pas autorisé dans vos réglages, la mission est suspendue."
                )

            effective_paid_key = config.get_effective_paid_key()
            if not effective_paid_key:
                raise AntigravityQuotaExhaustedError("Clé payante autorisée mais valeur introuvable dans la configuration.")

            logger.info("Bascule autorisée vers l'API directe Gemini avec clé payante.")
            if on_fallback and i > 0:
                await on_fallback(attempt_chain[i - 1], "Gemini API Direct (Clé Payante)", "Quota CLI épuisé")

            try:
                # Exécution via l'API directe payante
                from google import genai
                from google.genai import types

                paid_client = genai.Client(api_key=effective_paid_key)
                api_model = "gemini-2.5-pro" if decision.task_type in ("complex", "code") else "gemini-2.5-flash"
                resp = await paid_client.aio.models.generate_content(
                    model=api_model,
                    contents=prompt
                )
                output_text = resp.text or ""
                return {
                    "status": "completed",
                    "summary": output_text,
                    "model_used": f"Gemini API Direct ({api_model}) [PAID]",
                    "fallback_used": True
                }
            except Exception as paid_exc:
                if is_quota_error(paid_exc):
                    cooldown_manager.mark_exhausted("api_paid_gemini")
                    raise AntigravityQuotaExhaustedError("Quota saturé également sur l'API Gemini payante.") from paid_exc
                raise

        # 3. Modèle Antigravity CLI standard
        m_info = model_registry.get_model(target_model)
        supports_effort = m_info.supports_effort if m_info else False
        adapted_effort = decision.effort if supports_effort else None

        logger.info(f"Tentative d'exécution avec modèle: {target_model} (effort: {adapted_effort})")

        try:
            result = await runner_fn(target_model, adapted_effort)
            # Succès : réinitialiser le cooldown si existant
            cooldown_manager.reset_cooldown(target_model)
            return result
        except Exception as exc:
            if is_quota_error(exc):
                logger.warning(f"Quota saturé sur {target_model}. Erreur: {exc}")
                cooldown_manager.mark_exhausted(target_model)
                last_quota_error = exc

                # Notification de repli
                if i + 1 < len(attempt_chain):
                    next_model = attempt_chain[i + 1]
                    logger.info(f"Bascule de modèle : {target_model} -> {next_model}")
                    if on_fallback:
                        try:
                            await on_fallback(target_model, next_model, "Quota 5h / Rate limit dépassé")
                        except Exception as cb_err:
                            logger.debug(f"Erreur callback on_fallback: {cb_err}")
                continue
            else:
                # Erreur NON liée au quota : aucune bascule, on propage immédiatement
                logger.error(f"Erreur d'exécution hors-quota sur {target_model}: {exc}")
                raise

    # Si tous les modèles ont échoué sur quota
    raise AntigravityQuotaExhaustedError(
        f"Tous les modèles de la chaîne de repli ont atteint leur quota ({', '.join(attempt_chain)})."
    ) from last_quota_error
