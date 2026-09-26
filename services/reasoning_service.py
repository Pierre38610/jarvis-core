"""Service de raisonnement approfondi et multi-agents pour J.A.R.V.I.S.
S'appuie sur le pipeline d'agents autonomes Antigravity CLI tournant sur le VPS.
Stratégie de clé : clé GRATUITE en priorité, repli automatique sur clé PAYANTE si quota épuisé.
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
import config
from config import GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID, HAS_PAID_API_KEY, WORKSPACE_DIR
from google_antigravity import AntigravityAgent, resolve_antigravity_model, AntigravityQuotaExhaustedError
from services.console_monitor import console_monitor

# Clients Gemini : clé GRATUITE prioritaire, clé PAYANTE en repli (conditionnée à l'encoche utilisateur)
client_paid = genai.Client(api_key=GEMINI_API_KEY_PAID) if GEMINI_API_KEY_PAID else None
client_free = genai.Client(api_key=GEMINI_API_KEY_FREE) if GEMINI_API_KEY_FREE else None
client = client_paid or client_free

def _is_quota_error(exc: Exception) -> bool:
    """Détecte les erreurs de quota/rate-limit pour déclencher le repli sur clé payante."""
    err_str = f"{type(exc).__name__}: {str(exc)}".lower()
    keywords = ["429", "quota", "resource_exhausted", "resourceexhausted",
                "rate limit", "ratelimit", "too many requests", "limit exceeded", "exhausted"]
    if any(k in err_str for k in keywords):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code in (429, 8)

ARTIFACTS_DIR = os.path.join(WORKSPACE_DIR, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

class AutonomousReasoningEngine:
    """Moteur d'orchestration multi-agents autonome pour les tâches de réflexion complexe (Système 2).
    
    Architecture en 3 phases spécialisées :
    1. Prospecteur / Sources & Faits : Collecte des faits, données chiffrées, sources contradictoires.
    2. Analyste / Critique : Réfutation d'hallucinations, comparaison critique, structure logique.
    3. Synthèse & Artefact : Production rigoureuse du livrable dans le format requis (slides_schema, markdown_report, code_patch, json_benchmark) et écriture dans artifacts/.
    """

    def __init__(self, workspace: str = WORKSPACE_DIR, artifacts_dir: str = ARTIFACTS_DIR):
        self.workspace = os.path.abspath(workspace)
        self.artifacts_dir = os.path.abspath(artifacts_dir)
        os.makedirs(self.workspace, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def _build_investigation_prompt(self, goal: str, context: Optional[Dict[str, Any]], required_artifact: str) -> str:
        """Construit le prompt d'orchestration multi-agents imposant la démarche en 3 phases et le format de l'artefact."""
        ctx_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "{}"

        artifact_specs = {
            "slides_schema": (
                "LIVRABLE STRICT ATTENDU : Un tableau JSON contenant entre 5 et 8 objets diapositives respectant EXACTEMENT la structure suivante :\n"
                "[\n"
                "  {\n"
                "    \"titre_slide\": \"Titre percutant de la diapositive\",\n"
                "    \"category\": \"CATEGORIE\",\n"
                "    \"points\": [\"Fait ou argument 1\", \"Fait ou argument 2\", \"Fait ou argument 3\"],\n"
                "    \"key_metric\": {\"label\": \"NOM METRIQUE\", \"value\": \"VALEUR\", \"desc\": \"Explication\"},\n"
                "    \"notes\": \"Notes orateur détaillées pour la présentation orale.\"\n"
                "  }\n"
                "]\n"
                "IMPORTANT : Rends UNIQUEMENT le bloc JSON brut commençant par '[' et finissant par ']'. Aucun commentaire ni markdown autour."
            ),
            "markdown_report": (
                "LIVRABLE STRICT ATTENDU : Un rapport exécutif Stark Industries complet en Markdown structuré :\n"
                "# TITRE DU RAPPORT\n"
                "## 1. Synthèse Exécutive (Executive Summary)\n"
                "## 2. Faits Clés & Données Vérifiées\n"
                "## 3. Analyse Critique & Comparatif Approfondi\n"
                "## 4. Recommandations Stratégiques & Plan d'Action\n"
                "Rédige une analyse exhaustive, rigoureuse et factuelle sans concessions ni bavardage."
            ),
            "code_patch": (
                "LIVRABLE STRICT ATTENDU : Un plan d'implémentation logicielle et les patchs de code exacts.\n"
                "Inclus : 1) Analyse d'impact architecturale, 2) Code complet ou blocs diff, 3) Procédure de tests unitaires."
            ),
            "json_benchmark": (
                "LIVRABLE STRICT ATTENDU : Un objet JSON structuré contenant le benchmark comparatif :\n"
                "{\n"
                "  \"title\": \"Titre du benchmark\",\n"
                "  \"criteria\": [\"critère 1\", \"critère 2\"],\n"
                "  \"items\": [\n"
                "    {\"name\": \"Option A\", \"scores\": {\"critère 1\": 8, \"critère 2\": 9}, \"pros\": [...], \"cons\": [...], \"verdict\": \"...\"}\n"
                "  ],\n"
                "  \"recommendation\": \"Recommandation finale argumentée\"\n"
                "}\n"
                "IMPORTANT : Rends UNIQUEMENT le bloc JSON brut."
            )
        }

        spec = artifact_specs.get(required_artifact, artifact_specs["markdown_report"])

        return (
            f"MISSION D'INVESTIGATION ET DE RÉFLEXION APPROFONDIE (SYSTÈME 2 - MULTI-AGENTS)\n"
            f"OBJECTIF MAÎTRE : {goal}\n"
            f"CONTEXTE INITIAL : {ctx_str}\n\n"
            f"Tu opères comme un méta-agent orchestrateur découpant la réflexion en 3 sous-agents séquentiels :\n"
            f"1. SOUS-AGENT PROSPECTEUR / SOURCES : Rassemble des données tangibles, des faits historiques, des actualités récentes et des sources contradictoires vérifiées.\n"
            f"2. SOUS-AGENT ANALYSTE / CRITIQUE : Élimine les hallucinations et approximations. Confronte les chiffres, pèse les arguments et structure la démonstration logique.\n"
            f"3. SOUS-AGENT SYNTHÈSE & ARTEFACT : Produit le livrable final selon la spécification stricte ci-dessous, sans pollution de contexte ni préambule inutile.\n\n"
            f"{spec}"
        )

    async def run_autonomous_investigation(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        required_artifact: str = "markdown_report",
        timeout_seconds: int = 300,
        on_progress: Any = None,
        directive_queue: Any = None,
        model: str = "gemini-3.1-pro-high"
    ) -> Dict[str, Any]:
        """Exécute l'investigation complète en 3 étapes et enregistre l'artefact sur disque."""
        import re
        from datetime import datetime

        if on_progress:
            await on_progress({"step": "start", "text": f"Phase 1 : Sous-agent Prospecteur - Collecte des sources et vérification factuelle..."})

        prompt = self._build_investigation_prompt(goal, context, required_artifact)

        effective_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
        agent = AntigravityAgent(workspace=self.workspace, model=model, api_key=effective_key)

        async def _relay_progress(p_info):
            step = p_info.get("step", "")
            txt = p_info.get("text", "")
            if on_progress:
                if "source" in txt.lower() or "recherche" in txt.lower() or "prospect" in txt.lower():
                    await on_progress({"step": "prospector", "text": "Phase 1 : Analyse des sources et données de référence..."})
                elif "critique" in txt.lower() or "analys" in txt.lower() or "compar" in txt.lower():
                    await on_progress({"step": "critic", "text": "Phase 2 : Sous-agent Critique - Élimination des biais et structuration..."})
                elif "synth" in txt.lower() or "artefact" in txt.lower() or "format" in txt.lower():
                    await on_progress({"step": "synthesis", "text": f"Phase 3 : Sous-agent Synthèse - Génération de l'artefact ({required_artifact})..."})
                else:
                    await on_progress(p_info)

        # Exécution de l'investigation
        task_result = await agent.run_cli_task_stream(prompt, on_progress=_relay_progress, directive_queue=directive_queue)

        if task_result.status == "cancelled":
            return {"status": "cancelled", "summary": "Investigation interrompue par l'utilisateur.", "artifact_path": None}

        if task_result.status == "error":
            return {
                "status": "error",
                "summary": task_result.summary,
                "full_output": task_result.summary,
                "artifact_path": None,
                "model_used": task_result.model_label
            }

        raw_output = task_result.summary or ""

        # Détermination de l'extension et sauvegarde de l'artefact sur disque
        ext = "json" if ("json" in required_artifact or "slides" in required_artifact) else "md"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', goal[:25].strip().lower())
        artifact_filename = f"artifact_{clean_slug}_{timestamp}.{ext}"
        artifact_path = os.path.join(self.artifacts_dir, artifact_filename)

        parsed_content: Any = raw_output
        if ext == "json":
            # Extraction JSON robuste
            json_match = re.search(r'(\[.*\]|\{.*\})', raw_output, re.DOTALL)
            if json_match:
                try:
                    parsed_content = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    parsed_content = raw_output

        # Écriture du fichier artefact sur le système
        try:
            with open(artifact_path, "w", encoding="utf-8") as f:
                if isinstance(parsed_content, (dict, list)):
                    json.dump(parsed_content, f, ensure_ascii=False, indent=2)
                else:
                    f.write(str(parsed_content))
            print(f"[Reasoning Engine] Artefact généré avec succès dans : {artifact_path}")
        except Exception as write_err:
            print(f"[Reasoning Engine] Erreur écriture artefact: {write_err}")

        # Synthèse vocale percutante pour Aoede (2-3 phrases)
        if isinstance(parsed_content, list) and required_artifact == "slides_schema":
            oral_summary = f"Plan de présentation en {len(parsed_content)} diapositives structuré avec succès sur {goal}."
        elif isinstance(parsed_content, dict) and "recommendation" in parsed_content:
            oral_summary = f"Benchmark finalisé. Recommandation clé : {str(parsed_content.get('recommendation', ''))[:160]}."
        else:
            lines = [line.strip() for line in raw_output.split("\n") if line.strip() and not line.strip().startswith("#")]
            oral_summary = " ".join(lines[:2])[:280] if lines else "Investigation approfondie achevée avec succès."

        if on_progress:
            await on_progress({"step": "complete", "text": "Investigation terminée. Artefact enregistré et prêt."})

        return {
            "status": "completed",
            "artifact_type": required_artifact,
            "artifact_path": artifact_path,
            "artifact_filename": artifact_filename,
            "artifact_content": parsed_content,
            "summary": oral_summary,
            "full_output": raw_output,
            "model_used": task_result.model_label
        }

# Instance singleton exportée
reasoning_engine = AutonomousReasoningEngine()

async def run_deep_research_cli(instruction: str, model: str = "gemini-3.1-pro-high", on_progress: Any = None) -> Dict[str, Any]:
    """Exécute une investigation via le moteur universel AutonomousReasoningEngine (utilisé par SlidesService)."""
    try:
        res = await reasoning_engine.run_autonomous_investigation(
            goal=instruction,
            context={"source": "slides_service"},
            required_artifact="slides_schema",
            on_progress=on_progress,
            model=model
        )
        # Rétrocompatibilité : renvoie le format attendu par slides_service
        raw_text = json.dumps(res.get("artifact_content", [])) if isinstance(res.get("artifact_content"), (list, dict)) else str(res.get("full_output", ""))
        return {
            "status": res.get("status", "completed"),
            "summary": raw_text,
            "model_label": res.get("model_used", model),
            "artifact_path": res.get("artifact_path"),
            "error_type": None
        }
    except AntigravityQuotaExhaustedError:
        raise
    except Exception as e:
        return {
            "status": "error",
            "summary": f"Erreur du moteur de réflexion : {str(e)}",
            "model_label": model,
            "error_type": "error"
        }

async def run_deep_reasoning(
    question: str,
    model_choice: str | None = None,
    engine: str = "auto",
    confirmed_by_user: bool = False,
    on_progress: Any = None,
    directive_queue: Any = None
) -> Dict[str, Any]:
    """Routage intelligent de la réflexion approfondie (Système 2) :
    RÈGLE ABSOLUE D'INITIATIVE ET CONFIRMATION (Pierre Cassagnettes) :
    - Jarvis doit prendre l'initiative de proposer Antigravity CLI pour toute analyse complexe,
      comparatif stratégique, benchmark ou investigation poussée.
    - MAIS Jarvis doit TOUJOURS demander confirmation à Pierre avant de lancer l'exécution !
    - Si confirmed_by_user=False, l'outil renvoie 'requires_user_confirmation' avec instruction claire pour Aoede.
    - Dès que Pierre confirme à l'oral ou via l'écran, la réflexion multi-agents est engagée.
    """
    chosen_model = model_choice or "gemini-3.1-pro-high"

    # Vérification clé payante si modèle lourd et encoche décochée
    is_heavy_model = any(k in chosen_model.lower() for k in ["pro", "claude", "sonnet", "opus"])
    if is_heavy_model and not config.is_paid_key_authorized():
        cost_str = "~0.03 $"
        if "opus" in chosen_model.lower():
            cost_str = "~0.10 $"
        elif any(k in chosen_model.lower() for k in ["sonnet", "claude"]):
            cost_str = "~0.05 $"
        prompt_msg = (
            f"ATTENTION : Le modèle {chosen_model} nécessite la clé payante ({cost_str}), mais l'encoche d'autorisation de la clé payante est actuellement décochée dans l'application. "
            f"RÈGLE STRICTE ET ABSOLUE : Tu es dans l'impossibilité physique de faire des requêtes sur la clé payante tant que l'encoche n'est pas cochée par Pierre. "
            f"Demande à Pierre à l'oral avec ta voix Aoede : 'Pierre, pour réaliser cette tâche avec {chosen_model}, j'ai besoin de la clé payante. Peux-tu cocher l'encoche d'autorisation de la clé payante dans l'application ?'."
        )
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": True,
            "requires_checkbox": True,
            "action": "ask_deep_reasoning",
            "model": chosen_model,
            "reason": f"Le modèle {chosen_model} nécessite la clé payante qui est actuellement verrouillée.",
            "estimated_cost": cost_str,
            "message": prompt_msg,
            "instruction_to_jarvis": prompt_msg
        }

    # Vérification de l'accord utilisateur préalable
    if not confirmed_by_user:
        reason = f"Investigation approfondie multi-agents via Antigravity ({chosen_model}) pour : '{question[:80]}'"
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": False,
            "action": "ask_deep_reasoning",
            "model": chosen_model,
            "reason": reason,
            "estimated_cost": "0.00 $ (Session Google AI Pro)",
            "instruction_to_jarvis": (
                f"RÈGLE D'INITIATIVE ET DE CONFIRMATION OBLIGATOIRE : Cette tâche nécessite une réflexion approfondie multi-agents via Antigravity. "
                f"Tu as l'initiative de proposer cette analyse experte, mais tu DOIS IMPÉRATIVEMENT demander l'accord oral de Pierre avant de l'exécuter. "
                f"Demande-lui directement et naturellement avec ta voix Aoede : 'Pierre, pour analyser cette question en profondeur avec notre moteur multi-agents Antigravity, m'autorises-tu à lancer cette réflexion ?'. "
                f"Dès que Pierre valide à l'oral ('oui', 'vas-y', 'lance', 'd'accord'), réinvoque immédiatement 'ask_deep_reasoning' avec confirmed_by_user=True."
            )
        }

    # Pierre a confirmé : engagement du moteur multi-agents autonome
    print(f"[Reasoning Service] Accord confirmé. Lancement de AutonomousReasoningEngine avec {chosen_model}...")
    try:
        inv_res = await reasoning_engine.run_autonomous_investigation(
            goal=question,
            context={"mode": "deep_reasoning"},
            required_artifact="markdown_report",
            on_progress=on_progress,
            directive_queue=directive_queue,
            model=chosen_model
        )
        return {
            "source": "Antigravity CLI (VPS)",
            "model_label": inv_res.get("model_used", chosen_model),
            "status": inv_res.get("status", "completed"),
            "summary": inv_res.get("summary", ""),
            "full_text": inv_res.get("full_output", ""),
            "artifact_path": inv_res.get("artifact_path"),
            "artifact_filename": inv_res.get("artifact_filename")
        }
    except AntigravityQuotaExhaustedError:
        raise
    except Exception as e:
        print(f"[Reasoning Service] Erreur lors de l'investigation: {e}")
        console_monitor.record_error("Reasoning Service", str(e), level="ERROR")
        return {
            "source": "Antigravity CLI (VPS)",
            "model_label": chosen_model,
            "status": "error",
            "summary": f"Erreur lors de la réflexion approfondie : {str(e)}",
            "full_text": ""
        }
