"""services/task_planner.py
Planificateur de consignes multi-etapes pour J.A.R.V.I.S.

Principe :
- decompose(utterance, context) -> appelle gemini-flash (cle FREE, timeout 4s,
  response_schema JSON strict) et renvoie une liste ordonnee de steps.
- Declenche UNIQUEMENT si la consigne contient >=2 verbes/connecteurs d'action
  ou depasse 25 mots. Une consigne simple ne passe pas par le planificateur.
- Plan persistant en memoire (+ Redis avec TTL 1h).
- Chaque step a un etat {pending, running, done, failed, skipped}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.task_planner")

# --- Seuils de declenchement --------------------------------------------------
_ACTION_CONNECTORS = re.compile(
    r"\b(et|puis|ensuite|apres|egalement|aussi|de plus|en plus|"
    r"d'abord|premierement|deuxiemement|finalement|enfin)\b",
    re.IGNORECASE,
)

_ACTION_VERBS = re.compile(
    r"\b(envoie|envoyer|lance|lancer|ajoute|ajouter|joue|jouer|"
    r"cherche|chercher|reserve|reserver|ouvre|ouvrir|cree|creer|genere|"
    r"generer|mets|mettre|fais|faire|demarre|demarrer|telecharge|"
    r"telecharger|prepare|preparer|rappelle|rappeler|planifie|planifier|"
    r"appelle|appeler|ecris|ecrire|achete|acheter|commande|commander|"
    r"trouve|trouver|affiche|afficher|montre|montrer|calcule|calculer)\b",
    re.IGNORECASE,
)

MIN_WORDS_TRIGGER = 25
MIN_CONNECTORS_OR_VERBS = 2
PLAN_REDIS_TTL = 3600

STEP_STATUSES = {"pending", "running", "done", "failed", "skipped"}


# --- Dataclasses --------------------------------------------------------------

@dataclass
class PlanStep:
    id: str
    description: str
    tool_candidate: str = ""
    depends_on: List[str] = field(default_factory=list)
    verification: str = ""
    status: str = "pending"
    note: str = ""
    tool_result: Optional[Dict[str, Any]] = field(default=None)
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlanStep":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid_keys})


@dataclass
class Plan:
    plan_id: str
    utterance: str
    steps: List[PlanStep]
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    _injection_count: int = field(default=0, repr=False)

    def pending_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    def running_steps(self) -> List[PlanStep]:
        return [s for s in self.steps if s.status == "running"]

    def is_complete(self) -> bool:
        return all(s.status in ("done", "failed", "skipped") for s in self.steps)

    def done_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")

    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "failed")

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        return next((s for s in self.steps if s.id == step_id), None)

    def checklist_text(self) -> str:
        lines = []
        icons = {"pending": "?", "running": ">>", "done": "OK", "failed": "X", "skipped": "-"}
        for s in self.steps:
            icon = icons.get(s.status, "?")
            note = f" ({s.note})" if s.note else ""
            lines.append(f"[{icon}] Etape {s.id} : {s.description}{note}")
        return "\n".join(lines)

    def final_report(self) -> str:
        parts = []
        for s in self.steps:
            if s.status == "done":
                evidence = ""
                if s.tool_result and s.tool_result.get("evidence"):
                    evidence = f" ({s.tool_result['evidence']})"
                parts.append(f"{s.description} : fait{evidence}")
            elif s.status == "failed":
                hint = ""
                if s.tool_result and s.tool_result.get("error_hint"):
                    hint = f" -- {s.tool_result['error_hint']}"
                elif s.note:
                    hint = f" -- {s.note}"
                parts.append(f"{s.description} : echec{hint}")
            elif s.status == "skipped":
                parts.append(f"{s.description} : ignore")
            else:
                parts.append(f"{s.description} : non traite")
        return ". ".join(parts) + "."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "utterance": self.utterance,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# --- Singleton en memoire -----------------------------------------------------
_active_plan: Optional[Plan] = None


def get_active_plan() -> Optional[Plan]:
    return _active_plan


def set_active_plan(plan: Optional[Plan]) -> None:
    global _active_plan
    _active_plan = plan


def clear_active_plan() -> None:
    global _active_plan
    _active_plan = None


# --- Detection de la necessite du planificateur -------------------------------

def needs_planning(utterance: str) -> bool:
    """
    Retourne True si la consigne necessite une decomposition multi-steps.
    Criteres : >= 2 connecteurs/verbes d'action distincts OU > 25 mots.
    Une consigne simple ne passe JAMAIS par le planificateur.
    """
    if not utterance or not isinstance(utterance, str):
        return False

    words = utterance.split()
    connectors = _ACTION_CONNECTORS.findall(utterance)
    verbs = _ACTION_VERBS.findall(utterance)
    unique_verbs = {v.lower() for v in verbs}

    if len(words) > MIN_WORDS_TRIGGER:
        if len(connectors) >= 1 or len(unique_verbs) >= MIN_CONNECTORS_OR_VERBS:
            return True

    return (
        len(connectors) >= 1 and len(unique_verbs) >= 1
    ) or len(unique_verbs) >= MIN_CONNECTORS_OR_VERBS


# --- Decomposeur via Gemini Flash ---------------------------------------------

_DECOMPOSE_PROMPT = (
    "Tu es un planificateur d'actions pour un assistant IA vocal.\n"
    "Decoupe la consigne en etapes. Consigne : {utterance}\n"
    "Contexte : {context}\n"
    "Retourne uniquement du JSON avec cette structure :\n"
    "{{ \"steps\": [{{ \"id\": \"1\", \"description\": \"...\", "
    "\"tool_candidate\": \"...\", \"depends_on\": [], \"verification\": \"...\" }}] }}\n"
    "Max 6 etapes. tool_candidate parmi : search_web, search_train_routes, "
    "manage_calendar_event, send_email, play_music_deezer, create_push_reminder, "
    "run_browser_task, save_memory, ask_deep_reasoning, generate_presentation, "
    "generate_spreadsheet, ou vide si inconnu. JSON pur, sans backtick."
)


async def decompose(
    utterance: str,
    context: str = "",
    timeout: float = 4.0,
) -> Optional[Plan]:
    """
    Appelle gemini-flash (cle FREE) pour decomposer la consigne en steps JSON.
    Timeout strict 4s. Retourne un Plan ou None si echec/timeout.
    Jamais d'exception propagee vers l'appelant.
    """
    if not needs_planning(utterance):
        return None

    import config
    api_key = config.GEMINI_API_KEY_FREE
    if not api_key:
        logger.warning("[TaskPlanner] Cle FREE absente, planificateur desactive.")
        return None

    prompt = _DECOMPOSE_PROMPT.format(
        utterance=utterance.strip(),
        context=context.strip() or "Aucun"
    )

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=api_key)

        response_schema = genai_types.Schema(
            type="OBJECT",
            properties={
                "steps": genai_types.Schema(
                    type="ARRAY",
                    items=genai_types.Schema(
                        type="OBJECT",
                        properties={
                            "id": genai_types.Schema(type="STRING"),
                            "description": genai_types.Schema(type="STRING"),
                            "tool_candidate": genai_types.Schema(type="STRING"),
                            "depends_on": genai_types.Schema(
                                type="ARRAY",
                                items=genai_types.Schema(type="STRING")
                            ),
                            "verification": genai_types.Schema(type="STRING"),
                        },
                        required=["id", "description"]
                    )
                )
            },
            required=["steps"]
        )

        generate_config = genai_types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=response_schema,
        )

        loop = asyncio.get_event_loop()
        raw_response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=generate_config,
                )
            ),
            timeout=timeout,
        )

        text = (raw_response.text or "").strip()
        if not text:
            logger.warning("[TaskPlanner] Reponse vide de Gemini flash.")
            return None

        data = json.loads(text)
        raw_steps = data.get("steps", [])
        if not raw_steps:
            return None

        steps = []
        for raw in raw_steps[:6]:
            steps.append(PlanStep(
                id=str(raw.get("id", str(len(steps) + 1))),
                description=str(raw.get("description", "")),
                tool_candidate=str(raw.get("tool_candidate", "")),
                depends_on=[str(d) for d in raw.get("depends_on", [])],
                verification=str(raw.get("verification", "")),
                status="pending",
            ))

        if not steps:
            return None

        plan = Plan(
            plan_id=str(uuid.uuid4())[:8],
            utterance=utterance,
            steps=steps,
        )

        set_active_plan(plan)
        asyncio.create_task(_persist_plan_redis(plan))

        logger.info(
            "[TaskPlanner] Plan cree : %s -- %d etapes pour : %s",
            plan.plan_id, len(steps), utterance[:60]
        )
        return plan

    except asyncio.TimeoutError:
        logger.warning("[TaskPlanner] Timeout (%.1fs) lors de la decomposition.", timeout)
        return None
    except Exception as exc:
        logger.warning("[TaskPlanner] Erreur decomposition : %s", exc)
        return None


async def _persist_plan_redis(plan: Plan) -> None:
    """Persiste le plan dans Redis avec TTL 1h. Best-effort."""
    try:
        from services.cache import cache_service
        client = await cache_service.get_client()
        if client:
            key = f"jarvis:plan:{plan.plan_id}"
            await client.set(key, json.dumps(plan.to_dict()), ex=PLAN_REDIS_TTL)
    except Exception:
        pass


# --- Outils exposes au modele -------------------------------------------------

def get_plan_status() -> Dict[str, Any]:
    """
    Outil get_plan_status() : retourne la checklist courante et les steps restants.
    """
    plan = get_active_plan()
    if plan is None:
        return {
            "status": "done",
            "verified": True,
            "evidence": "Aucun plan multi-etapes actif.",
            "user_message": "Aucun plan en cours.",
            "has_plan": False,
            "pending_count": 0,
            "steps": [],
        }

    pending = plan.pending_steps()
    return {
        "status": "done",
        "verified": True,
        "evidence": f"Plan {plan.plan_id} -- {len(plan.steps)} etapes",
        "user_message": plan.checklist_text(),
        "has_plan": True,
        "plan_id": plan.plan_id,
        "total_steps": len(plan.steps),
        "pending_count": len(pending),
        "done_count": plan.done_count(),
        "failed_count": plan.failed_count(),
        "is_complete": plan.is_complete(),
        "steps": [s.to_dict() for s in plan.steps],
        "next_pending": pending[0].to_dict() if pending else None,
    }


def mark_plan_step(
    step_id: str,
    status: str,
    note: str = "",
) -> Dict[str, Any]:
    """
    Outil mark_plan_step() : marque une etape avec un statut et une note.
    """
    plan = get_active_plan()
    if plan is None:
        return {
            "status": "failed",
            "verified": False,
            "evidence": "",
            "user_message": "Aucun plan actif pour marquer cette etape.",
            "error_hint": "Appeler d'abord une decomposition de consigne.",
        }

    if status not in STEP_STATUSES:
        return {
            "status": "failed",
            "verified": False,
            "evidence": "",
            "user_message": f"Statut invalide : {status}",
            "error_hint": f"Valeurs autorisees : {sorted(STEP_STATUSES)}",
        }

    step = plan.get_step(step_id)
    if step is None:
        return {
            "status": "failed",
            "verified": False,
            "evidence": "",
            "user_message": f"Etape '{step_id}' introuvable.",
            "error_hint": f"IDs disponibles : {[s.id for s in plan.steps]}",
        }

    step.status = status
    step.note = note
    step.finished_at = time.time()

    if plan.is_complete():
        plan.completed_at = time.time()
        logger.info("[TaskPlanner] Plan %s termine.", plan.plan_id)

    return {
        "status": "done",
        "verified": True,
        "evidence": f"Etape {step_id} marquee '{status}'",
        "user_message": f"Etape {step_id} mise a jour : {status}.",
        "step": step.to_dict(),
        "plan_complete": plan.is_complete(),
        "pending_count": len(plan.pending_steps()),
    }


def update_step_with_tool_result(step_id: str, tool_result: Dict[str, Any]) -> None:
    """
    Met a jour le step avec le resultat reel d'un outil.
    Appelable par la boucle de completion de routers/voice.py.
    """
    plan = get_active_plan()
    if not plan:
        return
    step = plan.get_step(step_id)
    if not step:
        return

    raw_status = str(tool_result.get("status", "")).lower()
    if raw_status in ("done", "success", "sent", "ok", "completed", "generated",
                      "opened", "updated", "saved", "scheduled", "applied",
                      "opened_locally", "playing", "stopped", "adapted"):
        step.status = "done"
    elif raw_status in ("failed", "error", "failure", "timeout"):
        step.status = "failed"
    elif raw_status in ("started", "launched_in_background", "running", "in_progress",
                        "monitoring_active", "healing_in_progress"):
        step.status = "running"
    else:
        step.status = "done"

    step.tool_result = tool_result
    step.finished_at = time.time()

    if plan.is_complete():
        plan.completed_at = time.time()
        logger.info("[TaskPlanner] Plan %s complete automatiquement.", plan.plan_id)


def build_continuation_prompt(plan: Plan, done_count: int) -> str:
    """
    Message systeme court et imperatif injecte apres chaque tool_response
    pour forcer le modele a continuer si des steps sont pending.
    """
    pending = plan.pending_steps()
    total = len(plan.steps)

    if not pending:
        return ""

    next_step = pending[0]
    tool_hint = f" Utilise l'outil '{next_step.tool_candidate}'." if next_step.tool_candidate else ""
    return (
        f"[PLAN EN COURS -- CONSIGNE SYSTEME IMPERATIVE] "
        f"Etape {done_count}/{total} traitee. "
        f"Il reste {len(pending)} etape(s). "
        f"Prochaine : '{next_step.description}'.{tool_hint} "
        f"Continue IMMEDIATEMENT sans demander confirmation. "
        f"Ne dis PAS 'c'est fait' tant que get_plan_status renvoie des pending."
    )


def build_final_report_prompt(plan: Plan) -> str:
    """Consigne d'injection pour le rapport final."""
    report = plan.final_report()
    return (
        f"[PLAN TERMINE -- RAPPORT FINAL OBLIGATOIRE] "
        f"Toutes les etapes sont terminees. "
        f"Fais le recapitulatif avec ta voix Aoede : {report}"
    )


def get_plan_hud_payload(plan: Optional[Plan] = None) -> Dict[str, Any]:
    """Payload supervision_update pour le HUD."""
    if plan is None:
        plan = get_active_plan()
    if plan is None:
        return {"plan_active": False}

    return {
        "plan_active": True,
        "plan_id": plan.plan_id,
        "utterance": plan.utterance[:80],
        "total": len(plan.steps),
        "done": plan.done_count(),
        "failed": plan.failed_count(),
        "pending": len(plan.pending_steps()),
        "complete": plan.is_complete(),
        "steps": [
            {
                "id": s.id,
                "desc": s.description,
                "status": s.status,
                "tool": s.tool_candidate,
            }
            for s in plan.steps
        ],
    }
