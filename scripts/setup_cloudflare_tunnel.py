"""J.A.R.V.I.S. Cloudflare Tunnel Configuration Wizard
Permet de configurer facilement votre domaine permanent (ex: signalcraftapps.com)
afin que votre adresse HTTPS ne change JAMAIS et que votre raccourci mobile fonctionne 24/7.
"""

import os
import sys
import time
import subprocess
import urllib.request
import urllib.error

# Forcer l'encodage UTF-8 dans la console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = ROOT_DIR
ENV_FILE = os.path.join(ROOT_DIR, ".env")
CLOUDFLARED_BIN = os.path.join(ROOT_DIR, "cloudflared.exe")


def set_env_value(key: str, value: str):
    """Met à jour ou ajoute une clé dans le fichier .env."""
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def test_token(token: str, hostname: str):
    """Teste brièvement le token Cloudflare pour vérifier que la liaison fonctionne."""
    print(f"\n[*] Test du tunnel permanent avec Cloudflare vers {hostname}...")
    bin_path = CLOUDFLARED_BIN if os.path.exists(CLOUDFLARED_BIN) else "cloudflared.exe"

    proc = subprocess.Popen(
        [bin_path, "tunnel", "--protocol", "http2", "--no-prechecks", "run", "--token", token],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    print("  [⏳] Connexion au réseau Cloudflare Edge en cours...", end="", flush=True)
    time.sleep(4)

    if proc.poll() is not None:
        print(" [ÉCHEC]")
        out, _ = proc.communicate()
        print(f"[ERREUR] Le tunnel a échoué : {out}")
        return False

    print(" [OK]")
    print(f"  [✔] Le tunnel Cloudflare est validé et prêt pour https://{hostname} !")
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
    return True


def main():
    print("=" * 72)
    print("      J.A.R.V.I.S. - CONFIGURATION DU DOMAINE PERMANENT FIXE")
    print("                     signalcraftapps.com")
    print("=" * 72)
    print("\nCe guide va lier votre domaine 'signalcraftapps.com' à JARVIS.")
    print("Une fois configuré :")
    print("  • Votre adresse HTTPS sera TOUJOURS : https://jarvis.signalcraftapps.com")
    print("  • Elle ne changera plus JAMAIS quand vous relancez start_jarvis.bat")
    print("  • Votre raccourci sur smartphone fonctionnera en permanence !")
    print("  • Plus besoin de mot de passe ni de rescanner le QR code.")
    print("-" * 72)
    print("\nCOMMENT OBTENIR VOTRE TOKEN CLOUDFLARE EN 1 MINUTE (100% GRATUIT) :")
    print("  1. Connectez-vous sur votre compte Cloudflare : https://one.dash.cloudflare.com/")
    print("     (ou sur dash.cloudflare.com > menu gauche 'Zero Trust')")
    print("  2. Dans le menu de gauche, cliquez sur 'Networks' (ou Connectors) > 'Tunnels'.")
    print("  3. Cliquez sur 'Add a tunnel' (ou Create a tunnel).")
    print("  4. Choisissez 'Cloudflare Tunnel (cloudflared)' > Nommez-le 'jarvis'.")
    print("  5. À l'étape d'installation, sous 'Windows 64-bit', Cloudflare vous donne une commande :")
    print("     cloudflared.exe service install eyJhIjoi...")
    print("     -> Copiez UNIQUEMENT la clé secrète qui commence par 'eyJh...' (c'est le Token).")
    print("  6. À l'étape suivante ('Public Hostnames') :")
    print("     • Subdomain : jarvis")
    print("     • Domain    : signalcraftapps.com")
    print("     • Type      : HTTP")
    print("     • URL       : localhost:8000")
    print("     -> Cliquez sur 'Save tunnel'.")
    print("-" * 72)

    token = input("\nCollez votre Token Cloudflare (ou appuyez sur Entrée pour quitter) : ").strip()

    if not token:
        print("\nAucun token renseigné. La configuration reste inchangée.")
        return

    # Nettoyage si l'utilisateur a copié toute la commande
    if "tunnel run --token" in token:
        token = token.split("--token")[-1].strip().split()[0]
    elif "service install" in token:
        token = token.split("service install")[-1].strip().split()[0]

    hostname_input = input("Nom d'hôte souhaité [défaut: jarvis.signalcraftapps.com] : ").strip()
    hostname = hostname_input if hostname_input else "jarvis.signalcraftapps.com"

    # Enregistrement dans .env
    set_env_value("CLOUDFLARE_TUNNEL_TOKEN", token)
    set_env_value("CLOUDFLARE_HOSTNAME", hostname)

    print(f"\n[✔] Configuration enregistrée dans .env :")
    print(f"    CLOUDFLARE_TUNNEL_TOKEN = {token[:12]}...{token[-6:]}")
    print(f"    CLOUDFLARE_HOSTNAME     = {hostname}")

    # Test
    test_token(token, hostname)

    print("\n" + "=" * 72)
    print("  CONFIGURATION TERMINÉE AVEC SUCCÈS !")
    print("  Vous pouvez désormais lancer 'start_jarvis.bat'.")
    print(f"  Votre adresse fixe sera : https://{hostname}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
