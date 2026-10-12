"""tests/test_post_verification.py
Tests de vérification post-action stricts pour les outils J.A.R.V.I.S. (mail, slides, calendrier).
Garantit l'interdiction inviolable de déclarer un succès sans preuve matérielle (verified=False sans vérification réussie).
"""

from unittest.mock import AsyncMock, patch
import pytest

from core.tools.dispatcher import dispatch_tool
from core.tools.verifier import (
    verify_email_sent,
    verify_presentation_slides,
    verify_calendar_event,
)
from services.slides_service import PresentationVerificationResult


@pytest.mark.asyncio
async def test_email_post_verification_failure_yields_verified_false():
    """Vérifie que si l'email n'est pas trouvé dans les envoyés, verified=False est strict."""
    # Mock de l'envoi de mail réussissant techniquement au niveau SMTP
    mock_send = AsyncMock(return_value={"status": "sent", "email_id": "test_mail_1", "message_id": "<abc@stark>"})
    # Mock de la vérification IMAP échouant (non présent dans Sent)
    mock_verify = AsyncMock(return_value=(False, "E-mail non retrouvé dans la boîte d'envoi", "sent_box_empty"))

    with patch("core.tools.dispatcher.send_email_async", mock_send), \
         patch("core.tools.dispatcher.verify_email_sent", mock_verify):

        resp = await dispatch_tool(
            name="send_email",
            args={
                "subject": "Rapport opérationnel",
                "body": "Bonjour, rapport en pièce jointe.",
                "to_email": "pierre@stark.com",
                "confirmed_by_user": True,
            },
        )

        assert resp.get("verified") is False
        assert resp.get("status") in ("done", "failed", "error")


@pytest.mark.asyncio
async def test_email_post_verification_success_yields_verified_true():
    """Vérifie que la présence avérée dans les envoyés valide verified=True."""
    mock_send = AsyncMock(return_value={"status": "sent", "email_id": "mail_ok_123", "message_id": "<ok@stark>"})
    mock_verify = AsyncMock(return_value=(True, "Message-ID vérifié dans dossier Sent IMAP", None))

    with patch("core.tools.dispatcher.send_email_async", mock_send), \
         patch("core.tools.dispatcher.verify_email_sent", mock_verify):

        resp = await dispatch_tool(
            name="send_email",
            args={
                "subject": "Rapport opérationnel",
                "body": "Bonjour, rapport en pièce jointe.",
                "to_email": "pierre@stark.com",
                "confirmed_by_user": True,
            },
        )

        assert resp.get("verified") is True
        assert resp.get("status") == "done"
        assert "IMAP" in resp.get("evidence", "")


@pytest.mark.asyncio
async def test_slides_verification_real_count():
    """Vérifie que le nombre réel de slides est lu via l'API et conditionne le résultat."""
    # Simulation du retour API Google Slides : 4 diapositives générées
    mock_verify = AsyncMock(return_value=PresentationVerificationResult(
        verified=True,
        count=4,
        evidence="https://docs.google.com/presentation/d/pres_123",
        titles=["Intro", "Plan", "Architecture", "Conclusion"]
    ))

    with patch("services.slides_service.slides_service.verify_presentation", mock_verify):
        res = await verify_presentation_slides("pres_123", min_slides=1)
        assert res[0] is True
        assert res[1] == 4
        assert "pres_123" in res[2]


@pytest.mark.asyncio
async def test_calendar_creation_verification_failure():
    """Vérifie que la création d'un événement non relu dans l'agenda échoue avec verified=False."""
    mock_n8n_exec = AsyncMock(return_value={"status": "success", "event_id": "ev_test_fail", "result": {"event_id": "ev_test_fail"}})
    mock_verify = AsyncMock(return_value=(False, "Événement introuvable après création", None))

    with patch("services.automation.executer_action_externe", mock_n8n_exec), \
         patch("core.tools.dispatcher.verify_calendar_event", mock_verify):

        resp = await dispatch_tool(
            name="manage_calendar_event",
            args={
                "action": "creer",
                "titre": "Déjeuner de travail",
                "date_debut": "2026-10-02T12:30:00",
                "confirmed_by_user": True,
            },
        )

        assert resp.get("verified") is False
        assert resp.get("status") in ("failed", "error")


@pytest.mark.asyncio
async def test_calendar_deletion_verification():
    """Vérifie que la suppression d'un événement est attestée par sa disparition effective."""
    mock_n8n_exec = AsyncMock(return_value={"status": "success", "result": {}})

    # 1. Si après suppression l'événement est toujours présent -> verified=False
    mock_still_found = AsyncMock(return_value=(True, "Événement toujours présent", "ev_del_1"))
    with patch("services.automation.executer_action_externe", mock_n8n_exec), \
         patch("core.tools.dispatcher.verify_calendar_event", mock_still_found):
        resp = await dispatch_tool(
            name="manage_calendar_event",
            args={
                "action": "supprimer",
                "titre": "RDV Annulé",
                "confirmed_by_user": True,
            },
        )
        assert resp.get("verified") is False
        assert resp.get("status") in ("failed", "error")

    # 2. Si après suppression l'événement n'est plus trouvé -> verified=True
    mock_absent = AsyncMock(return_value=(False, "Événement non retrouvé", None))
    with patch("services.automation.executer_action_externe", mock_n8n_exec), \
         patch("core.tools.dispatcher.verify_calendar_event", mock_absent):
        resp_ok = await dispatch_tool(
            name="manage_calendar_event",
            args={
                "action": "supprimer",
                "titre": "RDV Annulé",
                "confirmed_by_user": True,
            },
        )
        assert resp_ok.get("verified") is True
        assert resp_ok.get("status") == "done"
