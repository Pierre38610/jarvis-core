"""J.A.R.V.I.S. Sync & Cloud Deploy - Stark Industries
Script automatisé de synchronisation double :
1. Git commit + git push origin main (dépôt GitHub).
2. Déploiement direct en 3 secondes vers le VPS Oracle Cloud (SFTP + tar).
3. Redémarrage transparent du service systemd 'jarvis' sur le cloud.
"""

import os
import sys
import argparse
import subprocess
import tarfile
import tempfile
import time
import paramiko

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(BASE_DIR, r"clés ssh\ssh-key-2026-09-25.key")
HOST = "158.178.206.213"
USER = "opc"

EXCLUDE_DIRS = {
    "venv", ".git", ".jarvis_chrome_profile", ".jarvis_shopping_profile",
    ".browseruse", ".antigravity_save", "downloads", "__pycache__", "clés ssh", "my-project",
    "releases", "current"
}
EXCLUDE_FILES = {
    "cloudflared.exe", "jarvis_memory.db", ".env"
}


def git_commit_and_push(commit_msg: str):
    print("=" * 70, flush=True)
    print("       ✦  J . A . R . V . I . S .   S Y N C   &   D E P L O Y  ✦", flush=True)
    print("=" * 70, flush=True)
    print(f"\n[1/3] Synchronisation Git GitHub...", flush=True)

    # Git add
    res = subprocess.run(["git", "add", "."], cwd=BASE_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Avertissement git add: {res.stderr.strip()}", flush=True)

    # Git commit
    status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True)
    if status.stdout.strip():
        msg = commit_msg or f"Update Jarvis Core - {time.strftime('%Y-%m-%d %H:%M:%S')}"
        res = subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, capture_output=True, text=True)
        print(f"  [✔] Commit créé : {msg}", flush=True)
    else:
        print("  [*] Aucun nouveau changement à commiter localement.", flush=True)

    # Git push
    print("  [*] Envoi vers GitHub (git push origin main)...", flush=True)
    res = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
    if res.returncode == 0:
        print("  [✔] Dépôt GitHub synchronisé avec succès.", flush=True)
    else:
        print(f"  [!] Note push: {res.stderr.strip() or res.stdout.strip()}", flush=True)


def deploy_to_vps():
    print(f"\n[2/3] Préparation de l'archive de mise à jour pour le VPS...", flush=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        archive_path = tmp.name

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for root, dirs, files in os.walk(BASE_DIR):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".antigravity")]
                for f in files:
                    if f in EXCLUDE_FILES or f.endswith((".pyc", ".log", ".tmp")):
                        continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, BASE_DIR)
                    tar.add(full, arcname=rel)

        sz_kb = os.path.getsize(archive_path) / 1024
        print(f"  [✔] Archive générée : {sz_kb:.1f} Ko", flush=True)

        print(f"\n[3/3] Connexion au VPS ({HOST}) & déploiement...", flush=True)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=HOST, username=USER, key_filename=KEY_PATH, timeout=15)

        # Upload
        sftp = client.open_sftp()
        remote_tmp = "/tmp/jarvis_update.tar.gz"
        sftp.put(archive_path, remote_tmp)
        sftp.close()

        # Extraction & Redémarrage
        cmd = (
            "tar -xzf /tmp/jarvis_update.tar.gz -C /home/opc/jarvis-core && "
            "rm -f /tmp/jarvis_update.tar.gz && "
            "sudo systemctl restart jarvis && "
            "sleep 1 && sudo systemctl is-active jarvis"
        )
        stdin, stdout, stderr = client.exec_command(cmd)
        status_out = stdout.read().decode('utf-8', errors='replace').strip()
        client.close()

        if "active" in status_out:
            print("  [✔] Code extrait sur le VPS.")
            print("  [✔] Service 'jarvis' redémarré avec succès (Statut: ACTIF).")
            print("\n" + "=" * 70)
            print("  🎉 DÉPLOIEMENT TERMINÉ : Votre Jarvis Cloud est 100% à jour !")
            print("=" * 70 + "\n")
        else:
            print(f"  [!] Attention, statut service : {status_out}")

    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)


def main():
    parser = argparse.ArgumentParser(description="Synchronisation Git & Déploiement automatique Jarvis VPS")
    parser.add_argument("-m", "--message", type=str, default="", help="Message de commit Git")
    args = parser.parse_args()

    git_commit_and_push(args.message)
    deploy_to_vps()


if __name__ == "__main__":
    main()
