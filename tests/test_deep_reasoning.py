"""tests/test_deep_reasoning.py
Test unitaire et d'intégration mockée pour le moteur de réflexion autonome DeepThinkingEngine.
Conforme à la règle no-paid-api-in-tests.md : Zéro appel API payante, mocks complets.
"""

import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from services.reasoning_service import (
    AutonomousReasoningEngine,
    run_deep_reasoning,
    run_deep_research_cli,
    ARTIFACTS_DIR
)
from google_antigravity import TaskResult, AntigravityQuotaExhaustedError
import config


@pytest.fixture(autouse=True)
def ensure_paid_key_authorized():
    orig = config.is_paid_key_authorized()
    config.set_paid_key_authorized(True)
    yield
    config.set_paid_key_authorized(orig)


@pytest.mark.asyncio
async def test_autonomous_investigation_generates_markdown_artifact():
    """Valide que AutonomousReasoningEngine orchestre les étapes et écrit l'artefact sur disque."""
    engine = AutonomousReasoningEngine()
    
    mock_markdown = (
        "# RAPPORT STRATÉGIQUE : AUDIT ARCHITECTURE CLOUD\n\n"
        "## 1. Synthèse Exécutive\n"
        "L'infrastructure hybride OCI ARM64 + Local PC offre une résilience optimale.\n\n"
        "## 2. Faits Clés & Données Vérifiées\n"
        "- 4 OCPU Ampere A1, 24 Go RAM.\n"
        "- Temps de réponse moyen < 15ms.\n\n"
        "## 3. Analyse Critique\n"
        "Aucun point de blocage détecté sur les buffers stdout/stderr.\n\n"
        "## 4. Recommandations\n"
        "Poursuivre le monitoring de session."
    )
    
    progress_steps = []
    async def track_progress(data):
        progress_steps.append(data.get("step"))
        
    with patch("services.reasoning_service.AntigravityAgent") as MockAgentClass:
        mock_instance = MagicMock()
        mock_instance.run_cli_task_stream = AsyncMock(return_value=TaskResult(
            summary=mock_markdown,
            status="completed",
            model_label="Gemini 3.1 Pro (High)"
        ))
        MockAgentClass.return_value = mock_instance
        
        result = await engine.run_autonomous_investigation(
            goal="Audit comparatif de l'infrastructure OCI vs Bare Metal",
            required_artifact="markdown_report",
            on_progress=track_progress,
            model="gemini-3.1-pro-high"
        )
        
        assert result["status"] == "completed"
        assert result["artifact_path"] is not None
        assert os.path.exists(result["artifact_path"])
        assert "L'infrastructure hybride" in result["summary"]
        assert len(progress_steps) >= 1
        
        # Vérification du fichier sur disque
        with open(result["artifact_path"], "r", encoding="utf-8") as f:
            content = f.read()
            assert "RAPPORT STRATÉGIQUE" in content
            
        # Nettoyage
        if os.path.exists(result["artifact_path"]):
            os.remove(result["artifact_path"])


@pytest.mark.asyncio
async def test_deep_reasoning_initiative_requires_confirmation():
    """Valide la règle absolue : Jarvis prend l'initiative mais DOIT demander confirmation si non confirmé."""
    # confirmed_by_user = False
    res = await run_deep_reasoning(
        question="Quelle est la meilleure approche d'orchestration multi-agents ?",
        confirmed_by_user=False
    )
    assert res["status"] == "requires_user_confirmation"
    assert "RÈGLE D'INITIATIVE ET DE CONFIRMATION OBLIGATOIRE" in res["instruction_to_jarvis"]
    assert "Pierre" in res["instruction_to_jarvis"]


@pytest.mark.asyncio
async def test_deep_reasoning_executes_when_confirmed():
    """Valide l'exécution fluide de deep_reasoning une fois l'accord de Pierre confirmé."""
    with patch("services.reasoning_service.reasoning_engine.run_autonomous_investigation") as mock_inv:
        mock_inv.return_value = {
            "status": "completed",
            "model_used": "Gemini 3.1 Pro (High)",
            "summary": "Synthèse percutante de l'analyse.",
            "full_output": "Rapport complet...",
            "artifact_path": "/fake/path/artifact.md",
            "artifact_filename": "artifact.md"
        }
        
        res = await run_deep_reasoning(
            question="Benchmark technique Kubernetes vs Nomad",
            confirmed_by_user=True
        )
        assert res["status"] == "completed"
        assert res["source"] == "Antigravity DeepThinkingEngine"
        assert res["summary"] == "Synthèse percutante de l'analyse."


@pytest.mark.asyncio
async def test_quota_exhausted_handling():
    """Valide la levée et la détection propre de AntigravityQuotaExhaustedError sans plantage silencieux."""
    with patch("services.reasoning_service.reasoning_engine.run_autonomous_investigation", side_effect=AntigravityQuotaExhaustedError("Quota 5h")):
        with pytest.raises(AntigravityQuotaExhaustedError):
            await run_deep_reasoning(
                question="Calcul tensoriel complexe",
                confirmed_by_user=True
            )
