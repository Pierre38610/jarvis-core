# CAPABILITIES LEDGER — Registre Factuel des Capacités Techniques de J.A.R.V.I.S.

Ce registre inventorie de manière exhaustive et factuelle les capacités déjà implémentées dans le code source de J.A.R.V.I.S. (`Pierre38610/jarvis-core`), ses limites techniques actuelles, l'historique des auto-améliorations appliquées et le backlog d'ingénierie.
**Règle d'or pour les agents de veille et d'auto-amélioration :** Toute fonctionnalité listée dans la Section 1 est DÉJÀ CODÉE et OPÉRATIONNELLE — il est strictement interdit de la reproposer comme nouvelle idée d'amélioration.

---

## 1. CAPACITÉS IMPLÉMENTÉES & OPÉRATIONNELLES (NE JAMAIS REPROPOSER)

### 1.1 Outils Gemini Live & Dispatcher (`backend/core/tools/declarations.py` & `backend/core/tools/dispatcher.py`)
Les **52 outils** suivants sont déjà déclarés, validés par `arg_validator.py` et routés dans `dispatcher.py` :
- **Système, Processus & Fichiers Locaux** :
  - `open_application` (`backend/core/tools/dispatcher.py`) : Ouverture d'applications locales Windows via l'agent relais (`ops/windows/jarvis_local_agent.py`).
  - `get_system_status` (`backend/core/tools/dispatcher.py`) : Télémétrie CPU, RAM, batterie, statut VPS et statut de connexion du PC local.
  - `manage_processes` (`backend/core/tools/dispatcher.py`) : Liste et arrêt sécurisé de processus lourds sur le PC.
  - `execute_system_command` (`backend/core/tools/dispatcher.py`) : Exécution de commandes système autorisées sur le PC local.
  - `take_screenshot_and_analyze` (`backend/core/tools/dispatcher.py`) : Capture d'écran locale et analyse multimodale Gemini Vision.
  - `create_local_file` (`backend/core/tools/dispatcher.py`) : Création de fichiers locaux dans l'espace autorisé.
  - `download_file` (`backend/core/tools/dispatcher.py`) : Téléchargement HTTP sécurisé avec confirmation utilisateur dans `downloads/`.
  - `list_workspace_files`, `read_workspace_file`, `search_workspace_files` (`backend/services/local_workspace_service.py`) : Exploration en lecture seule stricte du répertoire `_anti_gravity`.
- **Raisonnement Agentique, Recherche L1/L2/L3 & Auto-Amélioration** :
  - `ask_deep_reasoning` (`backend/services/reasoning_service.py`, `backend/google_antigravity.py`) : Délégation de raisonnement approfondi aux agents CLI Antigravity (`agy`).
  - `run_agentic_task` (`backend/services/agentic_runner.py`) : Exécution d'un agent `agy` en mode tâche (L1/L2) avec validation JSON et fallback API.
  - `run_l2_parallel_mission` (`backend/services/agentic_runner.py`) : Orchestration multi-agents L2 en parallèle dans des workspaces isolés avec `cross_check_l2_results`.
  - `self_improve` (`backend/services/self_improvement_service.py`, `backend/services/prompt_batch_runner.py`, `backend/services/weekly_improvement_watch.py`) : Auto-amélioration autonome en 3 modes (`propose` pour audit du code + recherche L2 + envoi de cartes Telegram avec boutons d'approbation ; `implement` pour coder un objectif dans un worktree Git isolé et ouvrir une PR ; `batch` pour exécuter un fichier `.md` de prompts de A à Z).
  - `search_web` (`backend/services/web_search.py`) : Recherche factuelle rapide L1 (< 2s) via DuckDuckGo / Tavily.
  - `fetch_web_page` (`backend/services/web_search.py`) : Extraction rapide du texte d'une URL.
  - `launch_deep_research` (`backend/services/deep_research_service.py`) : Recherche approfondie asynchrone L3 avec génération de rapport Markdown et deck Google Slides.
  - `get_active_task_status`, `guide_active_task`, `stop_current_action` (`backend/core/shared_state.py`) : Supervision temps réel des logs `ACTIVE_AGY_LOGS`, injection de directives à chaud et arrêt immédiat des tâches en cours.
- **Navigation Web & E-Commerce (`backend/services/browser_agent/`)** :
  - `browser_task` (`backend/services/browser_agent/antigravity_task_engine.py`) : Moteur de navigation autonome Playwright/CDP piloté par Antigravity.
  - `run_browser_task`, `interact_web_page`, `prepare_web_cart_or_checkout` (`backend/services/browser_agent/runner.py`) : Navigation web interactive, manipulation du DOM et préparation de panier e-commerce avec arrêt strict avant paiement (`payment_guard.py`).
  - `open_url` (`backend/core/tools/dispatcher.py`) : Ouverture directe d'URL sur le navigateur du PC de Pierre ou sur son smartphone.
- **Mobilité, Trains, Vols & Hébergements** :
  - `search_train_routes`, `monitor_train_Alert`, `open_train_booking` (`backend/services/train_service.py`) : Recherche d'itinéraires SNCF/SJ/Trainline, alertes TGV Max et ouverture de réservation.
  - `compare_flight_prices` (`backend/services/flight_service.py`) : Comparaison de vols multi-compagnies.
  - `search_accommodations` (`backend/services/accommodation_service.py`) : Recherche d'hôtels et logements.
  - `launch_phone_navigation` (`backend/services/navigation_service.py`) : Lancement d'itinéraire Google Maps sur le téléphone Android avec support des lieux enregistrés (`Maison`, `Travail`, `Salle de sport`).
- **Musique, Médias & E-Books** :
  - `control_spotify` (`backend/services/spotify_service.py`) : Contrôle complet Spotify Web API & Spotify Connect (lecture, pause, titres likés, volume, recherche, transfert d'appareil).
  - `play_music_deezer` (`backend/core/tools/dispatcher.py`) : Pilotage du lecteur Deezer via le relais local.
  - `play_video_stremio` (`backend/services/stremio_service.py`) : Lancement de films et séries sur Stremio.
  - `search_and_download_ebook`, `send_to_ereader`, `send_file_to_kindle`, `send_page_to_kindle` (`backend/services/ebook_service.py`, `backend/services/kindle_service.py`) : Recherche d'e-books (Anna's Archive / Z-Library / Gutenberg), conversion Calibre et envoi vers Kindle/Kobo.
- **Messagerie, E-mails, Telegram, Agenda & Productivité** :
  - `send_email`, `read_emails` (`backend/services/email_service.py`) : Envoi SMTP et lecture IMAP Gmail avec téléchargement automatique des pièces jointes dans `downloads/` et `data/prompt_batches/`.
  - `manage_calendar_event` (`backend/services/calendar_service.py`) : Lecture, création, modification et suppression d'événements Google Calendar.
  - `create_push_reminder` (`backend/services/reminder_service.py`) : Rappels programmés avec notification push / Telegram / e-mail.
  - `get_morning_briefing` (`backend/services/briefing_service.py`) : Briefing quotidien agrégé (météo, agenda, marchés, tâches).
  - `generate_presentation` (`backend/services/slides_service.py`) : Génération de présentations Google Slides / PowerPoint via n8n et agents.
  - `save_notion_entry`, `query_notion_knowledge` (`backend/services/notion_service.py`) : Intégration Notion complète.
- **Mémoire Hybride, Veille & Auto-Guérison SRE** :
  - `save_memory`, `search_memory`, `save_user_preference` (`backend/services/memory.py`) : Mémoire hybride PostgreSQL 16 + Qdrant (embeddings BAAI/bge-small 384d) + SQLite local.
  - `configure_watch_digest` (`backend/services/watch_digest_service.py`) : Configuration de veilles thématiques.
  - `check_console_errors` (`backend/services/console_monitor.py`) : Diagnostic des erreurs serveur temps réel.
  - `system_self_healing` (`backend/services/system_healing_service.py`) : Auto-guérison SRE en sandbox isolée avec déploiement Blue/Green et rollback en 1 clic.
  - `consult_jarvis_architecture` (`backend/services/architecture_service.py`) : Recherche dynamique dans `ARCHITECTURE_COMPLETE_JARVIS.md` et `CAPABILITIES_LEDGER.md`.
  - `confirm_paid_key` (`backend/services/key_gate.py`) : Consentement explicite pour l'usage ponctuel de la clé API Gemini payante.

### 1.2 Services Backend & Routeurs (`backend/services/` & `backend/routers/`)
- **Réception bidirectionnelle Telegram (`backend/services/self_improvement_telegram.py`)** : Polling `getUpdates`, téléchargement automatique des fichiers/documents envoyés par Pierre via `getFile` vers `downloads/` et `data/prompt_batches/`, et gestion des boutons inline signés HMAC (`si:app:...`, `bpa:res:...`).
- **Routage de modèles & Tiers cognitifs (`backend/services/model_routing/`, `backend/google_antigravity.py`)** : Sélection dynamique des modèles Antigravity (`gemini-4-argon-{low|medium|high}`, `gemini-3.8-flash-{low|medium|high}`, `claude-sonnet-5-5-{low|medium|high}`) et repli automatique sur erreur de quota 429.
- **Passerelle Vocale Gemini Live (`backend/routers/voice.py`, `backend/routers/device_voice.py`)** : Session full-duplex audio PCM 16kHz/24kHz avec `VoiceInjectionQueue`, `DeviceAudioPacer` (55ms) pour ESP32-S3, et synchronisation en direct de la présence du PC local (`local_agent_service.py`).

---

## 2. LIMITES TECHNIQUES CONNUES & GOULETS D'ÉTRANGLEMENT

1. **Captchas et anti-bots agressifs en navigation web (`backend/services/browser_agent/`)** : Les sites protégés par Cloudflare Turnstile ou DataDome peuvent bloquer le navigateur headless sur le VPS lorsque le relais Chrome du PC local de Pierre est hors-ligne.
2. **Latence de démarrage à froid des sous-processus `agy` (`backend/services/agentic_runner.py`)** : Chaque invocation CLI `agy` initialise un processus Node/Go complet (~2 à 4 secondes d'overhead avant le premier token).
3. **Granularité de l'observabilité des tokens et quotas Antigravity (`backend/services/model_routing/`)** : La détection de saturation de quota repose sur l'interception des erreurs 429/ResourceExhausted en sortie standard/erreur plutôt que sur une télémétrie prédictive du quota restant par fenêtre de 5 heures.
4. **Absence de connecteurs MCP spécialisés additionnels** : Seul Playwright est câblé en MCP ; des connecteurs MCP dédiés (GitHub natif, SQLite/PostgreSQL inspecteur en lecture seule, Docker/Systemd healthcheck) permettraient d'accélérer les diagnostics d'agents.
5. **Couverture des tests de bout en bout sur les callbacks d'édition Telegram (`si:edt:...`)** : Le flux de modification interactive d'une proposition sur Telegram avant exécution peut être enrichi avec la prise en charge d'une réponse textuelle directe (reply) de Pierre sur Telegram.

---

## 3. HISTORIQUE DES AUTO-AMÉLIORATIONS APPLIQUÉES

- **2026-10-24 — v5.99.2 (Résolution & Supervision Complète des Batchs de Prompts, Logs HUD & Télémétrie)** :
  - Refonte complète de `validate_safe_batch_path()` dans `backend/services/prompt_batch_runner.py` : détection des alias génériques ("un fichier .md", "latest", "batch"), exploration multi-dossiers (`prompts/Desktop`, `prompts/`, `data/prompt_batches/`, `downloads/`, racine du dépôt), sélection du fichier le plus récent contenant de véritables prompts Markdown.
  - Détection automatique du mode batch dans `backend/core/tools/dispatcher.py` même si le LLM omet `mode="batch"`, enregistrement immédiat du lot dans `ACTIVE_AGY_LOGS` et `active_task_controller`, capture et injection vocale explicite en cas d'erreur de lancement.
  - Enrichissement de `get_active_task_status` pour exposer l'état complet du dernier lot (progression, étape en cours, cause d'erreur, lien PR) au lieu d'un faux statut "en veille active".
  - Ajout de la route `/api/system/logs` dans `backend/routers/supervision.py` avec agrégation des logs de batchs et configuration standard de `logging.basicConfig(level=logging.INFO)` dans `backend/App.py`.

- **2026-10-24 — v5.99.1 (Résolution du Shadowing des Modules Racine VPS & Sécurisation de la Validation Globale)** :
  - Nettoyage et archivage automatique des fichiers racine obsolètes sur le VPS (`google_antigravity.py`, `config.py`, `auth.py`, `services/`, `core/`, `routers/`, `tests/`) dans `_archive/legacy_root/` pour supprimer le conflit de shadowing avec l'architecture modulaire `backend/`.
  - Encadrement de la validation globale finale dans `backend/services/prompt_batch_runner.py` avec `try/except subprocess.TimeoutExpired` et extension du délai d'exécution à 360 secondes avec `PYTHONPATH` strictement confiné au worktree.
  - Sécurisation du pipeline `ops/deploy/sync_deploy.py` avec étape automatisée de purge des fichiers obsolètes résiduels sur le VPS avant redémarrage du service systemd.

- **2026-10-24 — v5.99.0 (Auto-initialisation & Résilience des Worktrees Git pour Prompt Batch)** :
  - Ajout de `ensure_git_repository(repo_root)` dans `backend/services/self_improvement_service.py` pour auto-initialiser et configurer Git (`user.name`, `user.email`, remote `origin`, `git fetch origin main`, `git worktree prune`) si le dépôt est absent ou désynchronisé sur le VPS.
  - Sécurisation de `create_isolated_worktree()` avec `git worktree add -B` et suppression préventive de la branche locale pour éliminer les blocages de branches résiduelles.
  - Ajout du commit des étapes (`git add .` et `git commit`) dans `backend/services/prompt_batch_runner.py` pour chaque prompt validé et avant le push final.
  - Synchronisation automatique du dépôt Git VPS avec GitHub `main` dans le pipeline `ops/deploy/sync_deploy.py`.

- **2026-10-24 — v5.98.0 (Batch Correctif & Registre de Capacités)** :
  - Création de `CAPABILITIES_LEDGER.md` et ajout de `get_capabilities_ledger_summary()` + `verify_capability_not_already_implemented()` dans `backend/services/architecture_service.py`.
  - Refonte de `backend/services/weekly_improvement_watch.py` avec `generate_and_send_technical_improvements()`, audit du code réel, recherche technique L2 et filtre anti-coaching personnel/sportif.
  - Enrichissement de `self_improve` (`mode="propose" | "implement" | "batch"`) dans `declarations.py` et `dispatcher.py` + directive vocale dans `config.py`.
  - Réception automatique des fichiers envoyés sur Telegram (`self_improvement_telegram.py`), sauvegarde automatique des pièces jointes Gmail (`email_service.py`), correction du lanceur Windows (`ops/windows/start_agent_silent.vbs`) et alignement des drapeaux CLI `agy` v1.4.6 (`--model`, `--effort`).

---

## 4. BACKLOG TECHNIQUE & AXES D'INGÉNIERIE PRIORITAIRES

1. **Réponse textuelle Telegram pour l'action `✏️ Modifier` (`backend/services/self_improvement_telegram.py`)** : Permettre à Pierre de répondre directement au message Telegram d'une proposition après avoir cliqué sur `✏️ Modifier` pour ajuster le prompt avant de lancer `run_self_improvement`.
2. **Cache sémantique rapide pour les recherches L1/L2 répétées (`backend/services/web_search.py` & `backend/services/agentic_runner.py`)** : Mettre en cache Redis/SQLite (TTL 30 min) les synthèses de recherche identiques ou quasi-identiques pour réduire la latence à < 50ms et économiser le quota `agy`.
3. **Diagnostic proactif de santé des services VPS (`backend/services/supervision_service.py`)** : Vérifier périodiquement la latence de Redis, PostgreSQL, Qdrant et n8n avec rapport structuré dans `get_system_status`.
4. **Validation statique accrue des diffs d'auto-amélioration (`backend/services/self_improvement_service.py`)** : Détecter automatiquement dans `review_diff()` toute suppression accidentelle de fonction publique ou de route FastAPI existante avant d'autoriser le push Git.
