"""Tests unitaires et d'intégration pour le routage intelligent des modèles,
le registre, le constructeur de prompts et la gestion résiliente des quotas (fallback_handler).
GARANTIE STRICTE : Aucun appel API Gemini/Claude ni CLI réel (100% mocks).
"""

import asyncio
import json
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from model_registry import ModelInfo, ModelRegistry, model_registry, DEFAULT_MODELS
from model_router import RoutingDecision, select_model
from fallback_handler import (
    AntigravityQuotaExhaustedError,
    ModelCooldownManager,
    cooldown_manager,
    execute_with_fallback,
    is_quota_error
)
from prompt_builder import (
    build_prompt,
    parse_agent_response,
    STANDARD_JSON_SCHEMA
)


# ─── 1. Tests Registre de Modèles (model_registry) ───────────────────────────

def test_registry_fallback_cascade():
    """Vérifie la cascade : CLI indisponible -> fichier config -> liste par défaut."""
    reg = ModelRegistry(ttl_seconds=10)

    # Scénario A : CLI échoue, Config inexistante -> Liste par défaut
    with patch.object(reg, "_discover_via_cli", return_value=None), \
         patch.object(reg, "_load_from_config", return_value=None):
        models = reg.refresh(force=True)
        assert len(models) == len(DEFAULT_MODELS)
        assert reg.source == "default_fallback"
        assert reg.get_model("gemini-3.7-flash") is not None
        assert reg.get_model("claude-3-7-sonnet") is not None

    # Scénario B : CLI échoue, Config présente -> Fichier config
    custom_models = [
        ModelInfo(name="custom-flash", provider="gemini", tier="flash", supports_effort=True),
        ModelInfo(name="custom-pro", provider="gemini", tier="pro", supports_effort=True)
    ]
    with patch.object(reg, "_discover_via_cli", return_value=None), \
         patch.object(reg, "_load_from_config", return_value=custom_models):
        models = reg.refresh(force=True)
        assert len(models) == 2
        assert reg.source == "config_file"
        assert reg.get_model("custom-flash") is not None

    # Scénario C : CLI disponible -> Découverte CLI
    cli_models = [
        ModelInfo(name="cli-discovered-model", provider="gemini", tier="flash", supports_effort=True)
    ]
    with patch.object(reg, "_discover_via_cli", return_value=cli_models):
        models = reg.refresh(force=True)
        assert len(models) == 1
        assert reg.source == "cli"
        assert reg.get_model("cli-discovered-model") is not None


def test_registry_get_equivalent_gemini():
    """Vérifie la conversion d'un modèle Claude vers son équivalent Gemini."""
    reg = ModelRegistry()
    assert reg.get_equivalent_gemini_model("claude-3-7-sonnet") == "gemini-3.1-pro"
    assert reg.get_equivalent_gemini_model("gemini-3.1-pro") == "gemini-3.7-flash"


# ─── 2. Tests Routeur de Modèles (model_router) ──────────────────────────────

def test_routing_by_task_type():
    """Vérifie que chaque type de tâche sélectionne le modèle et l'effort attendus."""
    # Simple -> Flash low
    dec_simple = select_model("doc_sync")
    assert dec_simple.model in ("gemini-3.7-flash", "gemini-3.8-flash")
    assert dec_simple.effort == "low"
    assert dec_simple.task_type == "simple"

    # Medium -> Flash medium
    dec_medium = select_model("transport_optimizer")
    assert dec_medium.model in ("gemini-3.7-flash", "gemini-3.8-flash")
    assert dec_medium.effort == "medium"

    # Medium complexe -> Flash high
    dec_medium_high = select_model("spreadsheet_modeler", estimated_complexity="high")
    assert dec_medium_high.effort == "high"

    # Complex -> Pro high
    dec_complex = select_model("deep_research")
    assert "pro" in dec_complex.model
    assert dec_complex.effort == "high"
    assert dec_complex.task_type == "complex"

    # Code -> Claude 3.7 Sonnet (sans --effort)
    dec_code = select_model({"task_type": "code", "goal": "code_refactoring"})
    assert dec_code.model == "claude-3-7-sonnet"
    assert dec_code.effort is None
    assert dec_code.provider == "claude"


def test_routing_context_window_overflow():
    """Vérifie le surclassement de modèle si la taille du contexte dépasse la fenêtre."""
    # Contexte de 500k tokens sur Claude (fenêtre 200k) -> Doit surclasser vers Gemini Pro (2M)
    dec = select_model(task="code", context_size=500000)
    assert dec.context_window >= 500000
    assert "pro" in dec.model or "flash" in dec.model


def test_routing_overrides():
    """Vérifie les surcharges explicites (paramètres utilisateur et voix)."""
    # Override intensité
    dec_override = select_model("transport_optimizer", intensite_reflexion="approfondie")
    assert "pro" in dec_override.model
    assert dec_override.effort == "high"
    assert dec_override.is_override is True

    # Override vocal Claude
    dec_vocal_claude = select_model("analyse", query="Fais cette analyse avec claude s'il te plaît")
    assert dec_vocal_claude.model == "claude-3-7-sonnet"
    assert dec_vocal_claude.effort is None


# ─── 3. Tests Gestionnaire de Repli (fallback_handler) ─────────────────────────

@pytest.mark.asyncio
async def test_fallback_claude_to_gemini_cli():
    """Vérifie la bascule automatique de Claude vers Gemini CLI en cas de quota dépassé."""
    cooldown_manager.clear()
    decision = RoutingDecision(
        model="claude-3-7-sonnet",
        effort=None,
        fallback_chain=["gemini-3.1-pro", "gemini-3.7-flash"],
        provider="claude",
        task_type="code"
    )

    attempted_models = []

    async def mock_runner(model_name: str, effort: str | None):
        attempted_models.append(model_name)
        if model_name == "claude-3-7-sonnet":
            raise RuntimeError("Error 429: Rate limit / Quota exceeded for Claude 3.7 Sonnet")
        return {"status": "completed", "model_used": model_name, "summary": "Code généré par Gemini"}

    result = await execute_with_fallback(mock_runner, decision, prompt="Ecris un script")
    assert attempted_models == ["claude-3-7-sonnet", "gemini-3.1-pro"]
    assert result["status"] == "completed"
    assert result["model_used"] == "gemini-3.1-pro"
    assert cooldown_manager.is_in_cooldown("claude-3-7-sonnet") is True


@pytest.mark.asyncio
async def test_fallback_gemini_to_paid_api_authorized():
    """Vérifie la bascule vers l'API Paid Gemini quand autorisée par l'utilisateur."""
    cooldown_manager.clear()
    decision = RoutingDecision(
        model="gemini-3.1-pro",
        effort="high",
        fallback_chain=["gemini-3.7-flash", "api_paid_gemini"],
        provider="gemini",
        task_type="complex"
    )

    attempted_models = []

    async def mock_runner(model_name: str, effort: str | None):
        attempted_models.append(model_name)
        raise RuntimeError("AntigravityQuotaExhaustedError: 429 RESOURCE_EXHAUSTED")

    mock_genai_client = MagicMock()
    mock_resp = MagicMock(text="Résultat généré par Gemini API Direct Paid")
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch("config.is_paid_key_authorized", return_value=True), \
         patch("config.get_effective_paid_key", return_value="AIzaSyFAKE_PAID_KEY_SECRET"), \
         patch("google.genai.Client", return_value=mock_genai_client):

        res = await execute_with_fallback(mock_runner, decision, prompt="Rapport stratégique")
        assert attempted_models == ["gemini-3.1-pro", "gemini-3.7-flash"]
        assert res["status"] == "completed"
        assert "[PAID]" in res["model_used"]


@pytest.mark.asyncio
async def test_fallback_gemini_to_paid_api_unauthorized_raises_clear_error():
    """Vérifie qu'une erreur claire est levée sans bascule payante si non autorisée."""
    cooldown_manager.clear()
    decision = RoutingDecision(
        model="gemini-3.7-flash",
        effort="low",
        fallback_chain=["api_paid_gemini"],
        provider="gemini",
        task_type="simple"
    )

    async def mock_runner(model_name: str, effort: str | None):
        raise RuntimeError("Quota 5h saturé (code 429)")

    with patch("config.is_paid_key_authorized", return_value=False):
        with pytest.raises(AntigravityQuotaExhaustedError) as exc_info:
            await execute_with_fallback(mock_runner, decision, prompt="Vérifie ce fichier")
        assert "non autorisé" in str(exc_info.value).lower() or "clé payante" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_non_quota_error_does_not_trigger_fallback():
    """Vérifie qu'une erreur de syntaxe ou d'exécution ne déclenche aucun fallback."""
    cooldown_manager.clear()
    decision = RoutingDecision(
        model="gemini-3.7-flash",
        effort="low",
        fallback_chain=["gemini-3.8-flash", "api_paid_gemini"],
        provider="gemini",
        task_type="simple"
    )

    call_count = 0

    async def mock_runner(model_name: str, effort: str | None):
        nonlocal call_count
        call_count += 1
        raise ValueError("Erreur de syntaxe dans le script de l'agent : unexpected token")

    with pytest.raises(ValueError) as exc_info:
        await execute_with_fallback(mock_runner, decision, prompt="Test script")

    assert "unexpected token" in str(exc_info.value)
    assert call_count == 1  # Pas de tentative sur le modèle suivant


# ─── 4. Test Inviolabilité & Confidentialité de la Clé Payante ────────────────

@pytest.mark.asyncio
async def test_paid_key_never_appears_in_logs(caplog):
    """Test critique : vérifie que la clé PAID n'apparaît JAMAIS dans les logs."""
    cooldown_manager.clear()
    fake_secret = "AIzaSy_SUPER_CONFIDENTIAL_KEY_999"

    decision = RoutingDecision(
        model="gemini-3.1-pro",
        effort="high",
        fallback_chain=["api_paid_gemini"],
        provider="gemini",
        task_type="complex"
    )

    async def mock_runner(model_name: str, effort: str | None):
        raise RuntimeError("429 Too Many Requests")

    mock_genai_client = MagicMock()
    mock_resp = MagicMock(text="Analyse terminée")
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with caplog.at_level(logging.DEBUG):
        with patch("config.is_paid_key_authorized", return_value=True), \
             patch("config.get_effective_paid_key", return_value=fake_secret), \
             patch("google.genai.Client", return_value=mock_genai_client):

            await execute_with_fallback(mock_runner, decision, prompt="Mission secrète")

    log_text = caplog.text
    assert fake_secret not in log_text


# ─── 5. Tests Prompt Builder & Parseur Tolérant ───────────────────────────────

def test_prompt_builder_claude_vs_gemini():
    """Vérifie la génération de prompts adaptés par provider."""
    # Claude -> Balises XML
    prompt_claude = build_prompt(
        task="Refactorise auth.py",
        model="claude-3-7-sonnet",
        context={"user": "Pierre"}
    )
    assert "<system_role>" in prompt_claude
    assert "<objective>" in prompt_claude
    assert "<output_format>" in prompt_claude
    assert "Refactorise auth.py" in prompt_claude

    # Gemini -> Structure Markdown concise
    prompt_gemini = build_prompt(
        task="Analyse le planning transport",
        model="gemini-3.7-flash",
        effort="medium",
        context={"depart": "Paris"}
    )
    assert "# MISSION AUTONOME J.A.R.V.I.S." in prompt_gemini
    assert "NIVEAU DE RÉFLEXION : MEDIUM" in prompt_gemini
    assert "## 4. FORMAT DU RAPPORT FINAL OBLIGATOIRE" in prompt_gemini


def test_tolerant_json_parser():
    """Vérifie la tolérance du parseur face à des sorties polluées ou partielles."""
    # A. JSON propre dans bloc markdown
    clean_output = """
Voici l'exécution terminée :
```json
{
  "status": "completed",
  "summary": "Mise à jour réussie",
  "actions_done": ["patch appliqué"],
  "files_changed": ["config.py"],
  "errors": [],
  "next_steps": ["redémarrer le service"]
}
```
Bonne journée !
"""
    parsed = parse_agent_response(clean_output)
    assert parsed["status"] == "completed"
    assert parsed["summary"] == "Mise à jour réussie"
    assert parsed["files_changed"] == ["config.py"]

    # B. JSON brut au milieu de texte sans markdown
    noisy_output = """
Log line 1: info
Log line 2: check
{"status": "partial", "summary": "Tâche en cours", "actions_done": ["étape 1"], "files_changed": [], "errors": []}
Session terminée.
"""
    parsed_noisy = parse_agent_response(noisy_output)
    assert parsed_noisy["status"] == "partial"
    assert parsed_noisy["summary"] == "Tâche en cours"
    assert parsed_noisy["actions_done"] == ["étape 1"]

    # C. Sortie texte pur sans aucun JSON
    pure_text = "J'ai terminé l'analyse du système, tout est en ordre."
    parsed_text = parse_agent_response(pure_text)
    assert parsed_text["status"] == "completed"
    assert "J'ai terminé l'analyse" in parsed_text["summary"]
