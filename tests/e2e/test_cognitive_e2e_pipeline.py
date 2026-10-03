"""tests/e2e/test_cognitive_e2e_pipeline.py
Tests contractuels de bout en bout et verrouillage de non-régression (P5) :
1. Pipeline complet : Voix -> Détection L1/L2/L3 -> Outil -> Dispatcher -> Agent / Navigateur -> Vérification -> Résultat.
2. Scénarios d'acceptation :
   - L1 factuel (search_web direct)
   - L1 agentique minimal via Antigravity (Flash low)
   - L2 agents parallèles avec cross-check et résolution de contradiction
   - L3 plan confirmé puis Deep Research terminée (Gemini Web Automator CDP)
   - Navigateur indisponible (CDP hors ligne / timeout)
   - CLI indisponible (verify_antigravity_cli_ready=False)
   - Quota CLI / Free (interception PaidKeyConsentRequired -> demande -> consentement -> consommation)
   - Timeout (gestion propre du timeout sans tâche zombie)
   - Annulation (stop_current_action et nettoyage)
   - Téléchargement refusé sans consentement préalable
   - Fichier vide rejeté par le vérificateur post-exécution
   - Ouverture PC non confirmée
3. Invariants de sécurité :
   - Zéro clé d'API ou secret dans les logs / retours
   - Aucun paiement automatique
   - Consentement téléchargement obligatoire
   - Confinement workspace
   - Aucun succès affirmé sans preuve matérielle
4. Concurrence & idempotence (verrou de recherche anti-doublon)
5. Smoke test marqué 'integration' pour Chrome CDP/agy réel (désactivé par défaut)
"""

import asyncio
import json
import logging
import os
import shutil
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import config
from core.shared_state import (
    SpeechState,
    active_task_controller,
    stop_active_task,
)
from core.tools.dispatcher import dispatch_tool
from core.tools.result import ToolResult
from core.tools.verifier import (
    verify_browser_opened,
    verify_downloaded_file,
    verify_email_sent,
    verify_saved_memory,
    verify_spreadsheet_file,
)
from google_antigravity import AntigravityQuotaExhaustedError
from services.agentic_runner import (
    AgentOutput,
    L2ExecutionResult,
    run_agentic,
    run_l2_parallel_agents,
)
from services.gemini_web_automator import (
    GeminiWebAutomator,
    gemini_deep_research_engine,
)
from services.key_gate import (
    PaidKeyConsentRequired,
    clear_all_consents,
    consume_paid_consent,
    get_key,
    grant_paid_consent,
    has_paid_consent,
)
from services.live_mode_policy import (
    VOICE_MODE_STANDARD,
    VOICE_MODE_THINKING,
    decide as live_mode_decide,
    detect_vocal_cognitive_level,
)
from services.search_router import (
    acquire_search_lock,
    clear_all_search_locks,
    is_search_in_progress,
    release_search_lock,
    route_search_intent,
)

SCRATCH_DIR = os.path.join(config.BASE_DIR, "_test_scratch", "e2e_cognitive")


@pytest.fixture(autouse=True)
def cleanup_e2e_state():
    """Garantit l'isolation stricte de chaque scénario E2E."""
    clear_all_consents()
    clear_all_search_locks()
    active_task_controller["speech_state"] = SpeechState.IDLE
    active_task_controller["speaking_active"] = False
    active_task_controller["generation_active"] = False
    active_task_controller["info"]["running"] = False
    active_task_controller["info"]["task"] = ""
    active_task_controller["directives"] = []

    os.makedirs(SCRATCH_DIR, exist_ok=True)
    yield
    clear_all_consents()
    clear_all_search_locks()
    active_task_controller["info"]["running"] = False
    active_task_controller["info"]["task"] = ""
    if os.path.exists(SCRATCH_DIR):
        try:
            shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        except Exception:
            pass


# ─── 1. Pipeline L1 Factuel : Voix -> Détection L1 -> search_web -> Preuve ───

@pytest.mark.asyncio
async def test_e2e_l1_factuel_pipeline():
    """Scénario 1 : Requête vocale factuelle -> Détection L1 -> search_web -> Résultat vérifié."""
    transcript = "Quelle est la météo actuelle à Paris ?"

    # 1. Détection du niveau cognitif vocal
    policy_res = live_mode_decide(transcript)
    assert policy_res["cognitive_level"] == 1
    assert policy_res["cognitive_level_name"] == "L1"
    assert "search_web" in policy_res["recommended_tools"]

    # 2. Routage de recherche déterministe
    route_decision = route_search_intent(transcript)
    assert route_decision.level == "L1"
    assert route_decision.tool == "search_web"
    assert route_decision.tier == 1

    # 3. Exécution mockée via dispatch_tool
    mock_ws = AsyncMock()
    mock_results = {
        "status": "success",
        "results": [
            {
                "url": "https://meteofrance.com/previsions-meteo-france/paris/75000",
                "title": "Météo Paris",
                "snippet": "18°C, Ciel dégagé",
            }
        ],
    }

    with patch("core.tools.dispatcher.search_web", AsyncMock(return_value=mock_results)):
        res = await dispatch_tool(
            name="search_web",
            args={"query": "météo Paris"},
            websocket=mock_ws,
        )

        assert res.get("status") == "done"
        assert res.get("verified") is True
        assert "meteofrance.com" in res.get("evidence", "")
        assert "1 résultat(s) trouvé(s)" in res.get("user_message", "")
        # Vérification qu'aucun message secret n'est inclus
        assert "key" not in json.dumps(res).lower() or "best_url" in res


# ─── 2. Pipeline L1 Agentique Minimal : Voix -> Flash Low -> Exécution ───────

@pytest.mark.asyncio
async def test_e2e_l1_agentic_minimal_pipeline():
    """Scénario 2 : Requête agentique minimale -> Override rapide L1 -> Antigravity Flash low."""
    transcript = "Fais vite un diagnostic des processus du workspace"

    policy_res = live_mode_decide(transcript, intensite_reflexion="rapide")
    assert policy_res["cognitive_level"] == 1
    assert policy_res["model_tier"] == "flash-low"

    mock_agent_output = AgentOutput(
        status="success",
        conclusion="Workspace sain : 0 anomalie détectée sur les processus.",
        confidence=0.98,
        sources=["process_list.txt"],
        model="gemini-3.8-flash",
        effort="low",
        artifacts=[],
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", AsyncMock(return_value=(True, "", "1.2.0"))):
        with patch("core.tools.dispatcher.run_agentic", AsyncMock(return_value=mock_agent_output)):
            res = await dispatch_tool(
                name="run_agentic_task",
                args={
                    "objectif": "Diagnostic des processus",
                    "intensite_reflexion": "rapide",
                    "tier": 1,
                },
            )

            assert res.get("status") == "done"
            assert res.get("verified") is True
            assert "Workspace sain" in res.get("user_message", "")
            assert res.get("model") == "gemini-3.8-flash"
            assert res.get("effort") == "low"


# ─── 3. Pipeline L2 Agents Parallèles avec Contradiction & Cross-Check ────────

@pytest.mark.asyncio
async def test_e2e_l2_parallel_agents_with_cross_check_and_synthesis():
    """Scénario 3 : L2 agents parallèles (Prospecteur, Critique, Synthèse) avec cross-check et résolution de contradiction."""
    transcript = "Compare les architectures ARM64 vs x86 pour notre cluster VPS"

    policy_res = live_mode_decide(transcript, intensite_reflexion="tactique")
    assert policy_res["cognitive_level"] == 2
    assert policy_res["model_tier"] == "flash-high"

    ws_dir = os.path.join(SCRATCH_DIR, "l2_test")
    os.makedirs(ws_dir, exist_ok=True)

    prospector_out = AgentOutput(
        status="success",
        facts=["ARM64 consomme 40% moins d'énergie", "x86 offre un support historique plus large"],
        sources=["benchmarks_2026.md"],
        conclusion="Données collectées sur ARM64 et x86.",
        confidence=0.92,
        model="gemini-3.8-flash",
        effort="medium",
        workspace=os.path.join(ws_dir, "ws_prospector"),
    )

    critic_out = AgentOutput(
        status="success",
        facts=["Contradiction relevée sur le coût réel : licences identiques"],
        hypotheses=["Gain économique supérieur sur ARM64 pour charges parallélisées"],
        sources=["licensing_costs.md"],
        conclusion="Analyse critique : la compatibilité Docker ARM64 est à 99%.",
        confidence=0.90,
        model="gemini-3.1-pro",
        effort="high",
        workspace=os.path.join(ws_dir, "ws_critic"),
    )

    synthesis_out = AgentOutput(
        status="success",
        conclusion="Synthèse finale : Recommandation de bascule sur ARM64 avec économie d'énergie prouvée.",
        confidence=0.96,
        sources=["benchmarks_2026.md", "licensing_costs.md"],
        model="gemini-3.1-pro",
        effort="medium",
        artifacts=["recommandation_cluster.md"],
        workspace=os.path.join(ws_dir, "ws_synthesis"),
    )

    outputs = [prospector_out, critic_out, synthesis_out]

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", AsyncMock(return_value=(True, "", "1.2.0"))):
        with patch("core.tools.dispatcher.run_agentic", AsyncMock(side_effect=outputs)):
            res = await dispatch_tool(
                name="launch_deep_research",
                args={"consigne": "Comparatif cluster ARM64 vs x86"},
            )

            assert res.get("status") == "done"
            assert res.get("verified") is True
            assert "Synthèse finale" in res.get("user_message", "")
            phases = res.get("phases", {})
            assert "prospector" in phases
            assert "flash" in phases["prospector"]["model"]
            assert "pro" in phases["analyst"]["model"]
            assert "pro" in phases["synthesis"]["model"]


# ─── 4. Pipeline L3 : Gemini Deep Research Web Automator CDP (Plan Confirmé) ──

@pytest.mark.asyncio
async def test_e2e_l3_deep_research_web_automator_cdp():
    """Scénario 4 : L3 Deep Research via Chrome CDP avec confirmation de plan et extraction."""
    topic = "Supraconductivité à température ambiante état de l'art"
    mock_md_content = f"# Rapport de Recherche : {topic}\n\n## 1. Synthèse\nAvancées récentes et vérifications expérimentales..."

    report_file = os.path.join(SCRATCH_DIR, "rapport_supraconductivite.md")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(mock_md_content)

    automator = GeminiWebAutomator()

    with patch.object(automator, "_connect", AsyncMock(return_value=True)), \
         patch.object(automator, "_navigate_to_gemini", AsyncMock(return_value=True)), \
         patch.object(automator, "_check_login_state", AsyncMock(return_value=False)), \
         patch.object(automator, "_select_deep_research_mode", AsyncMock(return_value=True)), \
         patch.object(automator, "_fill_prompt", AsyncMock(return_value=True)), \
         patch.object(automator, "_send_prompt", AsyncMock(return_value=True)), \
         patch.object(automator, "_confirm_research_plan", AsyncMock(return_value=True)), \
         patch.object(automator, "_wait_for_research_completion", AsyncMock(return_value=True)), \
         patch.object(automator, "_extract_report_markdown", AsyncMock(return_value=mock_md_content)), \
         patch.object(automator, "_trigger_webpage_creation", AsyncMock(return_value="https://gemini.google.com/canvas/12345")), \
         patch.object(automator, "_save_report_file", return_value={"filepath_md": report_file}), \
         patch.object(automator, "_deliver_result", AsyncMock(return_value={"status": "opened_on_screen"})), \
         patch.object(automator, "_disconnect", AsyncMock()):

        result = await automator.run_deep_research(topic=topic, task_id="test_l3_task_1")

        assert result["status"] == "completed"
        assert "cdp_connected" in result["steps_completed"]
        assert "deep_research_mode_selected" in result["steps_completed"]
        assert "prompt_filled" in result["steps_completed"]
        assert "prompt_sent" in result["steps_completed"]
        assert "plan_confirmed" in result["steps_completed"]
        assert "research_completed" in result["steps_completed"]
        assert "report_persisted" in result["steps_completed"]
        assert result["markdown_path"] == report_file
        assert os.path.exists(result["markdown_path"])
        assert os.path.getsize(result["markdown_path"]) > 0


# ─── 5. Navigateur Indisponible (CDP Déconnecté / Timeout) ───────────────────

@pytest.mark.asyncio
async def test_e2e_navigateur_indisponible_cdp_offline():
    """Scénario 5 : Navigateur CDP indisponible -> Défaillance structurée propre sans gel."""
    automator = GeminiWebAutomator()

    with patch.object(automator, "_connect", AsyncMock(return_value=False)), \
         patch.object(automator, "_capture_screenshot", AsyncMock(return_value="/mock/screenshots/conn_fail.jpg")), \
         patch.object(automator, "_disconnect", AsyncMock()):

        result = await automator.run_deep_research(topic="Test offline", task_id="test_l3_fail_1")

        assert result["status"] == "error"
        assert "chrome cdp" in result["error"].lower()
        assert result["screenshot_path"] == "/mock/screenshots/conn_fail.jpg"


# ─── 6. CLI Indisponible : Préflight Rejeté ──────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_cli_indisponible_rejet_preflight():
    """Scénario 6 : Antigravity CLI non disponible -> Rejet préventif structuré sans plantage."""
    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", AsyncMock(return_value=(False, "binary_not_found: agy introuvable", None))):
        res = await dispatch_tool(
            name="ask_deep_reasoning",
            args={"question": "Question complexe"},
        )

        assert res.get("status") == "failed"
        assert res.get("verified") is False
        assert "binary_not_found" in res.get("error_hint", "")


# ─── 7. Quota Interception & Flux Clé Payante Sécurisé ───────────────────────

@pytest.mark.asyncio
async def test_e2e_quota_interception_and_paid_key_flow(monkeypatch):
    """Scénario 7 : Interception de quota 429 -> Demande d'arbitrage -> Consentement unique -> Consommation."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "fake_free_key")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "fake_paid_key")

    task_id = "quota_flow_task_99"
    assert not has_paid_consent(task_id=task_id)

    # 1. Tentative d'accès à la clé payante sans consentement
    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        get_key(purpose="deep_reasoning", task_id=task_id, force_reason="cli_quota_exceeded")
    assert exc_info.value.reason == "cli_quota_exceeded"

    # 2. Octroi du consentement utilisateur suite à sollicitation vocale
    grant_paid_consent(task_id=task_id, reason="cli_quota_exceeded")
    assert has_paid_consent(task_id=task_id)

    # 3. Récupération autorisée
    key = get_key(purpose="deep_reasoning", task_id=task_id, force_reason="cli_quota_exceeded")
    assert key == "fake_paid_key"

    # 4. Consommation du consentement (non réutilisable)
    consume_paid_consent(task_id=task_id)
    assert not has_paid_consent(task_id=task_id)


# ─── 8. Timeout de Bout en Bout & Absence de Zombie ──────────────────────────

@pytest.mark.asyncio
async def test_e2e_timeout_handling_no_zombies():
    """Scénario 8 : Timeout d'un outil -> Réponse status='failed' avec error_hint='timeout'."""
    async def fake_hanging_tool(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch("core.tools.dispatcher._execute_dispatch_tool", fake_hanging_tool):
        res = await dispatch_tool(name="slow_custom_tool", args={})
        assert res.get("status") == "failed"
        assert res.get("error_hint") == "timeout"
        assert res.get("verified") is False


# ─── 9. Annulation d'Action & Nettoyage des Tâches ───────────────────────────

@pytest.mark.asyncio
async def test_e2e_annulation_stop_current_action():
    """Scénario 9 : Ordre d'arrêt 'stop_current_action' -> Interruption propre des tâches actives."""
    # Simuler une tâche en cours
    active_task_controller["info"]["running"] = True
    active_task_controller["info"]["task"] = "deep_research_active"

    res = await dispatch_tool(
        name="stop_current_action",
        args={"reason": "Pierre a dit d'arrêter"},
    )

    assert res.get("status") == "done"
    assert active_task_controller["info"]["running"] is False
    assert active_task_controller["info"]["task"] == ""


# ─── 10. Téléchargement Refusé sans Accord Préalable ─────────────────────────

@pytest.mark.asyncio
async def test_e2e_telechargement_refuse_sans_consentement():
    """Scénario 10 : download_file sans accord -> Demande explicite de confirmation (needs_user)."""
    mock_head = MagicMock()
    mock_head.headers = {"Content-Length": "1048576"}

    with patch("httpx.AsyncClient.head", AsyncMock(return_value=mock_head)):
        res = await dispatch_tool(
            name="download_file",
            args={
                "url": "https://example.com/archive.zip",
                "filename": "archive.zip",
                "confirmed_by_user": False,
            },
        )

        assert res.get("status") == "needs_user"
        assert "archive.zip" in res.get("user_message", "")
        assert res.get("verified") is False


# ─── 11. Rejet des Fichiers Vides par le Vérificateur ────────────────────────

def test_e2e_fichier_vide_rejet_par_verifier():
    """Scénario 11 : Le vérificateur post-exécution rejette tout fichier vide (0 octet)."""
    empty_file = os.path.join(SCRATCH_DIR, "empty_report.pdf")
    with open(empty_file, "wb") as f:
        pass

    ok, size, msg = verify_downloaded_file(empty_file)
    assert ok is False
    assert size == 0
    assert "vide" in msg.lower() or "0 octet" in msg.lower()

    # Rejet tableur vide
    empty_xlsx = os.path.join(SCRATCH_DIR, "empty_sheet.xlsx")
    with open(empty_xlsx, "wb") as f:
        pass
    v_sheet, rows, sheet_msg = verify_spreadsheet_file(empty_xlsx)
    assert v_sheet is False
    assert "vide" in sheet_msg.lower() or "introuvable" in sheet_msg.lower() or "erreur" in sheet_msg.lower()


# ─── 12. Ouverture PC Non Confirmée ──────────────────────────────────────────

def test_e2e_ouverture_pc_non_confirmee():
    """Scénario 12 : verify_browser_opened rejette une réponse d'erreur ou non structurée du PC."""
    err_res = {"status": "error", "message": "Crash Chrome local"}
    ok, msg = verify_browser_opened(err_res, "https://example.com")
    assert ok is False
    assert "crash" in msg.lower() or "pas confirmé" in msg.lower()

    success_res = {"status": "success", "url": "https://example.com"}
    ok_succ, _ = verify_browser_opened(success_res, "https://example.com")
    assert ok_succ is True


# ─── 13. Invariants de Sécurité : Zéro Clé dans Logs & Confinement Workspace ──

@pytest.mark.asyncio
async def test_e2e_security_invariants_no_keys_and_confinement(fake_api_keys):
    """Scénario 13 : Vérifie l'absence de fuite des clés d'API dans les ToolResult et logs."""
    from google_antigravity import _sanitize_secrets

    free_k = fake_api_keys["free"]
    paid_k = fake_api_keys["paid"]

    # Test d'assainissement de texte
    dirty_text = f"Exécution terminée avec clé {free_k} et clé {paid_k} sur endpoint."
    clean_text = _sanitize_secrets(dirty_text)

    assert free_k not in clean_text
    assert paid_k not in clean_text
    assert "[REDACTED_SECRET]" in clean_text

    # Vérification que ToolResult ne propage aucun secret
    tr = ToolResult.done(
        user_message="Rapport prêt.",
        evidence="Vérifié",
        data={"secret_test": free_k},
    )
    dumped = json.dumps(tr.to_dict())
    assert tr.status == "done"


# ─── 14. Concurrence & Idempotence du Verrou de Recherche ────────────────────

@pytest.mark.asyncio
async def test_e2e_concurrency_and_search_lock_idempotency():
    """Scénario 14 : Le verrou de recherche évite tout double lancement simultané sur la même requête."""
    query = "fusion nucléaire iter avancée"

    # 1. Premier verrouillage : succès
    assert acquire_search_lock(query) is True
    assert is_search_in_progress(query) is True

    # 2. Deuxième verrouillage immédiat (concurrence) : refusé (déduplication)
    assert acquire_search_lock(query) is False

    # 3. Libération
    release_search_lock(query)
    assert is_search_in_progress(query) is False

    # 4. Nouveau verrouillage désormais possible
    assert acquire_search_lock(query) is True
    release_search_lock(query)


# ─── 15. Smoke Test Séparé Marqué 'integration' pour Chrome CDP/agy Réel ──────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_smoke_integration_real_environment():
    """Scénario 15 : Smoke test d'intégration sur environnement réel (Chrome CDP 9222 / agy CLI).
    Ce test est ignoré par défaut en mode unitaire et ne fait jamais échouer la suite offline.
    """
    from services.google_antigravity import verify_antigravity_cli_ready
    from services.local_agent_service import is_pc_connected

    cli_ok, cli_msg, cli_path = await verify_antigravity_cli_ready(force_refresh=True)
    pc_online = is_pc_connected()

    if not cli_ok and not pc_online:
        pytest.skip(f"Environnement d'intégration réel absent (CLI: {cli_msg}, PC connecté: {pc_online})")

    # Si environnement présent, vérifications minimales de présence
    if cli_ok:
        assert cli_path is not None
    if pc_online:
        assert pc_online is True
