# Règle d'arrêt et de non-sur-itération (Anti-boucle)

1. **Objectif clair et arrêt immédiat** : Dès que l'objectif demandé par l'utilisateur est implémenté et que la vérification minimale (syntaxe/compilation/import) est validée (`COMPILE_OK`), **s'arrêter immédiatement**.
2. **Interdiction du perfectionnisme non sollicité** : Ne pas relancer de tests exhaustifs, de benchmarks secondaires ou de refactorisations supplémentaires non demandées une fois le code fonctionnel.
3. **Gestion des commandes asynchrones** : Attendre directement le résultat d'une commande via un timeout synchrone raisonnable (`WaitMsBeforeAsync`), éviter d'enchaîner des micro-tâches de diagnostic redondantes ou d'interroger en boucle le statut de tâches d'arrière-plan.
4. **Validation ciblée uniquement** :
   - Tester l'import ou la compilation du fichier modifié une seule fois.
   - Si le test passe : présenter immédiatement la synthèse concise à l'utilisateur et terminer le tour sans appel d'outil superflu.
