"""Service d'automatisation n8n pour J.A.R.V.I.S.
Passerelle entre Gemini Live et les workflows n8n Community Edition (100 % gratuit).
Mécanisme : Webhooks HTTP locaux + CLI Docker pour l'import de workflows.
"""

import os
import json
import asyncio
import logging
import tempfile
import subprocess
from typing import Any, Optional, Dict

import httpx

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")
N8N_CONTAINER_NAME = os.getenv("N8N_CONTAINER_NAME", "jarvis_n8n")

_HTTP_TIMEOUT = 30.0  # secondes

# Mapping canonique des actions documentaires vers leurs webhooks n8n
ACTION_WEBHOOK_MAPPING = {
    "generer_fichier_tableur": "document-spreadsheet",
    "document-spreadsheet": "document-spreadsheet",
    "generer_presentation": "document-slides",
    "document-slides": "document-slides",
    "notion_enregistrer": "notion-entry",
    "notion-entry": "notion-entry",
}


# ─── 1. Déclenchement de workflow via Webhook ────────────────────────────────

async def trigger_webhook(action_name: str, payload: dict) -> dict:
    """Déclenche un workflow n8n via son Webhook HTTP local (méthode gratuite et illimitée).

    Args:
        action_name: Chemin du webhook configuré dans n8n (ex: "document-spreadsheet", "samsung-calendar").
        payload:     Données JSON envoyées au workflow.

    Returns:
        Réponse JSON retournée par le nœud "Respond to Webhook" de n8n.

    Raises:
        httpx.HTTPStatusError: Si n8n retourne un code HTTP d'erreur.
        httpx.TimeoutException:  Si n8n ne répond pas dans le délai imparti.
    """
    url = f"{N8N_BASE_URL}/webhook/{action_name}"
    headers = {"Content-Type": "application/json"}
    if N8N_WEBHOOK_SECRET:
        headers["X-Jarvis-Secret"] = N8N_WEBHOOK_SECRET

    logger.info("[automation] Déclenchement webhook '%s' → %s", action_name, url)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"raw": response.text}


# ─── 2. Tool Call Gemini Live : executer_action_externe & Helpers Documentaires ───

def build_spreadsheet_payload(nom_fichier: str, colonnes: list[str], lignes: list[list[Any]], description: str = "") -> dict:
    """Construit et normalise le payload pour le webhook document-spreadsheet."""
    clean_name = (nom_fichier or "document.xlsx").strip()
    if not clean_name.lower().endswith(".xlsx"):
        clean_name += ".xlsx"
    return {
        "nom_fichier": clean_name,
        "colonnes": colonnes or [],
        "lignes": lignes or [],
        "description": description or "",
        "downloads_dir": "/home/opc/jarvis-core/downloads/",
    }


def build_slides_payload(titre: str, theme: str, slides: list[dict[str, Any]]) -> dict:
    """Construit et normalise le payload pour le webhook document-slides."""
    clean_titre = (titre or "Presentation").strip()
    return {
        "titre": clean_titre,
        "theme": theme or "stark",
        "slides": slides or [],
        "downloads_dir": "/home/opc/jarvis-core/downloads/",
    }


def build_notion_payload(type_entree: str, titre: str, contenu: str, tags: Optional[list[str]] = None) -> dict:
    """Construit et normalise le payload pour le webhook notion-entry."""
    return {
        "type_entree": (type_entree or "note").strip().lower(),
        "titre": (titre or "Sans titre").strip(),
        "contenu": (contenu or "").strip(),
        "tags": tags or [],
        "source": "jarvis-voice",
    }


async def executer_action_externe(
    action: Optional[str] = None,
    parametres: Optional[dict] = None,
    action_name: Optional[str] = None
) -> dict:
    """Tool Call exposé à Gemini Live.

    Permet à Jarvis d'appeler dynamiquement n'importe quel workflow n8n actif
    en lui passant les paramètres extraits de la conversation vocale.

    Args:
        action:      Identifiant du workflow n8n (compatibilité rétroactive).
        parametres:  Dictionnaire libre de paramètres extraits par Gemini (optionnel).
        action_name: Identifiant canonique du workflow n8n (ex: "document-spreadsheet", "notion-entry").

    Returns:
        Réponse structurée du workflow n8n, ou dict d'erreur.
    """
    raw_action = (action_name or action or "").strip()
    if not raw_action:
        return {"status": "error", "error": "Paramètre 'action_name' manquant pour exécuter l'action externe."}

    effective_action = ACTION_WEBHOOK_MAPPING.get(raw_action, raw_action)
    effective_params = dict(parametres) if isinstance(parametres, dict) else {}

    # Normalisation spécifique des payloads pour les actions documentaires connues
    if effective_action == "document-spreadsheet":
        effective_params = build_spreadsheet_payload(
            nom_fichier=effective_params.get("nom_fichier", "tableur.xlsx"),
            colonnes=effective_params.get("colonnes", []),
            lignes=effective_params.get("lignes", []),
            description=effective_params.get("description", "")
        )
    elif effective_action == "document-slides":
        effective_params = build_slides_payload(
            titre=effective_params.get("titre", "Presentation"),
            theme=effective_params.get("theme", "stark"),
            slides=effective_params.get("slides", [])
        )
    elif effective_action == "notion-entry":
        effective_params = build_notion_payload(
            type_entree=effective_params.get("type_entree", "note"),
            titre=effective_params.get("titre", "Note rapide"),
            contenu=effective_params.get("contenu", ""),
            tags=effective_params.get("tags", [])
        )

    try:
        result = await trigger_webhook(action_name=effective_action, payload=effective_params)
        logger.info("[automation] Résultat action '%s': %s", effective_action, result)
        return {"status": "success", "action": effective_action, "result": result}
    except httpx.HTTPStatusError as exc:
        logger.error("[automation] Erreur HTTP webhook '%s': %s", effective_action, exc)
        return {
            "status": "error",
            "action": effective_action,
            "error": f"Erreur HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        }
    except httpx.TimeoutException:
        logger.error("[automation] Timeout webhook '%s'", effective_action)
        return {
            "status": "error",
            "action": effective_action,
            "error": f"Timeout : n8n n'a pas répondu en {_HTTP_TIMEOUT}s. Vérifiez que le workflow est actif.",
        }
    except httpx.ConnectError:
        logger.error("[automation] Erreur de connexion à n8n sur '%s'", N8N_BASE_URL)
        return {
            "status": "error",
            "action": effective_action,
            "error": f"Connexion impossible au serveur n8n ({N8N_BASE_URL}). Assurez-vous que le conteneur Docker n8n est bien démarré.",
        }
    except Exception as exc:
        logger.error("[automation] Erreur inattendue webhook '%s': %s", effective_action, exc)
        return {"status": "error", "action": effective_action, "error": str(exc)}


# ─── 3. Import de workflow via CLI n8n (Docker exec) ─────────────────────────

def import_workflow_from_json(workflow_dict: Any) -> bool:
    """Importe un ou plusieurs workflows n8n depuis un dictionnaire Python ou une liste via la CLI Docker.

    Mécanisme gratuit : utilise `n8n import:workflow` depuis l'intérieur du conteneur.
    Ne nécessite aucune licence Enterprise ni accès à l'API REST admin.

    Args:
        workflow_dict: Dictionnaire ou liste de dictionnaires représentant les workflows n8n (format JSON natif).

    Returns:
        True si l'import a réussi, False sinon.
    """
    if isinstance(workflow_dict, list):
        all_ok = True
        for item in workflow_dict:
            if isinstance(item, dict):
                if not import_workflow_from_json(item):
                    all_ok = False
        return all_ok

    if not isinstance(workflow_dict, dict):
        logger.error("[automation] Format invalide pour import_workflow_from_json : attendu dict ou list, reçu %s", type(workflow_dict))
        return False

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp_file:
            json.dump(workflow_dict, tmp_file, ensure_ascii=False, indent=2)
            tmp_path = tmp_file.name

        # Copier le fichier dans le conteneur n8n
        container_path = f"/tmp/jarvis_import_{os.path.basename(tmp_path)}"
        cp_cmd = ["docker", "cp", tmp_path, f"{N8N_CONTAINER_NAME}:{container_path}"]
        cp_result = subprocess.run(cp_cmd, capture_output=True, text=True, timeout=15)
        if cp_result.returncode != 0:
            logger.error("[automation] Erreur docker cp: %s", cp_result.stderr)
            return False

        # Importer le workflow via la CLI n8n dans le conteneur
        import_cmd = [
            "docker", "exec", N8N_CONTAINER_NAME,
            "n8n", "import:workflow", f"--input={container_path}"
        ]
        import_result = subprocess.run(import_cmd, capture_output=True, text=True, timeout=30)
        if import_result.returncode != 0:
            logger.error("[automation] Erreur n8n import: %s", import_result.stderr)
            return False

        logger.info("[automation] Workflow importé avec succès: %s", import_result.stdout.strip())

        # Nettoyer le fichier temporaire dans le conteneur
        subprocess.run(
            ["docker", "exec", N8N_CONTAINER_NAME, "rm", "-f", container_path],
            capture_output=True, timeout=10
        )

        # Activer/publier automatiquement le workflow si un ID est spécifié
        workflow_id = workflow_dict.get("id")
        if workflow_id:
            pub_cmd = ["docker", "exec", N8N_CONTAINER_NAME, "n8n", "publish:workflow", f"--id={workflow_id}"]
            pub_res = subprocess.run(pub_cmd, capture_output=True, text=True, timeout=20)
            if pub_res.returncode == 0:
                logger.info("[automation] Workflow %s publié avec succès.", workflow_id)
                # Redémarrer n8n pour recharger les listeners de webhook
                subprocess.run(["docker", "restart", N8N_CONTAINER_NAME], capture_output=True, text=True, timeout=30)
            else:
                logger.warning("[automation] Échec publication workflow %s: %s", workflow_id, pub_res.stderr)

        return True

    except subprocess.TimeoutExpired:
        logger.error("[automation] Timeout lors de l'import du workflow.")
        return False
    except Exception as exc:
        logger.error("[automation] Erreur import_workflow_from_json: %s", exc)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def export_workflow(workflow_id: str, output_path: str) -> bool:
    """Exporte un workflow n8n existant vers un fichier JSON local.

    Args:
        workflow_id:  ID numérique du workflow dans n8n.
        output_path:  Chemin de destination sur l'hôte.

    Returns:
        True si l'export a réussi, False sinon.
    """
    container_output = f"/tmp/export_{workflow_id}.json"
    try:
        export_cmd = [
            "docker", "exec", N8N_CONTAINER_NAME,
            "n8n", "export:workflow", f"--id={workflow_id}", f"--output={container_output}"
        ]
        result = subprocess.run(export_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error("[automation] Erreur n8n export: %s", result.stderr)
            return False

        cp_cmd = ["docker", "cp", f"{N8N_CONTAINER_NAME}:{container_output}", output_path]
        cp_result = subprocess.run(cp_cmd, capture_output=True, text=True, timeout=15)
        if cp_result.returncode != 0:
            logger.error("[automation] Erreur docker cp export: %s", cp_result.stderr)
            return False

        subprocess.run(
            ["docker", "exec", N8N_CONTAINER_NAME, "rm", "-f", container_output],
            capture_output=True, timeout=10
        )
        logger.info("[automation] Workflow %s exporté vers %s", workflow_id, output_path)
        return True

    except Exception as exc:
        logger.error("[automation] Erreur export_workflow: %s", exc)
        return False


# ─── 4. Définition du Tool Call pour Gemini Live ─────────────────────────────

# Schéma de la fonction exposée à Gemini Live (google.genai.types.FunctionDeclaration)
AUTOMATION_TOOL_DECLARATION = {
    "name": "executer_action_externe",
    "description": (
        "Déclenche un workflow n8n en arrière-plan pour exécuter une action externe : "
        "générer un fichier tableur Excel (.xlsx), créer une présentation Google Slides / PowerPoint (.pptx), "
        "ajouter une note ou tâche dans Notion, synchroniser le calendrier Samsung, envoyer des emails ou messages, "
        "envoyer une notification Gotify, domotique Home Assistant, etc. "
        "Utilise cette fonction dès qu'une action nécessite un service tiers ou un workflow n8n."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action_name": {
                "type": "string",
                "description": (
                    "Identifiant ou chemin de l'action / webhook n8n à déclencher. "
                    "Exemples : 'document-spreadsheet', 'document-slides', 'notion-entry', "
                    "'samsung-calendar', 'send-email', 'notion-note', 'gotify-notify', 'obsidian-note'."
                ),
            },
            "parametres": {
                "type": "object",
                "description": (
                    "Paramètres libres optionnels extraits de la conversation vocale et transmis au workflow. "
                    "Exemples : "
                    "Pour 'document-spreadsheet': {'nom_fichier': 'compta.xlsx', 'colonnes': ['Date', 'Montant'], 'lignes': [['2026-09-26', '150']]}. "
                    "Pour 'document-slides': {'titre': 'Projet Jarvis', 'theme': 'dark', 'slides': [{'titre_slide': 'Intro', 'points': ['Objectif', 'Scope']}]}. "
                    "Pour 'notion-entry': {'type_entree': 'note', 'titre': 'Idée', 'contenu': 'Détails...', 'tags': ['Projet']}."
                ),
            },
        },
        "required": ["action_name"],
    },
}
