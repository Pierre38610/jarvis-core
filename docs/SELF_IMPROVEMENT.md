# Service d'Auto-Amélioration Autonome J.A.R.V.I.S. (`self_improve`)

## 1. Vision et Objectifs
Le service `self_improve` confère à J.A.R.V.I.S. la capacité d'adapter, de recoder, d'optimiser et de tester lui-même son propre code source sur le VPS Oracle Cloud.
S'appuyant sur l'armée d'agents autonomes Antigravity CLI (`agy`), ce mécanisme opère sous confinement architectural strict, isolation git temporaire, préservation des ressources CPU du moteur vocal Gemini Live, et gouvernance inviolable (kill switch et plafonds de quotas).

---

## 2. Architecture & Confinement par Sous-Dossiers

Le dépôt est découpé en domaines fonctionnels confinés disposant de leurs propres règles d'architecture (`ARCHITECTURE.md`) et de leurs suites de tests unitaires ciblées :

| Sous-dossier logique | Répertoires autorisés (`allowed_subdirs`) | Contrat d'architecture | Tests unitaires ciblés (`targeted_test_files`) |
| :--- | :--- | :--- | :--- |
| `backend/core/tools` | `backend/core/tools`, `backend/core` | `backend/ARCHITECTURE.md` | `test_agentic_tools.py`, `test_antigravity_first_routing.py`, `test_tool_false_failures.py` |
| `backend/services/model_routing` | `backend/services/model_routing` | `backend/ARCHITECTURE.md` | `test_model_routing.py`, `test_paid_key_gate.py` |
| `backend/services/browser_agent` | `backend/services/browser_agent`, `backend/services` | `backend/ARCHITECTURE.md` | `test_antigravity_task_engine.py`, `test_browser_loop.py`, `test_antigravity_browser_mission.py` |
| `backend/services` | `backend/services` | `backend/ARCHITECTURE.md` | `test_antigravity_task_engine.py` |
| `backend/routers` | `backend/routers` | `backend/ARCHITECTURE.md` | `test_voice_multisession.py`, `test_mobile_bridge.py` |
| `frontend/static` | `frontend/static`, `static` | `frontend/ARCHITECTURE.md` | `test_version_sync.py` |
| `ops/deploy` | `ops/deploy`, `ops/scripts` | `ops/ARCHITECTURE.md` | `test_jarvis_deployer.py`, `test_check_protected_paths.py` |
| `ops/windows` | `ops/windows` | `ops/ARCHITECTURE.md` | `test_jarvis_deployer.py` |
| `firmware/esp32` | `firmware/esp32` | `firmware/ARCHITECTURE.md` | `test_device_voice_buffer.py`, `test_device_voice_followup.py` |
| `docs` | `docs` | `docs/ARCHITECTURE.md` | Documentation Markdown |

### Résolution du Périmètre (`resolve_subfolder_scope`)
- **Indice explicite (`target_hint`)** : Si l'utilisateur ou l'outil spécifie un sous-dossier cible (ex: `backend/services/model_routing`), le confinement s'applique immédiatement à ce sous-ensemble.
- **Détection heuristique** : En l'absence d'indice, les mots-clés de l'objectif (`goal`) sont scorés pour déduire le sous-dossier pertinent (ex: mots-clés liés au navigateur -> `backend/services/browser_agent`).
- **Règle de confinement strict** : L'agent a l'interdiction de modifier des fichiers en dehors des répertoires autorisés.

---

## 3. Sélection Dynamique des Modèles Antigravity (`resolve_live_agy_model`)

Le service interroge le registre dynamique des modèles (`model_registry.get_registry().refresh_if_needed()`) et arbitre le meilleur couple `(modèle, effort)` :

1. **Complexité `low` (Rapidité & Économie)** :
   - Modèle Flash actif le plus rapide (ex: `gemini-3.7-flash` ou `gemini-3.8-flash`).
   - Effort de réflexion : `low`.
2. **Complexité `medium` (Raisonnement Tactique Standard - Défaut)** :
   - Modèle Flash actif le plus récent (ex: `gemini-3.8-flash`).
   - Effort de réflexion : `medium`.
3. **Complexité `high` (Haute Ingénierie & Architecture)** :
   - Modèle Pro ou Claude Sonnet actif (ex: `gemini-3.1-pro` ou `claude-3-7-sonnet`).
   - Effort de réflexion : `high` (ou `None` pour Claude sans support d'effort).
4. **Interdiction formelle** : Le flag `--thinking` est rigoureusement banni de toutes les commandes générées pour Antigravity CLI.

---

## 4. Isolation d'Exécution & Priorité CPU

1. **Git Worktree Temporaire** :
   - Chaque session s'exécute dans un worktree dédié branché sur `jarvis/<type>-<slug>-<id>`.
   - L'espace de travail principal n'est jamais pollué en cours de développement.
   - En bloc `finally`, `cleanup_isolated_worktree()` garantit le démontage forcé et la suppression du répertoire temporaire.
2. **Priorité CPU Linux (`nice -n 10`)** :
   - Sous Linux, Antigravity CLI est systématiquement préfixé par `nice -n 10` pour garantir que le moteur vocal temps réel Gemini Live Audio conserve une priorité ordonnanceur absolue.
3. **Sémaphore Mono-Agent** :
   - Un sémaphore `_SELF_IMPROVE_LOCK` borne la concurrence à 1 agent d'auto-amélioration simultané (`MAX_CONCURRENT_SELF_IMPROVE = 1`).

---

## 5. Télémétrie et Streaming des Logs (`ACTIVE_AGY_LOGS`)

- Enregistrement immédiat dans `core.shared_state.register_agy_task`.
- Redirection ligne par ligne des flux `stdout` et `stderr` vers `append_agy_log(task_id, line)`.
- Censure préalable des secrets et tokens via `_sanitize_secrets()`.
- Déduction automatique de l'étape courante (`current_step`).
- Observabilité en direct via `get_active_task_status(include_logs=True)` et les événements WebSocket du HUD.

---

## 6. Boucle d'Essais et Portes de Validation Locales

L'agent dispose d'une boucle locale de **3 essais maximum** (`MAX_ITERATIONS = 3`) :
1. **Compilation Syntaxique (`py_compile`)** : Vérification immédiate de chaque fichier Python modifié.
2. **Anti-Régression & Protection des Chemins Critiques (`check_protected_paths.py`)** :
   - Interdiction absolue de modifier ou supprimer `.env*`, `auth_service.py`, `auth.py`, `key_gate.py`, `arg_validator.py`, `jarvis_deployer.py` et les workflows GitHub Actions `.github/workflows/`.
   - Interdiction formelle de supprimer des tests existants sous `backend/tests/`.
3. **Exécution des Tests Unitaires Ciblés (`pytest <targeted_test_files>`)** :
   - Exécution ultra-rapide des seuls tests pertinents pour le domaine concerné.
   - Si un échec survient, la trace d'erreur est injectée en rétroaction dans le prompt de l'itération suivante.

---

## 7. Revue du Diff et Création de Pull Request GitHub

- **Revue automatique du diff (`review_diff`)** : Examen léger du diff git (taille raisonnable, absence de motifs suspects comme `eval`, `rm -rf`, ou clés en clair).
- **Création de PR GitHub** : Si validé et si `creer_pr=True`, commit sur la branche isolée et appel à l'API REST GitHub (`/repos/{owner}/{repo}/pulls`) avec le token fine-grained.

---

## 8. Gouvernance & Kill Switch

1. **Kill Switch Persistant** :
   - Activation par consigne vocale : `"stop auto-amélioration"` ou `"arrête l'auto-amélioration"`.
   - Enregistrement d'un drapeau persistant sur le disque (`data/self_improve_kill_switch.flag`).
   - Bloque immédiatement tout nouveau run avec statut `blocked_kill_switch`.
2. **Plafonds de Quotas** :
   - Maximum 10 runs par 24h (`MAX_RUNS_PER_DAY = 10`).
   - Maximum 30 runs par 7 jours (`MAX_RUNS_PER_WEEK = 30`).
   - Journalisation atomique des sessions dans `data/self_improvement_journal.json`.

---

## 9. Déclaration et Utilisation de l'Outil `self_improve`

L'outil est déclaré dans `core/tools/declarations.py` et routé dans `core/tools/dispatcher.py` :
- `objectif` (`str`, requis) : Mission de recodage, refactorisation ou correction.
- `sous_dossier_cible` (`str`, optionnel) : Ex: `"backend/services/browser_agent"`.
- `complexite` (`str`, optionnel) : `"low"`, `"medium"` (défaut), `"high"`.
- `creer_pr` (`bool`, optionnel, défaut `True`) : Ouvrir une PR GitHub après succès.
