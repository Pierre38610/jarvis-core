# Architecture Archive & Historique — J.A.R.V.I.S. Core

## 1. Vision Globale de Jarvis
J.A.R.V.I.S. est un assistant IA multimodal et modulaire articulé autour de FastAPI asynchrone, de Google Gemini Live Audio et d'une infrastructure distribuée (Cloud VPS Oracle ARM64, relais PC local Windows et microcontrôleurs embarqués ESP32-S3).

## 2. Rôle Précis du Dossier `_archive/`
Le dossier `_archive/` est une zone de sauvegarde passive et de traçabilité historique :
- **Baselines Préalables** : Snapshots d'inventaires, hashs et bilans de tests (ex. `layout-baseline-*`).
- **Composants & Scripts Décommissionnés** : Anciens scripts temporaires, sauvegardes monolithiques legacy (`App_backup_monolith.py`), shims obsolètes après vérification complète.
- **Règle Fondamentale d'Archivage** : Les fichiers ne sont jamais supprimés directement à la corbeille lors du refactoring ; ils sont déplacés dans `_archive/` avec une documentation expliquant leur origine et motif de retrait.

## 3. Interfaces avec les Autres Dossiers
- **Aucune dépendance runtime** : Le dossier `_archive/` est strictement passif. Aucun code actif situé dans `backend/`, `frontend/`, `firmware/` ou `ops/` ne doit importer ou invoquer de fichier situé dans `_archive/`.
- Tout artefact contenant potentiellement des secrets, tokens ou clés privées est strictement banni de l'archive et exclu de Git.

## 4. Règle de Confinement
> **RÈGLE STRICTE** : L'agent ne modifie aucun fichier en dehors du dossier `_archive/` sans prompt ou instruction explicite. Tout ajout dans `_archive/` doit être motivé et documenté dans un README ou rapport associé.

## 5. Commandes de Vérification
```powershell
# Vérification de l'absence totale d'import vers _archive depuis le code actif
Select-String -Path backend\*.py,ops\*.py -Pattern '(_archive|legacy)'
```
