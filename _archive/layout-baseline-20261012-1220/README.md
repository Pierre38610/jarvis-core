# J.A.R.V.I.S. — Baseline et Inventaire Initial (Prompt P0)

- **Date d'exécution** : 12 octobre 2026 - 12:20 CEST
- **Branche Git créée** : `refactor/repo-layout`
- **Tag Git pré-déplacement** : `jarvis-layout-pre-move-20261012-1220` (sur le commit HEAD `5925a25`)
- **Dossier de sauvegarde** : `_archive/layout-baseline-20261012-1220/`
- **Environnement d'exécution** : Windows 11 (win32), PowerShell, Python 3.13.9, pytest-9.1.1, pluggy-1.6.0

---

## 1. Périmètre d'Inspection Strict (P0)

Conformément aux instructions du mandat P0, seuls les fichiers et dossiers suivants ont été inspectés :
- `App.py`
- `config.py`
- `auth.py`
- `core/shared_state.py`
- `core/tools/declarations.py`
- `core/tools/dispatcher.py`
- `routers/` (10 routeurs modulaires + `__init__.py`)
- `services/` (46 modules et sous-services + sous-dossiers `model_routing/` et `browser_agent/`)
- `static/index.html` (HUD PWA v5.95.0)
- `config/models.json` (catalogue des modèles LLM et quotas)
- `requirements.txt`
- `pytest.ini`
- `tests/conftest.py`
- `README.md`
- `AGENTS.md`
- `start_jarvis.bat`
- `sync_deploy.py`
- `firmware_esp32/build_firmware.bat`

**Aucun fichier de code source n'a été modifié.**

---

## 2. Commandes Exécutées et Fichiers de Consignation

| N° | Commande demandée | Fichier consigné | Statut / Résultat |
|:---|:---|:---|:---|
| 1 | `git status --short` | `01_git_status_short.txt` | working tree capturé (submodule `firmware_esp32/xiaozhi-esp32`, untracked prompt) |
| 2 | `git ls-files` | `02_git_ls_files.txt` | **251** fichiers suivis par Git dans le dépôt |
| 3 | `grep -RInE '(^|[^A-Za-z])(App\|config\|shared_state\|declarations\|dispatcher\|routers\|services\|static\|downloads\|DB_PATH\|jarvis_memory\|firmware_esp32\|scripts_tmp)' --include='*.py' --include='*.bat' --include='*.sh' --include='*.md' .` | `03_grep_references.txt` | **5 620** occurrences architecturales relevées et localisées |
| 4 | `python -m compileall -q App.py core routers services` | `04_compileall.txt` | **PASS (Exit 0)** — Tous les modules cibles compilent sans erreur de syntaxe |
| 5 | `.\venv\Scripts\pytest.exe -q tests/unit/` | `05_pytest_unit.txt` | **232 collectés : 223 passed, 18 errors** (voir analyse encodage Windows ci-dessous) |
| 6 | `.\venv\Scripts\pytest.exe -q tests/unit/test_language_service.py` | `06_pytest_targeted_test_language_service.txt` | **PASS : 13 passed in 0.08s (100%)** |

---

## 3. Détail des Résultats de Tests & Différence Environnement (Windows vs Linux)

### 3.1. Test ciblé `tests/unit/test_language_service.py`
- **Résultat** : 13 passed / 13 en 0.08s.
- **Statut** : **PASS**.

### 3.2. Campagne complète `tests/unit/`
- **Collecte** : 232 tests unitaires répartis sur 24 modules de tests.
- **Tests passés avec succès** : **223 passed**.
- **Erreurs relevées (18 erreurs sur 9 tests)** :
  - `tests/unit/test_voice_fluidity.py` (2 tests : `test_open_browser_returns_synchronously`, `test_generer_presentation_returns_background_status`)
  - `tests/unit/test_voice_injection_queue.py` (5 tests)
  - `tests/unit/test_voice_multisession.py` (2 tests)
- **Cause racine factuelle** :
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x82 in position 82: invalid start byte`
  Survenant dans `_pytest/capture.py` (`snap()` via `res = self.tmpfile.read()`).
  Le byte `0x82` correspond au caractère accentué `'é'` encodé en page de code Windows OEM (CP850 / CP1252) émis dans un flux de capture console intercepté par pytest. Lorsque le test est exécuté sans capture standard (`-s`), les assertions passent nominalement (ex. `test_voice_multisession.py`: 2 passed).
- **Note d'environnement (Windows vs Linux)** :
  Sous un environnement Linux (tel que le VPS Oracle Cloud Ubuntu ARM64 cible), le flux standard utilise UTF-8 de bout en bout (`LANG=C.UTF-8`), éliminant ce conflit de décodage spécifique à la console Windows PowerShell / CP850.

Conformément à la consigne P0 (*« Ne corrige rien : enregistre pass/fail/skipped et committe uniquement l'inventaire/rapport »*), aucun fichier de test ni de configuration n'a été altéré.

---

## 4. Vérification d'Absence de Secrets

Le dossier `_archive/layout-baseline-20261012-1220/` contient exclusivement :
- Les listes d'inventaire Git et de références textuelles.
- Les logs textuels des commandes de test et de compilation.
- Ce rapport de synthèse.

Aucune clé d'API, aucun token ni secret n'y est consigné.
