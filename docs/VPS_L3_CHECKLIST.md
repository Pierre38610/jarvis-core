# Checklist Opérationnelle VPS — Deep Research L3 Autonome (P8)

> **J.A.R.V.I.S. — Stark Industries Intelligence Core**  
> *Guide de déploiement, vérification pas-à-pas et validation manuelle du Moteur L3 sur VPS Cloud*

---

## 1. Vue d'Ensemble & Objectif

Ce document fournit la procédure complète, reproductible et sécurisée pour configurer, démarrer, vérifier et exploiter la recherche approfondie **Deep Research L3** directement sur le serveur VPS Oracle Cloud (`158.178.206.213`).

Grâce à cette architecture, J.A.R.V.I.S. exécute les recherches de niveau 3 en **totale autonomie sur le VPS** même lorsque le PC physique de l'utilisateur est éteint ou déconnecté. Les résultats sont présentés à l'écran si le PC est allumé, ou expédiés automatiquement par e-mail sécurisé à l'utilisateur.

```
                           ┌──────────────────────────────────────────────┐
                           │      Requête L3 (Voix / Texte / API)         │
                           └──────────────────────┬───────────────────────┘
                                                  │
                                                  ▼
                                ┌───────────────────────────────────┐
                                │ 1. Chrome VPS CDP (Port 9222)     │ ──► [Succès] ──► Livraison PC ou E-mail
                                └─────────────────┬─────────────────┘
                                                  │ (Échec / Non dispo)
                                                  ▼
                                ┌───────────────────────────────────┐
                                │ 2. Agent Local PC (si connecté)   │ ──► [Succès] ──► Affichage à l'écran
                                └─────────────────┬─────────────────┘
                                                  │ (PC déconnecté / Échec)
                                                  ▼
                                ┌───────────────────────────────────┐
                                │ 3. Map-Reduce Antigravity VPS     │ ──► [Succès] ──► E-mail / WebSocket
                                └───────────────────────────────────┘
```

---

## 2. Checklist Pas-à-Pas de Validation VPS

Suivez ces 7 étapes dans l'ordre pour valider ou dépanner l'installation sur le VPS.

---

### Étape 1 : Connexion SSH au VPS
Connectez-vous au serveur VPS Oracle Cloud :
```bash
ssh opc@158.178.206.213
```

Positionnez-vous dans le répertoire du projet :
```bash
cd /home/opc/jarvis-core
```

---

### Étape 2 : Installation & Dépendances (`setup_vps_chrome.sh`)
Exécutez le script d'installation idempotent pour installer Chromium/Google Chrome, Xvfb et Playwright :
```bash
# Rendre le script exécutable si besoin
chmod +x scripts/setup_vps_chrome.sh

# Lancement de l'installation automatisée
sudo ./scripts/setup_vps_chrome.sh
```

**Points vérifiés par le script :**
- Installation des paquets système (`google-chrome-stable` ou `chromium`, `xvfb`, polices, bibliothèques nss/atk).
- Installation des pilotes Playwright : `python3 -m playwright install chromium`.
- Création du profil persistant : `/home/opc/.jarvis_chrome_profile` avec permissions `700 (opc:opc)`.
- Installation et rechargement de l'unité systemd `/etc/systemd/system/jarvis-chrome.service`.

---

### Étape 3 : Configuration de l'Environnement (`.env`)
Vérifiez ou complétez le fichier `.env` sur le VPS :
```bash
nano .env
```

Assurez-vous que les variables suivantes sont définies (ajuster les chemins selon l'environnement) :
```bash
# ─── Configuration Chrome VPS & Deep Research L3 ──────────────────────────────
JARVIS_VPS_CHROME_PROFILE=/home/opc/.jarvis_chrome_profile
JARVIS_VPS_CHROME_CDP_URL=http://127.0.0.1:9222
JARVIS_VPS_CHROME_SERVICE_NAME=jarvis-chrome
JARVIS_VPS_CHROME_BIN=/usr/bin/google-chrome-stable
JARVIS_VPS_CHROME_HEADLESS=true
JARVIS_DEEP_RESEARCH_TIMEOUT_MINUTES=25
JARVIS_DEEP_RESEARCH_ENGINE=vps_chrome

# ─── Livraison E-mail Stark ──────────────────────────────────────────────────
SMTP_USER=pierrecassagnettes@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
EMAIL_FROM=pierrecassagnettes@gmail.com
```

> [!CAUTION]
> **Règle absolue de sécurité :** Ne jamais commiter le fichier `.env` ni afficher les mots de passe d'application dans les logs ou le chat.

---

### Étape 4 : Activation & Démarrage du Service Systemd
Démarrez et activez le service d'arrière-plan Chrome CDP :
```bash
# Recharger la configuration systemd
sudo systemctl daemon-reload

# Activer au démarrage du système et lancer immédiatement
sudo systemctl enable --now jarvis-chrome

# Vérifier le statut du service
sudo systemctl status jarvis-chrome
```

Le service doit être marqué **`active (running)`**.

---

### Étape 5 : Vérification Immédiate du Port CDP (9222)
Vérifiez que Chrome écoute sur le port CDP local `9222` :
```bash
curl -s http://127.0.0.1:9222/json/version
```

**Sortie attendue (JSON valide) :**
```json
{
   "Browser": "Chrome/130.0.6723.58",
   "Protocol-Version": "1.3",
   "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 ...",
   "V8-Version": "13.0.245.8",
   "WebKit-Version": "537.36 (@...)",
   "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."
}
```

Si la commande renvoie `Connection refused`, vérifiez les journaux du service :
```bash
journalctl -u jarvis-chrome -n 50 --no-pager
```

---

### Étape 6 : Vérification de la Session Google Gemini
Exécutez le script officiel de diagnostic de session :
```bash
python3 scripts/check_gemini_session.py
```

**Interprétation des résultats :**

| Code Retour | Affichage CLI | Statut | Action requise |
|:---:|:---|:---|:---|
| **`0`** | `[✔ SUCCÈS] Statut : ACTIVE` | **Opérationnel** | Aucune action, la session Gemini est prête pour L3. |
| **`1`** | `[✘ ATTENTION] Statut : LOGIN_REQUIRED` | **Action Requise** | Suivre la procédure de connexion dans `docs/VPS_GOOGLE_SESSION_SETUP.md`. |
| **`2`** | `[✘ ERREUR] Statut : UNAVAILABLE` | **Panne CDP** | Le service `jarvis-chrome` n'est pas démarré sur le port 9222. |

---

### Étape 7 : Lancement d'une Recherche Test & Consultation des Logs
Testez le cycle complet Deep Research avec un prompt d'essai :

```bash
# Lancement direct via Python CLI ou script de test
python3 -c "
import asyncio
from core.tools.dispatcher import dispatch_tool

async def test():
    res = await dispatch_tool(
        name='launch_deep_research',
        args={'consigne': 'Synthèse prospective batteries sodium-ion 2026', 'sync': True}
    )
    print('Status:', res.get('status'))
    print('Engine:', res.get('data', {}).get('engine'))
    print('Delivery:', res.get('data', {}).get('delivery'))

asyncio.run(test())
"
```

**Consultation des journaux d'activité en temps réel :**
```bash
# Suivre les logs de Chrome et Xvfb
journalctl -u jarvis-chrome -f

# Suivre les logs du noyau Jarvis
journalctl -u jarvis -f | grep -E "DeepResearch|CDP|L3Error"
```

---

## 3. Matrice de Dépannage Rapide (Troubleshooting)

| Symptôme | Cause Probable | Solution Rapide |
|:---|:---|:---|
| `curl: (7) Failed to connect to 127.0.0.1 port 9222` | Le service `jarvis-chrome` est arrêté ou en boucle d'erreur. | `sudo systemctl restart jarvis-chrome`<br>`journalctl -u jarvis-chrome -n 50` |
| `Statut : LOGIN_REQUIRED` | La session Google a expiré ou le profil est neuf. | Cloner `.jarvis_chrome_profile` depuis le PC via `scp` ou se connecter via VNC (voir `docs/VPS_GOOGLE_SESSION_SETUP.md`). |
| `SingletonLock` ou `Process already running` | Verrous orphelins suite à un arrêt forcé. | `sudo systemctl stop jarvis-chrome`<br>`rm -f /home/opc/.jarvis_chrome_profile/Singleton*`<br>`sudo systemctl start jarvis-chrome` |
| `Permission denied` sur `.jarvis_chrome_profile` | Propriétaire des fichiers modifié par une commande `root`. | `sudo chown -R opc:opc /home/opc/.jarvis_chrome_profile`<br>`sudo chmod -R 700 /home/opc/.jarvis_chrome_profile` |
| `E-mail non reçu` | Erreur d'authentification SMTP Gmail. | Vérifier `SMTP_USER` et le mot de passe d'application 16 caractères dans `.env`. |
| `Bascule automatique Map-Reduce` | Chrome VPS et PC local tous deux indisponibles. | Comportement de repli nominal et sécurisé : le rapport est produit par Antigravity CLI sans perte de service. |

---

## 4. Synthèse des Commandes Essentielles

```bash
# Redémarrage propre
sudo systemctl restart jarvis-chrome && sudo systemctl restart jarvis

# Statut synthétique
sudo systemctl status jarvis-chrome --no-pager
curl -s http://127.0.0.1:9222/json/version | head -n 8
python3 scripts/check_gemini_session.py

# Suivi direct des opérations
journalctl -u jarvis -u jarvis-chrome -f -n 50
```
