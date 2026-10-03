---
trigger: always_on
---

# Règle Git & Déploiement Cloud pour jarvis-core

- À chaque modification ou ajout de code validé au sein du projet `jarvis-core`, exécuter le script de synchronisation et déploiement cloud automatisé :
  `.\venv\Scripts\python.exe sync_deploy.py -m "Description concise des changements"` (ou `.\sync_deploy.bat "Description concise des changements"`).
- Ce script assure automatiquement :
  1. Le commit et le `git push origin main` vers le dépôt GitHub.
  2. Le déploiement instantané des fichiers modifiés sur le VPS Oracle Cloud (`158.178.206.213`).
  3. Le redémarrage transparent et sans coupure du service `jarvis` sur le serveur pour appliquer la nouvelle version en temps réel.
- Veiller à ne jamais commiter ni téléverser de fichiers sensibles (.env, bases de données, clés d'accès, clés SSH privées).
-Met bien à jour la version de l'agent visible sur l'app ( en haut de la page ) à chaque mise à jour du code