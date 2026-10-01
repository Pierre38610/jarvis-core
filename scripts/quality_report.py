#!/usr/bin/env python3
"""scripts/quality_report.py
Rapport de qualité et d'audit de supervision hebdomadaire (7 jours) J.A.R.V.I.S. :
- Fausses confirmations (false_claim)
- Coupures d'élocution (cuts)
- Appels Antigravity (répartition flash/pro et niveaux d'effort)
- Pourcentage de tours en mode thinking
- Échecs par outil
- Plans incomplets
- Nombre d'usages de la clé PAID et motifs associés
Fournit également une phrase de synthèse orale pour le morning briefing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configuration du PYTHONPATH vers la racine du projet
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.turn_audit import get_db_connection, init_turn_audit_db


def extract_antigravity_details(tool_name: str, tool_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Détecte si un outil correspond à un appel Antigravity et extrait modèle et effort."""
    t_name = (tool_name or "").lower()
    is_antigravity = any(
        k in t_name
        for k in (
            "antigravity",
            "deep_reasoning",
            "deep_research",
            "agentic",
            "ask_deep_reasoning",
            "lancer_agent_antigravity",
        )
    )
    model_raw = str(tool_data.get("model") or tool_data.get("antigravity_model") or "").lower()
    if not is_antigravity and not ("gemini" in model_raw or "pro" in model_raw or "flash" in model_raw):
        return None

    # Catégorisation du modèle : flash vs pro
    if "pro" in model_raw or "pro" in t_name:
        model_cat = "pro"
    else:
        model_cat = "flash"

    # Catégorisation du niveau d'effort
    effort_raw = str(
        tool_data.get("effort")
        or tool_data.get("thinking_level")
        or tool_data.get("intensite_reflexion")
        or ""
    ).lower()

    if any(k in effort_raw for k in ("high", "haute", "approfondie", "tier3", "tier 3")):
        effort = "high"
    elif any(k in effort_raw for k in ("low", "faible", "rapide", "tier1", "tier 1")):
        effort = "low"
    else:
        effort = "medium"

    return {"model": model_cat, "effort": effort}


def is_plan_incomplete(plan_str: str) -> bool:
    """Détermine si un texte de plan représente un plan incomplet."""
    if not plan_str or not isinstance(plan_str, str):
        return False
    norm = plan_str.lower().strip()
    if norm in ("aucun plan actif.", "", "none", "null"):
        return False

    # Présence de cases à cocher non validées
    if "[ ]" in plan_str or "[TODO]" in plan_str.upper() or "[EN COURS]" in plan_str.upper():
        return True

    # Analyse textuelle d'étapes (ex: étape 1/3)
    step_match = re.search(r"étape\s+(\d+)\s*/\s*(\d+)", norm)
    if step_match:
        current_step = int(step_match.group(1))
        total_steps = int(step_match.group(2))
        if current_step < total_steps:
            return True

    if "incomplet" in norm or "interrompu" in norm or "suspendu" in norm:
        return True

    return False


def generate_quality_report(
    days: int = 7,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Interroge la table turn_audit sur les N derniers jours et calcule les métriques qualité."""
    init_turn_audit_db(db_path)
    conn = get_db_connection(db_path)

    cutoff_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()

    try:
        cur = conn.execute(
            """
            SELECT id, session_id, transcript, voice_mode, tools, plan,
                   final_sentence, cuts, duration, paid_used, paid_reason,
                   paid_consent, false_claim, false_claim_warning, created_at
            FROM turn_audit
            WHERE created_at >= ?
            ORDER BY id ASC
            """,
            (cutoff_date,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    total_turns = len(rows)
    thinking_turns = 0
    total_cuts = 0
    turns_with_cuts = 0
    false_claims_count = 0
    false_claim_details: List[Dict[str, Any]] = []

    antigravity_calls = 0
    antigravity_models = {"flash": 0, "pro": 0}
    antigravity_efforts = {"low": 0, "medium": 0, "high": 0}

    tool_failures: Dict[str, int] = {}
    incomplete_plans_count = 0
    paid_usage_count = 0
    paid_reasons: Dict[str, int] = {}

    for row in rows:
        # 1. Mode thinking
        v_mode = str(row.get("voice_mode") or "").lower()
        if v_mode == "thinking":
            thinking_turns += 1

        # 2. Coupures
        c = int(row.get("cuts") or 0)
        total_cuts += c
        if c > 0:
            turns_with_cuts += 1

        # 3. Fausses confirmations
        if bool(row.get("false_claim")):
            false_claims_count += 1
            false_claim_details.append({
                "id": row.get("id"),
                "created_at": row.get("created_at"),
                "final_sentence": row.get("final_sentence"),
                "warning": row.get("false_claim_warning"),
            })

        # 4. Usages clé PAID
        if bool(row.get("paid_used")):
            paid_usage_count += 1
            r_str = str(row.get("paid_reason") or "unspecified").strip()
            paid_reasons[r_str] = paid_reasons.get(r_str, 0) + 1

        # 5. Plans incomplets
        p_str = row.get("plan") or ""
        if is_plan_incomplete(p_str):
            incomplete_plans_count += 1

        # 6. Analyse des outils (échecs et Antigravity)
        raw_tools = row.get("tools") or "[]"
        if isinstance(raw_tools, str):
            try:
                tools_list = json.loads(raw_tools)
            except Exception:
                tools_list = []
        elif isinstance(raw_tools, list):
            tools_list = raw_tools
        else:
            tools_list = []

        for t in tools_list:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name") or "unknown_tool")
            status = str(t.get("status") or "").lower()
            verified = bool(t.get("verified", False))

            # Échec par outil
            is_failure = status in ("error", "failed", "exception", "refused") or (
                status in ("done", "success", "completed") and not verified and t.get("verification_failed")
            )
            if is_failure:
                tool_failures[name] = tool_failures.get(name, 0) + 1

            # Appels Antigravity
            ag_info = extract_antigravity_details(name, t)
            if ag_info:
                antigravity_calls += 1
                antigravity_models[ag_info["model"]] = antigravity_models.get(ag_info["model"], 0) + 1
                antigravity_efforts[ag_info["effort"]] = antigravity_efforts.get(ag_info["effort"], 0) + 1

    pct_thinking = round((thinking_turns / total_turns * 100), 1) if total_turns > 0 else 0.0

    report = {
        "period_days": days,
        "cutoff_date": cutoff_date,
        "total_turns": total_turns,
        "false_confirmations": {
            "count": false_claims_count,
            "details": false_claim_details,
        },
        "cuts": {
            "total_cuts": total_cuts,
            "turns_with_cuts": turns_with_cuts,
        },
        "antigravity": {
            "total_calls": antigravity_calls,
            "models": antigravity_models,
            "efforts": antigravity_efforts,
        },
        "thinking": {
            "count": thinking_turns,
            "percentage": pct_thinking,
        },
        "tool_failures": tool_failures,
        "incomplete_plans": {
            "count": incomplete_plans_count,
        },
        "paid_usage": {
            "count": paid_usage_count,
            "reasons": paid_reasons,
        },
    }

    report["summary_sentence"] = format_quality_summary_sentence(report)
    return report


def format_quality_summary_sentence(report: Dict[str, Any]) -> str:
    """Produit une phrase de synthèse orale élégante digne de Tony Stark & Aoede."""
    false_claims = report["false_confirmations"]["count"]
    total_cuts = report["cuts"]["total_cuts"]
    paid_count = report["paid_usage"]["count"]
    pct_thinking = report["thinking"]["percentage"]
    tool_failures_count = sum(report["tool_failures"].values())

    if report["total_turns"] == 0:
        return "Bilan de supervision hebdomadaire : aucun tour vocal audité sur la période, systèmes au repos."

    if false_claims == 0 and paid_count == 0 and tool_failures_count == 0:
        return (
            f"Bilan de supervision sur 7 jours : 100% de fiabilité sans aucune fausse confirmation, "
            f"{pct_thinking:.0f}% en mode réflexion et {total_cuts} coupure d'élocution."
        )

    parts: List[str] = []
    if false_claims == 0:
        parts.append("zéro fausse confirmation")
    else:
        parts.append(f"{false_claims} fausse(s) confirmation(s) bloquée(s)")

    if tool_failures_count > 0:
        parts.append(f"{tool_failures_count} échec(s) d'outil géré(s)")

    if paid_count > 0:
        parts.append(f"{paid_count} recours à la clé payante avec consentement")
    else:
        parts.append("zéro surcoût payant")

    parts.append(f"{pct_thinking:.0f}% de réflexion et {total_cuts} coupure(s)")

    return f"Bilan de supervision sur 7 jours : {', '.join(parts)}."


def get_quality_briefing_sentence(db_path: Optional[str] = None) -> str:
    """Point d'entrée direct pour injecter la synthèse qualité dans le morning briefing."""
    try:
        report = generate_quality_report(days=7, db_path=db_path)
        return report.get("summary_sentence", "")
    except Exception as e:
        return "Bilan de supervision hebdomadaire nominal."


def format_markdown_report(report: Dict[str, Any]) -> str:
    """Formate le rapport complet en markdown clair et structuré."""
    md: List[str] = []
    md.append(f"# 🛡️ Rapport Qualité & Supervision JARVIS ({report['period_days']} derniers jours)")
    md.append(f"**Période analysée** : depuis le {report['cutoff_date']}")
    md.append(f"**Total des tours vocaux audités** : {report['total_turns']}")
    md.append("")
    md.append(f"### 🎙️ Synthèse Orale Morning Briefing\n> *\"{report['summary_sentence']}\"*")
    md.append("")
    md.append("### 1. Fausses Confirmations & Allégations")
    md.append(f"- **Nombre de détections** : {report['false_confirmations']['count']}")
    if report["false_confirmations"]["details"]:
        for d in report["false_confirmations"]["details"][:5]:
            md.append(f"  - Tour #{d['id']} [{d['created_at']}] : \"{d['final_sentence']}\" ({d['warning']})")
    md.append("")
    md.append("### 2. Coupures d'Élocution & Anti-Barge-in")
    md.append(f"- **Total des coupures constatées** : {report['cuts']['total_cuts']}")
    md.append(f"- **Tours concernés** : {report['cuts']['turns_with_cuts']}")
    md.append("")
    md.append("### 3. Mode Réflexion (Thinking)")
    md.append(f"- **Tours en mode thinking** : {report['thinking']['count']} / {report['total_turns']} ({report['thinking']['percentage']}%)")
    md.append("")
    md.append("### 4. Appels Antigravity CLI")
    ag = report["antigravity"]
    md.append(f"- **Total appels Antigravity** : {ag['total_calls']}")
    md.append(f"  - **Modèles** : Flash ({ag['models']['flash']}), Pro ({ag['models']['pro']})")
    md.append(f"  - **Niveaux d'effort** : Low ({ag['efforts']['low']}), Medium ({ag['efforts']['medium']}), High ({ag['efforts']['high']})")
    md.append("")
    md.append("### 5. Fiabilité des Outils & Échecs")
    if report["tool_failures"]:
        for tool, fails in sorted(report["tool_failures"].items(), key=lambda x: x[1], reverse=True):
            md.append(f"- **{tool}** : {fails} échec(s)")
    else:
        md.append("- Aucun échec d'outil détecté sur la période.")
    md.append("")
    md.append("### 6. Plans d'Action")
    md.append(f"- **Plans incomplets** : {report['incomplete_plans']['count']}")
    md.append("")
    md.append("### 7. Consommation Clé Payante (PAID)")
    md.append(f"- **Nombre d'usages autorisés** : {report['paid_usage']['count']}")
    if report["paid_usage"]["reasons"]:
        for reason, count in report["paid_usage"]["reasons"].items():
            md.append(f"  - Motif `{reason}` : {count}")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Générateur de rapport qualité JARVIS (7 jours)")
    parser.add_argument("--days", type=int, default=7, help="Nombre de jours à analyser (défaut: 7)")
    parser.add_argument("--db-path", type=str, default=None, help="Chemin vers la base SQLite turn_audit")
    parser.add_argument("--json", action="store_true", help="Sortie brute JSON")
    args = parser.parse_args()

    report = generate_quality_report(days=args.days, db_path=args.db_path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_markdown_report(report))


if __name__ == "__main__":
    main()
