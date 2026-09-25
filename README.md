# ✦ J.A.R.V.I.S. Core — Stark Industries AI Assistant ✦

Serveur central et orchestrateur modulaire pour J.A.R.V.I.S., déployé sur instance **Oracle Cloud Ubuntu ARM64 (Ampere A1 - 4 OCPU, 24 Go RAM)**.

---

## 🏛 Architecture & Infrastructure Modulaire

L'architecture s'appuie sur une stack Docker locale hautement performante, liée exclusivement sur `127.0.0.1` pour garantir une sécurité hermétique face au réseau public :

```
                        ┌──────────────────────────────┐
                        │   J.A.R.V.I.S. FastAPI Core   │
                        │    (App.py & services/*)     │
                        └──────────────┬───────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
┌──────────────┐               ┌──────────────┐               ┌──────────────┐
│    REDIS 7   │               │  POSTGRES 16 │               │    QDRANT    │
│    Alpine    │               │    Alpine    │               │  Vector DB   │
├──────────────┤               ├──────────────┤               ├──────────────┤
│ Cache TTL    │               │ Données      │               │ Mémoire      │
│ Heartbeat    │               │ relation-    │               │ sémantique,  │
│ Devices      │               │ nelles,      │               │ embeddings & │
│ Pub / Sub    │               │ historiques  │               │ recherche RAG│
│ 127.0.0.1    │               │ 127.0.0.1    │               │ 127.0.0.1    │
│ Port: 6379   │               │ Port: 5432   │               │ Port: 6333   │
└──────────────┘               └──────────────┘               └──────────────┘
```

---

## 🚀 Déploiement Rapide de la Stack Infrastructure (ARM64 VM)

### 1. Variables d'environnement requises (`.env`)

Assurez-vous que votre fichier `.env` sur le VPS et en local contient les variables suivantes (référez-vous à `.env.example`) :

```env
# ─── REDIS 7 (Cache & PubSub) ───
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=votre_mot_de_passe_redis_robuste
REDIS_DB=0

# ─── POSTGRESQL 16 ───
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=jarvis
POSTGRES_USER=jarvis_admin
POSTGRES_PASSWORD=votre_mot_de_passe_postgres_robuste

# ─── QDRANT ───
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
QDRANT_API_KEY=
```

### 2. Commandes Docker Compose

Depuis le répertoire du projet `/home/opc/jarvis-core` (ou en local) :

#### Démarrer l'ensemble des services en arrière-plan
```bash
docker compose up -d
```

#### Vérifier l'état et la santé des conteneurs
```bash
docker compose ps
```

#### Consulter les logs en temps réel
```bash
# Logs globaux
docker compose logs -f

# Logs ciblés Redis
docker compose logs -f redis

# Logs ciblés PostgreSQL
docker compose logs -f postgres

# Logs ciblés Qdrant
docker compose logs -f qdrant
```

#### Arrêter ou redémarrer la stack
```bash
# Arrêter sans supprimer les données
docker compose stop

# Redémarrer les services
docker compose restart

# Arrêter et libérer les conteneurs (les données persistent dans les volumes Docker)
docker compose down
```

---

## ⚡ Module Cache & État Temps Réel (`services/cache.py`)

Le module `services.cache.cache_service` offre une interface unifiée asynchrone avec **dégradation gracieuse** (fallback en mémoire vive transparente si Redis est hors ligne) :

### 1. Cache Clé / Valeur avec TTL
```python
from services.cache import cache_service

# Enregistrement avec expiration de 60 secondes (sérialise automatiquement dict/list)
await cache_service.set("user:session:pierre", {"role": "owner", "level": 1}, ttl=60)

# Récupération (désérialisation JSON automatique)
session = await cache_service.get("user:session:pierre", default=None)

# Suppression & vérification
exists = await cache_service.exists("user:session:pierre")
await cache_service.delete("user:session:pierre")
```

### 2. Gestion de la présence des Devices (Heartbeat temps réel)
```python
# Mettre à jour l'état du PC local ou d'un smartphone (TTL de 300s)
await cache_service.set_device_presence(
    device_name="pc_bureau",
    status="online",
    ttl=300,
    metadata={"os": "Windows 11", "agent_version": "1.0.0"}
)

# Récupérer l'état d'un device spécifique
pc_status = await cache_service.get_device_presence("pc_bureau")
# -> {"device": "pc_bureau", "status": "online", "last_seen": "...", "metadata": {...}}

# Récupérer l'ensemble des devices actifs
all_active = await cache_service.get_all_devices_presence()
```

### 3. Système Pub / Sub Asynchrone
```python
# Publication d'un événement
await cache_service.publish("jarvis:system:alerts", {"level": "INFO", "msg": "Stack démarrée"})

# Écoute d'un canal (dans une tâche asynchrone)
async for message in cache_service.listen_channel("jarvis:system:alerts"):
    print(f"Événement reçu : {message}")
```

---

## 🔄 Synchronisation & Déploiement Continu

Pour déployer les modifications instantanément vers GitHub et sur le VPS Oracle Cloud :

```powershell
# En ligne de commande Windows
.\venv\Scripts\python.exe sync_deploy.py -m "Modularisation stack docker et cache Redis"
# Ou via le script batch
.\sync_deploy.bat "Modularisation stack docker et cache Redis"
```

Ce script effectue :
1. Commit & `git push origin main`
2. Téléversement optimisé vers le VPS (`158.178.206.213`)
3. Redémarrage transparent du service systemd `jarvis`
