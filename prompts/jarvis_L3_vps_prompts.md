# Prompts Gemini Flash — Deep Research L3 autonome sur VPS

## Mode d’emploi

Exécuter **P1 → P8 dans cet ordre**, dans le dépôt `jarvis`. **Un prompt = une conversation Antigravity IDE**. Régler le niveau indiqué avant chaque prompt. Après chaque prompt, lancer les tests demandés et corriger uniquement ce qui est nécessaire. Ne pas toucher au reste du dépôt, ne pas faire de grand refactor et conserver les interfaces existantes autant que possible.

---

## P1 — Dépendances minimales

**Niveau de raisonnement : LOW**

**Objectif :** ajouter les dépendances manquantes nécessaires au flux L3.

**Fichiers à lire d’abord :** `requirements.txt`, `services/gemini_web_automator.py`, les tests de dépendances existants.

**Tâches :**
1. Ajouter `beautifulsoup4` et `PyJWT` dans `requirements.txt`, sans doublon et en respectant le format/les versions déjà utilisés.
2. Vérifier que les imports correspondants fonctionnent dans l’environnement du projet.
3. Ne modifier aucun code métier.

**Contraintes :** petit diff ; aucune dépendance supplémentaire ; ne pas réorganiser le fichier inutilement.

**Tests à écrire/lancer :** lancer les tests existants ciblant les dépendances, puis `pytest -q` si le coût est acceptable ; vérifier les imports `bs4` et `jwt`.

**Critère d’acceptation :** `requirements.txt` contient exactement les deux dépendances requises, les imports passent et les tests concernés passent.

---

## P2 — Erreurs L3 détaillées et propagées

**Niveau de raisonnement : HIGH**

**Objectif :** remplacer l’erreur générique L3 par une erreur exploitable par l’utilisateur et par Jarvis.

**Fichiers à lire d’abord :** `services/browser_agent/loop.py`, `services/gemini_web_automator.py`, `core/tools/dispatcher.py` (zones BrowserTask et erreurs L3), tests associés.

**Tâches :**
1. Définir une structure d’erreur stable contenant au minimum `étape`, `exception`, `traceback_court`, et, si disponible, `capture_ecran`/son chemin.
2. Capturer et propager cette structure depuis `browser_open_task`/le browser task et l’automator jusqu’au dispatcher, sans perdre l’exception originale.
3. Stocker la dernière erreur L3 dans un emplacement/mécanisme déjà approprié de Jarvis, avec accès sûr pour diagnostic (pas de secret dans les logs).
4. Remplacer « Erreur interne lors de la recherche » par un message utilisateur utile : étape échouée, cause courte et indication du repli en cours ; conserver les détails complets dans les logs et les données de résultat.
5. Préserver les statuts/interfaces de succès et le repli Map-Reduce.

**Contraintes :** petits diffs ; pas de refactor global ; traceback tronqué et borné ; captures optionnelles, non bloquantes ; ne jamais exposer tokens, cookies ou mots de passe.

**Tests à écrire/lancer :** tests unitaires d’une exception à chaque étape clé, vérification de propagation jusqu’au dispatcher, stockage de la dernière erreur, message sans secret et compatibilité avec le chemin de succès ; lancer `pytest -q` sur les tests concernés.

**Critère d’acceptation :** une panne simulée expose l’étape et la cause courte à l’utilisateur, le détail structuré est accessible à Jarvis, les logs contiennent `[DeepResearch]`/`[EXCEPTION RECHERCHE L3]` avec contexte, et aucun test existant ne régressse.

---

## P3 — Chrome + CDP persistant sur le VPS

**Niveau de raisonnement : HIGH**

**Objectif :** installer et maintenir sur le VPS un Chrome headless pilotable en CDP, sans PC local.

**Fichiers à lire d’abord :** `services/browser_service.py`, `services/gemini_web_automator.py`, `requirements.txt`, `.env.example`/configuration, `docker-compose.yml`, `scripts/`.

**Tâches :**
1. Créer `scripts/setup_vps_chrome.sh`, idempotent, avec détection de l’OS/paquets, installation de Chromium/Chrome et dépendances Xvfb nécessaires, puis `playwright install chromium`.
2. Créer une unité systemd (ou une configuration supervisord cohérente avec le dépôt) lançant Chrome avec `--headless`, `--remote-debugging-port=9222` et `--user-data-dir` persistant hors dépôt ; activer redémarrage automatique et logs utiles.
3. Ajouter les variables documentées, notamment `JARVIS_VPS_CHROME_PROFILE`, URL/port CDP, binaire Chrome et options headless, avec valeurs sûres et sans secrets committés.
4. Ne pas ajouter le profil au dépôt ni à Docker ; respecter l’exclusion de `.jarvis_chrome_profile`.
5. Rendre le script relançable et échouer avec un diagnostic clair si les privilèges ou paquets manquent.

**Contraintes :** ne pas remplacer l’orchestration existante ; pas de credentials dans le script ; pas de dépendance inutile ; préserver le fonctionnement des services Docker existants (Redis/PostgreSQL/Qdrant/n8n).

**Tests à écrire/lancer :** lint/shellcheck si disponible ; test non destructif d’idempotence et de génération de configuration ; vérification syntaxique systemd ; tests Python concernés.

**Critère d’acceptation :** une exécution sur VPS neuf prépare Chromium, Xvfb et Playwright ; le service démarre/re-démarre Chrome sur CDP 9222 avec un profil persistant hors dépôt ; une seconde exécution ne casse rien.

---

## P4 — Gestionnaire Python du Chrome VPS

**Niveau de raisonnement : HIGH**

**Objectif :** fournir une API Python fiable pour s’assurer que Chrome VPS est vivant avant une recherche L3.

**Fichiers à lire d’abord :** `services/gemini_web_automator.py` (connexion CDP), `services/browser_service.py`, configuration/env, conventions de tests.

**Tâches :**
1. Créer `services/vps_chrome.py` avec `ensure_chrome_running()` et un health check CDP explicite (URL/port configurables).
2. Vérifier la disponibilité avant connexion ; si nécessaire relancer le service/processus selon le mécanisme P3, avec timeout, backoff borné et logs structurés.
3. Retourner un résultat/une exception compatible avec la structure d’erreur P2 ; ne jamais bloquer indéfiniment.
4. Brancher uniquement l’appel minimal nécessaire à l’automator, sans changer encore l’ordre complet des replis de P6.

**Contraintes :** fonctions testables, injection des commandes/HTTP si utile ; pas de `killall` large ; pas de boucle infinie ; ne pas lancer Chrome localement par surprise.

**Tests à écrire/lancer :** tests mockés du CDP sain, CDP indisponible, relance réussie, timeout et relance échouée ; vérifier absence de lancement réel en test ; lancer les tests ciblés.

**Critère d’acceptation :** `ensure_chrome_running()` distingue sain/relançable/échec, respecte les timeouts et permet à l’automator de se connecter au CDP VPS avec des tests entièrement mockés.

---

## P5 — Documentation et session Google persistante

**Niveau de raisonnement : MEDIUM**

**Objectif :** documenter l’initialisation manuelle unique de la session Google/Gemini, sans automatiser la connexion.

**Fichiers à lire d’abord :** `services/gemini_web_automator.py`, `services/vps_chrome.py`, `.env.example`, documentation existante, `data/gemini_ui_map.json`.

**Tâches :**
1. Documenter une procédure VPS pour ouvrir Chrome via noVNC/VNC, ou copier avec précaution un profil depuis le PC vers `JARVIS_VPS_CHROME_PROFILE` ; préciser permissions, sauvegarde et arrêt du service avant copie.
2. Ajouter un script/commande de vérification « session Gemini active » qui détecte une page de login/`accounts.google.com` et retourne un code d’échec clair.
3. Ne pas automatiser la saisie de mot de passe, MFA ou récupération de session ; ne jamais afficher de cookie/token.
4. Documenter que `data/gemini_ui_map.json` peut être créé vide (`{"actions": {}}`) si absent, sans bloquer le flux.

**Contraintes :** documentation concise et reproductible ; aucune nouvelle donnée sensible dans Git ; ne pas modifier les sélecteurs UI sans nécessité.

**Tests à écrire/lancer :** tests mockés de détection session active et page login ; vérification du script en mode succès/échec ; lancer les tests ciblés.

**Critère d’acceptation :** un opérateur peut établir la session une seule fois, vérifier son état sans login automatisé, et un profil absent/une carte UI absente ne provoque pas de panne silencieuse.

---

## P6 — Routage L3 autonome VPS

**Niveau de raisonnement : HIGH**

**Objectif :** faire de Chrome VPS le premier chemin L3, sans dépendre du PC ni de `start_local_agent.bat`.

**Fichiers à lire d’abord :** `services/browser_agent/loop.py` (envoi `browser_open_task`, alias `run_browser_agent_task`), `services/gemini_web_automator.py`, `services/vps_chrome.py`, `core/tools/dispatcher.py`, tests L3.

**Tâches :**
1. Router `gemini_deep_research` vers l’automator connecté au CDP VPS via `vps_chrome.ensure_chrome_running()`, sans passer par `local_agent_service` en premier.
2. Conserver l’alias `run_browser_agent_task = run_browser_task` et les contrats existants.
3. Implémenter l’ordre strict des replis : **Chrome VPS → agent local PC si disponible → Map-Reduce Antigravity**.
4. Détecter proprement PC hors ligne ; journaliser chaque échec avec l’erreur structurée P2, sans masquer la cause réelle ; ne pas retarder inutilement le repli.
5. Garantir que rapport, sources, artefacts et `envoyer_email` restent compatibles avec le dispatcher.

**Contraintes :** petits diffs ; pas de duplication de l’automator ; pas de dépendance au `.bat` ; pas de changement du comportement des tâches browser simples non L3.

**Tests à écrire/lancer :** tests de routage VPS réussi ; VPS indisponible puis agent local ; VPS et local indisponibles puis Map-Reduce ; PC éteint ; erreur détaillée conservée ; test de compatibilité de l’alias ; lancer `pytest -q` ciblé.

**Critère d’acceptation :** L3 réussit avec le PC éteint si Chrome VPS et session Gemini sont disponibles ; chaque repli est appelé dans l’ordre exact et toutes les erreurs restent diagnostiquables.

---

## P7 — Livraison du rapport

**Niveau de raisonnement : MEDIUM**

**Objectif :** livrer le rapport sur le PC quand il est connecté, sinon par e-mail.

**Fichiers à lire d’abord :** `core/tools/dispatcher.py` (retour L3 et envoi mail), `services/gemini_web_automator.py`, fonctions websocket/UI et tests de notification.

**Tâches :**
1. Définir la détection fiable « PC connecté » via le mécanisme existant ; éviter une dépendance bloquante au PC.
2. Si connecté, afficher/retourner le rapport dans la page web/session Jarvis existante ; sinon envoyer le rapport final par l’automator/email déjà supporté.
3. Conserver sources, confiance, artefacts, statut et détail d’erreur ; gérer explicitement l’échec d’envoi mail et le journaliser.
4. Éviter les doublons lors du passage du mode affichage au mode e-mail.

**Contraintes :** réutiliser les fonctions existantes (`send_email_async` notamment) ; pas de nouvelle infrastructure ; ne pas exfiltrer de secrets.

**Tests à écrire/lancer :** PC connecté, PC absent, e-mail activé, échec e-mail, résultat avec artefacts et résultat en erreur ; lancer les tests ciblés.

**Critère d’acceptation :** le rapport apparaît sur la page si le PC est disponible, sinon arrive par e-mail, avec un résultat déterministe et des logs utiles en cas d’échec.

---

## P8 — Intégration finale et checklist VPS

**Niveau de raisonnement : HIGH**

**Objectif :** valider le parcours complet L3 et fournir une procédure manuelle exploitable.

**Fichiers à lire d’abord :** changements P1–P7, tests L3/browser/dispatcher, `scripts/setup_vps_chrome.sh`, unité systemd/supervisord, documentation et `.env.example`.

**Tâches :**
1. Ajouter un test d’intégration entièrement mocké : requête L3 → health check Chrome VPS → automator/CDP → rapport → affichage ou e-mail, avec simulation des replis.
2. Ajouter une checklist manuelle VPS avec commandes précises : installation, configuration `.env`, démarrage/activation du service, vérification `curl` CDP 9222, vérification session Gemini, lancement d’une recherche et consultation des logs.
3. Tester explicitement : PC éteint, session expirée, Chrome redémarré, échec VPS, repli local, repli Map-Reduce, e-mail et affichage PC.
4. Lancer le test d’intégration puis `pytest -q` complet ; corriger seulement les régressions introduites par P1–P7.
5. Vérifier `git diff`, absence de secrets/profil Google dans le dépôt, syntaxe Python/shell et documentation des variables.

**Contraintes :** ne pas ignorer un test en échec ; pas de test réel dépendant d’un compte Google dans CI ; mocks déterministes ; aucune modification hors périmètre.

**Tests à écrire/lancer :** test d’intégration mocké + `pytest -q` complet ; vérifications shell/configuration et inspection finale du diff.

**Critère d’acceptation :** le parcours mocké est vert, `pytest -q` complet est vert, la checklist permet une validation réelle sur le VPS sans PC, et le diff ne contient ni secret ni profil utilisateur.
