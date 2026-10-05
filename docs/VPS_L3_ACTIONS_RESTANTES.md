# Guide des Actions Manuelles Restantes — Deep Research L3 sur VPS

> **J.A.R.V.I.S. — Stark Industries Intelligence Core**  
> *Rapport de déploiement automatisé et guide pas-à-pas des étapes manuelles réservées à l'opérateur (Pierre)*

---

## 1. Bilan du Déploiement Automatique (Ce qui a été FAIT)

Toutes les étapes d'infrastructure, de dépendances et de configuration système sur le VPS Oracle Cloud (`158.178.206.213`) ont été exécutées et validées avec succès :

| Composant / Étape | Statut | Détail technique |
|:---|:---:|:---|
| **Connexion SSH VPS** | **✔ VALIDÉ** | Authentification automatique par clé `opc@158.178.206.213`. |
| **Paquets Système ARM64** | **✔ VALIDÉ** | Activation dépôt EPEL 9, installation de `Xvfb`, bibliothèques audio/graphiques et polices. |
| **Binaire Chromium** | **✔ VALIDÉ** | `Chromium 151.0.7922.173` (aarch64) et Playwright Chrome installés et opérationnels. |
| **Configuration `.env` VPS** | **✔ VALIDÉ** | Variables `JARVIS_VPS_CHROME_*`, timeouts L3 et configuration SMTP configurés. |
| **Service Systemd `jarvis-chrome`** | **✔ VALIDÉ** | Service d'arrière-plan installé, activé au démarrage (`systemctl enable`) et **ACTIF (`running`)**. |
| **Écoute CDP (Port 9222)** | **✔ VALIDÉ** | `http://127.0.0.1:9222/json/version` répond avec succès (WebSocket Debugger actif). |
| **Moteur de Repli Antigravity L3** | **✔ VALIDÉ** | Test de dispatch nominal validé avec succès sur le noyau VPS. |

---

## 2. Ce qu'il vous reste à faire Manuellement

### Pourquoi l'IA ne peut ABSOLUMENT PAS le faire :
1. **Protection Google & 2FA** : Google bloque systématiquement les connexions automatisées et exige des facteurs d'authentification humains (mot de passe maître + validation 2FA sur votre smartphone / invite Google Prompt / clé physique).
2. **Règle Absolue de Sécurité Stark** : J.A.R.V.I.S. et ses sous-agents ne manipulent, ne sollicitent et ne stockent **JAMAIS** vos mots de passe personnels ou vos codes d'authentification.

---

## 3. Procédure Recommandée en 2 Clics (Moins de 2 minutes)

Deux scripts prêts à l'emploi ont été créés pour vous éviter toute commande complexe.

```
   ┌─────────────────────────────┐        ┌─────────────────────────────┐        ┌─────────────────────────────┐
   │ 1. connect_gemini_web.bat   │        │ 2. sync_gemini_session_     │        │ 3. Deep Research L3 Prêt    │
   │    Connexion Google locale  │ ─────► │    to_vps.bat               │ ─────► │    Autonomie totale 24/7    │
   │    (Mot de passe + 2FA)     │        │    Migration auto vers VPS  │        │    sur le Cloud             │
   └─────────────────────────────┘        └─────────────────────────────┘        └─────────────────────────────┘
```

### Étape 1 : Connexion Unique sur votre PC Local
1. Dans le dossier `jarvis-core\scripts\`, double-cliquez sur :
   ```batch
   scripts\connect_gemini_web.bat
   ```
2. Une fenêtre officielle de Google Chrome s'ouvre sur `https://gemini.google.com/app` avec le profil isolé de Jarvis.
3. Connectez-vous à votre compte Google (saisissez votre mot de passe et validez votre 2FA sur votre téléphone).
4. Dès que vous êtes connecté et que l'interface de **Google Gemini** s'affiche : **fermez simplement la fenêtre de Chrome**.

---

### Étape 2 : Synchronisation 1-Clic vers le VPS
1. Dans le dossier `jarvis-core\scripts\`, double-cliquez sur :
   ```batch
   scripts\sync_gemini_session_to_vps.bat
   ```
2. Le script effectue automatiquement et en toute sécurité :
   - La compression du profil connecté (en excluant les caches volumineux inutiles).
   - Le transfert chiffré vers le serveur VPS Oracle.
   - L'application des permissions de sécurité strictes (`chmod 700`).
   - Le redémarrage transparent du service `jarvis-chrome`.
   - Le diagnostic immédiat confirmant le statut `[✔ SUCCÈS] ACTIVE`.

---

## 4. Méthode Alternative : Connexion Directe sur le VPS via VNC

Si vous préférez vous connecter directement sur le VPS sans passer par le PC local :

```bash
# 1. Arrêter le service Chrome sur le VPS
ssh opc@158.178.206.213 "sudo systemctl stop jarvis-chrome"

# 2. Lancer Xvfb et le serveur VNC sur le VPS
ssh opc@158.178.206.213 "Xvfb :99 -screen 0 1280x800x24 & x11vnc -display :99 -nopw -listen 127.0.0.1 &"

# 3. Ouvrir un tunnel SSH depuis votre PC
ssh -L 5900:127.0.0.1:5900 opc@158.178.206.213

# 4. Lancer Chrome sur le VPS (dans un second terminal SSH)
DISPLAY=:99 /usr/bin/chromium-browser --user-data-dir=/home/opc/.jarvis_chrome_profile https://gemini.google.com/app

# 5. Ouvrir votre client VNC local sur localhost:5900, vous connecter à Google, puis fermer Chrome.

# 6. Relancer le service Chrome
ssh opc@158.178.206.213 "sudo systemctl start jarvis-chrome"
```

---

## 5. Comment Vérifier que Tout est Opérationnel

Une fois l'étape 2 terminée, vous pouvez vérifier le statut à tout moment :

### Via la commande de diagnostic sur le VPS :
```bash
ssh opc@158.178.206.213 "cd /home/opc/jarvis-core && ./venv/bin/python scripts/check_gemini_session.py"
```
**Résultat attendu :**
```text
====================================================================
  ✦  J . A . R . V . I . S .   G E M I N I   S E S S I O N   C H E C K  ✦
====================================================================
Cible CDP : http://127.0.0.1:9222
Inspection de l'état d'authentification Google Gemini...
--------------------------------------------------------------------
[✔ SUCCÈS] Statut : ACTIVE
Message   : Session Google Gemini active et authentifiée.
====================================================================
```

### Via une recherche Deep Research réelle :
Dites simplement à J.A.R.V.I.S. (par voix ou texte) :
> *"Jarvis, lance une recherche approfondie sur l'état de l'art des supraconducteurs à température ambiante en 2026."*

J.A.R.V.I.S. pilotera Chromium sur le VPS en arrière-plan et vous expédiera le dossier complet de recherche par e-mail ou l'affichera directement sur votre écran HUD !
