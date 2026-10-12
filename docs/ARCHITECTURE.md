# Architecture Documentation & Workflows — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `docs/`
Le dossier `docs/` centralise l'ensemble de la documentation technique, des guides opérationnels et des spécifications de scénarios d'automatisation :
- **Guides & Procédures d'Exploitation** : `VPS_L3_ACTIONS_RESTANTES.md`, `VPS_L3_CHECKLIST.md`, `VPS_GOOGLE_SESSION_SETUP.md`.
- **Spécifications Fonctionnelles** : `BROWSER_AGENT_SPEC.md`, `N8N_GUIDE.md`.
- **Workflows Automatisés** : Définitions et exports de flux dans `docs/n8n_workflows/` (ex. `Jarvis_Multi_User_Unified_Engine.json`, `Jarvis_Web_Search_Extractor.json`).

## 3. Interfaces avec les Autres Dossiers
- **Racine** : Complète le document maître `ARCHITECTURE_COMPLETE_JARVIS.md` et le `README.md`.
- **`backend/`** : Décrit les endpoints, les services, les flux d'exécution et les formats d'échange.
- **`ops/`** : Référence les commandes d'administration serveur, configurations Docker et gestion de sessions.
- **`firmware/`** : Spécifie les protocoles de communication et consignes d'installation.
- **`_archive/`** : Aucune interaction directe.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `docs/` sans prompt ou instruction explicite. Les documents maîtres `ARCHITECTURE_COMPLETE_JARVIS.md`, `AGENTS.md` et `README.md` restent à la racine du projet.

## 5. Commandes de Vérification
```powershell
# Vérification de l'arborescence des documents et workflows
Get-ChildItem -Path docs -Recurse -File

# Vérification de l'absence de liens rompus dans la documentation
Select-String -Path docs/*.md -Pattern '\[.*\]\((?!http)(.*)\)'
```
