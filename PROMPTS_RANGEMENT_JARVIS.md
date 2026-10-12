# Prompts Antigravity — rangement et découpage de `Pierre38610/jarvis-core`

## Mode d’emploi

1. Ouvrir une branche dédiée et exécuter **P0** en premier. Chaque prompt est une unité de travail : ne pas lire tout le dépôt, limiter l’inspection aux fichiers listés.
2. Respecter la colonne **ordre** : les prompts « séquentiels » doivent être terminés et commités avant leurs dépendants ; les prompts parallélisables peuvent être lancés sur des branches séparées puis intégrés dans l’ordre.
3. À la fin de chaque prompt : commandes de vérification, résultat réel, `git diff --check`, commit dédié. En cas d’échec : `git revert <commit>` (ou restauration de la branche de travail), ne pas supprimer de fichier, rapporter l’erreur.
4. Aucun secret ne doit être déplacé ou copié. Les données runtime incertaines vont dans `_archive/` avec un README, jamais à la corbeille.

## Tableau récapitulatif

| N° | Rôle | Niveau | Ordre | Zone principale |
|---:|---|---|---|---|
| P0 | sauvegarde, inventaire, baseline | high | séquentiel, préalable | racine |
| P1 | squelette des sous-dossiers et règles | medium | séquentiel | racine/docs |
| P2 | frontend PWA | medium | parallèle après P1 | `frontend/` |
| P3 | firmware ESP32 | medium | parallèle après P1 | `firmware/` |
| P4 | ops, lancement Windows, déploiement | high | parallèle après P1 | `ops/` |
| P5 | docs, recettes, workflows | low | parallèle après P1 | `docs/` |
| P6 | archive des sauvegardes/scripts temporaires | low | séquentiel après P0 et P1 | `_archive/` |
| P7 | backend configuration, point d’entrée, compatibilité | high | séquentiel après P1/P4 | `backend/` |
| P8 | backend core/tools et routage des outils | high | séquentiel après P7 | `backend/` |
| P9 | backend routeurs FastAPI/WebSocket | high | séquentiel après P7 | `backend/` |
| P10 | backend services et données/config | high | séquentiel après P8/P9 | `backend/` |
| P11 | tests et import-paths | high | séquentiel après P7–P10 | `backend/tests/` |
| P12 | validation d’intégration, démarrage, documentation maître | high | séquentiel final | tout |

## Arborescence cible choisie

```text
jarvis-core/
├── backend/                         # FastAPI, état, outils, routeurs, services, DB et tests
│   ├── App.py
│   ├── config.py
│   ├── auth.py
│   ├── google_antigravity.py
│   ├── core/{shared_state.py,tools/}
│   ├── routers/
│   ├── services/
│   ├── model_registry.py, model_router.py, fallback_handler.py, prompt_builder.py
│   ├── config/models.json
│   ├── prompts/templates/
│   ├── db/
│   └── tests/
├── frontend/static/                  # HUD PWA : index.html, app.js, style.css, manifest, médias
├── firmware/esp32/                   # ancien firmware_esp32 : xiaozhi-esp32, scripts de build/flash
├── ops/                              # relais PC, tunnels, déploiement, scripts, .bat/.vbs, cloudflared
├── docs/                             # documentation et workflows n8n
├── data/                             # site_memory, gemini_ui_map, migration_reports
├── _archive/                         # sauvegardes, scripts temporaires et artefacts runtime non sûrs
├── AGENTS.md, README.md, requirements.txt, pytest.ini
└── ARCHITECTURE_COMPLETE_JARVIS.md  # index maître mis à jour
```

Les frontières sont logiques, pas une promesse d’indépendance d’exécution : `backend` dépend de `frontend` pour les chemins statiques et de `ops` pour certains contrats d’exécution ; `core/shared_state.py`, `core/tools/declarations.py` et `core/tools/dispatcher.py` restent les points de couplage à stabiliser avant tout déplacement.

## Faits à conserver comme contraintes d’architecture

- Stack décrite : Python/FastAPI asynchrone, Google Gemini Live Audio, Redis 7, PostgreSQL 16/asyncpg, Qdrant, SQLite, Docker Compose, Playwright/CDP, n8n, ESP-IDF C++ sur ESP32-S3.
- Backend documenté : `App.py`, `config.py`, `core/shared_state.py`, `core/tools/{declarations,dispatcher,arg_validator,result,verifier}.py`, 10 routeurs dans `routers/`, services métier dans `services/`.
- Interfaces critiques : `/ws`, `/ws/local-agent`, `/ws/device`, montage `/static` et `/downloads`, routeurs inclus dans `App.py`, 51 déclarations dans `core/tools/declarations.py` et alias dans `core/tools/dispatcher.py`.
- Couplages : `config.DB_PATH` vers `jarvis_memory.db`, `PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md` rechargé par `services/user_profile_service.py`, état partagé exclusivement dans `core/shared_state.py`, modèles dans `config/models.json`, résumé architectural lu par `services/architecture_service.py`, fichiers générés dans `downloads/`/`artifacts/`, Chrome CDP port 9222.
- Chemins explicites documentés : `/home/opc/jarvis-core/`, `/home/opc/jarvis-core/downloads`, `static/tunnel_url.json`, `tunnel_url.txt`, `DB_PATH`, `jarvis_memory.db`, `firmware_esp32/build_firmware.bat`, `scripts/setup_vps_chrome.sh`, `.\venv\Scripts\pytest.exe`, `sync_deploy.py`, `start_*.bat`.
- Inutiles/doublons cités : `App_backup_monolith.py` non importé ; `scripts_tmp_fix_slides*.py` et `scripts_tmp_append_tests.py` jetables ; shims racine `model_registry.py` (8 lignes), `model_router.py` (6), `fallback_handler.py` (15), `prompt_builder.py` (7), à archiver seulement après recherche d’imports.
- Règles de sécurité : pas de clé payante ni secret dans Git, pas de suppression directe, arrêt des actions financières/paiement avant validation humaine, tâches >300 ms en arrière-plan, `config.py` n’importe ni service ni routeur.

---

## P0 — Sauvegarde, inventaire et baseline

**Niveau : high — séquentiel, obligatoire.**

> Tu travailles dans `Pierre38610/jarvis-core`. Ne lis pas tout le dépôt. Inspecte uniquement : `App.py`, `config.py`, `auth.py`, `core/shared_state.py`, `core/tools/declarations.py`, `core/tools/dispatcher.py`, `routers/`, `services/`, `static/index.html`, `config/models.json`, `requirements.txt`, `pytest.ini`, `tests/conftest.py`, `README.md`, `AGENTS.md`, `start_jarvis.bat`, `sync_deploy.py`, `firmware_esp32/build_firmware.bat`.
>
> Crée `refactor/repo-layout`, puis un tag `jarvis-layout-pre-move-YYYYMMDD-HHMM`. Ne modifie encore aucun fichier. Sauvegarde les sorties dans `_archive/layout-baseline-YYYYMMDD-HHMM/` uniquement si ce dossier est nouveau et ne contient aucun secret. Exécute et consigne : `git status --short`, `git ls-files`, `grep -RInE '(^|[^A-Za-z])(App|config|shared_state|declarations|dispatcher|routers|services|static|downloads|DB_PATH|jarvis_memory|firmware_esp32|scripts_tmp)' --include='*.py' --include='*.bat' --include='*.sh' --include='*.md' .`, `python -m compileall -q App.py core routers services`, puis `.\venv\Scripts\pytest.exe -q tests/unit/` et le test ciblé `.\venv\Scripts\pytest.exe -q tests/unit/test_language_service.py` si les chemins existent. Si l’environnement est Linux, utilise `python -m pytest -q tests/unit/` et note la différence. Ne corrige rien : enregistre pass/fail/skipped et committe uniquement l’inventaire/rapport. En cas d’échec de commande, rapporte-le sans inventer une baseline.`

## P1 — Squelette, règles et contrats de déplacement

**Niveau : medium — séquentiel, après P0.**

> À partir de la branche et du tag P0, crée les dossiers vides `backend/`, `frontend/static/`, `firmware/esp32/`, `ops/`, `docs/`, `_archive/`. Ajoute un `ARCHITECTURE.md` dans chacun de ces six dossiers ; chaque fichier doit contenir : (1) une phrase sur Jarvis global, (2) le rôle précis du dossier, (3) ses interfaces avec les autres dossiers, (4) la règle « l’agent ne modifie pas hors de ce dossier sans prompt explicite », (5) ses commandes de vérification. Ajoute des `.gitkeep` seulement si nécessaire. Ne déplace encore aucun code. Mets à jour `README.md` ou `AGENTS.md` uniquement pour pointer vers ces contrats. Vérifie `find backend frontend firmware ops docs _archive -maxdepth 2 -type f`, `git diff --check`, puis commit dédié.`

## P2 — Isoler le frontend HUD

**Niveau : medium — parallélisable après P1.**

> Déplace avec `git mv` uniquement `static/index.html`, `static/app.js`, `static/style.css`, `static/manifest.json`, les SVG/PNG du HUD et `static/latest_screenshot.jpg` vers `frontend/static/`. Ne déplace pas `static/tunnel_url.json` sans vérifier son rôle runtime : s’il est généré, archive-le dans `_archive/runtime/` avec note ; sinon conserve-le dans `frontend/static/`. Avant/après, recherche `grep -RIn 'static/\|/static\|index.html\|tunnel_url.json' App.py config.py routers services ops frontend README.md docs`. Corrige les chemins statiques dans `App.py`/`config.py` sans changer les endpoints. Vérifie `python -m compileall -q App.py core routers services`, `grep -RIn 'frontend/static\|static/' App.py config.py`, et si possible démarre `python App.py` ou le serveur ASGI documenté puis teste `curl -I http://127.0.0.1:8000/`. Committe.`

## P3 — Isoler le firmware ESP32

**Niveau : medium — parallélisable après P1.**

> Déplace `firmware_esp32/xiaozhi-esp32/`, `firmware_esp32/build_firmware.bat` et `firmware_esp32/DEPLOY_GUIDE.sh` vers `firmware/esp32/`. Ne touche pas au code Python backend. Recherche d’abord `grep -RIn 'firmware_esp32\|xiaozhi-esp32\|build_firmware.bat\|DEPLOY_GUIDE.sh\|/ws/device' App.py config.py routers services ops docs README.md`. Corrige uniquement les références documentaires et chemins du script de build si elles deviennent fausses. Ne flashe pas de carte et ne crée aucun token NVS. Vérifie `grep -RIn 'firmware_esp32' . --exclude-dir=.git`, `test -f firmware/esp32/build_firmware.bat`, et la présence des fichiers C++/ESP-IDF. Committe.`

## P4 — Isoler ops, relais local et scripts de lancement

**Niveau : high — parallélisable après P1 ; dépend de P0 pour les chemins.**

> Crée `ops/launchers/`, `ops/windows/`, `ops/deploy/`, `ops/scripts/`, puis déplace explicitement : `jarvis_local_agent.py`, `local_browser_actions.py`, `tunnel_launcher.py` vers `ops/windows/` ; `start_jarvis.bat`, `start_local_agent.bat`, `stop_agent.bat`, `view_logs.bat`, `start_agent_silent.vbs`, `install_autostart.bat`, `uninstall_autostart.bat`, `open_n8n_tunnel.bat` vers `ops/windows/`; `sync_deploy.py`, `sync_deploy.bat`, `install_antigravity_arm64.sh`, `cloudflared.exe` vers `ops/deploy/`; le contenu de `scripts/` vers `ops/scripts/`. Avant chaque `git mv`, vérifie `grep -RIn 'jarvis_local_agent\|local_browser_actions\|tunnel_launcher\|sync_deploy\|scripts/\|start_local_agent\|cloudflared' App.py config.py core routers services tests docs README.md *.bat *.sh 2>/dev/null`. Corrige les imports Python et les chemins relatifs des `.bat/.vbs/.sh` vers la racine réelle ; ne change pas les hôtes, ports, commandes systemd ni secrets. Vérifie `python -m compileall -q ops/windows ops/deploy ops/scripts`, `grep -RIn 'ops/' App.py core routers services`, et un lancement `python ops/windows/jarvis_local_agent.py --help` seulement si supporté. N’exécute pas de déploiement distant. Committe.`

## P5 — Ranger la documentation et les workflows

**Niveau : low — parallélisable après P1.**

> Déplace vers `docs/` les documents déjà listés : `VPS_L3_ACTIONS_RESTANTES.md`, `VPS_L3_CHECKLIST.md`, `VPS_GOOGLE_SESSION_SETUP.md`, `BROWSER_AGENT_SPEC.md`, `N8N_GUIDE.md`, ainsi que `docs/n8n_workflows/*.json` en conservant le sous-dossier. Ne déplace pas `ARCHITECTURE_COMPLETE_JARVIS.md`, `AGENTS.md`, `README.md` ni `PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md`. Recherche les liens avant/après avec `grep -RIn 'VPS_L3\|BROWSER_AGENT_SPEC\|N8N_GUIDE\|n8n_workflows' . --exclude-dir=.git`. Corrige les liens Markdown cassés, sans changer le contenu métier. Vérifie `find docs -type f`, un script Python simple qui vérifie les liens relatifs existants, `git diff --check`, puis committe.`

## P6 — Archiver les sauvegardes et scripts jetables, sans suppression

**Niveau : low — séquentiel après P0/P1.**

> Avant tout déplacement, exécute `grep -RIn 'App_backup_monolith\|scripts_tmp_fix_slides\|scripts_tmp_append_tests' . --exclude-dir=.git`. Si aucune référence runtime n’existe, déplace avec `git mv` vers `_archive/legacy/` : `App_backup_monolith.py`, tous les fichiers correspondant exactement à `scripts_tmp_fix_slides*.py`, `scripts_tmp_append_tests.py`. Si une référence existe, ne déplace pas le fichier ; crée une note dans `_archive/README.md`. N’archive jamais `authorized_devices.json`, `qr_tickets.json`, `jarvis_memory.db`, `jarvis_agent.log` ou un fichier contenant potentiellement des secrets sans inspection ciblée et exclusion Git. Vérifie `git grep -n` sur les anciens noms, `git diff --name-status`, puis committe. Aucune suppression directe.`

## P7 — Déplacer le socle backend et préserver la compatibilité

**Niveau : high — séquentiel après P1/P4.**

> Déplace vers `backend/` avec `git mv` : `App.py`, `config.py`, `auth.py`, `google_antigravity.py`, `services/google_antigravity.py`, `services/antigravity_models.py`, `services/agentic_runner.py`, `services/agentic_dispatcher.py`, `services/key_gate.py`, `services/llm_router.py`, `services/live_mode_policy.py`, `services/task_planner.py`, `services/turn_audit.py`, et les quatre shims racine `model_registry.py`, `model_router.py`, `fallback_handler.py`, `prompt_builder.py`. Ne supprime pas les shims : ils restent dans `backend/` tant que `grep -RIn` ne prouve pas qu’aucun import legacy n’existe. Mets à jour les imports et les chemins de lancement vers `backend/App.py`; conserve un point d’entrée racine seulement si un script existant l’exige, et documente-le. Vérifie `grep -RInE 'from (config|auth|google_antigravity|model_registry|model_router|fallback_handler|prompt_builder)|import (config|auth|google_antigravity)' backend ops tests`, `python -m compileall -q backend`, et `python -c 'import sys; sys.path.insert(0,"backend"); import config; print(config.DB_PATH)'`. Aucun changement de comportement. Committe.`

## P8 — Déplacer core/tools et verrouiller le contrat 51 outils

**Niveau : high — séquentiel après P7.**

> Déplace `core/shared_state.py` et tout `core/tools/` (`declarations.py`, `dispatcher.py`, `arg_validator.py`, `result.py`, `verifier.py`) vers `backend/core/`. Mets à jour les imports dans `backend/App.py`, `backend/routers/`, `backend/services/`, `backend/tests/` et `ops/`. Ne renomme aucune fonction, alias d’outil, `ToolResult`, `BROWSER_TASKS`, `active_task_controller`, `speech_lock` ou `stop_current_action`. Vérifie les invariants avec `grep -c 'FunctionDeclaration' backend/core/tools/declarations.py`, `grep -RIn 'core.shared_state\|core.tools\|shared_state\|dispatcher\|declarations' backend ops`, `python -m compileall -q backend`, puis les tests ciblés mentionnant `dispatcher`, `tool`, `browser_task`, `ToolResult`. Si le nombre de déclarations ou un import baisse, revert et rapport. Committe.`

## P9 — Déplacer les routeurs FastAPI et conserver les endpoints

**Niveau : high — séquentiel après P7 ; peut être réparti par fichiers mais intégré séquentiellement.**

> Déplace vers `backend/routers/` les fichiers explicitement cités : `voice.py`, `device_voice.py`, `local_agent.py`, `chat.py`, `spotify.py`, `browser.py`, `supervision.py`, `settings.py`, `briefing.py`, `transport.py`. Corrige uniquement imports, `App.py` et chemins de templates/static/downloads. Avant/après, capture les routes avec `grep -RInE '@(app|router)\.(get|post|put|delete|websocket)' backend/App.py backend/routers`, et capture les trois WebSockets `/ws`, `/ws/local-agent`, `/ws/device`. Vérifie `python -m compileall -q backend`, `python -c 'import sys; sys.path.insert(0,"backend"); import App; print("app import ok")'`, puis démarre le serveur documenté et teste `curl -I http://127.0.0.1:8000/` si les dépendances sont disponibles. Ne modifie ni auth ni contrats JSON. Committe.`

## P10 — Déplacer les services, config, prompts et DB

**Niveau : high — séquentiel après P8/P9.**

> Déplace vers `backend/services/` tous les services déjà présents dans `services/`, en conservant les sous-dossiers `model_routing/` et `browser_agent/recipes/`. Déplace `config/models.json` vers `backend/config/models.json`, `prompts/templates/` vers `backend/prompts/templates/`, et `db/` vers `backend/db/`. Inclus explicitement : `cache.py`, `memory.py`, `memory_service.py`, `unified_memory.py`, `user_profile_service.py`, `auth_service.py`, `browser_service.py`, `download_service.py`, `email_service.py`, `slides_service.py`, `transport_service.py`, `spotify_service.py`, `language_service.py`, `metrics_service.py`, `system_healing_service.py`, `architecture_service.py`, `workspace_service.py`, `voice_injection_queue.py`, et les fichiers effectivement présents. Avant déplacement, recherche `grep -RIn 'config/models.json\|prompts/templates\|db/schema.sql\|DB_PATH\|jarvis_memory.db\|PROFIL_CANDIDATURE\|downloads/\|artifacts/' backend ops tests docs`. Corrige les chemins via `pathlib`/config sans hardcoder de nouvelle machine ; `config.py` reste sans import de service/routeur. Vérifie `python -m compileall -q backend`, import App, test ciblé mémoire/auth/routing, et `git diff --check`. Committe.`

## P11 — Tests, imports et package boundaries

**Niveau : high — séquentiel après P7–P10.**

> Déplace `tests/` vers `backend/tests/` seulement après avoir vérifié que les scripts de lancement et `pytest.ini` sont corrigés. Conserve `tests/unit/`, `tests/e2e/`, `conftest.py`, `run_all_tests.py`; ne déplace pas les tests dans `_archive/`. Mets à jour `pytest.ini`, `README.md`, `AGENTS.md` et les commandes `.\venv\Scripts\pytest.exe -v backend/tests/`. Recherche les anciens chemins avec `grep -RIn 'tests/\|from services\|from routers\|from core\|from config' . --exclude-dir=.git`. Vérifie `python -m compileall -q backend`, `python -m pytest -q backend/tests/unit/test_language_service.py`, puis `python -m pytest -q backend/tests/unit/` ; lance `backend/tests/e2e/` seulement si l’environnement le permet. Compare le nombre de tests collectés avant/après à la baseline P0. Revert si une régression d’import n’est pas expliquée. Committe.`

## P12 — Validation finale, démarrage et documentation maître

**Niveau : high — séquentiel final.**

> Inspecte seulement les surfaces critiques : `backend/App.py`, `backend/config.py`, `backend/core/shared_state.py`, `backend/core/tools/declarations.py`, `backend/core/tools/dispatcher.py`, `backend/routers/`, `backend/services/architecture_service.py`, `backend/tests/conftest.py`, `frontend/static/index.html`, `ops/`, `firmware/esp32/build_firmware.bat`, `ARCHITECTURE_COMPLETE_JARVIS.md`. Vérifie : `grep -RInE '(^|[^A-Za-z])(static|downloads|DB_PATH|jarvis_memory|/ws|local-agent|device|config/models.json|PROFIL_CANDIDATURE|/home/opc/jarvis-core)' backend frontend ops firmware docs`, `python -m compileall -q backend`, `python -m pytest -q backend/tests/unit/`, import `App`, puis démarrage ASGI et `curl -I http://127.0.0.1:8000/` avec timeout. Ne déploie pas et n’exécute pas `sync_deploy.py`. Mets à jour `ARCHITECTURE_COMPLETE_JARVIS.md` avec la nouvelle arborescence, chaque chemin déplacé, les interfaces `/ws`, `/ws/local-agent`, `/ws/device`, `/static`, `/downloads`, le nouveau chemin DB/config, les commandes de test et les limites. Vérifie que `backend/ARCHITECTURE.md`, `frontend/ARCHITECTURE.md`, `firmware/ARCHITECTURE.md`, `ops/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `_archive/ARCHITECTURE.md` existent et décrivent leurs interfaces. `git diff --check`, rapport pass/fail détaillé, commit final et tag `jarvis-layout-complete-YYYYMMDD-HHMM`. En cas d’échec, revert le dernier prompt et ne prétends pas que le serveur a démarré.`

---

## Éléments illisibles ou incertains

Le fichier de référence a été lu intégralement comme texte UTF-8 (193 112 octets, 1 627 lignes) ; aucune portion illisible n’a été détectée. Il contient toutefois des affirmations historiques à vérifier dans le dépôt réel avant déplacement : « 652 tests vérifiés », « 51 outils » alors qu’une note de routes indique 57 endpoints HTTP, chemins runtime générés (`tunnel_url.txt`, `static/tunnel_url.json`, `jarvis_memory.db`, logs), et certains noms de services apparaissent dans la description sans être visibles dans l’arborescence abrégée. Les prompts demandent donc une vérification locale et interdisent d’inventer une réussite.
