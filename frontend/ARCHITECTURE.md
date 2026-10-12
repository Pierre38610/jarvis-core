# Architecture Frontend — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `frontend/`
Le dossier `frontend/` héberge l'interface utilisateur web et la Progressive Web App (PWA) de Jarvis au sein du sous-dossier `frontend/static/` :
- **HUD & Interface Utilisateur** : `index.html` (structure HTML5 de l'interface, sidebar, statusbar, vues assistants, logs, supervision).
- **Logique Client & Temps Réel** : `app.js` (gestion des flux audio/WebSockets, rendu dynamique, notifications toast, interactions DOM).
- **Design System & Styles** : `style.css` (variables de thèmes, glassmorphism, animations, typographie Inter/JetBrains Mono, design adaptatif).
- **Manifeste PWA & Ressources Statiques** : `manifest.json`, icônes de l'application, graphismes et captures d'écran.

## 3. Interfaces avec les Autres Dossiers
- **`backend/`** : Les fichiers statiques de `frontend/static/` sont montés et exposés par `backend/App.py` via `/static` et `/`. L'application cliente consomme les API REST et les flux WebSocket fournis par `backend/routers/`.
- **`ops/`** : Les scripts de déploiement (`ops/deploy/sync_deploy.py`) transfèrent les assets statiques vers le serveur de production et contrôlent les versions de cache-busting.
- **`docs/`** : Contient les cartographies d'interface et spécifications UI/UX (ex. `UI_MAP.md`).
- **`firmware/`** et **`_archive/`** : Aucune interaction directe.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `frontend/` sans prompt ou instruction explicite.

## 5. Commandes de Vérification
```powershell
# Vérification de l'intégrité des fichiers essentiels du HUD
Test-Path frontend/static/index.html, frontend/static/app.js, frontend/static/style.css

# Vérification de l'absence de balises ou chemins statiques cassés
Select-String -Path frontend/static/index.html -Pattern 'href="|src="'
```
