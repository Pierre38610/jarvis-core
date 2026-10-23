"""tests/unit/test_end_to_end_deliverable_mission.py
Validation unitaire complète de la mission de bout en bout de A à Z par l'agent Antigravity :
- Création de livrables : site web, presentation pptx, rapport pdf, tableur xlsx
- Vérification matérielle (> 1024 octets)
- Ouverture sur PC local via open_browser
- Mise à jour du HUD mobile via set_browser_link
- Expédition par e-mail
- Annonce vocale Aoede via voice_injection_queue
- Routage dispatcher pour launch_deep_research et run_agentic_task
"""

import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from services.agentic_dispatcher import (
    execute_end_to_end_deliverable_mission,
    agentic_dispatcher,
)
from core.tools.verifier import verify_mission_deliverable
from core.tools.dispatcher import dispatch_tool


@pytest.mark.asyncio
async def test_execute_mission_website_creation():
    """Valide la création d'un site web de A à Z avec Tailwind, structure et vérification physique."""
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=True), \
         patch("services.local_agent_service.local_agent_service.send_rpc_command", new_callable=AsyncMock, return_value={"status": "success"}) as mock_rpc, \
         patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock) as mock_hud, \
         patch("services.voice_injection_queue.voice_injection_queue.enqueue", new_callable=AsyncMock) as mock_voice:

        res = await execute_end_to_end_deliverable_mission(
            goal="Créer un tableau de bord des énergies renouvelables",
            deliverable_type="website",
            context="Thème Stark, Tailwind CSS et graphiques Chart.js",
            send_email=False,
        )

        assert res["status"] == "completed"
        assert res["verified"] is True
        assert res["deliverable_type"] == "website"
        assert res["main_file"] == "index.html"
        assert os.path.exists(res["main_file_path"])
        assert res["file_size"] > 1024
        assert "/downloads/missions/" in res["public_url"]
        assert mock_rpc.await_count == 1
        rpc_call = mock_rpc.await_args
        assert rpc_call[0][0] == "open_browser"
        assert "/downloads/missions/" in rpc_call[0][1]["url"]
        assert mock_hud.await_count == 1
        assert mock_voice.await_count == 1


@pytest.mark.asyncio
async def test_execute_mission_pptx_creation():
    """Valide la génération autonome d'une présentation PowerPoint multi-slides."""
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock), \
         patch("services.voice_injection_queue.voice_injection_queue.enqueue", new_callable=AsyncMock):

        res = await execute_end_to_end_deliverable_mission(
            goal="Pitch deck levée de fonds IA Générative",
            deliverable_type="pptx",
            context="5 slides professionnelles",
            send_email=False,
        )

        assert res["status"] == "completed"
        assert res["verified"] is True
        assert res["deliverable_type"] == "pptx"
        assert res["main_file"].endswith(".pptx")
        assert os.path.exists(res["main_file_path"])
        assert res["file_size"] > 0
        assert res["opened_on_pc"] is False


@pytest.mark.asyncio
async def test_execute_mission_pdf_creation_and_email():
    """Valide la création d'un rapport PDF et son expédition par e-mail."""
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("services.email_service.send_email_async", new_callable=AsyncMock, return_value={"status": "sent"}) as mock_email, \
         patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock), \
         patch("services.voice_injection_queue.voice_injection_queue.enqueue", new_callable=AsyncMock):

        res = await execute_end_to_end_deliverable_mission(
            goal="Étude de marché sur les semi-conducteurs neuromorphiques",
            deliverable_type="pdf",
            context="Dossier technique complet",
            send_email=True,
            target_email="pierre@example.com",
        )

        assert res["status"] == "completed"
        assert res["verified"] is True
        assert res["deliverable_type"] == "pdf"
        assert os.path.exists(res["main_file_path"])
        assert res["file_size"] > 1024
        assert res["email_sent"] is True
        assert mock_email.await_count == 1
        assert mock_email.await_args.kwargs["to_email"] == "pierre@example.com"
        assert len(mock_email.await_args.kwargs["attachments"]) == 1


@pytest.mark.asyncio
async def test_execute_mission_xlsx_creation():
    """Valide la création autonome d'un tableur Excel dynamique avec formules."""
    with patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("services.browser_agent.loop.set_browser_link", new_callable=AsyncMock), \
         patch("services.voice_injection_queue.voice_injection_queue.enqueue", new_callable=AsyncMock):

        res = await execute_end_to_end_deliverable_mission(
            goal="Modèle financier de rentabilité cloud et ratios",
            deliverable_type="xlsx",
            context="Tableau avec formules et marge",
            send_email=False,
        )

        assert res["status"] == "completed"
        assert res["verified"] is True
        assert res["deliverable_type"] == "xlsx"
        assert res["main_file"].endswith(".xlsx")
        assert os.path.exists(res["main_file_path"])
        assert res["file_size"] > 0


def test_verify_mission_deliverable_checker():
    """Vérifie le fonctionnement de verify_mission_deliverable."""
    from config import BASE_DIR
    scratch_dir = os.path.join(BASE_DIR, "downloads", "_test_scratch_verify")
    os.makedirs(scratch_dir, exist_ok=True)
    try:
        non_existent = os.path.join(scratch_dir, "absent.pdf")
        ok, size, err = verify_mission_deliverable(non_existent)
        assert ok is False
        assert "introuvable" in err

        too_small = os.path.join(scratch_dir, "small.html")
        with open(too_small, "w", encoding="utf-8") as f:
            f.write("trop court")
        ok, size, err = verify_mission_deliverable(too_small, min_size=1024)
        assert ok is False
        assert "incomplet" in err

        valid_file = os.path.join(scratch_dir, "valid.html")
        with open(valid_file, "w", encoding="utf-8") as f:
            f.write("A" * 1500)
        ok, size, ev = verify_mission_deliverable(valid_file, min_size=1024)
        assert ok is True
        assert size == 1500
        assert "vérifié matériellement" in ev
    finally:
        import shutil
        if os.path.exists(scratch_dir):
            shutil.rmtree(scratch_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_dispatcher_run_agentic_task_routes_to_deliverable_mission():
    """Vérifie que run_agentic_task délègue à execute_end_to_end_deliverable_mission dès qu'un livrable est détecté."""
    mock_res = {
        "status": "completed",
        "verified": True,
        "main_file": "index.html",
        "full_url": "http://localhost:8000/downloads/missions/m1/index.html",
        "executive_summary_for_voice": "Le site web de monitoring est en ligne.",
    }

    with patch("services.agentic_dispatcher.execute_end_to_end_deliverable_mission", new_callable=AsyncMock, return_value=mock_res) as mock_mission:
        resp = await dispatch_tool(
            name="run_agentic_task",
            args={
                "objectif": "Créer un site web interactif de démonstration",
                "livrable_attendu": "Site web HTML avec Tailwind",
            },
            websocket=None,
            session=None,
        )

        mock_mission.assert_awaited_once()
        assert mock_mission.await_args.kwargs["deliverable_type"] == "website"
        assert resp["status"] == "done"
        assert "site web de monitoring est en ligne" in resp["user_message"]
        assert resp["verified"] is True


@pytest.mark.asyncio
async def test_dispatcher_launch_deep_research_prioritizes_antigravity_deliverable():
    """Vérifie que launch_deep_research route en priorité vers Antigravity A-to-Z sans passer par le fragile browser automator."""
    mock_res = {
        "status": "completed",
        "verified": True,
        "main_file": "report.pdf",
        "public_url": "/downloads/missions/m2/report.pdf",
        "full_url": "http://localhost:8000/downloads/missions/m2/report.pdf",
        "executive_summary_for_voice": "L'analyse approfondie sur l'énergie de fusion est prête.",
    }

    with patch("services.agentic_dispatcher.execute_end_to_end_deliverable_mission", new_callable=AsyncMock, return_value=mock_res) as mock_mission, \
         patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_browser_agent_task", new_callable=AsyncMock) as mock_browser:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Recherche approfondie sur les réacteurs à fusion compacts",
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        # Le fragile browser automator UI ne doit PAS avoir été appelé
        mock_browser.assert_not_awaited()
        # Le pipeline Antigravity de A à Z doit être exécuté
        mock_mission.assert_awaited_once()
        assert resp["status"] == "done"
        assert "énergie de fusion est prête" in resp["user_message"]
