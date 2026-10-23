# Prompts d’implémentation — circuit d’auto-amélioration de Jarvis

## Prérequis manuels

- Dépôt ciblé : `Pierre38610/jarvis-core`, branche `main`.
- Créer un token GitHub fine-grained limité à ce dépôt : contenu/branches/PRs, sans droits d’administration inutiles. Le stocker uniquement dans `.env` (jamais dans le dépôt, les logs, les prompts persistés ou les rapports).
- Renseigner les variables `.env` nécessaires : token GitHub, identifiant Telegram et token Bot Telegram, limites de crédits, chemins runtime, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (ou mot de passe d’application Gmail), `SMTP_FROM`, `SMTP_TO` et `SMTP_USE_TLS`. Ne jamais committer `.env`, une IP, un `chatId`, un JWT, un mot de passe ou une clé API. Les secrets doivent être lus par l’environnement ou un fichier de secrets hors dépôt. Pour Gmail, utiliser SMTP authentifié/TLS et un mot de passe d’application, jamais le mot de passe principal.
- Configurer manuellement la protection de `main` : PR obligatoire, CI verte, revue obligatoire, interdiction du push direct, et éventuellement CODEOWNERS obligatoire.
- Installer manuellement les unités systemd sur le VPS, avec utilisateur dédié, répertoires d’état persistants et permissions minimales. `jarvis-deployer.service` doit être un processus distinct de `jarvis.service`.
- Le code doit fonctionner 100 % sur le VPS, en mode headless : aucun PC Windows, téléphone/PWA, enceinte ESP32 ou client connecté ne doit être requis. Telegram est le seul canal de notification utilisateur.

## Règles d’exécution pour l’agent (à respecter dans TOUS les prompts)

- Chaque commande doit se terminer d’elle-même. Préfixer les commandes par `timeout 120` (ou `timeout 600` pour `pytest`). Si une commande dépasse 2 minutes, l’arrêter et le signaler au lieu d’attendre.
- Ne jamais utiliser `-f`/`--follow` (`journalctl -f`, `tail -f`, etc.), ni lancer un serveur/daemon au premier plan. Si un processus temporaire est indispensable : lancement en arrière-plan avec `timeout 30`, `nohup`, capture du PID, puis arrêt de ce PID uniquement.
- Ne jamais exécuter `sudo`, `systemctl`, `journalctl`, `reboot`, `pkill` ou `killall`, ni redémarrer/tuer le processus Jarvis, des processus Python ou l’environnement de l’agent. Ne jamais effectuer le vrai basculement du symlink `current`.
- Ne jamais toucher aux releases, au `current` ou au service réels sous `/opt/...`. Utiliser exclusivement `tmp_path`/répertoires temporaires et une variable `JARVIS_DEPLOY_ROOT` pointant vers un dossier temporaire.
- Toute commande doit être non interactive : `CI=1`, `GIT_TERMINAL_PROMPT=0`, options `-y` uniquement quand elles existent et aucun prompt Git/SSH/apt. Pas de réseau dans les tests.
- Rendre les durées de surveillance configurables par environnement (par exemple `DEPLOY_MONITOR_SECONDS`) et les fixer à 1–3 secondes dans les tests. Mocker subprocess, systemd et les probes HTTP/health ; ne pas appeler agy en réel dans les tests et ne pas lancer de longues sessions d’agent.
- Les étapes systemd/sudo/installation réelle sont laissées à l’utilisateur et doivent figurer sous **À faire par l’utilisateur** à la fin du prompt concerné.

## Ordre d’exécution

Exécuter les prompts dans l’ordre : **1 → 2 → 3 → 4 → 5 → 6 → 7 → 8**. Après chaque étape, relire le résumé de l’agent, vérifier le diff, puis exécuter les commandes de test indiquées. Ne passer à l’étape suivante que si les critères sont satisfaits. Les prompts sont autonomes et destinés à Gemini Flash dans Antigravity IDE, modèle moyen.

### Tableau de synthèse

| Prompt | Sujet | Niveau / routage agy |
|---:|---|---|
| 1A/1B | Déployeur testable + smoke CLI/systemd | 1A high → Pro/high ; 1B medium → Flash/medium |
| 2 | CI, CODEOWNERS, chemins protégés | medium → Flash/medium |
| 3 | Outil `self_improve`, PR, crédits | high → Pro/high |
| 4 | Validation Telegram, reprise | high → Pro/high |
| 5 | Veille L2 hebdomadaire | medium → Flash/medium |
| 6 | Mode arrière-plan VPS | high → Pro/high |
| 7 | Runner de séries `prompt_batch_runner` | high → Pro/high |
| 8 | Test E2E dry-run, dont mini-batch | high → Pro/high |

Pour tout nouveau niveau, mapper explicitement `low → Flash/low`, `medium → Flash/medium`, `high → Pro/high` (avec repli autorisé conforme au routeur existant).

## Repères réels du dépôt à respecter

- Cœur : `backend/App.py`, `backend/config.py`, `backend/core/tools/declarations.py`, `backend/core/tools/dispatcher.py`, `backend/core/tools/arg_validator.py`, `backend/core/tools/result.py`.
- Services utiles : `backend/services/console_monitor.py`, `deep_research_service.py`, `agentic_runner.py`, `briefing_service.py`, `system_healing_service.py`, `vps_chrome.py`, `google_antigravity.py`, `search_router.py`.
- Tests : `backend/tests/conftest.py`, `backend/tests/`, `backend/tests/unit/`.
- Déploiement : `sync_deploy.py` est un shim racine ; l’implémentation est `ops/deploy/sync_deploy.py`. Les scripts présents sont `ops/deploy/install_antigravity_arm64.sh`, `ops/deploy/sync_deploy.bat`, et `ops/scripts/jarvis-chrome.service`.
- Ag y : `backend/services/agentic_runner.py`, `backend/services/google_antigravity.py`, `backend/services/antigravity_models.py`, `backend/services/model_routing/`, avec précontrôle `verify_antigravity_cli_ready()`, commande `agy -p ... --dangerously-skip-permissions --output-format text`, `--model`, `--effort`, et interdiction de `--thinking`.
- Recherche : `launch_deep_research` est déclaré dans `backend/core/tools/declarations.py`, dispatché dans `backend/core/tools/dispatcher.py`, et le pipeline L2 parallèle est documenté dans `backend/services/agentic_runner.py` (`run_l2_parallel_agents`, `cross_check_l2_results`) ; la recherche L3 Gemini Web existe aussi mais est interdite pour la veille demandée.
- Morning briefing : `backend/services/briefing_service.py` ; l’architecture annonce 6 h 45 et Telegram, mais aucun routeur Telegram dédié n’est présent dans `backend/routers/`.

---

## Prompt 1A — Déployeur testable et tests unitaires

**Niveau conseillé : high** — orchestration de processus, rollback et sécurité opérationnelle ; une lecture approfondie réduit les erreurs irréversibles.

Dans `Pierre38610/jarvis-core`, implémente le cœur d’un déployeur VPS indépendant de `jarvis.service`, mais entièrement testable hors VPS.

**À lire explicitement :** `backend/services/console_monitor.py`, `backend/services/system_healing_service.py`, `backend/services/vps_chrome.py`, `sync_deploy.py`, `ops/deploy/sync_deploy.py`, `ops/scripts/jarvis-chrome.service`, `backend/App.py`, `backend/tests/conftest.py`.

**À créer/modifier :**
- créer `ops/deploy/jarvis_deployer.py` avec une API locale file/Unix socket ou HTTP loopback, idempotence et verrou mono-déploiement ;
- injecter la racine de déploiement (`JARVIS_DEPLOY_ROOT`), le runner de commandes et les probes health/Chrome/Telegram ;
- créer un module de tests offline sous `backend/tests/` pour file, états, rollback, timeouts, seuils et reprise ; utiliser uniquement `tmp_path` et des mocks.

Contrat minimal : demande persistante `queued/running/smoke/monitoring/succeeded/rolled_back/failed`, journal append-only, timeout, reprise après redémarrage et rapport Telegram via un adaptateur mockable. Implémente un blue/green sûr dans la racine injectée, avec `releases/<id>` et `current` temporaire uniquement ; ne touche jamais à `/opt/...`, au vrai `current` ou à un vrai `jarvis.service`. Le déployeur doit construire/activer une release, vérifier health HTTP, WebSocket, quelques outils et Chrome CDP port 9222 via contrats mockables, surveiller une durée configurable (`DEPLOY_MONITOR_SECONDS`, fixée à 1–3 s en test) et déclencher un rollback simulé au seuil configurable. Aucun secret dans les logs.

Ajoute des modes CLI `--once` et `--dry-run` qui terminent toujours et n’installent/ne redémarrent rien. Les tests pytest ne lancent ni serveur, ni daemon, ni agy, ni réseau réel.

**Ne touche pas :** `backend/core/tools/arg_validator.py`, `backend/services/key_gate.py`, auth/JWT, `.env`, les tests existants sauf ajout strictement nécessaire, et le contrat `/ws`, `/ws/local-agent`, `/ws/device`.

**Acceptation :** service distinct par conception ; racine/runner/probes injectables ; rollback atomique simulable ; configuration par environnement ; reprise après crash ; tests pytest déterministes avec `tmp_path` et mocks ; aucune commande bloquante.

**Commandes exactes :**
```bash
timeout 120 python -m py_compile ops/deploy/jarvis_deployer.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests
```

**À faire par l’utilisateur :** installer/configurer l’unité systemd sur le VPS, créer l’utilisateur et les répertoires persistants, puis effectuer les vérifications de service avec sudo/systemd. L’agent ne doit pas le faire.

Termine par un résumé de 8 lignes maximum : fichiers, contrats, tests, limites restantes.

## Prompt 1B — Smoke CLI et unités systemd non installées

**Niveau conseillé : medium** — vérification CLI et fichiers déclaratifs, sans action système.

À partir du déployeur de 1A, ajoute `ops/scripts/jarvis-deployer.service` et toute documentation courte `docs/JARVIS_DEPLOYER.md` nécessaire. Les fichiers systemd sont écrits et vérifiés comme texte seulement : ne pas les installer, démarrer ou valider avec `systemctl`.

Lance uniquement le smoke test `--dry-run`/`--once` dans une racine temporaire via `JARVIS_DEPLOY_ROOT`, avec timeout borné, sortie déterministe et mocks. Aucun vrai symlink `current`, service, daemon, sudo ou processus Jarvis ne doit être touché.

**Commande exacte :**
```bash
timeout 120 env CI=1 JARVIS_DEPLOY_ROOT="$(mktemp -d)" python -m ops.deploy.jarvis_deployer --dry-run --once
```

**À faire par l’utilisateur :** installer et activer l’unité systemd sur le VPS, puis tester le service manuellement selon sa procédure d’exploitation.

Résumé bref : smoke test, unité écrite, hypothèses et limites.

---

## Prompt 2 — CI, CODEOWNERS et garde-fou de chemins interdits

**Niveau conseillé : medium** — CI et règles déterministes, avec peu de raisonnement métier.

Ajoute une CI GitHub Actions minimale et un contrôle anti-régression.

**À lire :** `README.md`, `AGENTS.md`, `pytest.ini`, `requirements.txt`, `backend/tests/conftest.py`, `backend/core/tools/arg_validator.py`, `backend/services/key_gate.py`, `sync_deploy.py`, `ops/deploy/sync_deploy.py`. Vérifie aussi que `.github/` est absent ou présent.

**À créer :** `.github/workflows/ci.yml`, `.github/CODEOWNERS` (si `.github/` absent, le créer), `ops/scripts/check_protected_paths.py`, `docs/BRANCH_PROTECTION.md`, tests offline du script.

La CI doit exécuter `python -m compileall`, ruff si disponible/configuré, puis pytest offline. Le script doit échouer si une PR modifie/affaiblit : `.env*`, auth/JWT, `backend/services/key_gate.py`, `backend/core/tools/arg_validator.py`, le déployeur, `.github/workflows/`, ou supprime/affaiblit un test existant. Compare la branche PR à `main`, gère les chemins absents, et signale précisément le fichier et la règle. N’invente pas de règle GitHub non disponible : documente les protections de `main` à activer manuellement.

**Ne touche pas :** code métier, tests existants, secrets, et ne désactive jamais un check pour faire passer la CI.

**Acceptation :** CI offline reproductible, permissions minimales, CODEOWNERS lisible, script détectant ajouts/suppressions sensibles et tests du script.

**Commandes exactes :**
```bash
timeout 120 python -m compileall -q backend ops
timeout 120 env CI=1 GIT_TERMINAL_PROMPT=0 python ops/scripts/check_protected_paths.py --base main --head HEAD
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests
```

Résume brièvement les fichiers créés, les règles et les commandes réellement passées.

---

## Prompt 3 — Outil `self_improve`, PR et gouvernance des crédits

**Niveau conseillé : high** — worktree, subprocess, GitHub API, kill switch et budgets forment un circuit à risque.

Implémente l’outil `self_improve` en suivant la recette d’ajout d’outil existante.


**Rappel d’exécution :** toutes les commandes doivent être bornées par `timeout` et non interactives ; agy, GitHub, subprocess, réseau et longues sessions d’agent sont mockés dans les tests. Ne jamais lancer agy en réel, `sudo/systemctl`, daemon, `pkill` ou `killall`.

**À lire :** `backend/core/tools/declarations.py`, `backend/core/tools/dispatcher.py`, `backend/core/tools/arg_validator.py`, `backend/core/tools/result.py`, `backend/services/agentic_runner.py`, `backend/services/google_antigravity.py`, `backend/services/antigravity_models.py`, `AGENTS.md`, `backend/tests/conftest.py`.

**À créer/modifier :** créer `backend/services/self_improvement_service.py`, `backend/tests/test_self_improvement_service.py`, `backend/tests/test_self_improve_tool.py`, et modifier seulement `backend/core/tools/declarations.py` et `backend/core/tools/dispatcher.py` pour déclaration/dispatch. Ajouter une doc `docs/SELF_IMPROVEMENT.md`.

Contrat : créer un git worktree temporaire et une branche `jarvis/<type>-<slug>` ; lancer `agy` headless avec prompt cadré en 4 étapes (comprendre, modifier, tester, résumer) ; exiger les tests ; boucle locale maximum 3 essais ; produire diff et résumé ; pousser puis créer une PR via API GitHub. Utiliser uniquement un token fine-grained lu depuis `.env`/environnement, jamais `git config`, logs ou prompt persistant. Ajouter revue par second modèle séparée, kill switch persistant `stop auto-amélioration`, plafond crédits jour/semaine, journal SQLite/JSON atomique, et refus des chemins protégés.

**Ne touche pas :** `.env`, auth/JWT, `key_gate.py`, `arg_validator.py`, déployeur, workflows CI, ni les tests existants. Ne merge jamais ici.

**Acceptation :** worktree nettoyé en succès/échec, subprocess borné et tuable, PR idempotente, budgets appliqués avant agy, journal reprenable, aucun push sur `main`, aucun secret exposé.

**Commandes exactes :**
```bash
timeout 120 python -m py_compile backend/services/self_improvement_service.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests/test_self_improvement_service.py backend/tests/test_self_improve_tool.py backend/tests/test_arg_validator.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests
```

Résumé final bref : signatures, états persistés, protections et tests.

---

## Prompt 4 — Validation Telegram et reprise d’état

**Niveau conseillé : high** — machine à états persistante, callbacks et merge conditionnel nécessitent des invariants stricts.

Ajoute la validation Telegram des propositions `self_improve`.

**À lire :** `backend/services/self_improvement_service.py`, `backend/services/briefing_service.py`, `backend/core/tools/dispatcher.py`, `backend/core/tools/declarations.py`, `backend/tests/conftest.py`, `README.md`.

**À créer/modifier :** créer `backend/services/self_improvement_telegram.py`, `backend/tests/test_self_improvement_telegram.py`, `docs/SELF_IMPROVEMENT_TELEGRAM.md`; modifier le service d’auto-amélioration uniquement pour appeler un adaptateur Telegram injectable.

Implémente un rapport court avec boutons inline ✅ approuver, ❌ rejeter, ✏️ demander une modification ; callbacks signés/validés, identifiant de proposition non devinable, états persistants `proposed/approved/rejected/edit_requested/merging/merged/failed`, reprise après redémarrage et déduplication. Le merge automatique est désactivé par défaut et autorisé seulement si option explicite + petit correctif + CI verte + fichiers non protégés + revue second modèle. Sinon notifier la PR à merger. Telegram doit être l’API directe du service ; aucune IP ni `chatId` dans le repo.

**Ne touche pas :** routes WebSocket, auth/JWT, `key_gate.py`, tests existants, secrets.

**Acceptation :** callback après reboot, double-clic idempotent, refus sûr, pas de merge par défaut, tests avec Bot API mockée.

**Commandes exactes :**
```bash
timeout 120 python -m py_compile backend/services/self_improvement_telegram.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests/test_self_improvement_telegram.py backend/tests/test_self_improvement_service.py
```

Termine par un résumé des états et de la politique de merge.

---

## Prompt 5 — Veille hebdomadaire L2 uniquement

**Niveau conseillé : medium** — orchestration d’agents et comparaison de données, sans modifier le moteur L3.

Ajoute une veille hebdomadaire qui utilise exclusivement la recherche L2 VPS.

**À lire :** `backend/services/deep_research_service.py`, `backend/services/agentic_runner.py`, `backend/services/search_router.py`, `backend/services/console_monitor.py`, `backend/services/briefing_service.py`, `backend/core/tools/dispatcher.py`, `backend/tests/test_l2_parallel_agents.py`, `backend/tests/test_l2_research_pipeline.py`.

**À créer/modifier :** créer `backend/services/weekly_improvement_watch.py`, `backend/tests/test_weekly_improvement_watch.py`, `docs/WEEKLY_IMPROVEMENT_WATCH.md`; ajouter le scheduler serveur documenté dans le service, sans dépendre d’un client.

Utilise `run_l2_parallel_agents` et `cross_check_l2_results`, avec agents CLI `agy` parallèles, sources et incertitudes explicites. Interdis toute invocation de `launch_deep_research` en mode Gemini Web/L3, `gemini_web_automator.py`, Chrome local ou PC. Compare chaque proposition aux déclarations/outils existants et aux erreurs agrégées de `console_monitor.py`; génère une proposition non exécutable automatiquement, persistée et envoyée via l’adaptateur Telegram de l’étape 4. Scheduler idempotent, timezone configurable, intervalle hebdomadaire, état durable.

**Ne touche pas :** pipeline L3 existant, `browser_agent`, auth, tests existants.

**Acceptation :** aucune dépendance client, L2 vérifiable par mock, propositions sourcées, déduplication, reprise et test du scheduler.

**Commandes exactes :**
```bash
timeout 120 python -m py_compile backend/services/weekly_improvement_watch.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests/test_weekly_improvement_watch.py backend/tests/test_l2_parallel_agents.py backend/tests/test_l2_research_pipeline.py
```

Résumé en quelques lignes : sources, fonctions L2 appelées, scheduler et limites.

---

## Prompt 6 — Mode 100 % arrière-plan VPS

**Niveau conseillé : high** — audit transversal de dépendances et preuve d’absence de client connecté.

Rends le circuit complet strictement autonome sur le VPS.


**Rappel d’exécution :** l’audit et les tests restent offline, avec commandes bornées (`timeout`) et mocks ; ne pas lancer de service/daemon ni utiliser `sudo`, `systemctl`, `journalctl`, `pkill` ou `killall`. Les actions VPS/systemd sont documentées pour l’utilisateur uniquement.

**À lire :** tous les nouveaux fichiers des prompts 1 à 5, `backend/services/briefing_service.py`, `backend/services/agentic_runner.py`, `backend/services/deep_research_service.py`, `backend/services/vps_chrome.py`, `backend/routers/voice.py`, `backend/routers/local_agent.py`, `backend/routers/device_voice.py`, `ops/scripts/jarvis-chrome.service`, `pytest.ini`.

**À créer/modifier :** ajouter seulement les tests d’intégration offline nécessaires et `docs/BACKGROUND_VPS_MODE.md`; modifier les nouveaux services pour supprimer toute dépendance obligatoire à Windows, mobile, PWA, ESP32, WebSocket utilisateur ou Chrome connecté.

Le scheduler doit être serveur (systemd timer ou asyncio supervisé, choisir et justifier), la file et les journaux persistants, les notifications Telegram uniquement, agy headless. Les probes de santé doivent distinguer services serveur disponibles et clients optionnels ; ne jamais attendre une présence Redis d’appareil. Prévoir kill propre, redémarrage, lock et backoff. Le déployeur reste séparé de `jarvis.service`.

**Ne touche pas :** contrats `/ws*`, firmware, `local_agent.py`, auth/JWT, et ne supprime pas leurs fonctionnalités interactives ; elles doivent seulement être optionnelles pour ce circuit.

**Acceptation :** test d’exécution sans variables de présence client, sans navigateur local, sans PC/téléphone/ESP32 ; état repris après redémarrage ; aucun `time.sleep()` ni I/O bloquante dans les tâches async.

**Commandes exactes :**
```bash
timeout 120 python -m compileall -q backend ops
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests
```

Résumé bref des dépendances rendues optionnelles et de la preuve headless.

---

## Prompt 7 — Runner de séries de prompts `prompt_batch_runner`

**Niveau conseillé : high** — exécution persistante, subprocess, crédits, notifications et reprise après crash exigent des invariants stricts.

Implémente un runner serveur qui exécute une série de prompts dans l’ordre, sans bloquer Jarvis.


**Rappel d’exécution :** les tests mockent agy, subprocess, réseau, email et Telegram ; aucun vrai run d’agent long, serveur, daemon ou téléchargement réseau. Chaque commande est bornée par `timeout`, non interactive et sans `sudo/systemctl/journalctl/pkill/killall`.

**À lire :** `backend/services/self_improvement_service.py`, `backend/services/agentic_runner.py`, `backend/services/google_antigravity.py`, `backend/services/antigravity_models.py`, `backend/core/tools/declarations.py`, `backend/core/tools/dispatcher.py`, `backend/services/briefing_service.py`, `backend/tests/conftest.py`, `ops/deploy/sync_deploy.py`, `ARCHITECTURE_COMPLETE_JARVIS.md`. Pour les notifications, réutiliser `services.email_service.send_email_async` (appelé déjà par `deep_research_service.py` et `dispatcher.py`) ; ne pas créer un second SMTP si ce service est importable.

**À créer/modifier :** créer `backend/services/prompt_batch_runner.py`, `backend/tests/test_prompt_batch_parser.py`, `backend/tests/test_prompt_batch_runner.py`, `docs/PROMPT_BATCH_RUNNER.md`, une unité `ops/scripts/jarvis-prompt-batch.service` (ou l’intégrer à un worker systemd existant sans le rendre dépendant d’un client), puis modifier seulement `declarations.py` et `dispatcher.py` pour déclarer/dispatcher `prompt_batch_runner`. Suivre la recette en 4 étapes : déclaration, validation des arguments, dispatch vers service, tests/mock.

**Entrées et parsing :** accepter un fichier `.md` envoyé comme document Telegram, uploadé par la PWA, ou fourni par chemin/URL HTTPS validé. Refuser les chemins traversant la racine autorisée, les tailles excessives et les URLs non autorisées ; télécharger en timeout borné. Extraire les sections ordonnées `## Prompt N`, leur niveau `low|medium|high`, et le corps dans un bloc de code (tolérer le format existant sans bloc si le contenu est non ambigu). Refuser les numéros dupliqués/manquants, un niveau absent/inconnu ou un prompt vide. Conserver les actions manuelles des sections `Actions manuelles` / `Ce que tu dois faire`. Mapper `low → Flash/low`, `medium → Flash/medium`, `high → Pro/high`, via les résolveurs agy existants ; interdire `--thinking`.

**Exécution et état :** lancer chaque prompt séquentiellement, en arrière-plan sur le VPS, dans le worktree/branche de `self_improve`, avec `agy` headless, timeout par prompt et timeout global. Persister atomiquement SQLite (préféré) ou JSON : batch, source, hash, index, tentative, modèle/effort, états `queued/running/verifying/succeeded/failed/stopped/completed`, logs tronqués, résultat et PR. Reprendre après restart exactement au prompt et à la tentative sauvegardés ; verrou mono-runner, idempotence et nettoyage du worktree. Après chaque run, exécuter `py_compile`, `ruff` si disponible, puis `pytest` suite complète ; injecter l’erreur et l’extrait de logs dans les 2 retries suivants, maximum 3 tentatives par prompt.

**Garde-fous :** vérifier budget avant chaque prompt et chaque retry ; respecter le kill switch exact `stop auto-amélioration`, quotas, timeouts et la liste de fichiers interdits de `self_improvement_service`. À la première erreur persistante, quota, timeout ou crash, arrêter le batch (ne pas ignorer silencieusement). Exposer les actions Telegram `reprendre`, `ignorer`, `annuler` avec callback signé et état persistant ; `reprendre` relance le prompt courant, `ignorer` passe au suivant avec trace explicite, `annuler` termine proprement.

**Succès :** ouvrir une PR idempotente après le batch, sans merge ni push sur `main`. Envoyer un email via `send_email_async(subject, body, to_email, attachments)` ; si le service est indisponible seulement, fournir un adaptateur SMTP TLS avec `SMTP_HOST/PORT/USER/PASSWORD/FROM/TO/USE_TLS` et mocks. Le message contient un résumé par prompt, modèles/essais, résultats `py_compile/ruff/pytest`, lien PR et une section exactement intitulée **Ce que tu dois faire ensuite**, agrégeant les actions manuelles trouvées et une checklist générée par agy. Envoyer aussi une notification Telegram courte. Ne mettre aucun secret dans les logs ou l’état.

**Erreur :** envoyer immédiatement email + Telegram avec numéro du prompt, état, erreur, extrait borné des logs et boutons `reprendre/ignorer/annuler`. Tester les notifications mockées, les quotas, les timeouts et le crash/restart.

**Ne touche pas :** `.env`, auth/JWT, `key_gate.py`, `arg_validator.py`, workflows CI, contrats `/ws*`, tests existants hors ajouts strictement nécessaires.

**Acceptation :** parser Telegram/PWA/path/URL testé ; série séquentielle réellement persistante ; retry 3 fois avec erreur ; vérifications après chaque prompt ; reprise après redémarrage ; kill switch/crédits/fichiers interdits ; PR et notifications email/Telegram mockées ; aucun réseau réel dans les tests.

**Commandes exactes :**
```bash
timeout 120 python -m py_compile backend/services/prompt_batch_runner.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests/test_prompt_batch_parser.py backend/tests/test_prompt_batch_runner.py
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests
```

Résumé final en 8 lignes maximum : API, états, mapping agy, protections, notifications et tests.

---

## Prompt 8 — Test E2E dry-run du circuit complet

**Niveau conseillé : high** — le test doit couvrir les frontières sans créer de PR, merge, déploiement ou message réel.

Ajoute un test E2E dry-run de bout en bout avec une petite proposition factice et aucune mutation externe, puis un mini-test du runner de séries (2 prompts : un succès et un échec forcé).


**Rappel d’exécution :** l’agent prépare seulement le test, le script et les instructions ; il ne lance aucun E2E réel, agy, réseau, GitHub, Telegram, systemd ou déploiement. Le vrai E2E sur VPS doit être lancé par l’utilisateur, avec durées et commandes bornées.

**À lire :** tous les fichiers créés aux étapes 1 à 7, notamment `backend/services/prompt_batch_runner.py`, `backend/tests/conftest.py`, `backend/core/tools/dispatcher.py`, `backend/services/agentic_runner.py`, `ops/scripts/jarvis-deployer.service` et l’unité batch.

**À créer/modifier :** créer `backend/tests/e2e/test_self_improvement_circuit.py`, éventuellement une fixture dédiée dans `backend/tests/conftest.py`, un fixture Markdown de batch, et `docs/E2E_SELF_IMPROVEMENT.md`.

Le dry-run doit simuler : proposition de veille L2, contrôle budget/kill switch, worktree et branche temporaires, prompt agy sans exécution réelle, 0 à 3 vérifications locales, revue second modèle, création PR simulée, rapport Telegram simulé avec boutons, callback ✅ puis décision de merge refusée par défaut, demande de déploiement simulée, smoke tests simulés, surveillance courte et rollback simulé. Ajouter un fichier de 2 prompts pour `prompt_batch_runner` : le premier passe et le second échoue volontairement après 3 tentatives ; vérifier l’arrêt du batch, la reprise persistée au bon index, l’alerte email/Telegram mockée et les boutons reprendre/ignorer/annuler. Vérifier toutes les transitions persistées, la reprise après redémarrage et l’idempotence. Toute URL GitHub, envoi Telegram, push, merge, systemd ou déploiement réel doit être mocké et le test doit échouer si une sortie réelle est tentée.

**Ne touche pas :** tests existants hors fixtures strictement nécessaires, secrets, dépôt GitHub réel, `main`.

**Acceptation :** une commande unique, offline, déterministe, sans agy réel, sans réseau, sans fichier `.env`, avec rapport lisible des transitions et nettoyage garanti.

**Commande exacte :**
```bash
timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 timeout 600 env CI=1 GIT_TERMINAL_PROMPT=0 python -m pytest -q backend/tests/e2e/test_self_improvement_circuit.py
```

Résumé final très court : scénario, mocks, transitions couvertes, garanties d’absence d’effets externes.

---

## Si l’agent affiche encore « User cancelled agent execution »

- Vérifier dans Antigravity le réglage d’auto-exécution du terminal et la liste blanche/allowlist des commandes ; autoriser uniquement les commandes bornées et non interactives nécessaires.
- Reprendre avec : **« reprends à l’étape X, sans relancer la commande bloquante »**, en indiquant le dernier fichier/état déjà produit.
- Contrôler qu’aucun processus de suivi (`-f`), serveur au premier plan, prompt de mot de passe ou commande systemd/sudo n’a été relancé. Si une commande dépasse 2 minutes, arrêter et signaler plutôt que patienter.

## Incohérences et limites constatées lors de la préparation

- Le document d’architecture décrit `backend/` comme une restructuration déjà complète, mais la racine contient encore des shims `App.py` et `sync_deploy.py` ; il faut respecter les chemins réels ci-dessus.
- La documentation mentionne `jarvis.service`, blue/green `releases/current` et plusieurs scripts de déploiement, mais le listing GitHub consulté ne montre que `ops/scripts/jarvis-chrome.service` et `ops/deploy/sync_deploy.py`. Les prompts demandent donc de créer le déployeur et de vérifier les hypothèses au runtime.
- Aucun dossier `.github/` n’a été trouvé au listing racine ; le prompt 2 le crée explicitement.
- Aucun fichier Telegram dédié n’apparaît dans `backend/routers/`. L’architecture mentionne des notifications Telegram dans `briefing_service.py`, sans exposer ici un module stable de callbacks ; les prompts imposent un adaptateur injectable plutôt que de supposer un chemin absent.
- L’architecture cite `config/models.json`, `docs/VPS_L3_CHECKLIST.md` et `prompts/templates/`, mais ces chemins n’ont pas été confirmés dans les listings ciblés ; l’agent doit les vérifier avant de les importer.
- Le document contient une IP et un `chatId` dans des exemples architecturaux. Ils ne doivent pas être recopiés dans le code, les prompts persistés, les workflows ou la documentation nouvelle.
