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
        self._last_milestone_timestamps: Dict[str, float] = {}
        self._stats: Dict[str, int] = {
            "enqueued": 0,
            "delivered": 0,
            "rejected_sync": 0,
            "coalesced_milestones": 0,
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
        """Boucle consommatrice séquentielle et déterministe avec coalescence des TOOL_RESPONSE."""
        while True:
            try:
                item: InjectionItem = await self._queue.get()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VoiceInjectionQueue] Erreur dépilement: {e}")
                await asyncio.sleep(0.1)
                continue

            all_items = [item]
            # Coalescence : si plusieurs résultats d'outils TOOL_RESPONSE sont en attente, les fusionner en un seul tour
            if item.priority == InjectionPriority.TOOL_RESPONSE and self._queue and not self._queue.empty():
                extra_tools = []
                other_items = []
                while not self._queue.empty():
                    try:
                        cand = self._queue.get_nowait()
                        self._queue.task_done()
                        if cand.priority == InjectionPriority.TOOL_RESPONSE:
                            extra_tools.append(cand)
                        else:
                            other_items.append(cand)
                    except Exception:
                        break
                for o in other_items:
                    await self._queue.put(o)
                if extra_tools:
                    all_items.extend(extra_tools)
                    merged_texts = [it.text.strip() for it in all_items if it.text.strip()]
                    item.text = "\n\n".join(merged_texts)
                    logger.info(f"[VoiceInjectionQueue] {len(all_items)} résultats d'outils fusionnés en un seul message.")

            try:
                self._is_delivering = True
                success = await self._deliver_item(item)
                for it in all_items:
                    if it.future and not it.future.done():
                        it.future.set_result(success)
                if success:
                    self._stats["delivered"] += len(all_items)
                else:
                    self._stats["failed"] += len(all_items)
            except Exception as exc:
                logger.error(f"[VoiceInjectionQueue] Exception livraison vocal: {exc}", exc_info=True)
                for it in all_items:
                    if it.future and not it.future.done():
                        it.future.set_result(False)
                self._stats["failed"] += len(all_items)
            finally:
                self._is_delivering = False
                self._queue.task_done()

    async def _deliver_item(self, item: InjectionItem) -> bool:
        """Livre un élément à la session Gemini Live en respectant la machine à états de la parole."""
        from core.shared_state import (
            active_task_controller,
            is_action_sync_completed,
            wait_until_speech_finished,
            get_speech_state,
            SpeechState,
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

        # Règle unique : aucune injection de priorité 2, 3, 4 ne part si SpeechState != IDLE
        if item.priority in (InjectionPriority.TOOL_RESPONSE, InjectionPriority.PROGRESS_MILESTONE, InjectionPriority.PASSIVE_INFO):
            timeout = 15.0
            # Attente active de SpeechState == IDLE
            await wait_until_speech_finished(timeout=timeout, buffer_drainage_delay=max(0.35, item.drainage_delay))

            # Si l'utilisateur est en train de parler
            if get_speech_state() == SpeechState.USER_SPEAKING:
                if item.priority == InjectionPriority.PROGRESS_MILESTONE:
                    logger.info("[VoiceInjectionQueue] Jalon de progression abandonné : utilisateur en train de parler.")
                    self._stats["coalesced_milestones"] += 1
                    return False
                # Pour les réponses d'outils et infos passives, attendre que l'utilisateur finisse
                await wait_until_speech_finished(timeout=timeout, buffer_drainage_delay=0.35)

            # Sas de respiration acoustique strict : 350 ms après la fin réelle du playback client
            last_pb = active_task_controller.get("last_playback_finished_time", 0.0)
            if last_pb > 0:
                elapsed = time.time() - last_pb
                if elapsed < 0.35:
                    await asyncio.sleep(0.35 - elapsed)
        else:
            # Priorité INTERRUPTION (1) : réservée pour arrêt d'urgence ou alerte critique
            if get_speech_state() == SpeechState.MODEL_SPEAKING:
                from services.metrics_service import metrics_service
                is_user_stop = (
                    item.metadata.get("source") == "user"
                    or any(k in item.text.lower() for k in ("stop", "arrête", "arrete", "annule"))
                )
                if is_user_stop:
                    metrics_service.record_speech_cut("user_barge_in", details="Arrêt d'urgence prioritaire utilisateur")
                else:
                    metrics_service.record_speech_cut("internal", details=f"Interruption prioritaire interne: {item.text[:50]}")

        try:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part.from_text(text=item.text)]),
                turn_complete=True
            )
            # Pause de respiration et amorçage audio
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
        Applique les règles de canal unique, coalescence de jalons (20s) et rejet si l'utilisateur parle.
        """
        if not text or not text.strip():
            return False

        from core.shared_state import is_action_sync_completed, get_speech_state, SpeechState
        if action_key and is_action_sync_completed(action_key):
            logger.info(f"[VoiceInjectionQueue] Action '{action_key}' déjà synchronisée. Ignorée dès l'enfilage.")
            self._stats["rejected_sync"] += 1
            return False

        p_val = int(priority)

        # Règle 5 : Coalescence des PROGRESS_MILESTONE
        if p_val == InjectionPriority.PROGRESS_MILESTONE:
            # Jamais si l'utilisateur est en train de parler
            if get_speech_state() == SpeechState.USER_SPEAKING:
                logger.info("[VoiceInjectionQueue] Jalon refusé : l'utilisateur est en train de parler.")
                self._stats["coalesced_milestones"] += 1
                return False

            task_key = action_key or (metadata.get("task_id") if metadata else None)
            if task_key:
                now = time.time()
                last_t = self._last_milestone_timestamps.get(task_key, 0.0)
                if now - last_t < 20.0:
                    logger.info(f"[VoiceInjectionQueue] Jalon coalescé pour tâche '{task_key}' (< 20s depuis le précédent).")
                    self._stats["coalesced_milestones"] += 1
                    return False
                self._last_milestone_timestamps[task_key] = now

        self._ensure_worker()
        self._counter += 1
        self._stats["enqueued"] += 1

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

    def reset(self) -> None:
        """Réinitialise complètement la file pour les tests ou la reconnexion."""
        self.clear()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self._worker_task = None
        self._queue = None
        self._active_loop = None
        self._last_milestone_timestamps.clear()
        self._counter = 0
        self._is_delivering = False


# Singleton global
voice_injection_queue = VoiceInjectionQueue()
