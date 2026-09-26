# ✦ ARCHITECTURE TECHNIQUE & CAPACITÉS SYSTÈME DE J.A.R.V.I.S. ✦
> **Stark Industries AI Assistant — Document d'Analyse Intégrale & Spécifications Systèmes**
> *Destiné à l'évaluation architecturale, au benchmark technique et à l'élaboration de propositions d'optimisation par IA.*

---

## 📑 TABLE DES MATIÈRES

1. [Vue d'Ensemble & Philosophie du Projet](#1-vue-densemble--philosophie-du-projet)
2. [Topologie d'Infrastructure & Déploiement Hybride](#2-topologie-dinfrastructure--déploiement-hybride)
3. [Stack Logicielle & Persistance des Données](#3-stack-logicielle--persistance-des-données)
4. [Gouvernance des Modèles IA & Verrou Économique Physique](#4-gouvernance-des-modèles-ia--verrou-économique-physique)
5. [Le Moteur Vocal Temps Réel (Gemini Live Audio)](#5-le-moteur-vocal-temps-réel-gemini-live-audio)
6. [L'Agent Relais Local PC Windows (`jarvis_local_agent`)](#6-lagent-relais-local-pc-windows-jarvis_local_agent)
7. [Catalogue Exhaustif des Services & Outils (Function Calling)](#7-catalogue-exhaustif-des-services--outils-function-calling)
   - 7.1. Agent Autonome d'Ingénierie Logicielle (Antigravity IDE)
   - 7.2. Navigation Web Autonome & E-Commerce (Browser-Use / Playwright)
   - 7.3. Gestionnaire E-Book & Transfert Liseuses (Kindle / Kobo / Anna's Archive)
   - 7.4. Contrôleur Média & Streaming (Deezer Web Player / Stremio)
   - 7.5. Suite de Communication & Messagerie (Email Stark / IMAP / Chat Multimodal)
   - 7.6. Système de Mémoire Hybride (SQLite / Vectorielle Qdrant / Fastembed)
   - 7.7. Télémétrie, Diagnostics & Supervision Système
   - 7.8. Automatisation des Processus Externes & Pôle Documentaire (n8n Community)
   - 7.9. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
   - 7.10. Système Intelligent Ferroviaire & Mobilité (France & Suède)
8. [Matrice des Endpoints API REST & Contrats WebSockets](#8-matrice-des-endpoints-api-rest--contrats-websockets)
9. [Interface Utilisateur, PWA & HUD Mobile](#9-interface-utilisateur-pwa--hud-mobile)
10. [Analyse Critique : Forces, Dette Technique & Pistes d'Amélioration](#10-analyse-critique--forces-dette-technique--pistes-damélioration)

---

## 1. VUE D'ENSEMBLE & PHILOSOPHIE DU PROJET

### 1.1. Identité et Rôle
**J.A.R.V.I.S.** (*Just A Rather Very Intelligent System*) est un orchestrateur d'intelligence artificielle ubiquitaire conçu pour assister **Pierre Cassagnettes**. Inspiré de l'assistant emblématique de Stark Industries, le système fonctionne comme un **binôme d'égal à égal** :
- **Ton et personnalité** : Franc, direct, complice, naturel et pragmatique. Aucun formalisme servile, aucune flatterie artificielle ("zéro lèche-cul"). Il utilise un tutoiement naturel et constructif.
- **Identité vocale** : Voix féminine naturelle **Aoede** fournie par Gemini Live. Élocution humaine complète (aucune synthèse vocale robotique locale de type SAPI ou Windows SpeechSynth).
- **Annonce systématique d'action** : Tout ordre déclenchant un traitement asynchrone fait l'objet d'une confirmation orale immédiate ("*C'est bien noté Pierre, je lance la recherche...*") pour éliminer l'incertitude utilisateur.

### 1.2. Paradigme Opérationnel
Jarvis ne se limite pas à un simple chatbot conversationnel ou à un wrapper LLM :
1. **Agentique et outillé** : Il pilote de vrais navigateurs web, télécharge des fichiers, manipule le système de fichiers, exécute des commandes terminal, inspecte le code, écrit des applications et contrôle les périphériques locaux.
2. **Asynchrone et non-bloquant** : Les tâches lourdes (programmation avec Antigravity, navigation web complexe) tournent en tâche de fond (`asyncio.create_task`), permettant à l'utilisateur de continuer à dialoguer oralement avec Jarvis pendant l'exécution.
3. **Pilotable en direct** : L'utilisateur peut guider une tâche en cours (`guide_active_task`) ou l'interrompre physiquement à tout moment (`stop_current_action`).

---

## 2. TOPOLOGIE D'INFRASTRUCTURE & DÉPLOIEMENT HYBRIDE

Le système repose sur une architecture distribuée scindée entre un serveur Cloud central et un agent local PC.

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
│          │     N8N COMMUNITY    │                                                                       │
│          │    127.0.0.1:5678    │                                                                       │
│          │ Workflows auto / web │                                                                       │
│          └──────────────────────┘                                                                       │
└────────────────────────────────────────────────────▲────────────────────────────────────────────────────┘
                                                     │
                                                     │ WebSocket Sécurisé (/ws/local-agent)
                                                     │ Heartbeat & Télémétrie
                                                     │
┌────────────────────────────────────────────────────┴────────────────────────────────────────────────────┐
│                                     PC PERSONNEL WINDOWS 11 (LOCAL)                                     │
│                                                                                                         │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                         Agent Relais Local (jarvis_local_agent.py)                              │   │
│   │   • Lancement d'applications physiques (VS Code, VLC, Stremio, Notepad, Calculatrice, Terminal) │   │
│   │   • Contrôle du navigateur Google Chrome local (avec extensions et profils utilisateurs)       │   │
│   │   • Télémétrie matérielle physique (CPU réel, RAM réelle, état batterie, processus)            │   │
│   └──────────────────┬──────────────────────────────────────────────┬───────────────────────────────┘   │
│                      │                                              │                                   │
│                      ▼                                              ▼                                   │
│           ┌──────────────────────┐                       ┌──────────────────────┐                       │
│           │   DEEZER CONTROLLER  │                       │ LISEUSES PHYSIQUES   │                       │
│           │ Tampermonkey Userscript                      │ Kindle / Kobo via USB│                       │
│           │    WebSocket : 8765  │                       │ Montages lecteurs    │                       │
│           └──────────────────────┘                       └──────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Le Serveur Cloud Central (Oracle Cloud VPS)
- **Hébergement** : Instance Oracle Cloud Infrastructure (OCI) Always Free tier.
- **Ressources** : Architecture ARM64 (Ampere A1), 4 cœurs virtuels OCPU, 24 Go de mémoire vive.
- **Rôle** : Cerveau applicatif permanent, héberge le serveur FastAPI, la session Gemini Live Audio, les bases de données (Redis, Postgres, Qdrant), et le moteur de messagerie.

### 2.2. Le PC Physique Windows 11
- **Rôle** : Exécutant local de bureau. Comme le serveur cloud ne possède aucun écran physique ni affichage graphique, toutes les opérations nécessitant une interface graphique (lancer VS Code, ouvrir Google Chrome à l'écran, lancer un film dans Stremio, piloter Deezer ou détecter une liseuse USB) sont déléguées à l'agent local.

### 2.3. Topologie Réseau & Tunnels
Pour garantir l'accessibilité mobile sécurisée sans exposer les ports de la machine :
1. **Tunnel Principal** : Cloudflare Zero Trust via `cloudflared.exe`. Multiplexage HTTPS/HTTP/2 sortant vers `jarvis.signalcraftapps.com`. Aucun port d'entrée ouvert sur le pare-feu.
2. **Repli 1 (Quick Tunnel)** : En cas d'indisponibilité du domaine permanent, repli dynamique sur un sous-domaine éphémère `*.trycloudflare.com`.
3. **Repli 2 (Wi-Fi Direct LAN)** : Détection intelligente de l'interface réseau active (Wi-Fi vs Ethernet) en ignorant les adaptateurs virtuels et VPN d'entreprise (Cisco AnyConnect, TAP, Proton). Utilisé si le port Cloudflare 7844 est filtré.

### 2.4. Pipeline de Déploiement Continu (`sync_deploy.py`)
Le script `sync_deploy.py` (ou `sync_deploy.bat`) assure un cycle de mise en production instantané :
1. **Git Automation** : `git add .`, création du commit horodaté et `git push origin main`.
2. **Archive incrémentale** : Génération d'une archive `tar.gz` en mémoire excluant les artefacts lourds (`venv`, `.git`, profils Chrome, logs).
3. **Téléversement SFTP** : Connexion SSH via `paramiko` avec clé privée Ed25519 vers le VPS (`158.178.206.213`).
4. **Application & Redémarrage** : Extraction dans `/home/opc/jarvis-core`, relance sans coupure perceptible du service systemd (`sudo systemctl restart jarvis`), et vérification du statut actif.

---

## 3. STACK LOGICIELLE & PERSISTANCE DES DONNÉES

### 3.1. Composants de l'Infrastructure Docker

| Service | Image Conteneur | Port Local | Rôle Principal |
| :--- | :--- | :--- | :--- |
| **Redis 7** | `redis:alpine` | `127.0.0.1:6379` | Cache clé/valeur haute vitesse, TTL, Heartbeat présence des devices, Pub/Sub temps réel. |
| **PostgreSQL 16** | `postgres:16-alpine` | `127.0.0.1:5432` | Persistance relationnelle des conversations et des métadonnées mémoires (schéma `schema.sql`). |
| **Qdrant** | `qdrant/qdrant:latest` | `127.0.0.1:6333` | Moteur vectoriel de recherche sémantique (RAG) avec distance cosinus. |
| **n8n** | `n8nio/n8n:latest` | `127.0.0.1:5678` | Moteur d'automatisation no-code Community Edition, déclenché par webhooks locaux (montage volume partagé `/home/opc/jarvis-core/downloads` pour génération directe de fichiers). |

*Règle de sécurité stricte : tous les conteneurs Docker sont isolés et bindés exclusivement sur `127.0.0.1`. Aucun port n'est accessible publiquement sur internet.*

### 3.2. Mécanisme de Cache & Présence (`services/cache.py`)
Le service `CacheService` implémente un modèle asynchrone avec **dégradation gracieuse** :
- **Sérialisation automatique** : Stockage automatique d'objets JSON complexes avec expiration (TTL).
- **Heartbeat & Présence des Équipements** : Enregistrement de l'état du PC local (`pc_status`), des smartphones et tablettes sous la clé `jarvis:presence:{device_name}` (TTL typique 300 s).
- **Pub/Sub** : Diffusion d'événements internes sur le canal `jarvis:events:presence`.
- **Fallback mémoire RAM** : Si Redis est temporairement éteint ou inaccessible, l'application bascule automatiquement sur un dictionnaire Python en mémoire vive sans générer d'erreur bloquante.

### 3.3. Double Couche de Mémoire Persistante

```
                     ┌────────────────────────────────────────────────────────┐
                     │              REQUÊTE DE RECHERCHE MÉMOIRE              │
                     └───────────────────────────┬────────────────────────────┘
                                                 │
                                 ┌───────────────┴───────────────┐
                                 ▼                               ▼
                     ┌──────────────────────┐        ┌──────────────────────┐
                     │    PROFIL & FAITS    │        │  SOUVENIRS SÉMANTIQUES│
                     │    COURTS (SQLite)   │        │   (Qdrant + Postgres)│
                     └──────────┬───────────┘        └──────────┬───────────┘
                                │                               │
                                ▼                               ▼
                     • Nom, adresse, email           • fastembed BAAI/bge-small
                     • Pointure (42), mensurations   • Embeddings locaux 384 dim
                     • Clé payante autorisée (T/F)   • Recherche cosinus > 0.30
                     • Préférences de ton            • Fallback ILIKE SQL
```

1. **Mémoire Locale SQLite (`jarvis_memory.db`)** :
   - Table `user_profile` : Données de configuration et profil utilisateur immuable (prénom, nom, email par défaut, adresse postale, pointure de chaussure, taille de vêtement, email Kindle, flag de clé payante).
   - Table `memories` : Stockage rapide des faits généraux.
   - Table `chat_messages` : Historique des messages textuels et analyses multimodales.
2. **Mémoire Vectorielle Long-Terme (`services/memory.py`)** :
   - **Modèle d'embedding** : `BAAI/bge-small-en-v1.5` exécuté via la bibliothèque `fastembed`. Modèle local léger optimisé CPU/ARM, sans frais d'API externe. Dimension : 384.
   - **Indexation vectorielle (Qdrant)** : Stockage des vecteurs avec métadonnées (`content`, `category`, `importance`, `created_at`).
   - **Persistance structurée (PostgreSQL)** : Table `memories` typée avec enum (`préférence`, `fait`, `tâche`, `habitude`, `projet`, `contact`, `général`).
   - **Injection au démarrage de session** : Construction automatique du bloc de contexte mémoire injecté dans le prompt système de Gemini Live au lancement.

---

## 4. GOUVERNANCE DES MODÈLES IA & VERROU ÉCONOMIQUE PHYSIQUE

### 4.1. Répartition Bimodale des Clés API
Jarvis opère avec deux configurations de clés Gemini distinctes pour garantir à la fois réactivité et maîtrise des coûts :
- **Clé Gratuite (`GEMINI_API_KEY_FREE`)** : Utilisée prioritairement pour le flux vocal continu standard (`gemini-3.8-live`), les recherches web simples et les tâches ne nécessitant pas de grand modèle.
- **Clé Payante (`GEMINI_API_KEY_PAID`)** : Mobilisée pour `gemini-3.8-live-extended-thinking`, `gemini-3.8-flash` (zéro latence), les agents Antigravity lourds (`gemini-3.1-pro-preview`, `claude-3-7-sonnet`, `claude-3-opus`) et Browser-Use.

### 4.2. Règle d'Impossibilité Physique & Double Consentement
Le système applique un protocole de sécurité financière strict pour éviter toute facturation imprévue :
1. **L'Encoche Applicative (Switch UI)** : L'utilisateur active ou désactive l'autorisation dans l'interface HUD (persistée dans SQLite via `paid_key_authorized`).
   - **Impossibilité Physique** : Si l'encoche est décochée, la fonction `get_effective_paid_key()` renvoie une chaîne vide `""`. Les requêtes payantes sont physiquement impossibles au niveau du code backend.
2. **Consentement Oral Explicite** : Même si l'encoche est activée, dès qu'une action payante substantielle est sollicitée, Jarvis interrompt l'exécution immédiate, évalue le coût prévisionnel (ex: `~0.03 $`), et demande confirmation orale à Pierre avec sa voix Aoede :
   > *"Pierre, pour analyser cette architecture avec Gemini 3.1 Pro, j'ai besoin de mobiliser la clé payante (~0.03 $). M'autorises-tu à continuer ?"*
3. **Détection d'Épuisement de Quotas (429 / ResourceExhausted)** :
   Si la clé gratuite sature, le système ne bascule JAMAIS en douce sur la clé payante. Il prévient Pierre et attend son arbitrage.

---

## 5. LE MOTEUR VOCAL TEMPS RÉEL (GEMINI LIVE AUDIO)

### 5.1. Protocole Audio Full-Duplex
Le cœur interactionnel de Jarvis repose sur un canal WebSocket bidirectionnel `/ws` branché sur l'API officielle Gemini Live :
- **Format audio** : Flux PCM linéaire 16-bit, 16 kHz / 24 kHz mono.
- **Barge-in / Interruptibilité** : Si l'utilisateur commence à parler pendant que Jarvis est en train d'émettre de l'audio, le flux modèle est immédiatement interrompu côté client et serveur pour écouter l'ordre entrant.
- **Gating Micro & Silence Sender** : Lorsqu'un outil est en cours de démarrage, un mécanisme de gating et d'injection de trames de silence empêche les bruits résiduels de parasiter l'orchestrateur.

### 5.2. Boucle de Traitement des Outils (Non-Bloquante)
Dans les architectures classiques, l'appel d'un outil bloque la boucle de parole du modèle jusqu'à la fin de l'exécution. Jarvis utilise un paradigme asynchrone non-bloquant :
1. Gemini Live émet un `tool_call` (ex: `run_antigravity_task`).
2. Le backend renvoie **instantanément** un résultat préliminaire au modèle : `{"status": "launched_in_background"}`.
3. Le modèle répond immédiatement à Pierre à voix haute : *"C'est bien noté Pierre, je m'en occupe et je lance le développement avec Antigravity."*
4. La tâche lourde s'exécute en arrière-plan via `asyncio.create_task`.
5. Pendant ce temps, Pierre peut continuer à poser des questions ou discuter avec Jarvis.
6. Lorsque la tâche se termine, le backend injecte un message système dans le flux Gemini Live (`send_client_content`) pour que Jarvis annonce le résultat final à l'oral.

---

## 6. L'AGENT RELAIS LOCAL PC WINDOWS (`jarvis_local_agent`)

### 6.1. Problématique Résolue
Un serveur distant (VPS Oracle dans le cloud) ne peut pas interagir directement avec l'environnement physique de l'utilisateur : il n'a pas accès au bureau Windows, ne peut pas ouvrir de fenêtre Chrome, ne peut pas lancer de logiciel local et ne peut pas lire l'état matériel réel de la machine.

### 6.2. Fonctionnement du Relais WebSocket
L'agent `jarvis_local_agent.py` s'exécute sur le PC portable ou fixe de Pierre :
- **Liaison ascendante** : Il établit une connexion WebSocket sortante persistante vers `wss://jarvis.signalcraftapps.com/ws/local-agent` avec reconnexion automatique en boucle.
- **Protocole Request / Response** :
  - Le VPS envoie un paquet JSON : `{"req_id": "cmd_123", "action": "open_app", "params": {"app_name": "vscode"}}`.
  - L'agent local l'exécute localement et renvoie : `{"req_id": "cmd_123", "result": {"status": "success"}}`.
- **Télémétrie en temps réel** : Remontée périodique de l'utilisation CPU locale, RAM, batterie et état des processus vers le VPS.
- **Catalogue d'Applications Locales Supportées** :
  - *Développement* : Visual Studio Code (`code`), Terminaux Windows (`wt.exe`, `powershell`, `cmd`).
  - *Multimédia* : VLC Media Player, Spotify, Stremio.
  - *Bureautique & Outils* : Word, Excel, PowerPoint, Bloc-notes, Calculatrice, Explorateur de fichiers, Paint, Gestionnaire des tâches.

---

## 7. CATALOGUE EXHAUSTIF DES SERVICES & OUTILS (FUNCTION CALLING)

### 7.1. Agent Autonome d'Ingénierie Logicielle (Antigravity IDE)
- **Fichiers** : `google_antigravity.py`, `services/reasoning_service.py`.
- **Outils exposés** : `run_antigravity_task`, `guide_active_task`, `stop_current_action`, `ask_deep_reasoning`.
- **Moteur sous-jacent** : SDK Google Antigravity officiel avec agent outillé (`google.antigravity.Agent`).
- **Capacités** :
  - Création et modification chirurgicale de code source dans l'espace de travail `my-project`.
  - Inspection de fichiers (`view_file`), listing de répertoires (`list_dir`), recherche textuelle (`grep_search`).
  - Exécution de commandes shell réelles dans le terminal (compilation, tests, exécution de scripts).
- **Sélecteur Dynamique de Modèles** :
  - `gemini-3.8-flash-high/medium/low` : Modèle de développement standard rapide et économique.
  - `gemini-3.1-pro-preview` : Modèle d'ingénierie complexe, logique algorithmique avancée.
  - `claude-3-7-sonnet` / `claude-3-opus` : Résolus via Gemini 3.1 Pro haute réflexion pour l'architecture de précision.
- **Contrôle en direct** :
  - **Directives injectées en continu** : Possibilité de parler à Jarvis pendant qu'il code pour affiner l'instruction sans redémarrer (`active_task_controller["queue"]`).
  - **Arrêt d'urgence** : Interruption physique immédiate du thread de développement sur consigne orale (*"stop"*, *"arrête de coder"*).

### 7.2. Navigation Web Autonome & E-Commerce (Browser-Use / Playwright)
- **Fichier** : `services/browser_service.py`.
- **Outils exposés** : `search_web`, `run_browser_task`, `interact_web_page`, `prepare_web_cart_or_checkout`, `open_user_browser`, `set_browser_link`, `download_ebook_annas_archive`.
- **Routage Intelligent Hybride (VPS Headless vs PC Local GUI)** :
  - Orchestré par le flag `execution_target: Literal["vps_headless", "local_gui"]` présent sur toutes les fonctions de navigation.
  - **Mode Headless VPS (`vps_headless`)** : Les opérations légères (scraping de texte, lecture d'articles, vérification de liens, recherche DuckDuckGo, téléchargement d'EPUB sur Anna's Archive) s'exécutent en tâche de fond directement sur le serveur Cloud VPS via Playwright en mode 100% headless, sans réveiller le PC de Pierre.
  - **Mode GUI PC Local (`local_gui`)** : Les opérations nécessitant une session connectée (Amazon, Fnac), un affichage visuel à l'écran, ou la validation d'un panier d'achat (`prepare_web_cart_or_checkout`) sont automatiquement déléguées au script `jarvis_local_agent.py` sur le PC Windows de Pierre via le canal WebSocket sécurisé `/ws/local-agent`.
- **Capacités** :
  - **Recherche web enrichie** : Recherche DuckDuckGo avec extraction intelligente de deep links de transport (SNCF Connect, Trainline, Skyscanner, Booking).
  - **Agent autonome Vision (Browser-Use)** : Agent web autonome guidé par modèle vision (Gemini Flash Vision) capable de naviguer de manière indépendante sur des sites dynamiques, de remplir des formulaires complexes et de contourner les bannières de cookies.
  - **Repli Playwright direct** : Si Browser-Use échoue, bascule sur un script Playwright direct avec capture d'écran périodique (`/static/latest_screenshot.jpg`).
  - **Assistant d'achat autonome sécurisé (`prepare_web_cart_or_checkout`)** :
    - Recherche de produits (Amazon, Fnac, Decathlon, etc.).
    - Ajout au panier de la référence exacte.
    - Préremplissage automatique des coordonnées de Pierre Cassagnettes (nom, prénom, adresse, code postal, téléphone, pointure 42).
    - **Garde-fou bancaire absolu** : L'agent s'arrête STRICTEMENT avant l'étape de paiement final et ouvre Chrome à l'écran pour que Pierre valide lui-même son achat.

### 7.3. Gestionnaire E-Book & Transfert Liseuses (Kindle / Kobo / Anna's Archive)
- **Fichiers** : `services/download_service.py`, `services/browser_service.py`.
- **Outils exposés** : `download_file`, `search_and_download_ebook`, `send_to_ereader`, `send_page_to_kindle`, `send_file_to_kindle`, `list_chrome_extensions`.
- **Capacités** :
  - **Moteur E-Book Anna's Archive** : Recherche automatique par titre/auteur, détection et filtrage de la langue demandée (FR ou EN), vérification de validité structurelle du conteneur EPUB (`mimetype`, `META-INF/container.xml`).
  - **Détection Liseuse USB** : Analyse automatique des lecteurs de disques montés sous Windows pour identifier les périphériques Kindle, Kobo ou Bookeen et y copier directement les fichiers.
  - **Amazon Send to Kindle Web Direct** : Automatisation Playwright sur `amazon.com/sendtokindle` avec profil persistant connecté (`.jarvis_shopping_profile`) pour téléverser sans friction des fichiers jusqu'à 200 Mo.
  - **Extension Chrome Send to Kindle** : Détection des extensions installées dans le profil Chrome de Pierre et envoi d'articles web épurés sans publicité.
  - **Garde-fou de téléchargement** : Obligation d'obtenir l'accord oral préalable de Pierre avant de lancer un téléchargement (taille et provenance annoncées).

### 7.4. Contrôleur Média & Streaming (Deezer Web Player / Stremio)
- **Fichiers** : `deezer_bridge.py`, `services/media_service.py`.
- **Outils exposés** : `play_music_deezer`, `play_video_stremio`.
- **Contrôle Deezer 100% sans compte développeur payant** :
  - **Bridge WebSocket bidirectionnel** (`127.0.0.1:8765`) couplé à un userscript Tampermonkey (`deezer_controller.user.js`) injecté sur l'onglet `deezer.com`.
  - **Contrôles supportés** : Lecture, pause, bascule, morceau suivant, morceau précédent, activation/désactivation aléatoire (*shuffle*), réglage précis du volume (0-100%).
  - **Résolution sémantique intelligente** : Détection automatique des intentions vocales :
    - *"Mets mon Flow"* -> navigation instantanée vers `/channels/flow`.
    - *"Mets mes coups de cœur"* -> lecture de `/channels/loved-tracks`.
    - *"Joue Daft Punk"* -> recherche via l'API publique Deezer et sélection du morceau ou de l'album optimal.
- **Cinéma & Séries Stremio** :
  - Recherche du titre via l'API Stremio (Cinemeta).
  - Sélection automatisée du meilleur flux vidéo 1080p le plus fluide et léger (via scraper Torrentio).
  - Lancement immédiat de l'application Stremio sur la vidéo ciblée via protocole URI `stremio:///detail/...`.

### 7.5. Suite de Communication & Messagerie (Email Stark / IMAP / Chat Multimodal)
- **Fichiers** : `services/email_service.py`, `services/chat_service.py`.
- **Outils exposés** : `send_email`, `read_emails`, API `/api/chat/*`.
- **Envoi d'E-mails (SMTP)** :
  - Génération de rapports HTML élégants au format **Stark Industries Executive Report** (palette sombre, typographie soignée, badges d'état).
  - Support des pièces jointes locales et inclusion automatique de la dernière capture d'écran système.
  - Archivage local systématique de tous les courriels émis dans `outbox_emails/`.
- **Lecture d'E-mails (IMAP Gmail)** :
  - Connexion SSL sécurisée à la boîte de réception de Pierre (`pierrecassagnettes@gmail.com`).
  - Filtrage par mot-clé, expéditeur ou statut non lu.
  - Décodage des en-têtes MIME, extraction de snippets textuels et détection des pièces jointes pour restitution orale par Jarvis.
- **Messagerie & Analyse Multimodale (Chat Drawer)** :
  - Interface de clavardage permettant à l'utilisateur d'envoyer des captures d'écran, photos de schémas ou pannes techniques.
  - Traitement multimodal par **Gemini 3.8 Flash** : OCR complet, identification des composants, diagnostic pas-à-pas et réponse structurée en Markdown.

### 7.6. Système de Mémoire Hybride
- **Fichiers** : `services/unified_memory.py` (Façade), `services/memory_service.py` (SQLite), `services/memory.py` (Vectoriel).
- **Outils exposés** : `remember_user_fact`, `recall_user_memories`, `memoriser_information`.
- **Façade Unifiée (`UnifiedMemoryManager`)** : Orchestration transparente avec déduplication des données de profil immuables dans SQLite, et double indexation asynchrone non-bloquante pour la recherche sémantique (Qdrant) avec dégradation gracieuse (fallback SQLite textuel).

### 7.7. Télémétrie, Diagnostics & Supervision Système
- **Fichiers** : `services/system_service.py`, `services/supervision_service.py`, `services/console_monitor.py`.
- **Outils exposés** : `get_system_status`, `launch_application`, `check_console_errors`.
- **Supervision en temps réel (`SupervisionService`)** :
  - Enregistre et diffuse l'état d'activité de chaque outil (ID action, nom de l'outil, modèle IA, coût estimé, horodatage, étapes de progression).
  - Énumération des fenêtres ouvertes sur le PC Windows (via `EnumWindows` sous Windows).
  - Détection et agrégation des erreurs consoles et exceptions Python (`ConsoleMonitor`) avec diagnostic automatisé et suggestions de réparation.

### 7.8. Automatisation des Processus Externes, Pôle Documentaire & Présentations Avancées (n8n Community)
- **Fichiers** : `services/automation.py`, `services/slides_service.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`, `docs/N8N_GUIDE.md`, `docs/n8n_workflows/documents_suite.json`.
- **Outils exposés** : `executer_action_externe`, `generer_fichier_tableur`, `generer_presentation`, `notion_enregistrer`, `get_active_task_status`.
- **Pôle Documentaire & Présentations Google Slides Élaborées** :
  1. **Génération de tableurs Excel (.xlsx) (`generer_fichier_tableur`)** :
     - Convertit des listes JSON de données (comptabilité, budgets, benchmarks, listes de suivi) en classeurs Excel `.xlsx` propres.
     - Webhook n8n dédié : `POST http://127.0.0.1:5678/webhook/document-spreadsheet`.
     - Nœuds n8n : Webhook -> Formater Données -> Spreadsheet File (binaire xlsx) -> Enregistrer dans `/home/opc/jarvis-core/downloads/` -> Respond to Webhook.
     - Accès immédiat au fichier généré via le point de montage `/downloads/<nom_fichier>`.
  2. **Génération de présentations Google Slides Expertes & Esthétiques (`generer_presentation`, `services/slides_service.py`)** :
     - **Moteur de recherche approfondie (`SlidesService`)** : Plutôt que de créer un deck vide ou précipité, le service élabore un plan rigoureux, agrège des faits historiques et chiffres vérifiés (ex: Bitcoin : 21M de limite, SHA-256/PoW, halving avril 2024 à 3.125 BTC, ETF spot, Lightning Network, réserve de valeur), et trie les éléments d'impact.
     - **Design moderne 16:9 & Thèmes colorimétriques** : Cartes graphiques, typographies hiérarchisées, pastilles métriques (`key_metric`), séparateurs visuels et notes d'orateur complètes avec palette adaptée (`bitcoin`/`gold`, `stark`, `corporate`, `cyber`, `dark`).
     - **Élimination de la diapositive blanche par défaut** : La requête Google Slides `batchUpdate` génère les nouvelles diapositives enrichies puis supprime l'éventuelle diapositive vierge initiale ("Cliquez ici pour ajouter un titre").
     - **Pipeline n8n hybride** : Création initiale de la présentation Google Slides, injection par l'API REST `batchUpdate` des diapositives stylisées et export optionnel au format PPTX.
  3. **Prise de notes et to-do Notion (`notion_enregistrer`)** :
     - Ajoute des entrées structurées (notes rapides `note`, items de to-do list `todo`, fiches de veille `veille`, fiches projet `projet`) avec étiquettes dans Notion.
     - Webhook n8n dédié : `POST http://127.0.0.1:5678/webhook/notion-entry`.
     - Nœuds n8n : Webhook -> Formater Entrée Notion -> Notion Database Page Create -> Respond to Webhook.
  4. **Suivi d'Activité & Explication Vocale en Direct (`get_active_task_status`)** :
     - Permet à Jarvis d'interroger en direct l'état des opérations en arrière-plan (recherche documentaire, structuration du plan, génération Google Slides ou tâches Antigravity).
     - Lorsque Pierre demande oralement *"Qu'est-ce que tu es en train de faire ?"* ou *"Où en es-tu ?"*, Jarvis invoque cet outil et explique avec sa voix Aoede avec précision et naturel l'étape en cours et son avancement.
- **Passerelle vers n8n & Function Calling Gemini Live** :
  - **Déclaration formelle** : Intégrés dans `core/tools/declarations.py` avec `behavior=types.Behavior.NON_BLOCKING`.
  - **Exécution asynchrone non-bloquante** : Le dispatcheur (`core/tools/dispatcher.py`) renvoie instantanément un accusé de réception pour que Jarvis confirme immédiatement à l'oral avec sa voix Aoede le lancement du travail, puis délègue la requête au webhook HTTP local en tâche de fond (`asyncio.create_task`).
  - **Mise à jour HUD & Retour vocal final** : Durant la génération, le HUD affiche la progression, et dès la finalisation, l'URL de la présentation est projetée à l'écran (`set_browser_link`) et annoncée oralement par Jarvis.
  - **Résilience absolue** : Gestion systématique des exceptions (timeout 30s, erreurs de connexion, JSON malformé) évitant tout crash du canal vocal principal.
  - Workflows n8n exportables et packagés dans `docs/n8n_workflows/documents_suite.json`.

### 7.9. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
- **Fichiers** : `services/briefing_service.py`, `routers/briefing.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`, `docs/n8n_workflows/time_and_briefing.json`.
- **Outils exposés** : `agenda_gerer_evenement`, `creer_rappel_push`, `demander_morning_briefing`.
- **Architecture & Fonctionnalités** :
  1. **Agenda Samsung & Google Calendar (`agenda_gerer_evenement`)** :
     - Création, décalage et consultation des événements synchronisés nativement entre Google Calendar et l'application Samsung Calendar du smartphone de Pierre.
     - Webhook n8n dédié : `POST http://127.0.0.1:5678/webhook/agenda-event`.
     - Intégration directe avec le nœud officiel Google Calendar n8n avec synchronisation bidirectionnelle.
  2. **Capture Vocale & Rappels Push Mobiles (`creer_rappel_push`)** :
     - Prise de note orale instantanée et programmation d'un rappel push ou notification immédiate sur smartphone via le Stark Bot Telegram de Pierre.
     - Webhook n8n dédié : `POST http://127.0.0.1:5678/webhook/schedule-push-reminder` (liaison hôte 127.0.0.1).
     - Architecture n8n : Webhook -> Code (calcul du délai d'attente : immédiat 1s si `maintenant`/`immédiat`, ou temporisé à échéance) -> Nœud Wait -> Nœud Telegram officiel Stark Bot (`chatId: 6849746502`).
     - Paramètre `echeance` optionnel : valeur par défaut `maintenant` pour les notifications instantanées. Aliases de routage direct supportés (`telegram`, `telegram-notification`, `envoyer_notification_telegram`).
  3. **Morning Briefing Stark Industries (`demander_morning_briefing`)** :
     - Routine quotidienne compilée à 7h00 (via Cron n8n ou sur demande) agrégeant :
       * Météo locale en temps réel (Open-Meteo avec dégradation locale gracieuse).
       * Rendez-vous du jour issus de l'agenda mis en cache.
       * E-mails urgents non lus via IMAP Gmail (`services/email_service.py`).
       * État de santé des systèmes et présence des périphériques (`CacheService` / `SystemService`).
     - Résumé d'impact de 3-4 phrases courtes et percutantes au ton Stark Industries / Aoede.
     - Mise en cache Redis sous `jarvis:briefing:today` (TTL 16 heures).
     - Restitution vocale sans aucune latence au premier "Bonjour" de la journée.
  - Workflows n8n packagés dans `docs/n8n_workflows/time_and_briefing.json`.

### 7.10. Système Intelligent Ferroviaire & Mobilité (France & Suède)
- **Fichiers** : `services/transport_service.py`, `routers/transport.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`, `docs/n8n_workflows/train_monitoring.json`.
- **Outils exposés** : `rechercher_train`, `surveiller_train`, `reserver_billet_train_local`.
- **Capacités & Architecture** :
  1. **Recherche d'Itinéraires & Deep Links Paramétrés (`rechercher_train`)** :
     - Supporte l'ensemble des gares françaises (Paris, Lyon, Marseille, Bordeaux, Lille, Nantes, Strasbourg, etc.) et suédoises (Malmö, Stockholm, Göteborg, Lund, Uppsala, etc.).
     - Génération intelligente et automatisée de deep links directs avec slugs et paramètres d'horaires :
       * *France* : SNCF Connect (`https://www.sncf-connect.com/app/home/search/od/...`) et Trainline (`https://www.thetrainline.com/book/results?...`).
       * *Suède* : SJ direct (`https://www.sj.se/sv/sok-resa.html?...`), Trafikverket Open Data (`https://www.trafikverket.se/trafikinformation/tag/...`), et Skånetrafiken (`https://www.skanetrafiken.se/sok-resa/...`).
     * Scraper headless Playwright optimisé sur VPS pour extraire instantanément horaires, durées de trajet, correspondances et prix indicatifs sans solliciter le poste utilisateur.
     * **Dispatching non-bloquant** : Jarvis confirme immédiatement la prise en charge à voix haute avec sa voix Aoede, annonce le meilleur trajet dès disponibilité et pousse le bouton d'ouverture directe sur l'interface PWA via l'événement `browser_update` / `set_browser_link`.
  2. **Surveillance Proactive en Temps Réel (`surveiller_train`)** :
     - Déclenche une boucle de veille asynchrone orchestrée par n8n (`docs/n8n_workflows/train_monitoring.json`).
     - Interroge toutes les 10 minutes les flux Trafikverket Open Data (requêtes XML/JSON) ou SNCF GTFS-RT jusqu'au départ du train.
     - Évalue les retards, annulations et changements de voie/quai de départ.
     - Dès qu'un retard dépasse 5 minutes ou qu'une annulation est signalée :
       * Déclenche un webhook entrant sur Jarvis (`POST /api/train/alert`).
       * Injection instantanée dans la session Gemini Live active pour qu'Aoede prévienne oralement Pierre en direct.
       * Alerte push visuelle sur le HUD mobile et courriel exécutif Stark en copie de secours.
  3. **Préparation Sécurisée de Réservation Locale (`reserver_billet_train_local`)** :
     - **Respect absolu de l'isolation de sécurité** : exploration et scraping headless sur le VPS cloud ; interaction transactionnelle exclusivement sur le PC Windows physique via `execution_target="local_gui"`.
     - Délégué à `jarvis_local_agent.py` sur le PC Windows de Pierre via le canal WebSocket `/ws/local-agent` (action `prepare_train_checkout`).
     - Ouvre Google Chrome avec la session connectée de Pierre, charge le trajet prérempli jusqu'à l'écran de sélection de place / paiement.
     - **Garde-fou bancaire absolu** : aucune validation d'achat automatique, Pierre valide lui-même son règlement.

---

## 8. MATRICE DES ENDPOINTS API REST & CONTRATS WEBSOCKETS

### 8.0. Architecture Modulaire des Routeurs (`routers/` & `core/`)
Le serveur principal `App.py` est allégé (< 190 lignes) et instancie l'application FastAPI, configure les middlewares, initialise le cycle de vie (`startup`/`shutdown`) et monte les sous-routeurs étanches :
- **`routers/voice.py`** : Canal vocal WebSocket `/ws` (Gemini Live full-duplex, streaming PCM bidirectionnel, barge-in, gestion de quota gratuit/payant, injection dynamique de mémoire long-terme).
- **`routers/local_agent.py`** : WebSocket `/ws/local-agent` et statut `/api/local-agent/status` pour le pilotage du PC Windows de Pierre.
- **`routers/chat.py`** : Endpoints `/api/chat/*` pour la messagerie écrite multimodale et l'analyse visuelle de photos/captures.
- **`routers/media.py`** : Endpoints Deezer Web Player (`/api/media/deezer/*`) et ponts multimédia.
- **`routers/browser.py`** : Endpoints de navigation, extensions Chrome, Send to Kindle, téléchargements et gestion des emails (`/api/emails/*`, `/api/send-email`).
- **`routers/supervision.py`** : Endpoints `/api/supervision/*` (overview, fenêtres ouvertes) et injection de directives/arrêts d'urgence (`/api/task/*`).
- **`routers/briefing.py`** : Endpoints du Morning Briefing (`/api/briefing/*`) et de l'agenda synchronisé (`/api/agenda/*`).
- **`routers/transport.py`** : Endpoints de mobilité et transports ferroviaires (`/api/train/search`, `/api/train/monitor`, `/api/train/alert`, `/api/train/reserve-local`).
- **`routers/settings.py`** : Configuration dynamique (`/api/live-model`, `/api/settings/paid-key`, `/api/paid-consent`, `/api/tunnel-info`).
- **`core/shared_state.py`** : État partagé, clients API Gemini, gestion des exceptions de quota, diffusion temps réel.
- **`core/tools/declarations.py`** : Déclarations formelles des schémas d'outils Gemini Live Function Calling.
- **`core/tools/dispatcher.py`** : Routeur de dispatching asynchrone non-bloquant des appels d'outils vers les services métier.

### 8.1. Endpoints HTTP / REST


| Méthode | Route | Description & Rôle | Authentification |
| :--- | :--- | :--- | :--- |
| **GET** | `/` | Sert l'application PWA principale (`index.html`) | Ouvert |
| **POST** | `/api/auth` | Authentification maître par mot de passe & émission JWT | Mot de passe |
| **GET** | `/api/auth-qr` | Génération d'un ticket unique de pairage QR Code éphémère (TTL 5 min Redis) | Ouvert |
| **POST** | `/api/auth-qr` | Enregistrement d'un nouvel appareil via ticket QR Code unique (émission JWT) | Ticket QR |
| **POST** | `/api/auth/revoke` | Révocation immédiate d'un token JWT ou d'un appareil via Redis | Token |
| **GET** | `/api/verify` | Vérifie la validité du token JWT (avec migration transparente si ancien token) | Token |
| **GET** | `/api/tunnel-info` | Retourne les URLs du tunnel Cloudflare et l'IP LAN | Token |
| **POST** | `/api/send-email` | Envoi d'un courriel (format Stark Industries ou libre) | Token |
| **GET** | `/api/emails/inbox` | Lecture des e-mails reçus via IMAP | Token |
| **GET** | `/api/emails/outbox` | Liste des courriels archivés dans le dossier sortant | Token |
| **GET** | `/api/downloads` | Liste des fichiers téléchargés sur le serveur | Token |
| **GET** | `/downloads/*` | Téléchargement direct des fichiers générés (tableurs .xlsx, présentations .pptx) | Ouvert |
| **POST** | `/api/media/deezer/control` | Contrôle direct de Deezer (play, pause, next, volume) | Token |
| **GET** | `/api/media/deezer/status` | Retourne l'état du lecteur Deezer (titre, artiste, pochette) | Token |
| **GET** | `/api/media/deezer/userscript` | Fournit le script Tampermonkey pour le navigateur | Ouvert |
| **GET** | `/api/browser/extensions` | Liste les extensions Chrome installées sur la machine | Token |
| **POST** | `/api/browser/send-to-kindle`| Envoie une page web nettoyée sur la liseuse Kindle | Token |
| **POST** | `/api/browser/upload-and-send-to-kindle` | Upload multipart d'un EPUB/PDF vers Amazon Send to Kindle | Token |
| **GET** | `/api/browser/kindle-status` | Vérifie si la session Amazon Web est connectée | Token |
| **GET** | `/api/supervision/overview` | Données complètes de supervision (tâches, logs, devices) | Token |
| **GET** | `/api/supervision/windows` | Liste des fenêtres d'applications ouvertes à l'écran | Token |
| **POST** | `/api/task/directive` | Injection d'une consigne en direct dans la tâche de code | Token |
| **POST** | `/api/task/stop` | Interruption d'urgence de la tâche active | Token |
| **GET** | `/api/chat/history` | Historique de la messagerie multimodale écrite | Token |
| **POST** | `/api/chat/message` | Envoi d'un message texte + photo pour analyse vision | Token |
| **POST** | `/api/chat/clear` | Effacement de l'historique de chat | Token |
| **GET/POST**| `/api/live-model` | Lecture et permutation dynamique du modèle vocal Live | Token |
| **GET/POST**| `/api/settings/paid-key` | État et verrouillage de l'encoche de clé payante | Token |
| **POST** | `/api/paid-consent` | Approbation/refus d'une requête de coût payant | Token |
| **GET** | `/api/local-agent/status` | Statut de connexion du PC local physique de Pierre | Token |
| **POST** | `/api/briefing/compile` | Compilation et mise en cache du Morning Briefing (déclenché par cron n8n à 07:00) | Token |
| **GET** | `/api/briefing/today` | Récupération instantanée du Morning Briefing compilé du jour | Token |
| **GET** | `/api/agenda/today` | Consultation des rendez-vous d'agenda du jour mis en cache | Token |
| **POST** | `/api/train/search` | Recherche d'itinéraires et deep links trains (France & Suède) | Token |
| **POST** | `/api/train/monitor` | Déclenchement de la surveillance proactive d'un train via n8n | Token |
| **POST** | `/api/train/alert` | Webhook de réception d'alerte perturbation ferroviaire n8n | Ouvert (Secret) |
| **POST** | `/api/train/reserve-local` | Préparation de réservation sur le PC local Windows | Token |

### 8.2. Canaux WebSockets

#### 1. Canal Voix Principal (`/ws`)
- **Rôle** : Liaison full-duplex streaming audio entre le microphone/haut-parleur du client et Gemini Live.
- **Messages montants (Client -> Serveur)** :
  - Chunks audio PCM (`realtime_input`).
  - Événements de contrôle (`mic_mute`, `mic_unmute`).
- **Messages descendants (Serveur -> Client)** :
  - Chunks audio Gemini Live.
  - Changements d'état de l'avatar (`status` : idle, listening, speaking, thinking, coding, browsing, kindle, music).
  - Événements d'outils (`tool_start`, `task_progress_oral`, `task_completed`, `task_cancelled`).
  - Demandes d'autorisation payante (`paid_consent_request`).
  - Mises à jour de capture d'écran du navigateur (`browser_update`).

#### 2. Canal Relais Agent Local PC (`/ws/local-agent`)
- **Rôle** : Dialogue permanent entre le VPS Cloud et le script `jarvis_local_agent.py` sur le PC Windows.
- **Fonctionnalités** : Ordres d'exécution de commandes système, télémétrie matérielle et retours d'exécution.

---

## 9. INTERFACE UTILISATEUR, PWA & HUD MOBILE

### 9.1. Principes de Design & Ergonomie
L'interface de Jarvis a été développée selon des standards graphiques d'inspiration cyberpunk et Stark Industries :
- **Dark Mode Profond** : Palette articulée autour des noirs profonds (`#070B14`, `#0B0F19`), de bleus cyan électriques (`#38bdf8`, `#0284c7`) et d'accents violets/ambrés.
- **Avatar Vectoriel SVG Animé** : Tête holographique cyberpunk dotée de pupilles réactives, d'un visualiseur audio et d'un anneau énergétique tournant. Les filtres de lueur SVG changent dynamiquement de couleur selon l'activité (cyan pour le repos, violet pour la réflexion, vert pour le code, ambre pour Deezer, indigo pour Kindle).
- **Halo Audio Réactif** : Utilisation de la Web Audio API pour mesurer le volume en temps réel et pulser le réacteur proportionnellement à l'intensité de la voix.

```
┌────────────────────────────────────────────────────────────────────────┐
│ [●] STARK AI CORE     V 3.0 AUTONOMOUS AGENT      [KINDLE] [CHAT] [●]  │
├────────────────────────────────────────────────────────────────────────┤
│  ⚡ CLÉ PAYANTE : [  ON  ] 🔒 VERROUILLÉE                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                                ( ✦ )                                   │
│                        AVATAR HOLOGRAPHIQUE                            │
│                        Réacteur Arc Animé                              │
│                                                                        │
│                [ ÉTAT : DÉVELOPPEMENT EN COURS... ]                    │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  ACTIVITÉ RÉCENTE :                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ ⚡ Implémentation du code dans main.py...                         │  │
│  │ Modèle : Gemini 3.8 Flash (High) | Clé Payante (~0.005 $)        │  │
│  │ [ STOP ] [ GUIDER EN DIRECT : "Ajoute un bouton de retour..." ]  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────┤
│  LIEN ACTIF : [ OUVRIR LE TRAIN PARIS-LYON 14H08 ]                     │
├────────────────────────────────────────────────────────────────────────┤
│   [ 🎙️ MICROPHONE ACTIF ]              [ ⚙️ SUPERVISION COMPLÈTE ]     │
└────────────────────────────────────────────────────────────────────────┘
```

### 9.2. Composants & Modals Interactifs
- **Modal de Supervision Globale** : Affiche les actions en cours d'exécution, l'historique des requêtes API, la répartition des coûts, l'état de présence des machines (PC local, Mobile) et les fenêtres Windows actives.
- **Drawer Messagerie Multimodale** : Fenêtre latérale permettant de converser par écrit, d'uploader des photos par glisser-déposer ou via la caméra du smartphone, avec rendu Markdown complet et zoom sur les images.
- **Modal Send to Kindle Dédié** : Zone de dépôt rapide de fichiers EPUB/PDF pour téléversement direct vers la liseuse de Pierre avec statut de connexion Amazon en direct.
- **Modal d'Arbitrage Économique** : Dialogue d'alerte s'ouvrant automatiquement dès qu'une action payante requiert un consentement explicite.

---

## 10. ANALYSE CRITIQUE : FORCES, DETTE TECHNIQUE & PISTES D'AMÉLIORATION

> *Cette section met en lumière les points névralgiques du système afin de permettre à une intelligence artificielle d'évaluation de formuler des recommandations d'évolution ciblées et pertinentes.*

### 10.1. Forces Majeures de l'Architecture Actuelle
1. **Résilience et Dégradation Gracieuse** : Presque aucun composant n'est un point de défaillance unique. Si Redis tombe, la RAM prend le relais. Si Qdrant est hors-ligne, SQLite assure la mémoire. Si Browser-Use échoue, Playwright prend le relais.
2. **Hybridation Cloud / Edge Réussie** : La séparation claire entre le serveur Cloud (pensée, mémoire, routage) et l'agent local Windows (mains physiques, applications locales, audio) offre le meilleur des deux mondes.
3. **Exécution Asynchrone Non-Bloquante** : La capacité de Jarvis à répondre immédiatement à la voix tout en lançant des développements lourds en arrière-plan procure une expérience utilisateur d'une fluidité exceptionnelle.
4. **Garde-Fous Économiques et de Sécurité** : Le principe d'impossibilité physique sur la clé payante et l'interdiction absolue de procéder au paiement automatique dans les paniers e-commerce rendent le système sûr et prévisible.


---

*Document généré pour le projet J.A.R.V.I.S. Core — Stark Industries.*
