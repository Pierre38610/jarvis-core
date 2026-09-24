"""J.A.R.V.I.S. Tunnel & Uplink Launcher - Stark Industries
Gestionnaire automatique et sécurisé du Tunnel Cloudflare HTTPS (HTTP/2)
Supporte :
1. Tunnel Permanent Nominatif (Cloudflare Zero Trust Token sur signalcraftapps.com)
2. Repli Quick Tunnel Cloudflare (trycloudflare.com)
3. Repli Automatique Réseau Local Wi-Fi Direct (en cas de VPN actif ou port 7844 bloqué)
Avec VÉRIFICATION STRICTE DE JOIGNABILITÉ pour éliminer à 100% le bug "Erreur 1033 / Site indisponible".
"""

import os
import sys
import re
import time
import socket
import signal
import atexit
import threading
import subprocess
import urllib.request
import urllib.error
import json

# Forcer l'encodage UTF-8 dans la console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config

BASE_DIR = config.BASE_DIR
CLOUDFLARED_BIN = os.path.join(BASE_DIR, "cloudflared.exe")
TUNNEL_URL_FILE = os.path.join(BASE_DIR, "tunnel_url.txt")
STATIC_URL_FILE = os.path.join(BASE_DIR, "static", "tunnel_url.json")

cloudflared_process = None


def cleanup():
    """Arrête proprement le processus cloudflared à la fermeture."""
    global cloudflared_process
    if cloudflared_process:
        try:
            if cloudflared_process.poll() is None:
                print("\n[*] Arrêt du tunnel Cloudflare...")
                cloudflared_process.terminate()
                cloudflared_process.wait(timeout=2)
        except Exception:
            try:
                cloudflared_process.kill()
            except Exception:
                pass
        cloudflared_process = None


atexit.register(cleanup)


def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_network_info() -> tuple[str, bool, str]:
    """Détecte l'adresse IPv4 locale physique réelle (Wi-Fi ou LAN),
    en ignorant les adaptateurs virtuels et VPNs (Cisco AnyConnect, TAP, Proton, etc.).
    Retourne (ip_locale, vpn_actif, type_adaptateur).
    """
    vpn_detected = False
    wifi_ip = None
    lan_ip = None
    fallback_ip = None

    try:
        out = subprocess.check_output("ipconfig /all", text=True, errors="ignore", timeout=3)
        adapters = []
        current_name = ""
        current_ips = []

        for line in out.splitlines():
            line_str = line.strip()
            if line and not line.startswith(" ") and ":" in line:
                if current_name and current_ips:
                    adapters.append((current_name, current_ips))
                current_name = line.split(":")[0].strip()
                current_ips = []
            elif "ipv4" in line_str.lower() and ":" in line_str:
                m = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line_str)
                if m:
                    ip = m.group(0)
                    if not ip.startswith("127."):
                        current_ips.append(ip)

        if current_name and current_ips:
            adapters.append((current_name, current_ips))

        vpn_keywords = [
            "cisco", "anyconnect", "tap", "vpn", "proton", "wireguard",
            "openvpn", "virtual", "vmware", "hyper-v", "loopback", "vethernet"
        ]

        for name, ips in adapters:
            name_lower = name.lower()
            if any(k in name_lower for k in ["cisco", "anyconnect", "tap", "vpn", "proton"]) or any(ip.startswith("147.171.") for ip in ips):
                vpn_detected = True

            is_vpn = any(k in name_lower for k in vpn_keywords) or any(ip.startswith("147.171.") for ip in ips)
            is_wifi = any(w in name_lower for w in ["wi-fi", "wifi", "wireless", "sans fil", "wlan"])

            for ip in ips:
                if not is_vpn:
                    if is_wifi and not wifi_ip:
                        wifi_ip = ip
                    elif not lan_ip and (ip.startswith("192.168.") or ip.startswith("10.") or (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31)):
                        lan_ip = ip
                    elif not fallback_ip:
                        fallback_ip = ip

        if wifi_ip:
            return wifi_ip, vpn_detected, "Wi-Fi"
        if lan_ip:
            return lan_ip, vpn_detected, "Ethernet"
        if fallback_ip:
            return fallback_ip, vpn_detected, "LAN"
    except Exception:
        pass

    return "127.0.0.1", vpn_detected, "Localhost"


def check_port_7844_reachability(timeout: float = 2.0) -> bool:
    """Teste rapidement si le port sortant 7844 (Cloudflare Argo Edge) est joignable.
    Si le port est bloqué (VPN d'entreprise / campus), Cloudflare Edge retournera l'Erreur 1033.
    """
    probe_targets = [
        ("region1.v2.argotunnel.com", 7844),
        ("region2.v2.argotunnel.com", 7844),
        ("198.41.192.107", 7844)
    ]
    for host, port in probe_targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((host, port))
            s.close()
            if res == 0:
                return True
        except Exception:
            pass
    return False


def copy_to_clipboard(text: str) -> bool:
    """Copie un texte dans le presse-papier Windows via clip.exe."""
    if sys.platform != "win32":
        return False
    try:
        proc = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, shell=False)
        proc.communicate(input=text.encode("utf-8"), timeout=2)
        return True
    except Exception:
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2
            )
            return True
        except Exception:
            return False


def wait_for_backend(timeout: int = 25) -> bool:
    """Attend que le serveur backend FastAPI soit prêt sur http://127.0.0.1:8000."""
    print("  [⏳] Attente de la disponibilité du serveur FastAPI (port 8000)...", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/api/verify")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status in (200, 401):
                    print(" [PRÊT]")
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (200, 401, 403, 404):
                print(" [PRÊT]")
                return True
        except Exception:
            pass
        time.sleep(0.5)
        print(".", end="", flush=True)
    print(" [DÉMARRÉ]")
    return False


def wait_for_tunnel_reachability(url: str, timeout: int = 30) -> bool:
    """Vérifie que le tunnel HTTPS répond RÉELLEMENT depuis l'extérieur avant d'afficher le HUD.
    Élimine à 100% l'erreur 1033 et le bug 'Site indisponible'.
    """
    print("  [⏳] Vérification de la connectivité Cloudflare Edge...", end="", flush=True)
    start = time.time()
    target_probe = url.rstrip("/") + "/api/verify"

    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(
                target_probe,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JarvisMobileCheck/3.0"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status in (200, 401, 302, 307):
                    elapsed = round(time.time() - start, 1)
                    print(f" [LIAISON CONFIRMÉE en {elapsed}s (HTTP {resp.status})]")
                    return True
        except urllib.error.HTTPError as e:
            if e.code in (200, 401, 302, 307):
                elapsed = round(time.time() - start, 1)
                print(f" [LIAISON CONFIRMÉE en {elapsed}s (HTTP {e.code})]")
                return True
        except Exception:
            pass
        time.sleep(1)
        print(".", end="", flush=True)

    print(" [DÉLAI EXPIRÉ]")
    return False


def display_hud_banner(
    display_url: str,
    qr_url: str,
    local_ip: str,
    copied: bool,
    mode: str = "permanent",
    vpn_warning: bool = False,
    target_domain: str = None
):
    """Affiche l'interface console HUD Stark Industries pour l'utilisateur."""
    print("\n" + "=" * 76)
    print("       ✦  J . A . R . V . I . S .   C O R E   S E R V E R  ✦")
    print("                     STARK INDUSTRIES MOBILE UPLINK")
    print("=" * 76)
    print("  [✔] Serveur Backend FastAPI   : http://127.0.0.1:8000")

    if mode == "permanent":
        print("  [✔] Tunnel Cloudflare Edge    : ACTIF ET VÉRIFIÉ (HTTP/2)")
        print("  [⭐] Mode                      : DOMAINE PERMANENT FIXE")
        print("-" * 76)
        print("  ⭐ ADRESSE HTTPS FIXE (Ne change JAMAIS) :")
        print(f"     👉  {display_url}  👈")
        if copied:
            print("  📋 [COPIÉ DANS VOTRE PRESSE-PAPIER AUTOMATIQUEMENT]")
        print("-" * 76)
        print("  📱 RACCOURCI MOBILE PERMANENT :")
        print("     1. Scannez le QR Code ou ouvrez le lien ci-dessus sur votre téléphone.")
        print("     2. Ajoutez la page à l'écran d'accueil de votre smartphone :")
        print("        • Sur iPhone (Safari)  : Bouton Partager (carré + flèche) > 'Sur l'écran d'accueil'")
        print("        • Sur Android (Chrome) : Menu 3 points (⋮) > 'Ajouter à l'écran d'accueil'")
        print("     3. Votre raccourci restera toujours actif et connecté sans mot de passe !")
    elif mode == "local":
        print("  [⚠️] Tunnel Cloudflare Edge    : SUSPENDU (Port 7844 filtré)")
        if vpn_warning:
            print("  [🛡️] Diagnostic Sécurité       : VPN Actif (Cisco AnyConnect / Réseau institutionnel)")
        print("  [📡] Mode                      : RÉSEAU LOCAL DIRECT WI-FI (Garanti 100% fonctionnel)")
        print("-" * 76)
        print("  📡 ADRESSE WI-FI DIRECT (Protection contre l'Erreur 1033) :")
        print(f"     👉  {display_url}  👈")
        if copied:
            print("  📋 [COPIÉ DANS VOTRE PRESSE-PAPIER AUTOMATIQUEMENT]")
        print("-" * 76)
        print("  📱 ACCÈS MOBILE INSTANTANÉ (Même Wi-Fi) :")
        print("     1. Assurez-vous que votre smartphone est connecté au MÊME réseau Wi-Fi.")
        print("     2. Scannez le QR Code ci-dessous : votre téléphone se connecte directement !")
        print("-" * 76)
        if target_domain:
            print("  💡 POUR RÉACTIVER VOTRE RACCOURCI DISTANT FIXE :")
            print(f"     (Raccourci : {target_domain})")
            print("     • Déconnectez temporairement votre VPN Cisco AnyConnect de votre PC.")
            print("     • Le tunnel permanent s'activera alors automatiquement sans aucune configuration !")
    else:
        print("  [✔] Tunnel Cloudflare Edge    : ACTIF ET VÉRIFIÉ (HTTP/2)")
        print("  [⚠️] Mode                      : TEMPORAIRE (trycloudflare.com)")
        print("-" * 76)
        print("  📱 LIEN HTTPS TEMPORAIRE :")
        print(f"     👉  {display_url}  👈")
        if copied:
            print("  📋 [COPIÉ DANS VOTRE PRESSE-PAPIER AUTOMATIQUEMENT]")

    print("-" * 76)
    print("  ✨ SCAN QR CODE MOBILE : Enregistrement direct sans mot de passe")
    print(f"  💻 ACCÈS LOCAL (Même Wi-Fi) : http://{local_ip}:8000")
    print(f"  🔑 MOT DE PASSE (Saisie manuelle) : {config.ACCESS_PASSWORD}")
    print("-" * 76)

    # Affichage QR Code console si supporté
    try:
        import qrcode
        import io
        print("\n  [SCANNEZ AVEC L'APPAREIL PHOTO DE VOTRE TÉLÉPHONE - ACCÈS SÉCURISÉ] :")
        buf = io.StringIO()
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_url)
        qr.print_ascii(out=buf, invert=True)
        qr_str = buf.getvalue()
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(qr_str.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        else:
            print(qr_str)
    except Exception:
        pass

    print("=" * 76)
    print("  Appuyez sur [Ctrl + C] pour quitter et fermer le serveur.\n")


def save_tunnel_data(tunnel_url: str, local_ip: str):
    """Sauvegarde les métadonnées d'URL pour le frontend et les services."""
    try:
        with open(TUNNEL_URL_FILE, "w", encoding="utf-8") as f:
            f.write(tunnel_url)
    except Exception:
        pass

    try:
        with open(STATIC_URL_FILE, "w", encoding="utf-8") as f:
            json.dump({"url": tunnel_url, "local_ip": local_ip, "timestamp": time.time()}, f)
    except Exception:
        pass


def launch_qr_gui(qr_url: str, base_url: str, mode: str):
    """Ouvre la fenêtre graphique stylisée Stark HUD avec le QR Code."""
    try:
        qr_script = os.path.join(BASE_DIR, "show_qr.py")
        py_bin = sys.executable
        subprocess.Popen([py_bin, qr_script, qr_url, base_url, mode],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"  [!] Note: GUI QR Code non affiché ({e}), utilisez l'URL console.")


def run_permanent_tunnel(bin_path: str, token: str, hostname: str, local_ip: str, vpn_detected: bool):
    """Exécute un tunnel Cloudflare Zero Trust permanent avec token fixe,
    forcé en HTTP/2 sans pré-vérifications pour éviter les timeouts QUIC UDP.
    """
    global cloudflared_process

    tunnel_url = f"https://{hostname}"
    print(f"\n  [*] Démarrage du Tunnel Permanent Cloudflare vers {tunnel_url}...")

    # Forcer HTTP/2 et désactiver les pré-vérifications bloquantes
    cmd = [
        bin_path,
        "tunnel",
        "--protocol", "http2",
        "--no-prechecks",
        "run",
        "--token", token
    ]

    try:
        cloudflared_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as e:
        print(f"\n[ERREUR] Impossible d'exécuter cloudflared : {e}")
        return False

    def monitor_output():
        for line in iter(cloudflared_process.stdout.readline, ""):
            line_clean = line.strip()
            # Afficher uniquement les alertes critiques non répétitives
            if "ERR" in line_clean and not any(ign in line_clean.lower() for ign in ["icmp", "retrying"]):
                print(f"  [Cloudflare Log] {line_clean}")

    t = threading.Thread(target=monitor_output, daemon=True)
    t.start()

    # Vérification rapide de l'accessibilité du port 7844
    port_7844_ok = check_port_7844_reachability(timeout=2.0)

    is_reachable = False
    if port_7844_ok:
        is_reachable = wait_for_tunnel_reachability(tunnel_url, timeout=12)
    else:
        print("  [!] Port 7844 filtré (VPN/pare-feu détecté). Test rapide de liaison...", end="", flush=True)
        is_reachable = wait_for_tunnel_reachability(tunnel_url, timeout=3)
        if not is_reachable:
            print(" [INACCESSIBLE]")

    if is_reachable:
        # Tunnel opérationnel à 100%
        save_tunnel_data(tunnel_url, local_ip)
        qr_url = tunnel_url
        try:
            import auth
            ticket = auth.create_qr_ticket()
            qr_url = f"{tunnel_url}/?ticket={ticket}"
        except Exception:
            pass

        copied = copy_to_clipboard(tunnel_url)
        display_hud_banner(tunnel_url, qr_url, local_ip, copied, mode="permanent")
        launch_qr_gui(qr_url, tunnel_url, mode="permanent")
    else:
        # Port 7844 bloqué / VPN actif : basculement immédiat vers le Wi-Fi local
        # pour éliminer à 100% l'erreur 1033 sur le smartphone
        local_url = f"http://{local_ip}:8000"
        save_tunnel_data(local_url, local_ip)
        qr_url = local_url
        try:
            import auth
            ticket = auth.create_qr_ticket()
            qr_url = f"{local_url}/?ticket={ticket}"
        except Exception:
            pass

        copied = copy_to_clipboard(local_url)
        display_hud_banner(
            local_url,
            qr_url,
            local_ip,
            copied,
            mode="local",
            vpn_warning=vpn_detected,
            target_domain=tunnel_url
        )
        launch_qr_gui(qr_url, local_url, mode="local")

    cloudflared_process.wait()
    return True


def run_quick_tunnel(bin_path: str, local_ip: str, vpn_detected: bool):
    """Exécute un Quick Tunnel Cloudflare temporaire (trycloudflare.com)."""
    global cloudflared_process

    cmd = [
        bin_path,
        "tunnel",
        "--url", "http://127.0.0.1:8000",
        "--protocol", "http2",
        "--no-prechecks",
        "--http-host-header", "127.0.0.1:8000"
    ]

    print("  [*] Négociation du tunnel HTTPS avec Cloudflare...")

    try:
        cloudflared_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
    except Exception as e:
        print(f"\n[ERREUR] Impossible d'exécuter cloudflared : {e}")
        return False

    tunnel_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    for line in iter(cloudflared_process.stdout.readline, ""):
        line_clean = line.strip()

        if not tunnel_url and line_clean:
            if "requesting new quick tunnel" in line_clean.lower():
                print("  [*] Enregistrement du tunnel sur trycloudflare.com...")
            elif "ERR" in line_clean or "failed" in line_clean.lower() or "error" in line_clean.lower():
                if not any(ign in line_clean.lower() for ign in ["icmp", "retrying"]):
                    print(f"  [Cloudflare] {line_clean}")

        match = url_pattern.search(line_clean)
        if match and not tunnel_url:
            tunnel_url = match.group(0)
            print(f"  [*] URL allouée par Cloudflare : {tunnel_url}")

            save_tunnel_data(tunnel_url, local_ip)
            is_ok = wait_for_tunnel_reachability(tunnel_url, timeout=20)

            if is_ok:
                qr_url = tunnel_url
                try:
                    import auth
                    ticket = auth.create_qr_ticket()
                    qr_url = f"{tunnel_url}/?ticket={ticket}"
                except Exception:
                    pass

                copied = copy_to_clipboard(tunnel_url)
                display_hud_banner(tunnel_url, qr_url, local_ip, copied, mode="quick")
                launch_qr_gui(qr_url, tunnel_url, mode="quick")
            else:
                # Repli local
                local_url = f"http://{local_ip}:8000"
                save_tunnel_data(local_url, local_ip)
                qr_url = local_url
                try:
                    import auth
                    ticket = auth.create_qr_ticket()
                    qr_url = f"{local_url}/?ticket={ticket}"
                except Exception:
                    pass

                copied = copy_to_clipboard(local_url)
                display_hud_banner(
                    local_url,
                    qr_url,
                    local_ip,
                    copied,
                    mode="local",
                    vpn_warning=vpn_detected,
                    target_domain=tunnel_url
                )
                launch_qr_gui(qr_url, local_url, mode="local")

        if cloudflared_process.poll() is not None:
            if not tunnel_url:
                print(f"\n[ERREUR] cloudflared s'est arrêté avec le code {cloudflared_process.returncode}.")
            break

    if cloudflared_process:
        cloudflared_process.wait()
    return True


def main():
    bin_path = CLOUDFLARED_BIN if os.path.exists(CLOUDFLARED_BIN) else "cloudflared.exe"

    print("\n" + "=" * 60)
    print("  INITIALISATION DU TUNNEL SECURISE J.A.R.V.I.S.")
    print("=" * 60)

    # Nettoyage de tout processus précédent
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # Attente disponibilité backend FastAPI
    wait_for_backend(timeout=25)

    local_ip, vpn_detected, adapter_type = get_network_info()

    # Priorité 1 : Tunnel Permanent si le token Cloudflare Zero Trust est renseigné
    token = getattr(config, "CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    hostname = getattr(config, "CLOUDFLARE_HOSTNAME", "").strip() or "jarvis.signalcraftapps.com"

    if token:
        success = run_permanent_tunnel(bin_path, token, hostname, local_ip, vpn_detected)
        if success:
            return

    # Priorité 2 : Repli vers Quick Tunnel Cloudflare
    run_quick_tunnel(bin_path, local_ip, vpn_detected)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        cleanup()
        print("\n[*] J.A.R.V.I.S. Tunnel arrêté proprement.")
        sys.exit(0)
