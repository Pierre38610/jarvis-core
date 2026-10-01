"""core/tools/arg_validator.py
Validation stricte des arguments pour outils sensibles et actions irréversibles J.A.R.V.I.S.
Garantit qu'aucun outil critique n'est exécuté avec des arguments vides, génériques ou sans confirmation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from core.tools.result import ToolResult

# Mots ou expressions génériques interdits pour les outils sensibles
GENERIC_STRINGS: Set[str] = {
    "",
    "test",
    "test.",
    "testing",
    "un test",
    "test mail",
    "présentation",
    "presentation",
    "slides",
    "slide",
    "nouvelle présentation",
    "nouvelle presentation",
    "mail",
    "email",
    "e-mail",
    "nouveau mail",
    "message",
    "sans titre",
    "aucun",
    "none",
    "null",
    "undefined",
    "todo",
    "n/a",
    "titre",
    "evenement",
    "événement",
    "rdv",
    "reunion",
    "réunion",
    "bug",
    "erreur",
}

# Outils sensibles nécessitant une validation stricte
SENSITIVE_TOOLS: Set[str] = {
    "send_email",
    "mail_send",
    "draft_email_response",
    "generate_presentation",
    "generer_presentation",
    "modify_presentation",
    "modifier_presentation",
    "manage_calendar_event",
    "agenda_gerer_evenement",
    "system_self_healing",
    "auto_guerison_systeme",
}

# Outils ou actions irréversibles nécessitant confirmed_by_user == True
IRREVERSIBLE_TOOLS: Set[str] = {
    "send_email",
    "mail_send",
}


def is_generic_or_empty(val: Any, min_length: int = 3) -> bool:
    """Vérifie si une chaîne est vide, trop courte ou présente dans la liste générique."""
    if val is None:
        return True
    if not isinstance(val, str):
        return False
    s = val.strip().lower()
    if len(s) < min_length:
        return True
    return s in GENERIC_STRINGS


def validate_tool_arguments(name: str, args: Optional[Dict[str, Any]]) -> Optional[ToolResult]:
    """Valide les arguments d'un outil sensible avant tout dispatch.
    
    Returns:
        ToolResult(status='needs_user', question=...) si invalide, manquant ou non confirmé.
        None si les arguments sont valides et l'action autorisée.
    """
    args = args or {}
    tool_name = (name or "").strip().lower()

    if tool_name not in SENSITIVE_TOOLS:
        return None

    # Objet vide rejeté systématiquement pour les outils sensibles
    if not args or not any(v for v in args.values() if v is not None and v != ""):
        return ToolResult.needs_user(
            user_message=f"Les paramètres pour l'action '{tool_name}' sont manquants ou vides.",
            question=f"Quelles sont les précisions nécessaires pour exécuter '{tool_name}' ?",
            evidence="Validation rejetée : arguments vides",
            data={"reason": "empty_arguments", "tool": tool_name},
        )

    # ─── 1. Envoi d'e-mail (send_email) ──────────────────────────────────────────
    if tool_name in ("send_email", "mail_send"):
        subject = args.get("subject")
        body = args.get("body")
        to_email = args.get("to_email") or "Pierre"

        if is_generic_or_empty(subject, min_length=3):
            return ToolResult.needs_user(
                user_message="L'objet de l'e-mail est vide ou trop générique.",
                question="Quel est l'objet précis du courriel que vous souhaitez expédier ?",
                evidence="Validation rejetée : objet email invalide",
                data={"field": "subject", "rejected_value": subject},
            )

        if is_generic_or_empty(body, min_length=4):
            return ToolResult.needs_user(
                user_message="Le contenu de l'e-mail est vide ou trop court.",
                question="Quel est le contenu exact du message à envoyer ?",
                evidence="Validation rejetée : corps email invalide",
                data={"field": "body", "rejected_value": body},
            )

        # Action irréversible : envoi de mail requiert confirmation explicite
        if not bool(args.get("confirmed_by_user", False)):
            action_summary = f"Expédition d'un e-mail à {to_email} avec l'objet '{subject}'"
            return ToolResult.needs_user(
                user_message=f"Confirmation requise : {action_summary}.",
                question=f"Confirmez-vous l'envoi de cet e-mail à {to_email} avec pour objet '{subject}' ?",
                evidence="Confirmation utilisateur requise avant expédition e-mail",
                data={
                    "requires_confirmation": True,
                    "action_summary": action_summary,
                    "tool": tool_name,
                    "to_email": to_email,
                    "subject": subject,
                },
            )

    # ─── 2. Présentations (generate_presentation / modify_presentation) ──────────
    elif tool_name in ("generate_presentation", "generer_presentation"):
        sujet = args.get("sujet") or args.get("topic") or args.get("titre")
        consignes = args.get("consignes") or args.get("instructions") or args.get("prompt")

        if is_generic_or_empty(sujet, min_length=3):
            return ToolResult.needs_user(
                user_message="Le sujet de la présentation est manquant ou générique.",
                question="Quel est le sujet exact ou le titre de la présentation Google Slides à créer ?",
                evidence="Validation rejetée : sujet présentation invalide",
                data={"field": "sujet", "rejected_value": sujet},
            )

        if is_generic_or_empty(consignes, min_length=4):
            return ToolResult.needs_user(
                user_message="Les consignes pour la présentation sont trop vagues ou manquantes.",
                question="Quelles sont les consignes précises et le contenu souhaité pour la présentation ?",
                evidence="Validation rejetée : consignes présentation invalides",
                data={"field": "consignes", "rejected_value": consignes},
            )

    elif tool_name in ("modify_presentation", "modifier_presentation"):
        instruction = args.get("instruction") or args.get("instructions")
        if is_generic_or_empty(instruction, min_length=3):
            return ToolResult.needs_user(
                user_message="L'instruction de modification de présentation est manquante ou générique.",
                question="Quelle modification spécifique souhaitez-vous appliquer aux diapositives ?",
                evidence="Validation rejetée : instruction de modification présentation invalide",
                data={"field": "instruction", "rejected_value": instruction},
            )

    # ─── 3. Calendrier (manage_calendar_event) ──────────────────────────────────
    elif tool_name in ("manage_calendar_event", "agenda_gerer_evenement"):
        action = (args.get("action") or "consulter").strip().lower()
        titre = args.get("titre") or args.get("title") or args.get("summary")
        date_debut = args.get("date_debut") or args.get("start_time") or args.get("date")

        valid_actions = {"consulter", "creer", "create", "ajouter", "add", "decaler", "update", "supprimer", "delete", "cancel"}
        if action not in valid_actions:
            return ToolResult.needs_user(
                user_message=f"L'action d'agenda '{action}' n'est pas reconnue.",
                question="Souhaitez-vous consulter, créer, décaler ou supprimer un événement dans votre agenda ?",
                evidence="Validation rejetée : action agenda inconnue",
                data={"field": "action", "rejected_value": action},
            )

        if action in ("creer", "create", "ajouter", "add"):
            if is_generic_or_empty(titre, min_length=3):
                return ToolResult.needs_user(
                    user_message="Le titre du rendez-vous est manquant ou générique.",
                    question="Quel est l'intitulé précis du rendez-vous à ajouter à votre agenda ?",
                    evidence="Validation rejetée : titre agenda invalide",
                    data={"field": "titre", "rejected_value": titre},
                )
            if not date_debut or is_generic_or_empty(str(date_debut), min_length=2):
                return ToolResult.needs_user(
                    user_message="La date ou l'heure de début du rendez-vous est manquante.",
                    question="À quelle date et heure ce rendez-vous doit-il être positionné ?",
                    evidence="Validation rejetée : date début agenda manquante",
                    data={"field": "date_debut", "rejected_value": date_debut},
                )

        elif action in ("decaler", "update"):
            if is_generic_or_empty(titre, min_length=2) and not args.get("event_id"):
                return ToolResult.needs_user(
                    user_message="L'événement à décaler n'est pas précisé.",
                    question="Quel rendez-vous de votre agenda souhaitez-vous décaler ?",
                    evidence="Validation rejetée : cible décalage agenda manquante",
                    data={"field": "titre", "rejected_value": titre},
                )
            if not date_debut or is_generic_or_empty(str(date_debut), min_length=2):
                return ToolResult.needs_user(
                    user_message="Le nouvel horaire du rendez-vous est manquant.",
                    question="Vers quelle nouvelle date et heure souhaitez-vous déplacer ce rendez-vous ?",
                    evidence="Validation rejetée : nouvel horaire manquant",
                    data={"field": "date_debut", "rejected_value": date_debut},
                )

        elif action in ("supprimer", "delete", "cancel"):
            if is_generic_or_empty(titre, min_length=2) and not args.get("event_id"):
                return ToolResult.needs_user(
                    user_message="L'événement à supprimer n'est pas précisé.",
                    question="Quel rendez-vous de votre agenda souhaitez-vous annuler ou supprimer ?",
                    evidence="Validation rejetée : cible suppression agenda manquante",
                    data={"field": "titre", "rejected_value": titre},
                )
            # Action irréversible : suppression de calendrier requiert confirmation
            if not bool(args.get("confirmed_by_user", False)):
                target_desc = titre or args.get("event_id")
                action_summary = f"Suppression de l'événement '{target_desc}' dans l'agenda"
                return ToolResult.needs_user(
                    user_message=f"Confirmation requise : {action_summary}.",
                    question=f"Confirmez-vous la suppression définitive du rendez-vous '{target_desc}' de votre agenda ?",
                    evidence="Confirmation utilisateur requise avant suppression agenda",
                    data={
                        "requires_confirmation": True,
                        "action_summary": action_summary,
                        "tool": tool_name,
                        "action": action,
                        "titre": target_desc,
                    },
                )

    # ─── 4. Correction système (system_self_healing) ─────────────────────────────
    elif tool_name in ("system_self_healing", "auto_guerison_systeme"):
        action = (args.get("action") or "heal").strip().lower()
        motif = args.get("motif") or args.get("reason")
        patch_id = args.get("patch_id")

        if action in ("heal", "auto"):
            if is_generic_or_empty(motif, min_length=3):
                return ToolResult.needs_user(
                    user_message="Le motif de la correction système est manquant ou générique.",
                    question="Quelle anomalie ou erreur critique souhaitez-vous faire réparer par l'agent SRE ?",
                    evidence="Validation rejetée : motif auto-guérison invalide",
                    data={"field": "motif", "rejected_value": motif},
                )
            # Action irréversible : auto-guérison modifie le code source du serveur
            if not bool(args.get("confirmed_by_user", False)):
                action_summary = f"Intervention SRE et modification du code source pour : '{motif}'"
                return ToolResult.needs_user(
                    user_message=f"Confirmation requise : {action_summary}.",
                    question=f"Confirmez-vous le lancement d'une réparation autonome sur le serveur pour '{motif}' ?",
                    evidence="Confirmation utilisateur requise avant intervention système",
                    data={
                        "requires_confirmation": True,
                        "action_summary": action_summary,
                        "tool": tool_name,
                        "motif": motif,
                    },
                )

        elif action in ("rollback", "annuler"):
            if not bool(args.get("confirmed_by_user", False)):
                pid_str = f"du patch {patch_id}" if patch_id else "du dernier patch"
                action_summary = f"Annulation (rollback) {pid_str} sur le serveur"
                return ToolResult.needs_user(
                    user_message=f"Confirmation requise : {action_summary}.",
                    question=f"Confirmez-vous l'annulation et le rétablissement de la version précédente {pid_str} ?",
                    evidence="Confirmation utilisateur requise avant rollback",
                    data={
                        "requires_confirmation": True,
                        "action_summary": action_summary,
                        "tool": tool_name,
                        "patch_id": patch_id,
                    },
                )

        elif action in ("approve", "valider"):
            if not patch_id or is_generic_or_empty(str(patch_id), min_length=1):
                return ToolResult.needs_user(
                    user_message="L'identifiant du patch à valider est manquant.",
                    question="Quel est l'identifiant du patch système que vous souhaitez approuver ?",
                    evidence="Validation rejetée : patch_id manquant pour approbation",
                    data={"field": "patch_id"},
                )

    return None


# ─── Surveillance multi-actions & injection de rappel ───────────────────────────

ACTION_TRIGGER_PATTERNS = [
    r"\b(?:envoie|envoyer|expédie|expédier)\b.*\b(?:mail|email|courriel)\b",
    r"\b(?:prépare|préparer|crée|créer|génère|générer|fais|faire)\b.*\b(?:présentation|slides?|diapo|diaporama)\b",
    r"\b(?:ajoute|ajouter|mets|mettre|programme|programmer|note|noter)\b.*\b(?:agenda|calendrier|rdv|rendez-vous|réunion)\b",
    r"\b(?:supprime|supprimer|annule|annuler|efface|effacer)\b",
    r"\b(?:télécharge|télécharger|cherche|chercher)\b.*\b(?:livre|ebook|fichier|document)\b",
    r"\b(?:lance|lancer|exécute|exécuter|répare|réparer)\b",
]

_MULTI_ACTION_REMINDER_STATE: Dict[str, bool] = {}


def count_actions_in_text(text: str) -> int:
    """Compte le nombre d'intentions d'actions distinctes dans un texte utilisateur."""
    if not text or not isinstance(text, str):
        return 0
    t = text.lower()
    count = 0
    for pat in ACTION_TRIGGER_PATTERNS:
        if re.search(pat, t):
            count += 1
    # Détection de conjonctions d'actions explicites : "puis", "ensuite", "et aussi", "et après"
    conjunctions = [" puis ", " ensuite ", " et après ", " et ensuite ", " après ça "]
    for c in conjunctions:
        if c in t:
            count = max(count, 2)
            break
    return count


def should_inject_multi_action_reminder(
    transcript: Any,
    active_plan: Any = None,
    had_tool_call: bool = False,
    session_id: str = "default",
) -> Tuple[bool, Optional[str]]:
    """Vérifie si le modèle répond sans outil alors qu'au moins 2 actions sont requises.
    
    Règle : Si le transcript ou le plan contient ≥ 2 actions et que le modèle répond sans outil
            -> injecter un rappel système une seule fois.
    """
    if had_tool_call:
        _MULTI_ACTION_REMINDER_STATE[session_id] = False
        return False, None

    if _MULTI_ACTION_REMINDER_STATE.get(session_id, False):
        return False, None

    actions_count = 0

    # 1. Vérification dans le plan actif
    if active_plan:
        if hasattr(active_plan, "steps") and isinstance(active_plan.steps, list):
            actions_count = len(active_plan.steps)
        elif hasattr(active_plan, "pending_steps") and callable(active_plan.pending_steps):
            actions_count = len(active_plan.pending_steps())

    # 2. Vérification dans le transcript utilisateur
    if actions_count < 2:
        user_texts: List[str] = []
        if isinstance(transcript, str):
            user_texts.append(transcript)
        elif isinstance(transcript, list):
            for item in transcript:
                if isinstance(item, str):
                    user_texts.append(item)
                elif isinstance(item, dict) and item.get("role") in ("user", "human"):
                    user_texts.append(str(item.get("text") or ""))
        combined_text = " ".join(user_texts[-3:]) if user_texts else ""
        actions_count = max(actions_count, count_actions_in_text(combined_text))

    if actions_count >= 2:
        _MULTI_ACTION_REMINDER_STATE[session_id] = True
        reminder_text = (
            "[RAPPEL SYSTÈME OBLIGATOIRE] La demande utilisateur contient au moins 2 actions concrètes. "
            "Tu dois impérativement appeler les outils dédiés correspondants au lieu de te contenter d'une réponse purement orale."
        )
        return True, reminder_text

    return False, None


def reset_multi_action_reminder_state(session_id: str = "default") -> None:
    """Réinitialise l'état du rappel multi-actions pour une nouvelle interaction."""
    _MULTI_ACTION_REMINDER_STATE[session_id] = False
