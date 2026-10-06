"""J.A.R.V.I.S. - Connexion Sécurisée Google Gemini sur VPS via Interface Web noVNC.
Permet d'ouvrir Chromium directement sur le VPS dans votre navigateur local pour vous authentifier
avec votre compte Google (mot de passe + 2FA), sans aucun logiciel supplémentaire requis.
"""

import os
import sys
import time
import webbrowser
import threading
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


def start_vps_gui_session():
    print("=" * 72)
    print("  ✦  J . A . R . V . I . S .   C O N N E X I O N   G E M I N I   V P S  ✦")
    print("=" * 72)
    print("Ce script démarre une session graphique Chromium sécurisée directement sur")
    print("le VPS Cloud et ouvre l'interface dans votre navigateur web local.\n")

    keys = get_candidate_keys()
    if not keys:
        print("[!] Erreur : Aucune clé SSH trouvée.")
        sys.exit(1)

    print(f"[1/4] Connexion SSH au serveur VPS ({HOST})...")
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
        print(f"[!] Échec de connexion SSH au serveur {HOST}.")
        sys.exit(1)

    print("[2/4] Préparation de l'affichage distant Xvfb et noVNC sur le VPS...")
    # Nettoyage des processus antérieurs
    cleanup_cmd = (
        "sudo systemctl stop jarvis-chrome && "
        "pkill -f x11vnc || true && "
        "pkill -f websockify || true && "
        "pkill -f 'Xvfb :99' || true && "
        "rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 || true"
    )
    client.exec_command(cleanup_cmd)
    time.sleep(1)

    # Démarrage de Xvfb, x11vnc et noVNC / websockify sur le VPS
    start_cmd = (
        "Xvfb :99 -screen 0 1280x800x24 & "
        "sleep 1 && "
        "x11vnc -display :99 -nopw -listen 127.0.0.1 -forever -shared & "
        "sleep 1 && "
        "websockify --web /usr/share/novnc 6080 127.0.0.1:5900 & "
        "sleep 1 && "
        "DISPLAY=:99 /usr/bin/chromium-browser "
        "--user-data-dir=/home/opc/.jarvis_chrome_profile "
        "--no-first-run --no-default-browser-check "
        "--disable-dev-shm-usage --no-sandbox "
        "--window-size=1280,800 "
        "https://gemini.google.com/app &"
    )
    client.exec_command(start_cmd)
    time.sleep(3)

    print("[3/4] Ouverture du tunnel local vers le navigateur...")
    # Création du tunnel SSH direct pour le port 6080
    transport = client.get_transport()
    import socket
    local_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    local_server.bind(('127.0.0.1', 6080))
    local_server.listen(5)

    running = True

    def forward_tunnel():
        while running:
            try:
                local_conn, addr = local_server.accept()
                chan = transport.open_channel("direct-tcpip", ("127.0.0.1", 6080), addr)
                if chan is None:
                    local_conn.close()
                    continue

                def pipe(src, dst):
                    try:
                        while running:
                            data = src.recv(4096)
                            if not data:
                                break
                            dst.sendall(data)
                    except Exception:
                        pass
                    finally:
                        try:
                            src.close()
                        except Exception:
                            pass
                        try:
                            dst.close()
                        except Exception:
                            pass

                t1 = threading.Thread(target=pipe, args=(local_conn, chan), daemon=True)
                t2 = threading.Thread(target=pipe, args=(chan, local_conn), daemon=True)
                t1.start()
                t2.start()
            except Exception:
                break

    forward_thread = threading.Thread(target=forward_tunnel, daemon=True)
    forward_thread.start()

    url = "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale"
    print(f"\n[✔] Tunnel actif ! Ouverture de la page dans votre navigateur :")
    print(f"    {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("=" * 72)
    print("👉 INSTRUCTIONS D'AUTHENTIFICATION :")
    print("1. Votre navigateur affiche l'écran de Chromium distant sur le VPS.")
    print("2. Connectez-vous avec votre compte Google (mot de passe + 2FA téléphone).")
    print("3. Une fois arrivé sur l'interface principale de Gemini Web (gemini.google.com),")
    print("   revenez sur cette fenêtre de commande et APPUYEZ SUR [ENTRÉE].")
    print("=" * 72)

    try:
        input("\nAppuyez sur [ENTRÉE] lorsque vous êtes connecté sur Gemini Web...")
    except KeyboardInterrupt:
        pass

    print("\n[4/4] Fermeture de la session temporaire et démarrage du service autonome...")
    running = False
    try:
        local_server.close()
    except Exception:
        pass

    stop_cmd = (
        "sudo systemctl stop jarvis-chrome ; "
        "sudo pkill -15 -f chromium || true ; sudo pkill -15 -f chrome || true ; "
        "sleep 1 ; "
        "sudo pkill -9 -f chromium || true ; sudo pkill -9 -f chrome || true ; "
        "sudo pkill -9 -f x11vnc || true ; sudo pkill -9 -f websockify || true ; sudo pkill -9 -f Xvfb || true ; "
        "rm -f /home/opc/.jarvis_chrome_profile/Singleton* /tmp/.X99-lock /tmp/.X11-unix/X99 || true ; "
        "sudo chown -R opc:opc /home/opc/.jarvis_chrome_profile ; "
        "sudo chmod -R 700 /home/opc/.jarvis_chrome_profile ; "
        "sudo systemctl daemon-reload && "
        "sudo systemctl restart jarvis-chrome && "
        "sleep 3 && sudo systemctl is-active jarvis-chrome"
    )
    stdin, stdout, stderr = client.exec_command(stop_cmd)
    stdout.read()
    time.sleep(3)

    print("\n--- Diagnostic de Session Gemini sur le VPS ---")
    diag_out = ""
    for attempt in range(1, 7):
        time.sleep(2)
        stdin, stdout, stderr = client.exec_command("cd /home/opc/jarvis-core && ./venv/bin/python scripts/check_gemini_session.py")
        diag_out = stdout.read().decode('utf-8', errors='replace')
        if "ACTIVE" in diag_out or "SUCCÈS" in diag_out:
            break

    print(diag_out.strip())

    client.close()

    if "ACTIVE" in diag_out or "SUCCÈS" in diag_out:
        print("\n" + "=" * 72)
        print("  🎉 SESSION GOOGLE GEMINI VALIDÉE ET ACTIVE SUR LE CLOUD !")
        print("  Deep Research L3 est maintenant 100% opérationnel sur votre VPS.")
        print("=" * 72 + "\n")
    else:
        print("\n[!] Note : Si la session n'est pas encore marquée active, vous pouvez relancer ce script à tout moment.")


if __name__ == "__main__":
    start_vps_gui_session()
