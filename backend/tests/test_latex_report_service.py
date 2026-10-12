# -*- coding: utf-8 -*-
"""
tests/test_latex_report_service.py
Tests unitaires pour le service de génération et de compilation de rapports LaTeX L2 (Prompt 4).

Vérifie de manière 100% déterministe et hors-réseau :
1. Échappement rigoureux des caractères spéciaux LaTeX (& % $ # _ { } ~ ^ \\).
2. Structuration du document .tex (titre, résumé, sections, sources).
3. Compilation PDF isolée et réussie avec latexmk mocké.
4. Gestion du timeout lors de la compilation LaTeX via subprocess.
5. Gestion des erreurs de compilation LaTeX et extraction du message d'erreur depuis le fichier .log.
6. Création et inclusion systématique du rapport Markdown (.md) de repli.
7. Pipeline complet generate_and_compile_l2_report (succès PDF et repli MD).
8. Intégration dans le flux d'envoi d'e-mail avec pièces jointes mockées (PDF joint en succès, MD joint en échec).

TEST RÉEL MANUEL SUR VPS (DOCUMENTATION) :
------------------------------------------
Après avoir déployé et exécuté l'installation idempotente sur le VPS Oracle Cloud :
  sudo bash scripts/setup_vps_latex.sh
Pour tester manuellement la chaîne réelle complète en conditions réelles :
  1. Configurer les variables SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL).
  2. Lancer une requête L2 via Jarvis :
     "Jarvis, fais une analyse tactique et comparative des architectures de transformateurs et envoie le rapport par e-mail."
  3. Vérifier :
     - La génération du fichier .tex et la compilation de l'artefact .pdf dans workspace/reports/
     - La réception de l'e-mail avec le PDF en pièce jointe.
  4. Tester le repli Markdown en introduisant temporairement une commande TeX invalide ou en désactivant latexmk :
     - Vérifier que l'e-mail est reçu avec le rapport .md en pièce jointe et que l'erreur LaTeX est explicitement notifiée à l'utilisateur.
NOTE : Ne jamais automatiser de test réseau / SMTP / APT réel dans la suite pytest CI/CD.
"""

import os
import shutil
import tempfile
import subprocess
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

from services.latex_report_service import (
    escape_latex,
    sanitize_filename,
    markdown_to_latex_body,
    generate_latex_document,
    extract_latex_log_error,
    compile_latex,
    generate_and_compile_l2_report,
    LatexReportResult,
)


import uuid

@pytest.fixture
def isolated_dir():
    """Crée un répertoire temporaire isolé dans workspace/test_tmp nettoyé après chaque test."""
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace", "test_tmp")
    os.makedirs(base_dir, exist_ok=True)
    d = os.path.join(base_dir, f"test_{uuid.uuid4().hex[:8]}")
    os.makedirs(d, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)




# ─── 1. Tests d'Échappement et de Sécurisation ─────────────────────────────────

def test_escape_latex_special_chars():
    """Vérifie que tous les caractères réservés LaTeX (& % $ # _ { } ~ ^ \\) sont correctement protégés."""
    raw = r"Calcul de 10% & 20$ #1 _variable_ {test} 10^2 ~approx"
    escaped = escape_latex(raw)

    # Vérifications des échappements
    assert r"\%" in escaped
    assert r"\&" in escaped
    assert r"\$" in escaped
    assert r"\#" in escaped
    assert r"\_" in escaped
    assert r"\{" in escaped
    assert r"\}" in escaped
    assert r"\textasciicircum{}" in escaped
    assert r"\textasciitilde{}" in escaped


def test_escape_latex_none_and_empty():
    """Vérifie la robustesse face aux entrées None ou vides."""
    assert escape_latex(None) == ""
    assert escape_latex("") == ""


def test_sanitize_filename():
    """Vérifie le nettoyage des noms de fichiers de rapports."""
    clean = sanitize_filename("Rapport L2: Énergie & IA / Q3-2026 ??")
    assert ":" not in clean
    assert "/" not in clean
    assert "&" not in clean
    assert "?" not in clean
    assert "Rapport_L2" in clean


# ─── 2. Tests de Conversion Markdown et Génération .tex ───────────────────────

def test_markdown_to_latex_body_structure():
    """Vérifie la conversion du Markdown en structure LaTeX valide (sections, listes, gras, italique)."""
    md_input = (
        "# Section Principale\n"
        "Introduction avec du texte **en gras** et *en italique* et du `code_inline`.\n\n"
        "## Sous-section Analyse\n"
        "- Point 1 : première donnée avec 50% de croissance\n"
        "- Point 2 : seconde observation (coût: 100$)\n\n"
        "### Détail Technique\n"
        "1. Étape une\n"
        "2. Étape deux\n"
    )
    latex_output = markdown_to_latex_body(md_input)

    assert r"\section*{Section Principale}" in latex_output
    assert r"\subsection*{Sous-section Analyse}" in latex_output
    assert r"\subsubsection*{Détail Technique}" in latex_output
    assert r"\textbf{en gras}" in latex_output
    assert r"\textit{en italique}" in latex_output
    assert r"\texttt{code\_inline}" in latex_output
    assert r"\begin{itemize}" in latex_output
    assert r"\item Point 1 : première donnée avec 50\% de croissance" in latex_output
    assert r"\item Point 2 : seconde observation (coût: 100\$)" in latex_output
    assert r"\end{itemize}" in latex_output
    assert r"\begin{enumerate}" in latex_output
    assert r"\item Étape une" in latex_output
    assert r"\end{enumerate}" in latex_output


def test_generate_latex_document_full():
    """Vérifie que generate_latex_document assemble correctement titre, résumé, corps et sources."""
    title = "Benchmark des Modèles de Langage & Raisonnement"
    summary = "Résumé exécutif avec métriques clés : 95% de précision."
    body = "## Analyse Comparative\nRésultats détaillés des benchmarks."
    sources = [
        "https://arxiv.org/abs/1234.5678",
        {"title": "Documentation Officielle", "url": "https://example.com/docs"},
        "Rapport interne Stark Industries",
    ]

    tex_code = generate_latex_document(
        title=title,
        summary=summary,
        body=body,
        sources=sources,
    )

    assert r"\documentclass[11pt,a4paper]{article}" in tex_code
    assert r"\title{\textbf{\LARGE Benchmark des Modèles de Langage \& Raisonnement}}" in tex_code
    assert r"\begin{abstract}" in tex_code
    assert r"95\% de précision" in tex_code
    assert r"\end{abstract}" in tex_code
    assert r"\subsection*{Analyse Comparative}" in tex_code
    assert r"\section*{Sources et Références}" in tex_code
    assert r"\url{https://arxiv.org/abs/1234.5678}" in tex_code
    assert r"\href{https://example.com/docs}{Documentation Officielle}" in tex_code
    assert r"\item Rapport interne Stark Industries" in tex_code
    assert r"\end{document}" in tex_code


def test_markdown_to_latex_body_table_and_quote():
    """Vérifie la conversion des tableaux Markdown et citations en syntaxe LaTeX valide."""
    md_input = (
        "Voici un tableau comparatif :\n\n"
        "| Critère | Modèle A | Modèle B |\n"
        "|---|---|---|\n"
        "| Précision | 95% | 88% |\n"
        "| Vitesse | Rapide | Moyen |\n\n"
        "> Une citation importante d'expert.\n"
    )
    latex_output = markdown_to_latex_body(md_input)

    assert r"\begin{tabular}" in latex_output
    assert r"\toprule" in latex_output
    assert r"\midrule" in latex_output
    assert r"\bottomrule" in latex_output
    assert r"\end{tabular}" in latex_output
    assert r"Précision & 95\% & 88\% \\" in latex_output
    assert r"\begin{quote}" in latex_output
    assert r"Une citation importante d'expert." in latex_output
    assert r"\end{quote}" in latex_output


def test_generate_latex_document_target_pages_toc():
    """Vérifie que la table des matières n'est incluse que pour les documents d'au moins 3 pages."""
    # Moins de 3 pages -> pas de table des matières
    short_doc = generate_latex_document(
        title="Court Rapport",
        summary="Résumé court",
        body="## Intro\nTexte court.",
        target_pages=2,
    )
    assert r"\tableofcontents" not in short_doc

    # 3 pages -> table des matières incluse
    medium_doc = generate_latex_document(
        title="Rapport Moyen",
        summary="Résumé moyen",
        body="## Intro\nTexte moyen.",
        target_pages=3,
    )
    assert r"\tableofcontents" in medium_doc

    # 4 pages ou plus -> table des matières avec saut de page
    long_doc = generate_latex_document(
        title="Long Rapport",
        summary="Résumé long",
        body="## Intro\nTexte long.",
        target_pages=5,
    )
    assert r"\tableofcontents" in long_doc
    assert r"\newpage" in long_doc


def test_find_latex_compiler_auto_detection():
    """Vérifie le résolveur automatique de compilateur LaTeX."""
    from services.latex_report_service import find_latex_compiler

    # Si explicitement fourni et inexistant
    comp, comp_type = find_latex_compiler("non_existent_compiler_xyz_123")
    assert comp is None
    assert comp_type == "none"

    # Test avec un chemin mocké
    with patch("shutil.which", side_effect=lambda x: "/usr/bin/pdflatex" if "pdflatex" in x else None), \
         patch("os.path.exists", return_value=False):
        compiler, comp_type = find_latex_compiler()
        assert compiler == "/usr/bin/pdflatex"
        assert comp_type == "pdflatex"


# ─── 3. Tests de Compilation LaTeX & Gestion des Erreurs / Timeout ─────────────

def test_compile_latex_success(isolated_dir):
    """Vérifie la compilation réussie avec un mock de subprocess.run simulant latexmk."""
    tex_file = os.path.join(isolated_dir, "test_report.tex")
    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(r"\documentclass{article}\begin{document}Hello World\end{document}")
    pdf_file = os.path.join(isolated_dir, "test_report.pdf")

    def mock_subprocess_run(cmd, **kwargs):
        # Simule la production du PDF par latexmk
        with open(pdf_file, "wb") as f_pdf:
            f_pdf.write(b"%PDF-1.4 mock content")
        return MagicMock(returncode=0, stdout="Latexmk: All targets up-to-date", stderr="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        ok, pdf_path, log_path, err_extract = compile_latex(
            tex_path=tex_file,
            output_dir=isolated_dir,
            timeout=30.0,
        )

        assert ok is True
        assert pdf_path == pdf_file
        assert err_extract is None


def test_compile_latex_timeout(isolated_dir):
    """Vérifie la capture propre d'un timeout lors de la compilation TeX."""
    tex_file = os.path.join(isolated_dir, "test_timeout.tex")
    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(r"\documentclass{article}\begin{document}Loop\end{document}")

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="latexmk", timeout=5.0)):
        ok, pdf_path, log_path, err_extract = compile_latex(
            tex_path=tex_file,
            output_dir=isolated_dir,
            timeout=5.0,
        )

        assert ok is False
        assert pdf_path is None
        assert err_extract is not None
        assert "Timeout de compilation LaTeX dépassé (5.0s)" in err_extract


def test_compile_latex_compiler_not_found(isolated_dir):
    """Vérifie le comportement si latexmk n'est pas installé sur la machine."""
    tex_file = os.path.join(isolated_dir, "test_missing.tex")
    with open(tex_file, "w", encoding="utf-8") as f:
        f.write(r"\documentclass{article}\begin{document}Test\end{document}")

    with patch("subprocess.run", side_effect=FileNotFoundError("latexmk not found")):
        ok, pdf_path, log_path, err_extract = compile_latex(
            tex_path=tex_file,
            output_dir=isolated_dir,
            latexmk_bin="non_existent_latexmk",
        )

        assert ok is False
        assert pdf_path is None
        assert "introuvable sur le système" in err_extract


def test_extract_latex_log_error_parsing(isolated_dir):
    """Vérifie l'extraction d'erreur depuis un fichier .log TeX réel simulé."""
    log_file = os.path.join(isolated_dir, "error_doc.log")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(
            "This is pdfTeX, Version 3.141592653\n"
            "(./error_doc.tex\n"
            "! Undefined control sequence.\n"
            "l.42 \\invalidcommand\n"
            "                     {some text}\n"
            "Here is what happened...\n"
        )

    err = extract_latex_log_error(log_file)
    assert "! Undefined control sequence." in err
    assert "\\invalidcommand" in err


# ─── 4. Tests de generate_and_compile_l2_report (Succès et Repli MD) ──────────

def test_generate_and_compile_l2_report_success(isolated_dir):
    """Vérifie le pipeline complet en cas de succès de la compilation PDF."""
    pdf_created = os.path.join(isolated_dir, "rapport_test_l2.pdf")

    def mock_subprocess_run(cmd, **kwargs):
        with open(pdf_created, "wb") as f_pdf:
            f_pdf.write(b"%PDF-1.4 test content")
        return MagicMock(returncode=0, stdout="Latexmk: Success", stderr="")

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        result: LatexReportResult = generate_and_compile_l2_report(
            title="Rapport d'Analyse Tactique IA",
            content="## Résultats\nPerformance accrue de 40%.",
            summary="Synthèse générale.",
            sources=["https://example.com/ai"],
            output_dir=isolated_dir,
            base_name="rapport_test_l2",
        )

        assert result.success is True
        assert result.pdf_path is not None
        assert os.path.exists(result.pdf_path)
        assert result.md_path is not None
        assert os.path.exists(result.md_path)
        assert result.tex_path is not None
        assert os.path.exists(result.tex_path)
        assert "succès" in result.user_notice.lower()


def test_generate_and_compile_l2_report_fallback_to_markdown_on_error(isolated_dir):
    """Vérifie qu'en cas d'échec de compilation LaTeX, le fichier .md est bien généré et renvoyé en repli."""
    with patch("subprocess.run", side_effect=FileNotFoundError("latexmk missing")):
        result: LatexReportResult = generate_and_compile_l2_report(
            title="Rapport de Secours",
            content="Contenu important à préserver absolument.",
            summary="Résumé exécutif.",
            sources=["https://example.com/source"],
            output_dir=isolated_dir,
            base_name="rapport_fallback_test",
        )

        assert result.success is False
        assert result.pdf_path is None
        assert result.md_path is not None
        assert os.path.exists(result.md_path)
        # Vérification du contenu du fichier MD de repli
        with open(result.md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        assert "# Rapport de Secours" in md_content
        assert "Contenu important à préserver absolument." in md_content
        assert "https://example.com/source" in md_content
        # Vérification du message utilisateur explicite
        assert "Markdown" in result.user_notice
        assert "repli" in result.user_notice.lower() or "échoué" in result.user_notice.lower()


# ─── 5. Tests d'Intégration Dispatcher L2 avec Pièces Jointes Email ────────────

@pytest.mark.asyncio
async def test_dispatcher_l2_attaches_pdf_on_latex_success():
    """Vérifie que dispatch_tool('launch_deep_research') joint le PDF lors d'une compilation LaTeX réussie."""
    from core.tools.dispatcher import dispatch_tool
    from services.google_antigravity import AgentOutput

    mock_p = AgentOutput(status="success", conclusion="Prospection achevée", sources=["https://s1.org"], confidence="0.9")
    mock_a = AgentOutput(status="success", conclusion="Analyse achevée", sources=["https://s1.org"], confidence="0.95")
    mock_s = AgentOutput(status="success", conclusion="Synthèse L2 finale", sources=["https://s1.org"], confidence="0.95")

    fake_latex_res = LatexReportResult(
        success=True,
        pdf_path="/tmp/workspace/reports/rapport_l2.pdf",
        md_path="/tmp/workspace/reports/rapport_l2.md",
        tex_path="/tmp/workspace/reports/rapport_l2.tex",
        user_notice="Rapport PDF généré et compilé avec succès.",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock, side_effect=[mock_p, mock_a, mock_s]), \
         patch("services.latex_report_service.generate_and_compile_l2_report", return_value=fake_latex_res), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Analyse tactique comparative des batteries solides",
                "envoyer_email": True,
                "destinataire_email": "pierre@stark.com",
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        mock_send_email.assert_awaited_once()
        email_kwargs = mock_send_email.await_args.kwargs
        assert email_kwargs.get("to_email") == "pierre@stark.com"
        assert "[Multi-Agents L2]" in email_kwargs.get("subject", "")
        # Vérification que le PDF figure en première pièce jointe
        attachments = email_kwargs.get("attachments", [])
        assert "/tmp/workspace/reports/rapport_l2.pdf" in attachments


@pytest.mark.asyncio
async def test_dispatcher_l2_attaches_markdown_fallback_on_latex_failure():
    """Vérifie que dispatch_tool('launch_deep_research') joint le .md et prévient l'utilisateur si LaTeX échoue."""
    from core.tools.dispatcher import dispatch_tool
    from services.google_antigravity import AgentOutput

    mock_p = AgentOutput(status="success", conclusion="Prospection achevée", sources=["https://s1.org"], confidence="0.9")
    mock_a = AgentOutput(status="success", conclusion="Analyse achevée", sources=["https://s1.org"], confidence="0.95")
    mock_s = AgentOutput(status="success", conclusion="Synthèse L2 finale", sources=["https://s1.org"], confidence="0.95")

    fake_latex_fail = LatexReportResult(
        success=False,
        pdf_path=None,
        md_path="/tmp/workspace/reports/rapport_l2_fallback.md",
        tex_path="/tmp/workspace/reports/rapport_l2.tex",
        error_extract="latexmk introuvable",
        user_notice="La compilation du rapport en PDF LaTeX a échoué. Le rapport Markdown a été joint en repli.",
    )

    with patch("core.tools.dispatcher.verify_antigravity_cli_ready", new_callable=AsyncMock, return_value=(True, "", None)), \
         patch("core.tools.dispatcher.run_agentic", new_callable=AsyncMock, side_effect=[mock_p, mock_a, mock_s]), \
         patch("services.latex_report_service.generate_and_compile_l2_report", return_value=fake_latex_fail), \
         patch("services.local_agent_service.is_pc_connected_async", new_callable=AsyncMock, return_value=False), \
         patch("core.tools.dispatcher.send_email_async", new_callable=AsyncMock) as mock_send_email:

        resp = await dispatch_tool(
            name="launch_deep_research",
            args={
                "consigne": "Analyse comparative sans compilateur LaTeX",
                "envoyer_email": True,
                "destinataire_email": "pierre@stark.com",
                "sync": True,
            },
            websocket=None,
            session=None,
        )

        assert resp["status"] == "done"
        assert resp["verified"] is True
        mock_send_email.assert_awaited_once()
        email_kwargs = mock_send_email.await_args.kwargs
        attachments = email_kwargs.get("attachments", [])
        # Le fichier MD doit être joint à la place du PDF manquant
        assert "/tmp/workspace/reports/rapport_l2_fallback.md" in attachments
        # La notice sur l'échec LaTeX doit être présente dans le message utilisateur
        assert "LaTeX a échoué" in resp["user_message"] or "Markdown" in resp["user_message"]
