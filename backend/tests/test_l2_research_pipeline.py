"""tests/test_l2_research_pipeline.py
Tests exhaustifs de non-régression pour la recherche de niveau 2 (L2) :
- Collecte des sources et robustesse de l'extraction JSON (ANSI, code blocks, virgules traînantes, aliases)
- Résilience multi-agents et repli API directe
- Pipeline Map-Reduce complet (Prospecteur -> Analyste -> Synthèse)
- Génération et compilation du rapport LaTeX PDF
- Détection automatique d'envoi par e-mail et livraison avec pièce jointe PDF
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.tools.dispatcher import _execute_cli_map_reduce_pipeline, dispatch_tool
from services.agentic_runner import (
    AgentOutput,
    _extract_json_payload,
    _validate_json_schema,
    run_agentic,
)
from services.latex_report_service import LatexReportResult


def test_extract_json_payload_with_ansi_and_fences():
    """Vérifie l'extraction JSON en présence de codes ANSI et de blocs markdown."""
    raw = "\x1b[32m[INFO] Démarrage\x1b[0m\n```json\n{\n  \"facts\": [\"Fait 1: OK\", \"Fait 2: Validé\"],\n  \"sources\": [\"https://example.com/doc\"],\n  \"conclusion\": \"Synthèse complète\",\n  \"confidence\": 0.95,\n  \"artifacts\": []\n}\n```\n\x1b[34m[DONE]\x1b[0m"
    res = _extract_json_payload(raw)
    assert res is not None
    assert res["conclusion"] == "Synthèse complète"
    assert res["sources"] == ["https://example.com/doc"]
    assert len(res["facts"]) == 2
    assert _validate_json_schema(res) is True


def test_extract_json_payload_with_trailing_commas_and_nested_sources():
    """Vérifie la robustesse face aux virgules traînantes et sources sous forme d'objets imbriqués."""
    raw = """
    Voici les résultats de prospection :
    {
      "conclusion": "Analyse réussie.",
      "sources": [
        {"title": "Doc Officielle", "url": "https://example.com"},
      ],
      "facts": ["Faits chiffrés : 99.9% disponibilité"],
    }
    """
    res = _extract_json_payload(raw)
    assert res is not None
    assert res["conclusion"] == "Analyse réussie."
    assert len(res["sources"]) == 1
    assert _validate_json_schema(res) is True


def test_extract_json_payload_alias_normalization():
    """Vérifie que les alias (summary, references, data, etc.) sont correctement normalisés."""
    raw = """
    {
      "summary": "Résumé de l'exploration technique",
      "references": ["RFC 7519", "Doc Python"],
      "data": ["Point 1", "Point 2"]
    }
    """
    res = _extract_json_payload(raw)
    assert res is not None
    assert res["conclusion"] == "Résumé de l'exploration technique"
    assert res["sources"] == ["RFC 7519", "Doc Python"]
    assert res["facts"] == ["Point 1", "Point 2"]
    assert _validate_json_schema(res) is True


def test_extract_json_payload_synthesize_conclusion_from_facts_if_missing():
    """Si seule la liste de faits et sources est renvoyée, la conclusion est synthétisée sans échec."""
    raw = """
    {
      "facts": ["Serveur opérationnel sur port 8000", "Latence moyenne 12ms"],
      "sources": ["metrics.log"]
    }
    """
    res = _extract_json_payload(raw)
    assert res is not None
    assert "Serveur opérationnel" in res["conclusion"]
    assert res["sources"] == ["metrics.log"]
    assert _validate_json_schema(res) is True


@pytest.mark.asyncio
async def test_l2_map_reduce_pipeline_full_success_with_email_delivery():
    """Vérifie le déroulement complet du pipeline L2 jusqu'à la compilation PDF et l'envoi d'e-mail."""
    consigne = "Fais une recherche de niveau 2 sur l'architecture ARM64 et envoie le rapport pdf latex sur mon mail"

    prospector_out = AgentOutput(
        conclusion="Faits collectés : Architecture ARM64 performante et économe.",
        confidence=0.95,
        sources=["https://arm.com/spec", "https://kernel.org"],
        facts=["ARM64 consomme 40% moins d'énergie", "Large adoption serveur"],
        model="flash",
        effort="medium",
        status="success",
    )

    analyst_out = AgentOutput(
        conclusion="Analyse comparative : ARM64 vs x86-64 avec compromis coût/densité calcul.",
        confidence=0.92,
        sources=["https://arm.com/spec", "https://anandtech.com"],
        open_questions=["Compatibilité binaire sur vieux logiciels x86"],
        model="pro",
        effort="high",
        status="success",
    )

    synthesis_out = AgentOutput(
        conclusion="Rapport de synthèse L2 complet : Recommandation de migration progressive vers ARM64.",
        confidence=0.96,
        sources=["https://arm.com/spec", "https://kernel.org", "https://anandtech.com"],
        artifacts=["schema_arm64.png"],
        model="pro",
        effort="medium",
        status="success",
    )

    agent_outputs = [prospector_out, analyst_out, synthesis_out]

    async def mock_run_agentic(*args, **kwargs):
        return agent_outputs.pop(0)

    fake_latex_res = LatexReportResult(
        success=True,
        pdf_path="/tmp/workspace/reports/rapport_l2_arm64.pdf",
        md_path="/tmp/workspace/reports/rapport_l2_arm64.md",
        tex_path="/tmp/workspace/reports/rapport_l2_arm64.tex",
        user_notice="Rapport PDF compilé avec succès.",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", "agy")), \
         patch("core.tools.dispatcher.run_agentic", side_effect=mock_run_agentic), \
         patch("services.latex_report_service.generate_and_compile_l2_report", return_value=fake_latex_res), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email, \
         patch("core.tools.dispatcher.spawn_subagent", new_callable=AsyncMock), \
         patch("core.tools.dispatcher.update_subagent", new_callable=AsyncMock), \
         patch("core.tools.dispatcher.complete_subagent", new_callable=AsyncMock):

        res = await _execute_cli_map_reduce_pipeline(
            consigne=consigne,
            envoyer_email=False,  # doit être auto-détecté depuis la consigne
            destinataire_email="pierrecassagnettes@gmail.com",
            session=None,
            websocket=None,
            target_pages=3,
        )

        assert res.is_success is True
        assert "Recommandation de migration" in res.user_message
        assert res.data["delivery"]["status"] == "sent"
        assert res.data["delivery"]["to_email"] == "pierrecassagnettes@gmail.com"
        assert "/tmp/workspace/reports/rapport_l2_arm64.pdf" in res.data["delivery"]["attachments"]
        mock_send_email.assert_awaited_once()
        _, email_kwargs = mock_send_email.call_args
        assert "/tmp/workspace/reports/rapport_l2_arm64.pdf" in email_kwargs["attachments"]


@pytest.mark.asyncio
async def test_dispatch_tool_launch_deep_research_auto_detects_email_and_pages():
    """Vérifie que dispatch_tool('launch_deep_research') transmet bien target_pages et envoyer_email."""
    consigne = "Recherche de niveau 2 sur la fusion nucléaire (rapport de 5 pages) et envoie par mail"

    fake_latex_res = LatexReportResult(
        success=True,
        pdf_path="/tmp/workspace/reports/rapport_fusion.pdf",
        md_path="/tmp/workspace/reports/rapport_fusion.md",
        tex_path="/tmp/workspace/reports/rapport_fusion.tex",
        user_notice="Rapport PDF compilé.",
    )

    with patch("core.tools.dispatcher._execute_cli_map_reduce_pipeline", new_callable=AsyncMock) as mock_pipeline:
        from core.tools.result import ToolResult
        mock_pipeline.return_value = ToolResult.done(
            user_message="Analyse L2 sur la fusion terminée.",
            verified=True,
            data={"delivery": {"status": "sent"}},
        )

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": consigne,
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        mock_pipeline.assert_awaited_once()
        _, kwargs = mock_pipeline.call_args
        assert kwargs["target_pages"] == 5
        assert kwargs["envoyer_email"] is True
