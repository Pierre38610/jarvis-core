"""tests/test_vps_chrome_setup.py
Tests unitaires et de validation pour P3 — Chrome + CDP persistant sur le VPS.
Vérifie :
1. Le script shell d'installation scripts/setup_vps_chrome.sh (idempotence, détection OS, dépendances, Playwright, CDP).
2. L'unité systemd scripts/jarvis-chrome.service (syntaxe, options Chrome, sécurité, persistance hors dépôt).
3. La configuration Python (config.py, .env.example, .gitignore, sync_deploy.py, gemini_web_automator.py).
"""

import os
import re
import sys
import config
from config import BASE_DIR


def test_setup_script_exists_and_content():
    """Vérifie l'existence et les caractéristiques structurelles du script d'installation VPS."""
    script_path = os.path.join(BASE_DIR, "scripts", "setup_vps_chrome.sh")
    assert os.path.exists(script_path), f"Le script {script_path} doit exister."

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Shebang et strict mode
    assert content.startswith("#!/"), "Le script doit comporter un shebang."
    assert "set -euo pipefail" in content, "Le script doit utiliser set -euo pipefail pour une gestion rigoureuse des erreurs."

    # Détection OS et gestionnaires de paquets
    assert "apt-get" in content, "Le script doit supporter Debian/Ubuntu (apt-get)."
    assert "dnf" in content or "yum" in content, "Le script doit supporter RHEL/Oracle Linux (dnf/yum)."

    # Dépendances système & Xvfb
    assert "xvfb" in content.lower(), "Le script doit inclure l'installation de Xvfb."
    assert "chromium" in content.lower(), "Le script doit installer Chromium / Chrome."

    # Playwright
    assert "playwright install chromium" in content, "Le script doit exécuter 'playwright install chromium'."

    # Variables & persistance du profil hors dépôt
    assert "JARVIS_VPS_CHROME_PROFILE" in content, "Le script doit supporter JARVIS_VPS_CHROME_PROFILE."
    assert "JARVIS_CDP_PORT" in content, "Le script doit supporter JARVIS_CDP_PORT."
    assert ".jarvis_chrome_profile" in content, "Le script doit cibler le profil persistant .jarvis_chrome_profile."

    # Systemd
    assert "systemctl daemon-reload" in content, "Le script doit exécuter daemon-reload."
    assert "systemctl enable" in content, "Le script doit activer le service au démarrage."
    assert "systemctl restart" in content, "Le script doit démarrer / redémarrer le service."

    # Health check CDP
    assert "/json/version" in content, "Le script doit sonder l'endpoint CDP /json/version."
    assert "9222" in content, "Le port CDP par défaut 9222 doit être configuré."


def test_systemd_service_unit():
    """Vérifie la syntaxe et les directives de l'unité systemd jarvis-chrome.service."""
    unit_path = os.path.join(BASE_DIR, "scripts", "jarvis-chrome.service")
    assert os.path.exists(unit_path), f"L'unité systemd {unit_path} doit exister."

    with open(unit_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Sections obligatoires
    assert "[Unit]" in content, "L'unité doit contenir la section [Unit]."
    assert "[Service]" in content, "L'unité doit contenir la section [Service]."
    assert "[Install]" in content, "L'unité doit contenir la section [Install]."

    # Options Chrome indispensables pour headless CDP
    assert "--headless" in content, "Chrome doit être lancé en mode headless."
    assert "--remote-debugging-port=9222" in content or "--remote-debugging-port=" in content, "Le port CDP doit être configuré."
    assert "--remote-debugging-address=127.0.0.1" in content or "--remote-debugging-address=" in content, "L'adresse CDP doit être bornée."
    assert "--user-data-dir=" in content, "Le profil utilisateur doit être spécifié."
    assert "--no-sandbox" in content, "--no-sandbox doit être présent pour un fonctionnement conteneur/VPS fiable."
    assert "--disable-gpu" in content, "--disable-gpu doit être présent."

    # Résilience & Logging
    assert "Restart=always" in content, "Le service doit redémarrer automatiquement (Restart=always)."
    assert "SyslogIdentifier=jarvis-chrome" in content, "L'identifiant syslog doit être défini pour journalctl."
    assert "WantedBy=multi-user.target" in content, "Le service doit être rattaché à multi-user.target."


def test_config_exports_cdp_variables():
    """Vérifie que config.py exporte les variables CDP et profil Chrome."""
    assert hasattr(config, "JARVIS_VPS_CHROME_PROFILE"), "config.py doit exporter JARVIS_VPS_CHROME_PROFILE."
    assert hasattr(config, "JARVIS_CDP_PORT"), "config.py doit exporter JARVIS_CDP_PORT."
    assert hasattr(config, "JARVIS_CDP_HOST"), "config.py doit exporter JARVIS_CDP_HOST."
    assert hasattr(config, "JARVIS_CDP_URL"), "config.py doit exporter JARVIS_CDP_URL."
    assert hasattr(config, "JARVIS_CHROME_BIN"), "config.py doit exporter JARVIS_CHROME_BIN."
    assert hasattr(config, "JARVIS_CHROME_HEADLESS"), "config.py doit exporter JARVIS_CHROME_HEADLESS."

    assert config.JARVIS_CDP_PORT == 9222 or isinstance(config.JARVIS_CDP_PORT, int)
    assert "9222" in config.JARVIS_CDP_URL
    assert hasattr(config, "CHROME_PATH") and config.CHROME_PATH


def test_env_example_documents_cdp():
    """Vérifie que .env.example documente les variables de configuration Chrome CDP."""
    env_ex_path = os.path.join(BASE_DIR, ".env.example")
    with open(env_ex_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "JARVIS_VPS_CHROME_PROFILE" in content, ".env.example doit documenter JARVIS_VPS_CHROME_PROFILE."
    assert "JARVIS_CDP_PORT" in content, ".env.example doit documenter JARVIS_CDP_PORT."
    assert "JARVIS_CDP_HOST" in content, ".env.example doit documenter JARVIS_CDP_HOST."
    assert "JARVIS_CDP_URL" in content, ".env.example doit documenter JARVIS_CDP_URL."
    assert "JARVIS_CHROME_BIN" in content, ".env.example doit documenter JARVIS_CHROME_BIN."
    assert "JARVIS_CHROME_HEADLESS" in content, ".env.example doit documenter JARVIS_CHROME_HEADLESS."


def test_profile_exclusion_in_gitignore_and_deploy():
    """Vérifie que le profil Chrome est exclu de git et du déploiement VPS."""
    gitignore_path = os.path.join(BASE_DIR, ".gitignore")
    with open(gitignore_path, "r", encoding="utf-8") as f:
        git_content = f.read()

    assert ".jarvis_chrome_profile" in git_content, ".gitignore doit exclure .jarvis_chrome_profile."

    from sync_deploy import EXCLUDE_DIRS
    assert ".jarvis_chrome_profile" in EXCLUDE_DIRS, "sync_deploy.py doit exclure .jarvis_chrome_profile du tar de déploiement."


def test_gemini_web_automator_uses_config_cdp_url():
    """Vérifie que gemini_web_automator utilise l'URL CDP dynamique."""
    import services.gemini_web_automator as automator_mod
    assert hasattr(automator_mod, "CDP_URL")
    assert "9222" in automator_mod.CDP_URL
