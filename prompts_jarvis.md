# Prompts séquentiels pour l’agent de codage Gemini Flash — JARVIS

## Bloc de contexte réutilisable (à préfixer à chaque prompt)

Tu travailles dans le dépôt `Pierre38610/jarvis-core`. Objectif : corriger et renforcer JARVIS sans refactorisation hors périmètre, sans modifier les secrets, les paiements ni les contrats publics non concernés. Lis uniquement les fichiers et fonctions explicitement listés dans le prompt courant, puis les tests directement nécessaires. Avant toute modification, résume les invariants existants. Après modification, exécute les tests ciblés et donne un résumé court : fichiers changés, comportement, tests, limites. Ne prétends jamais qu’une vérification a réussi si elle n’a pas été exécutée. Préserve l’asyncio : toute tâche >300 ms ne doit pas bloquer `routers/voice.py`. Les opérations payantes, achats et téléchargements nécessitant consentement restent protégés.

La source documentaire principale est `ARCHITECTURE_COMPLETE_JARVIS.md`, mais elle peut diverger du code : en cas de contradiction, le code et les tests sont la source de vérité. Les agents CLI doivent être utilisés de façon déterministe, avec timeout, logs diagnostiquables, résultat vérifiable et repli explicite. Ne journalise aucune clé/token.

---

## P1 — Fiabiliser Antigravity CLI et l’utiliser pour le raisonnement minimal

**Fichiers/fonctions à lire, uniquement :**
- `google_antigravity.py`: `find_antigravity_binary` (lignes 344–371), `verify_antigravity_cli_ready` (375–419), `resolve_cli_model_args` (421–467), `AntigravityAgent.__init__`, `cancel`, `run_cli_task_stream` (469–646), ainsi que `resolve_cognitive_tier_sync` (99–203).
- `services/agentic_runner.py`: `run_agentic`, `_build_command`, `_extract_json_payload`, `_validate_json_schema`, `_is_quota_error`.
- `services/model_routing/model_router.py`: `select_model` et `RoutingDecision`.
- `services/model_routing/fallback_handler.py`: `execute_with_fallback`.
- `core/tools/dispatcher.py`: les branches `run_agentic_task`/`run_agent_task`, les appels à `verify_antigravity_cli_ready`, et `_resolve_agy_model`/`_resolve_agy_effort`.
- `config/models.json`, `config.py` uniquement pour `MODEL_ROUTING_ENABLED` et l’autorisation de clé.
- Tests existants directement liés à Antigravity, agentic runner, dispatcher et routing.

**Changements concrets :**
1. Faire de `verify_antigravity_cli_ready()` un préflight réellement partagé par tout chemin de lancement : binaire résolu, `--version`, délai borné, cache invalidable, message d’erreur structuré. Après modification de PATH/env, invalider/retester plutôt que réutiliser une réponse périmée.
2. Dans `run_cli_task_stream`, construire une commande unique et observable : `agy -p <instruction> --dangerously-skip-permissions --output-format text` puis uniquement `--model` et, si supporté, `--effort`. Ne jamais ajouter `--thinking`. Vérifier que le modèle/effort demandé est cohérent avec `resolve_cli_model_args`.
3. Ajouter des timeouts explicites de bout en bout (préflight, démarrage, exécution) et terminer proprement le processus en cas de timeout, annulation ou quota. Retourner un `TaskResult` stable (`status`, `error_type`, résumé non vide), sans tâche zombie.
4. Séparer clairement stdout, stderr et code de sortie ; conserver une erreur utile et tronquée, sans secrets. Détecter quota/429 sans considérer toute erreur stderr comme un quota.
5. Ajouter un fallback local au processus uniquement selon la politique existante : Flash low après échec quota du modèle haut ; API gratuite/payante uniquement via `key_gate` et consentement déjà prévu. Aucun fallback payant silencieux.
6. Rendre le chemin agentique prioritaire pour les tâches à raisonnement minimal : dans le dispatch/routage, une demande classée Tier 1 qui requiert une décision ou une modification mais ne requiert pas un simple outil déterministe doit appeler Antigravity Flash low plutôt que contourner systématiquement le CLI. Les tâches purement déterministes restent des outils directs.
7. Ajouter métrique/log non secret : tentative CLI, succès/échec, raison de fallback, latence, tier final. Ne pas loguer le prompt complet si celui-ci peut contenir des données sensibles.

**Tests d’acceptation :**
- Tests unitaires de `find_antigravity_binary`, préflight : binaire absent, `--version` code non nul, timeout, succès, cache puis `force_refresh`.
- Mock de `asyncio.create_subprocess_exec` : commande exacte sans `--thinking`, cwd/env corrects, stdout/stderr drainés, code non nul, timeout et annulation sans zombie.
- Test quota : repli Flash low ; test erreur syntaxe/non-quota : pas de bascule arbitraire.
- Test de dispatch : une tâche Tier 1 agentique utilise `AntigravityAgent`; un outil déterministe n’y passe pas.
- Test de non-divulgation des clés dans logs/résultats.
- Exécuter les tests ciblés et signaler précisément tout test non exécutable.

**Sortie attendue :** résumé court des fichiers modifiés, commande CLI observée, matrice des erreurs/replis et résultats de tests. Aucun changement hors périmètre.

---

## P2 — Routeur de recherche + détection de niveau vocal (L1 par défaut) + L1

**Fichiers/fonctions à lire, uniquement :**
- `ARCHITECTURE_COMPLETE_JARVIS.md`: sections 5.3–5.6, 6.2, 7.3, 9.2.1, et lignes/références autour de `search_web`, `launch_deep_research`, `browser_task`, `download_file`, `open_user_browser`.
- `services/model_routing/model_router.py`: `select_model`, `RoutingDecision`, règles de tâche et overrides.
- `google_antigravity.py`: `resolve_cognitive_tier_sync`, `resolve_cognitive_tier`, `COGNITIVE_TIER_1`, `AntigravityAgent`.
- `services/live_mode_policy.py`: `decide`, `get_policy`, `_detect_agentic_need`.
- `routers/voice.py`: réception de transcription/tool call, construction du prompt système et dispatch ; ne lire que les fonctions de décision et d’appel d’outils.
- `core/tools/declarations.py`: déclarations `search_web`, `launch_deep_research`, `browser_task`, `download_file`, `open_user_browser`.
- `core/tools/dispatcher.py`: branches de ces outils et `_infer_tool_tier_and_cost`.
- `services/browser_service.py`, `services/deep_research_service.py`: points d’entrée uniquement.
- Tests de routing, voice policy et outils de recherche existants.

**Changements concrets :**
1. Introduire/compléter un routeur de recherche déterministe : `search_web` pour une recherche courte/factuelle ; `browser_task` pour une navigation structurée ; `launch_deep_research` pour une recherche multi-source longue. Le routeur doit retourner outil, tier, effort, timeout et raison.
2. Définir la détection vocale explicite L1/L2/L3 à partir de l’intention transcrite : L1 par défaut en cas d’ambiguïté ; mots “rapide/simple”, action locale courte ou question factuelle → L1 ; comparaison multi-critères/planification → L2 ; “recherche approfondie/rapport/sources exhaustives” → L3. Les overrides utilisateur explicites priment.
3. L1 doit être économique : Gemini Flash low/Antigravity CLI si la tâche est agentique minimale, ou outil direct si elle est déterministe. Timeout court, pas de Pro, pas de navigateur Deep Research.
4. Injecter dans le prompt système de Live le niveau choisi, la raison et les outils autorisés, sans divulguer les politiques internes sensibles. Le niveau doit être transmis au dispatcher et audité.
5. Ne jamais lancer deux chemins de recherche pour la même intention ; le fallback doit être explicite et idempotent.
6. Conserver les confirmations obligatoires avant `download_file` et les vérifications post-exécution.

**Tests d’acceptation :**
- Table de cas vocaux : ambigu → L1 ; factuel → `search_web`/L1 ; navigation → `browser_task`/L2 ; recherche exhaustive → `launch_deep_research`/L3.
- Overrides “fais vite” et “analyse en profondeur” prioritaires.
- Vérifier propagation outil/tier/effort/timeout jusqu’au dispatcher et au log.
- Vérifier absence de double lancement et respect du consentement téléchargement.
- Tests async : aucun appel long synchrone dans la boucle voice.
- Tests de non-régression du contrat des outils et tests ciblés exécutés.

**Sortie attendue :** tableau court intention → outil → niveau → timeout, fichiers modifiés et tests. Pas de refactor général du moteur vocal.

---

## P3 — L2 : agents CLI parallèles, contre-vérification, synthèse et boucle de vérification bornée

**Fichiers/fonctions à lire, uniquement :**
- `services/deep_research_service.py`: fonctions MAP/REDUCE/quality gate et orchestration des agents.
- `services/agentic_runner.py`: `run_agentic` et validation JSON.
- `google_antigravity.py`: `AntigravityAgent.run_cli_task_stream`, `verify_antigravity_cli_ready`, `resolve_cli_model_args`.
- `services/model_routing/model_router.py`, `fallback_handler.py`.
- `core/tools/dispatcher.py`: `launch_deep_research`, `run_agentic_task`, `browser_task` et l’enveloppe de vérification.
- `core/tools/verifier.py` et `prompts/antigravity_prompts.py` si présents.
- Tests `tests/test_deep_research.py`, agentic runner et tests de quota/timeout.

**Changements concrets :**
1. Pour L2 seulement, lancer un nombre borné d’agents CLI Flash/Pro selon le besoin (maximum configurable, défaut 3) avec `asyncio.gather` et `asyncio.wait_for`. Chaque agent reçoit une mission spécialisée et un format JSON strict : faits, sources, hypothèses, incertitudes, conclusion.
2. Isoler chaque workspace/task-id et empêcher les écritures concurrentes dans le même artefact. Les agents ne doivent pas partager de secrets ni modifier des fichiers hors workspace.
3. Ajouter une phase de cross-check : comparer les résultats, repérer contradictions, affirmations sans source et sorties invalides. Ne pas traiter un JSON invalide comme succès.
4. Ajouter une synthèse par agent désigné ou étape REDUCE, puis une vérification finale indépendante. Définir `max_iterations` (défaut 2), timeout par agent et timeout global ; arrêter immédiatement si le budget est dépassé.
5. En cas d’échec partiel, retourner un résultat explicitement partiel avec les agents réussis/échoués, plutôt qu’un succès maquillé. Le quality gate doit pouvoir échouer.
6. Conserver la cascade quota-aware de P1 ; un quota ne doit pas relancer indéfiniment le même modèle.
7. Journaliser uniquement métadonnées : nombre d’agents, latence, itérations, statut, raison de repli.

**Tests d’acceptation :**
- Mock de trois agents : exécution réellement concurrente, résultat agrégé, ordre déterministe de synthèse.
- Un agent timeout/échoue : les autres sont récupérés, résultat partiel et erreur structurée.
- JSON invalide/contradiction : cross-check échoue puis au plus `max_iterations` relances.
- Vérifier timeout global et annulation de toutes les tâches enfants.
- Vérifier workspace isolé et absence d’écriture concurrente.
- Test quota/cooldown et quality gate négatif sans faux succès.
- Exécuter `tests/test_deep_research.py` et tests ciblés ; rapporter les absences.

**Sortie attendue :** schéma de résultat, bornes configurées, nombre réel d’agents/itérations dans les tests et résumé court.

---

## P4 — L3 : Gemini Deep Research via le navigateur du PC

**Fichiers/fonctions à lire, uniquement :**
- `local_browser_actions.py`: `BrowserBridge._ensure_browser`, `_get_page`, `browser_open_task`, `browser_snapshot`, `browser_act`, `browser_screenshot`, `browser_focus`.
- `jarvis_local_agent.py`: boucle WebSocket/RPC `handle_rpc_message` et handlers `browser_*`, `gemini_deep_research`, `open_browser`, `fetch_file`.
- `services/browser_agent/loop.py`: `BrowserTask`, `run_browser_task`/`run_browser_agent_task`, polling et statut.
- `services/deep_research_service.py`: `launch_deep_research_gemini_web`.
- `core/tools/dispatcher.py`: branche `launch_deep_research` et `download_file`/`open_user_browser`.
- `prompts/recipes/gemini_deep_research.md` si présent dans le dépôt ; si absent, le signaler et ne pas inventer son contenu.
- `services/gemini_web_automator.py` si présent.
- Architecture : sections 7.3, 9.3, 10.3, lignes 1057–1075 et 1167–1171.
- Tests `tests/test_gemini_web_automator.py`, deep research et local-agent/CDP.

**Changements concrets :**
1. Implémenter le flux L3 réel via Chrome existant en CDP 9222 : ouvrir/attacher l’onglet Gemini, vérifier connexion/session, sélectionner “Deep Research”, saisir le sujet, lancer, puis confirmer le plan proposé avant de poursuivre.
2. Utiliser des sélecteurs robustes par rôle/texte accessible (`get_by_role`, `get_by_text`, labels) avec fallback limité ; ne pas dépendre exclusivement de classes CSS ou d’IDs générés. Après chaque étape, prendre un snapshot DOM/texte utile.
3. Poller l’état jusqu’à terminaison avec intervalle et timeout globaux configurables ; ne pas bloquer la boucle voice. Gérer “plan à confirmer”, “génération en cours”, “terminé”, “connexion requise”, “erreur”.
4. À la fin, extraire le rapport complet en Markdown, utiliser explicitement l’option “create web page” si elle est disponible et requise par le flux, télécharger le fichier, puis demander au PC de l’ouvrir et le sauvegarder dans un dossier persistant configuré (`downloads/` ou `artifacts/`, jamais temporaire).
5. Vérifier après téléchargement : chemin sûr, existence, taille >0, extension attendue et accusé réel du local agent pour l’ouverture. Respecter l’accord préalable obligatoire avant tout rapatriement de fichier.
6. Sur chaque échec d’interaction, capturer une ou plusieurs screenshots JPEG et inclure leur chemin/identifiant dans le résultat ; ne jamais prétendre que la recherche est terminée si l’extraction ou la sauvegarde échoue.
7. Rendre le flux idempotent autant que possible avec `task_id`, statuts et nettoyage de référence sans fermer le Chrome utilisateur.

**Tests d’acceptation :**
- Tests Playwright mockés : sélection Deep Research, saisie, confirmation du plan, polling terminé et extraction.
- Fallback de sélecteur texte/role quand le sélecteur principal change.
- Timeout/connexion absente/plan non confirmé : statut explicite, screenshot capturée, aucune fausse réussite.
- Test “create web page”, téléchargement dans dossier persistant, validation taille >0 et ouverture locale accusée.
- Test consentement avant téléchargement et propagation de `task_id`.
- Test que le polling est une tâche asyncio non bloquante.
- Exécuter les tests Gemini/local browser disponibles ; signaler les tests non vérifiables sans Chrome réel.

**Sortie attendue :** diagramme textuel des états L3, sélecteurs utilisés, paramètres de timeout, preuves de tests mockés et limites du test sans poste Windows/Chrome réel.

---

## P5 — Tests end-to-end et verrouillage de non-régression

**Fichiers/fonctions à lire, uniquement :**
- Les fichiers modifiés par P1–P4.
- `core/tools/declarations.py`, `core/tools/dispatcher.py`, `core/tools/verifier.py`.
- `routers/voice.py`, `services/live_mode_policy.py`.
- `jarvis_local_agent.py`, `local_browser_actions.py`.
- `tests/` : tests Antigravity, routing, voice policy, deep research, Gemini web automator, local agent/CDP ; ne pas explorer le reste sans échec justifié.
- `pytest.ini` et la configuration de test nécessaire.

**Changements concrets :**
1. Ajouter des tests contractuels de bout en bout avec mocks déterministes pour : voix → détection L1/L2/L3 → outil → dispatcher → agent/ navigateur → vérification → résultat final.
2. Couvrir les scénarios : L1 factuel ; L1 agentique minimal via Antigravity ; L2 agents parallèles avec contradiction ; L3 plan confirmé puis Deep Research terminée ; navigateur indisponible ; CLI indisponible ; quota ; timeout ; annulation ; téléchargement refusé ; fichier vide ; ouverture PC non confirmée.
3. Vérifier les invariants sécurité : aucune clé dans logs, aucun paiement automatique, consentement téléchargement, workspace confiné, aucun succès sans preuve post-exécution.
4. Vérifier concurrence et nettoyage : aucune tâche asyncio orpheline, aucun agent CLI zombie, aucun onglet fermé par erreur, aucune double exécution d’un même `task_id`.
5. Ajouter éventuellement un test smoke séparé marqué `integration` pour Chrome CDP/agy réel ; il doit être désactivé par défaut et ne jamais faire échouer la suite offline.
6. Exécuter d’abord les tests ciblés puis toute la suite raisonnablement disponible ; rapporter les commandes, nombres passés/échoués/ignorés et les raisons.
7. Ne corriger que les régressions démontrées par ces tests. Pas de refactor ou changement de style non nécessaire.

**Tests d’acceptation :**
- Suite offline verte avec mocks et sans secrets/Chrome/agy réels.
- Scénarios d’échec produisent des statuts structurés et aucun faux succès.
- Test d’intégration réel est clairement marqué et son absence d’environnement est rapportée, non masquée.
- Vérification finale des diff, imports, lint/type checks disponibles et absence de fichiers temporaires livrés.

**Sortie attendue :** rapport final très court : commandes lancées, résultats, fichiers modifiés, scénarios non testables et éventuelles corrections restantes. Ne déclarer “terminé” que si les critères réellement exécutés le permettent.

---

## Limites de vérification connues au moment de la rédaction

Fichiers effectivement lus dans `/mnt/user-data/uploads/` : `ARCHITECTURE_COMPLETE_JARVIS.md`, `google_antigravity.py`, `local_browser_actions.py`, `model_router.py` (et doublons suffixés `(1)` présents mais non nécessaires). Les tentatives GitHub en lecture seule ont trouvé et téléchargé comme pièces jointes `jarvis_local_agent.py`, le shim `prompt_builder.py`, `services/model_routing/model_router.py`, `services/model_routing/prompt_builder.py` et `services/browser_agent/loop.py`, mais ces pièces jointes n’ont pas été déposées dans `/mnt/user-data/uploads/` dans cet environnement ; leur contenu n’a donc pas été lu ni utilisé comme preuve directe. `prompts/recipes/gemini_deep_research.md` n’a pas été trouvé dans le chemin demandé. Les références à ces fichiers dans P2–P5 sont donc des instructions de lecture pour l’agent de codage, pas des faits vérifiés ici.
