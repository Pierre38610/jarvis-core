#!/usr/bin/env bash
# ==============================================================================
# J.A.R.V.I.S. - Stark Industries
# Script d'Installation & Configuration : Google Chrome Headless + CDP VPS
# Objectif : Maintenir un Google Chrome persistant pilotable en CDP (port 9222)
# ==============================================================================

set -euo pipefail

# Couleurs et formatage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[✔]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

echo -e "${CYAN}======================================================================${NC}"
echo -e "${CYAN}       ✦  J . A . R . V . I . S .   V P S   C H R O M E   C D P  ✦      ${NC}"
echo -e "${CYAN}======================================================================${NC}"

# ─── 1. VÉRIFICATION DES PRIVILÈGES ET DE L'UTILISATEUR ───────────────────────
TARGET_USER="${SUDO_USER:-$USER}"
if [ "$TARGET_USER" = "root" ] && [ -n "${SUDO_USER:-}" ]; then
    TARGET_USER="$SUDO_USER"
fi
TARGET_HOME=$(eval echo "~${TARGET_USER}")

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    else
        error "Ce script nécessite des privilèges d'administration (root ou sudo) pour installer les paquets système et le service systemd."
        exit 1
    fi
fi

info "Utilisateur cible pour le service : ${TARGET_USER} (Home: ${TARGET_HOME})"

# ─── 2. CHARGEMENT DE LA CONFIGURATION ET DES VARIABLES ───────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env"

if [ -f "$ENV_FILE" ]; then
    info "Chargement des variables depuis ${ENV_FILE}"
    # Extraction sécurisée des variables pertinentes
    eval "$(grep -E '^(JARVIS_VPS_CHROME_PROFILE|JARVIS_CDP_PORT|JARVIS_CDP_HOST|JARVIS_CHROME_BIN)=' "$ENV_FILE" || true)"
fi

PROFILE_DIR="${JARVIS_VPS_CHROME_PROFILE:-${TARGET_HOME}/.jarvis_chrome_profile}"
CDP_PORT="${JARVIS_CDP_PORT:-9222}"
CDP_HOST="${JARVIS_CDP_HOST:-127.0.0.1}"
SERVICE_NAME="jarvis-chrome.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

info "Profil Chrome persistant : ${PROFILE_DIR}"
info "Port CDP configuré       : ${CDP_HOST}:${CDP_PORT}"

# ─── 3. DÉTECTION DU SYSTÈME D'EXPLOITATION & PAQUETS ─────────────────────────
info "Détection de l'OS et du gestionnaire de paquets..."
ARCH="$(uname -m)"
info "Architecture détectée : ${ARCH}"

if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="apt"
    info "Gestionnaire de paquets détecté : apt (Debian/Ubuntu)"
    
    info "Mise à jour de l'index des paquets..."
    $SUDO_CMD apt-get update -qq || warn "Échec partiel apt-get update, tentative d'installation des paquets..."

    # Dépendances système pour Chrome / Chromium / Xvfb / Playwright
    APT_PKGS=(
        xvfb
        ca-certificates
        curl
        wget
        fonts-liberation
        libasound2
        libatk-bridge2.0-0
        libatk1.0-0
        libcairo2
        libcups2
        libdbus-1-3
        libdrm2
        libgbm1
        libglib2.0-0
        libnspr4
        libnss3
        libpango-1.0-0
        libx11-6
        libxcomposite1
        libxdamage1
        libxext6
        libxfixes3
        libxrandr2
        libxkbcommon0
        libxshmfence1
    )

    info "Installation des dépendances système Chromium / Xvfb..."
    $SUDO_CMD apt-get install -y -qq "${APT_PKGS[@]}" || {
        # Repli pour Ubuntu 24.04+ (libasound2t64)
        warn "Tentative de repli pour les bibliothèques audio récentes..."
        $SUDO_CMD apt-get install -y -qq xvfb ca-certificates curl wget fonts-liberation libnss3 libgbm1 libatk1.0-0 libcups2 || true
    }

    # Installation de Chromium si disponible
    if ! command -v chromium-browser >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1; then
        info "Installation de Chromium via apt..."
        $SUDO_CMD apt-get install -y -qq chromium-browser || $SUDO_CMD apt-get install -y -qq chromium || true
    fi

elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
    PKG_MGR="dnf"
    YUM_CMD="dnf"
    if ! command -v dnf >/dev/null 2>&1; then
        YUM_CMD="yum"
    fi
    info "Gestionnaire de paquets détecté : ${YUM_CMD} (Oracle Linux / RHEL / CentOS / Fedora)"

    RPM_PKGS=(
        xorg-x11-server-Xvfb
        alsa-lib
        atk
        cups-libs
        gtk3
        libXcomposite
        libXcursor
        libXdamage
        libXext
        libXi
        libXrandr
        libXScrnSaver
        libXtst
        pango
        nss
        libdrm
        mesa-libgbm
        libxkbcommon
        curl
        ca-certificates
    )

    info "Installation des dépendances système Chromium / Xvfb via ${YUM_CMD}..."
    $SUDO_CMD $YUM_CMD install -y -q "${RPM_PKGS[@]}" || true

    if ! command -v chromium >/dev/null 2>&1 && ! command -v google-chrome >/dev/null 2>&1; then
        info "Tentative d'installation de Chromium..."
        $SUDO_CMD $YUM_CMD install -y -q chromium || true
    fi
else
    warn "Gestionnaire de paquets non standard. Assurez-vous que Xvfb, Chromium et les bibliothèques partagées sont installés."
fi

success "Dépendances système vérifiées."

# ─── 4. INSTALLATION PLAYWRIGHT CHROMIUM ───────────────────────────────────────
info "Vérification / installation du moteur Playwright Chromium..."

VENV_PYTHON="${REPO_DIR}/venv/bin/python"
VENV_PLAYWRIGHT="${REPO_DIR}/venv/bin/playwright"

if [ -x "$VENV_PYTHON" ]; then
    info "Environnement virtuel détecté dans ${REPO_DIR}/venv"
    # Installation du navigateur Playwright
    if [ -x "$VENV_PLAYWRIGHT" ]; then
        info "Exécution de 'playwright install chromium'..."
        $VENV_PLAYWRIGHT install chromium || warn "Avertissement lors de playwright install chromium"
        $VENV_PLAYWRIGHT install-deps chromium 2>/dev/null || true
    else
        info "Installation du CLI Playwright dans le venv..."
        "$VENV_PYTHON" -m pip install -q playwright || true
        "$VENV_PYTHON" -m playwright install chromium || warn "Avertissement installation playwright chromium"
    fi
elif command -v playwright >/dev/null 2>&1; then
    playwright install chromium || true
    playwright install-deps chromium 2>/dev/null || true
fi

# ─── 5. DÉTECTION DU BINAIRE CHROME / CHROMIUM ─────────────────────────────────
info "Recherche du binaire exécutable Chrome / Chromium..."

CHROME_BIN=""
CANDIDATE_BINS=(
    "${JARVIS_CHROME_BIN:-}"
    "/usr/bin/google-chrome-stable"
    "/usr/bin/google-chrome"
    "/usr/bin/chromium-browser"
    "/usr/bin/chromium"
    "/snap/bin/chromium"
    "${TARGET_HOME}/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
    "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
)

for cand in "${CANDIDATE_BINS[@]}"; do
    if [ -n "$cand" ]; then
        # Gestion des wildcards éventuels
        for resolved in $cand; do
            if [ -x "$resolved" ]; then
                CHROME_BIN="$resolved"
                break 2
            fi
        done
    fi
done

if [ -z "$CHROME_BIN" ]; then
    # Essai via command -v
    if command -v chromium-browser >/dev/null 2>&1; then
        CHROME_BIN="$(command -v chromium-browser)"
    elif command -v chromium >/dev/null 2>&1; then
        CHROME_BIN="$(command -v chromium)"
    elif command -v google-chrome >/dev/null 2>&1; then
        CHROME_BIN="$(command -v google-chrome)"
    fi
fi

if [ -z "$CHROME_BIN" ]; then
    error "Aucun binaire Chrome ou Chromium exécutable n'a été trouvé."
    error "Veuillez installer Chromium ou spécifier JARVIS_CHROME_BIN dans votre fichier .env."
    exit 1
fi

success "Binaire Chrome sélectionné : ${CHROME_BIN}"

# ─── 6. CRÉATION DU DOSSIER DE PROFIL PERSISTANT ──────────────────────────────
info "Configuration du répertoire de profil utilisateur persistant..."
$SUDO_CMD mkdir -p "${PROFILE_DIR}"
$SUDO_CMD chown -R "${TARGET_USER}:${TARGET_USER}" "${PROFILE_DIR}"
$SUDO_CMD chmod 700 "${PROFILE_DIR}"
success "Profil persistant prêt dans ${PROFILE_DIR}"

# ─── 7. CRÉATION / MISE À JOUR DE L'UNITÉ SYSTEMD ─────────────────────────────
info "Génération de l'unité systemd : ${SERVICE_PATH}..."

TMP_SERVICE=$(mktemp)
cat <<EOF > "$TMP_SERVICE"
[Unit]
Description=J.A.R.V.I.S. Headless Chrome CDP Service (Port ${CDP_PORT})
Documentation=https://github.com/Pierre38610/jarvis-core
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
Group=${TARGET_USER}
Environment=DISPLAY=:99
EnvironmentFile=-${REPO_DIR}/.env
ExecStartPre=/bin/mkdir -p ${PROFILE_DIR}
ExecStart=${CHROME_BIN} \\
    --headless=new \\
    --remote-debugging-port=${CDP_PORT} \\
    --remote-debugging-address=${CDP_HOST} \\
    --user-data-dir=${PROFILE_DIR} \\
    --no-first-run \\
    --no-default-browser-check \\
    --disable-blink-features=AutomationControlled \\
    --disable-gpu \\
    --no-sandbox \\
    --disable-dev-shm-usage \\
    --disable-background-networking \\
    --disable-background-timer-throttling \\
    --disable-breakpad \\
    --disable-features=Translate,OptimizationHints,MediaRouter \\
    --window-size=1280,800
Restart=always
RestartSec=5s
KillMode=process
TimeoutStopSec=10s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jarvis-chrome

[Install]
WantedBy=multi-user.target
EOF

$SUDO_CMD cp "$TMP_SERVICE" "$SERVICE_PATH"
$SUDO_CMD chmod 644 "$SERVICE_PATH"
rm -f "$TMP_SERVICE"

success "Unité systemd installée dans ${SERVICE_PATH}"

# ─── 8. ACTIVATION ET DÉMARRAGE DU SERVICE ────────────────────────────────────
info "Rechargement de systemd et démarrage du service ${SERVICE_NAME}..."
$SUDO_CMD systemctl daemon-reload
$SUDO_CMD systemctl enable "${SERVICE_NAME}"
$SUDO_CMD systemctl restart "${SERVICE_NAME}"

# ─── 9. VÉRIFICATION DU STATUT ET HEALTH CHECK CDP ────────────────────────────
info "Attente de la disponibilité de Chrome CDP sur http://${CDP_HOST}:${CDP_PORT}/json/version..."

MAX_TRIES=10
READY=false

for i in $(seq 1 $MAX_TRIES); do
    sleep 1
    if curl -s --max-time 2 "http://${CDP_HOST}:${CDP_PORT}/json/version" >/dev/null 2>&1; then
        READY=true
        break
    fi
done

if [ "$READY" = true ]; then
    success "Chrome CDP est opérationnel et répond sur le port ${CDP_PORT} !"
    CDP_VERSION=$(curl -s "http://${CDP_HOST}:${CDP_PORT}/json/version")
    echo -e "${CYAN}${CDP_VERSION}${NC}"
else
    warn "Chrome CDP n'a pas répondu immédiatement sur le port ${CDP_PORT}."
    warn "Statut du service systemd :"
    $SUDO_CMD systemctl status "${SERVICE_NAME}" --no-pager || true
    warn "Derniers logs du service :"
    $SUDO_CMD journalctl -u "${SERVICE_NAME}" -n 15 --no-pager || true
fi

echo -e "\n${CYAN}======================================================================${NC}"
echo -e "${GREEN}  🎉 CONFIGURATION CHROME VPS CDP TERMINÉE AVEC SUCCÈS !${NC}"
echo -e "  - Service systemd : sudo systemctl status ${SERVICE_NAME}"
echo -e "  - Logs en direct  : journalctl -u ${SERVICE_NAME} -f"
echo -e "  - Endpoint CDP    : http://${CDP_HOST}:${CDP_PORT}/json/version"
echo -e "  - Profil persistant: ${PROFILE_DIR}"
echo -e "${CYAN}======================================================================${NC}\n"
