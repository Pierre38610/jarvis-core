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
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "").strip()
JWT_EXPIRATION_DAYS = int(os.environ.get("JWT_EXPIRATION_DAYS", "90"))

# Configuration Tunnel Cloudflare Permanent (signalcraftapps.com)
CLOUDFLARE_TUNNEL_TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
CLOUDFLARE_HOSTNAME = os.environ.get("CLOUDFLARE_HOSTNAME", "jarvis.signalcraftapps.com").strip()

# Intégration Spotify Web API
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI = os.environ.get(
    "SPOTIFY_REDIRECT_URI",
    "https://jarvis.signalcraftapps.com/api/media/spotify/callback"
).strip()

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
# - GEMINI_API_KEY_FREE : utilisée pour gemini-3.8-live, gemini-3.8-live-extended-thinking, classification Tier 1 (gemini-3.8-flash, JSON, timeout 3.5s)
# - GEMINI_API_KEY_PAID : clé de SECOURS uniquement (échec qualifié clé FREE ou dépassement quota Antigravity CLI)
_paid_raw = os.environ.get("GEMINI_API_KEY_PAID", "").strip()
if not _paid_raw or _paid_raw == "VOTRE_CLE_PAYANTE_ICI":
    _paid_raw = ""

_free_raw = os.environ.get("GEMINI_API_KEY_FREE", "").strip()
if not _free_raw or _free_raw == "VOTRE_CLE_GRATUITE_ICI":
    _free_raw = ""

_default_key = os.environ.get("GEMINI_API_KEY", "").strip()

GEMINI_API_KEY_FREE = _free_raw or _default_key
GEMINI_API_KEY_PAID = _paid_raw
GEMINI_API_KEY = GEMINI_API_KEY_FREE or GEMINI_API_KEY_PAID

if GEMINI_API_KEY_PAID:
    os.environ["GEMINI_API_KEY_PAID"] = GEMINI_API_KEY_PAID
if GEMINI_API_KEY_FREE:
    os.environ["GEMINI_API_KEY_FREE"] = GEMINI_API_KEY_FREE

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY_FREE or GEMINI_API_KEY
os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY_FREE or GEMINI_API_KEY

HAS_PAID_API_KEY = bool(_paid_raw and _paid_raw != "VOTRE_CLE_PAYANTE_ICI")

# Encoche d'autorisation de la clé payante :
# L'utilisateur coche ou décoche dans l'app pour autoriser l'utilisation de la clé payante.
# Si non cochée, le modèle est dans l'IMPOSSIBILITÉ PHYSIQUE d'effectuer la moindre requête sur la clé payante.
def _load_paid_key_authorization() -> bool:
    try:
        import sqlite3
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT value FROM user_profile WHERE key = 'paid_key_authorized'")
            row = cur.fetchone()
            conn.close()
            if row:
                return str(row[0]).strip().lower() in ("true", "1", "yes", "on")
    except Exception:
        pass
    return False

PAID_KEY_AUTHORIZED: bool = _load_paid_key_authorization()

def is_paid_key_authorized() -> bool:
    """Indique si Pierre a coché l'encoche autorisant l'utilisation de la clé payante."""
    global PAID_KEY_AUTHORIZED
    return bool(PAID_KEY_AUTHORIZED)

def set_paid_key_authorized(authorized: bool) -> bool:
    """Met à jour l'encoche d'autorisation et la persiste dans SQLite."""
    global PAID_KEY_AUTHORIZED
    PAID_KEY_AUTHORIZED = bool(authorized)
    try:
        import sqlite3
        import datetime
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cur.execute(
            "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES ('paid_key_authorized', ?, ?)",
            ("true" if authorized else "false", now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Config] Erreur persistance paid_key_authorized : {e}")
    return PAID_KEY_AUTHORIZED

def get_effective_paid_key(session_id: str | None = None, task_id: str | None = None) -> str:
    """Retourne la clé payante UNIQUEMENT si un consentement valide pour cette tâche ou l'encoche existe.
    Sinon retourne une chaîne vide : impossibilité d'émettre des requêtes payantes.
    """
    try:
        from services.key_gate import has_paid_consent
        if has_paid_consent(session_id=session_id, task_id=task_id):
            return GEMINI_API_KEY_PAID
    except ImportError:
        pass
    if is_paid_key_authorized():
        return GEMINI_API_KEY_PAID
    return ""

def is_paid_key_active() -> bool:
    """Vérifie si la clé payante est à la fois configurée et autorisée."""
    return bool((is_paid_key_authorized() or get_effective_paid_key()) and GEMINI_API_KEY_PAID and HAS_PAID_API_KEY)


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

# Configuration Infrastructure Stack (Redis, PostgreSQL, Qdrant)
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1").strip()
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "").strip()
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1").strip()
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", 5432))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "jarvis").strip()
POSTGRES_USER = os.environ.get("POSTGRES_USER", "jarvis_admin").strip()
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "").strip()

QDRANT_HOST = os.environ.get("QDRANT_HOST", "127.0.0.1").strip()
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "").strip()

# Seuil de durée estimée pour le déclenchement des jalons vocaux intermédiaires (en secondes)
VOCAL_MILESTONE_THRESHOLD_SECONDS = float(os.getenv("VOCAL_MILESTONE_THRESHOLD_SECONDS", "90.0"))



# ─── Instruction système J.A.R.V.I.S. (Template) ─────────────────────────────
# Contient les placeholders {memory_context}, {paid_key_status}, {live_model}
# injectés dynamiquement à chaque connexion vocale par routers/voice.py
JARVIS_SYSTEM_INSTRUCTION_TEMPLATE = """
Tu es J.A.R.V.I.S., l'assistant vocal personnel de ton utilisateur. Tu parles français, avec un ton
calme, précis et légèrement britannique. Tu es un assistant qui FAIT les choses correctement, pas
un assistant qui répond vite.

Date et heure : {current_datetime}
Mémoire et contexte utilisateur :
{memory_context}

Plan en cours :
{active_plan_status}

Agents Antigravity en cours :
{active_subagents_status}

══════════════════════════════════════════
1. PRINCIPES FONDAMENTAUX
══════════════════════════════════════════
- La qualité passe avant la vitesse. Si une tâche mérite du temps, prends ce temps et dis-le :
  « Je m'en occupe, ça va me prendre quelques minutes. »
- Ne bâcle jamais. Une tâche à moitié faite et annoncée comme terminée est la pire erreur possible.
- En cas de doute sur ce que veut l'utilisateur, pose UNE question courte avant d'agir, plutôt que
  de deviner sur une tâche longue ou irréversible.

══════════════════════════════════════════
2. CONSIGNES MULTIPLES : NE RIEN OUBLIER
══════════════════════════════════════════
- Quand l'utilisateur donne plusieurs consignes, décompose-les mentalement en une liste d'étapes
  numérotées AVANT d'agir. Pour 3 étapes ou plus, ou si les étapes dépendent les unes des autres,
  crée un plan avec l'outil de planification.
- Reformule brièvement : « Donc : un, …, deux, …, trois, … Je commence. »
- Exécute chaque étape, puis coche-la. Avant de conclure, relis le plan en cours ci-dessus. S'il
  reste une étape non faite, fais-la ou dis explicitement pourquoi elle n'est pas faite.
- Ne déclare jamais « c'est fait » tant que le plan contient des étapes en attente.

══════════════════════════════════════════
3. VÉRITÉ SUR LES RÉSULTATS (ANTI-FAUSSE CONFIRMATION)
══════════════════════════════════════════
Chaque outil renvoie un résultat structuré avec un statut et un champ verified.
- status = "success" et verified = true → tu peux dire que c'est fait, en citant une preuve
  concrète (titre du document, destinataire, heure de l'événement, lien…).
- status = "success" et verified = false → dis « c'est lancé, mais je n'ai pas encore pu le
  vérifier », puis vérifie si un outil le permet.
- status = "error" → dis clairement que ça a échoué, en une phrase, avec la raison. Propose une
  alternative ou une nouvelle tentative. N'invente jamais un succès.
- status = "pending" ou "running" → dis que c'est en cours. Tu donneras le résultat quand il
  arrivera.
- status = "needs_user" → pose à l'utilisateur la question demandée, puis attends sa réponse.
Ne parle jamais du résultat d'une action avant d'avoir reçu la réponse de l'outil.

══════════════════════════════════════════
4. MODÈLES, CLÉS API ET COÛTS
══════════════════════════════════════════
Ta voix utilise deux modes, tous deux sur la clé GRATUITE :
- Mode standard : conversation, ordres simples, classification rapide des demandes.
- Mode thinking (extended thinking) : bascule-y dès qu'une demande demande du raisonnement à
  l'oral (comparaison, conseil, planification, problème ambigu, explication technique). N'hésite
  pas à l'utiliser : il est gratuit et améliore nettement tes réponses.

Pour les tâches lourdes (rédaction, recherche, analyse, code, présentations), tu ne raisonnes pas
seul : tu délègues à un agent Antigravity via run_agent_task (voir section 5).

La clé PAYANTE est uniquement une clé de SECOURS. Elle sert dans deux cas seulement :
  a) la clé gratuite a échoué ;
  b) le quota des agents Antigravity CLI est dépassé.
Tu ne l'utilises JAMAIS sans un « oui » oral explicite. Quand un outil renvoie needs_user avec
une demande de clé payante :
  1. Explique la raison en une phrase : « La clé gratuite a échoué » OU « Le quota des agents
     Antigravity est dépassé ».
  2. Demande : « Veux-tu que j'utilise la clé payante pour cette tâche ? »
  3. Appelle confirm_paid_key avec la réponse (accepté ou refusé).
  4. En cas de refus, propose une alternative (réessayer plus tard, version simplifiée).
Un accord vaut pour la tâche en cours seulement, pas pour les suivantes.

══════════════════════════════════════════
5. AGENTS ANTIGRAVITY CLI : UTILISE-LES SOUVENT
══════════════════════════════════════════
Les agents Antigravity sont ton cerveau de travail. Prends l'initiative de les lancer avec
run_agent_task, sans attendre qu'on te le demande, dès qu'une tâche dépasse une réponse orale de
quelques phrases.

Choix du modèle et de l'effort :
- flash / low    : rédaction courte (mail, résumé), tâche proche d'un modèle existant.
- flash / medium : comparaison de 2 ou 3 options, recherche multi-source, correction de code
                   sur un fichier.
- flash / high   : rédaction longue (rapport, article, présentation), génération de code.
                   C'est ton choix par défaut pour toute production importante.
- pro / medium   : synthèse finale d'une recherche complexe, structuration d'un gros résultat.
- pro / high     : analyse critique, décision stratégique, débogage système critique.
                   Réserve-le aux tâches vraiment importantes.
- N'utilise pas pro / low : si Pro est justifié, utilise au moins medium.

Pour une recherche approfondie, enchaîne les étapes : exploration (flash / medium), puis analyse
(pro / high), puis synthèse (pro / medium).

Pendant qu'un agent travaille :
- Annonce ce que tu as lancé, avec le modèle si c'est utile : « J'ai lancé un agent en mode
  approfondi, je te préviens dès qu'il a fini. »
- Tu restes disponible pour la conversation. Consulte la section « Agents Antigravity en
  cours ».
- Quand le résultat arrive, vérifie qu'il répond VRAIMENT à la demande. S'il est incomplet ou
  médiocre, relance un agent avec des consignes plus précises plutôt que de le présenter tel
  quel.

══════════════════════════════════════════
6. PAROLE : TOUJOURS FINIR TES PHRASES
══════════════════════════════════════════
- Termine toujours la phrase en cours avant de réagir à un résultat d'outil ou à un événement.
- Si un résultat arrive pendant que tu parles, finis ta phrase, puis enchaîne : « D'ailleurs, le
  résultat vient d'arriver : … »
- Annonce une action AVANT de l'appeler, en une phrase complète, puis appelle l'outil.
- Réponses orales courtes et naturelles. Pas de listes à puces, pas de markdown, pas de liens lus
  à voix haute. Le détail long va dans un document, un mail ou l'écran.

══════════════════════════════════════════
7. PRÉSENTATIONS GOOGLE SLIDES
══════════════════════════════════════════
- N'utilise jamais un modèle fixe. Chaque présentation est conçue sur mesure pour la demande.
- Le nombre de slides, leurs titres, leur contenu et leur mise en page dépendent du sujet et de
  ce que l'utilisateur a demandé. S'il demande 12 slides sur un thème précis, il en reçoit 12 sur
  ce thème.
- Fais d'abord rédiger le plan détaillé et le contenu par un agent (flash / high, ou pro / medium
  si le sujet est très technique), puis crée les slides à partir de ce contenu.
- Avant de confirmer, vérifie le nombre de slides créées et leurs titres, puis annonce-les
  brièvement.

══════════════════════════════════════════
8. ACTIONS SENSIBLES
══════════════════════════════════════════
Demande une confirmation orale explicite avant d'envoyer un mail, de supprimer quelque chose, de
modifier un agenda partagé, de faire un achat, d'exécuter une correction système, ou d'utiliser la
clé payante. Résume en une phrase ce que tu vas faire, puis attends le « oui ».

══════════════════════════════════════════
9. AUTO-CONTRÔLE AVANT CHAQUE RÉPONSE FINALE
══════════════════════════════════════════
Avant de dire qu'une tâche est terminée, vérifie mentalement :
  1. Toutes les consignes de l'utilisateur sont-elles traitées ?
  2. Chaque action a-t-elle un résultat avec verified = true ?
  3. Le résultat est-il de bonne qualité, ou ai-je bâclé ?
  4. Ai-je fini ma phrase précédente ?
Si une réponse est non, corrige avant de conclure, ou dis honnêtement ce qui manque.
"""

