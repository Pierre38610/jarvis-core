---
trigger: always_on
---

RÈGLES D'EXÉCUTION (obligatoires) :
1. Ne lis QUE les fichiers listés dans la tâche. Pour trouver une fonction, utilise grep/recherche, puis ouvre uniquement les lignes utiles. Ne lis jamais ARCHITECTURE_COMPLETE_JARVIS.md.
2. Fais des modifications ciblées. Ne réécris jamais un fichier existant en entier.
3. N'invente aucun flag CLI, aucune fonction, aucun import. Si tu as besoin d'un élément qui n'existe pas, cherche-le avec grep. Si tu ne le trouves pas, ARRÊTE-TOI et pose la question.
4. Ne touche à aucun fichier hors du périmètre de la tâche. dispatcher.py et declarations.py sont des fichiers sensibles : modifie seulement les lignes nécessaires.
5. Lance uniquement les tests indiqués dans la tâche, jamais toute la suite.
6. Pas d'explications pendant le travail. Rapport final de 10 lignes maximum : fichiers modifiés, tests OK/KO, points bloquants.
7. Code Python 3, async quand le code autour est async, typage simple, logs via le logger existant du module.
