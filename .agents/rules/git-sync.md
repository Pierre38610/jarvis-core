---
trigger: always_on
---

# Règle Git & Déploiement Cloud pour jarvis-core

## 1. Obligation de Déploiement Automatisé
À chaque modification ou ajout de code validé au sein du projet `jarvis-core`, l'agent **DOIT** exécuter le script de synchronisation et déploiement cloud automatisé :
`.\venv\Scripts\python.exe sync_deploy.py -m "Description concise des changements"`

## 2. Paramètre Critique d'Exécution Antigravity (`BypassSandbox: true`)
- ⚠️ **INDISPENSABLE** : Lors de l'appel à l'outil `run_command` pour exécuter `sync_deploy.py`, l'agent **DOIT OBLIGATOIREMENT** définir **`BypassSandbox: true`**.
- **Raison** : Le script effectue des opérations réseau sortantes vers GitHub (`git push origin main`) et vers le VPS Oracle Cloud (`158.178.206.213:22` via SFTP/SSH). Le sandbox par défaut sans réseau (`BypassSandbox: false`) bloque ces connexions et fait systématiquement échouer le déploiement.
- **Interpréteur** : Toujours utiliser l'interpréteur du venv local `.\venv\Scripts\python.exe` car il contient les dépendances requises (`paramiko`).

## 3. Mise à Jour Obligatoire de la Version de l'App (HUD)
Avant de lancer le déploiement, s'assurer que la version visible a bien été incrémentée/mise à jour dans :
1. `static/index.html` :
   - Tag de version HUD : `<span class="hud-version-tag" id="hudVersionTag" ...>vX.Y.Z</span>`
   - Cache-busting CSS & JS : `<link rel="stylesheet" href="/static/style.css?v=X.Y.Z">` et `<script src="/static/app.js?v=X.Y.Z"></script>`
2. `static/style.css` : En-tête de version (`Version X.Y.Z | ...`).
3. `ARCHITECTURE_COMPLETE_JARVIS.md` : Ligne « Dernière révision majeure » dans l'en-tête et §11.1.

## 4. Pipeline de Déploiement & Fonctionnement
Le script `sync_deploy.py` réalise de bout en bout :
1. `git add .`, `git commit -m "..."`, et `git push origin main` vers le dépôt GitHub.
2. Génération d'une archive `.tar.gz` filtrée (excluant `.env`, clés SSH, dossiers caches, venv).
3. Connexion SSH/SFTP au VPS Oracle Cloud (`158.178.206.213`), téléversement vers `/tmp/jarvis_update.tar.gz`.
4. Extraction dans `/home/opc/jarvis-core` et redémarrage propre du service systemd `sudo systemctl restart jarvis`.
5. Vérification du statut actif (`sudo systemctl is-active jarvis`).

## 5. Attente et Validation
- La commande dure généralement entre **15 et 30 secondes** (temps de compression, transfert SFTP et redémarrage).
- Configurer `WaitMsBeforeAsync: 10000` et attendre la fin de la tâche en vérifiant que la sortie affiche :
  `[✔] Service 'jarvis' redémarré avec succès (Statut: ACTIF).`
  `🎉 DÉPLOIEMENT TERMINÉ : Votre Jarvis Cloud est 100% à jour !`
- En cas d'erreur de clé SSH, vérifier la présence de la clé dans `clés ssh/ssh-key-2026-09-25.key`.
- Ne jamais commiter ni pousser de fichiers contenant des secrets ou mots de passe.