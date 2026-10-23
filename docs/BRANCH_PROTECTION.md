# Guide des Règles de Protection de Branche GitHub (Branch Protection)

Ce document détaille les paramètres obligatoires à activer sur le dépôt GitHub `Pierre38610/jarvis-core` afin de sanctuariser la branche `main` contre toute régression ou altération non contrôlée par un agent d'auto-amélioration autonome.

---

## 1. Branche Cible
- **Branch name pattern** : `main`

---

## 2. Règles de Protection Obligatoires

### A. Exiger une Pull Request avant toute fusion (Require a pull request before merging)
- **Require approvals** : Coché (Minimum : **1 approbation**).
- **Dismiss stale pull request approvals when new commits are pushed** : Coché.
  *Tout nouveau commit sur la PR invalide l'approbation précédente et nécessite une re-validation.*
- **Require review from Code Owners** : Coché.
  *Active l'obligation de revue par les propriétaires désignés dans `.github/CODEOWNERS` (`@Pierre38610`).*
- **Require conversation resolution before merging** : Coché.

### B. Exiger le succès des vérifications d'état (Require status checks to pass before merging)
- **Require status checks to pass before merging** : Coché.
- **Require branches to be up to date before merging** : Coché.
- **Status checks requis (depuis `.github/workflows/ci.yml`)** :
  - `Build & Test` (exécutant `check_protected_paths.py`, `compileall`, `ruff` et `pytest backend/tests/unit`).

### C. Règles d'intégrité et de sécurité
- **Do not allow bypassing the above settings** : Coché.
  *S'applique également aux administrateurs pour éviter les fusions accidentelles sans CI.*
- **Restrict who can push to matching branches** : Coché.
  *Aucun push direct sur `main` ; toute modification transite impérativement par une PR.*
- **Allow force pushes** : Décoché (**Jamais de `git push --force`** sur `main`).
- **Allow deletions** : Décoché (**Empêche la suppression** de la branche `main`).

---

## 3. Garde-fou Pré-commit pour les Agents Autonomes

Avant de soumettre une modification ou d'ouvrir une PR, l'agent autonome peut tester la conformité de son lot de fichiers avec :

```bash
python ops/scripts/check_protected_paths.py --files fichier1.py fichier2.py
```

En cas de modification d'un fichier sensible (authentification, clés API, validateur d'arguments, déploiement ou workflows CI), le script renvoie un code d'erreur `1` et bloque l'opération, nécessitant une approbation explicite de Pierre.
