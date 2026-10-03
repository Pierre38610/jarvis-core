"""Constructeur de prompts optimisés et parseur de réponses pour les agents Antigravity CLI.
Adapte la syntaxe des instructions selon le fournisseur (balises XML pour Claude, markdown concis pour Gemini)
et garantit un format de rapport de sortie standardisé en JSON.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

from services.model_routing.model_registry import model_registry

logger = logging.getLogger("jarvis.prompt_builder")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(BASE_DIR, "prompts", "templates")


# Schema JSON standard exigé
STANDARD_JSON_SCHEMA = """{
  "status": "completed | error | partial",
  "summary": "Résumé clair et concis de ce qui a été accompli",
  "actions_done": ["action 1 effectuée", "action 2 effectuée"],
  "files_changed": ["chemin/relatif/fichier1.py"],
  "errors": [],
  "next_steps": ["prochaine recommandation optionnelle"]
}"""


def _load_template(task_type: str) -> Optional[str]:
    """Charge un template de prompt personnalisé depuis le dossier prompts/templates si existant."""
    t_clean = task_type.lower().strip()
    path = os.path.join(TEMPLATES_DIR, f"{t_clean}.txt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.debug(f"Impossible de lire le template {path}: {e}")
    return None


def build_prompt(
    task: Union[str, Dict[str, Any]],
    model: str,
    effort: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    role: Optional[str] = None,
    max_context_chars: int = 15000
) -> str:
    """Construit un prompt hautement structuré et adapté au modèle cible (Gemini ou Claude).
    
    Args:
        task: Description textuelle ou dictionnaire de la tâche.
        model: Nom du modèle cible.
        effort: Niveau de réflexion optionnel ("low", "medium", "high").
        context: Dictionnaire de contexte additionnel.
        role: Rôle spécifique à injecter.
        max_context_chars: Limite de troncature intelligente pour le contexte.
    """
    m_info = model_registry.get_model(model)
    provider = m_info.provider if m_info else ("claude" if "claude" in model.lower() or "sonnet" in model.lower() else "gemini")

    if isinstance(task, dict):
        goal = task.get("goal") or task.get("description") or task.get("query") or str(task)
        task_type = task.get("task_type") or task.get("type") or "medium"
        raw_ctx = task.get("context") or context or {}
    else:
        goal = str(task)
        task_type = "medium"
        raw_ctx = context or {}

    # Formatage du contexte avec troncature intelligente
    ctx_str = json.dumps(raw_ctx, ensure_ascii=False, indent=2) if raw_ctx else "{}"
    if len(ctx_str) > max_context_chars:
        ctx_str = ctx_str[:max_context_chars] + "\n... [Contexte tronqué pour respecter les limites]"

    # Rôle par défaut
    agent_role = role or "Agent Autonome J.A.R.V.I.S. (Stark Industries)"

    # Vérifier template spécifique
    template_content = _load_template(task_type)

    if provider == "claude":
        # Structure optimisée pour Claude avec balises XML
        claude_instructions = template_content or "1. Analyse le besoin.\n2. Exécute les actions requises.\n3. Valide le travail effectué."
        xml_prompt = f"""<system_role>
Tu es l'{agent_role}. Tu travailles sous l'environnement Antigravity CLI pour Pierre Cassagnettes.
</system_role>

<objective>
{goal}
</objective>

<context>
{ctx_str}
</context>

<constraints>
- Autonomie totale : ne pose pas de questions interactives, prends les initiatives logiques et documente-les.
- Sécurité stricte : Ne lis, n'affiche et ne manipule JAMAIS de clés d'API, secrets ou fichiers .env.
- Périmètre : Reste confiné au répertoire du projet.
- Rigueur : Vérifie chaque modification de code par analyse ou tests.
</constraints>

<instructions>
{claude_instructions}
</instructions>

<output_format>
IMPORTANT : Ta réponse finale doit IMPÉRATIVEMENT inclure un objet JSON valide structuré selon ce schéma exact :
```json
{STANDARD_JSON_SCHEMA}
```
</output_format>
"""
        return xml_prompt.strip()

    else:
        # Structure optimisée pour Gemini (concise, directive et hiérarchisée)
        effort_line = f"NIVEAU DE RÉFLEXION : {effort.upper()}" if effort else ""
        gemini_instructions = template_content or (
            "- Analyse les données et exécute les opérations nécessaires de manière autonome.\n"
            "- Valide chaque étape pour garantir la fiabilité.\n"
            "- Respecte les contraintes de sécurité (zéro accès aux clés secrètes / .env)."
        )
        gemini_prompt = f"""# MISSION AUTONOME J.A.R.V.I.S.
RÔLE : {agent_role}
{effort_line}

## 1. OBJECTIF
{goal}

## 2. CONTEXTE INITIAL
{ctx_str}

## 3. DIRECTIVES & INSTRUCTIONS
{gemini_instructions}

## 4. FORMAT DU RAPPORT FINAL OBLIGATOIRE
À la fin de ton intervention, fournis impérativement un objet JSON valide avec cette structure exacte :
```json
{STANDARD_JSON_SCHEMA}
```
"""
        return gemini_prompt.strip()


def parse_agent_response(raw_output: str) -> Dict[str, Any]:
    """Extrait et parse de manière tolérante le rapport JSON de l'agent, même entouré de texte ou de logs."""
    if not raw_output or not raw_output.strip():
        return {
            "status": "empty",
            "summary": "Aucune sortie produite par l'agent.",
            "actions_done": [],
            "files_changed": [],
            "errors": ["Empty output"],
            "next_steps": []
        }

    # 1. Rechercher un bloc de code markdown ```json ... ```
    json_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
    if json_block_match:
        try:
            data = json.loads(json_block_match.group(1).strip())
            if isinstance(data, dict):
                return _normalize_parsed_json(data, raw_output)
        except json.JSONDecodeError:
            pass

    # 2. Rechercher le premier objet JSON valide entre accolades
    matches = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_output, re.DOTALL))
    for m in reversed(matches):  # Tester en partant de la fin (réponse finale)
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict) and ("status" in data or "summary" in data or "actions_done" in data):
                return _normalize_parsed_json(data, raw_output)
        except json.JSONDecodeError:
            continue

    # 3. Fallback : Parser basique si aucun JSON complet n'est extrait
    summary_lines = [line.strip() for line in raw_output.split("\n") if line.strip() and not line.strip().startswith("`")]
    summary_text = summary_lines[-1] if summary_lines else raw_output[:300]

    return {
        "status": "completed",
        "summary": summary_text,
        "actions_done": [],
        "files_changed": [],
        "errors": [],
        "next_steps": [],
        "raw_text": raw_output
    }


def _normalize_parsed_json(data: Dict[str, Any], raw_output: str) -> Dict[str, Any]:
    """Assure que toutes les clés standard sont présentes avec des types adéquats."""
    return {
        "status": data.get("status", "completed"),
        "summary": data.get("summary", raw_output[:200]),
        "actions_done": data.get("actions_done", []) if isinstance(data.get("actions_done"), list) else [],
        "files_changed": data.get("files_changed", []) if isinstance(data.get("files_changed"), list) else [],
        "errors": data.get("errors", []) if isinstance(data.get("errors"), list) else [],
        "next_steps": data.get("next_steps", []) if isinstance(data.get("next_steps"), list) else [],
        "raw_text": raw_output
    }
