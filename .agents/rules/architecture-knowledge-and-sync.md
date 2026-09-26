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
