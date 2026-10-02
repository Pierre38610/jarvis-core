Spécification Browser Agent Jarvis
S1. Principe
Un seul outil vocal générique, browser_task(goal, start_url?, recipe?), remplace l'automatisation codée site par site.
Le PC Windows (jarvis_local_agent.py) se contente d'OBSERVER et d'AGIR dans le vrai Chrome de l'utilisateur via CDP ([http://localhost:9222](http://localhost:9222/)). Il ne réfléchit pas.
Le VPS (services/browser_agent/) fait tourner la boucle. TOUTE la réflexion (choix des actions, analyse des captures d'écran, vérification) est déléguée aux agents CLI Antigravity (agy), appelés en sous-processus via le wrapper existant de google_antigravity.py.
Jarvis (Gemini Live) lance la tâche en arrière-plan, répond immédiatement et reste disponible à la voix. Le résultat est annoncé via VoiceInjectionQueue.
Jarvis ne construit JAMAIS une URL de résultat. À la fin, il met au premier plan l'onglet sur lequel l'agent a travaillé : la session et les cookies restent les mêmes.
S2. Boucle (VPS)
Pour chaque étape, jusqu'à max_steps (40 par défaut) ou max_duration :
OBSERVER : RPC browser_snapshot -> {url, title, elements, text}.
DÉCIDER : appel CLI « brain » (texte seul) avec : objectif, recette, mémoire du site, snapshot, 6 dernières actions et leurs résultats.
Si le brain répond need_screenshot=true : RPC browser_screenshot, image enregistrée dans /tmp/jarvis_browser//step_.jpg, puis appel CLI « vision » avec le chemin de l'image et la même question. Sa réponse remplace celle du brain.
GARDE-FOU : chaque action passe par guards.check_action() avant d'être exécutée.
AGIR : RPC browser_act (1 à 3 actions par étape).
Si done=true : appel CLI « verifier » sur un nouveau snapshot avec le critère de réussite. Si la vérification est OK, on termine. Sinon, la boucle reprend avec la raison de l'échec.
S3. Format des éléments (snapshot)
Une ligne par élément interactif visible, 150 éléments au maximum : [12] button "Ajouter au panier" / [5] input[text] placeholder="Ville de départ" value="" / [30] link "Panier (2)" href=/cart Le texte visible de la page est tronqué à 1500 caractères. Les ids sont stockés sur la page dans l'attribut data-jarvis-id et recalculés à chaque snapshot.
S4. Réponse JSON du brain (stricte, rien d'autre)
{"thought":"une phrase","actions":[{"type":"click","id":12}],"need_screenshot":false,"done":false,"result":"","handoff":null} Types d'action : click{id} | type{id,text,enter?:bool} | select{id,value} | scroll{direction:"down"|"up"} | goto{url} (uniquement pour start_url ou une URL lue dans la page) | wait{seconds<=120} | back{} | extract{} (renvoie le texte principal complet de la page). handoff : null ou {"reason":"captcha|login|2fa|choix_utilisateur","message":"phrase pour l'utilisateur"}.
S5. Garde-fous
Clic interdit si le texte de l'élément correspond (insensible à la casse) à : payer|paiement|commander|passer la commande|confirmer (la|ma) commande|acheter maintenant|valider et payer|pay now|place order|buy now|complete purchase|confirm booking. Dans ce cas, la tâche s'arrête avec status "ready_for_user", l'onglet est mis au premier plan et Jarvis dit : « C'est prêt, il ne te reste qu'à valider. »
Mots de passe, numéros de carte et CVV : jamais saisis par l'agent. Ces cas passent en handoff.
handoff : l'onglet est mis au premier plan, le message est annoncé à la voix, puis un snapshot est pris toutes les 5 s pendant 5 min au maximum. Le brain décide si le blocage est levé. Sinon, la tâche s'arrête avec status "needs_user".
stop_current_action annule la tâche.
S6. Mémoire par site
data/site_memory/.json : liste de {goal_pattern, steps:[description textuelle des actions réussies], last_success}. Elle est injectée dans le prompt du brain sous forme d'indice, jamais rejouée à l'aveugle.
S7. Recettes
services/browser_agent/recipes/.md : consignes en texte (start_url, étapes indicatives, critère de réussite, max_steps, max_duration). Recettes initiales : cart.md, train.md, gemini_deep_research.md.
