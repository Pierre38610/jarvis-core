"""core/tools/declarations.py
Palette complète des outils Gemini Live de J.A.R.V.I.S. (FunctionDeclarations).
Ce module est importé une seule fois par routers/voice.py lors de l'établissement de la session.
"""

from google.genai import types


def get_tools_list() -> list[types.Tool]:
    """Retourne la liste complète des outils déclarés pour Gemini Live."""
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="stop_current_action",
                    description=(
                        "ARRÊTE IMMÉDIATEMENT l'action, la recherche en cours, les agents Antigravity CLI ou la navigation web. "
                        "TU DOIS L'INVOQUER IMMÉDIATEMENT dès que Pierre te dit d'arrêter, de faire une pause, de stopper ou d'annuler "
                        "(ex: 'arrête', 'stop', 'annule', 'interromps', 'tais-toi et arrête', 'laisse tomber'). "
                        "Cette action interrompt physiquement l'agent Antigravity CLI sur le VPS ou le navigateur en arrière-plan et remet l'état à l'arrêt."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={"reason": types.Schema(type="STRING", description="Le motif ou la consigne d'arrêt exprimée par Pierre")}
                    )
                ),
                types.FunctionDeclaration(
                    name="guide_active_task",
                    description=(
                        "Permet à l'utilisateur de guider, adapter, modifier ou corriger en direct l'investigation ou l'action en cours "
                        "par les agents Antigravity CLI sur le VPS (ex: approfondir un axe, ajouter un paramètre, réorienter l'analyse ou l'ingénierie) sans interrompre la session."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={"directive": types.Schema(type="STRING", description="La consigne ou adaptation demandée par l'utilisateur pour l'action en cours")},
                        required=["directive"]
                    )
                ),
                types.FunctionDeclaration(
                    name="ask_deep_reasoning",
                    description=(
                        "MOTEUR UNIQUE MULTI-AGENTS ANTIGRAVITY CLI (SUR LE VPS) : "
                        "Mobilise le pipeline d'agents autonomes Antigravity CLI qui tournent sur le VPS (Prospecteur, Analyste critique, Synthèse & Artefact, Ingénierie) "
                        "pour toute tâche complexe, recherche approfondie, analyse comparative, benchmark, audit technique, réflexion ou conception avancée. "
                        "PRISE D'INITIATIVE MAXIMALE : À la moindre tâche un peu complexe ou recherche fouillée, propose immédiatement à Pierre de mobiliser les agents Antigravity CLI sur le VPS. "
                        "Si Pierre n'a pas encore validé, appelle cet outil avec confirmed_by_user=False pour obtenir la proposition orale pour Aoede. "
                        "Si Pierre a validé ou a directement ordonné d'utiliser Antigravity / recherche approfondie dès son instruction, appelle cet outil avec confirmed_by_user=True."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "question": types.Schema(type="STRING", description="La problématique, sujet d'investigation, question stratégique, audit ou mission à traiter en profondeur par Antigravity CLI sur le VPS"),
                            "model": types.Schema(type="STRING", description=(
                                "Modèle Antigravity CLI selon la complexité : "
                                "'gemini-3.1-pro-high' (par défaut, pour synthèse et analyse de référence), "
                                "'claude-3-opus' ou 'claude-3-7-sonnet' (pour analyse conceptuelle pointue), "
                                "ou 'gemini-3.8-flash-high' (pour investigation rapide)."
                            )),
                            "confirmed_by_user": types.Schema(type="BOOLEAN", description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta proposition. Par défaut False."),
                        },
                        required=["question"]
                    )
                ),
                types.FunctionDeclaration(
                    name="search_web",
                    description="Effectue une recherche rapide sur Internet pour obtenir des informations récentes, des faits, des prix ou des liens.",
                    parameters=types.Schema(type="OBJECT", properties={"query": types.Schema(type="STRING", description="La requête de recherche web précise")}, required=["query"])
                ),
                types.FunctionDeclaration(
                    name="run_browser_task",
                    description="Pilote un agent web autonome universel (Browser-Use) pour naviguer, réserver (hôtels, billets), remplir des formulaires, comparer des prix ou exécuter des missions sur n'importe quel site web.",
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "goal": types.Schema(type="STRING", description="L'objectif concret de navigation à accomplir sur le web"),
                            "url": types.Schema(type="STRING", description="L'URL de départ si connue, sinon laisser vide"),
                            "confirmed_by_user": types.Schema(type="BOOLEAN", description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral suite à ta demande expliquant le besoin et le coût estimé. Par défaut False."),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution de la navigation : 'vps_headless' (fond de tâche cloud discret sur le VPS) ou 'local_chrome_cdp' (interactif, directement sur le Google Chrome physique ouvert du PC de Pierre via CDP). Si le PC est hors-ligne, toujours 'vps_headless'. Si le PC est en ligne et que Pierre n'a pas spécifié, demande-lui s'il préfère agir sur son Chrome à l'écran ou discrètement en tâche de fond."
                            ),
                        },
                        required=["goal"]
                    )
                ),
                types.FunctionDeclaration(
                    name="open_user_browser",
                    description="Ouvre Google Chrome directement à l'écran de l'utilisateur avec son profil connecté pour afficher un site ou une page spécifique.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(type="STRING", description="L'URL à ouvrir dans le navigateur à l'écran"),
                            "reason": types.Schema(type="STRING", description="La raison de l'ouverture"),
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="set_browser_link",
                    description=(
                        "Définit ou met à jour le lien web précis affiché dans le HUD mobile pour que l'utilisateur puisse cliquer sur 'OUVRIR LE LIEN' "
                        "(ex: lien direct vers un train spécifique avec horaires, un vol précis, un hôtel, ou un article complet au lieu de la page d'accueil)."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(type="STRING", description="L'URL directe précise de la page ou de la réservation"),
                            "title": types.Schema(type="STRING", description="Le libellé court du lien (ex: 'Train Paris - Lyon 14h08', 'Vol Air France')"),
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="remember_user_fact",
                    description="Enregistre un souvenir, une préférence, une habitude ou une information importante concernant l'utilisateur dans la mémoire persistante long-terme de Jarvis.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "fact": types.Schema(type="STRING", description="Le fait, la préférence ou l'information à mémoriser durablement"),
                            "category": types.Schema(type="STRING", description="Catégorie (ex: 'préférences', 'projets', 'famille', 'voyage')"),
                        },
                        required=["fact"]
                    )
                ),
                types.FunctionDeclaration(
                    name="recall_user_memories",
                    description="Recherche dans la mémoire persistante long-terme des informations ou souvenirs passés sur l'utilisateur ou ses projets.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={"query": types.Schema(type="STRING", description="Mots-clés de recherche dans la mémoire")},
                        required=["query"]
                    )
                ),
                types.FunctionDeclaration(
                    name="memoriser_information",
                    description=(
                        "Mémorise de façon durable et vectorielle une information, préférence, fait ou tâche que Pierre te demande de retenir. "
                        "Utilise cet outil dès que Pierre dit 'retiens que', 'souviens-toi que', 'note que', 'mémorise que' ou toute formulation similaire."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "cle": types.Schema(type="STRING", description="Nom ou titre court de l'information à mémoriser (ex: 'couleur préférée', 'projet en cours')"),
                            "valeur": types.Schema(type="STRING", description="Contenu complet et détaillé de l'information à mémoriser"),
                            "categorie": types.Schema(type="STRING", description="Catégorie : 'préférence', 'fait', 'tâche', 'habitude', 'projet', 'contact', 'général'"),
                        },
                        required=["cle", "valeur"]
                    )
                ),
                types.FunctionDeclaration(
                    name="get_system_status",
                    description="Consulte l'état en direct de l'ordinateur de l'utilisateur (utilisation du processeur CPU, mémoire RAM, état de la batterie).",
                    parameters=types.Schema(type="OBJECT", properties={})
                ),
                types.FunctionDeclaration(
                    name="launch_application",
                    description=(
                        "Ouvre une application locale sur l'ordinateur de Pierre "
                        "(Calculatrice, Bloc-notes, VS Code, Explorateur, Chrome, VLC). "
                        "IMPORTANT : Pour Deezer utilise 'play_music_deezer'. Pour Stremio utilise 'play_video_stremio'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={"app_name": types.Schema(type="STRING", description="Nom de l'application (calculatrice, bloc-notes, vscode, explorateur, chrome, vlc)")},
                        required=["app_name"]
                    )
                ),
                types.FunctionDeclaration(
                    name="play_music_deezer",
                    description=(
                        "CONTRÔLE 100% DU WEB PLAYER DEEZER (deezer.com) : "
                        "Gère le Web Player Deezer en temps réel via liaison WebSocket locale et l'API Deezer officielle. "
                        "Permet de : "
                        "1) Mettre en pause ('pause', 'arrête la musique') via action='pause', "
                        "2) Reprendre la lecture ('play', 'remets la musique', 'reprends') via action='play', "
                        "3) Basculer play/pause via action='playpause', "
                        "4) Passer au morceau suivant ('suivant', 'morceau suivant', 'next') via action='next', "
                        "5) Revenir au morceau précédent ('précédent', 'morceau d'avant') via action='prev', "
                        "6) Activer/désactiver/basculer l'aléatoire ('mets en aléatoire', 'shuffle') via action='shuffle' (enable=True/False), "
                        "7) Régler le volume via action='volume' (ex: volume=75), "
                        "8) Obtenir l'état de lecture via action='status', "
                        "9) Choisir et lancer un titre, artiste, album ou playlist ('mets Daft Punk', 'joue du rock', 'choisis Billie Jean') via action='choose' avec query='...'. "
                        "Exemples : 'mets en pause la musique', 'musique suivante', 'mets Get Lucky de Daft Punk', 'active la lecture aléatoire', 'règle le son à 80%'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(type="STRING", description="Action à effectuer : 'play', 'pause', 'playpause', 'next', 'prev', 'shuffle', 'volume', 'status', 'choose', 'open'"),
                            "query": types.Schema(type="STRING", description="Titre du morceau, nom de l'artiste, album ou style de musique recherché"),
                            "item_type": types.Schema(type="STRING", description="Type de recherche si applicable : 'track' (défaut), 'album', 'playlist', 'artist'"),
                            "enable": types.Schema(type="BOOLEAN", description="Pour shuffle : True pour activer, False pour désactiver, omis pour basculer"),
                            "volume": types.Schema(type="INTEGER", description="Niveau de volume de 0 à 100 pour l'action 'volume'"),
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="play_video_stremio",
                    description=(
                        "Lance Stremio (installé sur l'ordi de Pierre) et ouvre automatiquement le film ou la série demandée. "
                        "Recherche le contenu via l'API Stremio (Cinemeta), sélectionne le meilleur stream 1080p le plus léger en Go (via Torrentio), "
                        "et ouvre Stremio directement sur le film/série. "
                        "Utilise cet outil dès que Pierre veut regarder un film ou une série. "
                        "Exemples : 'lance Inception', 'mets Breaking Bad', 'je veux voir Avatar 2'."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "title": types.Schema(type="STRING", description="Titre du film ou de la série (ex: 'Inception', 'Breaking Bad', 'Avatar', 'The Office')"),
                            "content_type": types.Schema(type="STRING", description="Type de contenu : 'movie' pour un film (défaut), 'series' pour une série TV"),
                        },
                        required=["title"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_email",
                    description=(
                        "Envoie un courriel à Pierre Cassagnettes (pierrecassagnettes@gmail.com) ou au destinataire externe demandé. "
                        "Pour Pierre Cassagnettes : utilise le format officiel exécutif Stark Industries (rapport, synthèse, capture d'écran). "
                        "Pour toute autre adresse : aucun message prédéfini ni habillage n'est ajouté, tu rédiges intégralement le mail de A à Z. "
                        "Pour joindre des documents (PDF, tableur Excel, ebook ePub, rapport, fichier texte, etc.) : renseigne impérativement 'attachments' avec le nom ou chemin du fichier."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "subject": types.Schema(type="STRING", description="L'objet de l'e-mail"),
                            "body": types.Schema(type="STRING", description="Le contenu du message rédigé par l'agent de A à Z"),
                            "to_email": types.Schema(type="STRING", description="Adresse destinataire. Par défaut: pierrecassagnettes@gmail.com"),
                            "attachments": types.Schema(
                                type="ARRAY",
                                items=types.Schema(type="STRING"),
                                description=(
                                    "Liste des fichiers ou documents à joindre en pièce jointe (ex: ['rapport.pdf'], ['Second Foundation.epub'], ['tableur.xlsx'], ou chemin complet). "
                                    "Tu peux simplement donner le nom du fichier, du livre ou du document, ou 'dernier' pour le dernier fichier téléchargé. "
                                    "Jarvis se charge de localiser automatiquement le document dans les téléchargements et sur le système."
                                )
                            ),
                            "include_latest_screenshot": types.Schema(type="BOOLEAN", description="Mettre à True pour joindre automatiquement une capture d'écran du système ou du navigateur"),
                        },
                        required=["subject"]
                    )
                ),
                types.FunctionDeclaration(
                    name="read_emails",
                    description=(
                        "Consulte et lit les e-mails reçus par Pierre Cassagnettes sur son adresse pierrecassagnettes@gmail.com via la boîte de réception Gmail. "
                        "Permet de récupérer les derniers messages reçus, de rechercher des mails précis par mot-clé ou expéditeur, "
                        "ou de filtrer les e-mails non lus pour en faire une synthèse vocale claire et fluide."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "count": types.Schema(type="INTEGER", description="Nombre d'e-mails récents à consulter (par défaut: 3 à 5)"),
                            "query": types.Schema(type="STRING", description="Mot-clé ou expéditeur optionnel pour filtrer la recherche"),
                            "unread_only": types.Schema(type="BOOLEAN", description="Mettre à True pour ne récupérer que les e-mails non lus"),
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="check_console_errors",
                    description=(
                        "Inspecte, lit et analyse les erreurs récentes de la console et des logs serveur pour diagnostiquer un dysfonctionnement, "
                        "tenter de corriger automatiquement le problème si possible, et informer Pierre à l'oral avec précision avec ta voix Aoede."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={"action": types.Schema(type="STRING", description="Action souhaitée : 'diagnose' (analyser les erreurs récentes), 'clear' (réinitialiser le journal d'erreurs)")}
                    )
                ),
                types.FunctionDeclaration(
                    name="interact_web_page",
                    description=(
                        "Lit, explore et interagit concrètement avec n'importe quelle page web : lit le texte et la structure HTML, "
                        "découvre les formulaires, champs et boutons, remplit des champs de texte, clique sur des éléments "
                        "ou fait défiler la page. Capture un aperçu visuel en direct."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(type="STRING", description="L'URL de la page web avec laquelle interagir"),
                            "action": types.Schema(type="STRING", description="Type d'action : 'read' (lecture et découverte des champs/boutons), 'click' (clic sur sélecteur), 'fill' (saisie de texte), 'scroll' (défilement)"),
                            "selector": types.Schema(type="STRING", description="Sélecteur CSS ou texte de l'élément cible pour le clic ou la saisie"),
                            "text_to_fill": types.Schema(type="STRING", description="Texte à saisir dans le champ si l'action est 'fill'"),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution : 'vps_headless' (Playwright headless cloud sur le VPS) ou 'local_chrome_cdp' (interactif, sur le Chrome physique du PC de Pierre via CDP)."
                            ),
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="prepare_web_cart_or_checkout",
                    description=(
                        "COMMANDE & ACHAT AUTONOME SÉCURISÉ POUR PIERRE : "
                        "Recherche un produit ou service, l'ajoute au panier sur un site marchand (Amazon, Fnac, Decathlon, SNCF, etc.), "
                        "navigue jusqu'à l'étape de commande, préremplit automatiquement les coordonnées de Pierre Cassagnettes, "
                        "S'ARRÊTE STRICTEMENT AVANT LE PAIEMENT (aucun prélèvement automatique) et ouvre automatiquement Google Chrome à l'écran."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "product_or_service": types.Schema(type="STRING", description="Le produit, livre, matériel ou service précis à ajouter au panier"),
                            "merchant_url": types.Schema(type="STRING", description="L'URL du site marchand ou boutique en ligne (optionnel, recherche auto si vide)"),
                            "open_when_ready": types.Schema(type="BOOLEAN", description="Ouvrir automatiquement Chrome à l'écran dès que le panier et le formulaire sont prêts (True par défaut)"),
                            "execution_target": types.Schema(
                                type="STRING",
                                enum=["vps_headless", "local_chrome_cdp"],
                                description="Cible d'exécution du panier/achat : 'local_chrome_cdp' (sur le navigateur Chrome physique du PC de Pierre via CDP) ou 'vps_headless' (fond de tâche cloud sur le VPS)."
                            ),
                        },
                        required=["product_or_service"]
                    )
                ),
                types.FunctionDeclaration(
                    name="download_file",
                    description=(
                        "Télécharge un fichier, document, ebook ou média depuis Internet sur l'ordinateur de Pierre. "
                        "RÈGLE STRICTE : Nécessite TOUJOURS l'accord oral préalable explicite de Pierre. "
                        "Si confirmed_by_user=False, l'outil analyse la taille et le nom, puis te demande d'obtenir l'accord oral de Pierre."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(type="STRING", description="L'URL directe de téléchargement du fichier"),
                            "filename": types.Schema(type="STRING", description="Nom de fichier optionnel sous lequel enregistrer le document"),
                            "confirmed_by_user": types.Schema(type="BOOLEAN", description="Mettre à True UNIQUEMENT après accord oral explicite de Pierre. Par défaut False."),
                            "file_type": types.Schema(type="STRING", description="Type de fichier : 'general' pour un document, 'ebook' pour un livre numérique"),
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_to_ereader",
                    description=(
                        "Achemine un livre numérique (ebook EPUB, MOBI, PDF) vers la liseuse de Pierre (Kindle, Kobo, Vivlio, Bookeen). "
                        "Détecte automatiquement si une liseuse est branchée en USB pour y copier directement le fichier, "
                        "ou l'expédie par courriel direct (Send-to-Kindle ou boîte email) avec le livre en pièce jointe."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "file_path": types.Schema(type="STRING", description="Chemin local du fichier ebook ou nom du livre téléchargé"),
                            "ereader_email": types.Schema(type="STRING", description="Adresse e-mail spécifique de la liseuse (ex: pierre@kindle.com) si connue"),
                            "method": types.Schema(type="STRING", description="Méthode de transfert : 'auto' (USB en priorité puis e-mail), 'usb' (USB uniquement), 'email' (envoi par courriel)"),
                        },
                        required=["file_path"]
                    )
                ),
                types.FunctionDeclaration(
                    name="search_and_download_ebook",
                    description=(
                        "Mission complète E-Book : Recherche un livre numérique sur Internet, demande l'accord oral de Pierre pour le télécharger, "
                        "puis l'envoie automatiquement sur sa liseuse (Kindle, Kobo) via USB ou e-mail. "
                        "Si confirmed_by_user=False, demande confirmation à Pierre avant de télécharger."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(type="STRING", description="Le titre ou l'auteur de l'ebook recherché (ex: 'L'art de la guerre', '1984 George Orwell')"),
                            "source_url": types.Schema(type="STRING", description="URL directe du site ou de la page de téléchargement si spécifiée par Pierre"),
                            "confirmed_by_user": types.Schema(type="BOOLEAN", description="Mettre à True UNIQUEMENT après que Pierre a explicitement donné son accord oral. Par défaut False."),
                            "send_to_reader": types.Schema(type="BOOLEAN", description="Transférer automatiquement sur la liseuse une fois téléchargé (True par défaut)"),
                            "ereader_email": types.Schema(type="STRING", description="Adresse e-mail spécifique de la liseuse si renseignée"),
                            "lang": types.Schema(type="STRING", description="Langue demandée pour le livre : 'en' (anglais) ou 'fr' (français). Détecter automatiquement selon la demande de Pierre."),
                        },
                        required=["query"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_page_to_kindle",
                    description=(
                        "ENVOI SUR LISEUSE KINDLE : "
                        "Envoie un article web, une page internet ou un document directement sur la liseuse Kindle de Pierre. "
                        "Utilise l'extension officielle Google Chrome 'Send to Kindle' et l'acheminement direct e-reader (par courriel vers sa liseuse). "
                        "Extrait le texte épuré sans publicité en mode lecture, l'expédie par mail et ouvre la page dans Google Chrome avec l'extension prête."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "url": types.Schema(type="STRING", description="L'URL directe de l'article web ou de la page à transférer vers la Kindle"),
                            "title": types.Schema(type="STRING", description="Titre optionnel de l'article pour la bibliothèque Kindle"),
                        },
                        required=["url"]
                    )
                ),
                types.FunctionDeclaration(
                    name="send_file_to_kindle",
                    description=(
                        "ENVOI DE FICHIER SUR LISEUSE KINDLE (AMAZON SEND TO KINDLE WEB) : "
                        "Dépose et envoie un fichier (livre numérique EPUB, document PDF, texte TXT, document Word DOC/DOCX, image) "
                        "directement sur la liseuse Kindle de Pierre via la page officielle Amazon Send to Kindle connectée à son compte."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "file_path": types.Schema(type="STRING", description="Chemin ou nom du fichier à déposer sur Amazon Send to Kindle"),
                            "open_browser_if_needed": types.Schema(type="BOOLEAN", description="Ouvre Chrome à l'écran si une reconnexion Amazon est requise (True par défaut)"),
                        },
                        required=["file_path"]
                    )
                ),
                types.FunctionDeclaration(
                    name="list_chrome_extensions",
                    description=(
                        "Liste les extensions Google Chrome installées sur l'ordinateur de Pierre "
                        "(Send to Kindle, Wanteeed, Adblock, SubWallet, etc.) et vérifie la disponibilité de Send to Kindle."
                    ),
                    parameters=types.Schema(type="OBJECT", properties={})
                ),
                types.FunctionDeclaration(
                    name="executer_action_externe",
                    description=(
                        "Déclenche un workflow d'automatisation externe n8n en arrière-plan pour exécuter des actions tierces : "
                        "ajouter un événement au calendrier Samsung, créer une note Notion ou Obsidian, envoyer une notification Gotify, "
                        "envoyer des emails ou messages, synchroniser des contacts, automatiser une tâche domotique, etc. "
                        "Utilise systématiquement cet outil dès qu'une action sollicite un service tiers ou un workflow d'automatisation n8n."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action_name": types.Schema(
                                type="STRING",
                                description=(
                                    "Nom ou identifiant de l'action / webhook n8n à déclencher. "
                                    "Exemples : 'document-spreadsheet', 'document-slides', 'notion-entry', "
                                    "'samsung-calendar', 'notion-note', 'gotify-notify', 'send-email', 'obsidian-note'."
                                )
                            ),
                            "parametres": types.Schema(
                                type="OBJECT",
                                description=(
                                    "Paramètres libres optionnels extraits de la conversation vocale et transmis au workflow. "
                                    "Exemple pour 'samsung-calendar' : {'titre': 'Dentiste', 'date': '2026-09-27', 'heure': '10:00', 'duree_minutes': 60}."
                                )
                            ),
                        },
                        required=["action_name"]
                    )
                ),
                types.FunctionDeclaration(
                    name="generer_fichier_tableur",
                    description=(
                        "GÉNÉRATION DE TABLEUR EXCEL (.xlsx) : "
                        "Convertit des listes et structures de données JSON (comptabilité, budgets, benchmarks, inventaires, listes) "
                        "en un fichier tableur Excel (.xlsx) propre et téléchargeable via n8n. "
                        "L'opération s'exécute en arrière-plan et le fichier est déposé dans /downloads/."
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
                        },
                        required=["nom_fichier", "colonnes", "lignes"]
                    )
                ),
                types.FunctionDeclaration(
                    name="generer_presentation",
                    description=(
                        "CRÉATION DE PRÉSENTATION GOOGLE SLIDES EXPERTE & ESTHÉTIQUE : "
                        "Conçoit une présentation Google Slides complète (5 à 8 diapositives), richement documentée, percutante et stylisée "
                        "(thèmes Stark sombre/cyan, Bitcoin/Gold or/noir, Corporate, Cyber). "
                        "Le système prend impérativement le temps en tâche de fond d'élaborer un plan narratif rigoureux, de rechercher des faits vérifiés, "
                        "actualités et métriques clés, de trier les informations et d'appliquer une mise en page soignée avec cartes de contenu et chiffres clés. "
                        "Tu dois spécifier le titre ou sujet (ex: 'Bitcoin', 'Intelligence Artificielle', 'Transition Énergétique'), et le thème souhaité. "
                        "Si tu n'as pas de liste de slides pré-écrite, laisse le champ 'slides' vide ou omis : Jarvis structurera lui-même les diapositives complètes. "
                        "L'opération s'exécute en tâche de fond et le lien direct vers Google Slides est fourni à Pierre à la fin."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "titre": types.Schema(
                                type="STRING",
                                description="Titre ou sujet général de la présentation (ex: 'Bitcoin : Révolution Monétaire', 'Intelligence Artificielle 2026')"
                            ),
                            "sujet": types.Schema(
                                type="STRING",
                                description="Thématique ou sujet détaillé à analyser et développer si distinct du titre"
                            ),
                            "theme": types.Schema(
                                type="STRING",
                                description="Thème esthétique : 'stark' (défaut, sombre futuriste Stark Industries), 'bitcoin' ou 'gold' (noir/or prestige crypto), 'corporate' (blanc/bleu exécutif), 'cyber' (néon/violet), 'dark' (minimaliste sombre)"
                            ),
                            "slides": types.Schema(
                                type="ARRAY",
                                items=types.Schema(
                                    type="OBJECT",
                                    properties={
                                        "titre_slide": types.Schema(type="STRING", description="Titre de la diapositive"),
                                        "category": types.Schema(type="STRING", description="Section ou catégorie (ex: 'HISTOIRE', 'ARCHITECTURE', 'MARCHÉ')"),
                                        "points": types.Schema(type="ARRAY", items=types.Schema(type="STRING"), description="Liste des points clés ou faits vérifiés"),
                                        "key_metric": types.Schema(
                                            type="OBJECT",
                                            properties={
                                                "label": types.Schema(type="STRING", description="Libellé du chiffre clé (ex: 'PLAFOND')"),
                                                "value": types.Schema(type="STRING", description="Valeur du chiffre clé (ex: '21M BTC')"),
                                                "desc": types.Schema(type="STRING", description="Explication concise du chiffre clé"),
                                            },
                                            description="Chiffre clé ou métrique majeure mise en exergue"
                                        ),
                                        "notes": types.Schema(type="STRING", description="Notes d'orateur ou texte explicatif"),
                                    },
                                    required=["titre_slide", "points"]
                                ),
                                description="Liste optionnelle de diapositives pré-structurées. Si omise, Jarvis élabore lui-même le plan et effectue les recherches."
                            ),
                        },
                        required=["titre"]
                    )
                ),
                types.FunctionDeclaration(
                    name="get_active_task_status",
                    description=(
                        "Consulte en temps réel l'état d'avancement, l'étape précise et les détails des tâches actives en arrière-plan "
                        "(recherche documentaire et génération Google Slides, développement Antigravity, navigation web, etc.). "
                        "À INVOQUER IMMÉDIATEMENT dès que Pierre te demande ce que tu es en train de faire, où en est sa présentation, "
                        "ou comment progresse son travail (ex: 'qu'est-ce que tu fais ?', 'où en est ma présentation ?', 'explique-moi ce que tu es en train de faire')."
                    ),
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "task_id": types.Schema(type="STRING", description="Identifiant optionnel d'une tâche spécifique à vérifier"),
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="notion_enregistrer",
                    description=(
                        "PRISE DE NOTES & TO-DO NOTION : "
                        "Ajoute une entrée structurée (note rapide, item de todo-list, fiche de veille, compte-rendu) "
                        "dans les bases de données et pages Notion de Pierre via n8n."
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
                types.FunctionDeclaration(
                    name="agenda_gerer_evenement",
                    description=(
                        "GESTION AGENDA SAMSUNG / GOOGLE CALENDAR : "
                        "Créer, décaler, consulter ou supprimer des événements et rendez-vous dans l'agenda de Pierre "
                        "(synchronisés nativement entre Google Calendar et l'application Samsung Calendar de son smartphone). "
                        "L'opération s'exécute en arrière-plan via webhook n8n."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "action": types.Schema(
                                type="STRING",
                                description="Action sur l'agenda : 'creer' (ajouter un événement), 'consulter' (voir les rendez-vous), 'decaler' (modifier horaire/date), 'supprimer' (annuler)"
                            ),
                            "titre": types.Schema(
                                type="STRING",
                                description="Titre ou intitulé de l'événement / rendez-vous"
                            ),
                            "date_debut": types.Schema(
                                type="STRING",
                                description="Date et heure de début au format ISO ou clair (ex: '2026-09-26T14:30:00', 'demain 10h')"
                            ),
                            "date_fin": types.Schema(
                                type="STRING",
                                description="Date et heure de fin optionnelle (ex: '2026-09-26T15:30:00')"
                            ),
                            "description": types.Schema(
                                type="STRING",
                                description="Description détaillée, lieu ou notes pour l'événement (optionnel)"
                            ),
                        },
                        required=["action", "titre", "date_debut"]
                    )
                ),
                types.FunctionDeclaration(
                    name="creer_rappel_push",
                    description=(
                        "CAPTURE VOCALE AVEC RAPPEL PUSH : "
                        "Note un mémo oral instantané et programme un rappel push sur le smartphone de Pierre "
                        "via n8n (Pushbullet / Web Push / Telegram Stark Bot) à une échéance ou un horaire précis."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "message": types.Schema(
                                type="STRING",
                                description="Message, texte du mémo ou rappel à notifier sur le smartphone"
                            ),
                            "echeance": types.Schema(
                                type="STRING",
                                description="Délai ou date/heure d'échéance du rappel ou de la notification (ex: 'maintenant' pour un envoi immédiat, 'dans 30 minutes', 'dans 2 heures', '18h30'). Par défaut 'maintenant'."
                            ),
                            "priorite": types.Schema(
                                type="STRING",
                                description="Niveau de priorité du rappel : 'basse', 'normale', 'haute', 'urgente'. Par défaut 'normale'."
                            ),
                        },
                        required=["message"]
                    )
                ),
                types.FunctionDeclaration(
                    name="demander_morning_briefing",
                    description=(
                        "MORNING BRIEFING STARK INDUSTRIES : "
                        "Restitue la routine matinale au ton Stark Industries (météo locale, rendez-vous du jour, "
                        "e-mails urgents non lus et résumé des tâches). "
                        "Interroge en priorité la clé Redis 'jarvis:briefing:today' préparée dès 7h00 pour un retour instantané sans latence, "
                        "ou compile les données fraîches si nécessaire."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
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
                types.FunctionDeclaration(
                    name="rechercher_train",
                    description=(
                        "RECHERCHE D'ITINÉRAIRES & ENCHAÎNEMENTS FERROVIAIRES (FRANCE & SUÈDE) : "
                        "Recherche les horaires, tarifs indicatifs et génère les liens valides de réservation "
                        "pour un trajet direct OU un enchaînement de plusieurs trains nécessitant plusieurs billets "
                        "(ex: Suède du Sud comme Malmö vers Kiruna / Laponie via Stockholm en train grande vitesse + train de nuit). "
                        "Supporte les gares françaises (Paris, Lyon, Marseille, etc.) et suédoises (Malmö, Stockholm, Kiruna, etc.). "
                        "Si Pierre demande de réserver, prendre ou ouvrir les billets, positionne 'reserver_automatiquement' à True pour "
                        "ouvrir immédiatement toutes les pages de réservation sur son navigateur Chrome pour qu'il n'ait plus qu'à payer."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
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
                                description="Si True (ou si Pierre souhaite réserver/acheter ou ouvrir les billets sur son navigateur), ouvre automatiquement les pages de réservation de chaque train sur le navigateur de son ordinateur pour qu'il n'ait plus qu'à payer."
                            ),
                        },
                        required=["origine", "destination", "date_depart"]
                    )
                ),
                types.FunctionDeclaration(
                    name="surveiller_train",
                    description=(
                        "SURVEILLANCE PROACTIVE EN TEMPS RÉEL D'UN TRAIN : "
                        "Active une boucle de veille via n8n (interrogation toutes les 10 min jusqu'au départ) "
                        "pour surveiller le quai de départ, l'heure et les retards sur les réseaux SNCF, SJ ou Trafikverket. "
                        "Alerte Pierre dès qu'une perturbation ou un retard supérieur à 5 minutes survient."
                    ),
                    behavior=types.Behavior.NON_BLOCKING,
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
                types.FunctionDeclaration(
                    name="reserver_billet_train_local",
                    description=(
                        "RÉSERVATION & PANIER SUR PC LOCAL WINDOWS : "
                        "Sur demande de réservation ou d'achat d'un ou plusieurs billets, ouvre la session Google Chrome sur le PC physique de Pierre "
                        "via jarvis_local_agent pour ouvrir la page du trajet ou de chaque segment (enchaînement de trains) jusqu'à l'écran de paiement. "
                        "Si les URLs ou gares sont omises, reprend automatiquement le dernier trajet ferroviaire recherché. "
                        "Respect absolu du garde-fou bancaire : aucune validation d'achat automatique, Pierre valide lui-même son règlement."
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
                types.FunctionDeclaration(
                    name="consulter_architecture_jarvis",
                    description=(
                        "CONSULTATION DE L'ARCHITECTURE ET DES CAPACITÉS SYSTÈME (ARCHITECTURE_COMPLETE_JARVIS.md) : "
                        "Accède en temps réel au document d'architecture officiel et complet de J.A.R.V.I.S. (rechargé dynamiquement). "
                        "Permet de vérifier : "
                        "1) L'infrastructure technique (VPS Oracle, Docker, Redis, Postgres, Qdrant, n8n, tunnels Cloudflare), "
                        "2) Le rôle du PC local Windows (jarvis_local_agent, profils Chrome, applications, ports Deezer), "
                        "3) Le catalogue exhaustif des capacités et outils disponibles, "
                        "4) Les limites strictes et garde-fous (interdiction paiement auto, interdiction téléchargement sans accord, etc.), "
                        "5) Les endpoints REST et WebSockets. "
                        "Utilise cet outil dès que Pierre te demande comment tu fonctionnes, ce que tu es, si tu es capable de faire quelque chose, "
                        "ou souhaite des détails techniques sur ton infrastructure."
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
            ]
        )
    ]

