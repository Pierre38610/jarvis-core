"""Garde-fous de sécurité pour les actions de navigation Browser Agent Jarvis (S5)."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("jarvis.browser_agent.guards")

# S5 : Mots-clés stricts interdisant le clic automatique (passage à ready_for_user)
PAYMENT_PATTERN = re.compile(
    r"\b(payer|paiement|commander|passer\s+la\s+commande|confirmer\s+(?:la|ma)\s+commande|"
    r"acheter\s+maintenant|valider\s+et\s+payer|pay\s+now|place\s+order|buy\s+now|"
    r"complete\s+purchase|confirm\s+booking)\b",
    re.IGNORECASE,
)

# S5 : Données bancaires et sensibles
SENSITIVE_FIELD_PATTERN = re.compile(r"(carte|card|cvv|cvc|iban)", re.IGNORECASE)
PASSWORD_PATTERN = re.compile(r"input\[password\]|type=[\"']?password[\"']?", re.IGNORECASE)


def _get_element_line(elem_id: Any, snapshot_elements: Any) -> str:
    """Retrouve la ligne ou la description textuelle correspondant à l'élément [id]."""
    if elem_id is None:
        return ""

    target_id_str = str(elem_id).strip()
    bracket_target = f"[{target_id_str}]"
    id_pattern = re.compile(rf"^\[{re.escape(target_id_str)}\]\b")

    lines: List[str] = []
    if isinstance(snapshot_elements, str):
        lines = snapshot_elements.splitlines()
    elif isinstance(snapshot_elements, list):
        for item in snapshot_elements:
            if isinstance(item, str):
                lines.append(item)
            elif isinstance(item, dict):
                if str(item.get("id", "")).strip() == target_id_str:
                    tag = item.get("tag", "element")
                    elem_type = item.get("type", "")
                    placeholder = item.get("placeholder", "")
                    name = item.get("name", "")
                    text = item.get("text", "")
                    parts = [f"[{target_id_str}]", tag]
                    if elem_type:
                        parts.append(f"[{elem_type}]")
                    if placeholder:
                        parts.append(f'placeholder="{placeholder}"')
                    if name:
                        parts.append(f'name="{name}"')
                    if text:
                        parts.append(f'"{text}"')
                    return " ".join(parts)
            else:
                lines.append(str(item))

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(bracket_target) or id_pattern.match(stripped):
            return stripped

    return ""


def check_action(
    action: Dict[str, Any],
    snapshot_elements: Union[List[Any], str, None],
) -> Tuple[bool, str]:
    """Vérifie si une action est autorisée selon les garde-fous de sécurité S5.

    Args:
        action: Dictionnaire de l'action à exécuter (ex: {"type": "click", "id": 3}).
        snapshot_elements: Liste des éléments du snapshot ou représentation textuelle.

    Returns:
        Tuple (allowed: bool, reason: str).
    """
    if not isinstance(action, dict):
        return False, "action_invalide: l'action doit être un dictionnaire"

    act_type = str(action.get("type", "")).strip().lower()

    # 1. Garde-fou goto : uniquement protocoles http:// et https://
    if act_type == "goto":
        url = str(action.get("url", "")).strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, f"goto_forbidden: seuls http et https sont autorisés ({url})"
        return True, ""

    # 2. Garde-fou click : refus strict des clics sur éléments de paiement / commande
    if act_type == "click":
        elem_id = action.get("id")
        elem_line = _get_element_line(elem_id, snapshot_elements)
        if elem_line and PAYMENT_PATTERN.search(elem_line):
            return (
                False,
                f"payment_forbidden: clic interdit sur élément de commande/paiement ({elem_line})",
            )
        return True, ""

    # 3. Garde-fou type : refus de saisie sur mot de passe ou coordonnées bancaires
    if act_type == "type":
        elem_id = action.get("id")
        elem_line = _get_element_line(elem_id, snapshot_elements)
        if elem_line:
            if PASSWORD_PATTERN.search(elem_line):
                return False, "sensitive_data: saisie interdite sur champ mot de passe"
            if SENSITIVE_FIELD_PATTERN.search(elem_line):
                return False, "sensitive_data: saisie interdite sur coordonnées bancaires (carte/cvv/iban)"
        return True, ""

    # 4. Autres actions supportées par S4 (select, scroll, wait, back, extract)
    if act_type in {"select", "scroll", "wait", "back", "extract"}:
        return True, ""

    return False, f"action_inconnue: type d'action non supporté ({act_type})"
