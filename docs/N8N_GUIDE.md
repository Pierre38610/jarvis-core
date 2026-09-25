# 🤖 Guide n8n × Jarvis — Le Manuel de l'Agent IA

> **Pour les agents IA et développeurs** : Ce guide est conçu pour être lu une seule fois et permettre l'ajout d'une nouvelle compétence n8n à Jarvis en moins de 15 minutes, sans poser de questions.

---

## Table des matières

1. [Architecture générale](#1-architecture-générale)
2. [Le Standard Jarvis — Protocole d'ajout d'une intégration](#2-le-standard-jarvis--protocole-dajout-dune-intégration)
3. [Structure du payload JSON](#3-structure-du-payload-json)
4. [Enregistrer l'action dans Gemini Live](#4-enregistrer-laction-dans-gemini-live)
5. [Gestion des credentials tiers (0 €)](#5-gestion-des-credentials-tiers-0-)
6. [Import / Export CLI Docker](#6-import--export-cli-docker)
7. [Commandes de maintenance](#7-commandes-de-maintenance)
8. [Catalogue des actions disponibles](#8-catalogue-des-actions-disponibles)
9. [Dépannage](#9-dépannage)

---

## 1. Architecture générale

```
Voix de Pierre
     │
     ▼
┌─────────────────────────────────────────┐
│        Gemini Live (App.py)             │
│  ┌──────────────────────────────────┐   │
│  │  Tool Call : executer_action_    │   │
│  │  externe(action, parametres)     │   │
│  └──────────────┬───────────────────┘   │
└─────────────────┼───────────────────────┘
                  │ HTTP POST (réseau Docker interne)
                  ▼
┌─────────────────────────────────────────┐
│     Backend Jarvis (services/automation.py)│
│  trigger_webhook(action_name, payload)  │
│  Header : X-Jarvis-Secret               │
└─────────────────┬───────────────────────┘
                  │ POST http://n8n:5678/webhook/<action>
                  ▼
┌─────────────────────────────────────────┐
│       n8n Community Edition             │
│  ┌─────────────────────────────────┐   │
│  │  Nœud Webhook (déclencheur)     │   │
│  │  Nœuds métier (API tierces)     │   │
│  │  Nœud Respond to Webhook        │   │
│  └─────────────────────────────────┘   │
└─────────────────┬───────────────────────┘
                  │ JSON Response
                  ▼
        Réponse vocale Jarvis
```

**Points clés :**
- **Tout est gratuit** : n8n Community Edition, webhooks illimités, CLI intégrée.
- **Réseau Docker isolé** : `jarvis_network` — n8n n'est jamais exposé publiquement.
- **Secret partagé** : header `X-Jarvis-Secret` pour authentifier les appels Jarvis → n8n.

---

## 2. Le Standard Jarvis — Protocole d'ajout d'une intégration

### Étape 1 — Créer le workflow dans n8n

1. Ouvrir l'interface n8n via tunnel SSH : `ssh -L 5678:localhost:5678 user@158.178.206.213`
2. Accéder à `http://localhost:5678` dans le navigateur.
3. Cliquer **"New Workflow"** → nommer le workflow : `Jarvis - <NomAction>`.

### Étape 2 — Configurer le nœud Webhook (déclencheur)

| Paramètre | Valeur requise |
|-----------|----------------|
| **HTTP Method** | `POST` |
| **Path** | `<action-slug>` (ex: `samsung-calendar`, `notion-note`) |
| **Authentication** | `Header Auth` |
| **Header Name** | `X-Jarvis-Secret` |
| **Header Value** | `{{ $env.N8N_WEBHOOK_SECRET }}` |
| **Respond** | `Using Respond to Webhook Node` ← **OBLIGATOIRE** |

> ⚠️ **"Respond Using: Respond to Webhook Node"** est obligatoire pour que `trigger_webhook()` reçoive une réponse JSON synchrone.

### Étape 3 — Ajouter les nœuds métier

Insérer les nœuds n8n correspondant à l'API tierce :
- **Google Calendar** → nœud `Google Calendar`
- **Notion** → nœud `Notion`
- **Gmail/SMTP** → nœud `Gmail` ou `Send Email`
- **HTTP Request** → pour toute API sans nœud natif

### Étape 4 — Configurer le nœud "Respond to Webhook"

```json
{
  "status": "success",
  "reply": "Message vocal que Jarvis lira à voix haute",
  "data": { ... }
}
```

**Format obligatoire de la réponse :**

| Champ | Type | Description |
|-------|------|-------------|
| `status` | `"success"` \| `"error"` | Résultat de l'opération |
| `reply` | `string` | Texte que Jarvis lira à voix haute |
| `data` | `object` (optionnel) | Données supplémentaires |

### Étape 5 — Activer le workflow

- Cliquer le toggle **Active** en haut à droite → le webhook est immédiatement opérationnel.

---

## 3. Structure du payload JSON

### Payload envoyé par Jarvis → n8n

```json
{
  "message": "ping",
  "param1": "valeur1",
  "param2": "valeur2"
}
```

Le payload est totalement libre. Gemini Live injecte les paramètres extraits de la voix de Pierre.

### Exemples par type d'intégration

**Samsung Calendar (`samsung-calendar`) :**
```json
{
  "titre": "Réunion équipe",
  "date": "2026-09-26",
  "heure": "14:00",
  "duree_minutes": 60,
  "description": "Point hebdomadaire"
}
```

**Notion (`notion-note`) :**
```json
{
  "titre": "Idée projet",
  "contenu": "Texte de la note dictée par Pierre",
  "database_id": "xxxxx"
}
```

**Gotify (`gotify-notify`) :**
```json
{
  "titre": "Alerte Jarvis",
  "message": "Contenu de la notification",
  "priorite": 5
}
```

**Obsidian (`obsidian-note`) :**
```json
{
  "nom_fichier": "2026-09-26-note.md",
  "contenu": "# Titre\n\nContenu de la note",
  "dossier": "Journal"
}
```

### Réponse retournée par n8n → Jarvis

```json
{
  "status": "success",
  "reply": "L'événement a été ajouté à ton calendrier pour demain à 14h.",
  "data": {
    "event_id": "abc123",
    "calendar": "Pierre"
  }
}
```

---

## 4. Enregistrer l'action dans Gemini Live

### Méthode : Ajouter à `AUTOMATION_TOOL_DECLARATION`

Le fichier [`services/automation.py`](services/automation.py) contient `AUTOMATION_TOOL_DECLARATION`.
Il suffit d'ajouter le nouvel identifiant dans la description du champ `action` :

```python
# Dans services/automation.py → AUTOMATION_TOOL_DECLARATION
"description": (
    "Identifiant du workflow n8n à déclencher. "
    "Exemples : 'samsung-calendar', 'send-email', 'notion-note', "
    "'gotify-notify', 'deezer-play', 'youtube-search', 'obsidian-note', "
    "'nouveau-slug-ici'.  # ← Ajouter ici
),
```

### Méthode : Connecter à App.py (si non encore fait)

Dans `App.py`, lors de la construction des tools Gemini Live, inclure :

```python
from services.automation import executer_action_externe, AUTOMATION_TOOL_DECLARATION
from google.genai import types

# Déclarer le tool
automation_tool = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(**AUTOMATION_TOOL_DECLARATION)
    ]
)

# Dans le handler de function_call Gemini Live :
if function_call.name == "executer_action_externe":
    result = await executer_action_externe(
        action=function_call.args["action"],
        parametres=function_call.args["parametres"]
    )
    # Retourner result["reply"] à la voix Jarvis
```

---

## 5. Gestion des credentials tiers (0 €)

### Google Calendar / Gmail (OAuth2 gratuit)

1. Aller sur [Google Cloud Console](https://console.cloud.google.com/)
2. **APIs & Services** → **Enable APIs** → activer `Google Calendar API` et `Gmail API`
3. **Credentials** → **Create OAuth 2.0 Client ID** → Type : `Web application`
4. Redirect URI : `http://localhost:5678/rest/oauth2-credential/callback`
5. Dans n8n : **Settings** → **Credentials** → **New** → `Google OAuth2 API`
6. Coller `Client ID` et `Client Secret` → **Connect** → autoriser le compte Google

> ✅ **Coût : 0 €** — Le tier gratuit Google Cloud couvre largement un usage personnel.

### Notion (Integration Token gratuit)

1. Aller sur [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. **New Integration** → nommer `Jarvis` → sélectionner le workspace
3. Copier le **Internal Integration Token**
4. Dans n8n : **Credentials** → `Notion API` → coller le token
5. Dans Notion : ouvrir chaque database → **Share** → inviter l'intégration `Jarvis`

> ✅ **Coût : 0 €** — Les intégrations Notion sont entièrement gratuites.

### Gotify (self-hosted, 0 €)

1. Gotify tourne déjà sur le VPS (ou l'ajouter au `docker-compose.yml`)
2. Dans n8n : utiliser le nœud `HTTP Request` vers `http://gotify:80/message`
3. Header : `X-Gotify-Key: <app_token>`

### Obsidian (via Plugin Local REST API)

1. Installer le plugin **Local REST API** dans Obsidian
2. Configurer le port (ex: `27123`) et la clé API
3. Dans n8n : `HTTP Request` vers `http://<ip_pc>:27123/vault/<chemin>`

---

## 6. Import / Export CLI Docker

### Importer un workflow depuis un fichier JSON

```bash
# Depuis l'hôte VPS — copier le fichier dans le conteneur puis importer
docker cp ./workflows/mon_workflow.json jarvis_n8n:/tmp/import.json
docker exec jarvis_n8n n8n import:workflow --input=/tmp/import.json

# Nettoyage
docker exec jarvis_n8n rm /tmp/import.json
```

### Importer depuis Python (via services/automation.py)

```python
from services.automation import import_workflow_from_json
import json

with open("workflows/test_ping.json") as f:
    wf = json.load(f)

success = import_workflow_from_json(wf)
print("Importé !" if success else "Erreur d'import")
```

### Exporter un workflow existant

```bash
# Lister les workflows pour trouver l'ID
docker exec jarvis_n8n n8n list:workflow

# Exporter un workflow par ID
docker exec jarvis_n8n n8n export:workflow --id=<ID> --output=/tmp/export.json
docker cp jarvis_n8n:/tmp/export.json ./workflows/mon_workflow.json
```

### Exporter TOUS les workflows

```bash
docker exec jarvis_n8n n8n export:workflow --all --output=/tmp/all_workflows.json
docker cp jarvis_n8n:/tmp/all_workflows.json ./workflows/backup_all.json
```

### Importer des credentials (chiffrés)

```bash
docker exec jarvis_n8n n8n import:credentials --input=/tmp/credentials.json
```

---

## 7. Commandes de maintenance

```bash
# Démarrer / redémarrer n8n
docker compose up -d n8n
docker compose restart n8n

# Voir les logs en temps réel
docker logs -f jarvis_n8n

# Vérifier le healthcheck
docker inspect jarvis_n8n --format='{{.State.Health.Status}}'

# Accéder au shell du conteneur
docker exec -it jarvis_n8n sh

# Sauvegarder le volume n8n_data
docker run --rm -v jarvis_n8n_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/n8n_backup_$(date +%Y%m%d).tar.gz /data

# Tester un webhook manuellement (depuis le VPS)
curl -s -X POST http://localhost:5678/webhook/test-ping \
  -H "Content-Type: application/json" \
  -H "X-Jarvis-Secret: <votre_secret>" \
  -d '{"message": "ping"}' | jq
```

---

## 8. Catalogue des actions disponibles

| Action (slug) | Description | Workflow |
|---------------|-------------|---------|
| `test-ping` | Test de connectivité n8n | `workflows/test_ping.json` |
| `samsung-calendar` | Ajouter un événement Google/Samsung Calendar | À créer |
| `send-email` | Envoyer un email via Gmail | À créer |
| `notion-note` | Créer une note Notion | À créer |
| `gotify-notify` | Envoyer une notification Gotify | À créer |
| `obsidian-note` | Créer une note Obsidian | À créer |
| `youtube-search` | Rechercher sur YouTube | À créer |
| `deezer-play` | Contrôler Deezer | À créer |

> Pour ajouter une ligne à ce tableau, créer le workflow n8n correspondant, puis ajouter le slug à `AUTOMATION_TOOL_DECLARATION` dans [`services/automation.py`](services/automation.py).

---

## 9. Dépannage

### n8n ne démarre pas

```bash
# Vérifier les logs
docker logs jarvis_n8n --tail=50

# Vérifier que N8N_ENCRYPTION_KEY est défini dans .env
grep N8N_ENCRYPTION_KEY .env
```

### Webhook retourne 404

- Vérifier que le workflow est **actif** (toggle vert dans l'UI n8n)
- Vérifier que le **Path** du nœud Webhook correspond exactement au slug appelé
- Tester manuellement avec `curl` (voir section 7)

### Erreur "Unauthorized" (401)

- Vérifier que `N8N_WEBHOOK_SECRET` est identique dans `.env` et dans le nœud Webhook n8n
- S'assurer que le header `X-Jarvis-Secret` est bien envoyé par `trigger_webhook()`

### Timeout (> 30s)

- Vérifier que le nœud **Respond to Webhook** est présent à la fin du workflow
- Vérifier que le nœud Webhook a bien **"Respond: Using Respond to Webhook Node"**
- Augmenter `_HTTP_TIMEOUT` dans `services/automation.py` si l'API tierce est lente

### Import de workflow échoue

```bash
# Vérifier que Docker est accessible depuis l'environnement Python
docker ps | grep jarvis_n8n

# Tester la commande manuellement
docker exec jarvis_n8n n8n import:workflow --input=/tmp/test.json
```

---

*Guide généré le 2026-09-25 — Jarvis Core v2.0 — n8n Community Edition*
