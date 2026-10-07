# Correctif définitif — Jarvis L3 Gemini Deep Research (Antigravity IDE)

Dépôt ciblé : `Pierre38610/jarvis-core` (branche `main`). Exécuter les prompts ci-dessous **dans l’ordre**, dans le même workspace. Le symptôme est confirmé : Gemini Flash répond parfois « Je ne suis qu’un modèle de langage… » puis le chip Deep Research apparaît après coup ; un collage manuel avec Deep Research actif fonctionne.

## Prompt 1 — niveau **high** (diagnostic + correctif minimal)

Tu es l’agent de maintenance du dépôt `jarvis-core`. Lis d’abord le code réel, sans te fier à la documentation :

- `services/gemini_web_automator.py` : `UIMapManager.get_action`, `UIMapManager.update_coordinates`, `GeminiWebAutomator.click_with_verification`, `_fill_prompt`, `_send_prompt`, `_confirm_research_plan`, `_wait_for_research_completion`, `run_deep_research` et le flux de connexion CDP ;
- `services/browser_agent/recipes/gemini_deep_research.md` ;
- `services/deep_research_service.py` ;
- `services/vps_chrome.py` ;
- tests associés, au minimum `tests/test_gemini_web_automator.py`, `tests/test_deep_research.py`, `tests/test_vps_chrome.py`, plus les tests qui patchent ces méthodes.

Corrige **uniquement** la course d’activation Deep Research et les clics fragiles, en conservant les interfaces et le comportement public. Dans `GeminiWebAutomator` :

1. Chaque exécution ouvre un chat neuf (aucun état/chip/prompt résiduel). Active Deep Research avec sélecteurs DOM/accessibilité robustes (`aria-label`, `role`, `aria-pressed`, `aria-selected`, `data-test-id`, texte exact/insensible à la casse), jamais une coordonnée en premier. Les coordonnées de `UIMapManager` ne sont qu’un dernier fallback, après recalcul DOM et vérification.
2. Après le clic d’activation, **poll** le DOM jusqu’à confirmation que le chip est réellement actif : `aria-pressed=true` ou `aria-selected=true`, ou chip Deep Research visible dans la zone de saisie/placeholder Deep Research. Timeout borné ; sinon ne rien envoyer et lever/retourner une erreur explicite contenant exactement `Deep Research non activé`.
3. Remplis le champ via locator DOM ; `insertText` ou frappe humanisée, puis petite pause. Relis la valeur/textContent et vérifie qu’elle est strictement égale au prompt avant tout envoi. Si elle diffère, corrige et revalide.
4. N’appelle `_send_prompt` qu’après ces validations. Après envoi, vérifie un signal de démarrage Deep Research (plan de recherche, indicateur de recherche ou UI équivalente). Si Gemini affiche le plan, `_confirm_research_plan` doit cliquer le bouton réel (`Démarrer la recherche` / `Lancer la recherche` / sélecteur ARIA), puis revérifier le démarrage. Ne pas utiliser de délai fixe comme preuve d’état.
5. Dans le texte extrait par `_wait_for_research_completion`/extraction, détecte les refus génériques FR/EN, notamment : `je ne suis qu'un modèle de langage`, `je ne suis qu’un modèle de langage`, `i'm just a language model`, `I am just a language model`, `as an AI language model`, `je ne peux pas effectuer cette recherche`. Normalise casse, accents/apostrophes et espaces.
6. En cas de refus ou d’activation non confirmée : journalise l’étape, l’état observé et le timeout sans secrets, prends une capture d’écran, ouvre un **nouveau chat**, puis réessaie **une seule fois** tout le flux activation → confirmation → insertion → vérification → envoi. Après le second échec, retourne une erreur explicite `Deep Research non activé` (pas un faux rapport réussi).

Ajoute des logs structurés sur les transitions et la cause d’échec, et une capture sur chaque échec terminal. Pas de refactor hors sujet, pas de changement de modèle, pas de modification des secrets/CDP. Fais un diff minimal et réponds seulement par un bref résumé des fichiers modifiés et des tests.

## Prompt 2 — niveau **medium** (tests unitaires anti-régression)

Ajoute ou adapte des tests unitaires avec mocks Playwright/CDP, sans navigateur réel, couvrant exactement :

- détection des refus génériques FR/EN, y compris apostrophe typographique et casse différente ;
- **aucun envoi** (`_send_prompt` jamais appelé) si le chip Deep Research ne devient pas actif avant le timeout ;
- polling positif via `aria-pressed`, `aria-selected` et/ou chip visible dans la zone de saisie ;
- vérification que le contenu inséré est égal au prompt avant l’envoi ;
- plan Gemini présent puis clic confirmé de `Démarrer la recherche`/`Lancer la recherche` ;
- refus : nouveau chat et retry exactement une fois, puis erreur `Deep Research non activé` ;
- priorité aux sélecteurs DOM/ARIA et recours aux coordonnées seulement en dernier fallback ;
- régression des interfaces existantes de `UIMapManager`, `click_with_verification`, `_fill_prompt`, `_send_prompt`, `_confirm_research_plan` et `_wait_for_research_completion`.

Lance au minimum :

```bash
python -m pytest -q tests/test_gemini_web_automator.py tests/test_deep_research.py tests/test_vps_chrome.py
```

Corrige seulement les tests ou le correctif nécessaires. Réponds avec le résultat court de la commande et les fichiers touchés.

## Prompt 3 — niveau **low** (vérification finale ciblée)

Relis le diff final et vérifie que le flux `run_deep_research` est strictement : chat neuf → activation DOM → polling chip actif → insertion → égalité du prompt → pause → envoi → confirmation éventuelle du plan → preuve de démarrage → attente/extraction. Vérifie qu’aucun clic coordonné n’est le chemin principal, qu’un timeout n’envoie jamais le prompt et qu’un refus ne peut pas être livré comme rapport. Exécute les tests ciblés ; ne modifie rien d’autre. Réponds uniquement : tests, fichiers modifiés, éventuel risque résiduel.

## Contraintes inviolables

- Ne pas faire de grand refactor ni toucher aux fonctionnalités L1/L2, à `deep_research_service.py` ou `vps_chrome.py` sauf nécessité prouvée par le flux CDP.
- Ne pas supprimer la compatibilité des mocks/tests existants.
- Ne jamais masquer un échec derrière un résultat générique ; le message terminal doit contenir `Deep Research non activé`.
- Ne pas exposer cookies, tokens, prompts sensibles ou captures dans les logs.
