"""J.A.R.V.I.S. - Vérification à distance de la session Gemini VPS.
Interroge le service Chrome autonome sur le serveur Oracle Cloud et affiche l'état exact.
"""

import os
import sys
import paramiko

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.environ.get("JARVIS_VPS_HOST", "158.178.206.213").strip()
USER = os.environ.get("JARVIS_VPS_USER", "opc").strip()


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


def main():
    print("=" * 70)
    print("  ✦  J . A . R . V . I . S .   C H E C K   G E M I N I   V P S  ✦")
    print("=" * 70)
    print(f"Connexion au serveur Cloud ({HOST})...")

    keys = get_candidate_keys()
    if not keys:
        print("[❌ ERREUR] Aucune clé SSH trouvée.")
        sys.exit(1)

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
        print(f"[❌ ERREUR] Impossible de se connecter en SSH au serveur {HOST}.")
        sys.exit(1)

    cmd = "cd /home/opc/jarvis-core && ./venv/bin/python scripts/check_gemini_session.py"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    client.close()

    if out.strip():
        print(out.strip())
    elif err.strip():
        print(err.strip())
    else:
        print("[!] Aucune sortie reçue du serveur.")


if __name__ == "__main__":
    main()
