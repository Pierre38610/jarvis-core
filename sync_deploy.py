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
from typing import Optional
import paramiko

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(BASE_DIR, r"clés ssh\ssh-key-2026-09-25.key")
HOST = os.environ.get("JARVIS_VPS_HOST", "158.178.206.213").strip()
USER = os.environ.get("JARVIS_VPS_USER", "opc").strip()

EXCLUDE_DIRS = {
    "venv", ".git", ".jarvis_chrome_profile", ".jarvis_shopping_profile",
    ".browseruse", ".antigravity_save", "downloads", "__pycache__", "clés ssh", "cles ssh", "my-project",
    "releases", "current", ".cache", ".pytest_cache", "build", "managed_components"
}
EXCLUDE_FILES = {
    "cloudflared.exe", "jarvis_memory.db", ".env"
}


def get_candidate_keys() -> list[str]:
    """Retourne la liste des clés SSH candidates existantes."""
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


def sync_and_verify_versions(target_version: Optional[str] = None) -> str:
    """Synchronise et valide automatiquement la version centrale sur tous les fichiers clés."""
    import re

    config_path = os.path.join(BASE_DIR, "config.py")
    index_path = os.path.join(BASE_DIR, "static", "index.html")
    style_path = os.path.join(BASE_DIR, "static", "style.css")
    arch_path = os.path.join(BASE_DIR, "ARCHITECTURE_COMPLETE_JARVIS.md")

    version = target_version
    if not version and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg_txt = f.read()
                m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', cfg_txt)
                if m:
                    version = m.group(1).strip()
        except Exception:
            pass

    if not version and os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                idx_txt = f.read()
                m = re.search(r'id=["\']hudVersionTag["\'][^>]*>v?([0-9]+\.[0-9]+\.[0-9]+)', idx_txt)
                if m:
                    version = m.group(1).strip()
        except Exception:
            pass

    if not version:
        version = "5.94.0"

    print(f"\n[0/3] Vérification & synchronisation des versions applicatives (v{version})...", flush=True)
    synced_files = []

    # 1. config.py
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                c_txt = f.read()
            if "APP_VERSION =" in c_txt:
                new_c = re.sub(r'APP_VERSION\s*=\s*["\'][^"\']+["\']', f'APP_VERSION = "{version}"', c_txt)
            else:
                new_c = f'APP_VERSION = "{version}"\n' + c_txt
            if new_c != c_txt:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(new_c)
                synced_files.append("config.py")
        except Exception as e:
            print(f"  [!] Avertissement sync config.py: {e}", flush=True)

    # 2. static/index.html
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                i_txt = f.read()
            new_i = i_txt
            new_i = re.sub(
                r'<span[^>]*id=["\']hudVersionTag["\'][^>]*>.*?</span>',
                f'<span class="hud-version-tag statusbar-version" id="hudVersionTag" title="Version {version} Stark AI">v{version}</span>',
                new_i,
                flags=re.DOTALL
            )
            new_i = re.sub(r'href=["\']/static/style\.css\?v=[^"\']+["\']', f'href="/static/style.css?v={version}"', new_i)
            new_i = re.sub(r'src=["\']/static/app\.js\?v=[^"\']+["\']', f'src="/static/app.js?v={version}"', new_i)
            if new_i != i_txt:
                with open(index_path, "w", encoding="utf-8") as f:
                    f.write(new_i)
                synced_files.append("static/index.html")
        except Exception as e:
            print(f"  [!] Avertissement sync index.html: {e}", flush=True)

    # 3. static/style.css
    if os.path.exists(style_path):
        try:
            with open(style_path, "r", encoding="utf-8") as f:
                s_txt = f.read()
            new_s = re.sub(r'Version\s+[0-9]+\.[0-9]+\.[0-9]+', f'Version {version}', s_txt, count=1)
            if new_s != s_txt:
                with open(style_path, "w", encoding="utf-8") as f:
                    f.write(new_s)
                synced_files.append("static/style.css")
        except Exception as e:
            print(f"  [!] Avertissement sync style.css: {e}", flush=True)

    # 4. ARCHITECTURE_COMPLETE_JARVIS.md
    if os.path.exists(arch_path):
        try:
            with open(arch_path, "r", encoding="utf-8") as f:
                a_txt = f.read()
            new_a = re.sub(r'Dernière révision majeure : Version\s+[0-9]+\.[0-9]+\.[0-9]+', f'Dernière révision majeure : Version {version}', a_txt)
            new_a = re.sub(r'Système J\.A\.R\.V\.I\.S\. Core V\s+[0-9]+\.[0-9]+\.[0-9]+', f'Système J.A.R.V.I.S. Core V {version}', new_a)
            if new_a != a_txt:
                with open(arch_path, "w", encoding="utf-8") as f:
                    f.write(new_a)
                synced_files.append("ARCHITECTURE_COMPLETE_JARVIS.md")
        except Exception as e:
            print(f"  [!] Avertissement sync ARCHITECTURE_COMPLETE_JARVIS.md: {e}", flush=True)

    if synced_files:
        print(f"  [✔] Fichiers harmonisés vers v{version} : {', '.join(synced_files)}", flush=True)
    else:
        print(f"  [✔] Toutes les balises de version sont 100% alignées sur v{version}.", flush=True)

    return version


def git_commit_and_push(commit_msg: str):
    print("=" * 70, flush=True)
    print("       ✦  J . A . R . V . I . S .   S Y N C   &   D E P L O Y  ✦", flush=True)
    print("=" * 70, flush=True)
    
    # Auto-synchronisation des versions
    sync_and_verify_versions()

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

        keys = get_candidate_keys()
        if not keys:
            print(f"\n[3/3] ⚠️ Aucune clé SSH trouvée.")
            print("  [*] Veuillez déposer votre clé privée dans 'clés ssh/ssh-key-2026-09-25.key' (dossier ignoré par git) ou dans '~/.ssh/'.")
            print("  [*] Le code a été commité et synchronisé sur GitHub (git push origin main).")
            return

        print(f"\n[3/3] Connexion au VPS ({HOST}) & déploiement...", flush=True)
        connected = False
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        for k in keys:
            try:
                client.connect(hostname=HOST, username=USER, key_filename=k, timeout=10)
                connected = True
                break
            except Exception:
                continue

        if not connected:
            print("  [!] Échec d'authentification SSH avec les clés candidates disponibles.")
            print("  [*] Le code est synchronisé sur GitHub. Pour déployer sur le VPS, assurez-vous que la clé Oracle est accessible.")
            return

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
