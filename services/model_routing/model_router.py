"""Routeur intelligent de modèles pour les agents Antigravity CLI et J.A.R.V.I.S.
Sélectionne le modèle optimal, le niveau d'effort approprié et la chaîne de repli résiliente
selon la tâche, la complexité, la taille du contexte et les préférences utilisateur.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from services.model_routing.model_registry import ModelInfo, model_registry

logger = logging.getLogger("jarvis.model_router")


@dataclass
class RoutingDecision:
    """Résultat de la décision d'arbitrage de modèle."""
    model: str
    effort: Optional[str]  # "low" | "medium" | "high" | None
    fallback_chain: List[str] = field(default_factory=list)
    reason: str = ""
    provider: str = "gemini"
    context_window: int = 1048576
    is_override: bool = False
    task_type: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "effort": self.effort,
            "fallback_chain": self.fallback_chain,
            "reason": self.reason,
            "provider": self.provider,
            "context_window": self.context_window,
            "is_override": self.is_override,
            "task_type": self.task_type
        }


# Missions par type de complexité
TASK_TYPE_MAPPING = {
    # Simple (Tier 1)
    "simple": "simple",
    "doc_sync": "simple",
    "book_curation": "simple",
    "email_simple": "simple",
    "log_check": "simple",
    "curation_livre_synthese": "simple",
    "documentation": "simple",
    "diagnostic": "simple",
    "quick_answer": "simple",

    # Medium (Tier 2)
    "medium": "medium",
    "transport_optimizer": "medium",
    "spreadsheet_modeler": "medium",
    "email_analysis": "medium",
    "email_drafting": "medium",
    "memory_consolidation": "medium",
    "morning_briefing": "medium",
    "slides": "medium",
    "slides_schema": "medium",
    "presentation": "medium",

    # Complex (Tier 3)
    "complex": "complex",
    "deep_research": "complex",
    "system_healing": "complex",
    "code_refactoring": "complex",
    "software_refactoring": "complex",
    "auto_guerison_systeme": "complex",
    "healing": "complex",
    "architecture": "complex",
    "engineering": "complex",

    # Code / Raisonnement Long
    "code": "code",
    "software_engineering": "code",
    "deep_coding": "code",
    "claude": "code"
}


def _extract_task_type(task: Union[str, Dict[str, Any], Any]) -> str:
    """Extrait le type de tâche normalisé à partir de divers formats d'entrée."""
    if isinstance(task, str):
        t_str = task.lower().strip()
        for k, v in TASK_TYPE_MAPPING.items():
            if k in t_str:
                return v
        return "medium"

    if isinstance(task, dict):
        # Chercher task_type, mission_type, category, type
        for key in ["task_type", "mission_type", "category", "type", "kind"]:
            val = task.get(key)
            if val and isinstance(val, str):
                v_lower = val.lower().strip()
                if v_lower in TASK_TYPE_MAPPING:
                    return TASK_TYPE_MAPPING[v_lower]
                for k, mapped in TASK_TYPE_MAPPING.items():
                    if k in v_lower:
                        return mapped
        return "medium"

    # Objet avec attributs
    for attr in ["task_type", "mission_type", "category", "type", "kind"]:
        if hasattr(task, attr):
            val = getattr(task, attr)
            if val and isinstance(val, str):
                v_lower = val.lower().strip()
                if v_lower in TASK_TYPE_MAPPING:
                    return TASK_TYPE_MAPPING[v_lower]
    return "medium"


def select_model(
    task: Union[str, Dict[str, Any], Any],
    query: str = "",
    context_size: int = 0,
    user_preference: Optional[str] = None,
    intensite_reflexion: Optional[str] = None,
    estimated_complexity: Optional[str] = None
) -> RoutingDecision:
    """Sélectionne le modèle d'IA optimal et son niveau de réflexion.
    
    Critères :
    1. Surcharge explicite (vocal, paramètre utilisateur, niveau d'intensité)
    2. Type de tâche et complexité estimée
    3. Taille du contexte (ajustement vers un modèle à fenêtre large si requis)
    4. Construction de la chaîne de repli en cascade
    """
    model_registry.refresh()

    # ─── 1. Surcharges explicites ───
    # A. Intensité de réflexion
    if intensite_reflexion:
        ir = intensite_reflexion.lower().strip()
        if any(k in ir for k in ["rapide", "low", "tier1", "economique"]):
            m_info = model_registry.get_model("gemini-3.7-flash") or model_registry.get_model("gemini-3.8-flash")
            m_name = m_info.name if m_info else "gemini-3.7-flash"
            return _build_decision(m_name, "low", f"Override explicite intensité: {intensite_reflexion}", is_override=True, task_type="simple")
        elif any(k in ir for k in ["tactique", "medium", "tier2"]):
            m_info = model_registry.get_model("gemini-3.7-flash") or model_registry.get_model("gemini-3.8-flash")
            m_name = m_info.name if m_info else "gemini-3.7-flash"
            return _build_decision(m_name, "medium", f"Override explicite intensité: {intensite_reflexion}", is_override=True, task_type="medium")
        elif any(k in ir for k in ["approfondie", "high", "tier3", "pro"]):
            m_info = model_registry.get_model("gemini-3.1-pro") or model_registry.get_model("gemini-3.1-pro-preview")
            m_name = m_info.name if m_info else "gemini-3.1-pro"
            return _build_decision(m_name, "high", f"Override explicite intensité: {intensite_reflexion}", is_override=True, task_type="complex")

    # B. Préférence utilisateur explicite
    if user_preference:
        up = user_preference.lower().strip()
        if "claude" in up or "sonnet" in up:
            m_info = model_registry.get_model("claude-3-7-sonnet")
            m_name = m_info.name if m_info else "claude-3-7-sonnet"
            return _build_decision(m_name, None, f"Override utilisateur Claude: {user_preference}", is_override=True, task_type="code")
        if "pro" in up or "3.1" in up:
            eff = "low" if "low" in up else "medium" if "med" in up else "high"
            m_info = model_registry.get_model("gemini-3.1-pro")
            m_name = m_info.name if m_info else "gemini-3.1-pro"
            return _build_decision(m_name, eff, f"Override utilisateur Pro: {user_preference}", is_override=True, task_type="complex")
        if "flash" in up or "3.7" in up or "3.8" in up:
            eff = "low" if any(k in up for k in ["low", "rapide"]) else "high" if "high" in up else "medium"
            m_info = model_registry.get_model("gemini-3.7-flash") or model_registry.get_model("gemini-3.8-flash")
            m_name = m_info.name if m_info else "gemini-3.7-flash"
            return _build_decision(m_name, eff, f"Override utilisateur Flash: {user_preference}", is_override=True, task_type="medium")

    # C. Signaux vocaux dans query
    if query:
        q_lower = query.lower()
        if any(sig in q_lower for sig in ["avec claude", "utilise claude", "mode claude", "sonnet"]):
            m_info = model_registry.get_model("claude-3-7-sonnet")
            m_name = m_info.name if m_info else "claude-3-7-sonnet"
            return _build_decision(m_name, None, "Override vocal: demande explicite de Claude", is_override=True, task_type="code")
        if any(sig in q_lower for sig in ["passe rapide", "mode rapide", "sans réfléchir", "juste un résumé", "check rapide"]):
            return _build_decision("gemini-3.7-flash", "low", "Override vocal: consigne de rapidité", is_override=True, task_type="simple")
        if any(sig in q_lower for sig in ["analyse approfondie", "réflexion maximale", "mode pro", "haute ingénierie", "délibération complète"]):
            return _build_decision("gemini-3.1-pro", "high", "Override vocal: consigne de réflexion approfondie", is_override=True, task_type="complex")

    # ─── 2. Routage par type de tâche & complexité ───
    task_type = _extract_task_type(task)
    complexity = (estimated_complexity or "").lower().strip()

    if task_type == "simple":
        target_model = "gemini-3.7-flash"
        target_effort = "low"
        reason = "Tâche simple (documentation, vérification, rapidité Tier 1)"
    elif task_type == "medium":
        target_model = "gemini-3.7-flash"
        if complexity in ("high", "complexe", "eleve"):
            target_effort = "high"
            reason = "Tâche intermédiaire à haute complexité (réflexion renforcée)"
        else:
            target_effort = "medium"
            reason = "Tâche intermédiaire (transport, tableur, e-mails)"
    elif task_type == "complex":
        target_model = "gemini-3.1-pro"
        target_effort = "high"
        reason = "Tâche complexe (recherche approfondie, refactoring, auto-réparation Système 2)"
    elif task_type == "code":
        target_model = "claude-3-7-sonnet"
        target_effort = None
        reason = "Génération de code et raisonnement logiciel ciblé Claude"
    else:
        target_model = "gemini-3.7-flash"
        target_effort = "medium"
        reason = "Routage standard par défaut"

    # ─── 3. Vérification de la taille du contexte ───
    m_info = model_registry.get_model(target_model)
    if m_info and context_size > 0:
        if context_size > m_info.context_window:
            # Passer à un modèle avec une plus grande fenêtre
            larger_models = [m for m in model_registry.list_models() if m.context_window >= context_size]
            if larger_models:
                larger_models.sort(key=lambda m: (m.cost_rank, m.latency_rank))
                chosen = larger_models[0]
                target_model = chosen.name
                reason += f" (surclassement contexte : {context_size} tokens > fenêtre {m_info.context_window})"

    decision = _build_decision(target_model, target_effort, reason, is_override=False, task_type=task_type)
    logger.info(f"Arbitrage modèle : {decision.model} (effort: {decision.effort}) pour '{task_type}' - {decision.reason}")
    return decision


def _build_decision(
    model_name: str,
    effort: Optional[str],
    reason: str,
    is_override: bool = False,
    task_type: str = "medium"
) -> RoutingDecision:
    """Construit l'objet RoutingDecision complet avec métadonnées et chaîne de repli."""
    m_info = model_registry.get_model(model_name)
    provider = m_info.provider if m_info else ("gemini" if "gemini" in model_name.lower() else "claude")
    ctx_window = m_info.context_window if m_info else 1048576
    supports_effort = m_info.supports_effort if m_info else (provider == "gemini")

    final_effort = effort if supports_effort else None

    # Construction de la chaîne de repli
    fallback_chain: List[str] = []
    if provider == "claude":
        # Claude -> Gemini Pro CLI -> Gemini Flash CLI -> Clé PAID API
        fallback_chain = ["gemini-3.1-pro", "gemini-3.7-flash", "api_paid_gemini"]
    elif "pro" in model_name.lower():
        # Gemini Pro -> Gemini Flash CLI -> Clé PAID API
        fallback_chain = ["gemini-3.7-flash", "gemini-3.8-flash", "api_paid_gemini"]
    else:
        # Gemini Flash -> Autre Flash CLI -> Gemini Pro CLI -> Clé PAID API
        fallback_chain = ["gemini-3.8-flash", "gemini-3.1-pro", "api_paid_gemini"]

    # Éviter d'avoir le modèle initial dans sa propre chaîne de repli
    fallback_chain = [f for f in fallback_chain if f != model_name]

    return RoutingDecision(
        model=model_name,
        effort=final_effort,
        fallback_chain=fallback_chain,
        reason=reason,
        provider=provider,
        context_window=ctx_window,
        is_override=is_override,
        task_type=task_type
    )
