# Guide Opérationnel : Initialisation & Persistance de Session Google / Gemini sur VPS (P5)

> **J.A.R.V.I.S. - Stark Industries Intelligence Core**  
> *Module de Recherche Autonome L3 Deep Research*

---

## 1. Principes Fondamentaux de Sécurité Stark

L'automatisation Deep Research L3 repose sur l'interaction avec l'interface web officielle de **Google Gemini** (`https://gemini.google.com/app`) via Chrome DevTools Protocol (CDP) sur le port `9222`.

Conformément aux directives de sécurité absolues de J.A.R.V.I.S. :
- **AUCUNE automatisation de mot de passe ou de 2FA/MFA** : Jarvis ne sollicite, ne manipule et ne stocke jamais vos mots de passe Google, clés de sécurité ou codes d'authentification à deux facteurs.
- **AUCUNE extraction de secrets** : Les cookies, jetons de session et clés d'accès ne sont jamais affichés dans les logs, ni stockés dans Git, ni transmis sur le réseau non chiffré.
- **Profil persistant unique** : La session est initialisée **une seule fois** manuellement par l'opérateur (Pierre) dans le profil Chrome persistant (`JARVIS_VPS_CHROME_PROFILE`), puis réutilisée de façon transparente par le service d'arrière-plan.

---

## 2. Deux Méthodes d'Initialisation de la Session

Deux approches sécurisées permettent d'établir la session persistante sur le VPS :

```
                        ┌────────────────────────────────────────────────────────┐
                        │   Méthodes d'Initialisation de Session Google Gemini   │
                        └──────────────────────────┬─────────────────────────────┘
                                                   │
                   ┌───────────────────────────────┴───────────────────────────────┐
                   ▼                                                               ▼
        [ Méthode A : Directe ]                                         [ Méthode B : Migration ]
    Connexion directe sur VPS via VNC                                Copie sécurisée du profil PC local
  (Idéal si VNC/noVNC est configuré)                                (Recommandé : rapide et sans mot de passe VPS)
```

---

### Méthode A : Connexion Manuelle Directe sur le VPS via VNC / noVNC

Cette méthode consiste à démarrer temporairement un serveur d'affichage graphique sur le VPS pour ouvrir Google Chrome, vous identifier avec votre 2FA, puis refermer Chrome.

#### Étape A.1 — Arrêter le service Chrome d'arrière-plan
```bash
sudo systemctl stop jarvis-chrome
```

#### Étape A.2 — Démarrer un serveur X virtuel et VNC temporaire
Sur le VPS Oracle Cloud :
```bash
# 1. Démarrer Xvfb sur le display :99
Xvfb :99 -screen 0 1280x800x24 &

# 2. Lancer x11vnc sur le display :99
x11vnc -display :99 -nopw -listen 127.0.0.1 -xkb &
```

#### Étape A.3 — Ouvrir un tunnel SSH sécurisé depuis le PC local
Depuis votre terminal PC (PowerShell ou Bash) :
```powershell
# Redirige le port VNC 5900 du VPS vers votre machine locale
ssh -L 5900:127.0.0.1:5900 opc@158.178.206.213
```

#### Étape A.4 — Lancer Google Chrome avec le profil persistant
Sur le VPS :
```bash
DISPLAY=:99 /usr/bin/google-chrome-stable \
    --user-data-dir=/home/opc/.jarvis_chrome_profile \
    --no-first-run \
    --no-default-browser-check \
    https://gemini.google.com/app
```

#### Étape A.5 — Authentification manuelle
1. Ouvrez votre client VNC local (ex: TigerVNC, RealVNC ou UltraVNC) sur `localhost:5900`.
2. Saisissez votre compte Google, validez votre mot de passe et votre validation 2FA (invite téléphone / clé YubiKey).
3. Une fois sur l'interface de **Gemini** (`https://gemini.google.com/app`), fermez la fenêtre de Chrome.
4. Tuez les processus `x11vnc` et `Xvfb` temporaires.

#### Étape A.6 — Redémarrer le service d'arrière-plan
```bash
sudo systemctl start jarvis-chrome
```

---

### Méthode B : Migration Sécurisée du Profil depuis le PC Local (Recommandée)

Si vous disposez déjà d'un profil Chrome local connecté (`.jarvis_chrome_profile` sur votre PC généré via `scripts/setup_gemini_login.py`), vous pouvez le cloner directement sur le VPS.

> [!IMPORTANT]
> **Règles d'or de la migration :**
> 1. Arrêter **impérativement** le service `jarvis-chrome` sur le VPS avant d'écraser les fichiers.
> 2. Fermer Chrome sur le PC local pour libérer les verrous SQLite (`LOCK`, `SingletonLock`).
> 3. Restaurer les permissions strictes (`chown -R opc:opc` et `chmod 700`) sur le VPS.

#### Procédure Pas-à-Pas :

```bash
# ── Sur le VPS : Préparation et sauvegarde ──
# 1. Arrêter le service Chrome
sudo systemctl stop jarvis-chrome

# 2. Sauvegarder le profil actuel s'il existe
if [ -d "/home/opc/.jarvis_chrome_profile" ]; then
    cp -r /home/opc/.jarvis_chrome_profile "/home/opc/.jarvis_chrome_profile.bak_$(date +%s)"
fi
```

```powershell
# ── Sur le PC Local (PowerShell) : Transfert sécurisé ──
# 1. S'assurer que le profil local existe
cd C:\Users\pierr\Documents\_anti_gravity\jarvis\jarvis-core

# 2. Transférer le profil via SCP ou RSYNC (en excluant les caches volumineux inutiles)
scp -r .jarvis_chrome_profile opc@158.178.206.213:/home/opc/.jarvis_chrome_profile
```

```bash
# ── Sur le VPS : Réglage des permissions & Démarrage ──
# 1. Corriger les permissions et propriétaires
sudo chown -R opc:opc /home/opc/.jarvis_chrome_profile
sudo chmod -R 700 /home/opc/.jarvis_chrome_profile

# 2. Supprimer d'éventuels verrous orphelins résiduels
rm -f /home/opc/.jarvis_chrome_profile/SingletonLock
rm -f /home/opc/.jarvis_chrome_profile/SingletonCookie
rm -f /home/opc/.jarvis_chrome_profile/SingletonSocket

# 3. Démarrer et activer le service Chrome
sudo systemctl daemon-reload
sudo systemctl restart jarvis-chrome
```

---

## 3. Script de Diagnostic : `check_gemini_session.py`

Un outil dédié en ligne de commande permet de vérifier instantanément si la session Gemini est active et prête :

```bash
# Exécution sur le VPS
python3 scripts/check_gemini_session.py
```

### Options CLI :
- `python3 scripts/check_gemini_session.py --cdp-url http://127.0.0.1:9222` : cible une URL CDP spécifique.
- `python3 scripts/check_gemini_session.py --timeout 20` : ajuste le délai d'attente réseau.
- `python3 scripts/check_gemini_session.py --json` : sortie formatée en JSON pour l'automatisation.
- `python3 scripts/check_gemini_session.py --quiet` : mode silencieux (seul le code retour est produit).

### Codes de Retour (Exit Codes) :
| Code | Statut | Signification |
|:---:|:---|:---|
| **`0`** | `ACTIVE` | Session Google Gemini active, authentifiée et opérationnelle pour Deep Research. |
| **`1`** | `LOGIN_REQUIRED` | Page de connexion Google ou écran d'authentification détecté (action requise). |
| **`2`** | `UNAVAILABLE` / `ERROR` | Chrome CDP non joignable (service arrêté ou port 9222 inaccessible). |

---

## 4. Résilience de la Carte d'Interface : `data/gemini_ui_map.json`

Le fichier `data/gemini_ui_map.json` enregistre les coordonnées et sélecteurs de l'interface Google Gemini.

### Comportement Garanti :
1. **Création Vide ou Absence Tolérée** : Si le fichier `data/gemini_ui_map.json` est manquant ou contient `{"actions": {}}`, **le système ne plante jamais**.
2. **Repli Automatique Intégré** : La classe `UIMapManager` (`services/gemini_web_automator.py`) embarque un dictionnaire de repli `DEFAULT_UI_MAP` avec tous les sélecteurs ARIA, rôles accessibles et sélecteurs CSS à jour.
3. **Auto-Apprentissage & Correction de Dérive** : Dès que Jarvis interagit avec l'interface, les coordonnées réelles des boutons (`Deep Research`, `Champ prompt`, `Start research`, etc.) sont recalculées dynamiquement et persistées automatiquement dans `gemini_ui_map.json`.

---

## 5. Checklist Rapide de Validation

- [ ] Chrome CDP actif : `curl -s http://127.0.0.1:9222/json/version` retourne `HTTP 200`.
- [ ] Session active : `python3 scripts/check_gemini_session.py` retourne `[✔ SUCCÈS] Statut : ACTIVE` (exit code 0).
- [ ] Profil persistant protégé : `ls -ld /home/opc/.jarvis_chrome_profile` a les droits `drwx------ (700)` appartenant à `opc:opc`.
- [ ] Aucun secret committé : `.gitignore` contient bien `.jarvis_chrome_profile` et `.jarvis_shopping_profile`.
