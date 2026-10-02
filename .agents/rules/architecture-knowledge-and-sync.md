# Règle Fondamentale : Connaissance Globale & Maintien de l'Architecture de Jarvis

## 1. Obligation de Lecture Préalable (Avant toute intervention)
- Avant d'entamer la moindre analyse, modification, ajout de fonctionnalité ou refactorisation sur le projet `jarvis-core`, l'agent **DOIT OBLIGATOIREMENT LIRE** le fichier de référence d'architecture :
  - **Emplacement du fichier** : `ARCHITECTURE_COMPLETE_JARVIS.md` (situé à la racine du projet).
- **Objectif** : Avoir une vision globale, précise et systémique de l'architecture de J.A.R.V.I.S. (topologie VPS Oracle Cloud + PC Windows local, protocoles audio Gemini Live, services Docker Redis/PostgreSQL/Qdrant/n8n, gestion des clés et quotas, outils agentiques Antigravity et Browser-Use). Cela garantit un travail efficient, sans réinventer des patterns existants et sans casser les mécanismes de résilience ou de sécurité établis.

## 2. Obligation de Mise à Jour (Une fois le travail terminé)
- Dès qu'une modification substantielle, un nouvel outil, un nouveau service, un changement de modèle ou une refactorisation est effectuée sur le projet, l'agent **DOIT OBLIGATOIREMENT COMPLÉTER ET METTRE À JOUR** le fichier `ARCHITECTURE_COMPLETE_JARVIS.md`.
- **Points de vigilance pour la mise à jour** :
  - Ajuster les schémas, descriptions de services et listes d'outils si nécessaire.
  - Documenter les nouveaux endpoints ou contrats WebSockets le cas échéant.
  - Maintenir le document à jour pour que les prochains agents puissent toujours s'appuyer sur une source de vérité 100 % exacte.

## 3. Protocole de Vérification Factuelle (Obligatoire Avant de Clore une Session)

Toute affirmation du référentiel doit pouvoir être prouvée par le code. L'agent **DOIT** re-vérifier les éléments suivants avec les commandes indiquées (Windows PowerShell, à la racine `jarvis-core`) dès qu'un doute existe, et corriger le document si un écart est constaté :

1. **Nombre et noms des outils déclarés** (le document en annonce **49**) :
   - `Select-String -Path core\tools\declarations.py -Pattern 'name="([a-z_]+)"' -AllMatches`
   - Vérifier la cohérence de la matrice §8.1 (une ligne par déclaration) et des compteurs de l'en-tête, de la table des matières et du §8.16.
2. **Routes HTTP / WebSocket réelles** (source : `App.py` + `routers/*.py`) :
   - `Select-String -Path App.py,routers\*.py -Pattern '@(app|router)\.(get|post|put|delete|websocket)\('`
   - Vérifier la matrice §9.1 (toute route déclarée doit y figurer, y compris les alias multi-décorateurs).
3. **Arborescence et inventaire de fichiers** :
   - `Get-ChildItem -Name` sur `core\tools`, `services`, `services\model_routing`, `services\browser_agent`, `routers`, `tests`.
   - Mettre à jour le §1.4 si un module a été ajouté, renommé ou supprimé.
4. **Modèles, routage et drapeaux** (source : `config/models.json`, `config.py`, `services/model_routing/`) :
   - `Select-String -Path config.py -Pattern 'MODEL_ROUTING_ENABLED|paid_key_authorized|get_effective_paid_key'`
   - `Select-String -Path services\model_routing\*.py,services\live_mode_policy.py -Pattern 'def (select_model|execute_with_fallback|_log_tier_routing)'`
   - Mettre à jour le §5 si un modèle, une règle de routage ou un mécanisme de consentement change.
5. **Version affichée dans le HUD** :
   - `Select-String -Path static\index.html -Pattern 'hud-version-tag'`
   - L'en-tête du document (ligne « Dernière révision majeure ») et la section §11.1 doivent citer exactement cette version.
6. **Règles de déontologie du rapport** : ne jamais inventer un nom d'outil, une route ou un symbole. Si un élément n'est pas retrouvé dans le code, il doit être supprimé du document ou explicitement marqué comme dette technique.
7. **Inventaire et santé de la suite de tests** (le document annonce **34 modules racine + 12 `tests/unit/` + 1 `tests/e2e/`**) :
   - `(Get-ChildItem tests -File -Filter 'test_*.py').Count` ; `(Get-ChildItem tests\unit -File -Filter 'test_*.py').Count` ; `(Get-ChildItem tests\e2e -File -Filter 'test_*.py').Count`
   - `python -m pytest tests --ignore=tests/e2e -q` (la campagne doit être **verte** avant de clore la session ; reporter le total exact dans §12.2.4).
   - Tout test obsolète (dérive de refactorisation : renommage de fonction, nouvel argument obligatoire, portail `arg_validator` exigeant `confirmed_by_user=True`) doit être **corrigé pour refléter le contrat réel du code**, jamais désactivé ni supprimé sans justification écrite.

## 4. Interdiction de Dérive Silencieuse

- Ne jamais « corriger » le document à l'aveugle : toute modification de compteur (nombre d'outils, de routes, de tests) doit être justifiée par une sortie de commande.
- Ne jamais réécrire intégralement un chapitre existant si une modification ciblée suffit (règle de moindre diff).
- En cas de refactorisation structurelle (déplacement de module, renommage de service), mettre à jour **simultanément** : §1.4 (arborescence), la section thématique concernée (§5, §7, §8, §9), la table des matières si un titre change, et l'en-tête de version.
- Terminer chaque intervention par un rapport JSON standardisé (voir `AGENTS.md`) mentionnant `files_changed` et les vérifications exécutées.
