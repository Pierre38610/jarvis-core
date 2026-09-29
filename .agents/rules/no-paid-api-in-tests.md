---
trigger: always_on
---

# Règle d'économie des tests pour Pierre

- **INTERDICTION D'UTILISER LES CLES API LORS DES TESTS** :
  - Ne jamais appeler l'API Gemini lors de l'exécution de tests automatisés, scripts de validation ou diagnostics de régression.
  - À la place, simuler les réponses, utiliser des mocks ou produire la réponse directement en tant que modèle LLM assistant pour les vérifications de pipeline.
