"""tests/test_tool_result.py
Tests unitaires et d'intégration pour ToolResult, le moteur de vérification post-exécution
et la couche de normalisation défensive dans dispatcher.py.
Conforme à la règle no-paid-api-in-tests.md : zéro appel API payante, mocks complets.
"""

import os
import pytest
import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from core.tools.result import ToolResult, normalize_result, ALLOWED_STATUSES
from core.tools.verifier import (
    verify_email_sent,
    verify_presentation_slides,
    verify_spreadsheet_file,
    verify_downloaded_file,
    verify_application_process,
    verify_calendar_event,
    verify_saved_memory,
    verify_browser_opened,
)
from core.tools.dispatcher import dispatch_tool
from services.metrics_service import metrics_service


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tests de la structure et des invariants de ToolResult
# ─────────────────────────────────────────────────────────────────────────────

def test_tool_result_allowed_statuses():
    """Valide que ToolResult n'autorise strictement que les 5 statuts spécifiés."""
    assert ALLOWED_STATUSES == {"done", "failed", "started", "partial", "needs_user"}
    assert len(ALLOWED_STATUSES) == 5

    res = ToolResult(status="done", verified=True, evidence="Message-ID: <123@jarvis>", user_message="Fait")
    assert res.status == "done"
    assert res.verified is True

    with pytest.raises(ValueError):
        ToolResult(status="completed", verified=True)

    with pytest.raises(ValueError):
        ToolResult(status="success", verified=True)

    with pytest.raises(ValueError):
        ToolResult(status="invalide_status")


def test_tool_result_done_requires_verified_logic():
    """Valide que ToolResult.done positionne verified et evidence."""
    res_v = ToolResult.done(user_message="C'est envoyé.", evidence="msg_id_999", verified=True)
    assert res_v.status == "done"
    assert res_v.verified is True
    assert res_v.evidence == "msg_id_999"
    assert res_v.to_dict()["verified"] is True

    res_nv = ToolResult.done(user_message="Lancé mais non vérifié.", verified=False)
    assert res_nv.status == "done"
    assert res_nv.verified is False


def test_tool_result_started_and_failed_constructors():
    """Valide les constructeurs started, failed, needs_user et partial."""
    started = ToolResult.started(task_id="slides_42", user_message="Génération en cours.")
    assert started.status == "started"
    assert started.task_id == "slides_42"
    assert started.verified is False

    failed = ToolResult.failed(user_message="Échec.", error_hint="Quota dépassé.", evidence="HTTP 429")
    assert failed.status == "failed"
    assert failed.error_hint == "Quota dépassé."
    assert failed.verified is False

    needs = ToolResult.needs_user(user_message="Confirmation requise ?", question="Supprimer ?")
    assert needs.status == "needs_user"
    assert needs.data.get("question") == "Supprimer ?"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tests de normalisation des statuts legacy
# ─────────────────────────────────────────────────────────────────────────────

def test_normalize_result_legacy_success_mappings(caplog):
    """Valide la conversion de tous les anciens statuts de succès vers 'done'."""
    legacy_success_statuses = [
        "success", "sent", "generated", "opened_locally", "completed"
    ]
    initial_claimed = metrics_service.get_claimed_success_without_verification_count()

    for legacy_st in legacy_success_statuses:
        caplog.clear()
        raw = {"status": legacy_st, "message": "Opération OK", "instruction_to_jarvis": "Dis que c'est fait."}
        norm = normalize_result(f"tool_{legacy_st}", raw)
        assert norm.status == "done"
        assert norm.verified is False  # Legacy n'avait pas de verified=True explicite
        assert norm.user_message in ("Opération OK", "Dis que c'est fait.")
        assert any("Format legacy détecté" in record.message for record in caplog.records)

    # Le compteur de succès non vérifié doit avoir augmenté
    assert metrics_service.get_claimed_success_without_verification_count() >= initial_claimed + len(legacy_success_statuses)


def test_normalize_result_legacy_background_and_error():
    """Valide la conversion des statuts legacy de background, needs_user et d'erreur."""
    bg_raw = {"status": "lance_en_arriere_plan", "action": "slides_bg"}
    norm_bg = normalize_result("slides_tool", bg_raw)
    assert norm_bg.status == "started"

    cart_raw = {"status": "cart_ready", "cart_url": "https://fnac.com/cart"}
    norm_cart = normalize_result("cart_tool", cart_raw)
    assert norm_cart.status == "needs_user"

    err_raw = {"status": "error", "error": "Fichier introuvable"}
    norm_err = normalize_result("file_tool", err_raw)
    assert norm_err.status == "failed"
    assert norm_err.error_hint == "Fichier introuvable"

    conf_raw = {"status": "requires_user_confirmation", "instruction_to_jarvis": "Demande à Pierre"}
    norm_conf = normalize_result("dl_tool", conf_raw)
    assert norm_conf.status == "needs_user"


def test_normalize_result_native_passthrough(caplog):
    """Valide qu'un ToolResult natif passe sans warning et sans altération."""
    caplog.clear()
    native = ToolResult.done(user_message="Terminé et vérifié", evidence="relecture_ok", verified=True)
    norm = normalize_result("native_tool", native)
    assert norm.status == "done"
    assert norm.verified is True
    assert norm.evidence == "relecture_ok"
    assert not any("Format legacy détecté" in record.message for record in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tests de vérification post-exécution (Mock API OK mais Vérification KO → failed)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_email_sent_fail():
    """Simule un envoi de mail où l'API renvoie 200/sent mais la relecture échoue -> Jarvis annonce l'échec/non confirmation."""
    mock_ws = AsyncMock()

    with patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send, \
         patch("core.tools.dispatcher.verify_email_sent", new_callable=AsyncMock) as mock_verify:

        mock_send.return_value = {
            "status": "success",
            "message_id": "<test_123@jarvis>",
            "to": "test@example.com",
            "subject": "Test Sujet"
        }
        mock_verify.return_value = (False, "Message introuvable dans le dossier Envoyés", None)

        res = await dispatch_tool(
            name="send_email",
            args={
                "to": "test@example.com",
                "subject": "Test Sujet",
                "body": "Contenu",
                # Le portail arg_validator exige une confirmation explicite avant tout envoi
                "confirmed_by_user": True,
            },
            websocket=mock_ws,
        )

        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "n'a pas pu être confirmé" in res["user_message"]
        assert "Courriel non retrouvé" in (res.get("error_hint") or "")


@pytest.mark.asyncio
async def test_verify_presentation_slides_zero_slides_fail():
    """Simule generate_presentation avec 0 slide créée -> failed."""
    # 1. Test unitaire du verifier
    with patch("services.slides_service.slides_service.verify_presentation", new_callable=AsyncMock) as mock_v:
        mock_v.return_value = (False, 0, "Présentation avec 0 diapositive")
        ok, count, detail = await verify_presentation_slides("pres_zero_slides", min_slides=1)
        assert ok is False
        assert count == 0
        assert "0" in detail

    # 2. Test avec ID vide
    from services.slides_service import slides_service
    is_ok, count, reason = await slides_service.verify_presentation("")
    assert is_ok is False
    assert count == 0


def test_verify_spreadsheet_file_missing_or_empty():
    """Vérifie qu'un tableur absent ou sans lignes renvoie un échec de vérification."""
    # Fichier inexistant
    ok, rows, detail = verify_spreadsheet_file("downloads/fichier_fantome_non_existant.xlsx")
    assert ok is False
    assert rows == 0
    assert "introuvable" in detail

    # Fichier vide (0 octet)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
        tf_name = tf.name
    try:
        ok_empty, rows_empty, detail_empty = verify_spreadsheet_file(tf_name)
        assert ok_empty is False
        assert rows_empty == 0
    finally:
        if os.path.exists(tf_name):
            os.remove(tf_name)


def test_verify_downloaded_file_missing_or_empty():
    """Vérifie qu'un fichier téléchargé absent ou à 0 octet renvoie un échec."""
    ok, size, detail = verify_downloaded_file("downloads/ebook_introuvable.epub")
    assert ok is False
    assert size == 0
    assert "introuvable" in detail

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf_name = tf.name
    try:
        ok_zero, size_zero, detail_zero = verify_downloaded_file(tf_name)
        assert ok_zero is False
        assert size_zero == 0
        assert "0 octet" in detail_zero
    finally:
        if os.path.exists(tf_name):
            os.remove(tf_name)


@pytest.mark.asyncio
async def test_download_file_fails_when_file_not_found():
    """dispatch_tool('download_file') avec API OK mais fichier manquant -> status='failed'."""
    mock_ws = AsyncMock()
    with patch("core.tools.dispatcher.download_file", new_callable=AsyncMock) as mock_dl:
        mock_dl.return_value = {
            "status": "completed",
            "filename": "fictif.pdf",
            "filepath": "downloads/fictif_introuvable_1234.pdf",
            "size": "50 KB"
        }
        res = await dispatch_tool(
            name="download_file",
            args={"url": "https://example.com/fictif.pdf", "filename": "fictif.pdf", "confirmed_by_user": True},
            websocket=mock_ws
        )
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "n'a pas pu être validé" in res["user_message"]


@pytest.mark.asyncio
async def test_search_and_download_ebook_fails_when_file_corrupt():
    """dispatch_tool('search_and_download_ebook') avec fichier vide -> status='failed'."""
    mock_ws = AsyncMock()
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tf:
        tf_name = tf.name
    try:
        with patch("core.tools.dispatcher.search_and_download_ebook", new_callable=AsyncMock) as mock_eb:
            mock_eb.return_value = {
                "status": "success",
                "filename": os.path.basename(tf_name),
                "filepath": tf_name,
                "message": "Téléchargé"
            }
            res = await dispatch_tool(
                name="search_and_download_ebook",
                args={"query": "Livre Inexistant", "confirmed_by_user": True},
                websocket=mock_ws
            )
            assert res["status"] == "failed"
            assert res["verified"] is False
    finally:
        if os.path.exists(tf_name):
            os.remove(tf_name)


@pytest.mark.asyncio
async def test_launch_application_fails_when_pid_dead():
    """dispatch_tool('launch_application') retourne un faux PID qui n'existe pas -> status='failed'."""
    mock_ws = AsyncMock()
    with patch("core.tools.dispatcher.launch_application", return_value={"status": "success", "app": "calc", "pid": 999999999, "message": "Lancé"}), \
         patch("core.tools.dispatcher.verify_application_process", return_value=(False, None, "Processus 999999999 inactif")):

        res = await dispatch_tool(
            name="launch_application",
            args={"app_name": "calc"},
            websocket=mock_ws
        )
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "n'a pas pu être confirmé" in res["user_message"]


@pytest.mark.asyncio
async def test_manage_calendar_event_fails_when_verify_fails():
    """dispatch_tool('manage_calendar_event', action='creer') avec n8n OK mais relecture introuvable -> failed."""
    mock_ws = AsyncMock()
    with patch("services.automation.executer_action_externe", new_callable=AsyncMock) as mock_n8n, \
         patch("core.tools.dispatcher.verify_calendar_event", new_callable=AsyncMock) as mock_verify:

        mock_n8n.return_value = {
            "status": "success",
            "result": {"event_id": "cal_evt_123"}
        }
        mock_verify.return_value = (False, "Événement non trouvé dans l'agenda", None)

        res = await dispatch_tool(
            name="manage_calendar_event",
            args={"action": "creer", "titre": "Réunion Test", "date_debut": "2026-10-01 10:00"},
            websocket=mock_ws
        )
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "n'a pas pu être confirmée" in res["user_message"]


@pytest.mark.asyncio
async def test_save_memory_fails_when_re_read_fails():
    """dispatch_tool('save_memory') avec insertion réussie mais relecture SQLite échoue -> failed."""
    mock_ws = AsyncMock()
    with patch("core.tools.dispatcher.unified_memory_manager.memorize", new_callable=AsyncMock) as mock_mem, \
         patch("core.tools.dispatcher.verify_saved_memory", return_value=(False, "Mémoire ID 42 introuvable dans SQLite")):

        mock_mem.return_value = {"id": 42, "status": "stored"}
        res = await dispatch_tool(
            name="save_memory",
            args={"fact": "Pierre aime le thé vert", "category": "preferences"},
            websocket=mock_ws
        )
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "n'a pas pu être vérifiée" in res["user_message"]


@pytest.mark.asyncio
async def test_open_user_browser_fails_when_ack_missing():
    """dispatch_tool('open_user_browser') sans accusé de réception du PC -> failed."""
    mock_ws = AsyncMock()
    with patch("core.tools.dispatcher.open_browser_window", return_value={"status": "opened_locally"}), \
         patch("core.tools.dispatcher.verify_browser_opened", return_value=(False, "Timeout en attente d'ack agent local")):

        res = await dispatch_tool(
            name="open_user_browser",
            args={"url": "https://google.com"},
            websocket=mock_ws
        )
        assert res["status"] == "failed"
        assert res["verified"] is False
        assert "Impossible d'ouvrir le navigateur" in res["user_message"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tests des métriques : claimed_success_without_verification
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claimed_success_without_verification_counter():
    """Valide l'incrémentation du compteur et sa présence dans le résumé des métriques."""
    c0 = metrics_service.get_claimed_success_without_verification_count()
    metrics_service.record_claimed_success_without_verification("test_unverified_tool")
    assert metrics_service.get_claimed_success_without_verification_count() == c0 + 1

    summary = await metrics_service.get_metrics_summary(window_str="24h")
    assert "claimed_success_without_verification" in summary
    assert summary["claimed_success_without_verification"] >= c0 + 1
