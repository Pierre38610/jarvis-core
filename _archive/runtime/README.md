# Artefacts Runtime Archivés — J.A.R.V.I.S. Core

Ce dossier conserve les artefacts et fichiers d'état générés lors de l'exécution runtime de J.A.R.V.I.S., archivés conformément au plan de rangement architectural (Prompt P2).

## Inventaire

### `tunnel_url.json`
- **Origine** : Généré lors de l'exécution du relais de tunnel Cloudflare (`tunnel_launcher.py`).
- **Contenu** : Objet JSON horodaté associant l'URL publique de tunnel (`https://jarvis.signalcraftapps.com`), l'adresse IP locale et le timestamp UNIX d'établissement de la session.
- **Rôle runtime** : Fichier d'état dynamique non source, anciennement situé dans `static/tunnel_url.json`. Déplacé ici pour isoler strictement les sources immuables du HUD PWA (`frontend/static/`).
