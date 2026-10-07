"""services/search_router.py
Routeur de recherche déterministe et gestion de l'idempotence pour J.A.R.V.I.S.

Arbitre entre :
- L1 (`search_web`) : Recherche courte, factuelle, rapide (< 2s), économique (coût 0.00 $).
- L2 (`launch_deep_research`) : Analyse tactique multi-agents CLI Antigravity sur VPS (120s).
- L3 (`browser_task`) : Recherche approfondie web Gemini Deep Research (600s).

Garantit :
1. L1 par défaut en cas d'ambiguïté.
2. Priorité absolue aux surcharges explicites utilisateur ("fais vite" -> L1, "analyse tactique" -> L2, "analyse en profondeur" -> L3).
3. Idempotence et prévention stricte de double lancement pour la même intention.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("jarvis.search_router")


@dataclass
class SearchRoutingDecision:
    """Décision déterministe d'arbitrage de recherche."""
    tool: str  # "search_web" | "launch_deep_research" | "browser_task"
    tier: int  # 1, 2, 3
    level: str  # "L1", "L2", "L3"
    effort: Optional[str]  # "low", "medium", "high", None
    timeout: int  # Secondes (15, 120, 600)
    reason: str
    is_override: bool = False
    query: str = ""
    model_name: str = ""
    recipe: Optional[str] = None

    def __post_init__(self):
        if not self.model_name:
            if self.tier == 3 or self.level == "L3":
                self.model_name = "gemini-2.5-pro"
            else:
                self.model_name = "gemini-2.5-flash"
        if not self.recipe and (self.tier == 3 or self.level == "L3") and self.tool == "browser_task":
            self.recipe = "gemini_deep_research"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "tier": self.tier,
            "level": self.level,
            "effort": self.effort,
            "timeout": self.timeout,
            "reason": self.reason,
            "is_override": self.is_override,
            "query": self.query,
            "model_name": self.model_name,
            "recipe": self.recipe,
        }


def _normalize_text(text: str) -> str:
    """Normalise une chaîne de texte (minuscules, sans accents) pour un appariement robuste."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    cleaned = "".join(c for c in norm if not unicodedata.combining(c))
    return cleaned.lower().strip()


# Verrou en mémoire des recherches actives (anti-double lancement)
_ACTIVE_SEARCH_INTENTS: Set[str] = set()


def _make_intent_key(query: str) -> str:
    """Génère une clé d'intention normalisée pour éviter les lancements concurrents identiques."""
    norm = _normalize_text(query)
    # Retirer la ponctuation pour éviter les faux négatifs
    cleaned = re.sub(r"[^\w\s]", "", norm)
    # Remplacer les espaces multiples
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100]


def acquire_search_lock(query: str) -> bool:
    """Tente d'acquérir le verrou pour une intention de recherche.
    Retourne True si le verrou est acquis, False si une recherche identique est déjà en cours.
    """
    key = _make_intent_key(query)
    if not key:
        return True
    if key in _ACTIVE_SEARCH_INTENTS:
        logger.warning(f"[SearchRouter] Verrou rejeté : recherche déjà en cours pour '{key}'")
        return False
    _ACTIVE_SEARCH_INTENTS.add(key)
    return True


def release_search_lock(query: str) -> None:
    """Libère le verrou d'une intention de recherche."""
    key = _make_intent_key(query)
    if key in _ACTIVE_SEARCH_INTENTS:
        _ACTIVE_SEARCH_INTENTS.discard(key)


def is_search_in_progress(query: str) -> bool:
    """Vérifie si une recherche identique est déjà en cours."""
    key = _make_intent_key(query)
    return key in _ACTIVE_SEARCH_INTENTS


def clear_all_search_locks() -> None:
    """Purge tous les verrous de recherche (utilisé pour les tests et réinitialisations)."""
    _ACTIVE_SEARCH_INTENTS.clear()


def route_search_intent(
    query: str = "",
    user_preference: Optional[str] = None,
    intensite_reflexion: Optional[str] = None,
    task_hint: Optional[str] = None,
) -> SearchRoutingDecision:
    """Arbitre de façon déterministe entre `search_web` (L1), `launch_deep_research` (L2 multi-agent CLI) et `browser_task` (L3 Gemini Deep Research).
    
    Règles d'arbitrage ordonnées :
    1. Surcharges explicites (mots-clés de vitesse/profondeur, intensite_reflexion, user_preference)
    2. Détection d'intention sémantique / lexicale (L3 recherche web approfondie > L2 analyse tactique multi-agent CLI > L1 factuel)
    3. Défaut L1 en cas d'ambiguïté (économique & rapide, aucun Pro, aucun navigateur lourd).
    """
    norm = _normalize_text(query)
    ir = _normalize_text(intensite_reflexion or "")
    up = _normalize_text(user_preference or "")
    th = _normalize_text(task_hint or "")

    # ─── 1. SURCHARGES EXPLICITES ───

    # A. Override par intensite_reflexion
    if ir:
        if any(k in ir for k in ["rapide", "tier1", "tier 1", "flash-low", "flash_low", "economique", "l1", "vite"]):
            return SearchRoutingDecision(
                tool="search_web",
                tier=1,
                level="L1",
                effort="low",
                timeout=15,
                reason=f"Override explicite intensité L1 rapide ({intensite_reflexion})",
                is_override=True,
                query=query,
            )
        elif any(k in ir for k in ["tactique", "tier2", "tier 2", "flash-high", "flash_high", "l2", "intermediaire"]):
            return SearchRoutingDecision(
                tool="launch_deep_research",
                tier=2,
                level="L2",
                effort="medium",
                timeout=120,
                reason=f"Override explicite intensité L2 tactique multi-agent CLI ({intensite_reflexion})",
                is_override=True,
                query=query,
            )
        elif any(k in ir for k in ["approfondie", "tier3", "tier 3", "pro-high", "pro_high", "l3", "fond", "pro", "exhaustif"]):
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="high",
                timeout=600,
                recipe="gemini_deep_research",
                reason=f"Override explicite intensité L3 approfondie web Gemini ({intensite_reflexion})",
                is_override=True,
                query=query,
            )

    # B. Override par user_preference
    if up:
        if any(k in up for k in ["l1", "tier1", "tier 1", "rapide", "flash-low", "simple", "vite"]):
            return SearchRoutingDecision(
                tool="search_web",
                tier=1,
                level="L1",
                effort="low",
                timeout=15,
                reason=f"Override préférence utilisateur L1 ({user_preference})",
                is_override=True,
                query=query,
            )
        elif any(k in up for k in ["l2", "tier2", "tier 2", "tactique", "cli", "multi-agent", "multi_agent"]):
            return SearchRoutingDecision(
                tool="launch_deep_research",
                tier=2,
                level="L2",
                effort="medium",
                timeout=120,
                reason=f"Override préférence utilisateur L2 multi-agent CLI ({user_preference})",
                is_override=True,
                query=query,
            )
        elif any(k in up for k in ["l3", "tier3", "tier 3", "deep", "deep_research", "pro", "approfondie", "browser", "web"]):
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="high",
                timeout=600,
                recipe="gemini_deep_research",
                reason=f"Override préférence utilisateur L3 Gemini Deep Research web ({user_preference})",
                is_override=True,
                query=query,
            )

    # C. Signaux vocaux prioritaires dans la requête
    if norm:
        # Override explicite L1 : "fais vite", "passe rapide", "mode rapide", etc.
        tier1_override_signals = [
            "fais vite", "passe rapide", "mode rapide", "en rapide", "reponse rapide",
            "sans reflechir", "juste un resume", "check rapide", "en vitesse", "sois bref",
            "en 2 secondes", "en deux secondes", "ultra rapide", "en un mot"
        ]
        has_l1_regex = bool(re.search(r"\b(l1|niveau\s*(1|un)|tier\s*(1|un)|palier\s*(1|un))\b", norm))
        if has_l1_regex or any(sig in norm for sig in tier1_override_signals):
            return SearchRoutingDecision(
                tool="search_web",
                tier=1,
                level="L1",
                effort="low",
                timeout=15,
                reason="Override vocal explicite: consigne de rapidité L1 ('fais vite' / 'L1')",
                is_override=True,
                query=query,
            )

        # Override explicite L3 : "analyse en profondeur", "deep research", "niveau 3", "L3", etc.
        tier3_override_signals = [
            "analyse en profondeur", "recherche approfondie", "analyse approfondie",
            "etude approfondie", "prends tout ton temps", "reflexion maximale",
            "analyse de fond", "etude de fond", "rapport complet", "sources exhaustives",
            "mode pro", "deep research", "cartographie complete", "panorama complet",
            "niveau 3", "niveau trois", "recherche de niveau 3", "recherche niveau 3",
            "recherche de nievau 3", "recherche nievau 3", "nievau 3", "nievau trois",
            "recherche l3", "palier 3", "tier 3", "palier de niveau 3", "lance une recherche l3",
            "lance une recherche de niveau 3", "lance recherche niveau 3", "fais une recherche l3",
            "fais une recherche de niveau 3", "fais une recherche niveau 3", "recherche approfondie l3"
        ]
        has_l3_regex = bool(re.search(r"\b(l3|nive?a?u\s*(3|trois)|nievau\s*(3|trois)|niv\s*(3|trois)|tier\s*(3|trois)|palier\s*(3|trois)|deep\s*research)\b", norm))
        if has_l3_regex or any(sig in norm for sig in tier3_override_signals):
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="high",
                timeout=600,
                recipe="gemini_deep_research",
                reason="Override vocal explicite: consigne de recherche approfondie web Gemini L3 ('analyse en profondeur' / 'niveau 3' / 'L3')",
                is_override=True,
                query=query,
            )

        # Override explicite L2 : "analyse tactique", "L2", "niveau 2", "tier 2", etc.
        tier2_override_signals = [
            "analyse tactique", "passe tactique", "tactique", "intermediaire", "mode tactique",
            "multi-agent", "multi agents", "multi-agents", "orchestration agents", "etude tactique",
            "recherche de niveau 2", "recherche niveau 2", "niveau deux", "nievau 2", "nievau deux",
            "recherche l2", "lance une recherche l2", "lance une recherche de niveau 2"
        ]
        has_l2_regex = bool(re.search(r"\b(l2|nive?a?u\s*(2|deux)|nievau\s*(2|deux)|niv\s*(2|deux)|tier\s*(2|deux)|palier\s*(2|deux))\b", norm))
        if has_l2_regex or any(sig in norm for sig in tier2_override_signals):
            return SearchRoutingDecision(
                tool="launch_deep_research",
                tier=2,
                level="L2",
                effort="medium",
                timeout=120,
                reason="Override vocal explicite: consigne tactique multi-agent CLI L2 ('analyse tactique' / 'L2')",
                is_override=True,
                query=query,
            )

    # ─── 2. DÉTECTION SÉMANTIQUE / LEXICALE PAR PALIER ───

    # Task hint explicite
    if th:
        if th in ("deep_research", "gemini_deep_research", "complex", "l3"):
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="high",
                timeout=600,
                recipe="gemini_deep_research",
                reason="Task hint ciblé Gemini Deep Research Web L3",
                is_override=False,
                query=query,
            )
        elif th in ("launch_deep_research", "multi_agent_cli", "medium", "tactique", "l2"):
            return SearchRoutingDecision(
                tool="launch_deep_research",
                tier=2,
                level="L2",
                effort="medium",
                timeout=120,
                reason="Task hint ciblé Multi-Agents CLI L2",
                is_override=False,
                query=query,
            )
        elif th in ("search_web", "web_search", "simple", "factuel", "l1"):
            return SearchRoutingDecision(
                tool="search_web",
                tier=1,
                level="L1",
                effort="low",
                timeout=15,
                reason="Task hint ciblé Recherche Web L1",
                is_override=False,
                query=query,
            )

    if norm:
        # A. Signaux L3 (Recherche approfondie, Deep Research, thèse, cartographie marché via Gemini Web)
        l3_signals = [
            "deep research", "recherche approfondie", "rapport complet", "cartographie",
            "etude de marche", "marche des", "marche du", "marche de", "panorama complet", "veille sectorielle", "sources exhaustives",
            "etat de l'art", "investigation poussee", "these", "etude de fond",
            "analyse de fond", "synthese detaillee de marche", "recherche de fond",
            "recherche sur", "recherche quantique", "materiaux supraconducteurs", "reseaux quantiques", "batteries solides"
        ]
        if any(sig in norm for sig in l3_signals):
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="high",
                timeout=600,
                recipe="gemini_deep_research",
                reason="Intention détectée: recherche web approfondie Gemini L3",
                is_override=False,
                query=query,
            )

        # B. Signaux L2 (Comparatifs, analyses multi-sources, benchmarks, analyse tactique multi-agents CLI VPS)
        l2_signals = [
            "analyse tactique", "tactique", "multi-agents", "multi agents", "orchestration",
            "etude tactique", "pipeline cli", "comparaison tactique", "comparatif",
            "comparaison", "compare", "comparer", "analyse multi-sources", "multi-sources",
            "benchmark", "etude comparative"
        ]
        if any(sig in norm for sig in l2_signals):
            return SearchRoutingDecision(
                tool="launch_deep_research",
                tier=2,
                level="L2",
                effort="medium",
                timeout=120,
                reason="Intention détectée: analyse tactique et comparatif multi-agent CLI L2",
                is_override=False,
                query=query,
            )

        # C. Signaux Navigation Web Autonome (actions interactives)
        nav_signals = [
            "navigue", "va sur le site", "va sur", "ouvre le site", "ajoute au panier",
            "panier", "reserve", "reservation", "billet de train", "billet train", "sncf",
            "trainline", "booking", "airbnb", "amazon", "fnac", "formulaire", "remplis",
            "clique sur", "connecte-toi a", "connecte toi a", "explore le site",
            "compare les prix sur", "recherche sur le site"
        ]
        if any(sig in norm for sig in nav_signals):
            rec = "cart" if any(k in norm for k in ["panier", "amazon", "fnac"]) else ("train" if any(k in norm for k in ["train", "sncf", "trainline"]) else None)
            return SearchRoutingDecision(
                tool="browser_task",
                tier=3,
                level="L3",
                effort="medium",
                timeout=120,
                recipe=rec,
                reason="Intention détectée: navigation web autonome",
                is_override=False,
                query=query,
            )

        # D. Signaux L1 (Recherche factuelle directe, météo, cours, définition, date, fait récent)
        l1_signals = [
            "meteo", "temperature", "cours de", "bourse", "score", "date de", "definition",
            "qui est", "c'est quoi", "qu'est-ce que", "horaire", "prix indicatif", "fait recent",
            "actualite", "derniere nouvelle", "cherche sur google", "recherche rapide",
            "trouve le lien", "site officiel de", "age de", "population de", "capitale de"
        ]
        if any(sig in norm for sig in l1_signals):
            return SearchRoutingDecision(
                tool="search_web",
                tier=1,
                level="L1",
                effort="low",
                timeout=15,
                reason="Intention détectée: requête factuelle directe L1",
                is_override=False,
                query=query,
            )

    # ─── 3. DÉFAUT ÉCONOMIQUE EN CAS D'AMBIGUÏTÉ -> L1 ───
    return SearchRoutingDecision(
        tool="search_web",
        tier=1,
        level="L1",
        effort="low",
        timeout=15,
        reason="Défaut économique L1 en cas d'ambiguïté (recherche rapide Factuelle)",
        is_override=False,
        query=query,
    )
