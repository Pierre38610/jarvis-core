"""Tests unitaires pour la résolution universelle des pièces jointes d'e-mail dans J.A.R.V.I.S."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ajout du dossier racine au PATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.email_service import resolve_attachment_path, send_email, DOWNLOADS_DIR, EBOOKS_DIR


class TestEmailAttachments(unittest.TestCase):

    def setUp(self):
        # Création de fichiers temporaires de test dans downloads et ebooks
        self.test_txt_path = os.path.join(DOWNLOADS_DIR, "test_document_sample.txt")
        with open(self.test_txt_path, "w", encoding="utf-8") as f:
            f.write("Contenu de test pour pièce jointe J.A.R.V.I.S.")

        self.test_pdf_name = "rapport_mensuel_2026.pdf"
        self.test_pdf_path = os.path.join(DOWNLOADS_DIR, self.test_pdf_name)
        with open(self.test_pdf_path, "w", encoding="utf-8") as f:
            f.write("%PDF-1.4 Mock PDF content")

    def tearDown(self):
        # Nettoyage
        for p in (self.test_txt_path, self.test_pdf_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_resolve_exact_basename(self):
        """Vérifie la résolution par nom de fichier simple dans downloads/."""
        res = resolve_attachment_path("test_document_sample.txt")
        self.assertIsNotNone(res)
        self.assertTrue(os.path.exists(res))
        self.assertEqual(os.path.abspath(res), os.path.abspath(self.test_txt_path))

    def test_resolve_virtual_prefix(self):
        """Vérifie la résolution avec préfixe virtuel /downloads/."""
        res = resolve_attachment_path("/downloads/test_document_sample.txt")
        self.assertIsNotNone(res)
        self.assertEqual(os.path.abspath(res), os.path.abspath(self.test_txt_path))

    def test_resolve_without_extension(self):
        """Vérifie la résolution automatique de l'extension omise (.pdf)."""
        res = resolve_attachment_path("rapport_mensuel_2026")
        self.assertIsNotNone(res)
        self.assertTrue(res.endswith(".pdf"))
        self.assertEqual(os.path.abspath(res), os.path.abspath(self.test_pdf_path))

    def test_resolve_case_insensitive(self):
        """Vérifie la résolution insensible à la casse."""
        res = resolve_attachment_path("TEST_DOCUMENT_SAMPLE.TXT")
        self.assertIsNotNone(res)
        self.assertEqual(os.path.abspath(res), os.path.abspath(self.test_txt_path))

    def test_resolve_keyword_latest(self):
        """Vérifie la résolution du mot-clé 'latest' ou 'dernier'."""
        res = resolve_attachment_path("latest")
        self.assertIsNotNone(res)
        self.assertTrue(os.path.exists(res))

    def test_resolve_substring_tokens(self):
        """Vérifie la résolution par mots-clés séparés (ex: 'rapport mensuel')."""
        res = resolve_attachment_path("rapport mensuel")
        self.assertIsNotNone(res)
        self.assertEqual(os.path.abspath(res), os.path.abspath(self.test_pdf_path))

    @patch("smtplib.SMTP")
    def test_send_email_string_attachment_no_char_split(self, mock_smtp):
        """Vérifie qu'un chemin transmis sous forme de chaîne simple n'est pas itéré caractère par caractère."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        # Test avec une chaîne directe au lieu d'une liste
        res = send_email(
            subject="Test Envoi Document",
            body="Veuillez trouver ci-joint le document.",
            to_email="pierrecassagnettes@gmail.com",
            attachments="test_document_sample.txt"
        )

        self.assertIn(res.get("status"), ("sent", "archived_in_outbox"))
        self.assertEqual(res.get("attachments_count"), 1)
        self.assertIn("test_document_sample.txt", res.get("attachments", []))

    @patch("smtplib.SMTP")
    def test_send_email_attachment_not_found_safeguard(self, mock_smtp):
        """Vérifie que si une pièce jointe demandée n'existe pas, l'envoi est bloqué et renvoie attachment_not_found."""
        res = send_email(
            subject="Test Document Inexistant",
            body="Test corps",
            to_email="pierrecassagnettes@gmail.com",
            attachments=["fichier_absolument_inexistant_xyz_12345.pdf"]
        )

        self.assertEqual(res.get("status"), "attachment_not_found")
        self.assertEqual(res.get("attachments_count"), 0)
        self.assertIn("fichier_absolument_inexistant_xyz_12345.pdf", res.get("missing_attachments", []))


if __name__ == "__main__":
    unittest.main()
