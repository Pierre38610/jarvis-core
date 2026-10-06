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

## 3. Méthode Recommandée : Connexion Directe dans votre Navigateur Web (1-Clic)

Cette méthode est la plus simple et la plus fiable : elle ouvre Chromium du VPS directement dans votre navigateur web local habituel (Chrome/Edge/Brave).

```
   ┌───────────────────────────────────┐        ┌───────────────────────────────────┐
   │ 1. Double-clic sur :              │        │ 2. Authentification Google        │
   │    connect_gemini_vps_browser.bat │ ─────► │    dans votre navigateur          │ ─────► [✔ SUCCÈS] Prêt !
   │    (Ouvre l'interface Web VPS)    │        │    (Mot de passe + 2FA sur tél)   │
   └───────────────────────────────────┘        └───────────────────────────────────┘
```

### Marche à suivre :
1. Dans le dossier `jarvis-core\scripts\`, double-cliquez sur :
   ```batch
   scripts\connect_gemini_vps_browser.bat
   ```
2. Votre navigateur web par défaut s'ouvre automatiquement sur la page sécurisée de Chromium distant (`http://127.0.0.1:6080`).
3. Connectez-vous à votre compte Google sur l'interface de Gemini (entrez votre e-mail, mot de passe et validez votre 2FA sur votre smartphone).
4. Dès que vous êtes connecté et que l'interface de **Google Gemini** (`gemini.google.com`) est affichée :
   - Revenez sur la fenêtre de terminal noire.
   - Appuyez simplement sur la touche **[ENTRÉE]**.
5. Le script ferme automatiquement l'accès temporaire, démarre le service autonome `jarvis-chrome` et valide la session : `[✔ SUCCÈS] Statut : ACTIVE`.

---

## 4. Méthode Alternative : Synchronisation depuis le Profil PC Local

Si vous préférez synchroniser le profil Chrome de votre PC vers le VPS :

1. **Étape 1 (PC Local)** : Double-cliquez sur `scripts\connect_gemini_web.bat`, connectez-vous puis fermez Chrome.
2. **Étape 2 (Migration VPS)** : Double-cliquez sur `scripts\sync_gemini_session_to_vps.bat`. L'archivage ultra-optimisé s'exécute désormais en **0,5 seconde** (fichiers essentiels de moins de 500 Ko) et synchronise le VPS.

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
