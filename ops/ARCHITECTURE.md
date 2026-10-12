# Architecture Ops & Déploiement — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `ops/`
Le dossier `ops/` regroupe l'outillage opérationnel, les scripts de lancement local Windows, le relais machine hôte et le pipeline de déploiement continu :
- **`ops/windows/`** : Agent local exécuté sur le poste Windows (`jarvis_local_agent.py`, `local_browser_actions.py`, `tunnel_launcher.py`), scripts de lancement et contrôle (`start_jarvis.bat`, `start_local_agent.bat`, `stop_agent.bat`, `view_logs.bat`, `start_agent_silent.vbs`).
- **`ops/deploy/`** : Scripts de synchronisation cloud vers VPS (`sync_deploy.py`, `sync_deploy.bat`, `install_antigravity_arm64.sh`), binaire `cloudflared.exe`.
- **`ops/scripts/`** : Scripts d'administration système et configuration du serveur (ex. `setup_vps_chrome.sh`).

## 3. Interfaces avec les Autres Dossiers
- **`backend/`** : Démarre l'instance `backend/App.py`. L'agent local Windows se connecte au serveur FastAPI via le WebSocket `/ws/local-agent` pour exécuter des actions locales (actions OS, navigateur Chrome CDP 9222). Le pipeline de déploiement pousse le code et redémarre le service systemd `jarvis`.
- **`frontend/`** : Déploie les assets statiques et s'assure de l'alignement des numéros de version.
- **`firmware/`** : Peut exposer des tunnels ou endpoints utilisés pour orienter le firmware ESP32.
- **`docs/`** : S'appuie sur les guides VPS et checklists d'exploitation.
- **`_archive/`** : Aucune interaction directe.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `ops/` sans prompt ou instruction explicite. Ne jamais exécuter de commande destructive (`git push --force`, purge de dossiers hors périmètre) ni exposer de clés SSH ou tokens d'API.

## 5. Commandes de Vérification
```powershell
# Compilation syntaxique Python des composants ops
python -m compileall -q ops

# Vérification de l'intégrité des scripts de lancement et déploiement
Test-Path ops/deploy/sync_deploy.py, ops/windows/jarvis_local_agent.py
```
