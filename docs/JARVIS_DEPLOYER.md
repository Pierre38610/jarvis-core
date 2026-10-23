# J.A.R.V.I.S. VPS Deployer — Service & Déploiement Blue/Green

Le déployeur indépendant J.A.R.V.I.S. (`ops/deploy/jarvis_deployer.py`) assure le cycle de vie Blue/Green sécurisé avec releases horodatées, symlink atomique, smoke tests et surveillance avec auto-rollback.

---

## 1. Installation Manuelle de l'Unité systemd

Sur le VPS Oracle Cloud (`opc@158.178.206.213`) :

```bash
# 1. Copier l'unité systemd dans le répertoire système
sudo cp /home/opc/jarvis-core/ops/scripts/jarvis-deployer.service /etc/systemd/system/jarvis-deployer.service

# 2. Recharger les démons systemd
sudo systemctl daemon-reload

# 3. Activer et démarrer le service déployeur
sudo systemctl enable --now jarvis-deployer

# 4. Vérifier le statut actif
sudo systemctl status jarvis-deployer --no-pager
```

> **Note de priorité CPU** : L'unité configure `Nice=10` afin que les opérations de build, compilation et packaging du déployeur ne concurrencent jamais l'allocation CPU du flux vocal temps réel (`jarvis.service`).

---

## 2. Modes d'Exécution CLI

```bash
# Lancement démon serveur loopback (http://127.0.0.1:8001)
python -m ops.deploy.jarvis_deployer --server

# Déploiement unique synchrone (s'arrête automatiquement à la fin)
python -m ops.deploy.jarvis_deployer --once

# Simulation sans bascule de production (dry-run)
python -m ops.deploy.jarvis_deployer --dry-run --once

# Rollback manuel vers la release précédente
python -m ops.deploy.jarvis_deployer --rollback

# Consultation de l'état persistant
python -m ops.deploy.jarvis_deployer --status
```

---

## 3. Endpoints API Loopback (Port 8001)

- `GET /health` : Statut du déployeur.
- `GET /status` : État courant, verrou et releases actives.
- `GET /history` : Historique des 50 derniers déploiements.
- `POST /deploy` : Déclenche un déploiement Blue/Green.
- `POST /rollback` : Déclenche un retour arrière immédiat vers la release précédente.
