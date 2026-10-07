# Jarvis — Refonte UI « Pro » (direction A : Linear/Vercel)
Agent : Gemini Flash · Antigravity IDE · Fichiers concernés : static/index.html, static/style.css, static/app.js
Faire les prompts dans l'ordre. Faire un commit après chaque prompt validé.

## Règles communes (déjà incluses dans chaque prompt, ne pas recoller)
- Ne JAMAIS renommer ou supprimer un id, une classe ou un data-attribute utilisé par app.js.
- Pas de framework, pas de build : HTML + CSS + JS vanilla, CDN autorisé.
- Ne pas lire app.js en entier : utiliser grep / la recherche.
- Après chaque modif : lancer l'app, ouvrir la page, vérifier qu'il n'y a aucune erreur console et que l'onglet touché fonctionne.

---

## Prompt 0 — Cartographie (niveau : LOW)
```
Lis AGENTS.md. Puis, SANS lire app.js en entier, fais un grep dans static/app.js de :
getElementById, querySelector, classList, innerHTML, data-.
Crée static/UI_MAP.md (max 80 lignes) qui liste :
1. Les ids/classes de index.html utilisés par app.js (ne pas toucher).
2. La liste des onglets/vues et modales avec leur id racine.
3. Les variables CSS existantes dans style.css (:root) et les 5 couleurs les plus utilisées.
4. Les endroits où app.js injecte du HTML avec du texte ou des emojis.
Ne modifie aucun autre fichier.
```

## Prompt 1 — Design tokens & typographie (niveau : MEDIUM)
```
Contexte : static/UI_MAP.md. Objectif : une base visuelle sobre et pro.
Dans static/style.css, en haut, crée/remplace :root par :
--bg:#0A0A0B; --surface:#111113; --surface-2:#18181B; --border:#1F1F23;
--text:#EDEDEF; --text-muted:#8B8B93; --accent:#3B82F6; --success:#22C55E;
--warning:#F59E0B; --danger:#EF4444; --radius:10px; --radius-sm:6px;
--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.25);
--font:'Inter',system-ui,sans-serif; --mono:'JetBrains Mono',ui-monospace,monospace;
--t:160ms cubic-bezier(.2,.8,.2,1);
Dans index.html <head> : ajoute Google Fonts Inter (400/500/600) + JetBrains Mono (400).
Puis, dans style.css : remplace les couleurs codées en dur par ces variables,
supprime text-transform:uppercase et letter-spacing > 0.05em (sauf sur les petits labels
de section, où il faut letter-spacing:.04em et font-size:11px), supprime les glows/text-shadow néon,
body font-family:var(--font), logs/code en var(--mono).
Ne change ni le HTML ni le JS. Vérifie chaque onglet visuellement + aucune erreur console.
```

## Prompt 2 — Coquille : sidebar + barre d'état (niveau : HIGH)
```
Contexte : static/UI_MAP.md. Ne renomme aucun id/classe existant.
1. index.html : enveloppe le contenu dans <div class="app-shell"> avec
   <aside class="sidebar"> (logo + nom "Jarvis" + liens : Assistant, Messages, Kindle,
   Supervision, Logs, Antigravity) et <main class="app-main">.
   Les liens doivent appeler la MÊME logique d'ouverture d'onglet que les boutons actuels
   (trouve-la par grep dans app.js et réutilise-la ; ne la duplique pas).
   Sidebar : 220px, var(--surface), border-right var(--border), lien actif = fond
   var(--surface-2) + texte var(--text).
2. Ajoute en haut de .app-main une <header class="statusbar"> (48px) qui contient :
   le nom du modèle actif, un badge "Gratuit"/"Payant" pour la clé, une pastille d'état de connexion
   (vert/orange/rouge), et la version en var(--text-muted) 12px. Alimente-la en déplaçant
   les éléments existants qui affichent déjà ces infos (ne crée pas de nouveaux appels réseau).
3. Supprime le texte purement décoratif (ex : "0x4F", "fn() async", "CPU: OK", "PROTOCOLE",
   "TRANSMISSION") à moins qu'un id soit lu par app.js ; dans ce cas, garde l'élément avec hidden.
Teste : navigation entre tous les onglets, statusbar à jour, aucune erreur console.
```

## Prompt 3 — Icônes (niveau : LOW)
```
Remplace les emojis de l'UI (index.html + les chaînes HTML injectées par app.js listées dans
UI_MAP.md) par des icônes Lucide : <script src="https://unpkg.com/lucide@latest"></script>,
<i data-lucide="mic"></i>, puis appelle lucide.createIcons() une fois au chargement et
après chaque injection de HTML qui contient des icônes.
Taille 16px dans la sidebar et les boutons, stroke-width 1.75, couleur currentColor.
Ne modifie pas les textes envoyés au backend ou à la TTS. Teste chaque onglet.
```

## Prompt 4 — Accueil : orbe + mini-lecteur (niveau : MEDIUM)
```
Vue Assistant (cœur JARVIS) :
- Centre l'élément micro/orbe existant : cercle de 160px, dégradé radial accent→transparent,
  animation "pulse" douce (scale 1→1.04, 2s) UNIQUEMENT quand l'état est "écoute"
  (réutilise la classe/état déjà posé par app.js ; sinon ajoute .is-listening au même endroit).
- En dessous, une seule ligne d'état 14px var(--text-muted) (ex : "À l'écoute · Gemini Live").
- Le lecteur Spotify devient un mini-lecteur fixé en bas de .app-main : 56px, var(--surface),
  pochette 40px, titre et artiste, boutons icônes. Garde tous les ids.
- Respecte prefers-reduced-motion (pas d'animation).
Teste : démarrage/arrêt du micro, contrôles Spotify.
```

## Prompt 5 — Supervision (niveau : HIGH)
```
Vue Supervision globale. Ne change pas les ids lus par app.js.
1. Découpe le contenu en 4 sous-onglets via un "segmented control" en haut :
   Modèles · Clés API · Métriques · Patches. Gère l'affichage en CSS + petit JS (classe .active),
   et ajoute ce JS dans app.js à la fin, dans une fonction initSupervisionTabs().
2. Métriques : grille de cartes .stat-card (valeur 24px 600, label 12px muted, bordure var(--border),
   radius var(--radius)). Garde les éléments existants qui reçoivent les valeurs.
3. États vides : quand une liste/table est vide ou vaut "0" / "Aucun patch", affiche
   un bloc .empty-state (icône Lucide 24px muted + une phrase utile + éventuel bouton).
   Implémente-le via une fonction utilitaire renderEmpty(el, icon, text) réutilisable.
4. Remplace les "Chargement..." / "Initialisation..." par des skeletons CSS (.skeleton shimmer).
5. Tables : lignes de 40px, header 12px muted, hover var(--surface-2), sans bordures verticales.
Teste avec des données présentes ET vides.
```

## Prompt 6 — Messagerie (niveau : MEDIUM)
```
Vue Messagerie, style ChatGPT. Garde les ids/handlers.
- Liste des messages : max-width 760px centrée ; bulles utilisateur alignées à droite
  (var(--surface-2)) ; réponses Jarvis à gauche sans fond, texte 15px line-height 1.6.
- Zone de saisie fixe en bas : textarea auto-resize (max 6 lignes), Entrée = envoyer,
  Maj+Entrée = nouvelle ligne, bouton envoyer avec une icône.
- Glisser-déposer d'image sur la zone de saisie → réutilise la fonction d'upload existante
  (trouve-la par grep). Affiche un aperçu miniature supprimable.
- Suggestions sous forme de petites pastilles cliquables au-dessus de la saisie quand le fil est vide.
- Scroll automatique en bas à chaque nouveau message.
Teste : envoi texte, envoi image (clic + drag&drop), fil vide.
```

## Prompt 7 — Kindle & Logs (niveau : MEDIUM)
```
Kindle : zone de dépôt (bordure 1px dashed var(--border), hover accent, icône upload),
barre de progression fine (4px, accent), liste des derniers envois (nom, date, statut sous forme de badge).
Réutilise la logique d'envoi existante.
Logs : style terminal. Fond #070708, var(--mono) 12.5px, une ligne par entrée,
niveau coloré (INFO muted, WARN warning, ERROR danger) ; filtres sous forme de segmented
control (Tous/Info/Warn/Erreur) ; champ de recherche qui filtre côté client ;
auto-scroll sauf si l'utilisateur a remonté. Garde les ids existants.
Teste : envoi Kindle, filtrage et recherche dans les logs.
```

## Prompt 8 — Modales, toasts, autorisation (niveau : MEDIUM)
```
1. Ajoute à app.js une fonction toast(message, type='info', ms=3500) : pile en bas à droite,
   var(--surface), bordure gauche 3px colorée selon le type, fermeture au clic, animation 160ms.
   Remplace par toast() les notifications existantes de type "Page web ouverte" ou "Rapport envoyé"
   (grep alert( et les éléments de notification).
2. L'alerte Bluetooth permanente devient un toast "warning" (affiché une seule fois par session).
3. Modale clé payante : titre clair "Utiliser la clé payante ?", coût estimé en grand,
   boutons "Refuser" (secondaire) / "Autoriser" (accent). Supprime "STARK BILLING".
   Garde les handlers.
4. Toutes les modales : overlay rgba(0,0,0,.6) + backdrop-filter blur(4px), radius 12px,
   max-width 440px, fermeture avec Échap et au clic sur l'overlay, focus sur le 1er bouton.
5. Écran d'autorisation : logo, une phrase, un bouton "Autoriser cet appareil". Retire la mise en scène.
Teste chaque modale (ouverture, Échap, boutons) et les toasts.
```

## Prompt 9 — Mobile, finitions, accessibilité (niveau : MEDIUM)
```
- En dessous de 768px : la sidebar devient une barre d'onglets fixée en bas (icônes + label 10px),
  la statusbar est réduite (modèle + pastille), le mini-lecteur passe au-dessus de la barre d'onglets.
- Transitions var(--t) sur hover/focus/ouverture ; :focus-visible = outline 2px var(--accent).
- Contraste AA sur le texte muted ; aria-label sur les boutons qui n'ont qu'une icône.
- Supprime le CSS mort : sélecteurs absents de index.html ET de app.js (vérifie par grep avant de supprimer).
Teste à 375px, 768px et 1440px (devtools) + aucune erreur console.
```

## Prompt 10 — Recette finale (niveau : LOW)
```
Parcours chaque vue et chaque modale listées dans static/UI_MAP.md. Pour chacune, vérifie :
affichage, actions principales, aucune erreur console, rendu à 375px.
Lance pytest. Corrige uniquement les régressions trouvées (changements minimaux).
Écris un résumé de 10 lignes max à la fin de UI_MAP.md (ce qui a changé + ce qui reste à faire).
```