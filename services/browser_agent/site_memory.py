"""Mémoire par site pour le Browser Agent Jarvis (S6)."""

from datetime import datetime, timezone
import json
import logging
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.browser_agent.site_memory")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE_MEMORY_DIR = os.path.join(BASE_DIR, "data", "site_memory")


def _sanitize_domain(domain: str) -> str:
    """Nettoie le nom de domaine pour une utilisation sécurisée comme nom de fichier."""
    clean = str(domain or "").strip().lower()
    clean = re.sub(r"^https?://", "", clean)
    clean = clean.split("/")[0].split(":")[0]
    clean = re.sub(r"[^a-z0-9_\-\.]", "_", clean)
    return clean or "unknown_domain"


def load_hint(domain: str, goal: str) -> str:
    """Charge un indice textuel basé sur les succès passés pour ce domaine et cet objectif.

    Renvoie au maximum 2 entrées (correspondance simple par mots communs),
    sous forme de texte de 600 caractères maximum.
    """
    if not domain or not goal:
        return ""

    safe_domain = _sanitize_domain(domain)
    file_path = os.path.join(SITE_MEMORY_DIR, f"{safe_domain}.json")

    if not os.path.exists(file_path):
        return ""

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as exc:
        logger.warning("[SiteMemory] Impossible de lire %s: %s", file_path, exc)
        return ""

    if not isinstance(entries, list) or not entries:
        return ""

    # Mots clés de l'objectif (mots de 3 lettres ou plus pour éviter les bruits)
    goal_words = set(w.lower() for w in re.findall(r"\w+", goal) if len(w) >= 3)
    if not goal_words:
        goal_words = set(w.lower() for w in re.findall(r"\w+", goal))

    scored_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pattern = str(entry.get("goal_pattern", ""))
        pattern_words = set(w.lower() for w in re.findall(r"\w+", pattern))
        common = goal_words & pattern_words
        score = len(common)
        if score > 0:
            scored_entries.append((score, entry))

    if not scored_entries:
        return ""

    # Trier par score décroissant et retenir au maximum 2 entrées
    scored_entries.sort(key=lambda x: x[0], reverse=True)
    top_entries = [item[1] for item in scored_entries[:2]]

    lines = []
    for entry in top_entries:
        goal_pat = entry.get("goal_pattern", "")
        steps = entry.get("steps", [])
        steps_str = " -> ".join(str(s) for s in steps) if steps else "aucune étape"
        lines.append(f"- {goal_pat} : {steps_str}")

    hint_text = "\n".join(lines).strip()
    return hint_text[:600]


def save_success(domain: str, goal: str, steps_descriptions: List[str]) -> bool:
    """Enregistre un parcours réussi en JSON atomique (fichier temporaire puis rename).

    Garde 20 entrées par domaine au maximum.
    """
    if not domain or not goal:
        return False

    os.makedirs(SITE_MEMORY_DIR, exist_ok=True)
    safe_domain = _sanitize_domain(domain)
    file_path = os.path.join(SITE_MEMORY_DIR, f"{safe_domain}.json")

    entries: List[Dict[str, Any]] = []
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    entries = loaded
        except Exception as exc:
            logger.warning("[SiteMemory] Échec lecture existant %s: %s", file_path, exc)
            entries = []

    new_entry = {
        "goal_pattern": goal.strip(),
        "steps": [str(s).strip() for s in (steps_descriptions or []) if str(s).strip()],
        "last_success": datetime.now(timezone.utc).isoformat(),
    }

    entries.append(new_entry)
    # Garder 20 entrées maximum
    entries = entries[-20:]

    tmp_path = os.path.join(SITE_MEMORY_DIR, f"{safe_domain}_{os.getpid()}_{time.time_ns()}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
            f.flush()

        # Tentatives de remplacement atomique avec court repli sous Windows
        for attempt in range(5):
            try:
                os.replace(tmp_path, file_path)
                break
            except (PermissionError, OSError):
                if attempt == 4:
                    raise
                time.sleep(0.02)

        logger.debug("[SiteMemory] Succès enregistré pour domaine %s", safe_domain)
        return True
    except Exception as exc:
        logger.error("[SiteMemory] Échec écriture atomique pour %s: %s", safe_domain, exc)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False
