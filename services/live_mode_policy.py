"""services/live_mode_policy.py
Politique de sélection de mode pour la voix Gemini Live de J.A.R.V.I.S.

Règles du mode thinking (dans l'ordre) :
1. Demande explicite (« vite » → standard ; « réfléchis bien », « prends ton temps », « en détail » → thinking) ;
2. Plan actif ≥ 3 étapes ;
3. 2 échecs d'outil consécutifs ;
4. tier_hint ≥ 2 ;
5. Sinon standard.

Hystérésis :
- Au moins 2 tours en thinking une fois activé ;
- Retour en standard après 3 tours consécutifs tier 1 sans plan actif.
- Demande explicite « vite » réinitialise immédiatement vers standard.

Indépendance :
- La décision du mode vocal (voice_mode: standard|thinking) et le besoin
  d'exécution agentique en tâche de fond (needs_agentic: bool) sont totalement indépendants.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional, Tuple, Union, Literal

VOICE_MODE_STANDARD: Literal["standard"] = "standard"
VOICE_MODE_THINKING: Literal["thinking"] = "thinking"

LIVE_MODEL_STANDARD = "gemini-3.8-live"
LIVE_MODEL_THINKING = "gemini-3.8-live-extended-thinking"


def _normalize_text(text: str) -> str:
    """Normalise une chaîne de texte (minuscules, sans accents) pour un appariement robuste."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    cleaned = "".join(c for c in norm if not unicodedata.combining(c))
    return cleaned.lower().strip()


def _count_plan_steps(plan_active: Any) -> int:
    """Convertit n'importe quelle représentation de plan_active en nombre d'étapes."""
    if not plan_active:
        return 0
    if isinstance(plan_active, bool):
        return 1 if plan_active else 0
    if isinstance(plan_active, (int, float)):
        return max(0, int(plan_active))
    if isinstance(plan_active, (list, tuple, set)):
        return len(plan_active)
    if isinstance(plan_active, dict):
        steps = plan_active.get("steps")
        if isinstance(steps, (list, tuple, set)):
            return len(steps)
        return len(plan_active)
    return 0


def _detect_agentic_need(
    transcript: str,
    force_agentic: Optional[bool] = None,
    task_kind: Optional[str] = None,
) -> Tuple[bool, str]:
    """Détermine indépendamment si la requête requiert une exécution agentique / tâche de fond."""
    if force_agentic is not None:
        kind = task_kind or ("agentic_task" if force_agentic else "conversation")
        return bool(force_agentic), kind

    if task_kind is not None and task_kind != "":
        tk = task_kind.strip().lower()
        non_agentic = {"conversation", "chat", "vocal_chat", "direct_answer", "general", "quick_query"}
        return tk not in non_agentic, task_kind

    norm = _normalize_text(transcript)
    if not norm:
        return False, "conversation"

    # Missions agentiques Stark & délégations lourdes
    if any(k in norm for k in ["deep research", "recherche approfondie", "investigation", "slides", "veille tech"]):
        return True, "deep_research"
    if any(k in norm for k in ["tableur", "excel", "spreadsheet", "modele financier", "modele comptable"]):
        return True, "spreadsheet_modeler"
    if any(k in norm for k in ["system healing", "auto-reparation", "repare le systeme", "diagnostic", "corrige le bug"]):
        return True, "system_healing"
    if any(k in norm for k in ["brouillon email", "redige un mail", "redige l'email", "envoie un mail"]):
        return True, "email_drafting"
    if any(k in norm for k in ["optimise le trajet", "reservation train", "comparateur vol", "billet train", "sncf"]):
        return True, "transport_optimizer"
    if any(k in norm for k in ["fiche de lecture", "ebook", "kindle", "resume du livre"]):
        return True, "book_curation"
    if any(k in norm for k in ["doc sync", "doc_sync", "documentation architecture"]):
        return True, "doc_sync"
    if any(k in norm for k in ["consolidation memoire", "knowledge graph"]):
        return True, "memory_consolidation"
    if any(k in norm for k in ["lance l'agent", "agentic", "antigravity", "tache de fond", "en arriere-plan"]):
        return True, "agentic_mission"

    return False, "conversation"


class LiveModePolicy:
    """Gère la politique de bascule de mode pour Gemini Live avec suivi d'hystérésis."""

    def __init__(self) -> None:
        self.current_mode: str = VOICE_MODE_STANDARD
        self.thinking_turns: int = 0
        self.consecutive_tier1_without_plan: int = 0
        self.pending_switch: Optional[str] = None
        self.pending_switch_meta: Dict[str, Any] = {}

    def reset(self) -> None:
        """Réinitialise l'état interne de la politique."""
        self.current_mode = VOICE_MODE_STANDARD
        self.thinking_turns = 0
        self.consecutive_tier1_without_plan = 0
        self.pending_switch = None
        self.pending_switch_meta = {}

    def apply_deferred_switch(self) -> Optional[str]:
        """Applique la bascule différée lorsque la parole est redevenue IDLE."""
        if self.pending_switch:
            new_mode = self.pending_switch
            self.current_mode = new_mode
            self.pending_switch = None
            if new_mode == VOICE_MODE_THINKING:
                self.thinking_turns = max(1, self.thinking_turns)
            return new_mode
        return None

    def decide(
        self,
        transcript: str = "",
        plan_active: Any = 0,
        recent_failures: int = 0,
        tier_hint: int = 1,
        force_agentic: Optional[bool] = None,
        task_kind: Optional[str] = None,
        speech_state: Any = None,
    ) -> Dict[str, Any]:
        """Décide du mode vocal et de l'activation agentique selon les règles ordonnées et l'hystérésis.

        Retourne un dictionnaire :
        {
            "voice_mode": "standard" | "thinking",
            "needs_agentic": bool,
            "task_kind": str,
            "reason": str,
            "switch_source": "user_demand" | "policy",
            "announcement_phrase": str,
            "switch_deferred": bool,
            "target_mode": str,
        }
        """
        norm = _normalize_text(transcript)
        plan_steps = _count_plan_steps(plan_active)

        # ─── 1. DÉCISION DU MODE VOCAL CIBLE (TARGET_MODE) ───
        target_mode: str
        reason: str
        switch_source: str = "policy"
        rule_fired: int = 5

        # Règle 1 : Demande explicite
        is_explicit_standard = bool(re.search(r"\b(vite|rapide|rapidement|en vitesse|fais vite|sois bref|bref|court)\b", norm))
        is_explicit_thinking = bool(re.search(
            r"\b(reflechis bien|prends ton temps|en detail|analyse en detail|pose-toi|pose toi)\b", norm
        ))

        if is_explicit_standard:
            rule_fired = 1
            target_mode = VOICE_MODE_STANDARD
            switch_source = "user_demand"
            reason = "Demande explicite: passage en standard (vite/rapide)"

        elif is_explicit_thinking:
            rule_fired = 1
            target_mode = VOICE_MODE_THINKING
            switch_source = "user_demand"
            reason = "Demande explicite: passage en thinking (réfléchis bien / prends ton temps / en détail)"

        # Règle 2 : Plan actif ≥ 3 étapes
        elif plan_steps >= 3:
            rule_fired = 2
            target_mode = VOICE_MODE_THINKING
            switch_source = "policy"
            reason = f"Plan actif complexe ({plan_steps} étapes >= 3)"

        # Règle 3 : 2 échecs d'outil consécutifs
        elif recent_failures >= 2:
            rule_fired = 3
            target_mode = VOICE_MODE_THINKING
            switch_source = "policy"
            reason = f"Échecs consécutifs d'outils ({recent_failures} >= 2)"

        # Règle 4 : tier_hint ≥ 2
        elif tier_hint >= 2:
            rule_fired = 4
            target_mode = VOICE_MODE_THINKING
            switch_source = "policy"
            reason = f"Complexité cognitive élevée (tier_hint={tier_hint} >= 2)"

        # Règle 5 : Sinon standard, soumis à l'hystérésis
        else:
            rule_fired = 5
            if self.current_mode == VOICE_MODE_THINKING:
                is_tier1_without_plan = (tier_hint <= 1 and plan_steps == 0)
                next_tier1_count = (self.consecutive_tier1_without_plan + 1) if is_tier1_without_plan else 0

                # Hystérésis : au moins 2 tours en thinking ; retour en standard après 3 tours tier 1 sans plan
                can_return_to_standard = (
                    self.thinking_turns >= 2 and next_tier1_count >= 3
                )

                if can_return_to_standard:
                    target_mode = VOICE_MODE_STANDARD
                    switch_source = "policy"
                    reason = "Retour en standard après 3 tours tier 1 sans plan actif"
                else:
                    target_mode = VOICE_MODE_THINKING
                    switch_source = "policy"
                    if self.thinking_turns < 2:
                        reason = f"Maintien thinking par hystérésis (minimum 2 tours requis, tour {self.thinking_turns + 1})"
                    else:
                        reason = f"Maintien thinking par hystérésis ({next_tier1_count}/3 tours tier 1 sans plan)"
            else:
                target_mode = VOICE_MODE_STANDARD
                switch_source = "policy"
                reason = "Mode standard (tier 1, pas de déclencheur thinking)"

        # ─── VÉRIFICATION DE LA PAROLE (SpeechState IDLE) ───
        is_speaking = False
        if speech_state is not None:
            st_str = str(speech_state).lower()
            is_speaking = "speaking" in st_str or "model_speaking" in st_str

        # Phrase courte uniquement si bascule vers thinking issue de la politique (pas demande explicite)
        announcement_phrase = ""
        mode_changing = (target_mode != self.current_mode)
        if mode_changing and target_mode == VOICE_MODE_THINKING and switch_source == "policy":
            announcement_phrase = "Je passe en mode réflexion."

        switch_deferred = False
        if mode_changing and is_speaking:
            switch_deferred = True
            self.pending_switch = target_mode
            self.pending_switch_meta = {
                "target_mode": target_mode,
                "reason": reason,
                "switch_source": switch_source,
                "announcement_phrase": announcement_phrase,
            }
            voice_mode = self.current_mode
        else:
            # Application de la décision
            switch_deferred = False
            self.pending_switch = None
            self.pending_switch_meta = {}
            self.current_mode = target_mode
            voice_mode = target_mode

            if target_mode == VOICE_MODE_THINKING:
                self.thinking_turns += 1
                if rule_fired == 5:
                    self.consecutive_tier1_without_plan = next_tier1_count
                else:
                    self.consecutive_tier1_without_plan = 0
            else:
                self.thinking_turns = 0
                self.consecutive_tier1_without_plan = 0

        # ─── 2. DÉCISION AGENTIQUE INDÉPENDANTE (NEEDS_AGENTIC) ───
        needs_agentic, detected_task_kind = _detect_agentic_need(
            transcript, force_agentic=force_agentic, task_kind=task_kind
        )

        return {
            "voice_mode": voice_mode,
            "target_mode": target_mode,
            "needs_agentic": needs_agentic,
            "task_kind": detected_task_kind,
            "reason": reason,
            "switch_source": switch_source,
            "announcement_phrase": announcement_phrase,
            "switch_deferred": switch_deferred,
        }


# Instance par défaut et registre de sessions
_default_policy = LiveModePolicy()
_session_policies: Dict[str, LiveModePolicy] = {}


def get_policy(session_id: Optional[str] = None) -> LiveModePolicy:
    """Retourne la politique liée à une session ou l'instance par défaut."""
    if not session_id:
        return _default_policy
    if session_id not in _session_policies:
        _session_policies[session_id] = LiveModePolicy()
    return _session_policies[session_id]


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
    """Point d'entrée modulaire pour l'évaluation de la politique Live."""
    policy = get_policy(session_id)
    return policy.decide(
        transcript=transcript,
        plan_active=plan_active,
        recent_failures=recent_failures,
        tier_hint=tier_hint,
        force_agentic=force_agentic,
        task_kind=task_kind,
        speech_state=speech_state,
    )


async def log_tier_routing_decision(
    query_text: str,
    decision: Dict[str, Any],
    latency_ms: float = 0.0,
    override_manuel: bool = False,
    fallback_occurred: bool = False,
) -> bool:
    """Journalise chaque décision dans PostgreSQL tier_routing_log sans bloquer."""
    try:
        from services.memory import memory_service
        chosen_tier = 2 if decision.get("voice_mode") == VOICE_MODE_THINKING else 1
        meta = {
            "voice_mode": decision.get("voice_mode"),
            "target_mode": decision.get("target_mode"),
            "needs_agentic": decision.get("needs_agentic"),
            "task_kind": decision.get("task_kind"),
            "switch_source": decision.get("switch_source"),
            "switch_deferred": decision.get("switch_deferred"),
        }
        return await memory_service.log_tier_routing(
            query_text=query_text or "live_turn",
            chosen_tier=chosen_tier,
            reason=decision.get("reason", "live_policy_decision"),
            final_tier=chosen_tier,
            latency_ms=latency_ms,
            override_manuel=override_manuel,
            fallback_occurred=fallback_occurred,
            metadata=meta,
        )
    except Exception:
        return False
