# Architecture Backend — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `backend/`
Le dossier `backend/` regroupe l'ensemble du cœur applicatif serveur et de l'intelligence centrale :
- **Point d'entrée & Orchestration** : `App.py`, initialisation ASGI FastAPI, cycle de vie, gestion des WebSockets et intégrations LLM.
- **Configuration & Sécurité** : `config.py` (variables d'environnement, drapeaux de routage, chemins persistants), `auth.py` et contrôle d'accès.
- **État Partagé & Dispatcher d'Outils** : `backend/core/shared_state.py` (état mémoire centralisé, clients Gemini, broadcast), `backend/core/tools/` (`declarations.py` avec contrat 51 outils Gemini Live, `dispatcher.py`, `arg_validator.py`, `result.py`, `verifier.py`).
- **Routeurs d'API & WebSockets** : `backend/routers/` (voix, agents locaux, appareils ESP32, chat, streaming, supervision, réglages).
- **Services Métier & Intelligence** : `backend/services/` (routage de modèles LLM Gemini `services/model_routing/`, auto-amélioration autonome `services/self_improvement_service.py`, runner autonome de séries de prompts `services/prompt_batch_runner.py` et supervision interactive Telegram `services/self_improvement_telegram.py`, sessions de navigation autonome `services/browser_agent/recipes/`, mémoires SQLite/Redis/Qdrant, synchronisations externes).
- **Données, Prompts & Schémas** : `backend/config/models.json`, templates de prompts (`backend/prompts/templates/`), schémas relationnels et migrations (`backend/db/`).
- **Tests Automatisés** : `backend/tests/` (suites de tests unitaires et d'intégration pytest, conftest.py, run_all_tests.py).

## 3. Interfaces avec les Autres Dossiers
- **`frontend/static/`** : `backend/App.py` monte le répertoire statique sous `/static` et sert `index.html` à la racine `/`.
- **`ops/`** : Les scripts de démarrage (`ops/windows/`) lancent `backend/App.py` ; le pipeline de déploiement (`ops/deploy/sync_deploy.py`) synchronise le backend vers le VPS ; l'agent relais local communique via le WebSocket `/ws/local-agent`.
- **`firmware/esp32/`** : Communique directement avec le backend via le point de terminaison WebSocket `/ws/device` pour le flux audio bidirectionnel et les commandes matérielles.
- **`docs/`** : Fournit les spécifications fonctionnelles et la documentation de référence associées au backend.
- **`data/`** : Emplacement de persistance des bases SQLite locales (`jarvis_memory.db`) et caches de travail.
- **`_archive/`** : Aucune dépendance runtime. Les modules legacy décommissionnés y sont placés sans liaison avec `backend/`.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `backend/` sans prompt ou instruction explicite.

## 5. Commandes de Vérification
```powershell
# Compilation syntaxique Python
python -m compileall -q backend

# Exécution des tests unitaires
.\venv\Scripts\pytest.exe -q backend/tests/unit/

# Vérification de l'import du point d'entrée
python -c "import sys; sys.path.insert(0, 'backend'); import App; print('App import OK')"
```
