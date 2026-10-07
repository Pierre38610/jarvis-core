"""tests/unit/test_email_reading.py
Tests unitaires complets pour la lecture et le parsing des e-mails IMAP dans email_service.py.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import email
from email.message import EmailMessage

from services.email_service import (
    read_received_emails,
    read_received_emails_async,
    _clean_email_query,
    _extract_email_body_and_attachments,
)


class TestEmailReading:
    """Tests unitaires pour le service de lecture d'emails."""

    def test_clean_email_query_generic_terms(self):
        """Vérifie que les termes génériques/temporels sont bien neutralisés."""
        assert _clean_email_query("dernier") == (None, False)
        assert _clean_email_query("derniers emails") == (None, False)
        assert _clean_email_query("mes mails") == (None, False)
        assert _clean_email_query("latest") == (None, False)
        assert _clean_email_query("inbox") == (None, False)
        assert _clean_email_query("") == (None, False)
        assert _clean_email_query(None) == (None, False)

    def test_clean_email_query_unread(self):
        """Vérifie la détection explicite des mots-clés de non-lecture."""
        assert _clean_email_query("non lus") == (None, True)
        assert _clean_email_query("unread") == (None, True)
        assert _clean_email_query("nouveaux") == (None, True)

    def test_clean_email_query_specific_sender_or_subject(self):
        """Vérifie le nettoyage des préfixes de requête de recherche ciblée."""
        assert _clean_email_query("de Pierre") == ("Pierre", False)
        assert _clean_email_query("from Google") == ("Google", False)
        assert _clean_email_query("sujet Facture") == ("Facture", False)
        assert _clean_email_query("GitHub") == ("GitHub", False)

    def test_extract_email_body_html_and_text(self):
        """Vérifie l'extraction et le nettoyage HTML/texte avec entités HTML."""
        msg = EmailMessage()
        msg["Subject"] = "Test HTML"
        msg["From"] = "Sender <sender@example.com>"
        msg.set_content("Texte brut de repli")
        msg.add_alternative("<p>Bonjour Pierre,&nbsp;voici votre facture &amp; re&ccedil;u.</p>", subtype="html")

        extracted = _extract_email_body_and_attachments(msg)
        assert "Texte brut de repli" in extracted["body_text"]
        assert extracted["attachments"] == []

    def test_extract_email_html_only(self):
        """Vérifie l'extraction quand seul le HTML est disponible sans plain text."""
        msg = EmailMessage()
        msg["Subject"] = "HTML Only"
        msg.set_content("<style>body{color:red;}</style><div>Bonjour <strong>Pierre</strong> &euro; 100</div>", subtype="html")

        extracted = _extract_email_body_and_attachments(msg)
        assert "Bonjour Pierre € 100" in extracted["body_text"]
        assert "style" not in extracted["body_text"]

    @patch("services.email_service.IMAP_USER", "test@gmail.com")
    @patch("services.email_service.IMAP_PASSWORD", "app_password_123")
    @patch("imaplib.IMAP4_SSL")
    def test_read_received_emails_nominal(self, mock_imap_ssl):
        """Vérifie la récupération nominale des e-mails récents via IMAP."""
        mock_mail = MagicMock()
        mock_imap_ssl.return_value = mock_mail
        mock_mail.select.return_value = ("OK", [b"10"])
        mock_mail.search.return_value = ("OK", [b"1 2 3"])

        # Création d'un message simulé
        test_msg = EmailMessage()
        test_msg["Subject"] = "Validation du projet Stark"
        test_msg["From"] = "Tony Stark <tony@stark.ai>"
        test_msg["Date"] = "Wed, 7 Oct 2026 14:00:00 +0200"
        test_msg.set_content("Le prototype J.A.R.V.I.S. est prêt.")

        raw_bytes = test_msg.as_bytes()
        mock_mail.fetch.return_value = ("OK", [(b"3 (BODY.PEEK[] {123}", raw_bytes), b")"])

        res = read_received_emails(max_count=2, query="Stark")
        assert res["status"] == "ok"
        assert res["count"] == 2
        assert res["emails"][0]["subject"] == "Validation du projet Stark"
        assert res["emails"][0]["from"] == "Tony Stark <tony@stark.ai>"
        assert "Le prototype J.A.R.V.I.S. est prêt." in res["emails"][0]["snippet"]

    @patch("services.email_service.IMAP_USER", "")
    @patch("services.email_service.SMTP_USER", "")
    @patch("services.email_service.DEFAULT_RECIPIENT_EMAIL", "")
    @patch("services.email_service.IMAP_PASSWORD", "")
    @patch("services.email_service.SMTP_PASSWORD", "")
    def test_read_received_emails_missing_credentials(self):
        """Vérifie l'erreur explicite quand aucun identifiant n'est configuré."""
        res = read_received_emails(max_count=5)
        assert res["status"] == "error"
        assert "non configurés" in res["message"]
        assert res["emails"] == []

    @patch("services.email_service.IMAP_USER", "test@gmail.com")
    @patch("services.email_service.IMAP_PASSWORD", "app_password_123")
    @patch("imaplib.IMAP4_SSL")
    def test_read_received_emails_auth_failure(self, mock_imap_ssl):
        """Vérifie la gestion d'erreur propre en cas d'authentification invalide."""
        mock_mail = MagicMock()
        mock_imap_ssl.return_value = mock_mail
        mock_mail.login.side_effect = Exception("[AUTHENTICATIONFAILED] Invalid credentials")

        res = read_received_emails(max_count=5)
        assert res["status"] == "error"
        assert "authentification" in res["message"].lower()

    @pytest.mark.asyncio
    @patch("core.tools.dispatcher.read_received_emails_async")
    async def test_dispatch_read_emails_nominal(self, mock_read_async):
        """Vérifie le dispatch de l'outil read_emails par core/tools/dispatcher.py."""
        from core.tools.dispatcher import dispatch_tool

        mock_read_async.return_value = {
            "status": "ok",
            "count": 1,
            "emails": [{
                "id": "1",
                "subject": "Facture Hébergement",
                "from": "Oracle Cloud <billing@oracle.com>",
                "date": "07/10/2026 à 14:30",
                "snippet": "Votre facture mensuelle est disponible.",
                "body": "Votre facture mensuelle est disponible.",
                "attachments": ["facture.pdf"],
                "has_attachments": True
            }]
        }

        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()

        res = await dispatch_tool(
            name="read_emails",
            args={"count": 3, "query": "Oracle"},
            websocket=mock_ws
        )

        assert res["status"] == "done"
        assert res["result"]["status"] == "ok"
        assert "Facture Hébergement" in res["instruction_to_jarvis"]
        assert "Oracle Cloud" in res["instruction_to_jarvis"]

    @pytest.mark.asyncio
    @patch("core.tools.dispatcher.read_received_emails_async")
    async def test_dispatch_read_emails_error(self, mock_read_async):
        """Vérifie le dispatch de l'outil read_emails en cas d'erreur de connexion."""
        from core.tools.dispatcher import dispatch_tool
        from unittest.mock import AsyncMock

        mock_read_async.return_value = {
            "status": "error",
            "message": "Délai de connexion dépassé (timeout)",
            "emails": []
        }

        mock_ws = MagicMock()
        mock_ws.send_text = AsyncMock()

        res = await dispatch_tool(
            name="read_emails",
            args={"count": 5},
            websocket=mock_ws
        )

        assert res["status"] == "failed"
        assert "difficulté" in res["instruction_to_jarvis"]

