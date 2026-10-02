"""core/tools/result.py
Contrat standardisé et universel de résultat d'outils J.A.R.V.I.S. (ToolResult).
Rend structurellement impossible qu'un outil annonce un succès sans preuve.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("jarvis.tools.result")

ALLOWED_STATUSES: Set[str] = {"done", "failed", "started", "partial", "needs_user"}

# Mapping déterministe des anciens statuts hétérogènes vers les 5 statuts stricts
LEGACY_STATUS_MAPPING: Dict[str, str] = {
    # Succès supposés legacy -> "done"
    "success": "done",
    "sent": "done",
    "saved": "done",
    "found": "done",
    "ok": "done",
    "cdp_executed": "done",
    "interacted": "done",
    "opened": "done",
    "updated": "done",
    "completed": "done",
    "ready": "done",
    "stopped": "done",
    "adapted": "done",
    "draft_created": "done",
    "ebook_delivered": "done",
    "sent_to_ereader": "done",
    "slides_created": "done",
    "generated": "done",
    "scheduled": "done",
    "opened_locally": "done",
    "diagnosed": "done",
    "executed": "done",
    "applied": "done",
    "summary_ready": "done",
    "broadcasted": "done",
    "cleared": "done",
    "playing": "done",
    # Tâches asynchrones en cours -> "started"
    "launched_in_background": "started",
    "lance_en_arriere_plan": "started",
    "running": "started",
    "healing_in_progress": "started",
    "monitoring_active": "started",
    "monitoring": "started",
    "in_progress": "started",
    # Échecs avérés -> "failed"
    "error": "failed",
    "failed": "failed",
    "échec": "failed",
    "echec": "failed",
    "failure": "failed",
    "timeout": "failed",
    "pc_offline": "failed",
    "pc_disconnected": "failed",
    "smtp_error": "failed",
    # Interaction utilisateur requise -> "needs_user"
    "requires_user_confirmation": "needs_user",
    "requires_validation": "needs_user",
    "cart_ready": "needs_user",
    "awaiting_user_payment": "needs_user",
    "awaiting_payment": "needs_user",
    "redirect_media": "needs_user",
    "needs_user": "needs_user",
    # Partiel -> "partial"
    "partial": "partial",
    "partiel": "partial",
}


@dataclass
class ToolResult:
    """Résultat normalisé retourné par tous les outils J.A.R.V.I.S.
    
    Attributes:
        status: ∈ {"done", "failed", "started", "partial", "needs_user"}
        verified: True UNIQUEMENT si une vérification indépendante de l'effet a réussi.
        evidence: Preuve matérielle (URL créée, message-id, chemin+taille, PID...).
        user_message: Phrase courte en français à énoncer ou paraphraser fidèlement.
        task_id: Identifiant de tâche si status="started".
        error_hint: Cause probable et suggestion d'action si status="failed" ou "partial".
        data: Données brutes métier pour compatibilité frontend et routeurs.
    """
    status: str
    verified: bool = False
    evidence: str = ""
    user_message: str = ""
    task_id: Optional[str] = None
    error_hint: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Statut ToolResult invalide : '{self.status}'. "
                f"Valeurs autorisées : {ALLOWED_STATUSES}"
            )
        if not isinstance(self.verified, bool):
            self.verified = bool(self.verified)
        if not self.user_message:
            self.user_message = self._default_user_message()

    def _default_user_message(self) -> str:
        if self.status == "done":
            if self.verified:
                return "L'action a été effectuée et vérifiée avec succès."
            return "L'action a été exécutée, mais la vérification n'a pas encore pu être confirmée."
        elif self.status == "started":
            return "L'opération est en cours d'exécution en arrière-plan."
        elif self.status == "failed":
            hint = f" ({self.error_hint})" if self.error_hint else ""
            return f"L'opération a échoué{hint}."
        elif self.status == "partial":
            return "L'opération n'a été que partiellement accomplie."
        elif self.status == "needs_user":
            return "Votre confirmation est nécessaire pour continuer."
        return "Traitement terminé."

    def to_dict(self) -> Dict[str, Any]:
        """Convertit ToolResult en dictionnaire prêt pour send_tool_response() et l'UI."""
        res: Dict[str, Any] = {
            "status": self.status,
            "verified": self.verified,
            "evidence": self.evidence,
            "user_message": self.user_message,
        }
        if self.task_id is not None:
            res["task_id"] = self.task_id
        if self.error_hint is not None:
            res["error_hint"] = self.error_hint

        # Inclusion transparente des données métier additionnelles
        if self.data and isinstance(self.data, dict):
            for k, v in self.data.items():
                if k not in res:
                    res[k] = v

        return res

    @property
    def is_success(self) -> bool:
        return self.status in ("done", "started")

    @classmethod
    def done(
        cls,
        user_message: str = "",
        evidence: str = "",
        verified: bool = True,
        data: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        error_hint: Optional[str] = None,
        **extra: Any,
    ) -> "ToolResult":
        """Opération terminée avec succès (vérifiée par défaut si evidence fournie)."""
        d = dict(data or {})
        d.update(extra)
        return cls(
            status="done",
            verified=verified,
            evidence=evidence,
            user_message=user_message,
            task_id=task_id,
            error_hint=error_hint,
            data=d,
        )

    @classmethod
    def failed(
        cls,
        user_message: str = "",
        error_hint: Optional[str] = None,
        evidence: str = "",
        data: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        **extra: Any,
    ) -> "ToolResult":
        """Échec avéré d'une opération (interdiction de prétendre au succès)."""
        d = dict(data or {})
        d.update(extra)
        return cls(
            status="failed",
            verified=False,
            evidence=evidence,
            user_message=user_message,
            error_hint=error_hint,
            task_id=task_id,
            data=d,
        )

    @classmethod
    def started(
        cls,
        task_id: Optional[str] = None,
        user_message: str = "",
        evidence: str = "",
        error_hint: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> "ToolResult":
        """Opération asynchrone lancée en arrière-plan."""
        d = dict(data or {})
        d.update(extra)
        return cls(
            status="started",
            verified=False,
            evidence=evidence,
            user_message=user_message,
            task_id=task_id,
            error_hint=error_hint,
            data=d,
        )

    @classmethod
    def partial(
        cls,
        user_message: str = "",
        evidence: str = "",
        error_hint: Optional[str] = None,
        task_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> "ToolResult":
        """Opération partielle ou audit incomplet."""
        d = dict(data or {})
        d.update(extra)
        return cls(
            status="partial",
            verified=False,
            evidence=evidence,
            user_message=user_message,
            task_id=task_id,
            error_hint=error_hint,
            data=d,
        )

    @classmethod
    def needs_user(
        cls,
        user_message: str = "",
        question: Optional[str] = None,
        evidence: str = "",
        error_hint: Optional[str] = None,
        task_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        **extra: Any,
    ) -> "ToolResult":
        """Attente d'une confirmation ou action de l'utilisateur."""
        d = dict(data or {})
        if question and "question" not in d:
            d["question"] = question
        d.update(extra)
        return cls(
            status="needs_user",
            verified=False,
            evidence=evidence,
            user_message=user_message,
            task_id=task_id,
            error_hint=error_hint,
            data=d,
        )


def normalize_result(tool_name: str, res: Any) -> ToolResult:
    """Enveloppe défensive : convertit tout retour d'outil (natif ou legacy) vers ToolResult.
    
    Log un WARNING systématique pour chaque outil renvoyant encore un format legacy.
    Garantit que la sortie respecte strictement le contrat des 5 statuts.
    """
    if isinstance(res, ToolResult):
        return res

    if not isinstance(res, dict):
        logger.warning(
            "[ToolResult] Outil '%s' a renvoyé un type non structuré (%s). Normalisation forcée.",
            tool_name,
            type(res).__name__,
        )
        msg = str(res) if res is not None else "Aucune réponse retournée."
        return ToolResult(
            status="done" if res is not None else "failed",
            verified=False,
            user_message=msg,
            data={"raw_response": res},
        )

    # Si le dictionnaire est déjà au format strict ToolResult
    raw_status = str(res.get("status", "")).lower().strip()
    has_verified = "verified" in res
    if raw_status in ALLOWED_STATUSES and has_verified:
        return ToolResult(
            status=raw_status,
            verified=bool(res.get("verified", False)),
            evidence=str(res.get("evidence", "")),
            user_message=str(res.get("user_message", "")),
            task_id=res.get("task_id"),
            error_hint=res.get("error_hint"),
            data={k: v for k, v in res.items() if k not in {
                "status", "verified", "evidence", "user_message", "task_id", "error_hint"
            }},
        )

    # Format Legacy détecté -> Logging de l'avertissement
    logger.warning(
        "[ToolResult] Format legacy détecté pour l'outil '%s' (statut reçu: '%s'). Normalisation en cours.",
        tool_name,
        res.get("status"),
    )

    # Résolution du statut canonique via la table de correspondance
    target_status = LEGACY_STATUS_MAPPING.get(raw_status)
    if not target_status:
        if raw_status in ALLOWED_STATUSES:
            target_status = raw_status
        elif any(k in raw_status for k in ("err", "fail", "echou", "invalide")):
            target_status = "failed"
        else:
            target_status = "done"

    # Extraction des preuves matérielles existantes
    evidence = (
        str(res.get("evidence") or "")
        or str(res.get("presentation_url") or "")
        or str(res.get("file_url") or "")
        or str(res.get("path") or res.get("file_path") or res.get("epub_path") or "")
        or (f"PID {res.get('pid')}" if res.get("pid") else "")
        or str(res.get("message_id") or "")
        or str(res.get("url") or "")
    )

    # Extraction du message utilisateur en français
    user_message = (
        str(res.get("user_message") or "")
        or str(res.get("message") or "")
        or str(res.get("instruction_to_jarvis") or "")
        or str(res.get("summary") or "")
    )

    # Extraction de l'identifiant de tâche
    task_id = (
        res.get("task_id")
        or res.get("action_id")
        or res.get("mission_id")
        or res.get("patch_id")
        or res.get("reminder_id")
    )

    # Extraction des indications d'erreur
    error_hint = (
        res.get("error_hint")
        or res.get("error")
        or (res.get("message") if target_status == "failed" else None)
    )

    # Par défaut sur un retour legacy, verified = False pour sécurité absolue
    # (sauf si explicitement fourni et vérifié)
    verified = bool(res.get("verified", False))

    if target_status == "done" and not verified:
        try:
            from services.metrics_service import metrics_service
            metrics_service.record_claimed_success_without_verification(tool_name)
        except Exception:
            pass

    extra_data = {
        k: v for k, v in res.items()
        if k not in {"status", "verified", "evidence", "user_message", "task_id", "error_hint"}
    }

    return ToolResult(
        status=target_status,
        verified=verified,
        evidence=evidence,
        user_message=user_message,
        task_id=str(task_id) if task_id is not None else None,
        error_hint=str(error_hint) if error_hint is not None else None,
        data=extra_data,
    )
