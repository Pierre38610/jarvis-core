#!/usr/bin/env bash
# ==============================================================================
# Script d'installation VPS idempotent pour la génération de rapports LaTeX
# ==============================================================================
# Usage :
#   sudo bash scripts/setup_vps_latex.sh
#   ou
#   bash scripts/setup_vps_latex.sh (avec sudo configuré pour l'utilisateur)
#
# Idempotence :
#   - Vérifie la présence des paquets Debian/Ubuntu requis avant installation.
#   - N'installe que les paquets strictement nécessaires manquants.
#   - Peut être relancé indéfiniment sans effet de bord ni réinstallation inutile.
#
# Paquets installés :
#   - texlive-latex-recommended
#   - texlive-latex-extra
#   - texlive-lang-french
#   - texlive-fonts-recommended
#   - latexmk
#   - lmodern
#
# Test de compilation :
#   - Crée un document .tex de test minimal contenant des accents français
#     dans un dossier temporaire isolé.
#   - Compile via 'latexmk -pdf -interaction=nonstopmode'.
#   - Vérifie la génération effective du fichier PDF et retourne un code d'erreur
#     non nul en cas d'échec.
#   - Nettoie automatiquement le dossier temporaire via trap.
# ==============================================================================

set -Eeuo pipefail

# 1. Gestion des privilèges d'exécution (root ou sudo)
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
        echo "[INFO] Exécution en mode non-root via sudo."
    else
        echo "[ERREUR] Ce script requiert des privilèges administrateur (root ou sudo disponible)." >&2
        exit 1
    fi
fi

# 2. Détection du gestionnaire de paquets et installation
if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="apt"
    REQUIRED_PACKAGES=(
        texlive-latex-recommended
        texlive-latex-extra
        texlive-lang-french
        texlive-fonts-recommended
        latexmk
        lmodern
    )
elif command -v dnf >/dev/null 2>&1; then
    PKG_MGR="dnf"
    REQUIRED_PACKAGES=(
        texlive-scheme-basic
        texlive-collection-latexrecommended
        texlive-collection-fontsrecommended
        texlive-babel-french
        texlive-lm
        latexmk
    )
elif command -v yum >/dev/null 2>&1; then
    PKG_MGR="yum"
    REQUIRED_PACKAGES=(
        texlive-scheme-basic
        texlive-collection-latexrecommended
        texlive-collection-fontsrecommended
        texlive-babel-french
        texlive-lm
        latexmk
    )
else
    echo "[ERREUR] Gestionnaire de paquets non supporté (apt, dnf ou yum requis)." >&2
    exit 1
fi

echo "[INFO] Vérification des paquets LaTeX requis ($PKG_MGR)..."
MISSING_PACKAGES=()

if [ "$PKG_MGR" = "apt" ]; then
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            MISSING_PACKAGES+=("$pkg")
        fi
    done
else
    for pkg in "${REQUIRED_PACKAGES[@]}"; do
        if ! rpm -q "$pkg" >/dev/null 2>&1; then
            MISSING_PACKAGES+=("$pkg")
        fi
    done
fi

if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
    echo "[INFO] Tous les paquets LaTeX requis sont déjà installés. Aucune installation nécessaire."
else
    echo "[INFO] Paquets manquants à installer : ${MISSING_PACKAGES[*]}"
    if [ "$PKG_MGR" = "apt" ]; then
        export DEBIAN_FRONTEND=noninteractive
        $SUDO apt-get update -y
        $SUDO apt-get install -y --no-install-recommends "${MISSING_PACKAGES[@]}"
    elif [ "$PKG_MGR" = "dnf" ]; then
        $SUDO dnf --enablerepo=ol9_codeready_builder --enablerepo=ol9_developer_EPEL install -y "${MISSING_PACKAGES[@]}"
    else
        $SUDO yum install -y "${MISSING_PACKAGES[@]}"
    fi
    echo "[INFO] Installation des paquets LaTeX terminée avec succès."
fi

# 3. Test de compilation d'un document LaTeX minimal avec accents français
echo "[INFO] Lancement du test de compilation LaTeX..."

TMP_DIR="$(mktemp -d -t latex_test_XXXXXX)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

TEST_TEX="$TMP_DIR/test_document.tex"
cat << 'EOF' > "$TEST_TEX"
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[french]{babel}

\title{Vérification Système LaTeX J.A.R.V.I.S.}
\author{Antigravity VPS Orchestrator}
\date{\today}

\begin{document}
\maketitle

\section{Introduction et Caractères Accentueés}
Ceci est un document de test généré automatiquement pour vérifier la chaîne de compilation \LaTeX.
Éléments testés : accents français (é, è, ê, ë, à, â, î, ï, ô, û, ù, ç, œ, æ), ligatures et polices vectorielles Modern.

\begin{itemize}
    \item Rapport d'activité L2 / L3 opérationnel.
    \item Encodage UTF-8 et césure française validés.
\end{itemize}

\end{document}
EOF

(
    cd "$TMP_DIR"
    latexmk -pdf -interaction=nonstopmode -quiet test_document.tex
)

TEST_PDF="$TMP_DIR/test_document.pdf"
if [ -f "$TEST_PDF" ] && [ -s "$TEST_PDF" ]; then
    echo "[SUCCÈS] Le test de compilation LaTeX a réussi (PDF généré : $(stat -c%s "$TEST_PDF" 2>/dev/null || wc -c < "$TEST_PDF") octets)."
else
    echo "[ERREUR] Échec du test de compilation : le fichier PDF n'a pas été généré correctement." >&2
    exit 1
fi

echo "[SUCCÈS] Environnement LaTeX VPS prêt et opérationnel pour Jarvis."
