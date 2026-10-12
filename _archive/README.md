# Archives & Composants Décommissionnés (`_archive/`)

Ce dossier conserve l'historique, les sauvegardes et les baselines du projet J.A.R.V.I.S. conformément aux règles d'architecture et de traçabilité (`_archive/ARCHITECTURE.md`).

## 1. Sous-dossiers

- **`layout-baseline-20261012-1220/`** : Baseline d'inventaire, métriques et résultats de tests initiaux capturés lors du prompt P0 avant tout refactoring d'arborescence.
- **`runtime/`** : Fichiers d'état runtime archivés lors des étapes de réorganisation (ex. `tunnel_url.json` lors de P2).
- **`legacy/`** : Composants monolithiques et scripts de maintenance jetables archivés lors du prompt P6 :
  - `App_backup_monolith.py` : Sauvegarde historique de l'ancien monolithe `App.py` (remplacé par l'architecture modulaire FastAPI/routeurs).
  - `scripts_tmp_fix_slides.py`, `scripts_tmp_fix_slides2.py`, `scripts_tmp_fix_slides3.py` : Scripts jetables utilisés pour corriger des erreurs de syntaxe ponctuelles dans `services/slides_service.py`.
  - `scripts_tmp_append_tests.py` : Script jetable d'insertion de tests unitaires pour `test_slides_service.py`.

## 2. Règle d'usage

Aucun fichier présent dans ce dossier n'est importé ni exécuté au runtime par le serveur FastAPI ou par les agents d'exploitation.
Aucun secret (clés d'API réelles, certificats ou tokens privés) ne doit être placé dans ce dossier.
