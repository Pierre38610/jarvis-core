"""services/latex_report_service.py
Service de génération et de compilation de rapports LaTeX pour les analyses multi-agents L2 de J.A.R.V.I.S.
Fournit :
  - L'échappement strict des caractères spéciaux LaTeX (& % $ # _ { } ~ ^ \\)
  - La structuration du document via un template LaTeX professionnel (titre, résumé, sections, sources)
  - La compilation isolée via latexmk avec gestion de timeout et capture des erreurs du log
  - La génération systématique d'un rapport Markdown de repli en cas d'échec de compilation
"""

import os
import re
import shutil
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger("jarvis.latex_report_service")

# Caractères spéciaux LaTeX à échapper obligatoirement : & % $ # _ { } ~ ^ \
LATEX_SPECIAL_CHARS = [
    ("\\", r"\textbackslash{}"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("$", r"\$"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]

DEFAULT_LATEX_TEMPLATE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[french]{babel}
\usepackage{geometry}
\geometry{top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm}
\usepackage{hyperref}
\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,      
    urlcolor=cyan,
    pdftitle={<PDFFILENAME>},
}
\usepackage{amsmath}
\setcounter{MaxMatrixCols}{20}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{xcolor}
\usepackage{fancyhdr}
\setlength{\headheight}{14pt}
\pagestyle{fancy}
\fancyhf{}
\rhead{\textcolor{gray}{J.A.R.V.I.S. --- Rapport Multi-Agents L2}}
\lhead{\textcolor{gray}{\nouppercase{\leftmark}}}
\rfoot{\textcolor{gray}{Page \thepage}}
\renewcommand{\headrulewidth}{0.4pt}

\title{\textbf{\LARGE <TITLE>}}
\author{\textbf{<AUTHOR>}}
\date{<DATE>}

\begin{document}

\maketitle
\thispagestyle{fancy}

<ABSTRACT_BLOCK>

<TOC_BLOCK>

\vspace{0.5cm}
\hrule
\vspace{0.5cm}

<BODY>

<SOURCES_BLOCK>

\vspace{1cm}
\begin{center}
\small\textcolor{gray}{Document généré automatiquement par J.A.R.V.I.S. -- Stark Multi-Agent Intelligence.}
\end{center}

\end{document}
"""


@dataclass
class LatexReportResult:
    """Structure de résultat standardisée pour la production d'un rapport LaTeX / Markdown."""
    success: bool
    pdf_path: Optional[str] = None
    md_path: Optional[str] = None
    tex_path: Optional[str] = None
    log_path: Optional[str] = None
    error_extract: Optional[str] = None
    user_notice: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "pdf_path": self.pdf_path,
            "md_path": self.md_path,
            "tex_path": self.tex_path,
            "log_path": self.log_path,
            "error_extract": self.error_extract,
            "user_notice": self.user_notice,
        }


def escape_latex(text: Any) -> str:
    """Échappe rigoureusement les caractères réservés LaTeX pour prévenir toute injection ou erreur TeX.
    Traite en premier l'antislash pour éviter les doubles échappements et filtre les caractères de contrôle non imprimables.
    """
    if text is None:
        return ""
    s = str(text)
    # Nettoie les caractères de contrôle non imprimables (ex: vertical tab \x0b, etc.)
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', s)
    for char, replacement in LATEX_SPECIAL_CHARS:
        s = s.replace(char, replacement)
    return s


def sanitize_filename(name: str) -> str:
    """Nettoie une chaîne pour en faire un nom de fichier sécurisé."""
    s = re.sub(r'[^a-zA-Z0-9_\-]', '_', name.strip())
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:60] or "rapport_l2"


def _format_inline_markdown(text: str) -> str:
    """Échappe le texte brut et convertit les marqueurs inline Markdown en LaTeX valide."""
    placeholders: List[str] = []

    def repl_code(m: re.Match) -> str:
        idx = len(placeholders)
        code_txt = escape_latex(m.group(1))
        placeholders.append(f"\\texttt{{{code_txt}}}")
        return f"PHLATEXINDEX{idx}ENDPH"

    def repl_link(m: re.Match) -> str:
        idx = len(placeholders)
        anchor = escape_latex(m.group(1))
        url = escape_latex(m.group(2))
        placeholders.append(f"\\href{{{url}}}{{{anchor}}}")
        return f"PHLATEXINDEX{idx}ENDPH"

    def repl_bold(m: re.Match) -> str:
        idx = len(placeholders)
        bold_txt = escape_latex(m.group(1))
        placeholders.append(f"\\textbf{{{bold_txt}}}")
        return f"PHLATEXINDEX{idx}ENDPH"

    def repl_italic(m: re.Match) -> str:
        idx = len(placeholders)
        it_txt = escape_latex(m.group(1))
        placeholders.append(f"\\textit{{{it_txt}}}")
        return f"PHLATEXINDEX{idx}ENDPH"

    t = re.sub(r'`([^`]+)`', repl_code, text)
    t = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', repl_link, t)
    t = re.sub(r'\*\*([^*]+)\*\*', repl_bold, t)
    t = re.sub(r'__([^_]+)__', repl_bold, t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', repl_italic, t)

    t_escaped = escape_latex(t)

    for idx, ph_val in enumerate(placeholders):
        t_escaped = t_escaped.replace(f"PHLATEXINDEX{idx}ENDPH", ph_val)

    return t_escaped


def _parse_markdown_table(table_lines: List[str]) -> str:
    """Convertit un bloc de lignes Markdown de tableau en environnement tabular LaTeX."""
    if not table_lines:
        return ""
    
    rows: List[List[str]] = []
    for line in table_lines:
        raw_cells = line.strip().strip("|").split("|")
        cells = [c.strip() for c in raw_cells]
        # Ignore la ligne de séparation |---|---|
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue
        rows.append(cells)

    if not rows:
        return ""

    num_cols = max(len(r) for r in rows)
    col_format = " ".join(["l"] * num_cols)

    latex_table = [
        r"\begin{center}",
        f"\\begin{{tabular}}{{{col_format}}}",
        r"\toprule"
    ]

    header = rows[0]
    # Complète les cellules manquantes
    while len(header) < num_cols:
        header.append("")
    header_formatted = [f"\\textbf{{{_format_inline_markdown(c)}}}" for c in header]
    latex_table.append(" & ".join(header_formatted) + r" \\")
    latex_table.append(r"\midrule")

    for row in rows[1:]:
        while len(row) < num_cols:
            row.append("")
        row_formatted = [_format_inline_markdown(c) for c in row]
        latex_table.append(" & ".join(row_formatted) + r" \\")

    latex_table.append(r"\bottomrule")
    latex_table.append(r"\end{tabular}")
    latex_table.append(r"\end{center}")

    return "\n".join(latex_table)


def markdown_to_latex_body(text: str) -> str:
    """Convertit du texte structuré ou Markdown en syntaxe LaTeX valide et protégée contre les injections."""
    if not text:
        return ""

    lines = text.strip().split("\n")
    latex_parts: List[str] = []
    in_itemize = False
    in_enumerate = False
    in_code_block = False
    table_buffer: List[str] = []

    def close_lists() -> List[str]:
        nonlocal in_itemize, in_enumerate
        res = []
        if in_itemize:
            res.append(r"\end{itemize}")
            in_itemize = False
        if in_enumerate:
            res.append(r"\end{enumerate}")
            in_enumerate = False
        return res

    def flush_table() -> List[str]:
        nonlocal table_buffer
        res = []
        if table_buffer:
            tbl = _parse_markdown_table(table_buffer)
            if tbl:
                res.append(tbl)
            table_buffer = []
        return res

    for raw_line in lines:
        line = raw_line.strip()

        # Gestion des blocs de code multi-lignes ```...```
        if line.startswith("```"):
            latex_parts.extend(close_lists())
            if table_buffer:
                latex_parts.extend(flush_table())
            if not in_code_block:
                in_code_block = True
                latex_parts.append(r"\begin{verbatim}")
            else:
                in_code_block = False
                latex_parts.append(r"\end{verbatim}")
            continue

        if in_code_block:
            latex_parts.append(raw_line)
            continue

        # Détection de ligne de tableau Markdown
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 2:
            latex_parts.extend(close_lists())
            table_buffer.append(line)
            continue
        elif table_buffer:
            latex_parts.extend(flush_table())

        if not line:
            latex_parts.extend(close_lists())
            latex_parts.append(r"\vspace{0.2cm}")
            continue

        # Ligne horizontale
        if line in ("---", "***", "___"):
            latex_parts.extend(close_lists())
            latex_parts.append(r"\vspace{0.3cm}\hrule\vspace{0.3cm}")
            continue

        # Citation / Blockquote
        if line.startswith("> "):
            latex_parts.extend(close_lists())
            quote_text = _format_inline_markdown(line[2:].strip())
            latex_parts.append(f"\\begin{{quote}}\n\\textit{{{quote_text}}}\n\\end{{quote}}")
            continue

        # Titres de sections Markdown
        if line.startswith("### "):
            latex_parts.extend(close_lists())
            title = _format_inline_markdown(line[4:].strip())
            latex_parts.append(f"\\subsubsection*{{{title}}}")
            continue
        elif line.startswith("## "):
            latex_parts.extend(close_lists())
            title = _format_inline_markdown(line[3:].strip())
            latex_parts.append(f"\\subsection*{{{title}}}")
            continue
        elif line.startswith("# "):
            latex_parts.extend(close_lists())
            title = _format_inline_markdown(line[2:].strip())
            latex_parts.append(f"\\section*{{{title}}}")
            continue

        # Listes à puces (- ou *)
        if line.startswith("- ") or line.startswith("* "):
            if in_enumerate:
                latex_parts.extend(close_lists())
            if not in_itemize:
                latex_parts.append(r"\begin{itemize}")
                in_itemize = True
            item_content = line[2:].strip()
            item_latex = _format_inline_markdown(item_content)
            latex_parts.append(f"  \\item {item_latex}")
            continue

        # Listes numérotées
        num_match = re.match(r'^(\d+)\.\s+(.*)$', line)
        if num_match:
            if in_itemize:
                latex_parts.extend(close_lists())
            if not in_enumerate:
                latex_parts.append(r"\begin{enumerate}")
                in_enumerate = True
            item_content = num_match.group(2).strip()
            item_latex = _format_inline_markdown(item_content)
            latex_parts.append(f"  \\item {item_latex}")
            continue

        # Paragraphe normal
        latex_parts.extend(close_lists())
        p_latex = _format_inline_markdown(line)
        latex_parts.append(f"{p_latex}\n")

    if in_code_block:
        latex_parts.append(r"\end{verbatim}")
    if table_buffer:
        latex_parts.extend(flush_table())
    latex_parts.extend(close_lists())
    return "\n".join(latex_parts)


def generate_latex_document(
    title: str,
    summary: str = "",
    body: str = "",
    sources: Optional[List[Any]] = None,
    author: str = "J.A.R.V.I.S. (Stark Multi-Agent Intelligence)",
    date_str: Optional[str] = None,
    target_pages: int = 3,
    template: str = DEFAULT_LATEX_TEMPLATE,
) -> str:
    """Génère le code source complet d'un document .tex à partir de données structurées échappées."""
    escaped_title = escape_latex(title)
    escaped_author = escape_latex(author)
    escaped_date = escape_latex(date_str or datetime.now().strftime("%d/%m/%Y à %H:%M"))

    # Résumé / Abstract
    abstract_block = ""
    if summary and summary.strip():
        abstract_content = markdown_to_latex_body(summary.strip())
        abstract_block = (
            "\\begin{abstract}\n"
            "\\noindent " + abstract_content + "\n"
            "\\end{abstract}"
        )

    # Bloc Table des matières (si rapport >= 3 pages)
    toc_block = ""
    if target_pages >= 3:
        toc_block = (
            "\\vspace{0.3cm}\n"
            "\\tableofcontents\n"
            "\\vspace{0.5cm}\n"
        )
        if target_pages >= 4:
            toc_block += "\\newpage\n"

    # Corps du rapport
    body_content = markdown_to_latex_body(body) if body else ""

    # Bloc des sources
    sources_block = ""
    if sources:
        cleaned_sources = [s for s in sources if s]
        if cleaned_sources:
            items = []
            for src in cleaned_sources:
                if isinstance(src, dict):
                    url = src.get("url") or src.get("link") or ""
                    title_s = src.get("title") or src.get("name") or url or "Source"
                    if url:
                        items.append(f"  \\item \\href{{{escape_latex(url)}}}{{{escape_latex(title_s)}}}")
                    else:
                        items.append(f"  \\item {escape_latex(title_s)}")
                else:
                    src_str = str(src).strip()
                    if src_str.startswith("http://") or src_str.startswith("https://"):
                        items.append(f"  \\item \\url{{{escape_latex(src_str)}}}")
                    else:
                        items.append(f"  \\item {escape_latex(src_str)}")

            sources_block = (
                "\\section*{Sources et Références}\n"
                "\\begin{itemize}\n"
                + "\n".join(items) + "\n"
                "\\end{itemize}"
            )

    tex_code = template
    tex_code = tex_code.replace("<PDFFILENAME>", escaped_title)
    tex_code = tex_code.replace("<TITLE>", escaped_title)
    tex_code = tex_code.replace("<AUTHOR>", escaped_author)
    tex_code = tex_code.replace("<DATE>", escaped_date)
    tex_code = tex_code.replace("<ABSTRACT_BLOCK>", abstract_block)
    tex_code = tex_code.replace("<TOC_BLOCK>", toc_block)
    tex_code = tex_code.replace("<BODY>", body_content)
    tex_code = tex_code.replace("<SOURCES_BLOCK>", sources_block)

    return tex_code


def extract_latex_log_error(log_path: Optional[str], fallback_output: str = "") -> str:
    """Extrait un message d'erreur clair et exploitable depuis le fichier .log généré par TeX."""
    if log_path and os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            error_lines = []
            for i, l in enumerate(lines):
                l_s = l.strip()
                if l_s.startswith("!") or "LaTeX Error:" in l_s or "Emergency stop" in l_s or "Fatal error" in l_s:
                    error_lines.append(l_s)
                    for j in range(i + 1, min(i + 4, len(lines))):
                        if lines[j].strip():
                            error_lines.append(lines[j].strip())
                    break
            if error_lines:
                return " ; ".join(error_lines[:3])
            
            # Dernières lignes pertinentes si pas de point d'exclamation trouvé
            non_empty = [l.strip() for l in lines if l.strip()]
            if non_empty:
                return " ; ".join(non_empty[-3:])
        except Exception as e:
            logger.warning(f"[LaTeX Report Service] Erreur lecture log {log_path}: {e}")

    if fallback_output:
        lines = [l.strip() for l in fallback_output.split("\n") if l.strip()]
        return " ; ".join(lines[-3:])[:300]

    return "Erreur TeX inconnue (aucun détail disponible dans le log)"


def find_latex_compiler(preferred_bin: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Détecte le meilleur compilateur LaTeX disponible (latexmk, pdflatex, xelatex).
    Privilégie pdflatex sur Windows si perl est absent (évite le blocage de MiKTeX latexmk).
    """
    if preferred_bin and preferred_bin not in ("latexmk", "auto", ""):
        w = shutil.which(preferred_bin) or (preferred_bin if os.path.exists(preferred_bin) else None)
        if w:
            return w, "custom"
        return None, "none"

    has_perl = bool(shutil.which("perl"))

    # 1. Si perl est présent ou sur Linux/VPS, tester latexmk en premier
    if (has_perl or os.name != "nt") and shutil.which("latexmk"):
        return shutil.which("latexmk"), "latexmk"

    # 2. pdflatex (incluant les chemins Windows MiKTeX et TeX Live standards)
    pdflatex_candidates = [
        "pdflatex",
        r"C:\Users\pierr\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"C:\texlive\2026\bin\windows\pdflatex.exe",
        r"C:\texlive\2025\bin\windows\pdflatex.exe",
        r"C:\texlive\2024\bin\windows\pdflatex.exe",
        "/usr/bin/pdflatex",
        "/usr/local/bin/pdflatex",
        "/home/opc/.local/bin/pdflatex",
    ]
    for cand in pdflatex_candidates:
        w = shutil.which(cand) or (cand if os.path.exists(cand) else None)
        if w:
            return w, "pdflatex"

    # 3. latexmk si aucun pdflatex direct n'a été trouvé
    latexmk_path = shutil.which("latexmk")
    if latexmk_path:
        return latexmk_path, "latexmk"

    # 4. xelatex
    xelatex_path = shutil.which("xelatex")
    if xelatex_path:
        return xelatex_path, "xelatex"

    return None, ""


def compile_latex(
    tex_path: str,
    output_dir: Optional[str] = None,
    timeout: float = 60.0,
    latexmk_bin: str = "latexmk",
) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Compile un fichier .tex en PDF avec latexmk ou pdflatex dans un dossier isolé.
    
    Args:
        tex_path: Chemin absolu vers le fichier .tex
        output_dir: Répertoire de travail pour la compilation
        timeout: Délai d'attente maximum en secondes
        latexmk_bin: Commande latexmk ou pdflatex (défaut: 'latexmk')
        
    Returns:
        Tuple (succès: bool, pdf_path: Optional[str], log_path: Optional[str], error_extract: Optional[str])
    """
    work_dir = os.path.abspath(output_dir or os.path.dirname(tex_path))
    os.makedirs(work_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(tex_path))[0]
    tex_filename = os.path.basename(tex_path)
    pdf_path = os.path.join(work_dir, f"{base_name}.pdf")
    log_path = os.path.join(work_dir, f"{base_name}.log")

    compiler_bin, compiler_type = find_latex_compiler(latexmk_bin)
    
    # Si non détecté par auto-détection, utilise l'argument tel quel pour permettre le mocking dans les tests
    if not compiler_bin:
        compiler_bin = latexmk_bin
        compiler_type = "latexmk" if "latexmk" in latexmk_bin else "pdflatex"

    if compiler_type == "latexmk" or "latexmk" in str(compiler_bin).lower():
        cmd = [
            compiler_bin,
            "-pdf",
            "-interaction=nonstopmode",
            tex_filename
        ]
    else:
        # Configuration pdflatex / MiKTeX / Linux TeX Live
        cmd = [
            compiler_bin,
            "-interaction=nonstopmode",
            "-file-line-error",
            tex_filename
        ]
        if os.name == "nt" or "miktex" in str(compiler_bin).lower():
            cmd.insert(1, "-enable-installer")

    try:
        logger.info(f"[LaTeX Report Service] Compilation : {' '.join(cmd)} dans {work_dir}")
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Si échec avec latexmk (ex: manque de perl sous Windows), tentative de repli immédiate vers pdflatex
        if proc.returncode != 0 and (compiler_type == "latexmk" or "latexmk" in str(compiler_bin).lower()):
            pdf_cand, _ = find_latex_compiler(preferred_bin="pdflatex")
            if pdf_cand and pdf_cand != compiler_bin:
                logger.info(f"[LaTeX Report Service] Repli automatique de latexmk vers pdflatex ({pdf_cand})")
                cmd_fallback = [
                    pdf_cand,
                    "-interaction=nonstopmode",
                    "-file-line-error",
                    tex_filename
                ]
                if os.name == "nt" or "miktex" in str(pdf_cand).lower():
                    cmd_fallback.insert(1, "-enable-installer")
                proc = subprocess.run(
                    cmd_fallback,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                compiler_bin = pdf_cand
                compiler_type = "pdflatex"
                cmd = cmd_fallback

        # Si pdflatex et présence potentielle de TOC/liens, passe 2 pour résoudre la table des matières
        if proc.returncode == 0 and compiler_type == "pdflatex":
            try:
                subprocess.run(
                    cmd,
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout / 2,
                )
            except Exception:
                pass

        if proc.returncode == 0 and os.path.exists(pdf_path):
            logger.info(f"[LaTeX Report Service] Compilation PDF réussie : {pdf_path}")
            return True, pdf_path, log_path if os.path.exists(log_path) else None, None

        # Erreur lors de la compilation
        err_msg = extract_latex_log_error(log_path, fallback_output=f"{proc.stdout}\n{proc.stderr}")
        logger.warning(f"[LaTeX Report Service] Échec compilation TeX (code {proc.returncode}): {err_msg}")
        return False, None, log_path if os.path.exists(log_path) else None, err_msg

    except subprocess.TimeoutExpired:
        err_msg = f"Timeout de compilation LaTeX dépassé ({timeout}s)"
        logger.warning(f"[LaTeX Report Service] {err_msg}")
        return False, None, log_path if os.path.exists(log_path) else None, err_msg

    except FileNotFoundError:
        err_msg = f"Le compilateur LaTeX ('{compiler_bin}') est introuvable sur le système."
        logger.warning(f"[LaTeX Report Service] {err_msg}")
        return False, None, None, err_msg

    except Exception as exc:
        err_msg = f"Erreur d'exécution de la compilation LaTeX : {exc}"
        logger.error(f"[LaTeX Report Service] {err_msg}", exc_info=True)
        return False, None, log_path if os.path.exists(log_path) else None, err_msg


def generate_and_compile_l2_report(
    title: str,
    content: str,
    summary: str = "",
    sources: Optional[List[Any]] = None,
    output_dir: Optional[str] = None,
    base_name: Optional[str] = None,
    timeout: float = 60.0,
    latexmk_bin: str = "latexmk",
    target_pages: int = 3,
) -> LatexReportResult:
    """Génère le document .tex, crée un fichier .md de repli, puis compile le PDF.
    En cas d'échec de compilation TeX, retourne le chemin du fichier .md de repli et le détail de l'erreur.
    """
    target_dir = os.path.abspath(
        output_dir or os.path.join(getattr(config, "WORKSPACE_DIR", "./workspace"), "reports")
    )
    os.makedirs(target_dir, exist_ok=True)

    slug = sanitize_filename(base_name or f"rapport_l2_{int(datetime.now().timestamp())}")
    md_path = os.path.join(target_dir, f"{slug}.md")
    tex_path = os.path.join(target_dir, f"{slug}.tex")

    # 1. Écriture systématique du rapport Markdown de repli
    md_lines = [f"# {title}\n"]
    if summary and summary.strip():
        md_lines.append(f"**Résumé exécutif :**\n{summary.strip()}\n")
    if content and content.strip():
        md_lines.append(f"{content.strip()}\n")
    if sources:
        cleaned_s = [s for s in sources if s]
        if cleaned_s:
            md_lines.append("## Sources & Références")
            for s in cleaned_s:
                if isinstance(s, dict):
                    u = s.get("url") or s.get("link") or ""
                    t = s.get("title") or s.get("name") or u or "Source"
                    md_lines.append(f"- [{t}]({u})" if u else f"- {t}")
                else:
                    md_lines.append(f"- {s}")
            md_lines.append("")

    try:
        with open(md_path, "w", encoding="utf-8") as f_md:
            f_md.write("\n".join(md_lines))
    except Exception as md_err:
        logger.warning(f"[LaTeX Report Service] Impossible d'écrire le fichier MD de repli {md_path}: {md_err}")

    # 2. Génération et écriture du document .tex avec échappement strict
    tex_code = generate_latex_document(
        title=title,
        summary=summary,
        body=content,
        sources=sources,
        target_pages=target_pages,
    )

    try:
        with open(tex_path, "w", encoding="utf-8") as f_tex:
            f_tex.write(tex_code)
    except Exception as tex_err:
        logger.error(f"[LaTeX Report Service] Erreur écriture fichier TeX {tex_path}: {tex_err}")
        return LatexReportResult(
            success=False,
            pdf_path=None,
            md_path=md_path,
            tex_path=tex_path,
            log_path=None,
            error_extract=str(tex_err),
            user_notice=f"Échec de création du fichier TeX ({tex_err}). Rapport Markdown disponible en repli.",
        )

    # 3. Compilation du PDF
    ok, pdf_path, log_path, err_extract = compile_latex(
        tex_path=tex_path,
        output_dir=target_dir,
        timeout=timeout,
        latexmk_bin=latexmk_bin,
    )

    if ok and pdf_path:
        notice = f"Rapport PDF généré et compilé avec succès ({os.path.basename(pdf_path)})."
        return LatexReportResult(
            success=True,
            pdf_path=pdf_path,
            md_path=md_path,
            tex_path=tex_path,
            log_path=log_path,
            error_extract=None,
            user_notice=notice,
        )
    else:
        notice = (
            f"La compilation du rapport en PDF LaTeX a échoué ({err_extract or 'erreur TeX'}). "
            f"Le rapport Markdown ({os.path.basename(md_path)}) a été généré et joint en repli."
        )
        return LatexReportResult(
            success=False,
            pdf_path=None,
            md_path=md_path,
            tex_path=tex_path,
            log_path=log_path,
            error_extract=err_extract,
            user_notice=notice,
        )

