"""tests/unit/test_automation_n8n.py
Tests unitaires pour services.automation.
Vérifie les appels HTTP vers les webhooks n8n (succès 200, codes 500, timeouts)
et les imports de workflows via un client HTTP mocké (aucune requête réseau réelle).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from services.automation import (
    trigger_webhook,
    executer_action_externe,
    import_workflow_from_json,
    N8N_BASE_URL,
)


@pytest.mark.asyncio
class TestTriggerWebhook:
    """Tests directs de trigger_webhook avec simulation httpx.AsyncClient."""

    async def test_trigger_webhook_success_200_json(self):
        """Réponse 200 avec payload JSON valide."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"calendar_event_created": True, "id": "evt_789"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_cls, \
             patch("services.automation.N8N_WEBHOOK_SECRET", "stark_secret_key"):
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await trigger_webhook("samsung-calendar", {"title": "Réunion Avengers", "time": "14:00"})

            assert result == {"calendar_event_created": True, "id": "evt_789"}
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == f"{N8N_BASE_URL}/webhook/samsung-calendar"
            assert call_args[1]["json"] == {"title": "Réunion Avengers", "time": "14:00"}
            assert call_args[1]["headers"]["X-Jarvis-Secret"] == "stark_secret_key"

    async def test_trigger_webhook_success_200_text_fallback(self):
        """Réponse 200 avec texte brut non JSON."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "OK Workflow Exécuté"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await trigger_webhook("test-action", {})
            assert result == {"raw": "OK Workflow Exécuté"}

    async def test_trigger_webhook_http_500_error_raises_status_error(self):
        """Une réponse HTTP 500 lève httpx.HTTPStatusError."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error in n8n node"
        
        request = httpx.Request("POST", f"{N8N_BASE_URL}/webhook/error-test")
        status_error = httpx.HTTPStatusError("500 Internal Error", request=request, response=mock_response)
        mock_response.raise_for_status.side_effect = status_error

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await trigger_webhook("error-test", {})

    async def test_trigger_webhook_timeout_raises_timeout_exception(self):
        """Un dépassement de délai lève httpx.TimeoutException."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out after 30s")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(httpx.TimeoutException):
                await trigger_webhook("slow-workflow", {})


@pytest.mark.asyncio
class TestExecuterActionExterne:
    """Tests du Tool Call Gemini Live : executer_action_externe()."""

    async def test_executer_action_externe_success(self):
        """Exécution réussie d'une action externe."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_trigger:
            mock_trigger.return_value = {"message_sent": True, "recipient": "Pepper"}

            res = await executer_action_externe(
                action_name="send-telegram-msg",
                parametres={"text": "Jarvis en ligne"}
            )

            assert res["status"] == "success"
            assert res["action"] == "send-telegram-msg"
            assert res["result"] == {"message_sent": True, "recipient": "Pepper"}
            mock_trigger.assert_called_once_with(action_name="send-telegram-msg", payload={"text": "Jarvis en ligne"})

    async def test_executer_action_externe_missing_action_name(self):
        """Paramètre action_name manquant renvoie une erreur sans appel réseau."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_trigger:
            res = await executer_action_externe(action_name="")
            assert res["status"] == "error"
            assert "manquant" in res["error"]
            mock_trigger.assert_not_called()

    async def test_executer_action_externe_handles_500_gracefully(self):
        """Erreur HTTP 500 capturée et restituée sous forme de dict d'erreur lisible."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Node [Telegram] execution failed: Bad Gateway"
        request = httpx.Request("POST", "http://test")
        error = httpx.HTTPStatusError("500 Error", request=request, response=mock_response)

        with patch("services.automation.trigger_webhook", side_effect=error):
            res = await executer_action_externe(action_name="failed-webhook")

            assert res["status"] == "error"
            assert res["action"] == "failed-webhook"
            assert "Erreur HTTP 500" in res["error"]
            assert "Telegram" in res["error"]

    async def test_executer_action_externe_handles_timeout_gracefully(self):
        """Timeout capturé et explicité pour l'utilisateur sans crasher l'agent."""
        with patch("services.automation.trigger_webhook", side_effect=httpx.TimeoutException("Timeout")):
            res = await executer_action_externe(action_name="stuck-node")

            assert res["status"] == "error"
            assert res["action"] == "stuck-node"
            assert "Timeout" in res["error"]
            assert "actif" in res["error"]

    async def test_executer_action_externe_handles_connection_error_gracefully(self):
        """Erreur de connexion (n8n offline) capturée et explicitée en français."""
        request = httpx.Request("POST", "http://127.0.0.1:5678/webhook/test")
        with patch("services.automation.trigger_webhook", side_effect=httpx.ConnectError("Connection refused", request=request)):
            res = await executer_action_externe(action_name="document-spreadsheet")

            assert res["status"] == "error"
            assert "Connexion impossible" in res["error"]
            assert "Docker n8n" in res["error"]

    async def test_executer_action_externe_document_spreadsheet(self):
        """Action document-spreadsheet avec normalisation automatique du nom de fichier .xlsx."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_trigger:
            mock_trigger.return_value = {"status": "success", "file": "compta.xlsx"}

            res = await executer_action_externe(
                action_name="generer_fichier_tableur",
                parametres={
                    "nom_fichier": "compta",
                    "colonnes": ["Date", "Montant"],
                    "lignes": [["2026-09-26", "100"]]
                }
            )

            assert res["status"] == "success"
            assert res["action"] == "document-spreadsheet"
            mock_trigger.assert_called_once()
            called_action, called_payload = mock_trigger.call_args[1].get("action_name", mock_trigger.call_args[0][0] if mock_trigger.call_args[0] else None), mock_trigger.call_args[1].get("payload", mock_trigger.call_args[0][1] if len(mock_trigger.call_args[0]) > 1 else None)
            assert called_action == "document-spreadsheet"
            assert called_payload["nom_fichier"] == "compta.xlsx"
            assert called_payload["colonnes"] == ["Date", "Montant"]

    async def test_executer_action_externe_document_slides(self):
        """Action document-slides avec thème et slides structurées."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_trigger:
            mock_trigger.return_value = {"status": "success", "presentation_id": "pres_123"}

            res = await executer_action_externe(
                action_name="generer_presentation",
                parametres={
                    "titre": "Pitch Jarvis",
                    "theme": "dark",
                    "slides": [{"titre_slide": "Intro", "points": ["P1", "P2"]}]
                }
            )

            assert res["status"] == "success"
            assert res["action"] == "document-slides"
            mock_trigger.assert_called_once()
            called_payload = mock_trigger.call_args[1].get("payload") or mock_trigger.call_args[0][1]
            assert called_payload["titre"] == "Pitch Jarvis"
            assert called_payload["theme"] == "dark"
            assert len(called_payload["slides"]) == 1

    async def test_executer_action_externe_notion_entry(self):
        """Action notion-entry avec type d'entrée, titre, contenu et tags."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_trigger:
            mock_trigger.return_value = {"status": "success", "notion_id": "notion_456"}

            res = await executer_action_externe(
                action_name="notion_enregistrer",
                parametres={
                    "type_entree": "todo",
                    "titre": "Acheter composants",
                    "contenu": "Microphone 24kHz pour Jarvis",
                    "tags": ["Urgent", "Hardware"]
                }
            )

            assert res["status"] == "success"
            assert res["action"] == "notion-entry"
            mock_trigger.assert_called_once()
            called_payload = mock_trigger.call_args[1].get("payload") or mock_trigger.call_args[0][1]
            assert called_payload["type_entree"] == "todo"
            assert called_payload["titre"] == "Acheter composants"
            assert called_payload["tags"] == ["Urgent", "Hardware"]


class TestImportWorkflowFromJson:
    """Tests de la méthode import_workflow_from_json via mock Docker CLI."""

    def test_import_workflow_nominal_success(self):
        workflow_data = {"id": "wkf_123", "name": "Sync Calendar", "nodes": []}

        with patch("subprocess.run") as mock_subproc:
            # Mock des succès pour docker cp, n8n import, docker rm, et n8n publish
            mock_subproc.return_value = MagicMock(returncode=0, stdout="Workflow wkf_123 imported successfully", stderr="")

            success = import_workflow_from_json(workflow_data)
            assert success is True
            assert mock_subproc.call_count >= 2

    def test_import_workflow_list_of_workflows_success(self):
        """Importation d'une liste de workflows (comme documents_suite.json)."""
        workflows = [
            {"id": "jarvis-doc-spreadsheet", "name": "Jarvis - Document Spreadsheet", "nodes": []},
            {"id": "jarvis-doc-slides", "name": "Jarvis - Document Slides", "nodes": []},
            {"id": "jarvis-notion-entry", "name": "Jarvis - Notion Entry", "nodes": []},
        ]

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = MagicMock(returncode=0, stdout="Imported", stderr="")

            success = import_workflow_from_json(workflows)
            assert success is True
            # Chaque workflow a été importé
            assert mock_subproc.call_count >= 6

    def test_import_workflow_docker_cp_failure(self):
        workflow_data = {"id": "wkf_fail", "nodes": []}

        with patch("subprocess.run") as mock_subproc:
            # Échec lors du docker cp
            mock_subproc.return_value = MagicMock(returncode=1, stdout="", stderr="Error: No such container: jarvis_n8n")

            success = import_workflow_from_json(workflow_data)
            assert success is False


@pytest.mark.asyncio
class TestDispatchDocumentTools:
    """Tests des 3 nouveaux outils du pôle documentaire dans core.tools.dispatcher."""

    async def test_dispatch_generer_fichier_tableur_non_blocking(self):
        from core.tools.dispatcher import dispatch_tool
        mock_ws = AsyncMock()
        mock_session = AsyncMock()

        with patch("services.automation.executer_action_externe", new_callable=AsyncMock) as mock_n8n:
            mock_n8n.return_value = {"status": "success", "result": {"file": "compta.xlsx"}}
            resp = await dispatch_tool(
                name="generer_fichier_tableur",
                args={
                    "nom_fichier": "compta.xlsx",
                    "colonnes": ["A", "B"],
                    "lignes": [["1", "2"]],
                    "description": "Comptabilité"
                },
                websocket=mock_ws,
                session=mock_session,
                is_paid_live=False,
                live_display_label="Gratuit"
            )

            assert resp["status"] == "lance_en_arriere_plan"
            assert resp["action"] == "generer_fichier_tableur"
            assert resp["nom_fichier"] == "compta.xlsx"
            assert "instruction_to_jarvis" in resp

    async def test_dispatch_generer_presentation_non_blocking(self):
        from core.tools.dispatcher import dispatch_tool
        mock_ws = AsyncMock()
        mock_session = AsyncMock()

        with patch("services.automation.executer_action_externe", new_callable=AsyncMock) as mock_n8n:
            mock_n8n.return_value = {"status": "success", "result": {"presentation_id": "123"}}
            resp = await dispatch_tool(
                name="generer_presentation",
                args={
                    "titre": "Projet Stark",
                    "theme": "stark",
                    "slides": [{"titre_slide": "S1", "points": ["P1"]}]
                },
                websocket=mock_ws,
                session=mock_session,
                is_paid_live=False,
                live_display_label="Gratuit"
            )

            assert resp["status"] == "lance_en_arriere_plan"
            assert resp["action"] == "generer_presentation"
            assert resp["titre"] == "Projet Stark"
            assert resp["slides_count"] == 1

    async def test_dispatch_notion_enregistrer_non_blocking(self):
        from core.tools.dispatcher import dispatch_tool
        mock_ws = AsyncMock()
        mock_session = AsyncMock()

        with patch("services.automation.executer_action_externe", new_callable=AsyncMock) as mock_n8n:
            mock_n8n.return_value = {"status": "success", "result": {"notion_id": "456"}}
            resp = await dispatch_tool(
                name="notion_enregistrer",
                args={
                    "type_entree": "note",
                    "titre": "Idée Jarvis",
                    "contenu": "Détails note",
                    "tags": ["Dev"]
                },
                websocket=mock_ws,
                session=mock_session,
                is_paid_live=False,
                live_display_label="Gratuit"
            )

            assert resp["status"] == "lance_en_arriere_plan"
            assert resp["action"] == "notion_enregistrer"
            assert resp["titre"] == "Idée Jarvis"


