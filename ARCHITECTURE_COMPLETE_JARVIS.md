# ✦ ARCHITECTURE TECHNIQUE & CAPACITÉS SYSTÈME DE J.A.R.V.I.S. ✦
> **Stark Industries AI Assistant — Document d'Analyse Intégrale, Spécifications Systèmes & Guide de Référence IA**
> *Référentiel architectural exhaustif destiné à l'évaluation technique, au pilotage opérationnel, au benchmark et à l'ingénierie logicielle par agents IA.*
> *Dernière révision majeure : Version 5.26.0 — Accès Lecture Seule Espace _anti_gravity (Stages, LTH, Micro-SaaS, jarvis, etc.), Service WorkspaceService étanche & Outils Live Dédiés (list_workspace_files, read_workspace_file, search_workspace_files).*

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
   - 7.3. Catalogue des 10 Actions Locales Supportées (Schémas & Paramètres)
   - 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
   - 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
   - 7.6. Télémétrie Matérielle Réelle (`psutil`)
8. [Catalogue Matriciel & Fiches des 38 Outils Unifiés (Function Calling)](#8-catalogue-matriciel--fiches-des-38-outils-unifiés-function-calling)
   - 8.1. Matrice Globale Exhaustive des 38 Outils Déclarés (Spécifications Exactes)
   - 8.2. Moteur Multi-Agents Antigravity CLI sur VPS (`ask_deep_reasoning`, `guide_active_task`, `stop_current_action`)
   - 8.3. Moteur Asynchrone Deep Research : Architecture à Double Moteur (Moteur A Gemini Web Automator + Moteur B Map-Reduce VPS)
   - 8.4. Moteur Délibératif Système 2 Transverse (Les 8 Missions Agentiques Spécialisées)
   - 8.5. Navigation Web Autonome, E-Commerce & Chrome CDP
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
2. **Zéro Paiement Bancaire Automatique** : Lors de commandes e-commerce (`prepare_web_cart_or_checkout`) ou de réservations ferroviaires (`reserver_billet_train_local`), l'agent recherche le produit, remplit le panier et les coordonnées de Pierre, puis **s'arrête impérativement** avant l'étape de validation d'achat pour que Pierre valide lui-même son paiement.
3. **Accord Préalable Obligatoire sur Téléchargement** : Avant de rapatrier un fichier ou un livre (`download_file`), Jarvis énonce la provenance et la taille estimée et attend la validation orale explicite de Pierre.
4. **Interdiction de Réciter du Code à l'Oral** : Les flux audio vocaux ne doivent jamais être pollués par la lecture de syntaxes informatiques, backticks ou symboles. Tout développement est délégué aux agents Antigravity CLI sur le VPS.
5. **Arrêt Physique Immédiat (`stop_current_action`)** : Dès que Pierre prononce un ordre d'interruption ("arrête", "stop", "annule", "laisse tomber"), l'orchestrateur coupe physiquement les sous-processus et les tâches de fond sans délai.

### 1.4. Arborescence Complète du Dépôt & Rôle de Chaque Fichier
Pour permettre à tout agent d'ingénierie d'éditer le code avec la même précision qu'un accès direct au dépôt :

```
jarvis-core/
├── App.py                               # Point d'entrée FastAPI, middleware CORS, montage statique & cycle de vie startup/shutdown
├── config.py                            # Constantes, répertoires, clés API, détection Chrome, switch payant, template prompt système
├── auth.py                              # Wrapper d'authentification légère et compatibilité
├── google_antigravity.py                # Wrapper Antigravity CLI VPS, routage cognitif 3 tiers, détection 429 et exécuteur de sous-agents
├── jarvis_local_agent.py                # Agent client WebSocket s'exécutant sur le PC Windows 11 (actions physiques, Chrome CDP, Spotify Desktop, Stremio)
├── tunnel_launcher.py                   # Gestionnaire du tunnel Cloudflare Zero Trust, fallback Quick Tunnel et LAN Wi-Fi
├── sync_deploy.py                       # Pipeline automatisé : Git commit/push + archive in-memory tar.gz + SFTP + relance systemd VPS
├── docker-compose.yml                   # Définition conteneurs Redis 7, Postgres 16, Qdrant et n8n (bound sur 127.0.0.1)
├── PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md # Dossier complet académique et pro de Pierre (Phelma SICOM, Scintil, Teem, Suède)
├── ARCHITECTURE_COMPLETE_JARVIS.md      # Le présent référentiel architectural complet maître
│
├── core/                                # Cœur applicatif transverse
│   ├── shared_state.py                  # État global partagé, clients Gemini, active_task_controller, verrou d'élocution, broadcast
│   └── tools/
│       ├── declarations.py              # Définitions Google GenAI FunctionDeclarations des 38 outils (schémas, descriptions ASR)
│       └── dispatcher.py                # Routeur central d'exécution des 38 outils, instrumentation des métriques et latences
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
│   ├── gemini_web_automator.py          # Moteur A Deep Research : pilotage gemini.google.com via Chrome CDP 9222, sans vision, map UI
│   ├── deep_research_service.py         # Moteur B Deep Research : pipeline Map-Reduce VPS (spec, MAP 3 ouvriers, REDUCE, Quality Gate)
│   ├── agentic_dispatcher.py            # Orchestrateur Système 2 universel : 8 missions spécialisées (transport, excel, healing, etc.)
│   ├── system_healing_service.py        # SRE autonome : analyse RCA, tests sandbox isolés, auto-tests, Blue/Green releases, symlink
│   ├── metrics_service.py               # Observabilité : enregistrement asynchrone Postgres/RAM des appels d'outils, latences, tiers
│   ├── browser_service.py               # Navigation Playwright headless VPS et local Chrome CDP, recherche DuckDuckGo, Send to Kindle
│   ├── download_service.py              # Téléchargement fichiers/ebooks (Anna's Archive), validation EPUB, détection liseuses USB
│   ├── email_service.py                 # Envoi SMTP Stark HTML et réception IMAP Gmail avec résolution floue des pièces jointes
│   ├── slides_service.py                # Générateur de présentations Google Slides polymorphes (7 layouts 16:9, conformité API v1)
│   ├── transport_service.py             # Calcul d'itinéraires ferroviaires France/Suède, découpage multi-segments, deep links Omio
│   ├── briefing_service.py              # Compilation morning briefing à 6h45, météo Open-Meteo, alertes et push Telegram
│   ├── user_profile_service.py          # Hot-reload de PROFIL_CANDIDATURE... via mtime, synchro SQLite et injection Live context
│   ├── unified_memory.py                # Façade unifiée : déduplication SQLite (profil) vs vectoriel Qdrant (souvenirs)
│   ├── memory.py                        # Client vectoriel Qdrant & modèle local fastembed BAAI/bge-small-en-v1.5 (384 dim)
│   ├── memory_service.py                # Service de persistance relationnelle des conversations et souvenirs
│   ├── cache.py                         # Cache Redis asynchrone, TTL, présence équipements et fallback mémoire vive dégradé
│   ├── auth_service.py                  # Cryptographie JWT HMAC-SHA256, tickets QR uniques 300s, révocation Redis et migration
│   ├── local_agent_service.py           # Client RPC émettant les requêtes vers jarvis_local_agent.py via WebSocket
│   ├── media_service.py                 # Routage des commandes audio Deezer et vidéo Stremio (URI protocol)
│   ├── supervision_service.py           # Agrégateur d'état système, sous-agents, métriques et fenêtres actives
│   ├── console_monitor.py               # Capture continue des logs et exceptions Python avec suggestions de diagnostics
│   ├── reasoning_service.py             # Pipeline d'agents Antigravity CLI et classification cognitive LLM légère Tier 1
│   ├── automation.py                    # Webhooks n8n génériques, export tableur XLSX et intégration Notion
│   ├── system_service.py                # Télémétrie système serveur/local et ouverture d'applications
│   ├── voice_injection_queue.py         # File d'attente à priorités FIFO pour injection vocale sans collision (Aoede)
│   ├── workspace_service.py             # Exploration et lecture seule stricte des projets locaux _anti_gravity (anti-traversal, filtres)
│   └── architecture_service.py          # Hot-reload de ARCHITECTURE_COMPLETE_JARVIS.md et outil live query_jarvis_architecture
│
├── db/
│   └── schema.sql                       # Schéma PostgreSQL (conversations, memories, tier_routing_log, tool_call_metrics, patches)
├── static/                              # Interface HUD PWA mobile Stark Industries (HTML, CSS cyberpunk, JS, SVGs)
├── data/
│   └── gemini_ui_map.json               # Coordonnées et sélecteurs DOM persistants pour l'automatisation gemini.google.com
└── tests/                               # Suite de validation automatisée (15+ fichiers de tests unitaires et d'intégration)
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
- **Clé Gratuite (`GEMINI_API_KEY_FREE`)** : Flux vocal standard (`gemini-3.8-live`), recherches factuelles, diagnostics légers.
- **Clé Payante (`GEMINI_API_KEY_PAID`)** : `gemini-3.8-live-extended-thinking`, `gemini-3.8-flash` haute vitesse, modèles lourds Antigravity (`gemini-3.1-pro-preview`, `claude-3-7-sonnet`, `claude-3-opus`) et vision Browser-Use.

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

### 7.3. Catalogue des 10 Actions Locales Supportées (Schémas & Paramètres)

| Action RPC | Description Opérationnelle | Paramètres Entrants | Structure Retournée |
| :--- | :--- | :--- | :--- |
| `launch_app` | Lance une application Windows physique installée. | `app_name: str` (`vscode`, `vlc`, `calc`, `notepad`, `terminal`, `stremio`) | `{"status": "success", "pid": int, "message": str}` |
| `open_browser` | Ouvre Google Chrome à l'écran sur une URL donnée. | `url: str`, `new_window: bool` (défaut False) | `{"status": "success", "message": str}` |
| `launch_media` | Déclenche la lecture multimédia dans VLC ou Stremio. | `title: str`, `content_type: str` (`movie`, `series`, `music`) | `{"status": "success", "launched": str}` |
| `spotify_launch`| Déclenche le lancement de Spotify Desktop sur le PC. | `uri: str` (opt) | `{"status": "success", "launched": "spotify"}` |
| `prepare_train_checkout` | Ouvre en parallèle les onglets Omio/Trainline préremplis. | `segments: list[dict]`, `urls: list[str]` | `{"status": "opened_locally", "count": int}` |
| `prepare_web_cart_or_checkout` | Ajoute au panier sur Chrome et s'arrête avant paiement. | `url: str`, `product: str` | `{"status": "cart_ready", "awaiting_payment": true}` |
| `interact_web_page` | Interagit unitairement avec une page web ouverte. | `url: str`, `instruction: str`, `selector: str` | `{"status": "interacted", "result": str}` |
| `execute_cdp_browser_action` | Contrôle Chrome via CDP `http://localhost:9222`. | `action: str` (`click`, `type`, `evaluate`), `selector: str`, `text: str` | `{"status": "cdp_executed", "data": any}` |
| `get_status` | Relève la télémétrie matérielle physique en direct. | Aucun | `{"cpu_percent": float, "ram_percent": float, "battery": dict}` |
| `fetch_file` | Extrait et encode en base64 un fichier local PC pour le Cloud. | `file_path: str` | `{"status": "ok", "filename": str, "data_b64": str, "size": int}` |
| `list_workspace_dir` | Liste récursivement dossiers et fichiers dans `_anti_gravity` (lecture seule). | `relative_path: str`, `depth: int`, `pattern: str` | `{"status": "success", "items": list, "items_count": int}` |
| `read_workspace_file` | Lit le contenu textuel paginé d'un fichier dans `_anti_gravity` (lecture seule). | `file_path: str`, `max_lines: int`, `offset_line: int` | `{"status": "success", "content": str, "total_lines": int}` |
| `search_workspace_files` | Recherche textuelle (grep) au sein des projets sous `_anti_gravity`. | `query: str`, `subpath: str`, `extension: str`, `max_results: int` | `{"status": "success", "matches": list, "matches_count": int}` |

### 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
Flux standards encapsulés dans `AutoFlushStream` (`buffering=1`, `flush()` immédiat) dans `jarvis_agent.log`. `sys.excepthook` capturant toute exception avec traceback horodaté.

### 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
- `start_agent_silent.vbs` : Lancement invisible en tâche de fond via `wscript.exe` (zéro invite de commande noire).
- `install_autostart.bat` & `uninstall_autostart.bat` : Inscription au démarrage automatique du registre Windows (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
- `start_local_agent.bat`, `stop_agent.bat`, `view_logs.bat`.

### 7.6. Télémétrie Matérielle Réelle (`psutil`)
Remontée périodique (toutes les 15 s) : CPU global, mémoire vive, pourcentage et statut de charge batterie, liste des processus consommateurs.

---

## 8. CATALOGUE MATRICIEL & FICHES DES 38 OUTILS UNIFIÉS (FUNCTION CALLING)

### 8.1. Matrice Globale Exhaustive des 38 Outils Déclarés

| # | Nom Officiel (`declarations.py`) | Alias Supportés (`dispatcher.py`) | Mode d'Exécution | Arguments Clés & Types | Format de Réponse (`tool_resp`) | Service Exécutant |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `stop_current_action` | `stop` | Bloquant | `reason: str` (opt) | `{"status": "stopped", "message": str, "instruction_to_jarvis": str}` | `core/shared_state.py` |
| **2** | `guide_active_task` | `guide` | Non-bloquant | `directive: str` (req) | `{"status": "adapted", "directive": str, "message": str}` | `core/shared_state.py` |
| **3** | `ask_deep_reasoning` | `deep_reasoning` | Non-bloquant | `question: str` (req), `model: str`, `intensite_reflexion: str`, `confirmed_by_user: bool` | `{"status": "launched_in_background"|"success", "summary": str}` | `services/reasoning_service.py` |
| **4** | `launch_deep_research` | `lancer_mission_deep_research` | Non-bloquant | `consigne_utilisateur: str` (req) | `{"status": "launched_in_background", "mission_spec": dict}` | `services/deep_research_service.py` |
| **5** | `search_web` | `web_search` | Bloquant | `query: str` (req) | `{"status": "success", "results": list[dict], "summary": str}` | `services/browser_service.py` |
| **6** | `run_browser_task` | `browser_task` | Non-bloquant | `goal: str` (req), `execution_target: str`, `url: str` | `{"status": "launched_in_background"|"completed", "result": str}` | `services/browser_service.py` |
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
| **19**| `prepare_web_cart_or_checkout` | `prepare_cart` | Non-bloquant | `product_or_service: str` (req), `merchant_url: str` | `{"status": "cart_ready", "awaiting_user_payment": true}` | `services/browser_service.py` |
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
| **34**| `open_train_booking` | `reserver_billet_train_local` | Non-bloquant | `operateur: str`, `urls_trajets: list[str]` | `{"status": "opened_locally", "tabs_count": int}` | `services/transport_service.py` |
| **35**| `query_jarvis_architecture` | `consulter_architecture_jarvis` | Bloquant | `sujet: str`, `section: str` | `{"status": "success", "content": str, "matched_titles": list}` | `services/architecture_service.py` |
| **36**| `draft_email_response` | `triage_et_brouillon_email` | Non-bloquant | `query: str`, `consigne: str` | `{"status": "draft_created", "file": str, "summary": str}` | `services/agentic_dispatcher.py` |
| **37**| `generate_book_summary` | `curation_livre_synthese` | Non-bloquant | `titre_livre: str` (req) | `{"status": "summary_ready", "epub_path": str}` | `services/agentic_dispatcher.py` |
| **38**| `system_self_healing` | `auto_guerison_systeme` | Non-bloquant | `motif: str`, `action: str` (`diagnose`\|`apply`\|`rollback`), `patch_id: str` | `{"status": "healing_in_progress"|"applied"|"requires_validation", "patch_id": str}` | `services/system_healing_service.py` |

### 8.2. Moteur Multi-Agents Antigravity CLI sur VPS
- **Fichiers** : `google_antigravity.py`, `services/reasoning_service.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`.
- **Exécution** : Sous-processus `agy` sur Ubuntu ARM64 adossé au jeton OAuth2 Google AI Pro (`~/.gemini/antigravity-cli/antigravity-oauth-token`), coût d'API nul.
- **Pipeline Délibératif 3 Phases** : Prospecteur → Analyste critique → Synthèse & Artefact.
- **Règles Strictes de Drapeaux** : `--model <nom>` et optionnellement `--effort <level>`. Bannissement formel de `--thinking` (qui causait `exit code 2`). Pré-contrôle `verify_antigravity_cli_ready()` avant d'annoncer `launched_in_background`.

### 8.3. Moteur Asynchrone Deep Research : Architecture à Double Moteur
Le système dispose de deux moteurs de Deep Research sélectionnés intelligemment :

#### Moteur A (Prioritaire) : Automatisation Gemini Web (`services/gemini_web_automator.py`)
- **Principe** : Automatisation directe de l'interface officielle `https://gemini.google.com` (Deep Research natif) via Chrome CDP port 9222 ou Playwright connecté au profil réel de Pierre.
- **Zéro Modèle de Vision** : Interactions déterministes par coordonnées mémorisées et inspection du DOM.
- **Cartographie UI Persistante (`data/gemini_ui_map.json`)** : Mémorise les coordonnées exactes des boutons ('Tools', 'Deep Research toggle', saisie prompt, bouton d'envoi).
- **Auto-Réparation de Dérive DOM** : Si un clic ne produit pas l'état attendu, inspection DOM par sélecteurs sémantiques (`button:has-text("Deep Research")`), recalcul des coordonnées et mise à jour automatique du JSON.
- **Polling Asynchrone Non-Bloquant** : Vérification toutes les 5s (`RESEARCH_POLL_INTERVAL`), timeout 20 min (`RESEARCH_MAX_WAIT`).
- **Livraison Conditionnelle** : Si le PC de Pierre est allumé, affichage en direct à l'écran dans Google Chrome. Si le PC est hors ligne, capture du snapshot HTML, génération de livrable et expédition par courriel Stark HTML.

#### Moteur B (Repli / Legacy) : Pipeline Map-Reduce VPS (`services/deep_research_service.py`)
Mobilisé si le Moteur A échoue ou si `use_legacy_engine=True` :
1. *Compilateur de Spécification Dynamique* : Tier 1 Flash JSON (`MissionSpec`).
2. *Override Géographique Absolu* : Bannissement formel des localisations par défaut de la mémoire (`DEFAULT_MEMORY_LOCATIONS`).
3. *Phase MAP* : 3 ouvriers Antigravity CLI parallèles (Startups/Incubateurs, Scale-ups/R&D, Grands Groupes).
4. *Phase REDUCE* : Déduplication stricte et normalisation (`NormalizedEntity`).
5. *Phase QUALITY GATE* : Agent critique appliquant 3 règles (volume, géographie, critères).
   - **Zéro Tolérance aux Livraisons Maquillées** : Si l'audit échoue après relances, `quality_gate_passed = False`. Aoede alerte immédiatement Pierre de vive voix, bannière rouge dans le rapport Markdown, et mention `[PARTIEL - AUDIT NON VALIDÉ]` dans les e-mails et messages Telegram.
6. *Livraison Déterministe Multi-Canal* : Rapport Markdown `/artifacts/`, deck Google Slides via n8n, notification Telegram et 5 jalons vocaux intermédiaires.

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

### 8.5. Navigation Web Autonome, E-Commerce & Chrome CDP
- Cibles : `vps_headless` (Playwright headless Linux), `local_chrome_cdp` (Chrome réel de Pierre sur PC Windows port 9222 avec cookies et sessions), `local_gui`.
- Assistant d'achat : remplit le panier et s'arrête strictement avant le paiement.

### 8.6. Pôle Documentaire & Présentations Google Slides Polymorphes v1
- `services/slides_service.py` : 7 layouts visuels widescreen 16:9 (`hero_title`, `key_metrics`, `cards_grid`, `split_compare`, `timeline_steps`, `quote_highlight`, `conclusion_call_to_action`).
- Conformité Google Slides API v1 (`ROUND_RECTANGLE`), suppression automatique de la diapositive blanche initiale.

### 8.7. Mobilité & Système Ferroviaire Intelligent (France & Suède)
- Décomposition multi-segments (ex: Malmö ↔ Kiruna via Stockholm Central avec TGV de jour + train de nuit).
- Deep links Omio directs et réservables. Ouverture multi-onglets simultanés sur Chrome local.
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
Afin de rendre structurellement impossible que Jarvis annonce oralement un succès non prouvé, la version 5.12.0 unifie l'intégralité des 38 outils sous un contrat canonique strict :

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

---

## 9. MATRICE DES ENDPOINTS API REST & PROTOCOLES WEBSOCKETS

### 9.1. Endpoints HTTP / REST FastAPI (Exhaustif)

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
| **POST** | `/api/task/directive` | Injecte une consigne en direct dans la tâche active. | Token JWT | `{"directive": "..."}` | `{"status": "adapted"}` |
| **POST** | `/api/task/stop` | Interruption physique d'urgence de la tâche active. | Token JWT | `{"reason": "..."}` | `{"status": "stopped"}` |
| **GET** | `/api/chat/history` | Historique de la messagerie multimodale écrite. | Token JWT | Aucun | `{"messages": [...]}` |
| **POST** | `/api/chat/message` | Envoi d'un message texte + photo pour analyse vision. | Token JWT | Multipart (`message`, `image`) | `{"reply": "Markdown..."}` |
| **POST** | `/api/chat/clear` | Efface l'historique de clavardage. | Token JWT | Aucun | `{"status": "cleared"}` |
| **GET/POST**| `/api/live-model` | Lecture ou permutation à chaud du modèle vocal Live. | Token JWT | `{"model": "gemini-3.8-live-extended-thinking"}`| `{"current_model": "..."}` |
| **GET/POST**| `/api/settings/paid-key` | État et verrouillage de l'encoche de clé payante. | Token JWT | `{"authorized": true}` | `{"paid_key_authorized": true}` |
| **POST** | `/api/paid-consent` | Approbation ou refus d'une demande de coût payant. | Token JWT | `{"consent": true}` | `{"status": "acknowledged"}` |
| **GET** | `/api/local-agent/status` | Statut de connexion et télémétrie du PC local Windows. | Token JWT | Aucun | `{"connected": true, "telemetry": {}}` |
| **POST** | `/api/briefing/compile` | Déclenche la compilation du Morning Briefing. | Token JWT | Aucun | `{"status": "compiled"}` |
| **GET** | `/api/briefing/today` | Récupère le Morning Briefing compilé du jour. | Token JWT | Aucun | `{"briefing": "..."}` |
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
- **Version affichée dans l'en-tête** : `V 5.11.0 SPÉCIFICATIONS ARCHITECTURALES & RÉFÉRENTIEL COMPLET IA`.

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

*Document de référence architecturale — Stark Industries — Système J.A.R.V.I.S. Core V 5.14.0.*
