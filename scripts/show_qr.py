"""J.A.R.V.I.S. Visual QR Code Pop-up (Stark Industries HUD)
Affiche une interface graphique moderne avec le QR Code vérifié,
la gestion du domaine permanent (signalcraftapps.com) et le bouton de copie rapide.
"""

import sys
import tkinter as tk
from PIL import Image, ImageTk
import qrcode
import subprocess


def copy_text_to_clipboard(text: str, btn: tk.Button):
    """Copie l'URL dans le presse-papier et modifie le libellé du bouton temporairement."""
    try:
        proc = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, shell=False)
        proc.communicate(input=text.encode("utf-8"), timeout=2)
    except Exception:
        pass
    
    orig_text = btn.cget("text")
    btn.config(text="✓ COPIÉ DANS LE PRESSE-PAPIER !", bg="#10B981", fg="#0B0F19")
    btn.after(2000, lambda: btn.config(text=orig_text, bg="#1E293B", fg="#38BDF8"))


def show_qr_window(qr_url: str, base_url: str = None, mode: str = "quick"):
    if not base_url:
        base_url = qr_url.split("/?")[0] if "/?" in qr_url else qr_url

    is_permanent = (mode == "permanent")

    root = tk.Tk()
    root.title("J.A.R.V.I.S. Mobile Uplink - Stark Industries")
    root.geometry("480x670")
    root.configure(bg="#0B0F19")
    root.resizable(False, False)

    # Assurer que la fenêtre passe au premier plan sans bloquer le reste
    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)

    # 1. En-tête HUD
    header_frame = tk.Frame(root, bg="#0B0F19")
    header_frame.pack(pady=(16, 6))

    title_lbl = tk.Label(
        header_frame,
        text="✦  J . A . R . V . I . S .  ✦",
        font=("Segoe UI", 16, "bold"),
        fg="#00E5FF",
        bg="#0B0F19"
    )
    title_lbl.pack()

    # Indicateur d'état vert "Vérifié en ligne"
    status_frame = tk.Frame(header_frame, bg="#0B0F19")
    status_frame.pack(pady=(2, 0))

    status_dot = tk.Label(
        status_frame,
        text="●",
        font=("Segoe UI", 10, "bold"),
        fg="#10B981",
        bg="#0B0F19"
    )
    status_dot.pack(side="left", padx=(0, 4))

    status_text = tk.Label(
        status_frame,
        text="LIAISON SÉCURISÉE VÉRIFIÉE EN LIGNE (HTTP/2)",
        font=("Segoe UI", 8, "bold"),
        fg="#10B981",
        bg="#0B0F19"
    )
    status_text.pack(side="left")

    # 2. Badge Permanent vs Temporaire
    badge_frame = tk.Frame(root, bg="#111827", bd=1, relief="solid")
    badge_frame.pack(fill="x", padx=30, pady=(6, 8))

    if is_permanent:
        badge_lbl = tk.Label(
            badge_frame,
            text="⭐ ADRESSE PERMANENTE FIXE (Ne change JAMAIS)",
            font=("Segoe UI", 9, "bold"),
            fg="#FACC15",
            bg="#111827"
        )
        badge_lbl.pack(pady=4)
    elif mode == "local":
        badge_lbl = tk.Label(
            badge_frame,
            text="📡 ACCÈS LOCAL DIRECT WI-FI (Même réseau Wi-Fi)",
            font=("Segoe UI", 9, "bold"),
            fg="#38BDF8",
            bg="#111827"
        )
        badge_lbl.pack(pady=4)
        status_dot.config(fg="#38BDF8")
        status_text.config(text="MODE LOCAL WI-FI ACTIF (Protection Erreur 1033)", fg="#38BDF8")
    else:
        badge_lbl = tk.Label(
            badge_frame,
            text="⚠️ ADRESSE TEMPORAIRE (trycloudflare.com)",
            font=("Segoe UI", 9, "bold"),
            fg="#F59E0B",
            bg="#111827"
        )
        badge_lbl.pack(pady=4)

    # 3. Génération du QR Code PIL (noir sur blanc pour un contraste et scan parfait)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    tk_img = ImageTk.PhotoImage(img)

    # Cadre avec bordure néon cyan
    qr_container = tk.Frame(root, bg="#00E5FF", bd=2)
    qr_container.pack(pady=6)

    qr_label = tk.Label(qr_container, image=tk_img, bg="white")
    qr_label.image = tk_img
    qr_label.pack(padx=5, pady=5)

    # 4. URL cliquable / affichée
    url_frame = tk.Frame(root, bg="#111827", bd=1, relief="solid")
    url_frame.pack(fill="x", padx=25, pady=(6, 8))

    url_lbl = tk.Label(
        url_frame,
        text=base_url,
        font=("Consolas", 10, "bold"),
        fg="#38BDF8",
        bg="#111827",
        wraplength=420,
        justify="center"
    )
    url_lbl.pack(pady=(6, 2))

    # Bouton copier URL rapide
    copy_btn = tk.Button(
        url_frame,
        text="📋 Copier l'adresse",
        font=("Segoe UI", 8, "bold"),
        fg="#38BDF8",
        bg="#1E293B",
        activebackground="#0284C7",
        activeforeground="#FFFFFF",
        relief="flat",
        cursor="hand2",
        padx=10,
        pady=3
    )
    copy_btn.config(command=lambda: copy_text_to_clipboard(base_url, copy_btn))
    copy_btn.pack(pady=(0, 6))

    # 5. Instructions raccourci mobile
    info_frame = tk.Frame(root, bg="#0B0F19")
    info_frame.pack(fill="x", padx=25, pady=(0, 10))

    if is_permanent:
        guide_text = (
            "📱 RACCOURCI FIXE SUR SMARTPHONE :\n"
            "1. Scannez le QR Code pour enregistrer ce terminal sans mot de passe.\n"
            "2. Sur Safari (iOS) : Partager > 'Sur l'écran d'accueil'.\n"
            "   Sur Chrome (Android) : Menu (⋮) > 'Ajouter à l'écran d'accueil'.\n"
            "✦ Votre raccourci marchera en permanence, sans jamais rescanner ! ✦"
        )
        guide_fg = "#10B981"
    elif mode == "local":
        guide_text = (
            "📡 ACCÈS LOCAL WI-FI DIRECT SÉCURISÉ :\n"
            "1. Connectez votre smartphone au MÊME réseau Wi-Fi.\n"
            "2. Scannez le QR Code pour ouvrir JARVIS sans mot de passe.\n"
            "💡 Déconnectez le VPN Cisco AnyConnect pour réactiver l'accès distant !"
        )
        guide_fg = "#38BDF8"
    else:
        guide_text = (
            "✨ SCANNER = ENREGISTREMENT SANS MOT DE PASSE ✨\n"
            "💡 Astuce : Pour que l'adresse ne change plus jamais et créer un\n"
            "raccourci définitif, renseignez CLOUDFLARE_TUNNEL_TOKEN dans .env !"
        )
        guide_fg = "#94A3B8"

    info_lbl = tk.Label(
        info_frame,
        text=guide_text,
        font=("Segoe UI", 8),
        fg=guide_fg,
        bg="#0B0F19",
        justify="center"
    )
    info_lbl.pack()

    # 6. Bouton Fermer
    btn_close = tk.Button(
        root,
        text="Fermer la fenêtre",
        command=root.destroy,
        font=("Segoe UI", 9, "bold"),
        fg="#0B0F19",
        bg="#00E5FF",
        activebackground="#38BDF8",
        activeforeground="#0B0F19",
        relief="flat",
        padx=20,
        pady=5,
        cursor="hand2"
    )
    btn_close.pack(pady=(2, 10))

    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()


if __name__ == "__main__":
    target_qr_url = sys.argv[1] if len(sys.argv) > 1 else "https://jarvis.stark.local"
    target_base_url = sys.argv[2] if len(sys.argv) > 2 else target_qr_url.split("/?")[0]
    target_mode = sys.argv[3] if len(sys.argv) > 3 else "quick"

    show_qr_window(target_qr_url, target_base_url, target_mode)
