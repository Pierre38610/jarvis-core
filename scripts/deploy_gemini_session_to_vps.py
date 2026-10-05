"""J.A.R.V.I.S. - Migration & Synchronisation Sécurisée de Session Gemini vers le VPS Cloud.
Permet d'exporter le profil Chrome connecté local (.jarvis_chrome_profile) vers le VPS Oracle
pour activer Deep Research L3 en toute sécurité et sans mot de passe sur le serveur.
"""

import os
import sys
import tarfile
import tempfile
import time
import paramiko

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PROFILE = os.path.join(BASE_DIR, ".jarvis_chrome_profile")
HOST = os.environ.get("JARVIS_VPS_HOST", "158.178.206.213").strip()
USER = os.environ.get("JARVIS_VPS_USER", "opc").strip()

EXCLUDE_CACHE_DIRS = {
    "Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache",
    "Service Worker/CacheStorage", "Service Worker/ScriptCache", "GrShaderCache"
}


def get_candidate_keys() -> list[str]:
    candidate_paths = [
        os.path.join(BASE_DIR, r"clés ssh\ssh-key-2026-09-25.key"),
        os.path.join(BASE_DIR, r"cles ssh\ssh-key-2026-09-25.key"),
        os.path.join(BASE_DIR, "ssh-key-2026-09-25.key"),
        os.path.expanduser(r"~/.ssh/ssh-key-2026-09-25.key"),
        os.path.expanduser(r"~/.ssh/id_rsa"),
        os.path.expanduser(r"~/.ssh/id_ed25519"),
    ]
    found = [p for p in candidate_paths if os.path.exists(p)]
    ssh_dir = os.path.expanduser("~/.ssh")
    if os.path.exists(ssh_dir):
        try:
            for f in os.listdir(ssh_dir):
                full_p = os.path.join(ssh_dir, f)
                if os.path.isfile(full_p) and full_p not in found:
                    if f.endswith((".key", ".pem", ".id_rsa")) or "oracle" in f.lower() or "vps" in f.lower():
                        found.append(full_p)
        except Exception:
            pass
    return found


def deploy_session():
    print("=" * 70)
    print("  ✦  J . A . R . V . I . S .   S Y N C   S E S S I O N   G E M I N I   V P S  ✦")
    print("=" * 70)

    if not os.path.exists(LOCAL_PROFILE):
        print(f"[!] Erreur : Le profil local '{LOCAL_PROFILE}' n'existe pas encore.")
        print("    Veuillez d'abord exécuter 'scripts/connect_gemini_web.bat' pour vous connecter à Google.")
        sys.exit(1)

    print(f"\n[1/4] Création de l'archive optimisée du profil Chrome local...")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        archive_path = tmp.name

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for root, dirs, files in os.walk(LOCAL_PROFILE):
                rel_root = os.path.relpath(root, LOCAL_PROFILE)
                # Filtrer les caches lourds
                if any(c_dir in rel_root for c_dir in EXCLUDE_CACHE_DIRS):
                    dirs.clear()
                    continue
                for f in files:
                    if f.startswith("Singleton") or f.endswith((".tmp", ".lock", ".log")):
                        continue
                    full_file = os.path.join(root, f)
                    rel_file = os.path.relpath(full_file, LOCAL_PROFILE)
                    tar.add(full_file, arcname=rel_file)

        sz_kb = os.path.getsize(archive_path) / 1024
        print(f"  [✔] Archive générée avec succès ({sz_kb:.1f} Ko).")

        keys = get_candidate_keys()
        if not keys:
            print("[!] Aucune clé SSH trouvée pour se connecter au VPS.")
            sys.exit(1)

        print(f"\n[2/4] Connexion au VPS ({HOST}) & arrêt temporaire du service Chrome...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connected = False
        for k in keys:
            try:
                client.connect(hostname=HOST, username=USER, key_filename=k, timeout=10)
                connected = True
                break
            except Exception:
                continue

        if not connected:
            print(f"[!] Échec de connexion SSH au VPS {HOST}.")
            sys.exit(1)

        # Arrêt du service
        client.exec_command("sudo systemctl stop jarvis-chrome")
        time.sleep(1)

        print("\n[3/4] Téléversement du profil et restauration des permissions sur le VPS...")
        sftp = client.open_sftp()
        remote_tar = "/tmp/gemini_profile.tar.gz"
        sftp.put(archive_path, remote_tar)
        sftp.close()

        extract_cmd = (
            "mkdir -p /home/opc/.jarvis_chrome_profile && "
            "tar -xzf /tmp/gemini_profile.tar.gz -C /home/opc/.jarvis_chrome_profile && "
            "rm -f /tmp/gemini_profile.tar.gz && "
            "rm -f /home/opc/.jarvis_chrome_profile/Singleton* && "
            "sudo chown -R opc:opc /home/opc/.jarvis_chrome_profile && "
            "sudo chmod -R 700 /home/opc/.jarvis_chrome_profile && "
            "sudo systemctl daemon-reload && "
            "sudo systemctl start jarvis-chrome && "
            "sleep 2 && sudo systemctl is-active jarvis-chrome"
        )
        stdin, stdout, stderr = client.exec_command(extract_cmd)
        status_out = stdout.read().decode('utf-8', errors='replace').strip()

        if "active" in status_out:
            print("  [✔] Profil extrait et sécurisé sur le VPS.")
            print("  [✔] Service 'jarvis-chrome' redémarré (Statut: ACTIF).")
        else:
            print(f"  [!] Statut du service : {status_out}")

        print("\n[4/4] Vérification de la session Google Gemini sur le VPS...")
        stdin, stdout, stderr = client.exec_command(
            "cd /home/opc/jarvis-core && ./venv/bin/python scripts/check_gemini_session.py"
        )
        diag_out = stdout.read().decode('utf-8', errors='replace')
        print(diag_out.strip())

        client.close()

        if "ACTIVE" in diag_out or "SUCCÈS" in diag_out:
            print("\n" + "=" * 70)
            print("  🎉 SESSION GEMINI VALIDÉE ET OPÉRATIONNELLE SUR LE VPS !")
            print("  Deep Research L3 est désormais 100% autonome sur votre Cloud.")
            print("=" * 70 + "\n")
        else:
            print("\n[ℹ] Note : Si le statut n'est pas encore ACTIVE, assurez-vous d'avoir bien complété l'authentification dans la fenêtre Chrome avant de relancer ce script.")

    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


if __name__ == "__main__":
    deploy_session()
