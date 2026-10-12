"""tests/test_arg_validator.py
Tests unitaires de validation stricte des arguments, confirmation obligatoire
et détection multi-actions sans appel API payant.
"""

import pytest
from core.tools.arg_validator import (
    validate_tool_arguments,
    count_actions_in_text,
    should_inject_multi_action_reminder,
    reset_multi_action_reminder_state,
)
from core.tools.result import ToolResult


def test_reject_empty_arguments():
    """Vérifie le rejet systématique d'arguments vides sur les outils sensibles."""
    for tool in ("send_email", "generate_presentation", "manage_calendar_event", "system_self_healing"):
        res = validate_tool_arguments(tool, {})
        assert isinstance(res, ToolResult), f"L'outil {tool} doit retourner un ToolResult"
        assert res.status == "needs_user"
        assert res.data.get("question") or getattr(res, "question", None) is not None or "Quelles sont" in res.user_message


def test_reject_generic_arguments_email():
    """Vérifie le rejet d'objets ou corps de mail génériques ou trop courts."""
    # Objet générique "test"
    res1 = validate_tool_arguments("send_email", {"subject": "test", "body": "Contenu du message valide"})
    assert res1.status == "needs_user"
    assert "objet" in res1.data.get("question", "").lower()

    # Corps de mail vide
    res2 = validate_tool_arguments("send_email", {"subject": "Rapport financier Q3", "body": ""})
    assert res2.status == "needs_user"
    assert "contenu" in res2.data.get("question", "").lower()


def test_email_requires_user_confirmation():
    """Vérifie qu'un envoi de mail valide nécessite confirmed_by_user=True."""
    # Arguments valides mais non confirmés
    args = {
        "subject": "Rapport d'audit trimestriel",
        "body": "Bonjour Pierre, voici les chiffres consolidés du trimestre.",
        "to_email": "direction@stark.com",
        "confirmed_by_user": False,
    }
    res = validate_tool_arguments("send_email", args)
    assert res.status == "needs_user"
    assert res.data.get("requires_confirmation") is True
    assert "Rapport d'audit trimestriel" in res.data.get("action_summary", "")

    # Avec confirmation explicite -> autorisé (None)
    args["confirmed_by_user"] = True
    assert validate_tool_arguments("send_email", args) is None


def test_reject_generic_arguments_presentation():
    """Vérifie le rejet de présentations aux sujets ou consignes génériques."""
    # Sujet "présentation"
    res1 = validate_tool_arguments("generate_presentation", {"sujet": "Présentation", "consignes": "Faire 5 slides"})
    assert res1.status == "needs_user"
    assert "sujet" in res1.data.get("question", "").lower()

    # Consignes génériques "test"
    res2 = validate_tool_arguments("generate_presentation", {"sujet": "Intelligence Artificielle Générative", "consignes": "test"})
    assert res2.status == "needs_user"
    assert "consignes" in res2.data.get("question", "").lower()

    # Présentation valide
    valid_args = {
        "sujet": "Architecture Microservices J.A.R.V.I.S.",
        "consignes": "Présenter les modules voix, supervision et runner agentique sur 6 diapositives.",
    }
    assert validate_tool_arguments("generate_presentation", valid_args) is None


def test_calendar_validation_and_confirmation():
    """Vérifie la validation du calendrier et la confirmation sur suppression."""
    # Création sans date
    res_creer = validate_tool_arguments("manage_calendar_event", {"action": "creer", "titre": "RDV Dentiste"})
    assert res_creer.status == "needs_user"
    assert "date" in res_creer.data.get("question", "").lower()

    # Suppression sans confirmation -> needs_user avec résumé
    res_suppr = validate_tool_arguments(
        "manage_calendar_event",
        {"action": "supprimer", "titre": "Point Synchronisation", "confirmed_by_user": False},
    )
    assert res_suppr.status == "needs_user"
    assert res_suppr.data.get("requires_confirmation") is True
    assert "Point Synchronisation" in res_suppr.data.get("action_summary", "")

    # Suppression avec confirmation -> autorisé
    assert validate_tool_arguments(
        "manage_calendar_event",
        {"action": "supprimer", "titre": "Point Synchronisation", "confirmed_by_user": True},
    ) is None


def test_system_healing_validation_and_confirmation():
    """Vérifie l'obligation de motif précis et confirmation pour l'auto-guérison."""
    # Motif vide ou générique "bug"
    res_generic = validate_tool_arguments("system_self_healing", {"action": "heal", "motif": "bug"})
    assert res_generic.status == "needs_user"

    # Action non confirmée -> needs_user avec résumé
    res_unconfirmed = validate_tool_arguments(
        "system_self_healing",
        {"action": "heal", "motif": "Exception 500 sur le router vocal", "confirmed_by_user": False},
    )
    assert res_unconfirmed.status == "needs_user"
    assert res_unconfirmed.data.get("requires_confirmation") is True

    # Action confirmée -> autorisé
    assert validate_tool_arguments(
        "system_self_healing",
        {"action": "heal", "motif": "Exception 500 sur le router vocal", "confirmed_by_user": True},
    ) is None


def test_multi_action_counting():
    """Vérifie le comptage d'actions dans un message textuel."""
    assert count_actions_in_text("Quelle heure est-il ?") == 0
    assert count_actions_in_text("Crée une présentation sur Rome") == 1
    # 2 actions reliées par puis ou verbes d'actions
    msg_multi = "Génère une présentation sur l'IA puis envoie un mail à Pierre avec le lien"
    assert count_actions_in_text(msg_multi) >= 2


def test_multi_action_reminder_injection_once():
    """Vérifie l'injection unique du rappel système si le modèle répond sans outil."""
    sess_id = "test_multi_action_session"
    reset_multi_action_reminder_state(sess_id)

    transcript = [
        {"role": "user", "text": "Crée une présentation sur le quantique puis programme une réunion demain à 14h"}
    ]

    # 1. Le modèle répond sans outil -> injection du rappel requise
    inject, prompt = should_inject_multi_action_reminder(transcript=transcript, had_tool_call=False, session_id=sess_id)
    assert inject is True
    assert "[RAPPEL SYSTÈME OBLIGATOIRE]" in prompt

    # 2. Deuxième appel sans outil -> NE DOIT PAS ré-injecter (une seule fois)
    inject2, prompt2 = should_inject_multi_action_reminder(transcript=transcript, had_tool_call=False, session_id=sess_id)
    assert inject2 is False
    assert prompt2 is None

    # 3. Si un tool call intervient -> reset de l'état
    should_inject_multi_action_reminder(transcript=transcript, had_tool_call=True, session_id=sess_id)

    # Réinitialisation
    reset_multi_action_reminder_state(sess_id)
