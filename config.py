import os
import sys

os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"

# Répertoires de base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SCREENSHOT_PATH = os.path.join(STATIC_DIR, "latest_screenshot.jpg")
AUTH_FILE = os.path.join(BASE_DIR, "authorized_devices.json")
DB_PATH = os.path.join(BASE_DIR, "jarvis_memory.db")
PROFILE_DIR = os.path.join(BASE_DIR, ".jarvis_chrome_profile")
WORKSPACE_DIR = os.path.join(BASE_DIR, "my-project")

CHAT_UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads", "chat")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(CHAT_UPLOADS_DIR, exist_ok=True)
os.makedirs(WORKSPACE_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

# Chargement prioritaire du fichier .env si présent
try:
    from dotenv import load_dotenv
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
except Exception:
    pass

# Mot de passe maître défini par l'utilisateur
ACCESS_PASSWORD = os.environ.get("JARVIS_PASSWORD", "Bonjourmotdepassedu52..")

# Configuration Tunnel Cloudflare Permanent (signalcraftapps.com)
CLOUDFLARE_TUNNEL_TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
CLOUDFLARE_HOSTNAME = os.environ.get("CLOUDFLARE_HOSTNAME", "jarvis.signalcraftapps.com").strip()

# Détection de l'exécutable Chrome sous Windows
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

# Détection des clés GEMINI (plan gratuit + plan payant)
if not os.environ.get("GEMINI_API_KEY"):
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                val, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
                if val:
                    os.environ["GEMINI_API_KEY"] = val
        except Exception:
            pass

# Clés API Gemini :
# - GEMINI_API_KEY_FREE : utilisée prioritairement pour le modèle vocal de base gemini-3.8-live
# - GEMINI_API_KEY_PAID : utilisée pour gemini-3.8-live-extended-thinking, gemini-3.8-flash, Agents Antigravity et repli automatique
_paid_raw = os.environ.get("GEMINI_API_KEY_PAID", "").strip()
if not _paid_raw or _paid_raw == "VOTRE_CLE_PAYANTE_ICI":
    _paid_raw = ""

_free_raw = os.environ.get("GEMINI_API_KEY_FREE", "").strip()
if not _free_raw or _free_raw == "VOTRE_CLE_GRATUITE_ICI":
    _free_raw = ""

_default_key = os.environ.get("GEMINI_API_KEY", "").strip()

GEMINI_API_KEY_FREE = _free_raw or _default_key
GEMINI_API_KEY_PAID = _paid_raw
GEMINI_API_KEY = GEMINI_API_KEY_PAID or GEMINI_API_KEY_FREE

if GEMINI_API_KEY_PAID:
    os.environ["GEMINI_API_KEY_PAID"] = GEMINI_API_KEY_PAID
if GEMINI_API_KEY_FREE:
    os.environ["GEMINI_API_KEY_FREE"] = GEMINI_API_KEY_FREE

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

HAS_PAID_API_KEY = bool(_paid_raw and _paid_raw != "VOTRE_CLE_PAYANTE_ICI")

# Voix préconstruite Gemini Live (Voix féminines disponibles : Aoede, Kore, Leda)
JARVIS_VOICE = os.environ.get("JARVIS_VOICE", "Aoede").strip()

# Modèle vocal Gemini Live officiel : 'gemini-3.8-live' (défaut) ou 'gemini-3.8-live-extended-thinking'
# Strictement limité à ces deux modèles (aucun repli vers 3.1)
GEMINI_LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
if GEMINI_LIVE_MODEL not in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
    GEMINI_LIVE_MODEL = "gemini-3.8-live"

# Configuration Service E-mail & Rapports Stark Industries
DEFAULT_RECIPIENT_EMAIL = os.environ.get("JARVIS_DEFAULT_EMAIL", "pierrecassagnettes@gmail.com")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
EMAIL_SENDER_NAME = os.environ.get("EMAIL_SENDER_NAME", "J.A.R.V.I.S. - Stark Industries")

# Configuration IMAP (Lecture des e-mails reçus)
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("IMAP_PORT", 993))
IMAP_SSL = os.environ.get("IMAP_SSL", "true").lower() in ("true", "1", "yes")

# Dossier d'archivage local des e-mails envoyés
EMAIL_OUTBOX_DIR = os.path.join(BASE_DIR, "outbox_emails")
os.makedirs(EMAIL_OUTBOX_DIR, exist_ok=True)


