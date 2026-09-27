"""services/voice_injection_queue.py
File d'injection vocale FIFO avec priorités pour la session Gemini Live (Aoede).
Architecture & Invariants :
1. Niveaux de priorité stricts :
   - INTERRUPTION (1) : Arrêt d'urgence (stop_current_action), alertes quotas critiques.
   - TOOL_RESPONSE (2) : Réponse d'outil synchrone / résultat direct.
   - PROGRESS_MILESTONE (3) : Jalons vocaux intermédiaires des tâches de fond longues (> seuil).
   - PASSIVE_INFO (4) : Restitution passive ou notifications d'arrière-plan non urgentes.
2. Ordre FIFO déterministe au sein de chaque priorité via un compteur monotone.
3. Règle d'or de canal unique (élimination de tout doublon si action_key déjà résolue).
4. Verrou d'élocution anti-coupure (wait_until_speech_finished) et drainage du buffer audio.
5. Pause de respiration post-émission (0.35s) pour laisser le flux audio Live s'amorcer,
   garantissant qu'aucune tâche de fond concurrente n'émette en collision.
"""

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
import logging
import time
from typing import Any, Dict, Optional

from google.genai import types
import config

logger = logging.getLogger("JarvisVoiceQueue")


class InjectionPriority(IntEnum):
    """Niveaux de priorité pour la file d'injection vocale Live."""
    INTERRUPTION = 1       # Priorité absolue : arrêt d'urgence, alerte quota critique
    TOOL_RESPONSE = 2      # Réponse synchrone d'outil / résultat direct
    PROGRESS_MILESTONE = 3 # Jalon de progression intermédiaire
    PASSIVE_INFO = 4       # Information passive / notification de fond non urgente


@dataclass(order=True)
class InjectionItem:
    """Élément ordonné de la file d'injection vocale."""
    priority: int
    sequence: int
    text: str = field(compare=False)
    session: Any = field(default=None, compare=False)
    action_key: Optional[str] = field(default=None, compare=False)
    wait_if_speaking: bool = field(default=True, compare=False)
    drainage_delay: float = field(default=2.0, compare=False)
    future: Optional[asyncio.Future] = field(default=None, compare=False)
    created_at: float = field(default_factory=time.time, compare=False)
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)


class VoiceInjectionQueue:
    """Gestionnaire singleton de la file d'injection vocale avec priorités."""

    def __init__(self, post_delivery_delay: float = 0.35):
        self.post_delivery_delay = post_delivery_delay
        self._queue: Optional[asyncio.PriorityQueue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._counter: int = 0
        self._active_loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_delivering: bool = False
        self._stats: Dict[str, int] = {
            "enqueued": 0,
            "delivered": 0,
            "rejected_sync": 0,
            "failed": 0
        }

    def _ensure_worker(self) -> None:
        """Garantit que la file et le worker d'arrière-plan sont rattachés à la boucle courante."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        if self._active_loop != loop or self._queue is None or self._worker_task is None or self._worker_task.done():
            self._active_loop = loop
            self._queue = asyncio.PriorityQueue()
            self._worker_task = asyncio.create_task(
                self._worker_loop(),
                name="voice_injection_worker"
            )

    async def _worker_loop(self) -> None:
        """Boucle consommatrice séquentielle et déterministe."""
        while True:
            try:
                item: InjectionItem = await self._queue.get()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VoiceInjectionQueue] Erreur dépilement: {e}")
                await asyncio.sleep(0.1)
                continue

            try:
                self._is_delivering = True
                success = await self._deliver_item(item)
                if item.future and not item.future.done():
                    item.future.set_result(success)
                if success:
                    self._stats["delivered"] += 1
                else:
                    self._stats["failed"] += 1
            except Exception as exc:
                logger.error(f"[VoiceInjectionQueue] Exception livraison vocal: {exc}", exc_info=True)
                if item.future and not item.future.done():
                    item.future.set_result(False)
                self._stats["failed"] += 1
            finally:
                self._is_delivering = False
                self._queue.task_done()

    async def _deliver_item(self, item: InjectionItem) -> bool:
        """Livre un élément à la session Gemini Live en respectant les verrous et règles de canal."""
        from core.shared_state import (
            active_task_controller,
            is_action_sync_completed,
            wait_until_speech_finished
        )

        session = item.session or active_task_controller.get("live_session")
        if not session:
            logger.warning("[VoiceInjectionQueue] Aucune session Live active, injection annulée.")
            return False

        # Règle d'or de canal unique
        if item.action_key and is_action_sync_completed(item.action_key):
            logger.info(
                f"[VoiceInjectionQueue Canal Unique] Action '{item.action_key}' déjà résolue "
                "de manière synchrone via tool_response. Injection annulée pour éliminer tout bégaiement."
            )
            self._stats["rejected_sync"] += 1
            return False

        # Verrou d'élocution anti-coupure (si demandé)
        if item.wait_if_speaking:
            timeout = 5.0 if item.priority == InjectionPriority.INTERRUPTION else 15.0
            await wait_until_speech_finished(timeout=timeout, buffer_drainage_delay=item.drainage_delay)

        try:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=item.text)]),
                turn_complete=True
            )
            # Pause de respiration et amorçage audio pour que les premiers paquets
            # de Aoede activent speaking_active avant que le prochain item de la file ne soit évalué
            if self.post_delivery_delay > 0:
                await asyncio.sleep(self.post_delivery_delay)
            return True
        except Exception as e:
            logger.error(f"[VoiceInjectionQueue] Erreur session.send_client_content: {e}")
            return False

    async def enqueue(
        self,
        text: str,
        priority: InjectionPriority | int = InjectionPriority.PASSIVE_INFO,
        session: Any = None,
        action_key: Optional[str] = None,
        wait_if_speaking: bool = True,
        drainage_delay: float = 2.0,
        wait_for_completion: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Enfile un message dans la file d'injection prioritaire.
        Si wait_for_completion=True, attend la fin effective de la livraison et retourne le booléen.
        """
        if not text or not text.strip():
            return False

        from core.shared_state import is_action_sync_completed
        if action_key and is_action_sync_completed(action_key):
            logger.info(f"[VoiceInjectionQueue] Action '{action_key}' déjà synchronisée. Ignorée dès l'enfilage.")
            self._stats["rejected_sync"] += 1
            return False

        self._ensure_worker()
        self._counter += 1
        self._stats["enqueued"] += 1

        p_val = int(priority)
        fut = asyncio.get_running_loop().create_future() if wait_for_completion else None

        item = InjectionItem(
            priority=p_val,
            sequence=self._counter,
            text=text,
            session=session,
            action_key=action_key,
            wait_if_speaking=wait_if_speaking,
            drainage_delay=drainage_delay,
            future=fut,
            metadata=metadata or {}
        )

        await self._queue.put(item)

        if wait_for_completion and fut:
            try:
                return await fut
            except Exception:
                return False

        return True

    def should_emit_milestones(self, estimated_duration: float = 0.0) -> bool:
        """Détermine si une tâche doit émettre des jalons intermédiaires selon le seuil configuré."""
        threshold = getattr(config, "VOCAL_MILESTONE_THRESHOLD_SECONDS", 90.0)
        return estimated_duration >= threshold

    async def emit_interruption(self, text: str, session: Any = None, wait_if_speaking: bool = False) -> bool:
        """Injecte une consigne d'interruption prioritaire immédiate."""
        return await self.enqueue(
            text=text,
            priority=InjectionPriority.INTERRUPTION,
            session=session,
            wait_if_speaking=wait_if_speaking,
            drainage_delay=0.5,
            wait_for_completion=True
        )

    async def emit_tool_response(self, text: str, action_key: Optional[str] = None, session: Any = None) -> bool:
        """Injecte une réponse d'outil synchrone."""
        return await self.enqueue(
            text=text,
            priority=InjectionPriority.TOOL_RESPONSE,
            session=session,
            action_key=action_key,
            wait_if_speaking=True,
            drainage_delay=1.5,
            wait_for_completion=True
        )

    async def emit_milestone(
        self,
        text: str,
        action_key: Optional[str] = None,
        drainage_delay: float = 1.5,
        session: Any = None,
        wait_for_completion: bool = False
    ) -> bool:
        """Injecte un jalon de progression intermédiaire pour une tâche longue."""
        return await self.enqueue(
            text=text,
            priority=InjectionPriority.PROGRESS_MILESTONE,
            session=session,
            action_key=action_key,
            wait_if_speaking=True,
            drainage_delay=drainage_delay,
            wait_for_completion=wait_for_completion
        )

    async def emit_passive_info(
        self,
        text: str,
        action_key: Optional[str] = None,
        session: Any = None,
        wait_for_completion: bool = False
    ) -> bool:
        """Injecte une notification ou information passive."""
        return await self.enqueue(
            text=text,
            priority=InjectionPriority.PASSIVE_INFO,
            session=session,
            action_key=action_key,
            wait_if_speaking=True,
            drainage_delay=2.0,
            wait_for_completion=wait_for_completion
        )

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les métriques de la file."""
        q_size = self._queue.qsize() if self._queue else 0
        return {
            **self._stats,
            "queue_size": q_size,
            "is_delivering": self._is_delivering
        }

    def clear(self) -> None:
        """Vide la file d'attente (par exemple lors d'un arrêt d'urgence)."""
        if self._queue:
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    if item.future and not item.future.done():
                        item.future.cancel()
                    self._queue.task_done()
                except Exception:
                    break


# Singleton global
voice_injection_queue = VoiceInjectionQueue()
