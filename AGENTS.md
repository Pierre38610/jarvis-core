# RÈGLES GÉNÉRALES DES AGENTS ANTIGRAVITY CLI (JARVIS)

Ce document définit les directives d'exécution obligatoires pour tout agent autonome lancé par J.A.R.V.I.S. via Antigravity CLI (`agy`).

## 1. Autonomie & Prise d'initiative
- N'interromps pas l'exécution pour poser des questions interactives à l'utilisateur.
- Fais des hypothèses raisonnables basées sur le contexte fourni, documente-les clairement dans ton rapport final.
- Résous les problèmes de manière autonome et va jusqu'au bout de la tâche confiée.

## 2. Sécurité & Confidentialité des Secrets
- **INTERDICTION STRICTE** de lire, afficher ou extraire les variables d'environnement secrètes, les fichiers `.env`, les clés d'API (Gemini, OpenAI, Anthropic, tokens Cloudflare, Stripe, etc.) ou les clés SSH privées.
- **AUCUNE ACTION DE PAIEMENT** : Ne jamais initier d'achat, de transaction financière ou de souscription.
- **PAS D'ACTIONS DESTRUCTIVES** : Pas de `rm -rf`, de `git push --force`, de suppression de base de données (`DROP TABLE`, `DELETE FROM ...` sans filtre) sans consigne explicite et validée.

## 3. Périmètre & Confinement
- Opère strictement au sein de l'espace de travail (`workspace`) fourni.
- Ne modifie aucun fichier système en dehors du périmètre du projet.
- **Contrats d'architecture par sous-dossier** : Chaque sous-dossier de l'arborescence modulaire dispose de son propre contrat d'architecture et de confinement. L'agent ne modifie aucun fichier hors du dossier ciblé par sa tâche sans prompt explicite :
  - `backend/ARCHITECTURE.md` : FastAPI, état, outils, routeurs, services, DB et tests.
  - `frontend/ARCHITECTURE.md` : Interface PWA HUD (`frontend/static/`).
  - `firmware/ARCHITECTURE.md` : Code C++/ESP-IDF pour microcontrôleur ESP32-S3 (`firmware/esp32/`).
  - `ops/ARCHITECTURE.md` : Relais local Windows, lanceurs et scripts de déploiement cloud.
  - `docs/ARCHITECTURE.md` : Spécifications, documentation technique et workflows n8n.
  - `_archive/ARCHITECTURE.md` : Sauvegardes, baselines et scripts historiques décommissionnés.

## 4. Rigueur, Registre de Capacités & Vérification du Travail
- **RÈGLE OBLIGATOIRE (`CAPABILITIES_LEDGER.md`)** : Toute mission d'auto-amélioration (`self_improve` ou `prompt_batch_runner`) qui ajoute, modifie ou corrige une fonctionnalité de Jarvis DOIT mettre à jour `CAPABILITIES_LEDGER.md` (et `ARCHITECTURE_COMPLETE_JARVIS.md` si l'architecture change) avant de clôturer la tâche.
- Vérifie systématiquement tes modifications (tests unitaires `pytest` via `.\venv\Scripts\pytest.exe -v backend/tests/`, vérification de syntaxe Python, linting) avant de clore la session.
- Ne réécris pas un fichier existant en entier si des modifications ciblées suffisent.

## 5. Rapport de Sortie Standardisé (JSON)
À la fin de ton intervention, ta dernière réponse doit obligatoirement inclure un bloc JSON structuré sous cette forme exacte :
```json
{
  "status": "completed",
  "summary": "Courte synthèse des réalisations",
  "actions_done": ["action 1", "action 2"],
  "files_changed": ["fichier1.py", "fichier2.py"],
  "errors": [],
  "next_steps": ["étape suivante optionnelle"]
}
```
Ce format est automatiquement parsé par le moteur de supervision J.A.R.V.I.S.
