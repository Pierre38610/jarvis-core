# Cartographie UI Jarvis (UI_MAP)

## 1. Identifiants & Classes Clés de index.html utilisés par app.js (NE PAS TOUCHER)
- **Écrans & Authentification** : `#authScreen`, `#mainScreen`, `#pwdInput`, `#authBtn`, `#authFeedback`.
- **Microphone / Orbe / Statut** : `#toggleBtn`, `#btnLabel`, `#reactorHalo`, `#stateBadge`, `#stateLabel`, `#statusMessage`, `#micDot`, `#micText`, `#micDb`, `.eq-bar`, `#transcriptBox`, `#volumeSlider`, `#volPercent`, `#muteBtn`, `#volIcon`, `#micSelect`, `#micToggle`, `#micToggleBadge`, `#micToggleContainer`, `#micToggleIcon`.
- **Moteur, Modèles & Live** : `#engineChip`, `#engineSourceBadge`, `#engineModelText`, `#engineKeyBadge`, `#engineActionsBadge`, `#engineActionsCount`, `#liveActivityBand`, `#liveActivityTitle`, `#liveActivityStep`, `#liveActivityDetail`, `#liveBandTimestamp`, `#liveModelTag`, `#liveKeyBadge`, `#paidKeyToggle`, `#paidToggleBadge`, `#btnSwitchLiveStd`, `#btnSwitchLiveThinking`.
- **Messagerie / Chat** : `#chatModal`, `#btnCloseChat`, `#btnOpenChat`, `#chatBadge`, `#chatMessages`, `#chatTextInput`, `#btnChatSend`, `#chatFileInput`, `#btnChatAttach`, `#chatImagePreviewBar`, `#chatPreviewImg`, `#chatPreviewName`, `#btnRemoveChatImage`, `#btnChatClear`, `#chatTypingIndicator`, `#chatTypingText`, `#chatWelcomeBanner`, `#chatLightboxModal`, `#btnCloseLightbox`, `#lightboxImg`, `#lightboxTitle`.
- **Kindle & Docks** : `#kindleModal`, `#btnOpenKindleModal`, `#btnCloseKindleModal`, `#kindleDropzone`, `#kindleUserName`, `#kindleAccountStatusTag`, `#kindleUploadCard`, `#kindleUploadFileName`, `#kindleUploadStatusTag`, `#kindleUploadMessage`, `#kindleProgressBar`, `#kindleHistoryContainer`, `#kindleHistoryList`, `#kindleHistoryEmpty`, `#kindleStatusDesc`, `#kindleWebArticleUrl`, `#spotifyDock`, `#spotifyDockCover`, `#spotifyDockTrack`, `#spotifyDockArtist`, `#spotifyDockDevice`, `#spotifyDockProgress`, `#spotifyBtnPlayPause`, `#spotifyPlayIcon`, `#taskDock`, `#browserDock`, `#emailDock`.
- **Supervision & Métriques** : `#supervisionModal`, `#btnOpenOverview`, `#btnCloseSupervision`, `#btnCloseSupervisionFooter`, `#btnRefreshSupervision`, `#supervisionActionBadge`, `#supActionsCountBadge`, `#supActiveActionsContainer`, `#supNoActiveActions`, `#supWindowsCountBadge`, `#supWindowsList`, `#supPatchesCountBadge`, `#supPatchesListContainer`, `#supToolsTable`, `#metTotalCalls`, `#metFailureRate`, `#metAvgLatency`, `#metP95Latency`, `#metTotalCost`, `#metTopToolsBars`, `#metToolsTableRows`, `#btnMetrics24h`, `#btnMetrics7j`, `#btnMetrics30j`, `#supPaidKeyToggle`, `#supPaidToggleBadge`.
- **Logs & Modale Consentement Payant** : `#logsModal`, `#btnCloseLogsModal`, `#logsContent`, `#logsCountBadge`, `#logsLastUpdate`, `#logsAutoRefreshToggle`, `#btnCopyLogs`, `#logsSearchInput`, `.logs-segmented-control`, `.logs-filter-btn`, `[data-filter]`, `#paidConsentModal`, `#paidConsentTitle`, `#paidConsentMessage`, `#paidConsentCost`, `#paidConsentReason`, `#btnApprovePaid`, `#btnRejectPaid`.
- **Classes dynamiques d'état** : `.active`, `.state-listening`, `.state-speaking`, `.state-thinking`, `.state-browsing`, `.state-coding`, `.state-music`, `.state-offline`, `.badge-*`, `.is-speaking`, `.has-active-subagents`.

## 2. Liste des Vues / Onglets et Modales (Id racine)
- **Vues principales (Onglets de navigation via .hud-tab-container & .hud-tab-pane)** :
  - Écran d'authentification : `#authScreen`
  - Écran principal (App Shell) : `#mainScreen`
  - Onglet 1 - Assistant (Cockpit Avatar, Micro, Docks & Audio) : `#tabViewAssistant`
  - Onglet 2 - Messages (Discussion instantanée, Vision & Chat) : `#chatModal`
  - Onglet 3 - Kindle (Amazon Send to Kindle & Historique) : `#kindleModal`
  - Onglet 4 - Supervision (Supervision Stark AI, Modèles, Clés, Métriques, Patches) : `#supervisionModal`
  - Onglet 5 - Logs (Terminal Journalctl, Filtres & Recherche en direct) : `#logsModal`
  - Onglet 6 - Antigravity (Constellation d'agents CLI, Pilotage & Directives) : `#tabViewAntigravity`
- **Modales & Tiroirs Diagonaux (Dialogues flottants réels)** :
  - Visualiseur plein écran de photos (Lightbox) : `#chatLightboxModal`
  - Aperçu d'écran navigateur : `#browserModal`
  - Autorisation Clé Payante : `#paidConsentModal`

## 3. Variables CSS Existantes (:root) & Couleurs Principales
- **Variables :root existantes (style.css)** :
  - Arrière-plans : `--bg-space`, `--bg-surface`, `--bg-card`, `--bg-card-hover`, `--bg-glass`, `--bg-input`
  - Bordures : `--border-subtle`, `--border-glass`, `--border-highlight`, `--border-active`
  - Accents fonctionnels : `--cyan-core` (#38bdf8), `--cyan-glow`, `--cyan-deep`, `--emerald-safe` (#10b981), `--amber-warn` (#f59e0b), `--purple-code` (#a855f7), `--rose-alert` (#f43f5e)
  - Typographie & Rayons : `--text-primary`, `--text-secondary`, `--text-muted`, `--radius-xs` à `--radius-full`
  - Ombres & Effets : `--shadow-card`, `--shadow-glow-cyan`, `--shadow-glow-emerald`, etc.
- **Top 5 Couleurs les plus fréquentes dans style.css** :
  1. `#ffffff` / `#fff` (blanc pur)
  2. `rgba(56, 189, 248, 0.35)` et dérivés (teintes cyan/sky)
  3. `#38bdf8` / `#0284c7` (cyan / bleu actif)
  4. `rgba(255, 255, 255, 0.08)` (bordures subtiles glassmorphism)
  5. `#94a3b8` / `#64748b` (textes secondaires / muted)

## 4. Injections innerHTML avec Texte ou Emojis / Icônes dans app.js
- **Contrôles Audio & Spotify** : `volIcon.innerHTML`, `spotifyPlayIcon.innerHTML` (icônes SVG Play/Pause/Mute).
- **Satellites d'activité & Toasts** : `satelliteEl.innerHTML`, `toast.innerHTML` (badges et statuts d'agents).
- **Transcription en direct** : `currentEntryEl.innerHTML` (labels `VOUS:` et `J.A.R.V.I.S.:`).
- **Supervision & Métriques** :
  - `supActiveActionsContainer.innerHTML` (actions en cours ou état vide).
  - `supToolsTable.innerHTML`, `supWindowsList.innerHTML`, `patchesContainer.innerHTML` (cartes de patches et fenêtres).
  - `metTopToolsBars.innerHTML`, `metToolsTableRows.innerHTML` ("Aucun appel d'outil...", "Aucune métrique...").
- **Messagerie Chat** :
  - `meta.innerHTML` (en-tête auteur VOUS / J.A.R.V.I.S. + timestamp).
  - `textDiv.innerHTML` (rendu Markdown via `formatMarkdownText`).
  - `btnCopy.innerHTML` (`Copier` / `✓ Copié !` avec SVG), `btnSpeak.innerHTML` (`Écouter` / `Aoede...` avec SVG).
- **Logs Console & Antigravity** :
  - `logsContent.innerHTML`, `agyLogsContent.innerHTML` (formatage des lignes colorées de log ou messages d'erreur).
- **Select Microphone** : `select.innerHTML` (`<option>Microphone par défaut (Système)</option>`).

## 5. Résumé de Recette & Architecture Multi-Onglets (v5.89.0)
- **Modifications réalisées** : Remplacement des popups modales par un système complet de navigation multi-onglets intégrée dans l'App Shell (`.hud-tab-container` / `.hud-tab-pane`). Tous les 6 onglets de la barre latérale (Assistant, Messages, Kindle, Supervision, Logs, Antigravity) sont désormais connectés et fonctionnels sans aucune superposition bloquante. Seuls les dialogues réels (Lightbox, Consentement Clé Payante, Capture Navigateur) restent des modales.
- **État des tests & stabilité** : 100% des tests passés au vert (`646 passed`), conformité totale avec le contrat DOM (`UI_MAP.md`).
- **Reste à faire / Évolutions futures** : Continuer l'enrichissement visuel des graphiques de télémétrie et des flux d'exécution d'agents Antigravity multi-tâches.

