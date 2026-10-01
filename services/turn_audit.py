"""services/turn_audit.py
Module d'audit de chaque tour de dialogue vocal JARVIS :
- Table SQLite 'turn_audit'
- Détecteur de fausses affirmations (false_claim)
- Récupération filtrée pour la supervision
- Fourniture des statuts de plan et sous-agents pour injection dans le prompt système
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import DB_PATH

logger = logging.getLogger("jarvis.turn_audit")

# Expression régulière pour détecter les affirmations d'action accomplie
FALSE_CLAIM_PATTERN = re.compile(
    r"\b(fait|faite|faits|faites|envoyé|envoyée|envoyés|envoyées|envoye|envoyee|créé|créée|créés|créées|cree|creee)\b",
    re.IGNORECASE,
)


def get_db_path(custom_path: Optional[str] = None) -> str:
    """Retourne le chemin SQLite courant, permettant le mock ou surcharge."""
    if custom_path:
        return custom_path
    import config
    return getattr(config, "DB_PATH", DB_PATH)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec row_factory Row."""
    target_path = get_db_path(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_turn_audit_db(db_path: Optional[str] = None) -> None:
    """Initialise la table turn_audit si elle n'existe pas déjà."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turn_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT DEFAULT 'voice',
                    transcript TEXT DEFAULT '',
                    voice_mode TEXT DEFAULT 'standard',
                    tools TEXT DEFAULT '[]',
                    plan TEXT DEFAULT '',
                    final_sentence TEXT DEFAULT '',
                    cuts INTEGER DEFAULT 0,
                    duration REAL DEFAULT 0.0,
                    paid_used INTEGER DEFAULT 0,
                    paid_reason TEXT DEFAULT '',
                    paid_consent TEXT DEFAULT '',
                    false_claim INTEGER DEFAULT 0,
                    false_claim_warning TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_turn_audit_created_at ON turn_audit(created_at)"
            )
    finally:
        conn.close()


def detect_false_claim(
    final_sentence: str,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Détecteur false_claim :
    Si la phrase finale contient « fait / envoyé / créé » sans aucun outil done+verified -> flag + WARNING.
    """
    if not final_sentence:
        return False, None

    tools = tools or []
    match = FALSE_CLAIM_PATTERN.search(final_sentence)
    if not match:
        return False, None

    trigger_word = match.group(1)

    # Vérification de la présence d'au moins un outil complété ET vérifié
    has_verified_done_tool = any(
        (
            str(t.get("status", "")).strip().lower() in ("done", "success", "completed", "ok")
            and bool(t.get("verified", False))
        )
        for t in tools
    )

    if not has_verified_done_tool:
        warning_msg = (
            f"WARNING: Affirmation non vérifiée détectée ('{trigger_word}') "
            f"dans la phrase finale sans aucun outil exécuté et vérifié avec succès."
        )
        logger.warning("[TurnAudit] %s | Phrase: '%s' | Outils: %s", warning_msg, final_sentence, tools)
        return True, warning_msg

    return False, None


def record_turn_audit(
    transcript: str,
    voice_mode: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    plan: str = "",
    final_sentence: str = "",
    cuts: int = 0,
    duration: float = 0.0,
    paid_used: bool = False,
    paid_reason: str = "",
    paid_consent: str = "",
    session_id: str = "voice",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Enregistre un tour audité dans la table turn_audit SQLite."""
    init_turn_audit_db(db_path)
    tools = tools or []

    is_false_claim, warning_msg = detect_false_claim(final_sentence, tools)
    created_at = datetime.utcnow().isoformat()
    tools_json = json.dumps(tools, ensure_ascii=False)

    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO turn_audit (
                    session_id, transcript, voice_mode, tools, plan,
                    final_sentence, cuts, duration, paid_used, paid_reason,
                    paid_consent, false_claim, false_claim_warning, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    transcript,
                    voice_mode,
                    tools_json,
                    plan,
                    final_sentence,
                    int(cuts),
                    float(duration),
                    1 if paid_used else 0,
                    paid_reason,
                    str(paid_consent),
                    1 if is_false_claim else 0,
                    warning_msg,
                    created_at,
                ),
            )
            inserted_id = cursor.lastrowid
    finally:
        conn.close()

    return {
        "id": inserted_id,
        "session_id": session_id,
        "transcript": transcript,
        "voice_mode": voice_mode,
        "tools": tools,
        "plan": plan,
        "final_sentence": final_sentence,
        "cuts": cuts,
        "duration": duration,
        "paid_used": paid_used,
        "paid_reason": paid_reason,
        "paid_consent": paid_consent,
        "false_claim": is_false_claim,
        "false_claim_warning": warning_msg,
        "created_at": created_at,
    }


def get_turn_audits(
    since: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Récupère la liste des tours audités depuis SQLite, filtrée éventuellement par 'since'."""
    init_turn_audit_db(db_path)
    conn = get_db_connection(db_path)
    rows = []
    try:
        query = "SELECT * FROM turn_audit"
        params: List[Any] = []
        if since:
            since_str = str(since).strip()
            # Si 'since' est un identifiant numérique entier
            if since_str.isdigit():
                query += " WHERE id > ?"
                params.append(int(since_str))
            else:
                query += " WHERE created_at > ?"
                params.append(since_str)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, tuple(params))
        raw_rows = cursor.fetchall()
        for r in raw_rows:
            d = dict(r)
            try:
                d["tools"] = json.loads(d.get("tools") or "[]")
            except Exception:
                d["tools"] = []
            d["paid_used"] = bool(d.get("paid_used"))
            d["false_claim"] = bool(d.get("false_claim"))
            rows.append(d)
    finally:
        conn.close()

    return rows


def get_active_plan_status_str() -> str:
    """Retourne l'état courant du plan sous forme de texte prêt pour injection prompt."""
    try:
        from services import task_planner as _task_planner_mod
        active_plan = _task_planner_mod.get_active_plan()
        if active_plan and hasattr(active_plan, "checklist_text"):
            return active_plan.checklist_text()
    except Exception as e:
        logger.debug("[TurnAudit] Erreur lecture active_plan: %s", e)
    return "Aucun plan actif."


def get_active_subagents_status_str() -> str:
    """Retourne l'état des sous-agents actifs sous forme de texte prêt pour injection prompt."""
    try:
        from services.supervision_service import supervision_service
        subagents = supervision_service.get_active_subagents()
        if subagents:
            return "\n".join([
                f"- [{sa.get('role', 'agent')}] {sa.get('name', 'subagent')} : {sa.get('activity', '')} ({sa.get('task', '')})"
                for sa in subagents
            ])
    except Exception as e:
        logger.debug("[TurnAudit] Erreur lecture subagents: %s", e)
    return "Aucun sous-agent actif."


def get_prompt_status_context() -> Dict[str, str]:
    """Fournit le dictionnaire de statut {active_plan_status, active_subagents_status} pour chaque tour."""
    return {
        "active_plan_status": get_active_plan_status_str(),
        "active_subagents_status": get_active_subagents_status_str(),
    }


def inject_turn_status_into_prompt(prompt_text: str) -> str:
    """Injecte dynamiquement {active_plan_status} et {active_subagents_status} dans le prompt système du tour."""
    if not prompt_text:
        prompt_text = ""
    ctx = get_prompt_status_context()
    plan_st = ctx["active_plan_status"]
    sub_st = ctx["active_subagents_status"]

    has_placeholders = "{active_plan_status}" in prompt_text or "{active_subagents_status}" in prompt_text
    if has_placeholders:
        return prompt_text.replace("{active_plan_status}", plan_st).replace("{active_subagents_status}", sub_st)

    # Si les placeholders ne sont pas présents, injection du bloc de statut
    status_block = (
        f"\n\n[STATUT DYNAMIQUE DU TOUR DE PAROLE]\n"
        f"- PLAN D'ACTION EN COURS : {plan_st}\n"
        f"- SOUS-AGENTS ACTIFS : {sub_st}\n"
    )
    return f"{prompt_text}{status_block}"
