"""Utilitaires asyncio partagés pour J.A.R.V.I.S.

Ce module centralise les patterns asyncio safe pour éviter les warnings
"Task exception was never retrieved" qui peuvent déclencher des boucles SRE.
"""

import asyncio
import logging
from typing import Coroutine, Any, Optional

logger = logging.getLogger(__name__)


def fire_and_forget(
    coro: Coroutine,
    *,
    name: Optional[str] = None,
    log_errors: bool = True,
) -> asyncio.Task:
    """Lance une coroutine en fire-and-forget de manière sûre.

    Contrairement à `asyncio.create_task()` nu, cette fonction attache
    automatiquement un callback `add_done_callback` qui :
    - Absorbe l'exception si `log_errors=False`
    - La logue en WARNING si `log_errors=True` (sans propager vers asyncio)

    Cela évite le warning Python :
        "Task exception was never retrieved"
    ...qui peut déclencher à tort le SRE autonome de Jarvis.

    Usage :
        fire_and_forget(spotify_service.duck_volume(), name="spotify_duck")
        fire_and_forget(briefing_service.send_telegram_alert(...))

    Args:
        coro: La coroutine à exécuter en arrière-plan.
        name: Nom optionnel de la tâche asyncio (utile pour le débogage).
        log_errors: Si True, logue les exceptions en WARNING au lieu de les
                    ignorer silencieusement.

    Returns:
        L'objet asyncio.Task créé.
    """
    task = asyncio.create_task(coro, name=name)

    def _done_callback(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None and log_errors:
            task_name = t.get_name() or "fire_and_forget"
            logger.warning(
                "[async_utils] Exception silencieuse dans '%s': %s: %s",
                task_name,
                type(exc).__name__,
                exc,
            )

    task.add_done_callback(_done_callback)
    return task
