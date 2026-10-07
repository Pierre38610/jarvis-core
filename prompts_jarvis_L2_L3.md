# Prompts Antigravity IDE — Jarvis L2 / L3

## Cause racine (diagnostic déjà effectué)
- L3 est actuellement décrit comme une orchestration multi-agents CLI Antigravity sur VPS.
- `services/search_router.py` route pourtant L3 vers `launch_deep_research`, et L2 vers `browser_task`.
- `core/tools/dispatcher.py` contient le pipeline CLI L3 en trois phases (prospector, analyst, synthesis) et ses redirections automatiques.
- Le moteur web Gemini existe déjà via `services/gemini_web_automator.py` et la tâche `gemini_deep_research` du browser agent.
- L2 doit devenir le niveau multi-agent CLI ; les tests et les déclarations doivent être alignés sur cette séparation.

> **Règle commune à tous les prompts :** ne pas lire tout le dépôt. Ouvrir uniquement les chemins explicitement listés dans le prompt, ainsi que les imports/tests strictement nécessaires pour comprendre les signatures. Ne modifier que les fichiers listés. Ne pas ajouter de dépendance non demandée.

---

## 1) L3 → Gemini Deep Research web **[niveau recommandé : high]**

**Prompt à coller dans Gemini Flash / Antigravity IDE**

Dans le repo `Pierre38610/jarvis-core`, corrige le routage afin que **L3 utilise Gemini Deep Research web** et que **L2 soit le niveau multi-agent CLI**.

### Fichiers autorisés
- `core/tools/declarations.py`
- `routers/voice.py`
- `services/search_router.py`
- `core/tools/dispatcher.py`
- `tests/test_search_router_and_vocal_level.py`
- `tests/test_l3_vps_routing.py`

### Étapes
1. Lire uniquement les sections pertinentes de ces fichiers, notamment `declarations.py:129-137`, `declarations.py:302-308`, le prompt système de `routers/voice.py`, les routes de `services/search_router.py`, et les blocs concernés de `core/tools/dispatcher.py`.
2. Déclarer L3 comme une recherche approfondie web Gemini ; supprimer les formulations qui imposent Antigravity CLI/VPS ou interdisent `browser_task`.
3. Faire router L3 vers le pipeline browser agent avec la tâche exacte `gemini_deep_research` (le moteur est dans `services/gemini_web_automator.py`, mais ne modifier pas ce fichier). Faire de `browser_task`/Gemini le chemin web L3, sans recréer un navigateur.
4. Déplacer la sémantique « multi-agent CLI » vers L2 et aligner les descriptions, le prompt vocal et les branchements du dispatcher.
5. Conserver un repli CLI uniquement si la recherche web échoue réellement. Le code doit signaler explicitement à l’utilisateur que le repli CLI a été utilisé ; ne jamais le présenter comme une recherche web réussie.
6. Mettre à jour les tests pour vérifier les niveaux, la tâche `gemini_deep_research`, le repli explicite et l’absence de contradiction L2/L3.

### Contraintes et critères
- Ne modifier aucun fichier hors de la liste autorisée.
- Préserver les interfaces publiques, les réponses vocales et la gestion d’erreurs existantes hors du routage concerné.
- Ne pas appeler le réseau dans les tests ; mocker le browser agent et le repli CLI.
- Les tests doivent échouer si L3 revient à `launch_deep_research` comme chemin principal ou si L2 est décrit comme `browser_task`.

### Vérification
```bash
pytest -q tests/test_search_router_and_vocal_level.py tests/test_l3_vps_routing.py
```

---

## 2) Installation LaTeX VPS idempotente **[niveau recommandé : low]**

**Prompt à coller dans Gemini Flash / Antigravity IDE**

Dans `Pierre38610/jarvis-core`, crée un script VPS idempotent pour la génération de rapports LaTeX.

### Fichier autorisé
- `scripts/setup_vps_latex.sh`

### Étapes
1. Créer un script Bash strict (`set -Eeuo pipefail`) relançable sans erreur.
2. Installer, via apt, les paquets exacts : `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-lang-french`, `texlive-fonts-recommended`, `latexmk`, `lmodern`.
3. Gérer proprement une exécution non-root (message clair ou usage de `sudo` disponible), sans supposer Docker ; il n’existe pas de `Dockerfile` à modifier.
4. Ajouter une vérification qui écrit dans un répertoire temporaire un `.tex` minimal avec accents français, le compile avec `latexmk -pdf -interaction=nonstopmode`, puis vérifie que le PDF existe. Nettoyer les fichiers temporaires avec `trap`.
5. Documenter dans les commentaires l’usage, l’idempotence, les paquets et le test de compilation ; ne pas installer autre chose.

### Contraintes et critères
- Ne modifier que `scripts/setup_vps_latex.sh`.
- Ne pas exécuter `apt`, ne pas demander de réseau et ne pas exiger LaTeX sur la machine de développement.
- Le script doit être lisible, retourner un code non nul en cas d’échec de compilation et fonctionner avec des accents français.

### Vérification statique
```bash
bash -n scripts/setup_vps_latex.sh
```

### Test réel manuel (sur VPS uniquement)
```bash
sudo bash scripts/setup_vps_latex.sh
```
Vérifier ensuite que le `.tex` de test compile en PDF et que le script peut être relancé sans réinstaller inutilement ni échouer.

---

## 3) Rapports LaTeX pour L2 + envoi email **[niveau recommandé : medium]**

**Prompt à coller dans Gemini Flash / Antigravity IDE**

Dans `Pierre38610/jarvis-core`, ajoute la production de rapports LaTeX au parcours **L2 multi-agent CLI**, puis l’envoi du PDF par email.

### Fichiers autorisés
- `services/latex_report_service.py` (nouveau)
- `core/tools/declarations.py`
- `core/tools/dispatcher.py`
- `services/agentic_runner.py`
- `services/email_service.py`

### Étapes
1. Lire uniquement les signatures et sections pertinentes de `services/agentic_runner.py`, `services/email_service.py`, `core/tools/declarations.py` et `core/tools/dispatcher.py` (notamment l’envoi avec pièce jointe autour de `1906-1950`, et les exemples autour de `787-792` et `1109-1113`).
2. Créer `services/latex_report_service.py` avec un template `.tex`, une fonction de génération et une fonction de compilation. Échapper au minimum `& % $ # _ { } ~ ^ \\` dans le contenu injecté ; ne jamais concaténer du contenu non échappé dans le document.
3. Compiler avec `latexmk -pdf -interaction=nonstopmode` via `subprocess`, dans un répertoire de travail isolé, avec timeout configurable. Retourner le chemin du PDF en succès ; en erreur, retourner/lever une erreur contenant le chemin du log et un extrait exploitable.
4. Consigner à l’agent L2 multi-agent CLI de rédiger le rapport en LaTeX structuré (titre, résumé, sections, sources si présentes), sans inventer de sources ni de résultats.
5. Brancher l’envoi email en réutilisant `services/email_service.py` et ses pièces jointes, avec le PDF joint en succès.
6. Si la compilation échoue, joindre un fichier `.md` de repli et indiquer clairement à l’utilisateur que le PDF n’a pas pu être compilé ; ne pas masquer l’erreur LaTeX.
7. Conserver L3 web inchangé par ce prompt ; ne pas déplacer le routage L3 traité au prompt 1.

### Contraintes et critères
- Ne modifier que les cinq fichiers autorisés.
- Pas de shell construit à partir du contenu utilisateur ; utiliser une liste d’arguments et un timeout.
- Ne pas appeler réseau, navigateur, SMTP ou apt dans les tests associés ; préserver la compatibilité avec une machine sans LaTeX.
- Respecter les signatures et mécanismes d’email existants, notamment les pièces jointes.

### Vérification
```bash
python -m py_compile services/latex_report_service.py
pytest -q tests/test_latex_report_service.py
```
Si ce test n’existe pas encore, créer d’abord le test dans le prompt 4, puis exécuter la commande.

---

## 4) Tests de non-régression et test VPS manuel **[niveau recommandé : low]**

**Prompt à coller dans Gemini Flash / Antigravity IDE**

Ajoute les tests de non-régression ciblés pour L2/L3 et les rapports LaTeX, sans aucun effet externe.

### Fichiers autorisés
- `tests/test_search_router_and_vocal_level.py`
- `tests/test_l3_vps_routing.py`
- `tests/test_latex_report_service.py` (nouveau)

### Étapes
1. Lire uniquement ces tests et les signatures des fonctions qu’ils testent ; ne pas parcourir tout le dépôt.
2. Compléter les tests L2/L3 : L3 appelle la tâche web `gemini_deep_research`, L2 sélectionne le multi-agent CLI, et le repli CLI de L3 est annoncé explicitement.
3. Tester le service LaTeX avec subprocess, filesystem et email mockés : échappement des caractères spéciaux, timeout, succès PDF, log en erreur et repli `.md` joint.
4. Interdire dans les tests tout réseau, navigateur, SMTP réel, apt, VPS ou dépendance à une installation LaTeX locale.
5. Ajouter des assertions sur les chemins de pièces jointes et sur les messages d’erreur ; éviter les assertions fragiles sur des timestamps ou des UUID.
6. Dans les commentaires de test, documenter le test réel manuel à exécuter sur un VPS après les prompts 1 à 3 ; ne pas l’automatiser dans pytest.

### Contraintes et critères
- Ne modifier que les fichiers de test listés.
- Utiliser uniquement des mocks/monkeypatch temporaires et les nettoyer après chaque test.
- Les tests doivent être déterministes et fonctionner hors réseau.

### Vérification
```bash
pytest -q tests/test_search_router_and_vocal_level.py tests/test_l3_vps_routing.py tests/test_latex_report_service.py
```

### Test réel manuel sur VPS
Après installation avec `sudo bash scripts/setup_vps_latex.sh`, lancer un rapport L2 complet avec les variables email configurées, vérifier la création du PDF, l’envoi avec pièce jointe et le repli `.md` en provoquant volontairement une erreur LaTeX. Ne jamais exécuter ce scénario dans CI.
