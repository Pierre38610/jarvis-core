"""core/tools/declarations.py
Palette complète des outils Gemini Live de J.A.R.V.I.S. (FunctionDeclarations).
Ce module est importé une seule fois par routers/voice.py lors de l'établissement de la session.
Catalogue unifié en anglais (snake_case) avec clauses d'exclusion strictes anti-confusion vocale (ASR).
"""

from google.genai import types


def get_tools_list() -> list[types.Tool]:
    """Retourne la liste complète des 38 outils déclarés pour Gemini Live."""
    return [
        types.Tool(
            function_declarations=[
                # ─── 1. stop_current_action ───────────────────────────────────────────
                types.FunctionDeclaration(
                    name="stop_current_action",
                    description=(
                        "ARRÊTE IMMÉDIATEMENT toute action, recherche, agent Antigravity CLI ou navigation web en cours d'exécution. "
                        "Cette action interrompt physiquement l'agent Antigravity CLI sur le VPS ou le navigateur en arrière-plan et remet l'état à l'arrêt. "
                        "À UTILISER QUAND : Pierre demande d'arrêter, de faire une pause, de stopper ou d'annuler immédiatement ce qui tourne "
                        "('arrête', 'stop', 'annule', 'interromps', 'tais-toi et arrête', 'laisse tomber'). "
                        "NE JAMAIS UTILISER QUAND : Pierre souhaite simplement réorienter ou donner une directive à une tâche active qui doit continuer "
                        "(utiliser 'guide_active_task') ou demander des nouvelles de l'avancement (utiliser 'get_active_task_status')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "reason": types.Schema(
                                type="STRING",
                                description="Le motif ou la consigne d'arrêt exprimée par Pierre"
                            )
                        }
                    )
                ),

                # ─── 2. guide_active_task ─────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="guide_active_task",
                    description=(
                        "Transmet en direct une consigne d'orientation, d'adaptation ou de correction à la tâche active ou à l'agent Antigravity CLI sans interrompre la session. "
                        "À UTILISER QUAND : Une tâche de fond est en cours et Pierre souhaite en direct affiner un axe, corriger un paramètre ou réorienter l'analyse. "
                        "NE JAMAIS UTILISER QUAND : Aucune tâche n'est active, quand Pierre veut stopper la tâche (utiliser 'stop_current_action'), "
                        "ou quand il s'agit d'une nouvelle demande indépendante (utiliser 'ask_deep_reasoning' ou 'launch_deep_research')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "directive": types.Schema(
                                type="STRING",
                                description="La consigne ou adaptation demandée par l'utilisateur pour l'action en cours"
                            )
                        },
                        required=["directive"]
                    )
                ),

                # ─── 3. ask_deep_reasoning ────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="ask_deep_reasoning",
                    description=(
                        "MOTEUR MULTI-AGENTS ANTIGRAVITY CLI VPS (Tiers 1, 2, 3) : "
                        "Mobilise le pipeline d'agents autonomes sur le VPS (Prospecteur, Analyste critique, Synthèse & Artefact, Ingénierie) "
                        "pour les réflexions complexes, analyses de code, audits techniques, benchmarks ou décisions architecturales. "
                        "À UTILISER QUAND : Pierre pose une problématique complexe nécessitant réflexion, architecture, ingénierie de code ou arbitrage logique. "
                        "Si Pierre n'a pas encore validé, confirmed_by_user=False. S'il a déjà validé, confirmed_by_user=True. "
                        "NE JAMAIS UTILISER QUAND : Une simple réponse factuelle rapide ou consultation d'actualité suffit (utiliser 'search_web'), "
                        "ni pour interagir avec une page web (utiliser 'run_browser_task'), "
                        "ni pour une prospection sectorielle de masse de 5-10 min avec extraction d'entreprises (utiliser 'launch_deep_research')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "question": types.Schema(
                                type="STRING",
                                description="La problématique, sujet d'investigation, question stratégique, audit ou mission à traiter en profondeur par Antigravity CLI sur le VPS"
                            ),
                            "model": types.Schema(
                                type="STRING",
                                description=(
                                    "Modèle Antigravity CLI selon la complexité : "
                                    "'gemini-3.1-pro-high' (par défaut, pour synthèse et analyse de référence), "
                                    "'claude-3-opus' ou 'claude-3-7-sonnet' (pour analyse conceptuelle pointue), "
                                    "ou 'gemini-3.8-flash-high' (pour investigation rapide)."
                                )
                            ),
                            "intensite_reflexion": types.Schema(
                                type="STRING",
                                description=(
                                    "Intensité cognitive et palier de réflexion Antigravity CLI souhaité : "
                                    "'rapide' (Tier 1 : Gemini 3.8 Flash low, 1-3s, économique, tâches simples), "
                                    "'tactique' (Tier 2 : Gemini 3.8 Flash high, quelques secondes, analyse logique poussée et préservation de quota), "
                                    "'approfondie' (Tier 3 : Gemini 3.1 Pro high, analyse de fond, haute ingénierie)."
                                ),
                                enum=["rapide", "tactique", "approfondie"]
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta proposition. Par défaut False."
                            ),
                        },
                        required=["question"]
                    )
                ),

                # ─── 4. launch_deep_research ──────────────────────────────────────────
                types.FunctionDeclaration(
                    name="launch_deep_research",
                    description=(
                        "MOTEUR UNIVERSEL DEEP RESEARCH MAP-REDUCE (5 à 10 minutes) : "
                        "Déclenche une recherche de fond exhaustive, multi-sources et autonome sur un écosystème ou secteur "
                        "(cartographie d'entreprises, benchmarks mondiaux, prospection de stages). "
                        "Déploie 3 ouvriers prospecteurs parallèles sur le VPS avec Quality Gate strict, "
                        "génère un rapport complet dans /artifacts/ et l'expédie par e-mail et notifications. "
                        "À UTILISER QUAND : Pierre demande expressément une étude de fond, prospection d'entreprises, cartographie sectorielle ou analyse de marché approfondie. "
                        "NE JAMAIS UTILISER QUAND : La réponse doit être immédiate ou porte sur un fait simple (utiliser 'search_web'), "
                        "ni pour du raisonnement de code ou d'architecture (utiliser 'ask_deep_reasoning'), "
                        "ni pour interagir avec un site web en direct (utiliser 'run_browser_task')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "consigne_utilisateur": types.Schema(
                                type="STRING",
                                description="La consigne brute intégrale dictée par Pierre, sans filtrage ni altération."
                            ),
                            "envoyer_email": types.Schema(
                                type="BOOLEAN",
                                description="True si la consigne orale mentionne un envoi par mail/courriel/rapport écrit (défaut False)."
                            ),
                            "destinataire_email": types.Schema(
                                type="STRING",
                                description="E-mail de destination si précisé oralement, sinon repli automatique sur le profil utilisateur."
                            ),
                        },
                        required=["consigne_utilisateur"]
                    )
                ),

                # ─── 5. search_web ────────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="search_web",
                    description=(
                        "Recherche textuelle rapide sur Internet via DuckDuckGo pour obtenir des informations factuelles récentes, définitions, cours ou liens en moins de 2 secondes. "
                        "À UTILISER QUAND : Pierre pose une question factuelle directe (météo, score sportif, date, définition, fait récent, prix indicatif) nécessitant une réponse immédiate. "
                        "NE JAMAIS UTILISER QUAND : Une interaction complexe est requise sur un site (clics, panier, formulaires : utiliser 'run_browser_task'), "
                        "ni pour un raisonnement technique approfondi (utiliser 'ask_deep_reasoning'), "
                        "ni pour une étude sectorielle lourde de 5-10 minutes (utiliser 'launch_deep_research')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="La requête de recherche web précise"
                            )
                        },
                        required=["query"]
                    )
                ),

                # ─── 6. run_browser_task ──────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="run_browser_task",
                    description=(
                        "Pilote un agent web autonome universel (Browser-Use) avec vision pour naviguer, explorer un site web, remplir des formulaires, comparer des offres en direct ou accomplir des missions multi-étapes. "
                        "À UTILISER QUAND : Une mission web dynamique requiert clics, interactions, navigation successive de page en page ou exploration visuelle d'un site. "
                        "NE JAMAIS UTILISER QUAND : Une recherche d'information textuelle simple suffit sans navigation complexe (utiliser 'search_web'), "
                        "ni pour une action ciblée sur une URL unique connue (utiliser 'interact_web_page'), "
                        "ni pour juste ouvrir Chrome à l'écran (utiliser 'open_user_browser')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "goal": types.Schema(
                                type="STRING",
                                description="L'objectif concret de navigation à accomplir sur le web"
                            ),
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL de départ si connue, sinon laisser vide"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta demande expliquant le besoin et le coût estimé. Par défaut False."
                            ),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution de la navigation : 'vps_headless' (fond de tâche cloud discret sur le VPS) ou 'local_chrome_cdp' (interactif, directement sur le Google Chrome physique ouvert du PC de Pierre via CDP). Si le PC est hors-ligne, toujours 'vps_headless'. Si le PC est en ligne et que Pierre n'a pas spécifié, demande-lui s'il préfère agir sur son Chrome à l'écran ou discrètement en tâche de fond."
                            ),
                        },
                        required=["goal"]
                    )
                ),

                # ─── 7. open_user_browser ─────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="open_user_browser",
                    description=(
                        "Ouvre Google Chrome directement à l'écran physique du PC de Pierre avec son profil connecté pour afficher un site ou une page spécifique. "
                        "À UTILISER QUAND : Pierre demande expressément de voir une page ou un site web s'ouvrir à l'écran de son ordinateur Windows. "
                        "NE JAMAIS UTILISER QUAND : Il faut seulement proposer un lien cliquable sur le smartphone / HUD mobile (utiliser 'set_browser_link'), "
                        "ni pour une navigation autonome en tâche de fond (utiliser 'run_browser_task')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL à ouvrir dans le navigateur à l'écran"
                            ),
                            "reason": types.Schema(
                                type="STRING",
                                description="La raison de l'ouverture"
                            ),
                        }
                    )
                ),

                # ─── 8. set_browser_link ──────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="set_browser_link",
                    description=(
                        "Définit ou met à jour le lien web interactif affiché dans le HUD mobile pour que Pierre puisse cliquer sur 'OUVRIR LE LIEN' sur son smartphone (billet de train, article, hôtel, réservation). "
                        "À UTILISER QUAND : Tu souhaites mettre à disposition de Pierre un lien direct précis sur son interface mobile. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande d'ouvrir la fenêtre Chrome à l'écran de son PC de bureau (utiliser 'open_user_browser')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL directe précise de la page ou de la réservation"
                            ),
                            "title": types.Schema(
                                type="STRING",
                                description="Le libellé court du lien (ex: 'Train Paris - Lyon 14h08', 'Vol Air France')"
                            ),
                        },
                        required=["url"]
                    )
                ),

                # ─── 9. save_memory (Fusion remember_user_fact + memoriser_information) ─
                types.FunctionDeclaration(
                    name="save_memory",
                    description=(
                        "Enregistre durablement un fait, une habitude, une préférence personnelle ou une information clé concernant Pierre dans la mémoire persistante vectorielle (Qdrant + SQLite). "
                        "À UTILISER QUAND : Pierre te demande de retenir ou mémoriser une information le concernant "
                        "('retiens que', 'souviens-toi que', 'note que', 'mémorise', 'ma couleur préférée est...', 'mon projet actuel est...'). "
                        "NE JAMAIS UTILISER QUAND : Pierre cherche à retrouver un souvenir existant (utiliser 'recall_user_memories'), "
                        "ni pour créer une note structurée dans son Notion (utiliser 'save_notion_entry'), "
                        "ni pour programmer un rappel avec horaire (utiliser 'create_push_reminder')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "fact": types.Schema(
                                type="STRING",
                                description="Le fait, la préférence, l'habitude ou l'information à mémoriser durablement"
                            ),
                            "category": types.Schema(
                                type="STRING",
                                description="Catégorie : 'preference', 'fact', 'habit', 'project', 'contact', 'general'"
                            ),
                            "key": types.Schema(
                                type="STRING",
                                description="Clé ou titre court optionnel pour indexer l'information (ex: 'couleur_preferee', 'projet_actuel')"
                            ),
                        },
                        required=["fact"]
                    )
                ),

                # ─── 10. recall_user_memories ─────────────────────────────────────────
                types.FunctionDeclaration(
                    name="recall_user_memories",
                    description=(
                        "Recherche sémantiquement dans la mémoire persistante long-terme des faits, préférences ou informations passées sur Pierre. "
                        "À UTILISER QUAND : Pierre demande ce que tu sais sur lui ou sur un sujet personnel "
                        "('qu'est-ce que tu sais sur mes goûts ?', 'tu te souviens de... ?', 'quel est mon projet ?'), "
                        "ou quand tu as besoin de vérifier ses préférences passées. "
                        "NE JAMAIS UTILISER QUAND : Pierre te demande d'enregistrer une nouvelle information (utiliser 'save_memory')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="Mots-clés de recherche dans la mémoire"
                            )
                        },
                        required=["query"]
                    )
                ),

                # ─── 11. get_system_status ────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="get_system_status",
                    description=(
                        "Consulte en direct la télémétrie matérielle de l'ordinateur et du serveur (CPU, RAM, disques, batterie). "
                        "À UTILISER QUAND : Pierre demande l'état de son PC, la charge du processeur, la mémoire vive libre ou l'autonomie restante. "
                        "NE JAMAIS UTILISER QUAND : Il s'agit d'analyser les logs de la console ou les erreurs logicielles du serveur (utiliser 'check_console_errors'), "
                        "ni pour démarrer une application (utiliser 'launch_application')."
                    ),
                    parameters=types.Schema(type="OBJECT", properties={})
                ),

                # ─── 12. launch_application ───────────────────────────────────────────
                types.FunctionDeclaration(
                    name="launch_application",
                    description=(
                        "Lance une application locale sur le PC Windows de Pierre (Calculatrice, Bloc-notes, VS Code, Explorateur, Chrome, VLC, Terminal). "
                        "À UTILISER QUAND : Pierre demande d'ouvrir un logiciel bureautique sur son poste de travail. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande de la musique (utiliser 'control_spotify'), "
                        "un film ou une série sur Stremio (utiliser 'play_video_stremio'), "
                        "ou une page web dans Chrome (utiliser 'open_user_browser')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "app_name": types.Schema(
                                type="STRING",
                                description="Nom de l'application (calculatrice, bloc-notes, vscode, explorateur, chrome, vlc, terminal)"
                            )
                        },
                        required=["app_name"]
                    )
                ),

                # ─── 13. control_spotify ─────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="control_spotify",
                    description=(
                        "Contrôle complet du lecteur Spotify Connect via la Web API Spotify officielle "
                        "(lecture, pause, suivant, précédent, volume, aléatoire, répétition, recherche de titre/artiste/album/playlist/épisode, "
                        "file d'attente, transfert d'appareil, like, playlists). "
                        "À UTILISER QUAND : Pierre demande d'écouter, de contrôler ou de régler de la musique ou un podcast sur Spotify. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande un film, une vidéo ou une série télévisée (utiliser 'play_video_stremio'), "
                        "ni pour lancer une application bureautique (utiliser 'launch_application'). "
                        "IMPORTANT : si Spotify n'est pas connecté (no_tokens), renvoyer le lien d'authentification /api/media/spotify/login."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description=(
                                    "Action à effectuer. Valeurs : "
                                    "'play' (lance ou relance la lecture, avec query optionnel), "
                                    "'pause' (met en pause), "
                                    "'resume' (reprend la lecture), "
                                    "'next' (piste suivante), "
                                    "'previous' (piste précédente), "
                                    "'seek' (position_ms requis), "
                                    "'volume' (volume absolu 0-100 ou delta relatif), "
                                    "'shuffle' (state='true'/'false'), "
                                    "'repeat' (state='off'/'track'/'context'), "
                                    "'queue_add' (ajouter un titre à la file), "
                                    "'get_queue' (voir la file), "
                                    "'list_devices' (appareils disponibles), "
                                    "'transfer' (transférer sur device), "
                                    "'like' (liker le morceau en cours), "
                                    "'unlike' (retirer le like), "
                                    "'add_to_playlist' (playlist_name requis), "
                                    "'create_playlist' (query=nom), "
                                    "'follow_artist' (query=nom artiste), "
                                    "'save_album' (query=nom album), "
                                    "'now_playing' (état courant), "
                                    "'search' (recherche sans lecture), "
                                    "'top' (top tracks/artists), "
                                    "'recent' (écoutes récentes)"
                                )
                            ),
                            "query": types.Schema(
                                type="STRING",
                                description="Titre du morceau, nom de l'artiste, de l'album, de la playlist ou du podcast recherché"
                            ),
                            "search_type": types.Schema(
                                type="STRING",
                                description="Type de contenu : 'track' (défaut), 'artist', 'album', 'playlist', 'episode', 'liked'"
                            ),
                            "device": types.Schema(
                                type="STRING",
                                description="Appareil cible (ex: 'pc', 'téléphone', 'enceinte', nom exact Spotify Connect). Optionnel."
                            ),
                            "volume": types.Schema(
                                type="INTEGER",
                                description="Volume absolu 0-100 pour l'action 'volume'"
                            ),
                            "volume_delta": types.Schema(
                                type="INTEGER",
                                description="Delta relatif de volume (ex: +10, -20) pour l'action 'volume'"
                            ),
                            "position_ms": types.Schema(
                                type="INTEGER",
                                description="Position de lecture en millisecondes pour l'action 'seek'"
                            ),
                            "state": types.Schema(
                                type="STRING",
                                description="Valeur complémentaire : 'true'/'false' pour shuffle, 'off'/'track'/'context' pour repeat, 'short_term'/'medium_term'/'long_term' pour top"
                            ),
                            "playlist_name": types.Schema(
                                type="STRING",
                                description="Nom de la playlist pour les actions 'add_to_playlist' et 'create_playlist'"
                            ),
                        },
                        required=["action"]
                    )
                ),

                # ─── 14. play_video_stremio ───────────────────────────────────────────
                types.FunctionDeclaration(
                    name="play_video_stremio",
                    description=(
                        "Recherche et lance un film ou un épisode de série sur Stremio localement en sélectionnant automatiquement le meilleur flux 1080p fluide. "
                        "À UTILISER QUAND : Pierre demande de regarder un film ou une série vidéo. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande un morceau de musique (utiliser 'control_spotify'), "
                        "ni pour une simple vidéo YouTube dans le navigateur (utiliser 'open_user_browser')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "title": types.Schema(
                                type="STRING",
                                description="Titre du film ou de la série (ex: 'Inception', 'Breaking Bad', 'Avatar', 'The Office')"
                            ),
                            "content_type": types.Schema(
                                type="STRING",
                                description="Type de contenu : 'movie' pour un film (défaut), 'series' pour une série TV"
                            ),
                        },
                        required=["title"]
                    )
                ),

                # ─── 15. send_email ───────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="send_email",
                    description=(
                        "Rédige et expédie un courriel via SMTP à Pierre Cassagnettes (format officiel exécutif Stark Industries) "
                        "ou à un destinataire externe, avec gestion de pièces jointes (documents, rapports, PDF, tableurs). "
                        "À UTILISER QUAND : Pierre demande d'envoyer un mail directement, de transmettre un fichier ou de s'auto-envoyer un compte-rendu. "
                        "NE JAMAIS UTILISER QUAND : Il faut analyser un fil de discussion complexe reçu et préparer un projet de réponse argumenté avant envoi "
                        "(utiliser 'draft_email_response'), ni pour consulter les emails entrants (utiliser 'read_emails')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "subject": types.Schema(
                                type="STRING",
                                description="L'objet de l'e-mail"
                            ),
                            "body": types.Schema(
                                type="STRING",
                                description="Le contenu du message rédigé par l'agent de A à Z"
                            ),
                            "to_email": types.Schema(
                                type="STRING",
                                description="Adresse destinataire. Par défaut: pierrecassagnettes@gmail.com"
                            ),
                            "attachments": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="Liste des fichiers ou documents à joindre en pièce jointe (ex: ['rapport.pdf'], ['tableur.xlsx'], ou chemin complet)."
                            ),
                            "include_latest_screenshot": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True pour joindre automatiquement une capture d'écran du système ou du navigateur"
                            ),
                        },
                        required=["subject"]
                    )
                ),

                # ─── 16. read_emails ──────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="read_emails",
                    description=(
                        "Consulte et résume les e-mails récents reçus dans la boîte Gmail de Pierre via IMAP, avec filtres par mot-clé, expéditeur ou non lus. "
                        "À UTILISER QUAND : Pierre demande s'il a reçu de nouveaux messages ou souhaite consulter ses e-mails. "
                        "NE JAMAIS UTILISER QUAND : Il faut envoyer un nouveau courriel (utiliser 'send_email'), "
                        "ni pour décortiquer des pièces jointes et concevoir un brouillon de réponse (utiliser 'draft_email_response')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "count": types.Schema(
                                type="INTEGER",
                                description="Nombre d'e-mails récents à consulter (par défaut: 3 à 5)"
                            ),
                            "query": types.Schema(
                                type="STRING",
                                description="Mot-clé ou expéditeur optionnel pour filtrer la recherche"
                            ),
                            "unread_only": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True pour ne récupérer que les e-mails non lus"
                            ),
                        }
                    )
                ),

                # ─── 17. check_console_errors ─────────────────────────────────────────
                types.FunctionDeclaration(
                    name="check_console_errors",
                    description=(
                        "Lit, inspecte et diagnostique les erreurs récentes des logs de la console serveur ou réinitialise le journal d'erreurs. "
                        "À UTILISER QUAND : Pierre signale une anomalie ou demande un diagnostic rapide de l'état des logs et erreurs du serveur, ou demande d'effacer le journal. "
                        "NE JAMAIS UTILISER QUAND : Une panne nécessite une modification et un patch autonome du code source par un agent SRE (utiliser 'system_self_healing'), "
                        "ni pour la télémétrie matérielle CPU/RAM (utiliser 'get_system_status')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description="Action souhaitée : 'diagnose' (analyser les erreurs récentes), 'clear' (réinitialiser le journal d'erreurs)"
                            )
                        }
                    )
                ),

                # ─── 18. interact_web_page ────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="interact_web_page",
                    description=(
                        "Interagit de manière unitaire et chirurgicale avec une page web spécifique (découverte DOM, clic sur un sélecteur précis, remplissage d'un champ connu, défilement). "
                        "À UTILISER QUAND : Tu as une URL connue et dois effectuer une manipulation précise (cliquer sur un bouton ciblé ou remplir un champ précis). "
                        "NE JAMAIS UTILISER QUAND : Il s'agit d'une mission de navigation globale multi-étapes sans sélecteurs précis connus (utiliser 'run_browser_task'), "
                        "ni pour préparer un panier d'achat e-commerce (utiliser 'prepare_web_cart_or_checkout')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL de la page web avec laquelle interagir"
                            ),
                            "action": types.Schema(
                                type="STRING",
                                description="Type d'action : 'read' (lecture et découverte des champs/boutons), 'click' (clic sur sélecteur), 'fill' (saisie de texte), 'scroll' (défilement)"
                            ),
                            "selector": types.Schema(
                                type="STRING",
                                description="Sélecteur CSS ou texte de l'élément cible pour le clic ou la saisie"
                            ),
                            "text_to_fill": types.Schema(
                                type="STRING",
                                description="Texte à saisir dans le champ si l'action est 'fill'"
                            ),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution : 'vps_headless' (Playwright headless cloud sur le VPS) ou 'local_chrome_cdp' (interactif, sur le Chrome physique du PC de Pierre via CDP)."
                            ),
                        },
                        required=["url"]
                    )
                ),

                # ─── 19. prepare_web_cart_or_checkout ─────────────────────────────────
                types.FunctionDeclaration(
                    name="prepare_web_cart_or_checkout",
                    description=(
                        "Recherche un produit ou service, l'ajoute au panier sur un site marchand (Amazon, Fnac, SNCF, etc.), navigue jusqu'à la commande et préremplit les coordonnées de Pierre, "
                        "puis S'ARRÊTE STRICTEMENT AVANT LE PAIEMENT (aucun prélèvement automatique, règle inviolable). "
                        "À UTILISER QUAND : Pierre demande de commander ou d'acheter un produit en ligne en préparant son panier jusqu'au règlement final. "
                        "NE JAMAIS UTILISER QUAND : Il s'agit d'une simple navigation exploratoire sans intention d'achat (utiliser 'run_browser_task' ou 'search_web'), "
                        "et ne jamais tenter de valider le paiement final."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "product_or_service": types.Schema(
                                type="STRING",
                                description="Le produit, livre, matériel ou service précis à ajouter au panier"
                            ),
                            "merchant_url": types.Schema(
                                type="STRING",
                                description="L'URL du site marchand ou boutique en ligne (optionnel, recherche auto si vide)"
                            ),
                            "open_when_ready": types.Schema(
                                type="BOOLEAN",
                                description="Ouvrir automatiquement Chrome à l'écran dès que le panier et le formulaire sont prêts (True par défaut)"
                            ),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution du panier/achat : 'local_chrome_cdp' (sur le navigateur Chrome physique du PC de Pierre via CDP) ou 'vps_headless' (fond de tâche cloud sur le VPS)."
                            ),
                        },
                        required=["product_or_service"]
                    )
                ),

                # ─── 20. download_file ────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="download_file",
                    description=(
                        "Télécharge un fichier, document ou média depuis une URL directe sur l'ordinateur de Pierre après avoir obtenu son accord oral explicite préalable. "
                        "À UTILISER QUAND : Tu disposes d'une URL de téléchargement direct et Pierre a validé oralement le rapatriement du fichier. "
                        "NE JAMAIS UTILISER QUAND : Il s'agit de rechercher un livre numérique par titre/auteur (utiliser 'search_and_download_ebook'), "
                        "ni sans l'accord oral préalable explicite de Pierre (garde-fous système)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(
                                type="STRING",
                                description="L'URL directe de téléchargement du fichier"
                            ),
                            "filename": types.Schema(
                                type="STRING",
                                description="Nom de fichier optionnel sous lequel enregistrer le document"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après accord oral explicite de Pierre. Par défaut False."
                            ),
                            "file_type": types.Schema(
                                type="STRING",
                                description="Type de fichier : 'general' pour un document, 'ebook' pour un livre numérique"
                            ),
                        },
                        required=["url"]
                    )
                ),

                # ─── 21. send_to_ereader (Fusion send_to_ereader + send_page_to_kindle + send_file_to_kindle) ─
                types.FunctionDeclaration(
                    name="send_to_ereader",
                    description=(
                        "Achemine un contenu (livre numérique EPUB/PDF, document local ou article web épuré) vers la liseuse de Pierre (Kindle, Kobo) "
                        "via USB, Amazon Send-to-Kindle Web ou e-mail. "
                        "À UTILISER QUAND : Pierre demande d'envoyer un ebook téléchargé, un document local ou un article web sur sa liseuse ou Kindle. "
                        "NE JAMAIS UTILISER QUAND : Le livre doit d'abord être recherché et téléchargé sur Internet (utiliser 'search_and_download_ebook'), "
                        "ni pour produire une fiche de lecture analytique (utiliser 'generate_book_summary')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "source": types.Schema(
                                type="STRING",
                                description="Chemin local du fichier ebook/document (ex: 'livre.epub') OU URL directe de l'article web à envoyer"
                            ),
                            "source_type": types.Schema(
                                type="STRING",
                                enum=["file", "url"],
                                description="Type de source : 'file' pour un fichier local ou 'url' pour une page web. Auto-détecté si omis."
                            ),
                            "method": types.Schema(
                                type="STRING",
                                enum=["auto", "usb", "kindle_web", "email"],
                                description="Méthode de transfert : 'auto' (USB en priorité puis e-mail), 'usb' (liseuse branchée), 'kindle_web' (Amazon Send to Kindle Web), ou 'email'."
                            ),
                            "title": types.Schema(
                                type="STRING",
                                description="Titre optionnel de l'article ou de l'ebook pour la bibliothèque de la liseuse"
                            ),
                            "ereader_email": types.Schema(
                                type="STRING",
                                description="Adresse e-mail spécifique de la liseuse (ex: pierre@kindle.com) si connue"
                            ),
                        },
                        required=["source"]
                    )
                ),

                # ─── 22. search_and_download_ebook ────────────────────────────────────
                types.FunctionDeclaration(
                    name="search_and_download_ebook",
                    description=(
                        "Mission complète e-book : Recherche un livre numérique sur Internet par titre/auteur, demande l'accord oral de Pierre, "
                        "le télécharge puis l'achemine optionnellement vers sa liseuse (Kindle, Kobo) via USB ou e-mail. "
                        "À UTILISER QUAND : Pierre demande de lui trouver et télécharger un livre numérique ou roman. "
                        "NE JAMAIS UTILISER QUAND : Le fichier du livre est déjà téléchargé sur le disque (utiliser 'send_to_ereader'), "
                        "ni pour télécharger un document non-ebook depuis une URL connue (utiliser 'download_file')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="Le titre ou l'auteur de l'ebook recherché (ex: 'L'art de la guerre', '1984 George Orwell')"
                            ),
                            "source_url": types.Schema(
                                type="STRING",
                                description="URL directe du site ou de la page de téléchargement si spécifiée par Pierre"
                            ),
                            "confirmed_by_user": types.Schema(
                                type="BOOLEAN",
                                description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral. Par défaut False."
                            ),
                            "send_to_reader": types.Schema(
                                type="BOOLEAN",
                                description="Transférer automatiquement sur la liseuse une fois téléchargé (True par défaut)"
                            ),
                            "ereader_email": types.Schema(
                                type="STRING",
                                description="Adresse e-mail spécifique de la liseuse si renseignée"
                            ),
                            "lang": types.Schema(
                                type="STRING",
                                description="Langue demandée pour le livre : 'en' (anglais) ou 'fr' (français). Détecter automatiquement selon la demande de Pierre."
                            ),
                        },
                        required=["query"]
                    )
                ),

                # ─── 23. list_chrome_extensions ───────────────────────────────────────
                types.FunctionDeclaration(
                    name="list_chrome_extensions",
                    description=(
                        "Liste les extensions Google Chrome installées dans le profil de Pierre pour vérifier leur présence et leur état (ex: Send to Kindle, Wanteeed). "
                        "À UTILISER QUAND : Tu dois diagnostiquer la disponibilité d'une extension de navigateur spécifique. "
                        "NE JAMAIS UTILISER QUAND : Pierre souhaite simplement ouvrir ou naviguer sur un site web (utiliser 'open_user_browser' ou 'search_web')."
                    ),
                    parameters=types.Schema(type="OBJECT", properties={})
                ),

                # ─── 24. execute_external_action (was executer_action_externe) ────────
                types.FunctionDeclaration(
                    name="execute_external_action",
                    description=(
                        "Déclenche un workflow d'automatisation générique sur n8n pour des intégrations tierces personnalisées (webhooks, domotique, Gotify, synchronisations). "
                        "À UTILISER QUAND : Une action spécifique nécessite un webhook n8n dédié qui ne possède pas son propre outil spécialisé. "
                        "NE JAMAIS UTILISER QUAND : L'action dispose d'un outil dédié (pour Notion utiliser 'save_notion_entry', "
                        "pour l'agenda utiliser 'manage_calendar_event', pour un rappel utiliser 'create_push_reminder')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action_name": types.Schema(
                                type="STRING",
                                description="Nom ou identifiant de l'action / webhook n8n à déclencher (ex: 'gotify-notify', 'domotique-scene', 'custom-sync')."
                            ),
                            "parametres": types.Schema(
                                type="OBJECT",
                                description="Paramètres libres optionnels extraits de la conversation vocale et transmis au workflow."
                            ),
                        },
                        required=["action_name"]
                    )
                ),

                # ─── 25. generate_spreadsheet (was generer_fichier_tableur) ───────────
                types.FunctionDeclaration(
                    name="generate_spreadsheet",
                    description=(
                        "Génère un classeur tableur Excel (.xlsx) structuré, avec colonnes, données et formules dynamiques optionnelles "
                        "via l'agent 'spreadsheet_modeler'. Le fichier est déposé dans /downloads/. "
                        "À UTILISER QUAND : Pierre demande de créer un tableur, un budget, un comparatif chiffré ou d'exporter des données tabulaires en format Excel. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande une présentation avec diapositives visuelles (utiliser 'generate_presentation'), "
                        "ni pour une note de synthèse Notion (utiliser 'save_notion_entry')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "nom_fichier": types.Schema(
                                type="STRING",
                                description="Nom du fichier Excel à créer (ex: 'budget_2026.xlsx', 'benchmark_modeles.xlsx')"
                            ),
                            "colonnes": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="Liste des noms des colonnes du tableau"
                            ),
                            "lignes": types.Schema(
                                type="ARRAY",
                                items=types.Schema(
                                    type="ARRAY",
                                    items=types.Schema(type="STRING"),
                                    description="Une ligne de données contenant les valeurs de chaque cellule"
                                ),
                                description="Liste des lignes du tableau"
                            ),
                            "description": types.Schema(
                                type="STRING",
                                description="Description optionnelle du contenu ou contexte du tableau"
                            ),
                            "modele_avance_agent": types.Schema(
                                type="BOOLEAN",
                                description="Si True (par défaut), mobilise proactivement l'agent Antigravity 'spreadsheet_modeler' (Système 2) pour injecter formules dynamiques (XLOOKUP, SUMIFS), ratios et mise en forme corporate Stark."
                            ),
                        },
                        required=["nom_fichier", "colonnes", "lignes"]
                    )
                ),

                # ─── 26. generate_presentation (was generer_presentation) ─────────────
                types.FunctionDeclaration(
                    name="generate_presentation",
                    description=(
                        "Conçoit une présentation Google Slides sur-mesure dont le nombre de diapositives, la structure narrative, le contenu et le style découlent fidèlement de la demande. "
                        "À UTILISER QUAND l'utilisateur veut une présentation. Recopie sa demande complète dans `consignes`. NE PAS inventer nb_slides s'il ne l'a pas précisé. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande un fichier tableur Excel (utiliser 'generate_spreadsheet'), "
                        "ni pour modifier une présentation existante (utiliser 'modify_presentation')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "sujet": types.Schema(
                                type="STRING",
                                description="Le sujet ou thème principal de la présentation (ex: 'Histoire de Rome', 'Architecture Microservices', 'Bitcoin')"
                            ),
                            "consignes": types.Schema(
                                type="STRING",
                                description="Recopie mot pour mot et fidèlement tout ce que l'utilisateur veut voir dans la présentation (consigne brute intégrale)."
                            ),
                            "nb_slides": types.Schema(
                                type="INTEGER",
                                description="Nombre exact de diapositives demandé par l'utilisateur si spécifié. Laisser null/omettre si non précisé (NE PAS inventer un chiffre)."
                            ),
                            "public": types.Schema(
                                type="STRING",
                                description="Public cible de la présentation si mentionné (ex: 'investisseurs', 'étudiants', 'direction technique', 'grand public')."
                            ),
                            "ton": types.Schema(
                                type="STRING",
                                description="Ton et style souhaités : 'corporate', 'créatif', 'sobre', 'pitch', 'stark', 'dark', 'gold', 'cyber'."
                            ),
                            "langue": types.Schema(
                                type="STRING",
                                description="Langue de rédaction de la présentation (par défaut 'fr')."
                            ),
                            "recherche_approfondie": types.Schema(
                                type="BOOLEAN",
                                description="Si True, active une recherche web/documentaire approfondie avant d'établir le plan."
                            ),
                            "titre": types.Schema(
                                type="STRING",
                                description="Titre optionnel de la présentation si spécifié explicitement."
                            ),
                        },
                        required=["sujet", "consignes"]
                    )
                ),

                # ─── 27. modify_presentation ──────────────────────────────────────────
                types.FunctionDeclaration(
                    name="modify_presentation",
                    description=(
                        "Modifie une présentation Google Slides existante selon une instruction vocale ou textuelle précise "
                        "(ex: 'ajoute une slide sur les risques', 'supprime la slide 3', 'change le titre de la 2'). "
                        "À UTILISER QUAND : Pierre souhaite modifier, enrichir ou réorganiser une présentation Google Slides déjà générée. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande de créer une nouvelle présentation à partir de zéro (utiliser 'generate_presentation')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "instruction": types.Schema(
                                type="STRING",
                                description="Instruction précise de modification (ex: 'ajoute une slide sur les risques', 'supprime la slide 3', 'change le titre de la 2')."
                            ),
                            "presentation_id": types.Schema(
                                type="STRING",
                                description="Identifiant Google Slides de la présentation ou 'last' pour cibler la dernière présentation créée (défaut 'last')."
                            ),
                        },
                        required=["instruction"]
                    )
                ),

                # ─── 27. get_active_task_status ───────────────────────────────────────
                types.FunctionDeclaration(
                    name="get_active_task_status",
                    description=(
                        "Consulte en direct l'avancement, l'étape courante et les détails d'une tâche de fond en cours "
                        "(génération de slides, prospection Deep Research, agent Antigravity, navigation). "
                        "À UTILISER QUAND : Pierre te demande où en est son travail ou ce que tu fais ('qu'est-ce que tu fais ?', 'où en est ma présentation ?'). "
                        "NE JAMAIS UTILISER QUAND : Pierre veut arrêter la tâche (utiliser 'stop_current_action'), "
                        "ni pour modifier son orientation en direct (utiliser 'guide_active_task')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "task_id": types.Schema(
                                type="STRING",
                                description="Identifiant optionnel d'une tâche spécifique à vérifier"
                            ),
                        }
                    )
                ),

                # ─── 28. save_notion_entry (was notion_enregistrer) ───────────────────
                types.FunctionDeclaration(
                    name="save_notion_entry",
                    description=(
                        "Enregistre une entrée structurée (note rapide, item de todo-list, fiche de veille, compte-rendu) "
                        "dans les bases et pages Notion de Pierre via n8n. "
                        "À UTILISER QUAND : Pierre demande explicitement d'ajouter une note, une tâche ou une fiche dans son Notion. "
                        "NE JAMAIS UTILISER QUAND : Il s'agit d'une préférence personnelle de dialogue à retenir pour Jarvis (utiliser 'save_memory'), "
                        "ni pour programmer un rappel avec alerte horaire sur son smartphone (utiliser 'create_push_reminder')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "type_entree": types.Schema(
                                type="STRING",
                                description="Type d'entrée Notion : 'note' (note rapide), 'todo' (tâche to-do list), 'veille' (fiche de veille/techno), 'projet' (fiche projet)"
                            ),
                            "titre": types.Schema(
                                type="STRING",
                                description="Titre de la note ou intitulé de la tâche"
                            ),
                            "contenu": types.Schema(
                                type="STRING",
                                description="Contenu textuel détaillé, description ou étapes"
                            ),
                            "tags": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="Liste d'étiquettes ou tags associés (ex: ['IA', 'Urgent', 'Jarvis'])"
                            ),
                        },
                        required=["type_entree", "titre", "contenu"]
                    )
                ),

                # ─── 29. manage_calendar_event (was agenda_gerer_evenement) ───────────
                types.FunctionDeclaration(
                    name="manage_calendar_event",
                    description=(
                        "Gère les événements sur l'agenda Google / Samsung Calendar de Pierre (créer, consulter, décaler, supprimer des rendez-vous). "
                        "À UTILISER QUAND : Pierre demande d'ajouter, vérifier ou modifier un rendez-vous dans son calendrier. "
                        "NE JAMAIS UTILISER QUAND : Il s'agit du briefing matinal (utiliser 'get_morning_briefing'), "
                        "ni d'un simple rappel push sans créneau d'agenda (utiliser 'create_push_reminder')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description="Action sur l'agenda : 'consulter' (voir les rendez-vous sans rien créer), 'creer' (ajouter un nouvel événement), 'decaler' (modifier horaire/date), 'supprimer' (annuler)"
                            ),
                            "titre": types.Schema(
                                type="STRING",
                                description="Titre ou intitulé du rendez-vous (requis uniquement pour créer, décaler ou supprimer)"
                            ),
                            "date_debut": types.Schema(
                                type="STRING",
                                description="Date et heure de début au format ISO ou clair (ex: '2026-09-28T14:30:00', 'demain 10h'). Requis pour créer ou décaler."
                            ),
                            "date_fin": types.Schema(
                                type="STRING",
                                description="Date et heure de fin optionnelle (ex: '2026-09-28T15:30:00')"
                            ),
                            "description": types.Schema(
                                type="STRING",
                                description="Description détaillée, lieu ou notes pour l'événement (optionnel)"
                            ),
                        },
                        required=["action"]
                    )
                ),

                # ─── 30. create_push_reminder (was creer_rappel_push) ─────────────────
                types.FunctionDeclaration(
                    name="create_push_reminder",
                    description=(
                        "Programme un rappel ou mémo vocal avec notification push immédiate ou différée sur le smartphone de Pierre via Telegram Stark Bot / Gotify. "
                        "À UTILISER QUAND : Pierre demande de lui rappeler quelque chose à une heure précise ou de lui envoyer un mémo sur son téléphone. "
                        "NE JAMAIS UTILISER QUAND : Il faut inscrire un événement officiel sur son agenda (utiliser 'manage_calendar_event'), "
                        "ni pour enregistrer une note durable sans rappel (utiliser 'save_notion_entry' ou 'save_memory')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "message": types.Schema(
                                type="STRING",
                                description="Message, texte du mémo ou rappel à notifier sur le smartphone"
                            ),
                            "echeance": types.Schema(
                                type="STRING",
                                description="Délai ou date/heure d'échéance du rappel (ex: 'maintenant' pour un envoi immédiat, 'dans 30 minutes', 'dans 2 heures', '18h30'). Par défaut 'maintenant'."
                            ),
                            "priorite": types.Schema(
                                type="STRING",
                                description="Niveau de priorité : 'basse', 'normale', 'haute', 'urgente'. Par défaut 'normale'."
                            ),
                        },
                        required=["message"]
                    )
                ),

                # ─── 31. get_morning_briefing (was demander_morning_briefing) ─────────
                types.FunctionDeclaration(
                    name="get_morning_briefing",
                    description=(
                        "Restitue la routine matinale Stark Industries compilée (météo à la position actuelle ou en mémoire, rendez-vous du jour en lecture seule, actualités des dernières 24 heures, e-mails urgents non lus). "
                        "Interroge en priorité la clé Redis 'jarvis:briefing:today' préparée dès 7h00 pour un retour instantané sans latence. "
                        "À UTILISER QUAND : Pierre demande son briefing du matin, le résumé du jour ou son récapitulatif quotidien. "
                        "NOTE IMPORTANTE : Cette action est en lecture seule absolue et n'ajoute JAMAIS aucun événement à l'agenda. "
                        "NE JAMAIS UTILISER QUAND : Pierre pose une question ciblée uniquement sur son agenda (utiliser 'manage_calendar_event') "
                        "ou souhaite juste lire ses emails (utiliser 'read_emails')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "force_refresh": types.Schema(
                                type="BOOLEAN",
                                description="Forcer la recompilation immédiate du briefing en temps réel au lieu d'utiliser le cache du jour (par défaut False)"
                            ),
                        }
                    )
                ),

                # ─── 32. search_train_routes (was rechercher_train) ───────────────────
                types.FunctionDeclaration(
                    name="search_train_routes",
                    description=(
                        "Recherche les horaires, enchaînements et tarifs ferroviaires (France SNCF et Suède SJ/Trafikverket), "
                        "avec optimisation multi-critères optionnelle par l'agent 'transport_optimizer'. "
                        "Si Pierre demande d'ouvrir ou réserver les billets dès la recherche, positionne 'reserver_automatiquement' à True. "
                        "À UTILISER QUAND : Pierre cherche un itinéraire ferroviaire, des horaires ou des correspondances en France ou en Suède. "
                        "NE JAMAIS UTILISER QUAND : Le trajet est déjà choisi et Pierre veut uniquement ouvrir la page de paiement sur son PC (utiliser 'open_train_booking'), "
                        "ni pour surveiller les retards d'un train en circulation (utiliser 'monitor_train')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "origine": types.Schema(
                                type="STRING",
                                description="Gare ou ville de départ (ex: 'Malmö Central', 'Stockholm', 'Paris', 'Lyon')"
                            ),
                            "destination": types.Schema(
                                type="STRING",
                                description="Gare ou région d'arrivée (ex: 'Kiruna', 'Abisko', 'Nord de la Suède', 'Stockholm Central', 'Marseille')"
                            ),
                            "date_depart": types.Schema(
                                type="STRING",
                                description="Date du voyage au format AAAA-MM-JJ ou clair (ex: '2026-09-28', 'demain', 'la semaine prochaine')"
                            ),
                            "heure_souhaitee": types.Schema(
                                type="STRING",
                                description="Heure ou moment de départ souhaité (ex: '11:00', '14h', 'matin', 'soir'). Optionnel."
                            ),
                            "pays": types.Schema(
                                type="STRING",
                                description="Réseau ferroviaire : 'auto' (détection automatique par ville), 'suede' (ou 'se'), 'france' (ou 'fr'). Par défaut 'auto'."
                            ),
                            "reserver_automatiquement": types.Schema(
                                type="BOOLEAN",
                                description="Si True, ouvre automatiquement les pages de réservation de chaque train sur le navigateur de son ordinateur pour qu'il n'ait plus qu'à payer."
                            ),
                            "optimiser_avec_agent": types.Schema(
                                type="BOOLEAN",
                                description="Si True (par défaut), déclenche proactivement l'agent Antigravity CLI pour l'analyse multi-critères approfondie (trains de jour vs trains de nuit, correspondances fines, confort couchette et repas)."
                            ),
                        },
                        required=["origine", "destination", "date_depart"]
                    )
                ),

                # ─── 33. monitor_train (was surveiller_train) ─────────────────────────
                types.FunctionDeclaration(
                    name="monitor_train",
                    description=(
                        "Active une veille proactive en temps réel sur un train en circulation via n8n (vérification régulière quai, retard, perturbations SNCF/SJ/Trafikverket). "
                        "Alerte Pierre dès qu'une perturbation ou un retard supérieur à 5 minutes survient. "
                        "À UTILISER QUAND : Pierre demande de surveiller son train pour être prévenu en cas de retard ou de changement de quai. "
                        "NE JAMAIS UTILISER QUAND : Pierre recherche un trajet ou compare des horaires de trains (utiliser 'search_train_routes')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "numero_train": types.Schema(
                                type="STRING",
                                description="Numéro ou référence du train (ex: 'TGV 6612', 'SJ 532', 'TER 881234')"
                            ),
                            "date": types.Schema(
                                type="STRING",
                                description="Date de circulation du train (AAAA-MM-JJ ou 'aujourd'hui', 'demain')"
                            ),
                            "operateur": types.Schema(
                                type="STRING",
                                description="Opérateur ferroviaire : 'sncf', 'sj', 'trafikverket', 'auto'. Par défaut 'sncf'."
                            ),
                        },
                        required=["numero_train", "date"]
                    )
                ),

                # ─── 34. open_train_booking (was reserver_billet_train_local) ─────────
                types.FunctionDeclaration(
                    name="open_train_booking",
                    description=(
                        "Ouvre directement les onglets de réservation du train sélectionné sur le navigateur Google Chrome du PC Windows de Pierre "
                        "via l'agent local pour qu'il n'ait plus qu'à choisir ses places et régler. "
                        "Si les URLs ou gares sont omises, reprend automatiquement le dernier trajet ferroviaire recherché. "
                        "Respect absolu du garde-fou bancaire : aucune validation d'achat automatique, Pierre valide lui-même son règlement. "
                        "À UTILISER QUAND : Pierre a choisi un trajet et confirme vouloir réserver ou ouvrir les pages d'achat sur son écran. "
                        "NE JAMAIS UTILISER QUAND : Pierre souhaite d'abord chercher, comparer les trains ou connaître les horaires (utiliser 'search_train_routes')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "operateur": types.Schema(
                                type="STRING",
                                description="Opérateur ou plateforme : 'sj', 'sncf', 'trainline', 'skanetrafiken', 'omio', 'auto'"
                            ),
                            "origine": types.Schema(
                                type="STRING",
                                description="Gare ou ville de départ (optionnel si déjà recherchée, ex: 'Malmö Central')"
                            ),
                            "destination": types.Schema(
                                type="STRING",
                                description="Gare ou ville d'arrivée (optionnel si déjà recherchée, ex: 'Kiruna')"
                            ),
                            "date_depart": types.Schema(
                                type="STRING",
                                description="Date du voyage (optionnel, ex: 'demain', '2026-09-28')"
                            ),
                            "url_trajet": types.Schema(
                                type="STRING",
                                description="URL directe ou deep link d'un trajet unique à ouvrir sur le Chrome local de Pierre"
                            ),
                            "urls_trajets": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description="Liste d'URLs des différents trains à ouvrir dans des onglets Chrome distincts (pour un enchaînement de plusieurs billets)"
                            ),
                            "description_trajet": types.Schema(
                                type="STRING",
                                description="Description concise du trajet ou de l'enchaînement (ex: 'Malmö → Stockholm → Kiruna')"
                            ),
                        },
                    )
                ),

                # ─── 35. query_jarvis_architecture (was consulter_architecture_jarvis) ─
                types.FunctionDeclaration(
                    name="query_jarvis_architecture",
                    description=(
                        "Interroge en temps réel le document officiel ARCHITECTURE_COMPLETE_JARVIS.md pour répondre à des questions techniques "
                        "sur l'infrastructure de Jarvis, ses capacités, ses garde-fous ou ses serveurs. "
                        "À UTILISER QUAND : Pierre pose des questions sur l'architecture système, les conteneurs Docker, les serveurs VPS, les protocoles audio ou les capacités techniques de Jarvis. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande l'utilisation CPU/RAM instantanée de la machine (utiliser 'get_system_status')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "sujet": types.Schema(
                                type="STRING",
                                description="Sujet ou mot-clé recherché (ex: 'infrastructure', 'docker', 'mémoire', 'deezer', 'antigravity', 'limites', 'endpoints', 'stremio')"
                            ),
                            "section": types.Schema(
                                type="STRING",
                                description="Titre ou numéro de section précis si connu (ex: '1', '2', '3', '7', '7.1', '8', '10')"
                            ),
                        }
                    )
                ),

                # ─── 36. draft_email_response (was triage_et_brouillon_email) ─────────
                types.FunctionDeclaration(
                    name="draft_email_response",
                    description=(
                        "Mobilise l'agent Antigravity CLI pour analyser en profondeur un email reçu ou un fil complexe, lire les pièces jointes PDF "
                        "et préparer un projet de réponse argumenté dans outbox_emails/. "
                        "À UTILISER QUAND : Un email reçu nécessite une analyse experte et la rédaction d'un brouillon soigné avant validation orale de Pierre. "
                        "NE JAMAIS UTILISER QUAND : Pierre souhaite juste envoyer un courriel direct qu'il dicte lui-même (utiliser 'send_email'), "
                        "ni pour une simple consultation de boîte de réception (utiliser 'read_emails')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(
                                type="STRING",
                                description="Expéditeur, mot-clé ou sujet de l'email à traiter (ex: 'Inria', 'stage', 'laboratoire', 'dernier')"
                            ),
                            "consigne": types.Schema(
                                type="STRING",
                                description="Consigne d'orientation ou souhait pour la réponse (ex: 'accepter pour jeudi 14h', 'demander un report')"
                            ),
                        }
                    )
                ),

                # ─── 37. generate_book_summary (was curation_livre_synthese) ──────────
                types.FunctionDeclaration(
                    name="generate_book_summary",
                    description=(
                        "Mobilise l'agent Antigravity CLI pour analyser les thèses majeures d'un livre et rédiger une fiche exécutive 'Synthèse & Clés de lecture' "
                        "de 2 pages dans /artifacts/, expédiée sur Kindle. "
                        "À UTILISER QUAND : Pierre demande une analyse de fond, un guide de lecture ou une synthèse critique d'un livre numérique. "
                        "NE JAMAIS UTILISER QUAND : Pierre veut juste transférer le fichier du livre sur sa liseuse sans synthèse (utiliser 'send_to_ereader'), "
                        "ni pour télécharger le livre (utiliser 'search_and_download_ebook')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "titre_livre": types.Schema(
                                type="STRING",
                                description="Titre ou nom du livre à analyser"
                            ),
                        },
                        required=["titre_livre"]
                    )
                ),

                # ─── 38. system_self_healing (was auto_guerison_systeme) ──────────────
                types.FunctionDeclaration(
                    name="system_self_healing",
                    description=(
                        "Déclenche l'agent SRE Antigravity pour analyser une anomalie critique de code, isoler la cause racine dans le code source serveur "
                        "et appliquer un patch correctif validé par tests. "
                        "À UTILISER QUAND : Une panne ou exception récurrente du serveur nécessite une réparation autonome du code source. "
                        "NE JAMAIS UTILISER QUAND : Pierre demande un simple diagnostic informatif des logs de la console sans réparation (utiliser 'check_console_errors')."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "motif": types.Schema(
                                type="STRING",
                                description="Motif, module ou anomalie à inspecter et corriger (ex: 'console', 'erreur 500', 'service')"
                            ),
                            "action": types.Schema(
                                type="STRING",
                                description="Action SRE spécifique : 'heal' (défaut, auto-guérison), 'rollback' (annuler le dernier patch ou un patch spécifique), 'approve' (valider et appliquer un patch critique en attente)",
                                enum=["heal", "rollback", "approve"]
                            ),
                            "patch_id": types.Schema(
                                type="STRING",
                                description="Identifiant spécifique du patch concerné (requis pour rollback ou approve ciblé, facultatif)"
                            )
                        }
                    )
                ),

                # ─── 39. get_plan_status ──────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="get_plan_status",
                    description=(
                        "Consulte l'état de la checklist du plan multi-étapes en cours. "
                        "À UTILISER QUAND : Une consigne multi-actions a été lancée et tu veux connaître "
                        "les étapes restantes avant d'annoncer que tout est fait. "
                        "RÈGLE ABSOLUE : Tu ne dis JAMAIS 'c'est fait' pour l'ensemble si get_plan_status renvoie pending_count > 0. "
                        "NE JAMAIS UTILISER QUAND : Aucun plan multi-étapes n'a été créé (consigne simple)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={}
                    )
                ),

                # ─── 40. mark_plan_step ──────────────────────────────────────────────────
                types.FunctionDeclaration(
                    name="mark_plan_step",
                    description=(
                        "Marque manuellement une étape du plan multi-étapes avec un statut et une note. "
                        "À UTILISER QUAND : Une étape du plan ne nécessite pas d'outil Jarvis "
                        "(ex: réponse orale, information déjà connue, étape déléguée à l'utilisateur). "
                        "NE JAMAIS UTILISER QUAND : L'étape a déjà été traitée par un outil (le dispatcher met à jour automatiquement)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "step_id": types.Schema(
                                type="STRING",
                                description="L'identifiant de l'étape à mettre à jour (ex: '1', '2', '3')"
                            ),
                            "status": types.Schema(
                                type="STRING",
                                description="Nouveau statut de l'étape",
                                enum=["done", "failed", "skipped", "pending"]
                            ),
                            "note": types.Schema(
                                type="STRING",
                                description="Note courte expliquant le résultat ou la raison (optionnel)"
                            ),
                        },
                        required=["step_id", "status"]
                    )
                ),
            ]
        )
    ]
