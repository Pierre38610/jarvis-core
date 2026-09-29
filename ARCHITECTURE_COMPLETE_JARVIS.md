# ✦ ARCHITECTURE TECHNIQUE & CAPACITÉS SYSTÈME DE J.A.R.V.I.S. ✦
> **Stark Industries AI Assistant — Document d'Analyse Intégrale, Spécifications Systèmes & Guide de Référence IA**
> *Référentiel architectural exhaustif destiné à l'évaluation technique, au pilotage opérationnel, au benchmark et à l'ingénierie logicielle par agents IA.*
> *Dernière révision majeure : Version 5.10.0 — Intégration Native de la Base de Connaissances & Dossier de Candidature Pierre Cassagnettes (Phelma SICOM, Scintil Photonics, Teem Photonics, Øresund, DSP, Photonique, ML appliqué).*

---

## 📑 TABLE DES MATIÈRES

1. [Vue d'Ensemble & Philosophie du Projet](#1-vue-densemble--philosophie-du-projet)
   - 1.1. Identité, Rôle & Relation d'Égal à Égal
   - 1.2. Paradigme Opérationnel & Principes Directeurs
   - 1.3. Les 5 Garde-Fous Inviolables
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
   - 5.4. Protocole de Résilience Quota-Aware & Dégradation Gracieuse (429)
6. [Le Moteur Vocal Temps Réel (Gemini Live Audio)](#6-le-moteur-vocal-temps-réel-gemini-live-audio)
   - 6.1. Protocole Audio Full-Duplex & Streaming PCM
   - 6.2. Assemblage Dynamique de l'Instruction Système & Contexte
   - 6.3. Modèles Vocaux Actifs & Permutation à Chaud
   - 6.4. Boucle de Traitement des Outils Asynchrone Non-Bloquante (< 300 ms)
   - 6.5. Règle d'Or de Canal Unique & Verrou d'Élocution Anti-Coupure
   - 6.6. Gestion des Interruptions (Barge-In) & Gating Micro
7. [L'Agent Relais Local PC Windows (`jarvis_local_agent`)](#7-lagent-relais-local-pc-windows-jarvis_local_agent)
   - 7.1. Problématique Résolue & Rôle Exécutant Physique
   - 7.2. Protocole WebSocket RPC & Reconnexion Résiliente
   - 7.3. Catalogue des 10 Actions Locales Supportées
   - 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
   - 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
   - 7.6. Télémétrie Matérielle Réelle (psutil)
8. [Catalogue Matriciel & Fiches des 38 Outils Unifiés (Function Calling)](#8-catalogue-matriciel--fiches-des-38-outils-unifiés-function-calling)
   - 8.1. Matrice Globale Exhaustive des 38 Outils Déclarés
   - 8.2. Moteur Multi-Agents Antigravity CLI sur VPS (`ask_deep_reasoning`, `guide_active_task`, `stop_current_action`)
   - 8.3. Moteur Universel Deep Research Map-Reduce (`launch_deep_research`)
   - 8.4. Moteur Délibératif Système 2 Transverse (Missions Spécialisées)
   - 8.5. Navigation Web Autonome, E-Commerce & Chrome CDP
   - 8.6. Pôle Documentaire & Présentations Google Slides Polymorphes v1
   - 8.7. Mobilité & Système Ferroviaire Intelligent (France & Suède)
   - 8.8. Gestionnaire E-Book, Liseuses Physiques & Send to Kindle
   - 8.9. Contrôleur Média & Streaming (Deezer Web Player & Stremio)
   - 8.10. Suite de Communication & Messagerie Stark
   - 8.11. Système de Mémoire Hybride (SQLite, Qdrant & Fastembed)
   - 8.12. Télémétrie, Diagnostics & Supervision Système
   - 8.13. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
   - 8.14. Connaissance Architecturale Dynamique & Auto-évaluation
9. [Matrice des Endpoints API REST & Protocoles WebSockets](#9-matrice-des-endpoints-api-rest--protocoles-websockets)
   - 9.1. Endpoints HTTP / REST FastAPI
   - 9.2. Contrat WebSocket Audio Gemini Live (`/ws`)
   - 9.3. Contrat WebSocket Relais Agent Local PC (`/ws/local-agent`)
   - 9.4. Contrat WebSocket Deezer Controller (`127.0.0.1:8765`)
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

---

## 1. VUE D'ENSEMBLE & PHILOSOPHIE DU PROJET

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
Pour garantir une sécurité absolue et une maîtrise totale de l'environnement :

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
│           │   DEEZER CONTROLLER  │                       │ LISEUSES PHYSIQUES   │                       │
│           │ Tampermonkey Userscript                      │ Kindle / Kobo via USB│                       │
│           │    WebSocket : 8765  │                       │ Montages lecteurs    │                       │
│           └──────────────────────┘                       └──────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Le Serveur Cloud Central (Oracle Cloud VPS)
- **Hébergement** : Instance Oracle Cloud Infrastructure (OCI) Always Free tier.
- **Ressources matérielles** : Architecture ARM64 (`aarch64` Ampere Altra), 4 cœurs virtuels OCPU, 24 Go de mémoire vive physique, stockage SSD NVMe.
- **Système d'exploitation** : Ubuntu 22.04 LTS.
- **Adresse IP publique** : `158.178.206.213`.
- **Rôle fonctionnel** : Cerveau applicatif permanent disponible 24h/24. Il héberge le serveur FastAPI, orchestre les sessions Gemini Live Audio, exécute les agents Antigravity CLI sur VPS, fait tourner la stack Docker (Redis, Postgres, Qdrant, n8n) et gère la messagerie SMTP/IMAP.

### 2.3. Le PC Physique Windows 11 & Rôle Exécutant
- **Rôle fonctionnel** : Exécutant matériel de bureau. Ne disposant d'aucun affichage graphique direct sur le VPS Cloud, toute opération nécessitant une interface visuelle à l'écran (ouvrir VS Code, manipuler Google Chrome avec sessions authentifiées, lancer un film dans Stremio, piloter Deezer ou détecter une liseuse branchée en USB) est déléguée à l'agent local.

### 2.4. Topologie Réseau, Tunnels Cloudflare & Résilience Réseau
Le système utilise `tunnel_launcher.py` pour assurer une accessibilité permanente sans ouvrir le moindre port d'entrée sur la box ou le routeur :
1. **Tunnel Principal (Cloudflare Zero Trust)** : Établi via `cloudflared.exe` avec jeton d'authentification (`CLOUDFLARE_TUNNEL_TOKEN`). Il multiplexe le trafic HTTPS/WSS sortant vers le nom d'hôte officiel `jarvis.signalcraftapps.com`. Aucun port d'écoute externe n'est requis sur le pare-feu.
2. **Repli 1 (Quick Tunnel)** : En cas d'indisponibilité du nom de domaine officiel, repli dynamique instantané sur un sous-domaine éphémère `*.trycloudflare.com`.
3. **Repli 2 (Wi-Fi Direct LAN avec Filtrage Avancé)** : Détection intelligente de l'adresse IPv4 physique active via inspection `ipconfig /all`. Le script filtre et ignore formellement les adaptateurs virtuels et VPNs d'entreprise (Cisco AnyConnect, TAP Windows, ProtonVPN, OpenVPN). Utilisé si le port Cloudflare 7844 est filtré sur le réseau local.
4. **Vérification Stricte de Joignabilité** : Le lanceur effectue une requête HTTP de sonde réelle pour éliminer à 100% l'erreur 1033 ("Tunnel indisponible"). Les URLs validées sont écrites dans `tunnel_url.txt` et `static/tunnel_url.json`.

### 2.5. Pipeline de Déploiement Continu & Synchronisation (`sync_deploy.py`)
Le déploiement en production est automatisé par le script `sync_deploy.py` (déclenchable via `sync_deploy.bat "Message de commit"`) :
1. **Contrôle Git & Commit** : Exécute `git add .`, produit un commit horodaté et pousse sur GitHub (`git push origin main`).
2. **Génération d'Archive en Mémoire** : Compile à la volée une archive `tar.gz` en mémoire vive (`io.BytesIO`) en excluant automatiquement les dossiers lourds et sensibles (`venv`, `.git`, `.jarvis_chrome_profile`, `.jarvis_shopping_profile`, logs, caches pytest).
3. **Téléversement SFTP Sécurisé** : Établit une liaison SSH via `paramiko` avec clé privée cryptographique Ed25519 vers le VPS Oracle (`158.178.206.213`).
4. **Extraction & Relance sans Coupure** : Décompresse les fichiers dans `/home/opc/jarvis-core`, applique les permissions d'exécution, redémarre le service systemd (`sudo systemctl restart jarvis`) et vérifie le statut actif (`active (running)`).

---

## 3. STACK LOGICIELLE, CONTENEURS DOCKER & PERSISTANCE DES DONNÉES

### 3.1. Matrice des Conteneurs Docker (`docker-compose.yml`)

| Service | Image Conteneur | Port Local | Volumes Persistants | Rôle & Spécificités Techniques |
| :--- | :--- | :--- | :--- | :--- |
| **Redis 7** | `redis:alpine` | `127.0.0.1:6379` | `redis_data:/data` | Cache clé/valeur haute performance, TTL, états de présence des appareils (`jarvis:presence:*`), Pub/Sub temps réel, blacklist de révocation JWT. Mémoire max : 2 Go (LRU). |
| **PostgreSQL 16**| `postgres:16-alpine` | `127.0.0.1:5432` | `postgres_data:/var/lib/postgresql/data` | Persistance relationnelle des conversations et des métadonnées mémoires (schéma `schema.sql`). |
| **Qdrant** | `qdrant/qdrant:latest` | `127.0.0.1:6333` | `qdrant_data:/qdrant/storage` | Moteur vectoriel pour recherche sémantique RAG (Distance Cosinus, collection `jarvis_memories`, vecteurs 384 dim). |
| **n8n Community**| `n8nio/n8n:latest` | `127.0.0.1:5678` | `n8n_data:/home/node/.n8n`<br>`/home/opc/jarvis-core/downloads` | Moteur d'automatisation no-code. Montage direct du dossier de téléchargement partagé pour générer des fichiers XLSX et interagir avec Google Slides, Calendar, Telegram. |

*Règle de sécurité inviolable : Tous les conteneurs sont strictement liés sur `127.0.0.1`. Aucun port n'est exposé publiquement sur l'interface réseau externe.*

### 3.2. Mécanisme de Cache, Présence & Pub/Sub (`services/cache.py`)
Le service `CacheService` implémente un modèle asynchrone fondé sur `redis.asyncio` avec **dégradation gracieuse intégrale** :
- **Sérialisation JSON Transparente** : Stockage et désérialisation automatique des dictionnaires et listes complexes avec expiration (TTL).
- **Heartbeat & Présence des Équipements** : Enregistrement de la présence du PC local (`pc_status`), des smartphones et tablettes sous `jarvis:presence:{device_name}` (TTL typique 300 s).
- **Pub/Sub Temps Réel** : Canal de diffusion `jarvis:events:presence` pour notifier les autres sous-systèmes des changements d'état matériel.
- **Mode Dégradé Local en RAM** : Si le serveur Redis est temporairement arrêté ou inaccessible, le service bascule instantanément sur un dictionnaire Python en mémoire vive sans bloquer ni lever d'exception critique.

### 3.3. Schéma Relationnel PostgreSQL 16 (`db/schema.sql`)
La persistance relationnelle est orchestrée par PostgreSQL 16 avec extension cryptographique `pgcrypto` :

```sql
-- Extension UUID pour identifiants uniques
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Table des conversations
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ,
    summary     TEXT        NOT NULL DEFAULT '',
    tags        TEXT[]      DEFAULT '{}'
);

-- Enum des catégories de mémoire long-terme
CREATE TYPE memory_category AS ENUM (
    'préférence', 'fait', 'tâche', 'habitude', 'projet', 'contact', 'général'
);

-- Table des souvenirs long-terme liés à Qdrant
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

-- Table de journalisation des arbitrages cognitifs & résilience 429
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
CREATE INDEX IF NOT EXISTS idx_tier_routing_chosen_tier ON tier_routing_log (chosen_tier);
CREATE INDEX IF NOT EXISTS idx_tier_routing_final_tier ON tier_routing_log (final_tier);

-- Table d'instrumentation et d'observabilité des appels d'outils
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
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tool_name ON tool_call_metrics (tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_status ON tool_call_metrics (status);
CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tier ON tool_call_metrics (cognitive_tier);

-- Table du journal des patches d'auto-guérison et SRE autonome
CREATE TABLE IF NOT EXISTS patches_auto_appliques (
    id                  TEXT            PRIMARY KEY,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    incident_motif      TEXT            NOT NULL,
    target_file         TEXT            NOT NULL,
    patch_diff          TEXT            NOT NULL,
    test_suite          TEXT,
    test_results        JSONB           NOT NULL DEFAULT '{}',
    status              TEXT            NOT NULL, -- 'applied', 'requires_validation', 'rolled_back', 'failed_tests', 'failed_syntax'
    is_critical         BOOLEAN         NOT NULL DEFAULT FALSE,
    release_path        TEXT,
    previous_release_path TEXT,
    applied_at          TIMESTAMPTZ,
    rolled_back_at      TIMESTAMPTZ,
    details             JSONB           NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_created_at ON patches_auto_appliques (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_target_file ON patches_auto_appliques (target_file);
CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_status ON patches_auto_appliques (status);
```

### 3.4. Moteur Vectoriel Qdrant & Embeddings Fastembed (`services/memory.py`)
- **Modèle d'embedding local** : `BAAI/bge-small-en-v1.5` exécuté via la bibliothèque `fastembed`. Modèle ultra-léger et optimisé pour processeurs CPU/ARM64, s'exécutant à coût zéro sans appel API externe. Dimension vectorielle : **384**.
- **Collection vectorielle** : `jarvis_memories` indexée avec métrique `Distance.COSINE`.
- **Compatibilité Multi-Versions Qdrant** : Prise en charge native des versions modernes de `qdrant-client` (>= 1.10.0) via `client.query_points(...)` et extraction de `ScoredPoint`, avec rétrocompatibilité automatique sur l'ancienne méthode `.search(...)`.
- **Résilience de Conversion Vectorielle** : Conversion robuste gérant à la fois les générateurs, tableaux `numpy.ndarray` et itérables Python.
- **Seuil de pertinence** : Filtre cosinus > 0.30 avec repli automatique sur une recherche textuelle SQL `ILIKE`.

### 3.5. Mémoire Locale Structurée SQLite (`jarvis_memory.db`)
Fichier SQLite local assurant la persistance rapide hors-cloud :
1. **Table `user_profile`** : Données de configuration immuables de Pierre Cassagnettes (`nom`, `prénom`, `email` par défaut, `adresse`, `pointure` de chaussure : 42, `taille` de vêtement, `kindle_email`, et état du switch `paid_key_authorized`).
2. **Table `memories`** : Stockage relationnel simple pour consultation textuelle directe.
3. **Table `chat_messages`** : Historique complet des conversations écrites multimodales et métadonnées d'images.

### 3.6. Façade Unifiée de Mémoire Long-Terme (`services/unified_memory.py`)
La classe `UnifiedMemoryManager` fusionne harmonieusement les deux couches :
- **Déduplication & Arbitrage** : Si une information correspond à une clé de profil reconnue (`pointure`, `adresse`, etc.), elle est enregistrée dans SQLite `user_profile`. Les autres faits sont indexés dans Qdrant et PostgreSQL en arrière-plan non-bloquant.
- **Injection Dynamique au Démarrage de Session** : Méthode `build_live_context_prompt()` qui agrège le profil de Pierre, les faits récents, le dossier de candidature et le résumé de l'architecture pour constituer le bloc d'instruction injecté dans Gemini Live au démarrage de chaque flux vocal.

### 3.7. Service de Connaissance Approfondie du Profil de Candidature (`services/user_profile_service.py`)
Ce service garantit que J.A.R.V.I.S. dispose à tout instant d'une maîtrise intégrale, vivante et contextuelle de l'ensemble des éléments académiques, techniques et professionnels de Pierre Cassagnettes :
1. **Source Dynamique & Surveillance Hot-Reload (`PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md`)** :
   - Surveillance de l'empreinte `mtime` du fichier à la racine du projet. Dès que Pierre enrichit ou édite son profil, les sections et la synthèse en mémoire vive sont rechargées instantanément à la volée.
2. **Découpage Structuré en 10 Chapitres Stratégiques** :
   - *Fiche d'identité & Coordonnées* : Élève-ingénieur 3e année (Bac+5 / MSc, Promo 2026), Malmö (Suède) / Grenoble (France), téléphone (+33 7 69 52 44 30), e-mail (`pierrecassagnettes@gmail.com`), Permis B & A2, disponibilité immédiate région Øresund sans visa (citoyen UE).
   - *Objectifs & Cibles de Stage* : Stage de Fin d'Études (PFE) / Master's Thesis de 5 à 6 mois (dès le 18 janvier 2026). Domaines cibles : DSP / Audio / Acoustique, Machine Learning appliqué aux signaux physiques, Photonique intégrée & Optoélectronique, Automatisation de bancs de test SCPI/PyVISA, Développement logiciel scientifique Python CustomTkinter, Embarqué.
   - *Formation Académique* : Grenoble INP – Phelma (Majeure SICOM - Signal, Image, Communication & Machine Learning), Prépa des INP, Bac S Mention Très Bien (Champollion). Référentiel compétences C1 à C6 et certification Sulitest.
   - *Expériences Professionnelles Réelles* :
     - *Scintil Photonics (Stage R&D 2025, 13 sem.)* : Suite de 4 IHM CustomTkinter divisant par 5 le temps de dépouillement sur wafer 200 mm (multiprocessing adapté), caractérisation pulsée athermique 500 ns supprimant le roll-off thermique sur puces SHIP™ (lasers DFB III-V/Si), alignement spectral OSA (< 1.0 GHz) et asservissement EEPROM embarqué, qualification EVK, diagnostic SCPI HP 81104A.
     - *Teem Photonics (Stage Opérateur Salle Blanche 2024, 8 sem.)* : Normes ISO, conformité ESD, assemblage micro-lasers pulsés passifs déclenchés.
     - *Trésorier BDE La Prépa des INP (2023-2024)* : Gestion budgétaire, partenariats, logistique d'événements.
   - *Matrice des Compétences Techniques* : Python avancé, C, MATLAB, Bash, Git, LaTeX, DSP, RIN, SNR, filtres RIF/RII, ML appliqué, composants photoniques, micro-contrôleurs, Langues (Français maternel, Anglais C1 pro, Italien B1/B2).
   - *Centres d'intérêt* : Volley-ball, Basket-ball, Course à pied, Moto A2, reproduction sonore et acoustique.
   - *Guide Rédactionnel & Templates* : Guides d'adaptation sectorielle, cold emails en anglais et français, aide-mémoire d'entretiens.
3. **Synchronisation Automatique Multi-Couches** :
   - *SQLite au Démarrage (`App.py`)* : Amorçage automatique des clés dans `user_profile` et des faits structurés dans `memories`.
   - *Injection Live Vocal (`routers/voice.py`)* : Synthèse exécutive injectée dans le prompt système de chaque session Gemini Live.
   - *Routage Cognitif Sémantique (`unified_memory.recall`)* : Interception immédiate de toute requête concernant Pierre, son CV, ses stages, ses compétences pour renvoyer les sections exactes avec un score de 1.0.
   - *Agents Antigravity & Deep Research* : Disponibilité intégrale pour le moteur `deep_research_service` et la mission `email_drafting` d'`agentic_dispatcher`.

---

## 4. ARCHITECTURE DE SÉCURITÉ, CRYPTOGRAPHIE & GESTION DES APPAREILS

### 4.1. Moteur d'Authentification Cryptographique (`services/auth_service.py` & `auth.py`)
J.A.R.V.I.S. met en œuvre une infrastructure d'authentification robuste conforme aux standards Stark Industries :

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
- **Algorithme de signature** : HMAC-SHA256 (`HS256`).
- **Structure du Payload JWT** :
  ```json
  {
    "device_id": "dev_a1b2c3d4e5f6",
    "device_name": "iPhone 15 Pro de Pierre",
    "role": "admin",
    "iat": 1740000000,
    "exp": 1747776000,
    "jti": "jwt_tok_9f8e7d6c5b4a"
  }
  ```
- **Durée de validité** : 90 jours par défaut (`JWT_EXPIRATION_DAYS`).
- **Génération Sécurisée de la Clé Secrète** : Si `JWT_SECRET_KEY` est absente de `.env`, `AuthService` génère une clé cryptographique de 64 octets aléatoires encodés en URL-safe (`secrets.token_urlsafe(64)` soit 86 caractères) et la persiste immédiatement dans le fichier `.env`.

### 4.3. Registre des Terminaux & Empreintes Matérielles (`authorized_devices.json`)
Chaque appareil autorisé fait l'objet d'un profilage enregistré :
- `device_id` (identifiant unique persistant généré côté client).
- `device_name` (libellé lisible, ex: "PC Windows Bureau", "Pixel 8 Pro").
- `ip_address` (dernière adresse IP observée).
- `user_agent` (signature de navigateur/OS).
- `registered_at` et `last_seen` (horodatages de traçabilité).
- `status` (`approved` ou `revoked`).

### 4.4. Protocole de Pairage QR Code Zero-Touch à Usage Unique
Pour connecter un smartphone en 2 secondes sans saisir le mot de passe maître sur écran tactile :
1. Le client déjà connecté demande un ticket de pairage (`GET /api/auth-qr`).
2. Le serveur génère un ticket aléatoire unique (`qr_ticket_{secrets.token_hex(16)}`), l'enregistre dans Redis sous `jarvis:qr_ticket:{ticket}` avec un TTL strict de **300 secondes (5 minutes)**, et génère un QR code à l'écran.
3. Le smartphone scanne le QR code, qui déclenche un `POST /api/auth-qr` avec le ticket.
4. Le serveur valide le ticket, le **consomme immédiatement** (suppression de Redis pour empêcher toute réutilisation), enregistre l'appareil et émet le token JWT signé.

### 4.5. Révocation Instantanée & Blacklist Redis
- En cas de perte ou de compromission d'un appareil, l'administrateur déclenche `POST /api/auth/revoke`.
- Le token (`jti`) et/ou l'identifiant matériel (`device_id`) sont inscrits dans Redis sous `jarvis:revoked_tokens:{jti}` et `jarvis:revoked_devices:{device_id}`.
- Tout appel subséquent (REST ou WebSocket) est rejeté immédiatement avec code HTTP 401. En cas de panne Redis, un set en mémoire vive assure la continuité du contrôle.

### 4.6. Migration Rétrocompatible Transparente des Anciens Jetons
Pour éviter toute déconnexion intempestive lors de la mise à jour du moteur d'authentification :
- Lorsqu'une requête arrive avec un ancien token hexadécimal en clair issu de `authorized_devices.json`, `AuthService` valide l'ancien token, émet à la volée un nouveau JWT signé, met à jour le cookie client et purge l'ancien token de la base.
- Un cache de transition (`_migrated_tokens_cache`) prévient toute condition de course lors de requêtes simultanées.

---

## 5. GOUVERNANCE DES MODÈLES IA, VERROU ÉCONOMIQUE & ROUTAGE COGNITIF EN 3 TIERS

### 5.1. Répartition Bimodale des Clés API (Gratuite vs Payante)
Jarvis opère avec deux configurations de clés Gemini distinctes pour concilier performance continue et maîtrise budgétaire :
- **Clé Gratuite (`GEMINI_API_KEY_FREE`)** : Réservée au flux vocal continu standard (`gemini-3.8-live`), aux recherches web élémentaires et aux diagnostics légers.
- **Clé Payante (`GEMINI_API_KEY_PAID`)** : Déployée pour `gemini-3.8-live-extended-thinking`, `gemini-3.8-flash` haute vitesse, les agents Antigravity lourds (`gemini-3.1-pro-preview`, `claude-3-7-sonnet`, `claude-3-opus`) et la navigation visuelle Browser-Use.

### 5.2. Verrou Physique Applicatif & Double Consentement Oral
1. **L'Encoche Matérielle Applicative (Switch UI)** : L'utilisateur active ou désactive l'autorisation dans l'interface HUD (persistée dans SQLite via `paid_key_authorized`). Si la case est décochée, `get_effective_paid_key()` renvoie une chaîne vide `""`. Aucune requête payante ne peut physiquement être émise.
2. **Double Consentement Oral Explicite** : Même lorsque l'encoche est cochée, dès qu'une action payante substantielle est sollicitée, Jarvis interrompt l'exécution immédiate, évalue le coût estimatif (ex: `~0.03 $`) et demande confirmation orale à Pierre :
   > *"Pierre, pour analyser cette architecture avec Gemini 3.1 Pro, j'ai besoin de mobiliser la clé payante (~0.03 $). M'autorises-tu à continuer ?"*
3. **Détection d'Épuisement de Quotas (429 / ResourceExhausted)** : Si la clé gratuite sature, le système ne bascule JAMAIS en douce sur la clé payante sans accord explicite.

### 5.3. Routage Cognitif Dynamique en 3 Paliers (Tiers 1, 2, 3)
Pour préserver le quota glissant de 5 heures Google AI Pro tout en garantissant des temps de réponse adaptés :

| Palier (Tier) | Modèle Résolu | Réflexion (Thinking) | Cibles Principales & Cas d'Usage | Latence Typique | Impact Quota 5h |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TIER 1 — Rapidité & Économie** | `gemini-3.8-flash` | `low` (ou minimal) | `doc_sync`, `book_curation`, `email_simple`, diagnostics de routine, vérifications d'état, classification de routage. | 1 à 3 secondes | Négligeable (0 % Pro) |
| **TIER 2 — Raisonnement Tactique** | `gemini-3.8-flash` | `high` (renforcé) | `transport_optimizer`, `spreadsheet_modeler`, `email_drafting`, `memory_consolidation`, requêtes libres par défaut. | 4 à 10 secondes | Nul sur le quota 3.1 Pro |
| **TIER 3 — Délibération Système 2** | `gemini-3.1-pro` | `high` (délibératif) | `deep_research` multi-sources, `system_healing` critique, `code_refactoring`, ingénierie complexe. | 20 à 60 secondes | Consommation mesurée sur Pro |

#### Mécanismes d'Arbitrage Ordonnés (`resolve_cognitive_tier`)
Face aux transcriptions vocales imparfaites et à la variabilité du langage naturel, l'ancienne heuristique par seuil de caractères (> 600) et regex a été remplacée par un arbitrage strict en 3 niveaux :
1. **Priorité 1 — Surcharge Explicite Utilisateur (Overriding Prioritaire)** :
   - Consignes vocales de rapidité : "*fais une passe rapide*", "*réponds vite*", "*sans réfléchir*", "*juste les grandes lignes*" → Verrouillage immédiat au **TIER 1** (`is_override=True`).
   - Consignes vocales de profondeur : "*prends tout ton temps*", "*analyse en profondeur*", "*mode délibératif*", "*cherche à fond*" → Verrouillage immédiat au **TIER 3** (`is_override=True`).
   - Paramètre d'API explicite `intensite_reflexion` (`rapide` → T1, `tactique` → T2, `approfondie` → T3) ou modèle cible forcé (`gemini-3.1-pro`, `gemini-3.8-flash`).
2. **Priorité 2 — Table de Correspondance Déterministe (`mission_type`)** :
   - Routage automatique selon le type d'agent ou mission déclarée (`deep_research` → T3, `code_refactoring` → T3, `doc_sync` → T1, etc.).
3. **Priorité 3 — Classifieur LLM Léger Tier 1 (`classify_query_tier_with_llm`)** :
   - Pour toute requête libre non couverte par les priorités 1 et 2, Jarvis consulte un modèle Tier 1 ultra-rapide (`gemini-3.8-flash` avec timeout de 3,5s et `response_mime_type="application/json"`).
   - Le modèle retourne un objet JSON strict :
     ```json
     {
       "tier": 1 | 2 | 3,
       "reason": "Explication concise de la décision de complexité cognitive"
     }
     ```
   - En cas d'erreur de parsing, d'indisponibilité ou de dépassement de délai, un repli déterministe sécurisé vers le **TIER 2** (`gemini-3.8-flash-high`) est automatiquement appliqué.

#### Télémétrie & Traçabilité Post-Hoc (`tier_routing_log`)
Chaque routage est persisté de manière asynchrone et non-bloquante dans la table relationnelle PostgreSQL `tier_routing_log` :
- `query_text` : Prompt ou consigne d'entrée.
- `chosen_tier` : Palier initialement sélectionné par le classifieur ou la surcharge (1, 2 ou 3).
- `reason` : Justification fournie par le LLM Tier 1 ou identification de la règle d'override.
- `final_tier` : Palier réellement exécuté (permettant d'identifier un fallback 429 subséquent).
- `latency_ms` : Durée totale de traitement de la tâche de raisonnement.
- `override_manuel` : Booléen (`true` si consigne explicite Pierre ou paramètre d'intensité forcé).
Cette table permet de mesurer a posteriori les erreurs de routage, la pertinence du classifieur et la fréquence des dégradations de service.

### 5.4. Protocole de Résilience Quota-Aware & Dégradation Gracieuse (429)
En cas de saturation du quota glissant 5h sur `gemini-3.1-pro` :
1. **Interception Immédiate** : Détection de l'exception `AntigravityQuotaExhaustedError` ou code HTTP 429 / `ResourceExhausted`.
2. **Fallback Transparent Instantané** : Relance automatique de la tâche sur le TIER 2 (`gemini-3.8-flash` avec réflexion `high`) sans annulation de la mission.
3. **Audit de Sécurité Économique & Non-Consommation de Clé Payante** :
   - **Garantie d'inviolabilité** : Le modèle de fallback Tier 2 est `gemini-3.8-flash`.
   - **Contrôle d'autorisation** : La clé transmise au fallback passe obligatoirement par la vérification stricte :
     ```python
     fallback_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
     ```
   - Si la case "Activer clé payante" est décochée dans l'interface, `is_paid_key_authorized()` renvoie `False` et `get_effective_paid_key()` renvoie `""`. Le fallback s'exécute **exclusivement et physiquement** sur le quota de la clé gratuite (`GEMINI_API_KEY_FREE`).
   - Il est **impossible** qu'un repli 429 bascule silencieusement sur la clé payante sans accord préalable.
4. **Notification Proactive Multicanale** : Enregistrement de l'incident dans `SupervisionService` et alerte vocale/Telegram sans interruption de service :
   > *"Pierre, le quota 5h sur 3.1 Pro est atteint. J'ai automatiquement basculé l'agent sur 3.8 Flash en réflexion renforcée pour finaliser la tâche sans blocage."*
5. **Mise à Jour Télémétrique** : Le champ `final_tier` dans `tier_routing_log` est mis à jour à 2 (tandis que `chosen_tier` reste à 3), permettant de mesurer avec précision l'impact des quotas sur la journée.

---

## 6. LE MOTEUR VOCAL TEMPS RÉEL (GEMINI LIVE AUDIO)

### 6.1. Protocole Audio Full-Duplex & Streaming PCM
Le cœur vocal de Jarvis repose sur un canal WebSocket bidirectionnel `/ws` connecté directement à l'API officielle Gemini Live de Google :
- **Format audio montant & descendant** : Flux PCM linéaire 16-bit, 16 kHz ou 24 kHz mono sans compression destructrice.
- **Streaming Bidirectionnel Permanent** : L'utilisateur parle naturellement sans appuyer sur un bouton (Push-to-Talk optionnel), et Jarvis émet ses réponses audio au fil de la génération de tokens.

### 6.2. Assemblage Dynamique de l'Instruction Système & Contexte
À chaque établissement de connexion vocale, la fonction `_build_system_instruction()` compile dynamiquement :
1. Le gabarit d'identité Stark Industries (`JARVIS_SYSTEM_INSTRUCTION_TEMPLATE`).
2. Le bloc de mémoire unifiée extrait par `unified_memory_manager.build_live_context_prompt()` (profil de Pierre, faits marquants, préférences).
3. L'arbitrage de présence du PC Windows (`is_pc_connected()`) dictant les règles de navigation (écran Chrome local vs VPS headless).
4. La directive stricte d'élocution humaine et d'éradication des amorces robotiques.
5. Le résumé architectural dynamique extrait de `ARCHITECTURE_COMPLETE_JARVIS.md`.

### 6.3. Modèles Vocaux Actifs & Permutation à Chaud
- **Modèle Standard** : `gemini-3.8-live` (faible latence, conversation continue fluide).
- **Modèle avec Réflexion Étendue** : `gemini-3.8-live-extended-thinking` (raisonnement analytique direct au fil de l'eau).
- **Permutation Dynamique** : L'utilisateur peut permuter de modèle à la volée via l'interface HUD (`/api/live-model`). La session intercepte l'exception interne `ModelSwitchRequested`, ferme proprement le canal et réinitialise la session Live avec le nouveau modèle sans coupure côté client.

### 6.4. Boucle de Traitement des Outils Asynchrone Non-Bloquante (< 300 ms)
Dans les architectures classiques, l'appel d'un outil bloque la parole du modèle jusqu'à la fin de l'exécution. Jarvis utilise un paradigme asynchrone non-bloquant :
1. Gemini Live émet un `tool_call` (ex: `ask_deep_reasoning`, `lancer_mission_deep_research`, `generer_presentation`).
2. Le dispatcheur (`core/tools/dispatcher.py`) renvoie **instantanément** un accusé de réception préliminaire : `{"status": "launched_in_background"}`.
3. Le modèle confirme oralement à Pierre en moins de 300 ms avec sa voix Aoede : *"Je m'en charge Pierre, je lance l'investigation sur le VPS."*
4. La tâche lourde s'exécute en arrière-plan via `asyncio.create_task`.
5. Pierre et Jarvis continuent à dialoguer normalement pendant l'exécution.
6. À la fin de la tâche, le backend injecte une notification via `safe_send_live_client_content` pour restitution vocale finale.

### 6.5. File d'Injection Vocale à Priorités FIFO (`VoiceInjectionQueue`)
Afin d'éviter les collisions audio et de garantir un ordre déterministe lors de l'achèvement simultané de plusieurs tâches d'arrière-plan, la vérification ponctuelle `is_model_speaking()` est pilotée par un gestionnaire de file d'attente asynchrone dédié (`services/voice_injection_queue.py`) :
1. **Hiérarchie Stricte des Priorités (Enum `InjectionPriority`)** :
   - `INTERRUPTION (1)` : Ordres d'arrêt d'urgence (`stop_current_action`), alertes critiques SRE.
   - `TOOL_RESPONSE (2)` : Réponses directes d'outils et retours de commandes utilisateur.
   - `PROGRESS_MILESTONE (3)` : Jalons de progression intermédiaires des tâches longues (ex: étapes Deep Research).
   - `PASSIVE_INFO (4)` : Télémétrie passive, logs informatifs non-urgents, notifications de veille.
2. **Ordonnancement Déterministe** :
   - Les éléments de priorité supérieure préemptent les éléments de priorité inférieure.
   - Entre deux messages de même niveau de priorité, un compteur séquentiel monotone garantit un ordre FIFO absolu.
3. **Boucle de Consommation & Sas de Sécurité** :
   - Vérification de la **Règle d'Or de Canal Unique** (`is_action_sync_completed`) : rejet immédiat si un retour synchrone officiel `tool_response` a déjà été transmis pour l'action.
   - Respect strict du **Verrou d'Élocution** (`wait_until_speech_finished`) : attente passive de la fin de parole d'Aoede et vidange du tampon audio.
   - Fenêtre de respiration post-restitution (350 ms par défaut) pour permettre l'amorçage des tampons de la session Live.
   - Purge intégrale (`queue.clear()`) lors de l'arrêt d'urgence (`stop_active_task`).

### 6.6. Jalons Vocaux Intermédiaires pour Tâches de Fond (`VOCAL_MILESTONE_THRESHOLD_SECONDS`)
Pour éliminer l'effet "boîte noire" sur les opérations asynchrones de longue durée :
- **Seuil Configurable** : Défini par la variable d'environnement `VOCAL_MILESTONE_THRESHOLD_SECONDS` (90 secondes par défaut dans `config.py`).
- **Émission Proactive** : Toute tâche dont la durée estimée excède ce seuil émet des jalons d'avancement vocal (ex: compilateur de spec, phase MAP, phase REDUCE, quality gate, livraison).
- **Consommation Fluide** : Les jalons sont enfilés avec la priorité `PROGRESS_MILESTONE (3)`. Jarvis informe Pierre brièvement sans jamais couper la parole ni écraser une réponse interactive prioritaire.

### 6.7. Règle d'Or de Canal Unique & Verrou d'Élocution Anti-Coupure
Pour éliminer les bugs de bégaiement ("stuttering") ou les coupures intempestives en pleine phrase :
1. **Règle d'Or de Canal Unique (`mark_action_sync_completed` & `is_action_sync_completed`)** : Si une action s'est exécutée de manière synchrone et a déjà fourni son résultat via le message officiel `tool_response`, l'injection parallèle d'un `send_client_content` est formellement bloquée.
2. **Verrou d'Élocution & Drainage Audio (`wait_until_speech_finished`)** : Avant d'injecter un message dans la session Live, le serveur vérifie si Aoede est en train de parler (`is_model_speaking()`). Si oui, le système temporise jusqu'à la fin de l'élocution plus un délai de vidange du tampon audio (0,3 à 2,0 secondes).

### 6.8. Gestion des Interruptions (Barge-In) & Gating Micro
- Si l'utilisateur commence à parler pendant qu'Aoede restitue une réponse, le frontend et le backend détectent immédiatement l'interruption (barge-in), coupent la lecture sonore côté client et purgent les tampons pour écouter la nouvelle instruction.
- Un système de gating et d'injection de trames de silence évite que des bruits résiduels de fond ne réveillent inopinément le modèle.

---

## 7. L'AGENT RELAIS LOCAL PC WINDOWS (`jarvis_local_agent`)

### 7.1. Problématique Résolue & Rôle Exécutant Physique
Un serveur VPS distant n'a pas accès à l'écran physique, aux périphériques USB, ni au navigateur réel de l'utilisateur. L'agent `jarvis_local_agent.py` s'exécute en arrière-plan sur le PC Windows 11 de Pierre et fait le pont entre le Cloud et le poste de travail.

### 7.2. Protocole WebSocket RPC & Reconnexion Résiliente
- **Liaison WebSocket Sécurisée** : L'agent établit une connexion sortante permanente vers `wss://jarvis.signalcraftapps.com/ws/local-agent`.
- **Boucle de Reconnexion Automatique** : En cas de coupure réseau ou de mise en veille du PC, l'agent tente indéfiniment de se reconnecter avec backoff exponentiel.
- **Format des Requêtes RPC** :
  ```json
  {"req_id": "req_101", "action": "open_browser", "params": {"url": "https://amazon.fr"}}
  ```
- **Format des Réponses RPC** :
  ```json
  {"req_id": "req_101", "result": {"status": "success", "message": "Chrome ouvert à l'écran"}}
  ```

### 7.3. Catalogue des 10 Actions Locales Supportées

| Action RPC | Description & Rôle Opérationnel | Paramètres Principaux |
| :--- | :--- | :--- |
| `launch_app` | Ouvre une application Windows physique installée (VS Code, VLC, Terminal, Calculatrice, Bloc-notes, Stremio...). | `app_name: str` |
| `open_browser` | Ouvre Google Chrome à l'écran avec le profil connecté de Pierre sur une URL donnée. | `url: str`, `new_window: bool` |
| `launch_media` | Déclenche la lecture d'un flux multimédia ou d'une vidéo dans VLC ou Stremio. | `title: str`, `content_type: str` |
| `deezer_action`| Relais direct vers le contrôleur Deezer local (port 8765). | `action: str`, `query: str`, `volume: int` |
| `prepare_train_checkout` | Ouvre simultanément les onglets de réservation ferroviaire préremplis (Omio / Trainline) pour chaque segment de voyage. | `segments: list[dict]`, `urls: list[str]` |
| `prepare_web_cart_or_checkout` | Prépare un panier d'achat sur Chrome local avec profil connecté et s'arrête avant le paiement. | `url: str`, `product: str` |
| `interact_web_page` | Interagit avec une page web ouverte dans Chrome local via Playwright ou CDP. | `url: str`, `instruction: str` |
| `execute_cdp_browser_action` | Pilote l'instance réelle Google Chrome via Chrome DevTools Protocol (`http://localhost:9222`). | `action: str`, `selector: str`, `text: str` |
| `get_status` | Relève instantanément la télémétrie matérielle physique (CPU, RAM, batterie, processus). | Aucun |
| `fetch_file` | Extrait et encode en base64 un fichier local du PC pour transmission au serveur VPS (pièces jointes e-mail). | `file_path: str` |

### 7.4. Journalisation Auto-Flush & Interception Globale des Crashs
- **Classe `AutoFlushStream`** : Encapsule les flux standards pour garantir un encodage strict UTF-8 et un forçage d'écriture immédiat sur disque (`buffering=1`, `flush()` systématique) dans `jarvis_agent.log`.
- **Intercepteur Global `sys.excepthook`** : Capture toute exception non gérée, extrait la trace complète d'erreur (`traceback`) et l'écrit avec horodatage dans le fichier de log pour éliminer tout crash silencieux.

### 7.5. Exécution Silencieuse VBScript & Scripts d'Automatisation Windows
- `start_agent_silent.vbs` : Lance l'agent via `wscript.exe` de manière 100% invisible en arrière-plan, sans ouvrir aucune invite de commande noire à l'écran.
- `install_autostart.bat` : Inscrit l'agent au démarrage automatique de Windows via la base de registre (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`).
- `uninstall_autostart.bat` : Supprime l'inscription du registre.
- `start_local_agent.bat` & `stop_agent.bat` : Démarrage et arrêt manuel de secours.
- `view_logs.bat` : Visualisation en temps réel du journal d'exécution.

### 7.6. Télémétrie Matérielle Réelle (psutil)
L'agent interroge périodiquement `psutil` pour remonter :
- Utilisation processeur globale (`psutil.cpu_percent`).
- Utilisation de la mémoire vive (`psutil.virtual_memory`).
- État de la batterie (`psutil.sensors_battery` : pourcentage, branchement secteur).
- Top des processus consommateurs en mémoire et en calcul.

---

## 8. CATALOGUE MATRICIEL & FICHES DES 38 OUTILS UNIFIÉS (FUNCTION CALLING)

> **Mise à jour V 5.3.0 — Refactorisation & Unification Cognitive** :
> 1. **Consolidation (41 → 38 outils)** :
>    - `save_memory` : fusionne `remember_user_fact` et `memoriser_information` avec gestion unifiée de `fact`, `category`, `key`.
>    - `send_to_ereader` : fusionne `send_to_ereader`, `send_page_to_kindle` et `send_file_to_kindle` avec paramètre `source` (fichier ou URL), `source_type` (`file`|`url`) et `method` (`auto`|`usb`|`kindle_web`|`email`).
> 2. **Clauses d'Arbitrage ASR Strictes** : Chaque outil intègre une clause explicite `À UTILISER QUAND : ...` et `NE JAMAIS UTILISER QUAND : ...` pour éliminer toute confusion sur entrée vocale bruitée.
> 3. **Uniformisation Naming** : Adoption universelle de la convention anglaise `snake_case` (verbe + complément). Rétrocompatibilité intégrale à 100 % maintenue dans `core/tools/dispatcher.py` pour tous les identifiants historiques et alias.

### 8.1. Matrice Globale Exhaustive des 38 Outils Déclarés

| # | Nom Unifié (v5.3.0) | Nom Historique / Alias | Service Exécutant | Mode d'Exécution | Arguments Clés | Rôle Opérationnel & Impact Système |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `stop_current_action` | `stop` | `core/shared_state.py` | Bloquant (Immédiat) | `reason: str` | Arrêt physique d'urgence immédiat de toute tâche, agent ou navigation en cours. |
| **2** | `guide_active_task` | `guide` | `core/shared_state.py` | Non-bloquant | `directive: str` | Injection d'une consigne d'orientation en direct dans la tâche active. |
| **3** | `ask_deep_reasoning` | `deep_reasoning` | `services/reasoning_service.py` | Non-bloquant | `question: str`, `intensite_reflexion` | Moteur délibératif multi-agents Antigravity CLI sur VPS (Tiers 1, 2, 3). |
| **4** | `launch_deep_research` | `lancer_mission_deep_research` | `services/deep_research_service.py` | Non-bloquant | `consigne_utilisateur: str` | Moteur Deep Research Map-Reduce (5-10 min, 3 axes, Quality Gate). |
| **5** | `search_web` | `web_search` | `services/browser_service.py` | Bloquant | `query: str` | Recherche web factuelle ultra-rapide via DuckDuckGo (< 2s). |
| **6** | `run_browser_task` | `browser_task` | `services/browser_service.py` | Non-bloquant | `goal: str`, `execution_target` | Navigation web autonome via agent vision Browser-Use ou Playwright. |
| **7** | `open_user_browser` | `open_browser` | `services/browser_service.py` | Bloquant | `url: str`, `reason: str` | Ouvre Google Chrome directement à l'écran du PC Windows de Pierre. |
| **8** | `set_browser_link` | `browser_link` | `core/shared_state.py` | Bloquant | `url: str`, `title: str` | Positionne le lien actif cliquable dans le HUD mobile. |
| **9** | `save_memory` | `remember_user_fact`, `memoriser_information` | `services/unified_memory.py` | Bloquant | `fact: str`, `category: str`, `key: str` | **Fusion V5.3.0** : Enregistre durablement un fait, habitude ou clé dans Qdrant + SQLite. |
| **10** | `recall_user_memories` | `search_memories` | `services/unified_memory.py` | Bloquant | `query: str` | Recherche sémantique par distance cosinus dans Qdrant et SQLite. |
| **11** | `get_system_status` | `get_status` | `services/system_service.py` | Bloquant | Aucun | Diagnostic télémétrique complet des ressources (CPU, RAM, disques, batterie). |
| **12** | `launch_application` | `launch_app` | `services/system_service.py` | Bloquant | `app_name: str` | Lance une application Windows sur le PC local (VS Code, VLC, Calc, Notepad). |
| **13** | `play_music_deezer` | `deezer_action` | `services/media_service.py` | Bloquant | `action: str`, `query: str`, `volume` | Contrôle total du lecteur Deezer Web officiel via bridge WebSocket local. |
| **14** | `play_video_stremio` | `launch_media` | `services/media_service.py` | Bloquant | `title: str`, `content_type: str` | Lance un film ou une série en streaming 1080p fluide sur Stremio local. |
| **15** | `send_email` | `mail_send` | `services/email_service.py` | Bloquant | `subject: str`, `body: str`, `attachments` | Rédige et expédie un courriel Stark Industries avec pièces jointes résolues. |
| **16** | `read_emails` | `get_emails` | `services/email_service.py` | Bloquant | `count: int`, `query: str`, `unread_only` | Consulte la boîte Gmail de Pierre via IMAP et résume les messages. |
| **17** | `check_console_errors` | `console_errors` | `services/console_monitor.py` | Bloquant | `action: str` (`diagnose`|`clear`) | Analyse les logs de console, diagnostique les erreurs ou purge le journal. |
| **18** | `interact_web_page` | `web_interaction` | `services/browser_service.py` | Non-bloquant | `url: str`, `action: str`, `selector: str` | Action unitaire ciblée sur une page (DOM, clic sélecteur, saisie champ). |
| **19** | `prepare_web_cart_or_checkout` | `prepare_cart` | `services/browser_service.py` | Non-bloquant | `product_or_service: str`, `merchant_url` | Ajoute un produit au panier et préremplit les coordonnées (sans payer). |
| **20** | `download_file` | `file_download` | `services/download_service.py` | Non-bloquant | `url: str`, `filename: str` | Télécharge un fichier depuis une URL après accord oral préalable explicite. |
| **21** | `send_to_ereader` | `send_page_to_kindle`, `send_file_to_kindle` | `services/download_service.py` / `browser_service.py` | Non-bloquant | `source: str`, `source_type`, `method` | **Fusion V5.3.0** : Achemine un ebook, document ou article web vers la liseuse (USB, Kindle Web, mail). |
| **22** | `search_and_download_ebook` | `download_ebook` | `services/download_service.py` | Non-bloquant | `query: str`, `lang: str` | Recherche un livre sur Anna's Archive, accord oral, download et envoi liseuse. |
| **23** | `list_chrome_extensions` | `chrome_extensions` | `services/browser_service.py` | Bloquant | Aucun | Énumère les extensions installées dans le profil Chrome de Pierre. |
| **24** | `execute_external_action` | `executer_action_externe` | `services/automation.py` | Non-bloquant | `action_name: str`, `parametres: dict` | Déclenche un webhook générique d'automatisation sur n8n. |
| **25** | `generate_spreadsheet` | `generer_fichier_tableur` | `services/automation.py` | Non-bloquant | `nom_fichier: str`, `colonnes`, `lignes` | Génère un classeur Excel `.xlsx` complet avec modèle financier Stark. |
| **26** | `generate_presentation` | `generer_presentation` | `services/slides_service.py` | Non-bloquant | `titre: str`, `theme: str`, `slides` | Conçoit une présentation Google Slides experte polymorphe (7 layouts). |
| **27** | `get_active_task_status` | `task_status` | `services/supervision_service.py`| Bloquant | `task_id: str` | Explique oralement l'état et l'avancement d'une tâche de fond en cours. |
| **28** | `save_notion_entry` | `notion_enregistrer` | `services/automation.py` | Non-bloquant | `titre: str`, `type_entree: str`, `contenu` | Enregistre une note, to-do list ou fiche de veille dans Notion via n8n. |
| **29** | `manage_calendar_event` | `agenda_gerer_evenement` | `services/briefing_service.py` | Non-bloquant | `action: str`, `titre: str`, `date_debut` | Crée, décale, consulte ou supprime des événements sur Google/Samsung Calendar. |
| **30** | `create_push_reminder` | `creer_rappel_push` | `services/briefing_service.py` | Non-bloquant | `message: str`, `echeance: str` | Programme une notification push sur smartphone via Telegram Stark Bot. |
| **31** | `get_morning_briefing` | `demander_morning_briefing` | `services/briefing_service.py` | Bloquant | `force_refresh: bool` | Restitue le briefing matinal compilé (météo, agenda, e-mails urgents, trains). |
| **32** | `search_train_routes` | `rechercher_train` | `services/transport_service.py`| Bloquant | `origine: str`, `destination`, `date_depart` | Calcule un itinéraire ferroviaire France/Suède avec optimisation multi-critères. |
| **33** | `monitor_train` | `surveiller_train` | `services/transport_service.py`| Non-bloquant | `numero_train: str`, `date: str` | Active la veille proactive 10 min sur Trafikverket/SNCF avec alertes directs. |
| **34** | `open_train_booking` | `reserver_billet_train_local` | `services/transport_service.py`| Non-bloquant | `operateur: str`, `urls_trajets` | Ouvre les onglets de réservation du train sur le Chrome physique du PC. |
| **35** | `query_jarvis_architecture` | `consulter_architecture_jarvis` | `services/architecture_service.py`| Bloquant | `sujet: str`, `section: str` | Interroge interactivement le présent fichier d'architecture en temps réel. |
| **36** | `draft_email_response` | `triage_et_brouillon_email` | `services/agentic_dispatcher.py` | Non-bloquant | `query: str`, `consigne: str` | Triage exécutif Système 2, analyse pièces jointes PDF et projet de réponse. |
| **37** | `generate_book_summary` | `curation_livre_synthese` | `services/agentic_dispatcher.py` | Non-bloquant | `titre_livre: str` | Synthèse exécutive 2 pages 'Clés de lecture' envoyée sur Kindle en bonus. |
| **38** | `system_self_healing` | `auto_guerison_systeme` | `services/agentic_dispatcher.py`<br>`services/system_healing_service.py` | Non-bloquant | `motif: str`, `action: str`, `patch_id: str` | SRE autonome : analyse RCA, tests isolés en sandbox, test non-régression auto-généré, déploiement Blue/Green releases/symlink, escalade fichiers critiques (validation orale Pierre) et journalisation PostgreSQL. |

---

### 8.2. Moteur Multi-Agents Antigravity CLI sur VPS
- **Fichiers sources** : `google_antigravity.py`, `services/reasoning_service.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`.
- **Outils exposés** : `ask_deep_reasoning`, `guide_active_task`, `stop_current_action`.
- **Principe d'exécution** : S'exécute directement sur le serveur Cloud Ubuntu ARM64 adossé au jeton OAuth2 Google AI Pro de Pierre (`/home/opc/.gemini/antigravity-cli/antigravity-oauth-token`), garantissant un coût d'API nul.
- **Pipeline Délibératif Système 2 en 3 Phases** :
  1. *Phase 1 — Sous-agent Prospecteur* : Exploration approfondie, recherche web contradictoire, collecte de données techniques et chiffres vérifiés.
  2. *Phase 2 — Sous-agent Analyste Critique* : Élimination méthodique des hallucinations, confrontation des hypothèses, vérification de cohérence logique.
  3. *Phase 3 — Sous-agent Synthèse & Production d'Artefacts* : Rédaction du livrable final structuré (`markdown_report`, `slides_schema`, `code_patch`) sauvegardé dans `/artifacts/`.
- **Routage en 3 Tiers** : Arbitrage ordonné entre Tier 1 (`gemini-3.8-flash-low`), Tier 2 (`gemini-3.8-flash-high`) et Tier 3 (`gemini-3.1-pro-high`) avec bascule instantanée en cas de quota 429.
- **Résilience CLI & Pré-contrôle Opérationnel Strict (Anti-Faux Positifs v5.8.0)** :
  - *Drapeaux Officiels du Binaire `agy`* : Injonction stricte de `--model <nom_modele>` et optionnellement `--effort <low|medium|high|max>`. Bannissement formel de tout drapeau erroné non supporté tel que `--thinking` (qui provoquait une terminaison fatale `exit code 2`).
  - *Détection Déterministe & Enrichissement PATH* : `find_antigravity_binary()` résout les emplacements connus (`~/.local/bin/agy`, `/home/opc/.local/bin/agy`, `/usr/local/bin/antigravity-cli`), et injecte dynamiquement ces répertoires dans le `PATH` du sous-processus.
  - *Pré-contrôle Opérationnel `verify_antigravity_cli_ready()`* : Avant toute déclaration de prise en charge en tâche de fond dans `dispatcher.py` (`ask_deep_reasoning`, `launch_deep_research`), un test de viabilité pré-vol rapide est exécuté. Si le binaire est absent ou non-réactif, l'orchestrateur **refuse catégoriquement** d'émettre `launched_in_background` et transmet une consigne ferme à Aoede pour informer Pierre de l'indisponibilité immédiate du cluster sans masquer l'incident.
  - *Propagation Non-Trompeuse des Erreurs* : Les échecs d'exécution renvoient explicitement `status="error"` avec `error_type="binary_not_found"` ou `execution_failed`, interdisant toute synthèse d'artefact maquillée ou confirmation orale hallucinée.

### 8.3. Moteur Universel Deep Research Map-Reduce (`lancer_mission_deep_research`)
- **Fichier source** : `services/deep_research_service.py`.
- **Architecture opérationnelle en 6 étapes intégrées** :
  1. *Étape 1 : Compilateur de Spécification Dynamique* (`MissionSpec`) via Tier 1 Flash en mode JSON strict. Extrait les entités cibles, la quantité (défaut 5), la localisation géographique stricte et les critères obligatoires.
  2. *Étape 2 : Override Géographique Absolu*. Dès qu'une zone géographique est spécifiée dans la consigne orale de Pierre, l'ensemble des localisations mémoire par défaut (Grenoble, Paris, Lyon, France, Stockholm, Suède...) sont formellement bannies (`exclusion_geographique`), éliminant tout biais de contexte.
  3. *Étape 3 : Phase MAP — Prospection Parallèle VPS en 3 Axes Fonctionnels Universels*. Déploiement simultané via `asyncio.gather` de 3 ouvriers spécialisés sur Antigravity CLI :
     - *Ouvrier 1 (Startups & Incubateurs locaux)*.
     - *Ouvrier 2 (Pôles technologiques, Scale-ups & R&D privés)*.
     - *Ouvrier 3 (Grands groupes, filiales et éditeurs établis)*.
  4. *Étape 4 : Phase REDUCE — Fusion, Déduplication & Normalisation*. Fusion des retours bruts, déduplication stricte par clé normalisée et structuration sous la dataclass `NormalizedEntity`.
   5. *Étape 5 : Phase QUALITY GATE — Boucle de Rejet Fermée & Gestion Explicite d'Échec*. L'agent critique applique 3 règles éliminatoires :
      - Règle 1 : Volume strict (`nombre_valide >= quantite_cible`).
      - Règle 2 : Conformité géographique stricte (zéro entité hors zone).
      - Règle 3 : Complétude des critères (100% des critères obligatoires documentés).
      En cas de manquement, relance ciblée d'ouvriers prospecteurs pour combler les fiches (jusqu'à 2 itérations).
      - **Gestion Explicite de l'Échec Quality Gate (Zéro Tolérance aux Livraisons Maquillées)** : Si après 2 relances le score reste insuffisant (`not est_conforme`), le système refuse formellement de masquer le déficit :
        * Le statut `quality_gate_passed = False` et `target_fully_reached = False` est gravé dans le payload.
        * **Alerte Vocale Live** : Aoede signale immédiatement à Pierre avec franchise que la cible n'a pas été pleinement atteinte (ex: *"Attention Pierre, l'audit qualité signale que la cible n'a pas été atteinte : seulement 7 entités validées sur 20..."*).
        * **Bannière d'Avertissement Écrite** : Le rapport Markdown affiche un bandeau rouge bien visible `[ALERTE AUDIT QUALITÉ : CIBLE NON PLEINEMENT ATTEINTE]` avec le détail des motifs de rejet et le badge `AUDIT REJETÉ`.
        * **Push Telegram & Courriel** : Les sujets et messages portent la mention explicite `[PARTIEL - AUDIT NON VALIDÉ]`.
   6. *Étape 6 : Livraison Déterministe Multi-Canal & Jalons Vocaux Intermédiaires* :
      Pendant toute la mission, 5 jalons vocaux sont transmis via `VoiceInjectionQueue` (priorité `PROGRESS_MILESTONE`, respectant le verrou d'élocution `wait_until_speech_finished`) :
      - *Jalon 1 (Spécification)* : Validation de la cible et des critères d'exclusion géographique.
      - *Jalon 2 (Fin Phase MAP)* : Nombre de fiches brutes extraites par les 3 ouvriers.
      - *Jalon 3 (Fin Phase REDUCE)* : Nombre d'entités uniques retenues après déduplication.
      - *Jalon 4 (Quality Gate)* : Confirmation de validation ou avertissement de cible partielle.
      - *Jalon 5 (Livraison finale)* : Synthèse exécutive orale et disponibilité des artefacts (Markdown, Google Slides, Push Telegram, E-mail).

### 8.4. Moteur Délibératif Système 2 Transverse (Missions Spécialisées)
- **Fichier source** : `services/agentic_dispatcher.py`.
- **Missions agentiques natives** :
  1. `transport_optimizer` : Analyse comparative confort/temps, arbitrage train de jour vs couchette de nuit, marges de sécurité aux correspondances.
  2. `spreadsheet_modeler` : Ingénierie de tableurs financiers avec formules dynamiques (`XLOOKUP`, `SUMIFS`), mise en forme corporate Stark (#1E293B) et génération directe via script Python `openpyxl`.
  3. `system_healing` : SRE autonome sur incident, analyse de cause racine (RCA), exécution isolée de la suite de tests en sandbox temporaire (hors production), auto-génération de test minimal de non-régression si aucun test n'existe, pattern Blue/Green `releases/<timestamp>` + symlink atomique `current` permettant le rollback instantané, règle d'escalade avec validation orale de Pierre pour les fichiers critiques (`auth_service.py`, `dispatcher.py`), et journalisation complète dans la table PostgreSQL `patches_auto_appliques`.
  4. `email_drafting` : Triage des courriers complexes, décorticage de pièces jointes PDF via `pypdf`, rédaction de projets de réponse sauvegardés dans `outbox_emails/`.
  5. `book_curation` : Synthèse exécutive en 2 pages des thèses majeures d'un livre téléchargé, transmise sur Kindle.
  6. `morning_briefing` : Préparation stratégique à 6h45 croisant météo, agenda, e-mails et veille technique IA.
  7. `memory_consolidation` : Assainissement nocturne, détection de contradictions et réconciliation du Knowledge Graph.
  8. `doc_sync` : Détection continue du décalage (drift) entre le code réel et `ARCHITECTURE_COMPLETE_JARVIS.md`.

### 8.5. Navigation Web Autonome, E-Commerce & Chrome CDP
- **Fichiers sources** : `services/browser_service.py`, `jarvis_local_agent.py`.
- **Routage Hybride Typé (`execution_target`)** :
  - `vps_headless` : Exécution discrète sur le serveur Cloud via Playwright headless (recherche, scraping, e-books).
  - `local_chrome_cdp` : Pilotage direct du Chrome physique de Pierre via Chrome DevTools Protocol port 9222 (`playwright.chromium.connect_over_cdp`). Conserve 100% des cookies, sessions Google/Amazon et extensions.
  - `local_gui` : Ouverture fenêtrée d'applications à l'écran.
- **Arbitrage de Présence PC** : Si le PC est éteint, repli automatique sur `vps_headless`. Si le PC est allumé, Jarvis demande poliment à Pierre s'il préfère agir à l'écran ou en arrière-plan.
- **Assistant d'Achat Sécurisé (`prepare_web_cart_or_checkout`)** : Remplit le panier, saisit l'adresse et s'arrête strictement avant le paiement.

### 8.6. Pôle Documentaire & Présentations Google Slides Polymorphes v1
- **Fichiers sources** : `services/slides_service.py`, `services/automation.py`, `docs/n8n_workflows/documents_suite.json`.
- **Présentations Google Slides Élaborées (`generer_presentation`)** :
  - *Nombre de diapositives libre & adaptatif* : Plus aucun plafond fixe de 6 slides. Calé sur la consigne de Pierre ou calculé selon la complexité (3 à 14+ slides).
  - *7 Layouts Visuels Polymorphes (16:9 Widescreen 720x405 PT)* : `hero_title`, `key_metrics`, `cards_grid`, `split_compare`, `timeline_steps`, `quote_highlight`, `conclusion_call_to_action`.
  - *Conformité Google Slides API v1* : Utilisation exclusive du type de forme officiel `ROUND_RECTANGLE` (évitant tout rejet HTTP 400).
  - *Élimination de la slide blanche initiale* : Suppression automatique de la diapositive vierge par défaut via son `objectId`.
  - *5 Thèmes Esthétiques* : `stark`, `corporate`, `dark`, `gold`/`bitcoin`, `cyber`.
- **Tableurs Excel Avancés (`generer_fichier_tableur`)** : Création de classeurs `.xlsx` stylisés avec formules natives et KPIs.
- **Intégration Notion (`notion_enregistrer`)** : Prise de notes rapides, items to-do et fiches de veille créées directement dans la base de données Notion de Pierre via webhook n8n.

### 8.7. Mobilité & Système Ferroviaire Intelligent (France & Suède)
- **Fichiers sources** : `services/transport_service.py`, `routers/transport.py`, `jarvis_local_agent.py`, `docs/n8n_workflows/train_monitoring.json`.
- **Capacités** :
  - *Décomposition Multi-Segments (Grand Nord Arctique / Laponie)* : Découpage intelligent des trajets sans train direct (ex: Malmö ↔ Kiruna) en 2 billets avec escale sécurisée à Stockholm Central (SJ Snabbtåg de jour + SJ Nattåg couchette de nuit).
  - *Deep Links Directs & Réservables* : Génération d'URLs profondes Omio (`https://www.omio.fr/trains/...`) et Trainline affichant immédiatement les trains réels avec bouton 'Réserver', sans redirection vers une page d'accueil vide.
  - *Réservation Multi-Onglets Parallèles sur PC Local (`reserver_billet_train_local`)* : Ouvre simultanément chaque segment dans un onglet distinct Google Chrome sur l'écran de Pierre.
  - *Surveillance Temps Réel n8n (`surveiller_train`)* : Scrute toutes les 10 minutes les flux Trafikverket Open Data et SNCF. En cas de retard > 5 min ou annulation, alerte vocale immédiate dans Gemini Live et alerte Telegram.

### 8.8. Gestionnaire E-Book, Liseuses Physiques & Send to Kindle
- **Fichiers sources** : `services/download_service.py`, `services/browser_service.py`.
- **Capacités** :
  - *Moteur Anna's Archive* : Scraping et téléchargement direct d'ouvrages avec filtrage strict de la langue demandée (FR ou EN) et validation de l'arborescence EPUB (`mimetype`, `META-INF/container.xml`).
  - *Détection Liseuse USB* : Détecte les périphériques de stockage amovibles montés sous Windows pour y copier directement les fichiers.
  - *Amazon Send to Kindle Web Direct* : Téléversement automatisé Playwright sur `amazon.com/sendtokindle` avec profil persistant connecté (`.jarvis_shopping_profile`) supportant des fichiers jusqu'à 200 Mo.
  - *Extension Send to Kindle* : Détection automatique des extensions Chrome installées sur la machine de Pierre.

### 8.9. Contrôleur Média & Streaming (Deezer Web Player & Stremio)
- **Fichiers sources** : `deezer_bridge.py`, `services/media_service.py`.
- **Deezer Web Player 100% Zéro-Coût** :
  - Bridge WebSocket bidirectionnel local sur le port `8765`.
  - Userscript Tampermonkey (`static/deezer_controller.user.js`) injecté sur l'onglet `deezer.com`.
  - Résolution sémantique : "Mets mon Flow" -> `/channels/flow`, "Mes coups de cœur" -> `/channels/loved-tracks`, recherche d'artistes/titres et contrôle du volume.
- **Cinéma & Séries Stremio** :
  - Interrogation de l'API Cinemeta et résolution de flux 1080p légers via Torrentio.
  - Lancement direct de l'application Stremio via protocole URI `stremio:///detail/...`.

### 8.10. Suite de Communication & Messagerie Stark
- **Fichiers sources** : `services/email_service.py`, `services/chat_service.py`.
- **Émission SMTP Stark Industries** :
  - Gabarit HTML corporate sombre haute définition (palette Stark, typographie soignée, badges d'état).
  - *Moteur de Résolution Universelle des Pièces Jointes (`resolve_attachment_path`)* : Résolution floue de fichiers PDF, EPUB, XLSX depuis `downloads/`, `artifacts/`, `my-project/`, les dossiers système Windows (`Downloads`, `Documents`) ou URLs distantes.
  - *Relais Fichier PC-VPS (`fetch_file`)* : Rapatriement base64 d'un document local depuis le PC de Pierre pour inclusion immédiate dans un courriel envoyé par le Cloud.
  - Garde-fou anti-mail vide si une pièce jointe demandée est introuvable.
  - Archivage systématique dans `outbox_emails/`.
- **Réception IMAP Gmail** : Consultation sécurisée de `pierrecassagnettes@gmail.com` avec décodage MIME et synthèse vocale des e-mails urgents.
- **Messagerie Multimodale Vision** : Analyse de captures d'écran, schémas techniques et photos via Gemini 3.8 Flash Vision avec rendu Markdown.

### 8.11. Système de Mémoire Hybride (SQLite, Qdrant & Fastembed)
- **Fichiers sources** : `services/unified_memory.py`, `services/memory_service.py`, `services/memory.py`.
- Façade transparente orchestrant les faits immuables (profil SQLite) et les souvenirs sémantiques RAG (Qdrant + Fastembed local 384 dim).
- Seuil de similarité cosinus > 0.30 et dégradation gracieuse textuelle en cas d'indisponibilité vectorielle.

### 8.12. Télémétrie, Diagnostics & Supervision Système
- **Fichiers sources** : `services/system_service.py`, `services/supervision_service.py`, `services/console_monitor.py`.
- Traçabilité en temps réel des actions engagées, des sous-agents déployés, des clés API sollicitées et de la consommation estimée.
- Inspection continue des exceptions Python (`ConsoleMonitor`) avec diagnostic automatisé et suggestions de réparation.

### 8.13. Agenda Google/Samsung, Rappels Push Mobiles & Morning Briefing
- **Fichiers sources** : `services/briefing_service.py`, `routers/briefing.py`, `docs/n8n_workflows/time_and_briefing.json`.
- Synchronisation bidirectionnelle Google Calendar / Samsung Calendar via n8n.
- Prise de note vocale et rappel push instantané ou différé sur smartphone via le Telegram Stark Bot (`chatId: 6849746502`).
- Compilation automatique du Morning Briefing à 7h00 (météo Open-Meteo, rendez-vous du jour, e-mails non lus, état des serveurs) mis en cache dans Redis (`jarvis:briefing:today`).

### 8.14. Connaissance Architecturale Dynamique & Auto-évaluation
- **Fichier source** : `services/architecture_service.py`.
- Surveillance en temps réel de l'empreinte `mtime` du fichier maître `ARCHITECTURE_COMPLETE_JARVIS.md`.
- Rechargement instantané en mémoire vive (< 5 ms) sans redémarrage de serveur lors de toute modification.
- Outil interactif `consulter_architecture_jarvis` permettant à Jarvis d'interroger ses propres spécifications techniques pour répondre précisément à Pierre sur son fonctionnement.

---

## 9. MATRICE DES ENDPOINTS API REST & PROTOCOLES WEBSOCKETS

### 9.1. Endpoints HTTP / REST FastAPI

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
| **POST** | `/api/media/deezer/control` | Contrôle direct de Deezer (play, pause, next, volume). | Token JWT | `{"action": "play", "query": "..."}` | `{"status": "success"}` |
| **GET** | `/api/media/deezer/status` | Retourne l'état du lecteur Deezer (titre, artiste, pochette).| Token JWT | Aucun | `{"status": "playing", "track": "..."}` |
| **GET** | `/api/media/deezer/userscript`| Sert le script Tampermonkey pour le navigateur. | Ouvert | Aucun | Fichier JS |
| **GET** | `/api/browser/extensions` | Énumère les extensions Chrome installées sur la machine. | Token JWT | Aucun | `[{"id": "...", "name": "Send to Kindle"}]` |
| **POST** | `/api/browser/send-to-kindle` | Envoie un article web nettoyé sur la liseuse Kindle. | Token JWT | `{"url": "...", "title": "..."}` | `{"status": "sent"}` |
| **POST** | `/api/browser/upload-and-send-to-kindle` | Upload multipart d'un EPUB/PDF vers Amazon Send to Kindle. | Token JWT | Multipart form-data (`file`) | `{"status": "uploaded"}` |
| **GET** | `/api/browser/kindle-status` | Vérifie si la session Amazon Web est connectée. | Token JWT | Aucun | `{"connected": true}` |
| **POST** | `/api/browser/open-kindle-login` | Ouvre Chrome sur la page de connexion Send to Kindle. | Token JWT | Aucun | `{"status": "opened"}` |
| **POST** | `/api/open-chrome-profile` | Ouvre Chrome avec le profil persistant de Jarvis. | Token JWT | `{"url": "..."}` | `{"status": "opened"}` |
| **GET** | `/api/supervision/overview` | Données complètes de supervision (tâches, logs, appareils). | Token JWT | Aucun | `{"actions": [], "subagents": []}` |
| **GET** | `/api/supervision/windows` | Liste des fenêtres d'applications ouvertes à l'écran. | Token JWT | Aucun | `{"windows": [...]}` |
| **GET** | `/api/supervision/metrics` | Métriques agrégées d'outils, latences p95, tiers et coûts. | Token JWT | `?window=24h/7j/30j` | `{"top_tools": [], "latencies": []}` |
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
| **POST** | `/api/train/search` | Recherche de trajets ferroviaires et deep links directs. | Token JWT | `{"origin": "...", "destination": "...", "date": "..."}`| `{"segments": [], "deep_links": []}`|
| **POST** | `/api/train/monitor` | Active la surveillance proactive n8n d'un train. | Token JWT | `{"train_number": "...", "date": "..."}` | `{"status": "monitoring"}` |
| **POST** | `/api/train/alert` | Webhook de réception d'alerte de retard n8n. | Secret n8n | `{"train": "...", "delay_min": 15}` | `{"status": "broadcasted"}` |
| **POST** | `/api/train/reserve-local` | Préparation de réservation multi-onglets sur PC local. | Token JWT | `{"segments": [...]}` | `{"status": "opened_locally"}` |

### 9.2. Contrat WebSocket Audio Gemini Live (`/ws`)
- **URL** : `wss://jarvis.signalcraftapps.com/ws?token={jwt_token}`
- **Messages montants (Client -> Serveur)** :
  - Chunks audio micro : `{"realtime_input": {"media_chunks": [{"data": "base64_pcm...", "mime_type": "audio/pcm"}]}}`
  - Contrôle micro : `{"type": "mic_mute"}` / `{"type": "mic_unmute"}`
- **Messages descendants (Serveur -> Client)** :
  - Chunks audio modèle : `{"audio": "base64_pcm..."}`
  - Changement d'état de l'avatar : `{"type": "status", "state": "thinking|speaking|coding|browsing...", "msg": "..."}`
  - Supervision & Sous-agents : `{"type": "supervision_update", "overview": {...}}`, `{"type": "subagent_spawn", "agent": {...}}`, `{"type": "subagents_update", "agents": [...]}`
  - Mise à jour navigateur : `{"type": "browser_update", "url": "...", "title": "...", "screenshot": "..."}`
  - Demande d'arbitrage payant : `{"type": "paid_consent_request", "action": "...", "cost_est": "~0.03 $"}`
  - Annonce textuelle discrète : `{"type": "jarvis_announcement", "text": "...", "voice": false}`

### 9.3. Contrat WebSocket Relais Agent Local PC (`/ws/local-agent`)
- **URL** : `wss://jarvis.signalcraftapps.com/ws/local-agent?token={jwt_token}`
- **Messages VPS -> PC Local** :
  ```json
  {
    "req_id": "rpc_98765",
    "action": "launch_app",
    "params": {"app_name": "vscode"}
  }
  ```
- **Messages PC Local -> VPS** :
  ```json
  {
    "req_id": "rpc_98765",
    "result": {
      "status": "success",
      "pid": 14208,
      "message": "Visual Studio Code lancé avec succès"
    }
  }
  ```
- **Heartbeat & Télémétrie périodique (toutes les 15 s)** :
  ```json
  {
    "type": "heartbeat",
    "cpu_percent": 12.4,
    "ram_percent": 48.2,
    "battery": {"percent": 98, "power_plugged": true}
  }
  ```

### 9.4. Contrat WebSocket Deezer Controller (`127.0.0.1:8765`)
- Pont bidirectionnel local avec l'onglet Chrome `deezer.com` injecté par Tampermonkey.
- Schéma d'ordre : `{"action": "play|pause|next|prev|shuffle|volume", "query": "...", "volume": 75}`.
- Schéma d'état retourné : `{"status": "playing", "track": "Around the World", "artist": "Daft Punk", "album": "Homework", "cover": "https://..."}`.

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
- **Version affichée dans l'en-tête** : `V 5.2.0 EXHAUSTIVE SYSTEM SPECIFICATIONS & DISTRIBUTED CORE`.

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
- `music` : Ambre doré vibrant (Deezer Web Player actif).
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

*Document de référence architecturale — Stark Industries — Système J.A.R.V.I.S. Core V 5.2.0.*
