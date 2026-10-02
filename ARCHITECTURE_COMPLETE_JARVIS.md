# ✦ ARCHITECTURE TECHNIQUE & CAPACITÉS SYSTÈME DE J.A.R.V.I.S. ✦
> **Stark Industries AI Assistant — Document d'Analyse Intégrale, Spécifications Systèmes & Guide de Référence IA**
> *Référentiel architectural exhaustif destiné à l'évaluation technique, au pilotage opérationnel, au benchmark et à l'ingénierie logicielle par agents IA.*
> *Dernière révision majeure : Version 5.37.0 — Canal vocal enceinte physique ESP32-S3 Waveshare AI Smart Speaker (`routers/device_voice.py`, `/ws/device`, `/api/device/*`), protocole WebSocket JSON+binaire PCM, wake word `wn9_jarvis_tts` (ESP-SR WakeNet 9), JWT `role=device`, présence Redis `jarvis:presence:device:<id>`, règle canal unique. Précédent : Routage Intelligent des Modèles Antigravity CLI (`services/model_routing/`, `config/models.json`), exécuteur agentique `services/agentic_runner.py`, gouvernance des clés `services/key_gate.py`, planificateur multi-étapes `services/task_planner.py` & audit anti-fausses-affirmations `services/turn_audit.py`.*

---

## 📑 TABLE DES MATIÈRES

1. [Vue d'Ensemble, Philosophie du Projet & Cartographie du Codebase](#1-vue-densemble-philosophie-du-projet--cartographie-du-codebase)
   - 1.1. Identité, Rôle & Relation d'Égal à Égal
   - 1.2. Paradigme Opérationnel & Principes Directeurs
   - 1.3. Les 5 Garde-Fous Inviolables
   - 1.4. Arborescence Complète du Dépôt & Rôle de Chaque Fichier
2. [Topologie d'Infrastructure & Déploiement Hybride](#2-topologie-dinfrastructure--déploiement-hybride)
   - 2.1. Schéma d'Architecture Globale
   - 2.2. Le Serveur Cloud Central (Oracle Cloud VPS ARM64)
   - 2.3. Le PC Physique Windows 11 & Rôle Exécutant
   - 2.4. Topologie Réseau, Tunnels Cloudflare & Résilience Réseau
   - 2.5. Pipeline de Déploiement Continu & Synchronisation (`sync_deploy.py`)
3. [Stack Logicielle, Conteneurs Docker & Persistance des Données](#3-stack-logicielle-conteneurs-docker--persistance-des-données)
   - 3.1. Matrice des Conteneurs Docker (`docker-compose.yml`)
   - 3.2. Mécanisme de Cache, Présence & Pub/Sub (`services/cache.py`)
   - 3.3. Schéma Relationnel PostgreSQL 16 (`db/schema.sql`)
   - 3.4. Moteur Vectoriel Qdrant & Embeddings Fastembed (`services/memory.py`)
   - 3.5. Mémoire Locale Structurée SQLite (`jarvis_memory.db`)
   - 3.6. Façade Unifiée de Mémoire Long-Terme (`services/unified_memory.py`)
   - 3.7. Service de Connaissance Approfondie du Profil de Candidature (`services/user_profile_service.py`)
4. [Architecture de Sécurité, Cryptographie & Gestion des Appareils](#4-architecture-de-sécurité-cryptographie--gestion-des-appareils)
   - 4.1. Moteur d'Authentification Cryptographique (`services/auth_service.py` & `auth.py`)
   - 4.2. Tokens JWT Signés (HMAC-SHA256) & Gestion des Clés Secrètes
   - 4.3. Registre des Terminaux & Empreintes Matérielles (`authorized_devices.json`)
   - 4.4. Protocole de Pairage QR Code Zero-Touch à Usage Unique
   - 4.5. Révocation Instantanée & Blacklist Redis
   - 4.6. Migration Rétrocompatible Transparente des Anciens Jetons
5. [Gouvernance des Modèles IA, Verrou Économique & Routage Cognitif en 3 Tiers](#5-gouvernance-des-modèles-ia-verrou-économique--routage-cognitif-en-3-tiers)
   - 5.1. Répartition Bimodale des Clés API (Gratuite vs Payante)
   - 5.2. Verrou Physique Applicatif & Double Consentement Oral
   - 5.3. Routage Cognitif Dynamique en 3 Paliers (Tiers 1, 2, 3)
   - 5.4. Mécanismes d'Arbitrage Ordonnés (`resolve_cognitive_tier`) & Télémétrie (`tier_routing_log`)
   - 5.5. Protocole de Résilience Quota-Aware & Dégradation Gracieuse (429)
   - 5.6. Routage Intelligent Antigravity CLI, Résilience Quota & Politique Vocale
6. [Le Moteur Vocal Temps Réel (Gemini Live Audio)](#6-le-moteur-vocal-temps-réel-gemini-live-audio)
   - 6.1. Protocole Audio Full-Duplex & Streaming PCM
   - 6.2. Assemblage Dynamique de l'Instruction Système & Contexte
   - 6.3. Modèles Vocaux Actifs & Permutation à Chaud
   - 6.4. Boucle de Traitement des Outils Asynchrone Non-Bloquante (< 300 ms)
   - 6.5. File d'Injection Vocale à Priorités FIFO (`VoiceInjectionQueue`)
   - 6.6. Jalons Vocaux Intermédiaires (`VOCAL_MILESTONE_THRESHOLD_SECONDS`)
   - 6.7. Règle d'Or de Canal Unique & Verrou d'Élocution Anti-Coupure
   - 6.8. Gestion des Interruptions (Barge-In) & Gating Micro
7. [L'Agent Relais Local PC Windows (`jarvis_local_agent`)](#7-lagent-relais-local-pc-windows-jarvis_local_agent)
   - 7.1. Problématique Résolue & Rôle Exécutant Physique
   - 7.2. Protocole WebSocket RPC & Reconnexion Résiliente
   - 7.3. Catalogue des 20 Actions Locales Supportées (Schémas & Paramètres)
   - 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
   - 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
   - 7.6. Télémétrie Matérielle Réelle (`psutil`)
8. [Catalogue Matriciel & Fiches des 49 Outils Unifiés (Function Calling)](#8-catalogue-matriciel--fiches-des-49-outils-unifiés-function-calling)
   - 8.1. Matrice Globale Exhaustive des 49 Outils Déclarés (Spécifications Exactes)
   - 8.2. Moteur Multi-Agents Antigravity CLI sur VPS (`ask_deep_reasoning`, `guide_active_task`, `stop_current_action`)
   - 8.3. Moteur Asynchrone Deep Research : Architecture à Double Moteur (Moteur A Browser Agent Gemini Web + Moteur B Map-Reduce VPS)
   - 8.4. Moteur Délibératif Système 2 Transverse (Les 8 Missions Agentiques Spécialisées)
   - 8.5. Interaction Web Autonome & Agent Navigateur Local (`browser_task`)
   - 8.6. Pôle Documentaire & Présentations Google Slides Polymorphes v1
   - 8.7. Mobilité & Système Ferroviaire Intelligent (France & Suède)
   - 8.8. Gestionnaire E-Book, Liseuses Physiques & Send to Kindle
   - 8.9. Contrôleur Média : Spotify & Stremio
   - 8.10. Suite de Communication & Messagerie Stark
   - 8.11. Système de Mémoire Hybride (SQLite, Qdrant & Fastembed)
   - 8.12. Télémétrie, Observabilité & Métriques des Outils (`services/metrics_service.py`)
   - 8.13. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
   - 8.14. Connaissance Architecturale Dynamique & Auto-évaluation
   - 8.15. SRE Autonome & Auto-Guérison Système (`services/system_healing_service.py`)
   - 8.16. Contrat Universel ToolResult & Moteur de Vérification d'Effet Réel (Zero Unverified Claims)
9. [Matrice des Endpoints API REST & Protocoles WebSockets](#9-matrice-des-endpoints-api-rest--protocoles-websockets)
   - 9.1. Endpoints HTTP / REST FastAPI (Exhaustif)
   - 9.2. Contrat WebSocket Audio Gemini Live (`/ws`)
   - 9.3. Contrat WebSocket Relais Agent Local PC (`/ws/local-agent`)
   - 9.4. Contrat & Intégration Spotify Web API (Connect & OAuth 2.0 PKCE)
10. [Cycle de Vie, Supervision & Événements des Sous-Agents](#10-cycle-de-vie-supervision--événements-des-sous-agents)
    - 10.1. Cycle de Vie d'un Sous-Agent
    - 10.2. Diffusion Temps Réel & Structure des Événements
    - 10.3. Visualisation dans le HUD Mobile
11. [Interface Utilisateur, PWA & HUD Mobile Stark Industries](#11-interface-utilisateur-pwa--hud-mobile-stark-industries)
    - 11.1. Principes Ergonomiques & Design System Cyberpunk
    - 11.2. Avatar Vectoriel SVG & Réacteur Arc Réactif
    - 11.3. Machine à États Visuelle
    - 11.4. Tiroirs, Modals Interactifs & Vues Dédiées
12. [Analyse Critique : Forces, Dette Technique & Pistes d'Amélioration](#12-analyse-critique--forces-dette-technique--pistes-damélioration)
    - 12.1. Forces Majeures de l'Architecture Actuelle
    - 12.2. Points d'Attention & Dette Technique
    - 12.3. Pistes d'Évolution Stratégique & Prochaines Étapes
13. [Guide du Développeur & Recettes d'Ingénierie pour Agents IA](#13-guide-du-développeur--recettes-dingénierie-pour-agents-ia)
    - 13.1. Invariants d'Implémentation & Style de Code
    - 13.2. Recette 1 : Déclarer & Implémenter un Nouvel Outil Gemini Live
    - 13.3. Recette 2 : Ajouter un Nouvel Endpoint REST ou WebSocket
    - 13.4. Recette 3 : Ajouter une Action RPC Local Agent PC
    - 13.5. Recette 4 : Créer une Nouvelle Mission Agentique Système 2
    - 13.6. Patterns d'Accès aux Bases de Données (PostgreSQL, SQLite, Qdrant, Redis)
    - 13.7. Glossaire des Variables d'Environnement (`.env` vs `config.py`)
    - 13.8. Exécution des Tests & Validation Hors-Ligne
    - 13.9. Procédure de Déploiement & Maintenance Cloud (`sync_deploy.py`)

---

## 1. VUE D'ENSEMBLE, PHILOSOPHIE DU PROJET & CARTOGRAPHIE DU CODEBASE

### 1.1. Identité, Rôle & Relation d'Égal à Égal
**J.A.R.V.I.S.** (*Just A Rather Very Intelligent System*) est un orchestrateur d'intelligence artificielle ubiquitaire de niveau exécutif conçu pour assister **Pierre Cassagnettes**. Directement inspiré de l'assistant emblématique de Tony Stark, le système incarne une philosophie de collaboration symbiotique :

- **Positionnement d'égal à égal** : Jarvis n'est pas un sous-fifre servile ni un simple chatbot passif. Il opère comme un binôme d'élite, brillant, direct, complice et pragmatique.
- **Éradication de la flatterie artificielle ("Zéro lèche-cul")** : Aucune courbette, aucun "À vos ordres", aucune flatterie feinte. Le tutoiement est naturel, fluide et constructif. Si une proposition de Pierre peut être optimisée ou simplifiée, Jarvis le lui signale immédiatement avec franchise.
- **Identité vocale humaine Aoede** : Restitution sonore féminine chaleureuse, vivante et spontanée fournie par l'API Gemini Live Audio. Aucune voix synthétique locale (pas de SAPI, eSpeak ou Windows SpeechSynth).
- **Éradication des tics verbaux & Amorces directes** : Interdiction formelle des préambules répétitifs ("C'est noté", "Très bien Pierre", "Entendu", "C'est compris", "En tant qu'IA"). Pour les actions immédiates, Jarvis commence directement par le verbe d'action ou donne le résultat final sans fioriture.

### 1.2. Paradigme Opérationnel & Principes Directeurs
1. **Agentique & Outillé** : Jarvis dispose de vraies mains numériques. Il pilote des navigateurs web (Cloud headless et Chrome local physique), lit et écrit sur le système de fichiers, inspecte du code, produit des applications complètes, manipule des bases de données et contrôle les périphériques locaux.
2. **Asynchrone & Non-Bloquant (< 300 ms)** : Pour toute tâche délibérative ou lourde, le dispatcheur renvoie immédiatement un accusé de réception préliminaire (`launched_in_background`). Jarvis confirme la prise en charge à l'oral en moins de 300 ms avec sa voix Aoede, tandis que la mission s'exécute en tâche de fond (`asyncio.create_task`). Pierre peut continuer à dialoguer librement sans gel du flux audio.
3. **Pilotable en Direct** : Grâce à l'outil `guide_active_task`, l'utilisateur peut réorienter ou enrichir en direct une tâche en cours d'exécution.
4. **Prise d'Initiative Proactive (Moteur Système 2)** : Dès qu'une requête nécessite de la réflexion, de l'optimisation fine ou un croisement de sources, Jarvis propose ou engage proactivement les agents Antigravity sur le VPS plutôt que de se contenter de réponses réflexes de surface.

### 1.3. Les 5 Garde-Fous Inviolables
```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          LES 5 GARDE-FOUS INVIOLABLES DE J.A.R.V.I.S.                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. IMPOSSIBILITÉ PHYSIQUE CLÉ PAYANTE : Verrouillage matériel côté serveur si non-coché│
│ 2. AUCUN PAIEMENT BANCAIRE AUTOMATIQUE : Arrêt strict avant l'étape de transaction     │
│ 3. AUCUN TÉLÉCHARGEMENT SANS ACCORD : Consentement oral explicite préalable requis     │
│ 4. INTERDICTION DE CODER À L'ORAL : Récitation de code bannie du flux audio vocal      │
│ 5. ARRÊT PHYSIQUE IMMÉDIAT : Interruption instantanée sur mot-clé ('stop', 'annule')   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```
1. **Impossibilité Physique sur la Clé Payante** : Si l'encoche n'est pas cochée par Pierre sur le HUD, la fonction `get_effective_paid_key()` renvoie `""`. Aucune requête payante n'est techniquement possible au niveau réseau/code.
2. **Zéro Paiement Bancaire Automatique** : Lors de commandes e-commerce (`prepare_web_cart_or_checkout`) ou de réservations ferroviaires (`open_train_booking` / `reserver_billet_train_local`), l'agent autonome `browser_task` (protégé par `services/browser_agent/guards.py`) recherche le produit ou trajet, remplit le panier et les formulaires, puis **s'arrête impérativement** avant l'étape de validation d'achat (`ready_for_user`) pour que Pierre valide lui-même son paiement physique.
3. **Accord Préalable Obligatoire sur Téléchargement** : Avant de rapatrier un fichier ou un livre (`download_file`), Jarvis énonce la provenance et la taille estimée et attend la validation orale explicite de Pierre.
4. **Interdiction de Réciter du Code à l'Oral** : Les flux audio vocaux ne doivent jamais être pollués par la lecture de syntaxes informatiques, backticks ou symboles. Tout développement est délégué aux agents Antigravity CLI sur le VPS.
5. **Arrêt Physique Immédiat (`stop_current_action`)** : Dès que Pierre prononce un ordre d'interruption ("arrête", "stop", "annule", "laisse tomber"), l'orchestrateur coupe physiquement les sous-processus et les tâches de fond sans délai.

### 1.4. Arborescence Complète du Dépôt & Rôle de Chaque Fichier
Pour permettre à tout agent d'ingénierie d'éditer le code avec la même précision qu'un accès direct au dépôt :

```
jarvis-core/
├── App.py                               # Point d'entrée FastAPI, montage /static & /downloads, routes d'auth (/api/auth*, /api/verify), startup/shutdown
├── App_backup_monolith.py               # Sauvegarde de l'ancien monolithe App.py (dette technique, non importé par le runtime)
├── config.py                            # Constantes, répertoires, clés FREE/PAID, encoche paid_key_authorized, MODEL_ROUTING_ENABLED
├── auth.py                              # Wrapper d'authentification légère et compatibilité
├── google_antigravity.py                # Implémentation racine du wrapper Antigravity CLI VPS (AntigravityAgent, resolve_cognitive_tier(_sync), verify_antigravity_cli_ready, resolve_cli_model_args, find_antigravity_binary)
├── model_registry.py                    # Shim racine du registre de découverte et catalogue des modèles (Gemini / Claude)
├── model_router.py                      # Shim racine du routeur intelligent de modèles (select_model)
├── fallback_handler.py                  # Shim racine du gestionnaire de repli résilient quota (execute_with_fallback)
├── prompt_builder.py                    # Shim racine du constructeur de prompts adaptés et parseur JSON tolérant
├── AGENTS.md                            # Charte générale et règles obligatoires pour tout agent autonome Antigravity CLI
├── jarvis_local_agent.py                # Agent client WebSocket s'exécutant sur le PC Windows 11 (20 actions physiques, Chrome CDP, Spotify Desktop, Stremio)
├── local_browser_actions.py             # Pont CDP Playwright côté PC (port 9222), balisage DOM data-jarvis-id, exécution d'actions et screenshots
├── tunnel_launcher.py                   # Gestionnaire du tunnel Cloudflare Zero Trust, fallback Quick Tunnel et LAN Wi-Fi
├── sync_deploy.py                       # Pipeline automatisé : Git commit/push + archive in-memory tar.gz + SFTP + relance systemd VPS
├── docker-compose.yml                   # Définition conteneurs Redis 7, Postgres 16, Qdrant et n8n (bound sur 127.0.0.1)
├── PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md # Dossier complet académique et pro de Pierre (Phelma SICOM, Scintil, Teem, Suède)
├── ARCHITECTURE_COMPLETE_JARVIS.md      # Le présent référentiel architectural complet maître
├── requirements.txt / pytest.ini / README.md
├── start_jarvis.bat / start_local_agent.bat / stop_agent.bat / view_logs.bat / sync_deploy.bat / open_n8n_tunnel.bat
├── start_agent_silent.vbs               # Lancement invisible du relais PC via wscript.exe (zéro console)
├── install_autostart.bat / uninstall_autostart.bat / install_antigravity_arm64.sh / cloudflared.exe
├── authorized_devices.json / qr_tickets.json / jarvis_memory.db / tunnel_url.txt / jarvis_agent.log
├── scripts_tmp_fix_slides*.py / scripts_tmp_append_tests.py # Scripts jetables historiques (dette technique, purge recommandée)
├── .agents/rules/                       # Règles agents locales (AGENTS.md, architecture-knowledge-and-sync.md, git-sync.md)
│
├── config/
│   └── models.json                      # Catalogue déclaratif (5 modèles Gemini/Claude) + routing_rules + fallback_chain + cooldown 300s
│
├── prompts/
│   └── templates/                       # Templates modulaires par complexité (simple.txt, medium.txt, complex.txt, code.txt)
│
├── core/                                # Cœur applicatif transverse
│   ├── shared_state.py                  # État global partagé, clients Gemini FREE/PAID, active_task_controller, verrou d'élocution, broadcast
│   └── tools/
│       ├── declarations.py              # 49 FunctionDeclarations Google GenAI (schémas, descriptions ASR, behavior BLOCKING/NON_BLOCKING)
│       ├── dispatcher.py                # Routeur central d'exécution (49 outils + alias), boucle browser_task, métriques, consentement payant
│       ├── arg_validator.py             # Validation stricte des arguments (validate_tool_arguments) & rappel multi-actions
│       ├── result.py                    # Contrat canonique ToolResult (done/failed/started/partial/needs_user) + normalize_result
│       └── verifier.py                  # Vérifications post-exécution d'effet réel (email, slides, xlsx, download, process, agenda, mémoire, navigateur)
│
├── routers/                             # Routeurs modulaires FastAPI (/api/* et /ws/*)
│   ├── voice.py                         # WebSocket /ws : session bidirectionnelle Gemini Live Audio, streaming PCM et injection client
│   ├── local_agent.py                   # WebSocket /ws/local-agent et GET /api/local-agent/status (relais PC physique)
│   ├── chat.py                          # GET/POST /api/chat/* : messagerie multimodale écrite et vision Gemini 3.8 Flash
│   ├── spotify.py                       # GET/POST /api/media/spotify/* : OAuth PKCE, playback, devices, migration Deezer->Spotify
│   ├── browser.py                       # /api/browser/*, /api/downloads, /api/emails/* : gestion documents, Kindle et courriels
│   ├── supervision.py                   # /api/supervision/*, /api/task/* : métriques, fenêtres actives, patches SRE, directives
│   ├── settings.py                      # /api/live-model, /api/settings/paid-key, /api/paid-consent, /api/tunnel-info
│   ├── briefing.py                      # /api/briefing/*, /api/agenda/*, /api/device/location : météo, rendez-vous, géolocalisation
│   └── transport.py                     # /api/train/* : recherche de trains, surveillance proactive n8n, alertes et résa multi-onglets
│
├── services/                            # Services métier d'arrière-plan et d'intégration
│   ├── model_routing/                   # Module de routage intelligent et résilience de quota pour Antigravity CLI
│   │   ├── model_registry.py            # Registre dynamique avec cache TTL (1h) et cascade CLI -> Config -> Liste par défaut
│   │   ├── model_router.py              # Sélection optimale du modèle et niveau d'effort selon type, complexité et contexte
│   │   ├── fallback_handler.py          # Cascade de repli Claude -> Gemini CLI -> API PAID, gestion cooldowns et détection 429
│   │   └── prompt_builder.py            # Formatage adapté (XML pour Claude, Markdown pour Gemini) et parseur JSON tolérant
│   ├── browser_agent/                   # Moteur de navigation autonome piloté par Antigravity CLI (S1/S2)
│   │   ├── loop.py                      # Boucle de navigation S2 (run_browser_task, cycle snapshot-decide-act, handoff, verifier)
│   │   ├── cli_brain.py                 # Cerveau décisionnel S4 et vérificateur s'appuyant sur les agents CLI agy
│   │   ├── guards.py                    # Garde-fous de sécurité S5 (anti-paiement strict, interdiction données bancaires/mots de passe)
│   │   ├── site_memory.py               # Persistance atomique par domaine des parcours de navigation réussis (S6)
│   │   └── recipes/                     # Recettes de navigation spécialisées (cart.md, train.md, gemini_deep_research.md)
│   ├── deep_research_service.py         # Moteur B Deep Research : pipeline Map-Reduce VPS (spec, MAP 3 ouvriers, REDUCE, Quality Gate)
│   ├── agentic_dispatcher.py            # Orchestrateur Système 2 universel : 8 missions spécialisées (transport, excel, healing, etc.)
│   ├── agentic_runner.py                # Exécuteur agy : prompt JSON strict, validation de schéma, retry, repli Gemini payant via key_gate
│   ├── antigravity_models.py            # Modèles & efforts agy (MODEL_FLASH/MODEL_PRO, validate_model_and_effort, choose_model_and_effort)
│   ├── antigravity_prompts.py           # Prompts de rôle Antigravity, exigences de sortie JSON et prompt de retry
│   ├── key_gate.py                      # Gouvernance FREE/PAID : consentement par tâche, échec qualifié, action en attente, get_key()
│   ├── llm_router.py                    # Routeur LLM unifié (Live standard/thinking sur clé FREE, bascule PAID via key_gate)
│   ├── live_mode_policy.py              # Politique voice_mode (thinking vs standard), hystérésis, détection besoin agentique, log tier routing
│   ├── task_planner.py                  # Planificateur multi-étapes (needs_planning, decompose, get_plan_status, mark_plan_step, HUD)
│   ├── turn_audit.py                    # Audit de tour : détection de fausses affirmations, contexte plan/sous-agents injecté au prompt
│   ├── gemini_web_automator.py          # Automatisation de l'UI Gemini Web (Moteur A Deep Research via Chrome local)
│   ├── chat_service.py                  # Messagerie écrite multimodale (clients FREE/PAID, consentement key_gate)
│   ├── system_healing_service.py        # SRE autonome : analyse RCA, tests sandbox isolés, auto-tests, Blue/Green releases, symlink
│   ├── metrics_service.py               # Observabilité : enregistrement asynchrone Postgres/RAM des appels d'outils, latences, tiers
│   ├── browser_service.py               # Navigation Playwright headless VPS et local Chrome CDP, recherche DuckDuckGo, Send to Kindle
│   ├── download_service.py              # Téléchargement fichiers/ebooks (Anna's Archive), validation EPUB, détection liseuses USB
│   ├── email_service.py                 # Envoi SMTP Stark HTML et réception IMAP Gmail avec résolution floue des pièces jointes
│   ├── slides_service.py                # Générateur & modificateur de présentations Google Slides (7 layouts 16:9, conformité API v1)
│   ├── transport_service.py             # Calcul d'itinéraires ferroviaires France/Suède, découpage multi-segments, deep links Omio
│   ├── briefing_service.py              # Compilation morning briefing à 6h45, météo Open-Meteo, alertes et push Telegram
│   ├── spotify_service.py               # Spotify Web API (OAuth PKCE, playback, devices, vérification post-action /me/player)
│   ├── deezer_migration_service.py      # Migration Deezer -> Spotify (ISRC puis fuzzy matching, scoring de confiance, rapports)
│   ├── media_service.py                 # Routage des commandes audio Deezer et vidéo Stremio (URI protocol)
│   ├── automation.py                    # Webhooks n8n génériques, export tableur XLSX et intégration Notion
│   ├── user_profile_service.py          # Hot-reload de PROFIL_CANDIDATURE... via mtime, synchro SQLite et injection Live context
│   ├── unified_memory.py                # Façade unifiée : déduplication SQLite (profil) vs vectoriel Qdrant (souvenirs)
│   ├── memory.py                        # Client vectoriel Qdrant & modèle local fastembed BAAI/bge-small-en-v1.5 (384 dim)
│   ├── memory_service.py                # Service de persistance relationnelle des conversations et souvenirs
│   ├── cache.py                         # Cache Redis asynchrone, TTL, présence équipements et fallback mémoire vive dégradé
│   ├── auth_service.py                  # Cryptographie JWT HMAC-SHA256, tickets QR uniques 300s, révocation Redis et migration
│   ├── local_agent_service.py           # Client RPC émettant les requêtes vers jarvis_local_agent.py via WebSocket
│   ├── supervision_service.py           # Agrégateur d'état système, sous-agents, métriques et fenêtres actives
│   ├── console_monitor.py               # Capture continue des logs et exceptions Python avec suggestions de diagnostics
│   ├── reasoning_service.py             # Pipeline d'agents Antigravity CLI et classification cognitive LLM légère Tier 1
│   ├── google_antigravity.py            # Façade de ré-export agy (google_antigravity racine + antigravity_models + agentic_runner) ; l'implémentation réelle du wrapper est à la racine
│   ├── system_service.py                # Télémétrie système serveur/local et ouverture d'applications
│   ├── voice_injection_queue.py         # File d'attente à priorités FIFO pour injection vocale sans collision (Aoede)
│   ├── workspace_service.py             # Exploration et lecture seule stricte des projets locaux _anti_gravity (anti-traversal, filtres)
│   └── architecture_service.py          # Hot-reload de ARCHITECTURE_COMPLETE_JARVIS.md et outil live query_jarvis_architecture
│
├── scripts/                             # install_agent_rules.py, quality_report.py, deploy_n8n_vps.py, setup_*.py, show_qr.py, try_browser_task.py, *.bat
│
├── db/
│   ├── schema.sql                       # Schéma PostgreSQL (conversations, memories, tier_routing_log, tool_call_metrics, patches)
│   ├── spotify_schema.sql               # Tables SQLite des tokens OAuth Spotify
│   └── migrations/001_create_tool_call_metrics.sql
├── docs/                                # BROWSER_AGENT_SPEC.md, N8N_GUIDE.md, n8n_workflows/*.json (documents_suite, time_and_briefing, train_monitoring)
├── static/                              # HUD PWA Stark Industries (index.html, app.js, style.css, manifest.json, SVG/PNG, latest_screenshot.jpg, tunnel_url.json)
├── data/                                # site_memory/<domain>.json (parcours web réussis), gemini_ui_map.json, migration_reports/
└── tests/                               # 34 modules pytest racine + tests/unit/ (12) + tests/e2e/ (1), conftest.py, run_all_tests.py (génère `tests/RAPPORT_TESTS_JARVIS.txt`, dernière campagne le 27/09/2026 — 19 modules/services vérifiés), dossiers scratch : tests/scratch_healing/, tests/_test_scratch/)
```

---

## 2. TOPOLOGIE D'INFRASTRUCTURE & DÉPLOIEMENT HYBRIDE

### 2.1. Schéma d'Architecture Globale

```
                         ┌────────────────────────────────────────────────────────┐
                         │                    TERMINAUX CLIENTS                   │
                         │    • Smartphone PWA (HUD Mobile / Audio Full-Duplex)   │
                         │    • Navigateur Desktop (Chrome / Dashboard Stark)     │
                         └───────────────────────────┬────────────────────────────┘
                                                     │ HTTPS / WSS
                                                     ▼
                         ┌────────────────────────────────────────────────────────┐
                         │      PASSERELLE D'ACCÈS CLOUDFLARE ZERO TRUST          │
                         │       Domaine : jarvis.signalcraftapps.com             │
                         │      (Tunnel HTTP/2 multiplexé sortant, port 7844)     │
                         └───────────────────────────┬────────────────────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SERVEUR CLOUD CENTRAL (ORACLE CLOUD VPS)                                │
│                          Instance Ubuntu ARM64 (Ampere A1 - 4 OCPU, 24 Go RAM)                         │
│                                           IP : 158.178.206.213                                          │
│                                                                                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              FastAPI Backend Core (App.py - Port 8000)                             │  │
│  │   • Endpoint WebSocket Gemini Live (/ws)            • Routage des requêtes REST (/api/*)          │  │
│  │   • Supervision & Notifications (/ws/supervision)   • Relais Agent Local PC (/ws/local-agent)     │  │
│  │   • Moteur Délibératif Antigravity CLI VPS          • Moteur Deep Research Map-Reduce             │  │
│  └──────────────────┬─────────────────────────────┬────────────────────────────┬─────────────────────┘  │
│                     │                             │                            │                        │
│                     ▼                             ▼                            ▼                        │
│          ┌──────────────────────┐      ┌──────────────────────┐     ┌──────────────────────┐            │
│          │    REDIS 7 (Docker)  │      │ POSTGRES 16 (Docker) │     │    QDRANT (Docker)   │            │
│          │    127.0.0.1:6379    │      │    127.0.0.1:5432    │     │    127.0.0.1:6333    │            │
│          │  Cache, TTL, Pub/Sub │      │ Historique sessions  │     │ Base vectorielle RAG │            │
│          └──────────────────────┘      └──────────────────────┘     └──────────────────────┘            │
│                     │                                                                                   │
│                     ▼                                                                                   │
│          ┌──────────────────────┐                                                                       │
│          │     N8N COMMUNITY    │  (Port 5678 - Montage volume /home/opc/jarvis-core/downloads)         │
│          │ Workflows documents, │  (Slides polymorphes, tableurs xlsx, surveillance trains Trafikverket)│
│          │ agenda et calendrier │                                                                       │
│          └──────────────────────┘                                                                       │
└────────────────────────────────────────────────────▲────────────────────────────────────────────────────┘
                                                     │
                                                     │ WebSocket Sécurisé (/ws/local-agent)
                                                     │ Heartbeat & Télémétrie Hardware
                                                     │
┌────────────────────────────────────────────────────┴────────────────────────────────────────────────────┐
│                                     PC PERSONNEL WINDOWS 11 (LOCAL)                                     │
│                                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         Agent Relais Local (jarvis_local_agent.py)                              │   │
│   │   • Lancement d'applications physiques (VS Code, VLC, Stremio, Notepad, Calculatrice, Terminal) │   │
│   │   • Contrôle Chrome CDP persistant port 9222 (profil réel, cookies Google/Amazon, sessions)    │   │
│   │   • Télémétrie matérielle physique (CPU réel, RAM réelle, état batterie, processus actifs)     │   │
│   │   • Extraction sécurisée de fichiers locaux pour pièces jointes (fetch_file base64)            │   │
│   └──────────────────┬──────────────────────────────────────────────┬───────────────────────────────┘   │
│                      │                                              │                                   │
│                      ▼                                              ▼                                   │
│           ┌──────────────────────┐                       ┌──────────────────────┐                       │
│           │   SPOTIFY CONNECT    │                       │ LISEUSES PHYSIQUES   │                       │
│           │ Web API + PKCE VPS   │                       │ Kindle / Kobo via USB│                       │
│           │ Multi-Devices Connect│                       │ Montages lecteurs    │                       │
│           └──────────────────────┘                       └──────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Le Serveur Cloud Central (Oracle Cloud VPS)
- **Hébergement** : Instance Oracle Cloud Infrastructure (OCI) Always Free tier.
- **Ressources matérielles** : Architecture ARM64 (`aarch64` Ampere Altra), 4 cœurs virtuels OCPU, 24 Go de mémoire vive physique, stockage SSD NVMe.
- **Système d'exploitation & Emplacement** : Ubuntu 22.04 LTS, répertoire applicatif `/home/opc/jarvis-core/`.
- **Adresse IP publique** : `158.178.206.213`.
- **Service systemd** : Géré via `jarvis.service` (`sudo systemctl restart jarvis`, logs : `journalctl -u jarvis -f`).

### 2.3. Le PC Physique Windows 11 & Rôle Exécutant
- **Rôle fonctionnel** : Exécutant matériel de bureau. Ne disposant d'aucun affichage graphique direct sur le VPS Cloud, toute opération nécessitant une interface visuelle à l'écran (ouvrir VS Code, manipuler Google Chrome avec sessions authentifiées, lancer un film dans Stremio, lancer Spotify Desktop ou détecter une liseuse branchée en USB) est déléguée à l'agent local.

### 2.4. Topologie Réseau, Tunnels Cloudflare & Résilience Réseau
Le système utilise `tunnel_launcher.py` pour assurer une accessibilité permanente sans ouvrir le moindre port d'entrée sur la box ou le routeur :
1. **Tunnel Principal (Cloudflare Zero Trust)** : Établi via `cloudflared.exe` avec jeton d'authentification (`CLOUDFLARE_TUNNEL_TOKEN`). Multiplexe le trafic HTTPS/WSS sortant vers `jarvis.signalcraftapps.com` (port 7844).
2. **Repli 1 (Quick Tunnel)** : En cas d'indisponibilité, repli dynamique instantané sur un sous-domaine `*.trycloudflare.com`.
3. **Repli 2 (Wi-Fi Direct LAN)** : Détection intelligente de l'IPv4 active via `ipconfig /all`, avec filtrage strict des adaptateurs virtuels (Cisco AnyConnect, TAP, VPNs).
4. **Vérification de Joignabilité** : Requête HTTP de sonde réelle pour éliminer l'erreur 1033. URLs validées écrites dans `tunnel_url.txt` et `static/tunnel_url.json`.

### 2.5. Pipeline de Déploiement Continu & Synchronisation (`sync_deploy.py`)
Déclenché via `.\venv\Scripts\python.exe sync_deploy.py -m "Description"` (ou `.\sync_deploy.bat "Description"`) :
1. **Git Commit & Push** : `git add .`, commit horodaté et `git push origin main`.
2. **Archive In-Memory** : Compression `tar.gz` en mémoire vive (`io.BytesIO`) excluant `.git`, `venv`, logs, caches pytest, profils Chrome.
3. **SFTP SSH Ed25519** : Liaison directe vers `158.178.206.213` via `paramiko`.
4. **Extraction & Relance sans Coupure** : Décompression dans `/home/opc/jarvis-core`, `sudo systemctl restart jarvis` et vérification du statut actif.

---

## 3. STACK LOGICIELLE, CONTENEURS DOCKER & PERSISTANCE DES DONNÉES

### 3.1. Matrice des Conteneurs Docker (`docker-compose.yml`)

| Service | Image Conteneur | Port Local | Volumes Persistants | Rôle & Spécificités Techniques |
| :--- | :--- | :--- | :--- | :--- |
| **Redis 7** | `redis:alpine` | `127.0.0.1:6379` | `redis_data:/data` | Cache clé/valeur, TTL, présence appareils (`jarvis:presence:*`), Pub/Sub, blacklist JWT. Max 2 Go LRU. |
| **PostgreSQL 16**| `postgres:16-alpine` | `127.0.0.1:5432` | `postgres_data:/var/lib/postgresql/data` | Persistance relationnelle conversations, souvenirs, logs de routage, métriques d'outils et patches SRE. |
| **Qdrant** | `qdrant/qdrant:latest` | `127.0.0.1:6333` | `qdrant_data:/qdrant/storage` | Moteur vectoriel pour recherche sémantique RAG (Distance Cosinus, collection `jarvis_memories`, 384 dim). |
| **n8n Community**| `n8nio/n8n:latest` | `127.0.0.1:5678` | `n8n_data:/home/node/.n8n`<br>`/home/opc/jarvis-core/downloads` | Moteur no-code. Montage direct du volume téléchargements pour générer des fichiers XLSX et interagir avec Slides. |

*Règle stricte : Tous les conteneurs sont liés sur `127.0.0.1`. Aucun port n'est exposé sur l'interface publique.*

### 3.2. Mécanisme de Cache, Présence & Pub/Sub (`services/cache.py`)
- **Sérialisation JSON Transparente** : Stockage et désérialisation de structures complexes avec TTL.
- **Heartbeat & Présence** : Enregistrement de l'état PC et smartphones sous `jarvis:presence:{device_name}` (TTL 300 s).
- **Pub/Sub Temps Réel** : Canal `jarvis:events:presence` diffusant les changements d'état matériel.
- **Mode Dégradé Local en RAM** : Si Redis est arrêté, bascule instantanée sur un dictionnaire Python en mémoire vive.

### 3.3. Schéma Relationnel PostgreSQL 16 (`db/schema.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS conversations (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT        NOT NULL DEFAULT '',
    tags        TEXT[]      DEFAULT '{}'
);

CREATE TYPE memory_category AS ENUM (
    'préférence', 'fait', 'tâche', 'habitude', 'projet', 'contact', 'général'
);

CREATE TABLE IF NOT EXISTS memories (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    category        memory_category NOT NULL DEFAULT 'fait',
    content         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    qdrant_id       UUID,
    conversation_id UUID            REFERENCES conversations(id) ON DELETE SET NULL,
    importance      SMALLINT        NOT NULL DEFAULT 1 CHECK (importance BETWEEN 1 AND 5),
    metadata        JSONB           NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tier_routing_log (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    query_text          TEXT            NOT NULL,
    chosen_tier         SMALLINT        NOT NULL CHECK (chosen_tier IN (1, 2, 3)),
    reason              TEXT            NOT NULL DEFAULT '',
    final_tier          SMALLINT        NOT NULL CHECK (final_tier IN (1, 2, 3)),
    fallback_occurred   BOOLEAN         NOT NULL DEFAULT FALSE,
    latency_ms          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    override_manuel     BOOLEAN         NOT NULL DEFAULT FALSE,
    metadata            JSONB           NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tier_routing_created_at ON tier_routing_log (created_at DESC);

CREATE TABLE IF NOT EXISTS tool_call_metrics (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    tool_name           TEXT            NOT NULL,
    status              TEXT            NOT NULL,
    latency_ms          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    cognitive_tier      SMALLINT,
    cost_est            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    is_paid_key         BOOLEAN         NOT NULL DEFAULT FALSE,
    metadata            JSONB           NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_created_at ON tool_call_metrics (created_at DESC);

CREATE TABLE IF NOT EXISTS patches_auto_appliques (
    id                  TEXT            PRIMARY KEY,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    incident_motif      TEXT            NOT NULL,
    target_file         TEXT            NOT NULL,
    patch_diff          TEXT            NOT NULL,
    test_suite          TEXT,
    test_results        JSONB           NOT NULL DEFAULT '{}',
    status              TEXT            NOT NULL,
    is_critical         BOOLEAN         NOT NULL DEFAULT FALSE,
    release_path        TEXT,
    previous_release_path TEXT,
    applied_at          TIMESTAMPTZ,
    rolled_back_at      TIMESTAMPTZ,
    details             JSONB           NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_created_at ON patches_auto_appliques (created_at DESC);
```

### 3.4. Moteur Vectoriel Qdrant & Embeddings Fastembed (`services/memory.py`)
- **Modèle d'embedding local** : `BAAI/bge-small-en-v1.5` via `fastembed` (exécuté sur CPU ARM64, coût zéro, dimension **384**).
- **Collection vectorielle** : `jarvis_memories` avec métrique `Distance.COSINE`.
- **Compatibilité Multi-Versions** : Utilise `client.query_points(...)` pour les versions récentes de `qdrant-client` avec repli automatique sur `.search(...)`. Seuil de pertinence > 0.30 et repli SQL `ILIKE`.

### 3.5. Mémoire Locale Structurée SQLite (`jarvis_memory.db`)
Assure la persistance locale immédiate hors-cloud :
1. `user_profile` : Clés immuables de Pierre (`nom`, `prenom`, `email`, `adresse`, `pointure` 42, `taille`, `kindle_email`, et état du switch `paid_key_authorized`).
2. `memories` : Miroir relationnel direct pour consultation textuelle rapide.
3. `chat_messages` : Historique des échanges textuels et métadonnées multimodales.
4. `patches_auto_appliques` : Miroir local hors-ligne pour la traçabilité SRE.

### 3.6. Façade Unifiée de Mémoire Long-Terme (`services/unified_memory.py`)
La classe `UnifiedMemoryManager` arbitre les accès :
- Si l'information est une clé de profil reconnue, mise à jour dans SQLite `user_profile`.
- Les faits et souvenirs généraux sont indexés en arrière-plan dans Qdrant et PostgreSQL.
- Méthode `build_live_context_prompt()` agrégeant profil, faits récents, profil de candidature et résumé architectural pour injection dans Gemini Live à l'ouverture de chaque session.

### 3.7. Service de Connaissance Approfondie du Profil de Candidature (`services/user_profile_service.py`)
Garantit une maîtrise absolue et vivante du dossier professionnel de Pierre :
- **Source Dynamique** : Surveillance de `PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md` via `os.path.getmtime()`. Rechargement en RAM sans redémarrage dès édition.
- **10 Chapitres Stratégiques** : Identité (élève-ingénieur Grenoble INP - Phelma SICOM, MSc 2026, Malmö/Grenoble), cibles de stage (PFE 5-6 mois dès le 18 janvier 2026 en DSP/audio, optoélectronique, photonique intégrée, ML appliqué), stages R&D réels (Scintil Photonics : banc SCPI, laser DFB, athermique 500ns, suite IHM CustomTkinter divisant par 5 le temps de test wafer ; Teem Photonics : salle blanche ISO, lasers microchip), compétences (Python, C, MATLAB, DSP, LaTeX, Anglais C1 pro, Italien B1/B2).
- **Synchronisation Automatique Multi-Couches** : Amorçage SQLite au boot, injection dans le Live Context de `routers/voice.py`, priorité absolue (score 1.0) dans `unified_memory.recall()`, et transmission directe aux agents Antigravity et missions d'emailing.

---

## 4. ARCHITECTURE DE SÉCURITÉ, CRYPTOGRAPHIE & GESTION DES APPAREILS

### 4.1. Moteur d'Authentification Cryptographique (`services/auth_service.py` & `auth.py`)
```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        INFRASTRUCTURE D'AUTHENTIFICATION STARK                         │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Mot de passe maître chiffré dans .env (JARVIS_PASSWORD)                              │
│ • Tokens JWT signés HMAC-SHA256 avec claims standard (jti, iat, exp, device_id, role)  │
│ • Génération automatique d'une clé secrète JWT_SECRET_KEY forte (64 octets urlsafe)    │
│ • Pairage QR Code zero-touch instantané avec ticket à usage unique (TTL 300 s)         │
│ • Révocation immédiate et blacklistage de tokens/appareils via Redis                   │
│ • Migration transparente des anciens tokens en clair sans rupture de session           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2. Tokens JWT Signés (HMAC-SHA256) & Gestion des Clés Secrètes
- **Algorithme** : HMAC-SHA256 (`HS256`).
- **Payload type** : `{"device_id": "dev_...", "device_name": "...", "role": "admin", "iat": ..., "exp": ..., "jti": "jwt_tok_..."}`.
- **Durée** : 90 jours (`JWT_EXPIRATION_DAYS`). Auto-génération de `JWT_SECRET_KEY` (64 octets urlsafe) si absente du `.env`.

### 4.3. Registre des Terminaux & Empreintes Matérielles (`authorized_devices.json`)
Consigne pour chaque équipement : `device_id`, `device_name`, `ip_address`, `user_agent`, `registered_at`, `last_seen`, `status` (`approved` ou `revoked`).

### 4.4. Protocole de Pairage QR Code Zero-Touch à Usage Unique
1. Client connecté déclenche `GET /api/auth-qr`.
2. Serveur génère un ticket aléatoire unique (`qr_ticket_{secrets.token_hex(16)}`), stocké dans Redis avec un TTL strict de **300 secondes (5 minutes)**.
3. Smartphone scanne le QR code (`POST /api/auth-qr` avec le ticket).
4. Serveur valide le ticket, le **supprime immédiatement de Redis** (anti-rejeu), enregistre l'appareil et émet le JWT.

### 4.5. Révocation Instantanée & Blacklist Redis
- Route `POST /api/auth/revoke`. Inscription immédiate dans `jarvis:revoked_tokens:{jti}` et `jarvis:revoked_devices:{device_id}`.
- Tout appel ultérieur renvoie HTTP 401. Set en RAM de secours en cas de panne Redis.

### 4.6. Migration Rétrocompatible Transparente des Anciens Jetons
À la réception d'un ancien token hexadécimal, `AuthService` valide l'ancien token, émet un nouveau JWT, met à jour le cookie et purge l'ancien token de la base.

---

## 5. GOUVERNANCE DES MODÈLES IA, VERROU ÉCONOMIQUE & ROUTAGE COGNITIF EN 3 TIERS

### 5.1. Répartition Bimodale des Clés API (Gratuite vs Payante)
- **Clé Gratuite (`GEMINI_API_KEY_FREE`)** : Flux vocal standard (`gemini-3.8-live`), recherches factuelles, diagnostics légers, exécution Antigravity CLI (coût d'API nul via jeton OAuth2 Google AI Pro).
- **Clé Payante (`GEMINI_API_KEY_PAID`)** : `gemini-3.8-live-extended-thinking`, `gemini-3.8-flash` haute vitesse, modèles lourds Antigravity (`gemini-3.1-pro-preview`, `claude-3-7-sonnet`), vision Browser-Use et repli `api_paid_gemini`.
- **Gouvernance Centralisée (`services/key_gate.py`)** : `get_key()` est le point unique de distribution des clés. Le module expose :
  - `grant_paid_consent()` / `has_paid_consent()` / `revoke_paid_consent()` / `consume_paid_consent()` : consentement payant **par session ou par tâche** (clé dérivée par `_make_consent_key(session_id, task_id)`), révocable et à usage unique.
  - `is_qualified_free_key_failure(error, retry_count)` : qualification stricte des échecs autorisant un repli payant (quota épuisé, 429, refus serveur) et renvoi du motif.
  - `set_pending_action()` / `get_pending_action()` / `clear_pending_action()` : action en attente d'autorisation (`PendingAction`), consommée par l'outil `confirm_paid_key`.
  - `clear_all_consents()` : purge globale (fin de session ou coupure d'urgence).

### 5.2. Verrou Physique Applicatif & Double Consentement Oral
1. **Encoche Applicative (Switch UI)** : Persistée dans SQLite `user_profile` (`paid_key_authorized`). Si décochée, `get_effective_paid_key()` renvoie `""`. Aucune requête payante n'est émise au niveau réseau.
2. **Double Consentement Oral Explicite** : Même avec l'encoche cochée, toute action payante majeure requiert un accord vocal de Pierre avec estimation chiffrée (~0.03 $).
3. **Détection 429** : Zéro bascule silencieuse de la clé gratuite vers la clé payante sans accord préalable.

### 5.3. Routage Cognitif Dynamique en 3 Paliers (Tiers 1, 2, 3)

| Palier (Tier) | Modèle Résolu | Réflexion (Thinking) | Cibles Principales & Cas d'Usage | Latence Typique | Impact Quota 5h |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TIER 1 — Rapidité & Économie** | `gemini-3.8-flash` | `low` (ou minimal) | `doc_sync`, `book_curation`, `email_simple`, diagnostics routine, checks d'état. | 1 à 3 secondes | Négligeable (0 % Pro) |
| **TIER 2 — Raisonnement Tactique** | `gemini-3.8-flash` | `high` (renforcé) | `transport_optimizer`, `spreadsheet_modeler`, `email_drafting`, requêtes libres par défaut. | 4 à 10 secondes | Nul sur le quota 3.1 Pro |
| **TIER 3 — Délibération Système 2** | `gemini-3.1-pro` | `high` (délibératif) | `deep_research` multi-sources, `system_healing` critique, `code_refactoring`, ingénierie. | 20 à 60 secondes | Consommation mesurée sur Pro |

> **Résolution Déclarative Complémentaire** : `config/models.json` porte la table `routing_rules` (task_type `simple` → `gemini-3.7-flash`/`low`, `medium` → `gemini-3.7-flash`/`medium`, `complex` → `gemini-3.1-pro`/`high`, `code` → `claude-3-7-sonnet` sans effort) avec `fallback_chain` explicite par règle et `cooldown_seconds = 300`. Le drapeau `MODEL_ROUTING_ENABLED` (`config.py`, variable d'environnement, `true` par défaut) active ou désactive ce routage intelligent.

### 5.4. Mécanismes d'Arbitrage Ordonnés (`resolve_cognitive_tier`) & Télémétrie (`tier_routing_log`)
1. **Priorité 1 — Surcharge Explicite (Override)** : Mots-clés de rapidité ("fais vite", "passe rapide") → Tier 1 ; mots-clés de profondeur ("analyse en profondeur", "prends tout ton temps") → Tier 3 ; paramètre `intensite_reflexion` forcé.
2. **Priorité 2 — Table Déterministe (`mission_type`)** : `deep_research` → T3, `transport_optimizer` → T2, `doc_sync` → T1.
3. **Priorité 3 — Classifieur LLM Léger Tier 1 (`classify_query_tier_with_llm`)** : Appel `gemini-3.8-flash` rapide (timeout 3.5s, `response_mime_type="application/json"`) retournant `{"tier": 1|2|3, "reason": "..."}`. Repli sécurisé sur Tier 2 en cas de timeout.
4. **Télémétrie Asynchrone** : Chaque décision est consignée dans la table PostgreSQL `tier_routing_log` (`query_text`, `chosen_tier`, `reason`, `final_tier`, `latency_ms`, `override_manuel`).

### 5.5. Protocole de Résilience Quota-Aware & Dégradation Gracieuse (429)
En cas d'exception `AntigravityQuotaExhaustedError` ou HTTP 429 sur `gemini-3.1-pro` :
- Bascule automatique transparente sur Tier 2 (`gemini-3.8-flash-high`).
- Garantie d'inviolabilité : le modèle de repli utilise strictement la clé gratuite sauf si l'encoche payante est cochée.
- Notification proactive Aoede et inscription de l'incident dans `SupervisionService` et `tier_routing_log` (`final_tier = 2`).

### 5.6. Routage Intelligent Antigravity CLI, Résilience Quota & Politique Vocale
1. **Activation (`MODEL_ROUTING_ENABLED`)** : `config.py` lit la variable d'environnement (défaut `true`). Si désactivée, le pipeline retombe sur la sélection statique historique (`MODEL_FLASH` / `MODEL_PRO`).
2. **Registre (`services/model_routing/model_registry.py`)** : découverte dynamique (`agy models list --json`) avec cache TTL 1 h et cascade de repli CLI → `config/models.json` → catalogue par défaut en dur.
3. **Routeur (`services/model_routing/model_router.py`)** : `select_model()` arbitre modèle et niveau d'effort selon le type de tâche, la complexité et le contexte. Les alias de modèle/effort sont normalisés par `services/antigravity_models.py` (`validate_model_and_effort`, `choose_model_and_effort`, `MODEL_FLASH`, `MODEL_PRO`) et côté dispatcher par `_resolve_agy_model()` / `_resolve_agy_effort()`.
4. **Repli (`services/model_routing/fallback_handler.py`)** : `execute_with_fallback()` enchaîne Claude → Gemini CLI → `api_paid_gemini`, détecte les 429/quota, gère les cooldowns (300 s) et n'appelle la clé payante que si `config.is_paid_key_authorized()` est vrai (`config.get_effective_paid_key()`).
5. **Prompts (`services/model_routing/prompt_builder.py`)** : formatage XML (Claude) / Markdown (Gemini), injection des templates `prompts/templates/` et parseur JSON tolérant.
6. **Exécution Agentique (`services/agentic_runner.py`)** : `run_agentic()` construit la commande `agy` (`_build_command`), exige une sortie JSON stricte (`_extract_json_payload` + `_validate_json_schema`), détecte l'épuisement de quota (`_is_quota_error`) puis bascule sur `_execute_gemini_paid_fallback()` en s'appuyant sur `key_gate`.
7. **Politique Vocale (`services/live_mode_policy.py`)** : `decide()` arbitre en direct le mode `thinking` vs `standard` du Live (hystérésis via `get_policy()`, détection du besoin agentique par `_detect_agentic_need()`) et journalise chaque décision dans `tier_routing_log` via `log_tier_routing_decision()`.

---

## 6. LE MOTEUR VOCAL TEMPS RÉEL (GEMINI LIVE AUDIO)

### 6.1. Protocole Audio Full-Duplex & Streaming PCM
- Endpoint `/ws` connecté directement à l'API Google Gemini Live.
- Streaming PCM linéaire 16-bit, 16 kHz ou 24 kHz mono bidirectionnel permanent sans Push-to-Talk obligatoire.
- Accusé de lecture réel du client : le navigateur web ou l'application émet un message WebSocket `playback_finished` lorsque son buffer de lecture Web Audio API (`AudioBufferSourceNode`) est physiquement vide.

### 6.2. Assemblage Dynamique de l'Instruction Système & Contexte
À l'ouverture du WebSocket, compilation de :
1. Gabarit Stark Industries (`JARVIS_SYSTEM_INSTRUCTION_TEMPLATE`).
2. Bloc de mémoire contextuelle unifiée (`unified_memory_manager.build_live_context_prompt()`).
3. État matériel PC (`is_pc_connected()`).
4. Résumé architectural dynamique extrait d'`ARCHITECTURE_COMPLETE_JARVIS.md`.

### 6.3. Modèles Vocaux Actifs & Permutation à Chaud Différée
- Modèle standard : `gemini-3.8-live` ; Modèle avec réflexion : `gemini-3.8-live-extended-thinking`.
- Permutation à chaud via `/api/live-model` ou message WebSocket `set_live_model`.
- **Bascule différée anti-coupure** : Si Jarvis est en train de parler (`SpeechState != IDLE`), la requête de bascule est mise en attente (`active_task_controller["pending_model_switch"] = new_model`) et annoncée discrètement. La réinitialisation de session (`ModelSwitchRequested`) n'est déclenchée que lorsque le statut repasse en `IDLE`, protégeant la phrase entamée.

### 6.4. Boucle de Traitement des Outils Asynchrone Non-Bloquante (< 300 ms)
1. Gemini Live émet un `tool_call`.
2. Dispatcheur notifie `notify_tool_started(name)` (`SpeechState.TOOL_PENDING`) et renvoie **instantanément** un accusé de réception préliminaire : `{"status": "launched_in_background"}`.
3. Aoede confirme vocalement à Pierre en moins de 300 ms.
4. Tâche lourde exécutée en tâche de fond (`asyncio.create_task`).
5. Pierre et Jarvis continuent de dialoguer librement pendant l'exécution.
6. Notification finale injectée dans le flux via `VoiceInjectionQueue`.

### 6.5. File d'Injection Vocale à Priorités FIFO (`VoiceInjectionQueue`) & Coalescence
- `INTERRUPTION (1)` : Ordres d'arrêt d'urgence (`stop_current_action`), alertes SRE critiques. Seule cette priorité peut couper une prise de parole en cours.
- `TOOL_RESPONSE (2)` : Retours directs d'outils et commandes.
- `PROGRESS_MILESTONE (3)` : Jalons d'avancement des tâches longues.
- `PASSIVE_INFO (4)` : Télémétrie passive et logs non-urgents.
- **Règle Unique de Silence** : Aucune injection de priorité 2, 3 ou 4 ne part si `SpeechState != IDLE`. La file attend que le client ait fini de jouer le son (`playback_finished`) + un sas de respiration acoustique de 350 ms.
- **Coalescence des Retours d'Outils d'Arrière-Plan** : Si plusieurs tâches en tâche de fond se terminent alors que Jarvis est en train de parler, leurs messages `TOOL_RESPONSE` sont fusionnés en un seul tour conversationnel complet injecté en une seule fois.
- **Coalescence des Jalons de Progression** : Maximum 1 injection `PROGRESS_MILESTONE` par tâche toutes les 20 secondes, et rejet immédiat si l'utilisateur est en train de parler (`SpeechState.USER_SPEAKING`).

### 6.6. Jalons Vocaux Intermédiaires (`VOCAL_MILESTONE_THRESHOLD_SECONDS`)
- Variable d'environnement (90 secondes par défaut).
- Émission proactive de jalons vocaux pour les opérations longues afin d'éliminer l'effet "boîte noire", cadencée par la file d'injection prioritaire.

### 6.7. Machine à États Explicite de la Parole (`SpeechState`) & Règle d'Or de Canal Unique
1. **Machine à États `SpeechState`** :
   - `IDLE` : Aucun flux audio émis ou en attente de restitution physique.
   - `MODEL_SPEAKING` : Gemini Live génère de l'audio ou le client Web Audio restitue les trames PCM (maintien tant que `playback_finished` n'est pas reçu).
   - `USER_SPEAKING` : L'utilisateur a pris la parole (VAD ou speech recognition actif).
   - `TOOL_PENDING` : Un outil est en cours de dispatching synchrone.
   - *Auto-expiration sécurisée* : Si un client se déconnecte abruptement sans renvoyer `playback_finished`, retour automatique à `IDLE` dès `estimated_speech_end + 3.0s`.
2. **Règle d'Or de Canal Unique** :
   - `mark_action_sync_completed` : Si une action s'est exécutée de manière synchrone et a répondu via `tool_response`, l'injection parallèle d'un `send_client_content` est formellement bloquée.
   - `safe_send_live_client_content` : Tous les appels directs (`set_paid_key_authorized`, `paid_consent_response`, directives orales) transitent par la file d'injection et respectent le verrou d'élocution.

### 6.8. Gestion des Interruptions (Barge-In) & Traçabilité des Coupures de Parole
1. **Barge-in utilisateur immédiat** : Si l'utilisateur commence à parler pendant qu'Aoede s'exprime, le son est coupé instantanément côté client et relayé au backend.
2. **Distinction stricte des causes de coupure (Objectif 0 Coupure Interne)** :
   - Interruption utilisateur : journalisation explicite `SPEECH_CUT reason=user_barge_in`.
   - Interruption accidentelle ou interne (système, conflit d'outils) : journalisation explicite `SPEECH_CUT reason=internal`.
   - Compteur `internal_speech_cuts` exposé et tracé en temps réel sur `/api/supervision/metrics` pour audit et alerte SRE.

---

## 7. L'AGENT RELAIS LOCAL PC WINDOWS (`jarvis_local_agent`)

### 7.1. Problématique Résolue & Rôle Exécutant Physique
Le VPS distant n'a pas accès à l'écran, au Chrome réel, ni aux périphériques USB. `jarvis_local_agent.py` fait le pont permanent entre le Cloud et le poste de travail physique Windows 11.

### 7.2. Protocole WebSocket RPC & Reconnexion Résiliente
- Connexion sortante vers `wss://jarvis.signalcraftapps.com/ws/local-agent?token=...`.
- Reconnexion automatique avec backoff exponentiel. Messages RPC structurés (`{"req_id": "...", "action": "...", "params": {...}}`).

### 7.3. Catalogue des 20 Actions Locales Supportées (Schémas & Paramètres)

| Action RPC | Description Opérationnelle | Paramètres Entrants | Structure Retournée |
| :--- | :--- | :--- | :--- |
| `launch_app` | Lance une application Windows physique installée. | `app_name: str` (`vscode`, `vlc`, `calc`, `notepad`, `terminal`, `stremio`) | `{"status": "success", "pid": int, "message": str}` |
| `open_browser` | Ouvre Google Chrome à l'écran sur une URL donnée. | `url: str`, `new_window: bool` (défaut False) | `{"status": "success", "message": str}` |
| `launch_media` | Déclenche la lecture multimédia dans VLC ou Stremio. | `title: str`, `content_type: str` (`movie`, `series`, `music`) | `{"status": "success", "launched": str}` |
| `spotify_launch`| Déclenche le lancement de Spotify Desktop sur le PC. | `uri: str` (opt) | `{"status": "success", "launched": "spotify"}` |
| `browser_open_task` | Ouvre un onglet dédié dans le Chrome existant (CDP 9222) pour une tâche. | `task_id: str`, `start_url: str` | `{"ok": bool, "url": str}` |
| `browser_snapshot` | Injecte `data-jarvis-id` (1..150) et extrait le snapshot DOM & texte visible. | `task_id: str` | `{"ok": bool, "url": str, "title": str, "elements": str, "text": str}` |
| `browser_act` | Exécute une série de 1 à 3 actions (`click`, `type`, `select`, `scroll`, `goto`, `wait`, `back`, `extract`). | `task_id: str`, `actions: list[dict]` | `[{"action": dict, "ok": bool, "text"?: str, "error"?: str}]` |
| `browser_screenshot` | Capture d'écran JPEG qualité 60 du viewport encodée en base64. | `task_id: str` | `{"ok": bool, "image": str, "screenshot": str}` |
| `browser_focus` | Met l'onglet actif de la tâche au premier plan à l'écran. | `task_id: str` | `{"ok": bool}` |
| `browser_close_task` | Oublie la référence de l'onglet sans fermer la page physique. | `task_id: str` | `{"ok": bool}` |
| `prepare_train_checkout` | Ouvre en parallèle les onglets Omio/Trainline préremplis. | `segments: list[dict]`, `urls: list[str]` | `{"status": "opened_locally", "count": int}` |
| `prepare_web_cart_or_checkout` | Ajoute au panier sur Chrome et s'arrête avant paiement (délègue à `browser_task`). | `url: str`, `product: str` | `{"status": "cart_ready", "awaiting_payment": true}` |
| `interact_web_page` | Interagit unitairement avec une page web ouverte. | `url: str`, `instruction: str`, `selector: str` | `{"status": "interacted", "result": str}` |
| `get_status` | Relève la télémétrie matérielle physique en direct. | Aucun | `{"cpu_percent": float, "ram_percent": float, "battery": dict}` |
| `fetch_file` | Extrait et encode en base64 un fichier local PC pour le Cloud. | `file_path: str` | `{"status": "ok", "filename": str, "data_b64": str, "size": int}` |
| `list_workspace_dir` | Liste récursivement dossiers et fichiers dans `_anti_gravity` (lecture seule). | `relative_path: str`, `depth: int`, `pattern: str` | `{"status": "success", "items": list, "items_count": int}` |
| `read_workspace_file` | Lit le contenu textuel paginé d'un fichier dans `_anti_gravity` (lecture seule). | `file_path: str`, `max_lines: int`, `offset_line: int` | `{"status": "success", "content": str, "total_lines": int}` |
| `search_workspace_files` | Recherche textuelle (grep) au sein des projets sous `_anti_gravity`. | `query: str`, `subpath: str`, `extension: str`, `max_results: int` | `{"status": "success", "matches": list, "matches_count": int}` |
| `execute_cdp_browser_action` | Exécute une séquence d'actions CDP sur une URL dans le Chrome local (pont Playwright). | `url: str`, `actions: list[dict]`, `instruction: str`, `task_id: str` | `{"status": "success", "url": str, "title": str, "performed_actions": list, "screenshot_path": str, "result_summary": str}` |
| `gemini_deep_research` | Lance le Moteur A Deep Research via l'interface Gemini Web dans le Chrome local. | `topic: str` | `{"status": str, "message": str}` |


### 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
Flux standards encapsulés dans `AutoFlushStream` (`buffering=1`, `flush()` immédiat) dans `jarvis_agent.log`. `sys.excepthook` capturant toute exception avec traceback horodaté.

### 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
- `start_agent_silent.vbs` : Lancement invisible en tâche de fond via `wscript.exe` (zéro invite de commande noire).
- `install_autostart.bat` & `uninstall_autostart.bat` : Inscription au démarrage automatique du registre Windows (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
- `start_local_agent.bat`, `stop_agent.bat`, `view_logs.bat`.

### 7.6. Télémétrie Matérielle Réelle (`psutil`)
Remontée périodique (toutes les 15 s) : CPU global, mémoire vive, pourcentage et statut de charge batterie, liste des processus consommateurs.

---

## 8. CATALOGUE MATRICIEL & FICHES DES 49 OUTILS UNIFIÉS (FUNCTION CALLING)

### 8.1. Matrice Globale Exhaustive des 49 Outils Déclarés

> **Source de vérité** : `core/tools/declarations.py` contient exactement **49** `types.FunctionDeclaration` (vérifiable par `Select-String -Path core\tools\declarations.py -Pattern 'name="([a-z_]+)"'`). Les alias sont résolus dans `core/tools/dispatcher.py`.

| # | Nom Officiel (`declarations.py`) | Alias Supportés (`dispatcher.py`) | Mode d'Exécution | Arguments Clés & Types | Format de Réponse (`tool_resp`) | Service Exécutant |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `stop_current_action` | `stop` | Bloquant | `reason: str` (opt) | `{"status": "stopped", "message": str, "instruction_to_jarvis": str}` | `core/shared_state.py` |
| **2** | `guide_active_task` | `guide` | Non-bloquant | `directive: str` (req) | `{"status": "adapted", "directive": str, "message": str}` | `core/shared_state.py` |
| **3** | `ask_deep_reasoning` | `deep_reasoning` | Non-bloquant | `question: str` (req), `model: str`, `intensite_reflexion: str`, `confirmed_by_user: bool` | `{"status": "launched_in_background"|"success", "summary": str}` | `services/reasoning_service.py` |
| **4** | `launch_deep_research` | `lancer_mission_deep_research`, `deep_research` | Non-bloquant | `consigne: str`, `consigne_utilisateur: str` (alias ASR), `envoyer_email: bool`, `destinataire_email: str` — *aucun champ marqué requis* (le dispatcher accepte `consigne` / `consigne_utilisateur` / `sujet`) | `ToolResult` (`done`\|`failed`) | `services/browser_agent` (recette `gemini_deep_research`, résultat attendu en direct) avec repli `services/deep_research_service.py` |
| **5** | `search_web` | `web_search` | Bloquant | `query: str` (req) | `{"status": "success", "results": list[dict], "summary": str}` | `services/browser_service.py` |
| **6** | `browser_task` | `run_browser_task` (déclaration jumelle) | Non-bloquant | `goal: str` (req), `start_url: str`, `recipe: str` (`cart`\|`train`\|`gemini_deep_research`) | `{"status": "launched_in_background", "task_id": str}` | `services/browser_agent/loop.py` & `local_browser_actions.py` |
| **7** | `open_user_browser` | `open_browser` | Bloquant | `url: str` (req), `reason: str` | `{"status": "opened", "url": str, "message": str}` | `services/browser_service.py` |
| **8** | `set_browser_link` | `browser_link` | Bloquant | `url: str` (req), `title: str` | `{"status": "updated", "url": str, "title": str}` | `core/shared_state.py` |
| **9** | `save_memory` | `remember_user_fact`, `memoriser_information` | Bloquant | `fact: str` (req), `category: str`, `key: str` | `{"status": "saved", "fact": str, "storage": str}` | `services/unified_memory.py` |
| **10**| `recall_user_memories` | `search_memories` | Bloquant | `query: str` (req) | `{"status": "found", "results": list[dict], "count": int}` | `services/unified_memory.py` |
| **11**| `get_system_status` | `get_status` | Bloquant | Aucun | `{"status": "ok", "server": dict, "pc_local": dict}` | `services/system_service.py` |
| **12**| `launch_application` | `launch_app` | Bloquant | `app_name: str` (req) | `{"status": "success"|"error", "app": str, "message": str}` | `services/system_service.py` |
| **13**| `control_spotify` | `spotify_control` | Bloquant (<300ms) / Arrière-plan | `action: str` (req), `query: str`, `device: str`, `volume: int`, `search_type: str` | `{"status": "done"|"started", "verified": bool, "message": str}` | `services/spotify_service.py` |
| **14**| `play_video_stremio` | `launch_media` | Bloquant | `title: str` (req), `content_type: str` | `{"status": "success", "title": str, "protocol_uri": str}` | `services/media_service.py` |
| **15**| `send_email` | `mail_send` | Bloquant | `subject: str` (req), `body: str` (req), `to_email: str`, `attachments: list[str]` | `{"status": "sent", "to": str, "attachments_resolved": list[str]}` | `services/email_service.py` |
| **16**| `read_emails` | `get_emails` | Bloquant | `count: int`, `query: str`, `unread_only: bool` | `{"status": "success", "emails": list[dict], "summary": str}` | `services/email_service.py` |
| **17**| `check_console_errors` | `console_errors` | Bloquant | `action: str` (`diagnose`\|`clear`) | `{"status": "diagnosed", "errors": list[dict], "advice": str}` | `services/console_monitor.py` |
| **18**| `interact_web_page` | `web_interaction` | Non-bloquant | `url: str` (req), `action: str`, `selector: str`, `text: str` | `{"status": "interacted", "result": str}` | `services/browser_service.py` |
| **19**| `prepare_web_cart_or_checkout` | `prepare_cart` | Non-bloquant | `product_or_service: str` (req), `merchant_url: str` | Enveloppe `browser_task` (`recipe="cart"`) | `services/browser_agent/loop.py` |
| **20**| `download_file` | `file_download` | Non-bloquant | `url: str` (req), `filename: str` | `{"status": "downloaded", "path": str, "size_mb": float}` | `services/download_service.py` |
| **21**| `send_to_ereader` | `send_page_to_kindle`, `send_file_to_kindle` | Non-bloquant | `source: str` (req), `source_type: str` (`file`\|`url`), `method: str` | `{"status": "sent_to_ereader", "destination": str}` | `services/download_service.py` |
| **22**| `search_and_download_ebook` | `download_ebook` | Non-bloquant | `query: str` (req), `lang: str` (`fr`\|`en`) | `{"status": "ebook_delivered", "title": str, "epub_path": str}` | `services/download_service.py` |
| **23**| `list_chrome_extensions` | `chrome_extensions` | Bloquant | Aucun | `{"status": "success", "extensions": list[dict]}` | `services/browser_service.py` |
| **24**| `execute_external_action` | `executer_action_externe` | Non-bloquant | `action_name: str` (req), `parametres: dict` | `{"status": "executed", "n8n_result": dict}` | `services/automation.py` |
| **25**| `generate_spreadsheet` | `generer_fichier_tableur` | Non-bloquant | `nom_fichier: str`, `colonnes: list`, `lignes: list`, `modele_avance_agent: bool` | `{"status": "generated", "file_url": str, "path": str}` | `services/automation.py` |
| **26**| `generate_presentation` | `generer_presentation` | Non-bloquant | `titre: str` (req), `theme: str`, `slides: list[dict]`, `recherche_approfondie: bool` | `{"status": "slides_created", "presentation_url": str}` | `services/slides_service.py` |
| **27**| `get_active_task_status` | `task_status` | Bloquant | `task_id: str` (opt) | `{"status": "running"|"idle", "task": str, "progress": int}` | `services/supervision_service.py` |
| **28**| `save_notion_entry` | `notion_enregistrer` | Non-bloquant | `titre: str` (req), `type_entree: str`, `contenu: str` | `{"status": "saved", "notion_id": str}` | `services/automation.py` |
| **29**| `manage_calendar_event` | `agenda_gerer_evenement` | Non-bloquant | `action: str` (`create`\|`list`\|`delete`), `titre: str`, `date_debut: str` | `{"status": "success", "events": list[dict]}` | `services/briefing_service.py` |
| **30**| `create_push_reminder` | `creer_rappel_push` | Non-bloquant | `message: str` (req), `echeance: str` (req) | `{"status": "scheduled", "reminder_id": str, "time": str}` | `services/briefing_service.py` |
| **31**| `get_morning_briefing` | `demander_morning_briefing` | Bloquant | `force_refresh: bool` | `{"status": "ready", "briefing_text": str, "cached": bool}` | `services/briefing_service.py` |
| **32**| `search_train_routes` | `rechercher_train` | Bloquant | `origine: str` (req), `destination: str` (req), `date_depart: str`, `optimiser_avec_agent: bool` | `{"status": "success", "segments": list, "deep_links": list}` | `services/transport_service.py` |
| **33**| `monitor_train` | `surveiller_train` | Non-bloquant | `numero_train: str` (req), `date: str` | `{"status": "monitoring_active", "train": str}` | `services/transport_service.py` |
| **34**| `open_train_booking` | `reserver_billet_train_local` | Non-bloquant | `origine: str`, `destination: str`, `date_depart: str`, `url_trajet: str` | Enveloppe `browser_task` (`recipe="train"`) | `services/browser_agent/loop.py` |
| **35**| `query_jarvis_architecture` | `consulter_architecture_jarvis` | Bloquant | `sujet: str`, `section: str` | `{"status": "success", "content": str, "matched_titles": list}` | `services/architecture_service.py` |
| **36**| `draft_email_response` | `triage_et_brouillon_email` | Non-bloquant | `query: str`, `consigne: str` | `{"status": "draft_created", "file": str, "summary": str}` | `services/agentic_dispatcher.py` |
| **37**| `generate_book_summary` | `curation_livre_synthese` | Non-bloquant | `titre_livre: str` (req) | `{"status": "summary_ready", "epub_path": str}` | `services/agentic_dispatcher.py` |
| **38**| `system_self_healing` | `auto_guerison_systeme` | Non-bloquant | `motif: str`, `action: str` (`diagnose`\|`apply`\|`rollback`), `patch_id: str` | `{"status": "healing_in_progress"|"applied"|"requires_validation", "patch_id": str}` | `services/system_healing_service.py` |

| **39**| `run_browser_task` | `browser_task` (déclaration jumelle) | Non-bloquant | `goal: str` (req), `start_url: str`, `recipe: str` (`cart`\|`train`\|`gemini_deep_research`) | `{"status": "launched_in_background", "task_id": str}` | `services/browser_agent/loop.py` & `local_browser_actions.py` |
| **40**| `browser_task_status` | — | Bloquant | `task_id: str` (opt) | `{"status": str, "task_id": str, "steps": int, "goal": str, "result": any}` ou `{"status": "success", "tasks": list[dict]}` (sans `task_id`) | `core/tools/dispatcher.py` (registre `BROWSER_TASKS`) |
| **41**| `run_agentic_task` | `run_agent_task` (déclaration jumelle) | Non-bloquant | `objectif: str` (req), `contexte: str`, `livrable_attendu: str`, `model_override: str` (`flash`\|`pro`), `effort_override: str` (`low`\|`medium`\|`high`), `timeout: int` (défaut 300) | `ToolResult` (`started` \| `done` \| `failed`) | `services/agentic_runner.py` (via `services/agentic_dispatcher.py`) |
| **42**| `run_agent_task` | `run_agentic_task` (déclaration jumelle) | Non-bloquant | Identiques à `run_agentic_task` (`objectif`, `contexte`, `livrable_attendu`, `model_override`, `effort_override`, `timeout`) | `ToolResult` (`started` \| `done` \| `failed`) | `services/agentic_runner.py` (via `services/agentic_dispatcher.py`) |
| **43**| `modify_presentation` | `modifier_presentation` | Non-bloquant | `instruction: str` (req), `presentation_id: str` (`last` par défaut) | `ToolResult` (`done` avec `presentation_id`, `presentation_url`, `verified`) | `services/slides_service.py` |
| **44**| `get_plan_status` | — | Bloquant | Aucun | `{"status": "done", "verified": true, "has_plan": bool, "plan_id": str, "total_steps": int, "pending_count": int, "done_count": int, "failed_count": int, "is_complete": bool, "steps": list[dict], "next_pending": dict}` | `services/task_planner.py` |
| **45**| `mark_plan_step` | — | Bloquant | `step_id: str` (req), `status: str` (req : `done`\|`failed`\|`skipped`\|`pending`), `note: str` | `{"status": "done"\|"failed", "verified": bool, "user_message": str, "evidence": str, "error_hint": str}` (+ broadcast HUD) | `services/task_planner.py` |
| **46**| `confirm_paid_key` | `confirmer_cle_payante` | Bloquant | `accept: bool` (req) | `ToolResult` (`done`, ou `failed` avec `error_hint="no_pending_action"`) | `services/key_gate.py` |
| **47**| `list_workspace_files` | `lister_fichiers_workspace` | Bloquant | `relative_path: str`, `depth: int` (1 à 3, défaut 1), `pattern: str` | `ToolResult.done` (`items`, `items_count`, `truncated`, `verified=True`) | `services/workspace_service.py` |
| **48**| `read_workspace_file` | `lire_fichier_workspace` | Bloquant | `file_path: str` (req), `max_lines: int` (défaut 200, max 500), `offset_line: int` (défaut 1) | `ToolResult.done` (`content`, `total_lines`, `lines_shown`, `verified=True`) | `services/workspace_service.py` |
| **49**| `search_workspace_files` | `chercher_fichiers_workspace` | Bloquant | `query: str` (req), `subpath: str`, `extension: str`, `max_results: int` (défaut 30) | `ToolResult.done` (`matches`, `matches_count`, `verified=True`) | `services/workspace_service.py` |
> **Total vérifié : 49 déclarations.** Les paires `browser_task`/`run_browser_task` et `run_agentic_task`/`run_agent_task` sont deux déclarations distinctes partageant le même exécuteur (compatibilité de nommage Gemini Live) ; les lignes 39 et 42 matérialisent ces déclarations jumelles.

### 8.2. Moteur Multi-Agents Antigravity CLI sur VPS & Routage Intelligent de Modèles
- **Fichiers** : `google_antigravity.py`, `services/model_routing/` (`model_registry.py`, `model_router.py`, `fallback_handler.py`, `prompt_builder.py`), `config/models.json`, `prompts/templates/`, `AGENTS.md`.
- **Exécution** : Sous-processus `agy` sur Ubuntu ARM64 adossé au jeton OAuth2 Google AI Pro (`~/.gemini/antigravity-cli/antigravity-oauth-token`), coût d'API nul.
- **Pipeline Délibératif 3 Phases** : Prospecteur → Analyste critique → Synthèse & Artefact.
- **Règles Strictes de Drapeaux** : `--model <nom>` et optionnellement `--effort <level>` (low | medium | high | max). Bannissement formel de `--thinking` (qui causait `exit code 2`). Pré-contrôle `verify_antigravity_cli_ready()` avant d'annoncer `launched_in_background`.

#### 8.2.1. Architecture du Routage Intelligent des Modèles (`services/model_routing/`)
1. **Registre Dynamique & Catalogue (`model_registry.py`)** :
   - Découverte dynamique via la commande CLI (`agy models list --json`) avec mise en cache TTL configurable (1h).
   - Cascade de repli : Découverte CLI → Configuration déclarative `config/models.json` → Catalogue par défaut en dur (`gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-3.1-pro`, `gemini-3.1-pro-preview`, `claude-3-7-sonnet`).
   - Métadonnées complètes par modèle : `provider` (gemini/claude), `tier` (flash/pro/sonnet), `supports_effort` (bool), `context_window` (200k à 2M tokens), `cost_rank`, `latency_rank`, `strengths` et `aliases`.
2. **Routeur Intelligent d'Arbitrage (`model_router.py`)** :
   - Fonction maître `select_model(task, query, context_size, user_preference, intensite_reflexion) -> RoutingDecision`.
   - Matrice de décision par tâche :
     - *Simple (Tier 1)* : `gemini-3.7-flash`, réflexion `low` (diagnostics, synchronisation doc).
     - *Moyenne (Tier 2)* : `gemini-3.7-flash`, réflexion `medium` ou `high` (tableurs, transport, e-mails).
     - *Complexe (Tier 3)* : `gemini-3.1-pro`, réflexion `high` (recherche approfondie, refactoring, auto-réparation Système 2).
     - *Code / Raisonnement Long* : `claude-3-7-sonnet`, sans argument effort (ingénierie logicielle ou préférence Claude explicite).
   - Surclassement automatique vers les modèles à grande fenêtre (2M tokens) si la taille du contexte dépasse la capacité du modèle initial.
3. **Gestionnaire de Repli Quota Résilient (`fallback_handler.py`)** :
   - Cascade automatique : Modèle Claude (CLI) → Modèle Gemini équivalent (CLI) → API Directe Gemini avec clé PAID (strictement conditionnée à `user_profile.paid_key_authorized` / `get_effective_paid_key()`) → Erreur explicite.
   - Détection exhaustive des erreurs 429 et saturations de quota (`RESOURCE_EXHAUSTED`, `rate limit`, `too many requests`, `quota 5h`).
   - Mise en quarantaine temporaire (cooldown de 300s) des modèles saturés pour éviter les blocages répétés.
   - Les erreurs non liées au quota (syntaxe, timeouts, annulations) sont remontées immédiatement sans bascule de modèle.
   - Inviolabilité absolue : aucune clé secrète ni token n'est jamais journalisé ou exposé.
4. **Constructeur de Prompts Adaptés & Parseur Tolérant (`prompt_builder.py`)** :
   - Adaptation du format d'instruction par fournisseur : balises XML structurées pour Claude (`<system_role>`, `<objective>`, `<constraints>`, `<output_format>`), structure Markdown concise et directive pour Gemini.
   - Templates modulaires par type de mission dans `prompts/templates/` (`simple.txt`, `medium.txt`, `complex.txt`, `code.txt`).
   - Exigence de rapport final au format JSON standard `{status, summary, actions_done, files_changed, errors, next_steps}`.
   - Parseur tolérant capable d'extraire le JSON valide même en présence de texte introductif ou de logs d'exécution.
5. **Charte de Règles Déportée (`AGENTS.md`)** :
   - Directives universelles déployées sur le VPS et dans l'espace de travail local : autonomie sans interruption, confinement strict au workspace, interdiction des secrets/.env/paiements, vérification par tests unitaires et restitution JSON finale.

### 8.3. Moteur Asynchrone Deep Research : Architecture à Double Moteur
Le système dispose de deux moteurs de Deep Research sélectionnés intelligemment :

#### Moteur A (Prioritaire) : Navigation Autonome Gemini Web (`services/browser_agent/` - Recette `gemini_deep_research`)
- **Principe** : Pilotage autonome de `https://gemini.google.com/app` via l'agent `browser_task` et la recette `gemini_deep_research.md` sur le Chrome connecté de l'utilisateur (port 9222).
- **Cycle d'Exécution** : Activation du mode Deep Research, saisie du sujet de recherche, validation du plan proposé par Gemini, attente active non-bloquante (`wait 120` répété pendant la génération), extraction intégrale du rapport Markdown (`extract`) et restitution vocale / courriel Stark HTML.
- **Gestion de Session** : Réutilisation directe du profil et des cookies Google existants sans ressaisie d'identifiants. En cas de déconnexion, déclenchement immédiat d'un `handoff` utilisateur.
- **Point d'Entrée Unifié (vérifié le 02/10/2026)** : `services/deep_research_service.launch_deep_research_gemini_web(topic, live_session=None, use_legacy_engine=False)` encapsule ce Moteur A : elle instancie `BrowserTask(task_id="bt_dr_<ms>", goal=topic, recipe="gemini_deep_research")`, exécute `await run_browser_task(task)` et retourne `{"status": "success", "task_id": str, "result": dict}` en cas de succès, sinon `{"status": "error", "error": str, "fallback": "legacy"}`. Avec `use_legacy_engine=True`, elle court-circuite le Browser Agent vers le Moteur B (`{"status": "legacy_engine"}`).

#### Moteur B (Repli) : Pipeline Map-Reduce VPS (`services/deep_research_service.py`)
Mobilisé automatiquement si le Moteur A échoue ou si le navigateur local n'est pas disponible :
1. *Compilateur de Spécification Dynamique* : Tier 1 Flash JSON (`MissionSpec`).
2. *Override Géographique Absolu* : Bannissement formel des localisations par défaut de la mémoire (`DEFAULT_MEMORY_LOCATIONS`).
3. *Phase MAP* : 3 ouvriers Antigravity CLI parallèles (Startups/Incubateurs, Scale-ups/R&D, Grands Groupes).
4. *Phase REDUCE* : Déduplication stricte et normalisation (`NormalizedEntity`).
5. *Phase QUALITY GATE* : Agent critique appliquant 3 règles (volume, géographie, critères).
   - **Zéro Tolérance aux Livraisons Maquillées** : Si l'audit échoue après relances, `quality_gate_passed = False`. Aoede alerte immédiatement Pierre de vive voix, bannière rouge dans le rapport Markdown, et mention `[PARTIEL - AUDIT NON VALIDÉ]` dans les e-mails et messages Telegram.
6. *Livraison Déterministe Multi-Canal* : Rapport Markdown `/artifacts/`, deck Google Slides via n8n, notification Telegram et jalons vocaux intermédiaires.

> **Contrat de Dispatch Vérifié (02/10/2026)** : contrairement à `browser_task` (qui rend la main immédiatement avec `{"status": "launched_in_background", "task_id": str}`), l'outil `launch_deep_research` **attend** le verdict du Moteur A. `core/tools/dispatcher.py` (branche `launch_deep_research`, l. 595-624) instancie `BrowserTask(task_id="bt_dr_<ms>", goal=consigne, recipe="gemini_deep_research")`, l'exécute via `await run_browser_agent_task(task=dr_task)` et retourne **directement** le `ToolResult` du Browser Agent si `is_success` et `dr_task.status != "failed"` (le rapport est alors expédié par e-mail si `envoyer_email=true`, destinataire par défaut `pierrecassagnettes@gmail.com`). Le repli Map-Reduce VPS n'est déclenché qu'en cas d'échec ou d'exception, après contrôle `verify_antigravity_cli_ready()` (retour `ToolResult.failed(error_hint=cli_err)` si le CLI `agy` est indisponible, sans jamais annoncer un lancement fictif). Ce contrat est verrouillé par `tests/test_deep_research.py` (9/9 verts) et `tests/test_gemini_web_automator.py` (21/21 verts).

### 8.4. Moteur Délibératif Système 2 Transverse (Les 8 Missions Agentiques Spécialisées)
Orchestrées par `services/agentic_dispatcher.py` :
1. `transport_optimizer` : Analyse comparative TGV vs train de nuit, marges de correspondances avec bagages, options de repas en gare, itinéraire exécutif.
2. `spreadsheet_modeler` : Conception autonome de modèles financiers `.xlsx` via `openpyxl` avec formules natives (`XLOOKUP`, `SUMIFS`), charte corporate Stark (#1E293B).
3. `system_healing` : SRE autonome avec RCA, exécution en sandbox temporaire, Blue/Green releases et escalade avec accord oral sur fichiers critiques.
4. `email_drafting` : Triage exécutif, analyse de pièces jointes PDF via `pypdf`, brouillon argumenté dans `outbox_emails/`.
5. `book_curation` : Fiche exécutive 'Clés de lecture' 2 pages expédiée sur Kindle.
6. `morning_briefing` : Préparation à 6h45 croisant météo, agenda, actualités et trains.
7. `memory_consolidation` : Déduplication nocturne et réconciliation de contradictions.
8. `doc_sync` : Contrôle de cohérence entre le code des routeurs et `ARCHITECTURE_COMPLETE_JARVIS.md`.

### 8.5. Interaction Web Autonome & Agent Navigateur Local (`browser_task`)

#### 8.5.1. Paradigme & Schéma du Flux Opérationnel
Le système d'interaction web repose sur une architecture découplée en tâche de fond :
1. **Jarvis (Gemini Live)** : Reçoit l'intention vocale, déclenche `browser_task(goal, start_url, recipe)` de manière non-bloquante, confirme oralement à Pierre (« Je m'en occupe ») et reste immédiatement disponible à la voix.
2. **Exécution en Arrière-Plan** : `core/tools/dispatcher.py` instancie un `BrowserTask` et lance `run_browser_agent_task(task, notify)` au sein d'une tâche asyncio supervisée (`BROWSER_TASKS`).
3. **Agent Local PC (`jarvis_local_agent.py` & `local_browser_actions.py`)** : Se connecte via CDP sur l'instance Chrome réelle ouverte de Pierre (`http://localhost:9222`), conservant tous ses cookies et sessions authentifiées. Il exécute les ordres physiques (DOM, clics, saisie, captures) sans logique décisionnelle locale.
4. **Cerveau Décisionnel Cloud (`services/browser_agent/cli_brain.py`)** : TOUTE la réflexion (analyse du snapshot DOM, décision d'action S4, analyse d'image par vision si nécessaire, vérification de réussite) est déléguée aux agents CLI Antigravity (`agy`) exécutés en sous-processus sur le VPS.
5. **Boucle d'Action & Vérification (S2)** :
   - *Observer* : RPC `browser_snapshot` → extrait l'URL, le titre, le texte visible (1500 car) et numérote jusqu'à 150 éléments interactifs avec l'attribut `data-jarvis-id`.
   - *Décider* : Appel CLI `agy` (`decide`) avec objectif, recette, mémoire du site, snapshot et 6 dernières actions.
   - *Vision* : Si `need_screenshot=true` (ou après 3 erreurs consécutives), RPC `browser_screenshot` (JPEG qualité 60), enregistrement dans le cache (`step_<n>.jpg`), et appel CLI `agy` multimodal analysant l'image.
   - *Garde-Fou* : Validation de chaque action par `guards.check_action()`.
   - *Agir* : RPC `browser_act` exécutant 1 à 3 actions (`click`, `type`, `select`, `scroll`, `goto`, `wait`, `back`, `extract`).
   - *Vérifier* : Lorsque `done=true`, appel CLI `agy` (`verify`) pour valider formellement le critère de réussite.
6. **Mise au Premier Plan & Notification Vocale** : Jarvis ne génère jamais d'URL de résultat artificielle. À la fin, RPC `browser_focus` met l'onglet actif au premier plan et le résultat est injecté dans le flux vocal via `VoiceInjectionQueue`.

```
┌─────────────────┐       (1) Tool Call Non-Bloquant       ┌───────────────────────────────┐
│   Gemini Live   ├───────────────────────────────────────►│ core/tools/dispatcher.py      │
│  (Session Voix) │◄───────────────────────────────────────┤ (asyncio bg task + RPC bridge)│
└────────┬────────┘       (6) Injection Vocale Finale      └───────────────┬───────────────┘
         │            (VoiceInjectionQueue: TOOL_RESPONSE)                 │
         │                                                                 │ (2) RPC WebSocket
         ▼                                                                 ▼
┌─────────────────┐                                        ┌───────────────────────────────┐
│   Supervision   │                                        │  jarvis_local_agent.py (PC)   │
│ & HUD Mobile UI │                                        │  local_browser_actions.py     │
└─────────────────┘                                        └───────────────┬───────────────┘
                                                                           │ (3) Playwright CDP
                                                                           ▼
                                                           ┌───────────────────────────────┐
                                                           │ Google Chrome Réel (Port 9222)│
                                                           │ (Sessions & Cookies de Pierre)│
                                                           └───────────────┬───────────────┘
                                                                           │
                                                                           │ (4) DOM balisé data-jarvis-id
                                                                           │     & Captures d'écran JPEG
                                                                           ▼
                                                           ┌───────────────────────────────┐
                                                           │ services/browser_agent/       │
                                                           │ - loop.py (Boucle S2)         │
                                                           │ - guards.py (Garde-fous S5)   │
                                                           │ - site_memory.py (Mémoire S6) │
                                                           └───────────────┬───────────────┘
                                                                           │ (5) Invocation CLI
                                                                           ▼
                                                           ┌───────────────────────────────┐
                                                           │ Antigravity CLI (agy VPS)     │
                                                           │ cli_brain.py (decide, verify) │
                                                           └───────────────────────────────┘
```

#### 8.5.2. Répertoire des Composants & Rôles des Fichiers
- `local_browser_actions.py` : Pont CDP Playwright côté PC Windows (`BrowserBridge`), assurant la connexion sur le port 9222, le balisage dynamique du DOM (`data-jarvis-id` de 1 à 150), l'exécution ordonnée des actions et la capture d'écran JPEG viewport.
- `services/browser_agent/__init__.py` : Point d'entrée exportant `BrowserTask`, `TASKS`, `run_browser_task`, `cancel_task`, `check_action`, `load_hint`, `save_success`.
- `services/browser_agent/loop.py` : Orchestrateur de la boucle de navigation autonome S2 (gestion des étapes `max_steps`, du délai `max_duration`, des erreurs consécutives, de l'appel vision, du mécanisme de `handoff` et de la vérification finale).
- `services/browser_agent/cli_brain.py` : Cerveau décisionnel et vérificateur s'appuyant sur Antigravity CLI (`agy`), avec invite textuelle ou multimodale (analyse de captures d'écran), validation stricte du format JSON S4 et réessai automatique en cas d'anomalie de syntaxe.
- `services/browser_agent/guards.py` : Garde-fous de sécurité S5 vérifiant chaque action avant exécution. Bloque tout clic sur élément de paiement/commande final (`PAYMENT_PATTERN`) et interdit la saisie automatique de mots de passe ou coordonnées bancaires (`PASSWORD_PATTERN`, `SENSITIVE_FIELD_PATTERN`).
- `services/browser_agent/site_memory.py` : Persistance atomique des parcours de navigation réussis par domaine sous `data/site_memory/<domain>.json` (S6), injectant jusqu'à 2 résumés d'étapes passées comme indices pour le cerveau.
- `services/browser_agent/recipes/` : Dossier contenant les consignes de navigation spécialisées au format Markdown.

#### 8.5.3. Catalogue des Recettes Disponibles (`services/browser_agent/recipes/`)
- `cart.md` : Consignes pour l'e-commerce générique (recherche de produit, sélection du meilleur compromis prix/pertinence, gestion des pop-ups/cookies, ajout au panier, arrêt strict avant commande).
- `train.md` : Consignes pour la recherche et sélection d'itinéraires ferroviaires sur SNCF Connect (avec repli Trainline), sélection des horaires optimaux et arrêt sur la page passagers/pré-paiement.
- `gemini_deep_research.md` : Consignes pour l'automatisation de Google Gemini (`https://gemini.google.com/app`), activation du mode Deep Research, lancement de la recherche, surveillance en boucle (`wait 120`), extraction du rapport intégral avec `extract` et transmission.

#### 8.5.4. Outils Exposés à Gemini Live & Rétrocompatibilité
- `browser_task` : Outil maître générique de navigation autonome. Accepte `goal` (objectif en langage naturel), `start_url` (URL de départ optionnelle) et `recipe` (`cart`, `train`, `gemini_deep_research`).
- `browser_task_status` : Outil de suivi d'avancement retournant l'état, l'étape en cours et l'objectif pour un `task_id` donné.
- `prepare_web_cart_or_checkout` (alias `prepare_cart`) : Conservé pour rétrocompatibilité ; enveloppe automatiquement `browser_task` avec la recette `cart`.
- `open_train_booking` (alias `reserver_billet_train_local`) : Conservé pour rétrocompatibilité ; enveloppe automatiquement `browser_task` avec la recette `train`.
- `launch_deep_research` (alias `deep_research`, `lancer_mission_deep_research`) : Enveloppe en priorité `browser_task` avec la recette `gemini_deep_research` avant de basculer sur le pipeline Map-Reduce VPS en cas d'échec.
- `run_browser_task` : Conservé comme alias direct / compatibilité historique vers `browser_task`.

#### 8.5.5. Garde-Fous de Sécurité & Protocole de Handoff
- **Anti-Paiement Inviolable** : Tout clic sur un bouton d'achat final (mots-clés : *payer, paiement, commander, passer la commande, valider et payer, pay now, place order, buy now*, etc.) est intercepté par `guards.py`. La tâche s'interrompt avec le statut `ready_for_user`, l'onglet est mis au premier plan via `browser_focus`, et Jarvis annonce oralement : « C'est prêt, il ne te reste qu'à valider. »
- **Données Confidentielles** : Mots de passe, numéros de carte de crédit, IBAN et CVV ne sont jamais saisis par l'agent.
- **Protocole de Handoff Utilisateur** : En cas de détection d'un obstacle non automatisable (captcha, écran de connexion obligatoire, 2FA, choix complexe), l'agent bascule en `handoff`. L'onglet est mis au premier plan, Jarvis prévient Pierre vocalement avec priorité `INTERRUPTION`, puis le système surveille l'évolution de la page par un snapshot toutes les 5 secondes pendant 5 minutes maximum. Si l'utilisateur lève le blocage, la tâche reprend de manière fluide ; sinon, elle se clôture avec le statut `needs_user`.
- **Annulation Physique** : L'outil `stop_current_action` déclenche `cancel_task(task_id)` qui interrompt immédiatement la boucle asynchrone et libère l'onglet.

#### 8.5.6. Limites Connues
- **Captchas & Défis Anti-Bot** : Cloudflare Turnstile, reCAPTCHA v2/v3 et puzzles interactifs ne sont pas résolus automatiquement par l'agent et nécessitent une intervention humaine via le protocole de handoff.
- **Authentification Forte & 2FA** : Les formulaires exigeant des codes SMS, clés FIDO2 ou notifications bancaires sur smartphone requièrent le relais de l'utilisateur.
- **Sites sans Recette Dédiée** : Pour les services complexes non couverts par une recette (`recipes/*.md`), l'agent fonctionne par heuristique générale ; son efficacité dépend de la clarté du DOM et du respect du quota des 150 éléments interactifs balisés par snapshot.
- **Contraintes de Fenêtrage DOM** : Les snapshots filtrent les éléments interactifs à 150 éléments visibles (hauteur max 2 viewports) et tronquent le texte descriptif de la page à 1500 caractères.

### 8.6. Pôle Documentaire & Présentations Google Slides Polymorphes v1
- `services/slides_service.py` : 7 layouts visuels widescreen 16:9 (`hero_title`, `key_metrics`, `cards_grid`, `split_compare`, `timeline_steps`, `quote_highlight`, `conclusion_call_to_action`).
- Conformité Google Slides API v1 (`ROUND_RECTANGLE`), suppression automatique de la diapositive blanche initiale.

### 8.7. Mobilité & Système Ferroviaire Intelligent (France & Suède)
- Décomposition multi-segments (ex: Malmö ↔ Kiruna via Stockholm Central avec TGV de jour + train de nuit).
- Recherche de trajets et réservation : `search_train_routes` (recherche d'horaires et liaisons) et `open_train_booking` (alias `reserver_billet_train_local`, qui délègue l'interaction web sur les sites de réservation à `browser_task` avec la recette `train.md`).
- Surveillance Trafikverket/SNCF toutes les 10 min par n8n avec alerte vocale et Telegram si retard > 5 min.

### 8.8. Gestionnaire E-Book, Liseuses Physiques & Send to Kindle
- Scraping Anna's Archive avec contrôle strict de la langue (FR/EN) et intégrité EPUB.
- Détection des liseuses USB montées sous Windows et téléversement direct Amazon Send to Kindle Web (fichiers jusqu'à 200 Mo).

### 8.9. Contrôleur Média : Spotify & Stremio
- **Spotify Web API & Connect** : Client asynchrone direct (`services/spotify_service.py`) avec OAuth 2.0 PKCE, tokens chiffrés Fernet dans SQLite et cache Redis. Contrôle lecture, recherche (titre, artiste, album, playlist), favoris, files d'attente, volume et transfert d'appareils.
  - **Gestion de l'Appareil par Défaut** : Table SQLite `user_device_preferences`. Résolution prioritaire : 1) Indice oral explicite (`device="pc"`), 2) Appareil actuellement actif, 3) Préférence utilisateur enregistrée (par défaut 'telephone'). Si le smartphone est absent de Spotify Connect, émission d'un message vocal explicite sans bascule silencieuse PC.
  - **Ducking Intelligent du Volume** : Dès que Jarvis commence à parler (`MODEL_SPEAKING`), le volume réel est sauvegardé et abaissé (~25% ou cible 15%). Dès la fin de parole (`playback_finished`, `speech_ended` ou interruption barge-in), le volume réel d'origine est restauré. Le ducking est ignoré si `supports_volume=false`, n'intervient qu'une seule fois par tour de parole, et n'écrase pas le réglage si l'utilisateur a ajusté son volume manuellement entre-temps.
- **Stremio & VLC** : Interrogation Cinemeta / Torrentio pour trouver les flux 1080p légers et lancement via protocole URI `stremio:///detail/...` ou VLC direct via l'agent local.

### 8.10. Suite de Communication & Messagerie Stark
- Envoi SMTP avec gabarit Stark HTML et résolution floue universelle des pièces jointes (`resolve_attachment_path`). Rapatriement de fichiers locaux du PC via `fetch_file` base64.
- Consultation IMAP Gmail et archivage automatique dans `outbox_emails/`.

### 8.11. Système de Mémoire Hybride (SQLite, Qdrant & Fastembed)
Arbitrage automatique entre faits de profil (SQLite) et mémoire vectorielle RAG (Qdrant + Fastembed local 384 dim).

### 8.12. Télémétrie, Observabilité & Métriques des Outils (`services/metrics_service.py`)
Consignation non-bloquante de chaque appel d'outil dans PostgreSQL `tool_call_metrics` (statut, latence, tier, coût, arguments). Exposition sur `/api/supervision/metrics` avec fenêtres temporelles 24h, 7j, 30j.
Comprend également le compteur d'intégrité `claimed_success_without_verification` : incrémenté automatiquement par `normalize_result()` dès qu'un outil prétend à un succès terminé (`status="done"`) sans qu'une vérification indépendante matérielle n'ait pu être attestée (`verified=False`).

### 8.13. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
Synchronisation bidirectionnelle Google/Samsung Calendar via n8n. Rappels push instantanés via Telegram Stark Bot (`chatId: 6849746502`). Briefing matinal compilé dans Redis (`jarvis:briefing:today`).

### 8.14. Connaissance Architecturale Dynamique & Auto-évaluation
`services/architecture_service.py` surveille `ARCHITECTURE_COMPLETE_JARVIS.md` via `mtime`. Outil `query_jarvis_architecture` permettant à Jarvis de citer ses propres spécifications.

### 8.15. SRE Autonome & Auto-Guérison Système (`services/system_healing_service.py`)
- Analyse de cause racine (RCA) suite à des crashs interceptés par `console_monitor.py`.
- Validation syntaxique stricte (`py_compile`).
- Exécution de tests dans une sandbox temporaire isolée (excluant `venv`, `.git`).
- Auto-génération de test minimal de non-régression si aucun test n'existe pour le module ciblé.
- **Règle d'Escalade Fichiers Critiques** : Si un fichier sensible (`CRITICAL_FILES = {"auth_service.py", "dispatcher.py", "auth.py", "declarations.py", "security.py"}`) est touché, le patch passe au statut `requires_validation` et attend l'approbation orale explicite de Pierre.
- Déploiement Blue/Green atomique (`releases/<timestamp>` + symlink `current`), rollback instantané en 1 clic ou commande vocale. Persistance PostgreSQL + SQLite.

### 8.16. Contrat Universel ToolResult & Moteur de Vérification d'Effet Réel (Zero Unverified Claims)
Afin de rendre structurellement impossible que Jarvis annonce oralement un succès non prouvé, le contrat canonique strict s'applique à l'intégralité des 49 outils déclarés :

0. **Portail de Validation Pré-Exécution (`core/tools/arg_validator.py`)** :
   - `validate_tool_arguments(name, args)` est invoqué en toute première instruction de `_execute_dispatch_tool()` (`core/tools/dispatcher.py`, section « 0. Validation stricte des arguments et confirmation utilisateur »), **avant** toute logique métier.
   - Il ne s'applique qu'aux outils sensibles déclarés dans `SENSITIVE_TOOLS` (`send_email`/`mail_send`, `draft_email_response`, `generate_presentation`/`generer_presentation`, `modify_presentation`/`modifier_presentation`, `manage_calendar_event`/`agenda_gerer_evenement`, `system_self_healing`/`auto_guerison_systeme`) et retourne `None` (exécution autorisée) pour tous les autres.
   - `is_generic_or_empty(val, min_length)` rejette les valeurs absentes, trop courtes ou présentes dans le lexique `GENERIC_STRINGS` (`"test"`, `"mail"`, `"présentation"`, `"titre"`, `"bug"`, `"todo"`, …).
   - Les actions irréversibles (`IRREVERSIBLE_TOOLS`, suppression d'événement d'agenda, auto-guérison) exigent en outre `confirmed_by_user=True` ; à défaut, le portail renvoie un `ToolResult.needs_user` (`"Confirmation requise : …"`) et l'outil n'est jamais exécuté.
   - Ce portail est la première ligne de défense du « Zero Unverified Claims » : une requête d'e-mail à objet vide/générique, ou un envoi non confirmé, ne peut structurellement pas atteindre le SMTP. *(Reconciliation vérifiée le 02/10/2026 : `tests/test_tool_result.py::test_verify_email_sent_fail` passait auparavant `subject="Test Sujet"` sans `confirmed_by_user`, donc le portail interceptait l'appel en `needs_user` ; le test transmet désormais `confirmed_by_user=True` et valide bien la bascule `failed` post-vérification — 17/17 tests verts.)*

1. **La Dataclass Canonique `ToolResult` (`core/tools/result.py`)** :
   - `status ∈ {"done", "failed", "started", "partial", "needs_user"}` (5 valeurs cardinales exhaustives, validation immédiate en `__post_init__`).
   - `verified: bool` : `True` **uniquement** si une vérification indépendante post-exécution a matériellement réussi.
   - `evidence: str` : Preuve matérielle tangible du résultat (URL Google Slides vérifiée, message-id SMTP/IMAP, chemin physique et taille en octets d'un téléchargement, PID actif d'un processus Windows, ID d'événement calendrier, etc.).
   - `user_message: str` : Synthèse concise rédigée en français pour restitution orale naturelle via la voix Live Aoede.
   - `task_id: Optional[str]` : Identifiant de la tâche asynchrone pour les statuts `started`.
   - `error_hint: Optional[str]` : Cause technique probable et action suggérée en cas de `failed`.
   - `data: dict` : Dictionnaire métier préservant la compatibilité descendante avec l'UI PWA et les tests.

2. **Couche d'Enveloppe & Migration Progressive (`normalize_result`)** :
   - Dans `core/tools/dispatcher.py`, tout résultat d'outil passe obligatoirement par `normalize_result()`.
   - Les anciens statuts disparates (`sent`, `generated`, `opened_locally`, `cart_ready`, `lance_en_arriere_plan`, etc.) sont traduits vers les 5 statuts canoniques via `LEGACY_STATUS_MAPPING`.
   - Un avertissement explicite (`logger.warning("[ToolResult] Format legacy détecté...")`) est consigné pour chaque outil renvoyant un format historique non migré.
   - Si un outil legacy renvoie un statut converti en `done` sans avoir positionné `verified=True`, le compteur `claimed_success_without_verification` est automatiquement incrémenté dans `metrics_service`.

3. **Moteur de Vérification Post-Exécution (`core/tools/verifier.py`)** :
   Chaque outil produisant un effet externe fait l'objet d'une contre-vérification matérielle avant validation du résultat. Si la vérification échoue, le statut bascule irrévocablement en `failed` même si l'appel d'API initial a renvoyé un code 200 :
   - `send_email` : Relecture effective du courriel dans le dossier IMAP `Sent` ou confirmation du `message_id` cryptographique retourné par le serveur de messagerie.
   - `generate_presentation` : Appel de l'API Google Slides (`presentations.get`) sur l'ID généré pour compter les diapositives réellement présentes (`slide_count >= min_slides`).
   - `generate_spreadsheet` : Contrôle de l'existence physique du fichier `.xlsx` sur le disque et comptage effectif des lignes (`rows > 0`).
   - `download_file` / `search_and_download_ebook` : Vérification `os.path.exists()` et validation que la taille du fichier est strictement supérieure à 0 octet.
   - `launch_application` : Récupération du PID réel auprès du PC Windows et validation de son existence active en mémoire via `psutil.pid_exists(pid)`.
   - `manage_calendar_event` : Relecture de l'événement créé ou modifié dans le calendrier.
   - `save_memory` : Relecture immédiate de la mémoire mémorisée par ID dans la base locale SQLite.
   - `open_user_browser` : Attente d'un accusé de réception explicite de `jarvis_local_agent.py` sur le poste physique (pas uniquement émission WebSocket).

4. **Protocole d'Élocution Vocale Gemini Live (`config.py`)** :
   Le prompt système interdit formellement de masquer un échec ou d'extrapoler sur une tâche non vérifiée. L'élocution est gouvernée par le statut strict du `ToolResult` :
   - `done` + `verified=True` : Jarvis annonce l'accomplissement avec certitude et cite l'evidence matérielle.
   - `done` + `verified=False` : Jarvis précise avec prudence que l'opération a été transmise mais que la confirmation matérielle n'est pas encore établie.
   - `started` : Jarvis indique exclusivement que le traitement a été lancé en arrière-plan et attend l'injection du résultat final.
   - `failed` : Jarvis énonce clairement l'échec, indique la cause probable (`error_hint`) et propose immédiatement une alternative sans minimiser.
   - `needs_user` : Jarvis pose la question ou demande la validation requise et attend la réponse de l'utilisateur.

### 8.17. Orchestration Agentique, Planificateur Multi-Étapes, Consentement Payant & Espace de Travail
1. **Exécution Agentique Antigravity (`run_agentic_task` / `run_agent_task`)** :
   - Champs : `objectif` (requis), `contexte`, `livrable_attendu`, `model_override` (`flash`\|`pro`, défaut `pro` via `_resolve_agy_model`), `effort_override` (`low`\|`medium`\|`high`, défaut `high` via `_resolve_agy_effort`), `timeout` (défaut 300 s).
   - Pré-contrôle systématique `verify_antigravity_cli_ready()` : en cas d'indisponibilité de la CLI, échec explicite (`cli_not_ready`) sans annonce de lancement.
   - Exécution par `services/agentic_runner.py` (`run_agentic`) : sortie JSON stricte, retry, puis repli `_execute_gemini_paid_fallback()` sous contrôle de `services/key_gate.py`.
2. **Planificateur Multi-Étapes (`services/task_planner.py`)** :
   - `needs_planning(utterance)` détecte les consignes multi-actions ; `decompose()` construit un `Plan` (étapes + statuts) persisté dans Redis (`_persist_plan_redis`).
   - Outils dédiés : `get_plan_status` (checklist, `pending_count`, `next_pending`) et `mark_plan_step` (`step_id`, `status`, `note`).
   - Mise à jour automatique : `update_step_with_tool_result()` est appelée par la boucle Live (`routers/voice.py`, à la réception du `ToolResult`) ; `get_plan_hud_payload()` alimente le HUD mobile, `build_continuation_prompt()` / `build_final_report_prompt()` pilotent la voix, `clear_active_plan()` clôt le plan.
   - **Règle absolue** : Jarvis ne peut jamais annoncer « c'est fait » pour l'ensemble tant que `pending_count > 0`.
3. **Consentement Payant (`confirm_paid_key`)** : résout l'action en attente (`get_pending_action()`), accorde ou révoque le consentement (`grant_paid_consent` / `revoke_paid_consent`) et ne permet la bascule payante que pour la tâche concernée. Sans action en attente, l'outil échoue avec `error_hint="no_pending_action"`.
4. **Espace de Travail Local en Lecture Seule (`list_workspace_files`, `read_workspace_file`, `search_workspace_files`)** :
   - Périmètre strict : racine `_anti_gravity` fournie par `ANTI_GRAVITY_DIR` (`config.py`), exposée par `workspace_service.ANTI_GRAVITY_ROOT = os.path.realpath(config.ANTI_GRAVITY_DIR)`, avec garde-fous `is_path_safe()` (anti-traversée) et `is_binary_file()` (détection binaire).
   - Tiers cognitif et coût inférés par `_infer_tool_tier_and_cost()` (`core/tools/dispatcher.py`) ; provenance de la donnée tracée dans l'evidence (`items_count`, `lines_shown`, `matches_count`) et bornes appliquées côté service (`depth` borné à 1‑3, `max_lines` borné à 500).
   - Aucune opération d'écriture, de modification ou de suppression n'est exposée par ces outils.
5. **Statut de Navigation Web (`browser_task_status`)** : expose l'état d'une tâche `browser_task` (`task_id`, `status`, `steps`, `goal`, `result`) ou la liste complète du registre `BROWSER_TASKS` ; complète l'outil `get_active_task_status` (vue supervision) par une vue orientée navigateur.
6. **Modification de Présentation (`modify_presentation`)** : applique une instruction vocale/texte à une présentation Google Slides existante (`presentation_id` ou `last`), avec contre-vérification d'effet réel via `core/tools/verifier.py`.

---

## 9. MATRICE DES ENDPOINTS API REST & PROTOCOLES WEBSOCKETS

### 9.1. Endpoints HTTP / REST FastAPI (Exhaustif)

> **Note d'exhaustivité (vérifiée)** : 55 routes HTTP sont déclarées par les décorateurs `@app.*` / `@router.*` (App.py : 6 ; briefing : 6 ; browser : 12 ; chat : 3 ; local_agent : 1 ; settings : 7 ; spotify : 7 ; supervision : 9 ; transport : 4). Deux paires lecture/écriture sont regroupées dans une seule ligne ci-dessous (`GET/POST /api/live-model` et `GET/POST /api/settings/paid-key`), et le montage statique `/downloads` complète le tableau. Tous les routeurs sont inclus sans préfixe **sauf** `routers/transport.py` (`APIRouter(prefix="/api/train")`). Les deux WebSockets (`/ws`, `/ws/local-agent`) sont décrits en §9.2 et §9.3.

| Méthode | Route | Description & Rôle Opérationnel | Authentification | Payload / Paramètres Types | Réponse Type |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GET** | `/` | Sert l'application PWA principale (`index.html`). | Ouvert | Aucun | Fichier HTML statique |
| **POST** | `/api/auth` | Vérifie le mot de passe maître et émet le jeton JWT. | Mot de passe | `{"password": "..."}` | `{"status": "ok", "token": "jwt..."}` |
| **GET** | `/api/auth-qr` | Émet un ticket unique de pairage QR Code (TTL 300 s). | Ouvert | Aucun | `{"status": "ok", "ticket": "qr_..."}` |
| **POST** | `/api/auth-qr` | Enregistre l'appareil après scan du QR code. | Ticket QR | `{"ticket": "qr_..."}` | `{"status": "ok", "token": "jwt..."}` |
| **POST** | `/api/auth/revoke` | Révoque immédiatement un token JWT ou un appareil via Redis. | Token JWT | `{"token_id": "...", "device_id": "..."}` | `{"status": "ok"}` |
| **GET** | `/api/verify` | Valide le jeton d'enregistrement (avec migration si ancien). | Token JWT / Cookie | Query param `?token=` ou Cookie | `{"authorized": true, "device_name": "..."}` |
| **GET** | `/api/tunnel-info` | Retourne l'URL du tunnel Cloudflare et l'IP LAN. | Token JWT | Aucun | `{"tunnel_url": "https://...", "lan_ip": "..."}` |
| **POST** | `/api/send-email` | Envoie un courriel (Stark HTML ou libre). | Token JWT | `{"subject": "...", "body": "...", "attachments": []}` | `{"status": "sent"}` |
| **GET** | `/api/emails/inbox`| Lit les courriels reçus via Gmail IMAP. | Token JWT | `count: int`, `query: str`, `unread_only: bool` | `{"emails": [...]}` |
| **GET** | `/api/emails/outbox`| Liste les courriels archivés dans le dossier sortant. | Token JWT | Aucun | `{"emails": [...]}` |
| **GET** | `/api/emails/preview/{id}`| Prévisualise le rendu HTML d'un courriel archivé. | Ouvert | Path param `email_id` | Document HTML |
| **GET** | `/api/downloads` | Liste les fichiers et e-books téléchargés. | Token JWT | Aucun | `{"downloads": [], "ebooks": []}` |
| **GET** | `/downloads/*` | Téléchargement direct des fichiers générés (.xlsx, .md). | Ouvert | Chemin du fichier | Flux binaire |
| **GET** | `/api/media/spotify/login` | Initialisation OAuth 2.0 PKCE Spotify (redirection). | Token JWT | Aucun | Redirection 307 |
| **GET** | `/api/media/spotify/callback` | Callback OAuth Spotify (échange code PKCE + stockage SQLite/Redis). | Ouvert | `?code=...&state=...` | Redirection HUD |
| **GET** | `/api/media/spotify/auth-status` | Indique si Spotify est connecté et quel utilisateur est lié. | Token JWT | Aucun | `{"authenticated": true, "display_name": str, "spotify_user_id": str, "scope": str}` |
| **GET** | `/api/media/spotify/status` | Retourne l'état temps réel du lecteur Spotify Connect. | Token JWT | Aucun | `{"is_playing": true, ...}` |
| **POST** | `/api/media/spotify/control` | Contrôle direct du lecteur Spotify (play, pause, next, like, etc.). | Token JWT | `{"action": "play", "query": "..."}` | `{"status": "done"}` |
| **GET** | `/api/media/spotify/migration/status` | Statut temps réel de la migration Deezer->Spotify. | Token JWT | Aucun | `{"status": "completed", ...}` |
| **POST** | `/api/media/spotify/migration/start` | Déclenche la migration Deezer->Spotify en tâche de fond. | Token JWT | `{"dry_run": false}` | `{"status": "started"}` |
| **GET** | `/api/browser/extensions` | Énumère les extensions Chrome installées sur la machine. | Token JWT | Aucun | `[{"id": "...", "name": "Send to Kindle"}]` |
| **POST** | `/api/browser/send-to-kindle` | Envoie un article web nettoyé sur la liseuse Kindle. | Token JWT | `{"url": "...", "title": "..."}` | `{"status": "sent"}` |
| **POST** | `/api/browser/send-file-to-kindle` | Envoie un fichier présent sur disque vers Kindle. | Token JWT | `{"file_path": "..."}` | `{"status": "sent"}` |
| **POST** | `/api/browser/upload-and-send-to-kindle` | Upload multipart d'un EPUB/PDF vers Send to Kindle. | Token JWT | Multipart form-data (`file`) | `{"status": "uploaded"}` |
| **GET** | `/api/browser/kindle-status` | Vérifie si la session Amazon Web est connectée. | Token JWT | Aucun | `{"connected": true}` |
| **POST** | `/api/browser/open-kindle-login` | Ouvre Chrome sur la page de connexion Send to Kindle. | Token JWT | Aucun | `{"status": "opened"}` |
| **POST** | `/api/open-chrome-profile` | Ouvre Chrome avec le profil persistant de Jarvis. | Token JWT | `{"url": "..."}` | `{"status": "opened"}` |
| **GET** | `/api/supervision/overview` | Données complètes de supervision (tâches, logs, appareils). | Token JWT | Aucun | `{"actions": [], "subagents": []}` |
| **GET** | `/api/supervision/windows` | Liste des fenêtres d'applications ouvertes à l'écran. | Token JWT | Aucun | `{"windows": [...]}` |
| **GET** | `/api/supervision/metrics` | Métriques agrégées d'outils, latences p95, tiers et coûts. | Token JWT | `?window=24h|7j|30j` | `{"top_tools": [], "latencies": []}` |
| **GET** | `/api/supervision/patches` | Historique des patches d'auto-guérison SRE. | Token JWT | Aucun | `{"patches": [...]}` |
| **POST** | `/api/supervision/patches/{id}/rollback` | Annule un patch déployé et restaure la version précédente. | Token JWT | Path param `id` | `{"status": "rolled_back"}` |
| **POST** | `/api/supervision/patches/{id}/approve` | Approuve un patch critique en attente de validation. | Token JWT | Path param `id` | `{"status": "applied"}` |
| **GET** | `/api/supervision/turns` | Audit des tours de dialogue (outils, transcript, fausses affirmations, durée, coupures). | Token JWT | `?since=...&limit=50` | `{"turns": [...]}` |
| **POST** | `/api/task/directive` | Injecte une consigne en direct dans la tâche active. | Token JWT | `{"directive": "..."}` | `{"status": "adapted"}` |
| **POST** | `/api/task/stop` | Interruption physique d'urgence de la tâche active. | Token JWT | `{"reason": "..."}` | `{"status": "stopped"}` |
| **GET** | `/api/chat/history` | Historique de la messagerie multimodale écrite. | Token JWT | Aucun | `{"messages": [...]}` |
| **POST** | `/api/chat/message` | Envoi d'un message texte + photo pour analyse vision. | Token JWT | Multipart (`message`, `image`) | `{"reply": "Markdown..."}` |
| **POST** | `/api/chat/clear` | Efface l'historique de clavardage. | Token JWT | Aucun | `{"status": "cleared"}` |
| **GET/POST**| `/api/live-model` | Lecture ou permutation à chaud du modèle vocal Live. | Token JWT | `{"model": "gemini-3.8-live-extended-thinking"}`| `{"current_model": "..."}` |
| **POST** | `/api/supervision/set-model` | Alias de `/api/live-model` : permutation à chaud du modèle vocal Live. | Token JWT | `{"model": "..."}` | `{"current_model": "..."}` |
| **GET/POST**| `/api/settings/paid-key` | État et verrouillage de l'encoche de clé payante. | Token JWT | `{"authorized": true}` | `{"paid_key_authorized": true}` |
| **POST** | `/api/paid-consent` | Approbation ou refus d'une demande de coût payant. | Token JWT | `{"consent": true}` | `{"status": "acknowledged"}` |
| **GET** | `/api/local-agent/status` | Statut de connexion et télémétrie du PC local Windows. | Token JWT | Aucun | `{"connected": true, "telemetry": {}}` |
| **POST** | `/api/briefing/compile` | Déclenche la compilation du Morning Briefing. | Token JWT | Aucun | `{"status": "compiled"}` |
| **GET** | `/api/briefing/today` | Récupère le Morning Briefing compilé du jour. | Token JWT | Aucun | `{"briefing": "..."}` |
| **GET** | `/api/briefing` | Alias de `/api/briefing/today` (paramètre `?refresh=true` pour forcer la recompilation). | Token JWT | `?refresh=bool` | `{"briefing": "..."}` |
| **GET** | `/api/agenda/today` | Récupère les rendez-vous du jour en cache. | Token JWT | Aucun | `{"events": [...]}` |
| **POST** | `/api/device/location` | Enregistre les coordonnées GPS du terminal mobile. | Token JWT | `{"latitude": float, "longitude": float}` | `{"status": "updated"}` |
| **GET** | `/api/device/location` | Récupère la dernière position GPS enregistrée. | Token JWT | Aucun | `{"location": {...}}` |
| **POST** | `/api/train/search` | Recherche de trajets ferroviaires et deep links directs. | Token JWT | `{"origin": "...", "destination": "...", "date": "..."}`| `{"segments": [], "deep_links": []}`|
| **POST** | `/api/train/monitor` | Active la surveillance proactive n8n d'un train. | Token JWT | `{"train_number": "...", "date": "..."}` | `{"status": "monitoring"}` |
| **POST** | `/api/train/alert` | Webhook de réception d'alerte de retard n8n. | Secret n8n | `{"train": "...", "delay_min": 15}` | `{"status": "broadcasted"}` |
| **POST** | `/api/train/reserve-local` | Préparation de réservation multi-onglets sur PC local. | Token JWT | `{"segments": [...]}` | `{"status": "opened_locally"}` |

### 9.2. Contrat WebSocket Audio Gemini Live (`/ws`)
- **URL** : `wss://jarvis.signalcraftapps.com/ws?token={jwt_token}`
- **Messages montants (Client -> Serveur)** : Chunks audio micro base64 PCM (`{"realtime_input": {"media_chunks": [...]}}`), `{"type": "mic_mute"}` / `{"type": "mic_unmute"}`.
- **Messages descendants (Serveur -> Client)** : Chunks audio modèle (`{"audio": "base64_pcm..."}`), états de l'avatar (`{"type": "status", "state": "thinking|speaking|coding..."}`), supervision (`{"type": "supervision_update"}`, `{"type": "subagent_spawn"}`), `{"type": "paid_consent_request"}`, `{"type": "browser_update"}`.

### 9.3. Contrat WebSocket Relais Agent Local PC (`/ws/local-agent`)
- **URL** : `wss://jarvis.signalcraftapps.com/ws/local-agent?token={jwt_token}`
- **Requête VPS -> PC** : `{"req_id": "rpc_123", "action": "open_browser", "params": {"url": "https://..."}}`
- **Réponse PC -> VPS** : `{"req_id": "rpc_123", "result": {"status": "success", "message": "..."}}`
- **Heartbeat PC -> VPS (toutes les 15 s)** : `{"type": "heartbeat", "cpu_percent": 12.4, "ram_percent": 48.2, "battery": {"percent": 98, "power_plugged": true}}`

### 9.4. Contrat & Intégration Spotify Web API (Connect & OAuth 2.0 PKCE)
- **Authentification & Tokens** : Authorization Code Grant avec PKCE côté VPS (`GET /api/media/spotify/login` et `/callback`). Tokens d'accès et de rafraîchissement chiffrés via clé Fernet dérivée de `JWT_SECRET_KEY` stockés dans SQLite (`spotify_tokens`) avec TTL Redis et verrou asynchrone anti-refresh concurrent.
- **Contrôle & Endpoints** : `POST /api/media/spotify/control` accepte `action: str` (`play`, `pause`, `resume`, `next`, `previous`, `seek`, `volume`, `shuffle`, `repeat`, `queue_add`, `get_queue`, `list_devices`, `set_default_device`, `transfer`, `like`, `unlike`, `add_to_playlist`, `create_playlist`, `follow_artist`, `search`, `top`, `recent`).
- **Observabilité & Vérification Réelle** : Vérification post-action via `GET /me/player` pour confirmer que `is_playing` et le volume correspondent fidèlement avant de certifier `verified=True`.

---

## 10. CYCLE DE VIE, SUPERVISION & ÉVÉNEMENTS DES SOUS-AGENTS

### 10.1. Cycle de Vie d'un Sous-Agent
Dans le cadre de missions Système 2 ou Deep Research, Jarvis instancie des sous-agents spécialisés via `spawn_subagent` :
```
                  ┌───────────────────────────────┐
                  │       SPAWN_SUBAGENT          │
                  │ (Attribution ID, rôle, tâche) │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │       UPDATE_SUBAGENT         │
                  │ (Progression, logs, métriques)│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │      COMPLETE_SUBAGENT        │
                  │ (Artefact produit, statut OK) │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │     CLEAR_ALL_SUBAGENTS       │
                  │ (Purge et archivage en fin)   │
                  └───────────────────────────────┘
```

### 10.2. Diffusion Temps Réel & Structure des Événements
Chaque transition d'état d'un sous-agent émet un événement WebSocket vers le frontend :
```json
{
  "type": "subagent_spawn",
  "agent": {
    "agent_id": "worker_incubators_174000",
    "name": "Ouvrier 1 — Pépinières & Startups",
    "role": "Prospecteur Régional",
    "activity": "research",
    "task": "Cartographie des incubateurs à São Paulo",
    "model": "gemini-3.1-pro-high",
    "status": "running",
    "progress": 35,
    "started_at": 1740001200
  }
}
```

### 10.3. Visualisation dans le HUD Mobile
Les sous-agents apparaissent dynamiquement sous forme de cartes d'activité dans le modal de supervision du HUD, avec indicateurs lumineux de progression, modèle sollicité et statut en direct.

---

## 11. INTERFACE UTILISATEUR, PWA & HUD MOBILE STARK INDUSTRIES

### 11.1. Principes Ergonomiques & Design System Cyberpunk
- **Identité Visuelle** : Palette sombre profonde (`#070B14`, `#0B0F19`), cyan électrique Stark (`#38bdf8`, `#0284c7`), accents ambre et violet néon.
- **Typographie** : Polices modernes géométriques sans-serif d'inspiration high-tech.
- **Responsive PWA** : Conçue pour une expérience native sur smartphone (iOS Safari / Android Chrome) et desktop avec support PWA (`manifest.json`, installation sur écran d'accueil).
- **Version affichée dans l'en-tête** (`static/index.html`, classe `hud-version-tag`) : `V 5.36.0 AGY MODEL ROUTING & RESILIENCE`.

### 11.2. Avatar Vectoriel SVG & Réacteur Arc Réactif
- **Tête Holographique SVG Animée** : Réacteur Arc central avec anneaux rotatifs et visualiseur audio réactif.
- **Réactivité Sonore Web Audio API** : Mesure l'amplitude du signal micro et audio en temps réel pour faire pulser la lueur du réacteur proportionnellement à l'intensité de la voix.

### 11.3. Machine à États Visuelle
L'avatar adapte ses filtres de lueur SVG et ses anneaux rotatifs selon l'état système :
- `idle` : Cyan doux pulsant lentement (repos, écoute passive).
- `listening` : Cyan électrique vif réactif à la voix de Pierre.
- `speaking` : Pulsation au rythme de la voix Aoede.
- `thinking` : Violet délibératif pulsant rapidement (moteur Système 2).
- `coding` : Vert matrice (génération de code ou Antigravity CLI).
- `browsing` : Bleu cobalt (navigation autonome Browser-Use / Chrome CDP).
- `kindle` : Indigo feutré (transfert ou lecture d'e-book).
- `music` : Ambre doré vibrant (Spotify Connect actif).
- `media` : Pourpre profond (lecture cinéma Stremio).

### 11.4. Tiroirs, Modals Interactifs & Vues Dédiées
1. **Modal de Supervision Globale** : Vue synoptique affichant les actions en cours, les sous-agents actifs, la télémétrie matérielle physique du PC Windows, les fenêtres d'applications ouvertes et la consommation des clés API.
2. **Drawer Messagerie Multimodale (Chat Drawer)** : Tiroir coulissant permettant d'échanger par écrit, de glisser-déposer des captures d'écran ou de photographier une panne avec la caméra du smartphone pour analyse visuelle immédiate par Gemini 3.8 Flash.
3. **Modal Send to Kindle Dédié** : Zone de glisser-déposer pour téléversement direct de fichiers EPUB/PDF vers la liseuse de Pierre avec statut de connexion Amazon en direct.
4. **Modal d'Arbitrage Économique** : Fenêtre d'alerte s'ouvrant automatiquement dès qu'une action payante requiert un consentement explicite.
5. **Modal de Pairage QR Code** : Affichage du QR code à usage unique pour enrôlement instantané d'un nouveau terminal mobile.

---

## 12. ANALYSE CRITIQUE : FORCES, DETTE TECHNIQUE & PISTES D'AMÉLIORATION

### 12.1. Forces Majeures de l'Architecture Actuelle
1. **Résilience et Dégradation Gracieuse Systémique** : Zéro point de défaillance unique (SPOF). Si Redis tombe, la RAM prend le relais. Si Qdrant est inaccessible, SQLite assure la recherche textuelle. Si le PC local est éteint, le Cloud headless prend le relais. Si le quota 3.1 Pro est atteint, le Tier 2 Flash-high finalise la tâche.
2. **Hybridation Cloud / Edge Réussie** : Répartition optimale entre le VPS Cloud toujours actif (cerveau permanent, RAG, sessions Gemini Live) et l'agent local Windows 11 (mains physiques, applications locales, audio, Chrome CDP).
3. **Réactivité Vocale Non-Bloquante (< 300 ms)** : Confirmation orale instantanée d'Aoede couplée à l'exécution de fond, éliminant tout sentiment de latence pour l'utilisateur.
4. **Garde-Fous Économiques et Financiers Inviolables** : Impossibilité physique d'engager des frais sans encoche active et arrêt strict avant toute transaction bancaire.
5. **Raisonnement Délibératif Système 2 Universel** : Pipeline multi-agents complet (Prospecteur, Critique, Synthèse) capable d'adresser aussi bien le code, les transports, les Google Slides que les audits stratégiques.

### 12.2. Points d'Attention & Dette Technique
1. **Gestion de Concurrence sur Profils Chrome Locaux** : Lorsque Chrome CDP est sollicité alors que Pierre navigue manuellement, des verrous de profil temporaires peuvent survenir si Chrome n'est pas lancé avec le flag de débogage distant adéquat.
2. **Volumétrie des Logs en Longue Session** : Le fichier `jarvis_agent.log` sur Windows nécessite la mise en place d'une rotation automatique des journaux (`RotatingFileHandler`).
3. **Dépendance Réseau Cloudflare** : Bien que le tunnel Zero Trust soit exceptionnellement stable, un filtrage d'entreprise sur le port 7844 impose le repli Wi-Fi local.
4. **Dette Documentaire & Risque de Dérive** : ce référentiel a historiquement dérivé (nombre d'outils, arborescence, versions). Toute évolution doit être répercutée immédiatement (règle `.agents/rules/architecture-knowledge-and-sync.md`). Sources de vérité à interroger : `core/tools/declarations.py` (49 déclarations), `App.py` + `routers/*.py` (routes), `config/models.json` (modèles et routage), `static/index.html` (classe `hud-version-tag`). **Campagne de vérification du 02/10/2026** : ces quatre sources ont été re-contrôlées par commande après correction des tests obsolètes — 49 déclarations (`name="`), 55 routes (App 6 / briefing 6 / browser 12 / chat 3 / local_agent 1 / settings 7 / spotify 7 / supervision 9 / transport 4), 34 modules pytest racine + 12 `tests/unit/` + 1 `tests/e2e/`, `MODEL_ROUTING_ENABLED` (défaut `true`, `config.py` l. 163), `cooldown_seconds = 300` (`config/models.json` l. 3), HUD `V 5.36.0 AGY MODEL ROUTING & RESILIENCE`. Suite complète relancée hors e2e (`python -m pytest tests --ignore=tests/e2e`) : **427 passed, 0 failed**.
5. **Shims Rétrocompatibles à la Racine** : `model_registry.py` (8 lignes), `model_router.py` (6 lignes), `fallback_handler.py` (15 lignes) et `prompt_builder.py` (7 lignes) ne sont que des ré-exports vers `services/model_routing/` ; ils doivent être purgés dès qu'aucun import legacy ne subsiste. **Attention (correction vérifiée)** : `google_antigravity.py` racine (564 lignes) n'est **pas** un shim mais l'implémentation réelle du wrapper agy (`AntigravityAgent`, `verify_antigravity_cli_ready`, `resolve_cognitive_tier`, `resolve_cli_model_args`) ; c'est `services/google_antigravity.py` (62 lignes) qui est la façade de ré-export.
6. **Artefacts de Sauvegarde & Scripts Jetables** : `App_backup_monolith.py` (plusieurs milliers de lignes, non importé par le runtime) et les `scripts_tmp_*.py` alourdissent le dépôt et faussent les inventaires de code ; leur archivage est recommandé.
7. **Résumé Global du Rapport de Recette Non Fiable** : `tests/run_all_tests.py` produit `tests/RAPPORT_TESTS_JARVIS.txt` (dernière campagne : 27/09/2026) dont la ligne « RESUME GLOBAL : 19/19 MODULES ET SERVICES TESTES ET 100% VALIDES » est **contredite** par son propre contenu (modules 15 « Interactive Browser & Cart », 17 « Deezer Control » et 18 « Chrome Extensions & Kindle » journalisés en `[FAILURE]`). Le compteur global du générateur doit être recalculé à partir des statuts réels avant toute communication de résultat (dette technique ouverte).
8. **Docstring Obsolète sur `launch_deep_research_gemini_web`** : la docstring de `services/deep_research_service.py` (l. 1485-1494) annonce encore un retour immédiat `{status: launched_in_background}` alors que l'implémentation **attend** `run_browser_task()` et retourne `{status: success|error}` (contrat réel décrit en §8.3). Le commentaire doit être aligné sur le code.

### 12.3. Pistes d'Évolution Stratégique & Prochaines Étapes
1. **Anticipation Proactive d'Agenda & Trajets** : Déclenchement automatique de la recherche de trains et de l'optimisation des correspondances dès qu'un rendez-vous extérieur est créé sur Google Calendar.
2. **Pont Domotique Home Assistant** : Extension du catalogue d'outils pour piloter les luminaires et thermostats connectés de Pierre.
3. **Modèles Locaux On-Premise de Secours (Ollama / Llama 3)** : Intégration d'un LLM local sur le PC Windows pour garantir des fonctions vocales de base même en cas de coupure internet totale.

---

## 13. GUIDE DU DÉVELOPPEUR & RECETTES D'INGÉNIERIE POUR AGENTS IA

> **Section conçue spécifiquement pour les LLMs et agents d'ingénierie logicielle** :
> Fournit les règles formelles, les conventions de code, les signatures types et les recettes opératoires pas-à-pas pour modifier, enrichir ou réparer le codebase de J.A.R.V.I.S.

### 13.1. Invariants d'Implémentation & Style de Code
1. **Asynchronisme Non-Bloquant Absolu** :
   - Tout appel I/O (réseau, base de données, processus, disque) DOIT être asynchrone (`async`/`await`).
   - Interdiction formelle d'utiliser `time.sleep()` (utiliser `asyncio.sleep()`) ou la bibliothèque `requests` synchrone (utiliser `httpx.AsyncClient` ou `aiohttp`).
   - Ne jamais bloquer la boucle d'événements de `routers/voice.py` : toute tâche de plus de 300 ms doit être enveloppée dans `asyncio.create_task()`.
2. **Gestion et Propagation des Erreurs** :
   - Logger systématiquement les exceptions via `logger.error(...)` ou `console_monitor.log_exception(...)`.
   - Renvoyer des dictionnaires structurés contenant au minimum `{"status": "success"|"error", "message": "..."}`.
   - Ne jamais masquer un échec critique par une fausse confirmation orale (respect strict de l'éthique Stark).
3. **Imports & Dépendances Circulaires** :
   - L'état global et les clients partagés résident exclusivement dans `core/shared_state.py`.
   - `config.py` ne doit importer aucun service ni routeur.

### 13.2. Recette 1 : Déclarer & Implémenter un Nouvel Outil Gemini Live
Pour ajouter un 39e outil ou modifier un outil existant :

1. **Étape 1 — Déclaration FunctionDeclaration dans `core/tools/declarations.py`** :
   Ajouter l'outil dans la liste renvoyée par `get_tools_list()` :
   ```python
   types.FunctionDeclaration(
       name="nom_de_l_outil",
       description=(
           "Description claire de la capacité. "
           "À UTILISER QUAND : ... "
           "NE JAMAIS UTILISER QUAND : ..."
       ),
       behavior=types.Behavior.NON_BLOCKING, # ou omettre si bloquant
       parameters=types.Schema(
           type="OBJECT",
           properties={
               "param1": types.Schema(type="STRING", description="Explication du paramètre"),
               "param2": types.Schema(type="BOOLEAN", description="Flag d'activation")
           },
           required=["param1"]
       )
   )
   ```
2. **Étape 2 — Routage dans `core/tools/dispatcher.py`** :
   Ajouter la branche correspondante dans `_execute_dispatch_tool()` :
   ```python
   elif name in ("nom_de_l_outil", "alias_historique"):
       param1 = args.get("param1", "")
       param2 = bool(args.get("param2", False))
       # Si tâche lourde non-bloquante :
       asyncio.create_task(mon_service.executer_tache(param1, websocket=websocket))
       return {
           "status": "launched_in_background",
           "message": f"Action {param1} lancée en arrière-plan.",
           "instruction_to_jarvis": "Confirme brièvement et naturellement à Pierre avec ta voix Aoede que tu t'en occupes."
       }
   ```
3. **Étape 3 — Implémentation du Service Métier dans `services/mon_service.py`** :
   Créer ou enrichir la classe de service avec exécution résiliente et gestion de repli.
4. **Étape 4 — Test Unitaire dans `tests/test_mon_outil.py`** :
   Vérifier la déclaration via `get_tools_list()` et le dispatch mocké offline.

### 13.3. Recette 2 : Ajouter un Nouvel Endpoint REST ou WebSocket
1. Créer ou ouvrir le routeur dans `routers/mon_domaine.py` :
   ```python
   from fastapi import APIRouter, Depends, Request
   from services.auth_service import auth_service

   router = APIRouter(prefix="/api/mon-domaine", tags=["MonDomaine"])

   @router.post("/action")
   async def mon_action(payload: MonModelPydantic, request: Request):
       token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
       user = await auth_service.verify_token(token)
       if not user:
           return JSONResponse(status_code=401, content={"error": "Non autorisé"})
       # Logique métier
       return {"status": "ok", "data": ...}
   ```
2. Monter le routeur dans `App.py` :
   ```python
   from routers import mon_domaine
   app.include_router(mon_domaine.router)
   ```

### 13.4. Recette 3 : Ajouter une Action RPC Local Agent PC
1. Dans `jarvis_local_agent.py`, ajouter le handler dans la boucle `handle_rpc_message` :
   ```python
   elif action == "nouvelle_action_physique":
       result = executer_action_locale(params)
       await send_rpc_response(req_id, result)
   ```
2. Dans `services/local_agent_service.py`, déclarer la méthode RPC cliente :
   ```python
   async def call_nouvelle_action(self, param: str) -> dict:
       return await self.send_rpc_command("nouvelle_action_physique", {"param": param})
   ```

### 13.5. Recette 4 : Créer une Nouvelle Mission Agentique Système 2
1. Dans `services/agentic_dispatcher.py` :
   - Ajouter le nom de mission au type `MissionType`.
   - Ajouter le générateur de prompt spécialisé dans `_build_domain_prompt()`.
   - Déclarer le palier cognitif par défaut (Tier 1, 2 ou 3) dans `google_antigravity.py:resolve_cognitive_tier_sync()`.
   - Configurer le dossier de sortie (`artifacts/` ou `downloads/`) et la notification multicanale (Aoede + Telegram).

### 13.6. Patterns d'Accès aux Bases de Données
- **PostgreSQL 16 (Pool asyncpg)** :
  ```python
  from services.memory import vector_memory
  pool = vector_memory._pg_pool
  async with pool.acquire() as conn:
      row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", mem_id)
  ```
- **SQLite Local (`jarvis_memory.db`)** :
  ```python
  import sqlite3
  from config import DB_PATH
  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()
  cur.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
  row = cur.fetchone()
  conn.close()
  ```
- **Qdrant (Embeddings Fastembed 384 dim)** :
  ```python
  from services.memory import vector_memory
  points = await vector_memory.search_semantic(query="lasers DFB", limit=5)
  ```

### 13.7. Glossaire des Variables d'Environnement (`.env` vs `config.py`)
- `JARVIS_PASSWORD` : Mot de passe maître initial pour générer les tokens d'appareils.
- `JWT_SECRET_KEY` : Clé secrète 64 octets signant les JWT (générée automatiquement si absente).
- `GEMINI_API_KEY_FREE` : Clé gratuite pour la voix Live standard et les classifications T1.
- `GEMINI_API_KEY_PAID` : Clé payante pour les modèles Pro/Claude et la vision Browser-Use.
- `CLOUDFLARE_TUNNEL_TOKEN` : Jeton d'authentification du tunnel Zero Trust permanent.
- `SMTP_USER` / `SMTP_PASSWORD` : Identifiants Gmail pour l'envoi de rapports Stark HTML.
- `REDIS_HOST` / `POSTGRES_HOST` / `QDRANT_HOST` : Hôtes Docker (défaut `127.0.0.1`).
- `VOCAL_MILESTONE_THRESHOLD_SECONDS` : Seuil en secondes pour déclencher les jalons oraux intermédiaires (défaut `90.0`).

### 13.8. Exécution des Tests & Validation Hors-Ligne
- Lancer l'intégralité des tests : `.\venv\Scripts\pytest.exe -v tests/`
- Lancer un test ciblé : `.\venv\Scripts\pytest.exe -v tests/test_architecture_service.py`
- *Règle d'or de test* : Tous les tests unitaires s'exécutent hors-ligne sans consommer le moindre centime d'API grâce aux mocks dans `tests/conftest.py`.

### 13.9. Procédure de Déploiement & Maintenance Cloud
- Après toute modification validée par les tests, exécuter :
  `.\venv\Scripts\python.exe sync_deploy.py -m "Description concise des changements"`
- Sur le serveur VPS, le service est configuré sous systemd :
  - Redémarrer : `sudo systemctl restart jarvis`
  - Statut : `sudo systemctl status jarvis`
  - Journaux en direct : `journalctl -u jarvis -f -n 100`

---

*Document de référence architecturale — Stark Industries — Système J.A.R.V.I.S. Core V 5.36.0.*
