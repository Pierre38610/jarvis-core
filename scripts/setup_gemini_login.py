"""J.A.R.V.I.S. - Authentification Sécurisée Google Gemini.
Lance Google Chrome officiel natif avec le profil .jarvis_chrome_profile
pour permettre la connexion Google sans aucun outil d'automatisation.
"""

import os
import sys
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(ROOT_DIR, ".jarvis_chrome_profile")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"


def setup_login():
    print("=" * 65)
    print("  J.A.R.V.I.S. - AUTHENTIFICATION SÉCURISÉE GOOGLE GEMINI")
    print("=" * 65)
    print("Ce processus lance Google Chrome natif avec votre profil Jarvis :")
    print(f"  {PROFILE_DIR}")
    print()
    print("Instructions :")
    print("1. Connectez-vous normalement a votre compte Google (mot de passe + 2FA).")
    print("2. Google autorise la connexion car aucun outil d'automatisation n'est actif.")
    print("3. J.A.R.V.I.S. ne voit JAMAIS votre mot de passe.")
    print("4. Une fois arrive sur l'interface de Gemini Web, fermez simplement Chrome.")
    print("=" * 65)
    print()

    os.makedirs(PROFILE_DIR, exist_ok=True)

    if not os.path.exists(CHROME_PATH):
        print(f"[ERREUR] Chrome introuvable à l'emplacement standard : {CHROME_PATH}")
        sys.exit(1)

    cmd = [
        CHROME_PATH,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gemini.google.com/app"
    ]

    print("[Navigateur] Lancement de Google Chrome natif...")
    proc = subprocess.Popen(cmd)

    print("[En attente] Connectez-vous sur gemini.google.com, puis fermez Chrome...")
    proc.wait()

    print()
    print("[Succès] Session Google enregistrée dans :", PROFILE_DIR)
    print("JARVIS peut maintenant utiliser votre session connectée pour la réflexion !")


if __name__ == "__main__":
    setup_login()
