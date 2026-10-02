"""Script d'installation des règles AGENTS.md sur le VPS et dans l'environnement local.
Copie AGENTS.md dans ~/.gemini/config/rules/AGENTS.md et dans le dossier de travail.
"""

import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_MD_SRC = os.path.join(BASE_DIR, "AGENTS.md")

DESTINATIONS = [
    os.path.normpath(os.path.expanduser("~/.gemini/config/rules/AGENTS.md")),
    os.path.normpath(os.path.expanduser("~/.gemini/antigravity-cli/rules/AGENTS.md")),
    os.path.normpath(os.path.join(BASE_DIR, ".agents", "rules", "AGENTS.md")),
    os.path.normpath(os.path.join(BASE_DIR, "my-project", "AGENTS.md"))
]


def install_agent_rules():
    if not os.path.exists(AGENTS_MD_SRC):
        print(f"[Install Rules] Erreur : Fichier source '{AGENTS_MD_SRC}' introuvable.")
        sys.exit(1)

    print(f"[Install Rules] Source : {AGENTS_MD_SRC}")
    for dest in DESTINATIONS:
        try:
            dest_dir = os.path.dirname(dest)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(AGENTS_MD_SRC, dest)
            print(f"[Install Rules] Installé -> {dest}")
        except Exception as e:
            print(f"[Install Rules] Avertissement pour {dest} : {e}")


if __name__ == "__main__":
    install_agent_rules()
