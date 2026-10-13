# Guide Google Workspace MCP & Paramètre OAuth 2.0 `is_agentic`

> **Référence Projet Google Cloud** : `jarvis-pierre`  
> **Date d'entrée en vigueur** : 12 Octobre 2026  
> **Échéance critique** : 11 Novembre 2026 (Rejet strict des clients non-agentiques)  
> **Verrouillage irréversible** : 12 Novembre 2026  

---

## 1. Contexte & Annonce Officielle Google Cloud

Google déploie les serveurs **Google Workspace Model Context Protocol (MCP)**, exposant nativement les fonctionnalités de **Gmail**, **Google Drive**, **Google Calendar**, **Google Docs**, et **Google Slides** aux agents IA externes (dont J.A.R.V.I.S.).

Afin de permettre aux administrateurs Google Workspace et Google Cloud de différencier le trafic des agents IA autonomes du trafic applicatif classique, Google introduit la classification **`is_agentic`** sur tous les clients OAuth 2.0.

### Calendrier Officiel

| Date | Événement | Impact pour J.A.R.V.I.S. |
| :--- | :--- | :--- |
| **12 Octobre 2026** | Ouverture du paramètre `is_agentic` | Le réglage peut être activé directement sur le client OAuth existant du projet `jarvis-pierre`. |
| **11 Novembre 2026** | **Blocage strict** des accès non-agentiques | Google rejette toute requête vers les serveurs Workspace MCP avec l'erreur :<br>`the client isn't marked as an AI agent`. |
| **12 Novembre 2026** | **Verrouillage définitif** | Le paramètre devient permanent sur les clients existants. Pour passer un client en agentic après cette date, il sera obligatoire de créer un nouvel identifiant OAuth Client ID. |

---

## 2. Procédure Pas-à-Pas Immédiate (À faire dans Google Cloud Console)

Cette action s'effectue directement dans l'interface de gestion Google Cloud Console pour le projet `jarvis-pierre` :

1. **Accéder à la console Google Cloud** :
   Ouvrez la page des identifiants du projet :  
   👉 [Google Cloud Console - Identifiants jarvis-pierre](https://console.cloud.google.com/apis/credentials?project=jarvis-pierre)

2. **Sélectionner le Client OAuth 2.0** :
   Dans la section **ID client OAuth 2.0** (OAuth 2.0 Client IDs), cliquez sur l'identifiant client utilisé par Jarvis / n8n (ex: `Jarvis n8n Webhook Client` ou `Web client`).

3. **Activer la classification Agentique** :
   - Repérez le paramètre **"AI Agent"** ou **"Agentic application"** (`is_agentic`).
   - Activez la case à cocher / bascule sur **Activé / True**.

4. **Enregistrer** :
   - Cliquez sur **Enregistrer** (**Save**) en bas de page.

> 💡 **Délai de propagation** : Le réglage est effectif en quelques secondes sur les serveurs Google.

---

## 3. Prise en Charge & Protection dans J.A.R.V.I.S. Core

Le code de J.A.R.V.I.S. intègre un système proactif d'interception et de diagnostic :

1. **Module `backend/services/automation.py`** :
   - La fonction `check_workspace_agentic_error` inspecte automatiquement les réponses et les exceptions HTTP renvoyées par les webhooks n8n et les requêtes Google Workspace.
   - En cas d'erreur `the client isn't marked as an AI agent` ou `is_agentic`, l'action retourne une erreur explicite avec le flag `is_agentic_error: True` et pointe vers le guide de résolution.
2. **Module `backend/services/slides_service.py`** :
   - La fonction `verify_presentation` intercepte les codes HTTP 401/403 retournés par l'API Google Slides et signale immédiatement si le client doit être classé agentique.
3. **Workflows n8n** :
   - Les nœuds Google Calendar (`time_and_briefing.json`) et Google Slides (`documents_suite.json`) conservent leur fonctionnement sans interruption dès lors que le client OAuth est basculé sur `is_agentic`.

---

## 4. Foire Aux Questions (FAQ)

### Que se passe-t-il si je ne modifie rien avant le 11 novembre 2026 ?
- Les appels traditionnels aux REST APIs pures continueront de fonctionner temporairement, mais toute fonctionnalité utilisant ou migrant vers les serveurs Workspace MCP échouera avec l'erreur `the client isn't marked as an AI agent`.
- À partir du 12 novembre 2026, l'ancien client OAuth ne pourra plus être modifié : il faudra alors créer un tout nouveau Client ID OAuth dans Google Cloud, reconfigurer les secrets dans n8n et réautoriser le compte Google.

### Y a-t-il un surcoût ?
- **Non, 0 €**. La classification `is_agentic` est purement un paramètre de gouvernance et de sécurité de Google Workspace, sans surcoût de facturation.
