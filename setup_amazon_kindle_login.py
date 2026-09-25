"""J.A.R.V.I.S. - Configuration et Connexion Amazon Send to Kindle.
Permet d'ouvrir Chrome natif avec le profil .jarvis_chrome_profile pour s'identifier sur Amazon.
"""

import os
import sys
import subprocess
import asyncio
from config import CHROME_PATH, PROFILE_DIR
from services.browser_service import check_kindle_web_status

def open_amazon_login():
    print("=" * 65)
    print("  J.A.R.V.I.S. - AUTHENTIFICATION AMAZON SEND TO KINDLE")
    print("=" * 65)
    print(f"Profil persistant utilisé : {PROFILE_DIR}")
    print("URL cible : https://www.amazon.fr/sendtokindle")
    print()

    if not os.path.exists(CHROME_PATH):
        print(f"[ERREUR] Chrome introuvable à : {CHROME_PATH}")
        sys.exit(1)

    cmd = [
        CHROME_PATH,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.amazon.fr/sendtokindle"
    ]

    print("[Navigateur] Lancement de Google Chrome natif...")
    proc = subprocess.Popen(cmd)
    print("[En attente] Connectez-vous à votre compte Amazon, puis fermez Chrome...")
    proc.wait()

    print()
    print("[Vérification] Analyse de l'état de connexion de la session...")
    status = asyncio.run(check_kindle_web_status())
    if status.get("logged_in"):
        print(f"[Succès] Session Amazon active pour : {status.get('user_name', 'Pierre')} !")
        print("J.A.R.V.I.S. peut désormais envoyer vos documents et livres directement sur votre Kindle !")
    else:
        print("[Information] La session n'est pas encore connectée. Vous pourrez relancer ce script à tout moment.")

if __name__ == "__main__":
    open_amazon_login()
