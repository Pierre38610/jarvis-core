# Architecture Firmware — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `firmware/`
Le dossier `firmware/` héberge le code embarqué et les utilitaires de build pour les périphériques matériels autonomes connectés à Jarvis :
- **Sous-dossier `firmware/esp32/`** : Implémentation C++ / ESP-IDF basée sur Xiaozhi ESP32 pour carte ESP32-S3.
- **Scripts de Build & Flash** : `build_firmware.bat`, `DEPLOY_GUIDE.sh` et configurations de compilation du microcontrôleur.
- **Protocoles Embarqués** : Gestion de la capture audio micro, haut-parleur I2S, protocoles d'encodage Opus/PCM et handshake WebSocket.

## 3. Interfaces avec les Autres Dossiers
- **`backend/`** : Le firmware se connecte en client WebSocket au serveur FastAPI sur l'endpoint `/ws/device` géré par `backend/routers/device_voice.py`.
- **`ops/`** : Les scripts d'automatisation peuvent fournir les points d'accès tunnels ou les adresses IP nécessaires à la configuration du firmware.
- **`docs/`** : Les guides d'installation et de flashage y sont référencés.
- **`frontend/`** et **`_archive/`** : Aucune interaction directe.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `firmware/` sans prompt ou instruction explicite. L'agent ne déclenche aucun flashage matériel direct ni génération de clé secrète NVS sans validation humaine.

## 5. Commandes de Vérification
```powershell
# Vérification de la présence des scripts de build
Test-Path firmware/esp32/build_firmware.bat

# Vérification de l'intégrité de l'arborescence du firmware
Get-ChildItem -Path firmware/esp32/ -Recurse -Filter CMakeLists.txt
```
