"""Service de raisonnement approfondi pour J.A.R.V.I.S.
Permet d'arbitrer entre l'API Google GenAI Thinking et l'agent Antigravity IDE
(avec choix parmi Gemini 3.8 Flash Low/Med/High, 3.1 Pro Low/Med/High, Claude 3.7 Sonnet et Claude Opus).
Stratégie de clé : clé GRATUITE en priorité, repli automatique sur clé PAYANTE si quota épuisé.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
import config
from config import GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID, HAS_PAID_API_KEY, WORKSPACE_DIR
from google_antigravity import AntigravityAgent, resolve_antigravity_model, AntigravityQuotaExhaustedError

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

async def run_antigravity_task(
    instruction: str,
    model: str = "gemini-3.8-flash-high",
    workspace_path: str = WORKSPACE_DIR,
    on_progress: Any = None,
    directive_queue: Any = None,
    try_free_key: bool = True,
    confirmed_by_user: bool = False
) -> Dict[str, Any]:
    """Exécute une tâche dans le workspace local avec Antigravity IDE et le modèle spécifié.
    Stratégie stricte de gestion de clés :
    - Modèles lourds (Pro 3.1, Claude 3.7 Sonnet, Claude Opus) : nécessitent obligatoirement la clé payante.
      Si confirmed_by_user=False, renvoie 'requires_user_confirmation' avec motif et estimation de coût.
    - Modèles Flash (3.8 Flash, 3.5 Flash) : tente d'abord avec la clé GRATUITE.
      Si quota gratuit atteint et confirmed_by_user=False, renvoie 'requires_user_confirmation'.
    - Il est STRICTEMENT IMPOSSIBLE d'utiliser la clé payante sans confirmation expresse de l'utilisateur.
    """
    is_flash_model = any(k in model.lower() for k in ["flash", "3.8", "3.5", "3.6"])
    is_heavy_model = any(k in model.lower() for k in ["pro", "claude", "sonnet", "opus"])

    # 1. Vérification pour les modèles lourds : clé payante obligatoire
    if is_heavy_model:
        if not config.is_paid_key_authorized():
            if "opus" in model.lower():
                cost_str = "~0.10 $"
                model_info = "Claude 3 Opus"
            elif any(k in model.lower() for k in ["sonnet", "claude"]):
                cost_str = "~0.05 $"
                model_info = "Claude 3.7 Sonnet"
            else:
                cost_str = "~0.03 $"
                model_info = "Gemini 3.1 Pro"
            reason = f"Développement avancé d'architecture et de code avec {model_info} : '{instruction[:80]}'"
            print(f"[Reasoning Service] Modèle lourd {model} demandé mais clé payante NON AUTORISÉE dans l'application.")
            prompt_msg = (
                f"ATTENTION : Le modèle {model_info} nécessite la clé payante ({cost_str}), mais l'encoche d'autorisation de la clé payante est actuellement décochée dans l'application. "
                f"RÈGLE STRICTE ET ABSOLUE : Tu es dans l'impossibilité physique de faire des requêtes sur la clé payante tant que l'encoche n'est pas cochée par Pierre. "
                f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede pourquoi tu préconises {model_info} ({reason}), "
                f"indique-lui l'estimation du coût ({cost_str}), "
                f"et demande-lui directement : 'Pierre, pour réaliser cette tâche avec {model_info}, j'ai besoin de la clé payante. Peux-tu cocher l'encoche d'autorisation de la clé payante dans l'application ?'. "
                f"Attends qu'il coche la case dans l'application."
            )
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "requires_checkbox": True,
                "action": "run_antigravity_task",
                "model": model,
                "reason": reason,
                "estimated_cost": cost_str,
                "message": prompt_msg,
                "instruction_to_jarvis": prompt_msg
            }
        elif not confirmed_by_user:
            if "opus" in model.lower():
                cost_str = "~0.10 $"
                model_info = "Claude 3 Opus"
            elif any(k in model.lower() for k in ["sonnet", "claude"]):
                cost_str = "~0.05 $"
                model_info = "Claude 3.7 Sonnet"
            else:
                cost_str = "~0.03 $"
                model_info = "Gemini 3.1 Pro"
            reason = f"Développement avancé d'architecture et de code avec {model_info} : '{instruction[:80]}'"
            print(f"[Reasoning Service] Modèle lourd {model} demandé sans confirmation. Accord payant requis.")
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "action": "run_antigravity_task",
                "model": model,
                "reason": reason,
                "estimated_cost": cost_str,
                "instruction_to_jarvis": (
                    f"ATTENTION : Le modèle {model_info} nécessite la clé payante ({cost_str}). "
                    f"RÈGLE STRICTE ET ABSOLUE : Il est STRICTEMENT IMPOSSIBLE d'utiliser la clé payante sans confirmation expresse de Pierre. "
                    f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede pourquoi tu préconises {model_info} ({reason}), "
                    f"indique-lui l'estimation du coût ({cost_str}), "
                    f"et demande-lui explicitement son accord oral : 'M'autorisez-vous à utiliser la clé payante pour cette tâche ?'. "
                    f"Attends sa confirmation. Dès qu'il valide à l'oral ou via l'écran, réinvoque 'run_antigravity_task' avec confirmed_by_user=True."
                )
            }

    # 2. Détermination de la clé à utiliser
    if is_flash_model:
        # Les modèles Flash passent sur la CLÉ PAYANTE UNIQUEMENT SI elle est autorisée par l'utilisateur
        if config.is_paid_key_authorized() and GEMINI_API_KEY_PAID:
            api_key_to_use = GEMINI_API_KEY_PAID
            key_label = "Clé Payante"
            print(f"[Reasoning Service] Antigravity Flash sur CLÉ PAYANTE autorisée pour zéro latence ({model})...")
        elif GEMINI_API_KEY_FREE:
            api_key_to_use = GEMINI_API_KEY_FREE
            key_label = "Clé Gratuite"
            print(f"[Reasoning Service] Antigravity Flash sur Clé Gratuite (clé payante verrouillée ou non configurée)...")
        else:
            return {"status": "error", "summary": "Aucune clé API disponible. La clé payante est verrouillée dans l'application et aucune clé gratuite n'est configurée.", "model_label": model}
    elif not confirmed_by_user or not config.is_paid_key_authorized():
        # Modèles non-flash lourds sans confirmation préalable ou sans encoche cochée
        if not config.is_paid_key_authorized():
            reason = f"L'utilisation du modèle {model} nécessite la clé payante, qui est actuellement verrouillée dans l'application."
            instr = f"Demande à Pierre à l'oral de cocher l'encoche d'autorisation de la clé payante dans l'application pour utiliser {model}."
        else:
            reason = f"L'utilisation du grand modèle {model} nécessite la clé payante."
            instr = f"Demande confirmation à Pierre pour utiliser {model} sur la clé payante."
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": True,
            "requires_checkbox": not config.is_paid_key_authorized(),
            "action": "run_antigravity_task",
            "model": model,
            "reason": reason,
            "estimated_cost": "~0.03 $",
            "instruction_to_jarvis": instr
        }
    else:
        # Pierre a expressément confirmé pour un grand modèle ET la case est cochée
        if not config.is_paid_key_authorized():
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "requires_checkbox": True,
                "action": "run_antigravity_task",
                "model": model,
                "reason": "La clé payante est physiquement verrouillée (encoche décochée dans l'application).",
                "estimated_cost": "~0.03 $",
                "instruction_to_jarvis": "Pierre, l'encoche d'autorisation de la clé payante est décochée dans l'application. Veuillez la cocher pour me permettre d'effectuer des requêtes payantes."
            }
        if not GEMINI_API_KEY_PAID:
            return {"status": "error", "summary": "Aucune clé payante configurée.", "model_label": model}
        api_key_to_use = GEMINI_API_KEY_PAID
        key_label = "Clé Payante"
        print(f"[Reasoning Service] Antigravity grand modèle sur CLÉ PAYANTE confirmée ({model})...")


    try:
        agent = AntigravityAgent(workspace=workspace_path, model=model, api_key=api_key_to_use)
        result = await agent.run_task_stream(instruction, on_progress=on_progress, directive_queue=directive_queue)
        return {
            "status": result.status,
            "summary": result.summary,
            "model_label": result.model_label,
            "error_type": getattr(result, "error_type", None),
            "engine": "Antigravity IDE",
            "key_used": key_label
        }
    except asyncio.CancelledError:
        print(f"[Reasoning Service] Antigravity annulé par l'utilisateur.")
        _, label = resolve_antigravity_model(model)
        return {
            "status": "cancelled",
            "summary": "Développement interrompu à votre demande.",
            "model_label": label,
            "engine": "Antigravity IDE",
            "key_used": key_label
        }
    except Exception as e:
        # Si la clé gratuite a échoué par quota, NE PAS basculer automatiquement sur la clé payante !
        if key_label == "Clé Gratuite" and _is_quota_error(e):
            print(f"[Reasoning Service] Quota clé gratuite atteint pour Antigravity. Vérification autorisation clé payante...")
            if not config.is_paid_key_authorized():
                reason = f"Le quota de la clé gratuite pour coder a été atteint. Pour poursuivre, l'encoche de la clé payante doit être cochée dans l'application : '{instruction[:80]}'"
                cost_str = "~0.005 $ (< 1 centime)"
                return {
                    "status": "requires_user_confirmation",
                    "requires_paid_consent": True,
                    "requires_checkbox": True,
                    "action": "run_antigravity_task",
                    "model": model,
                    "reason": reason,
                    "estimated_cost": cost_str,
                    "instruction_to_jarvis": (
                        f"ATTENTION : Le quota de la clé gratuite a été atteint. "
                        f"La clé payante est actuellement verrouillée dans l'application (encoche décochée). "
                        f"RÈGLE STRICTE ET ABSOLUE : Tu es dans l'impossibilité physique de continuer sans clé payante. "
                        f"Demande poliment à Pierre à l'oral avec ta voix Aoede : 'Pierre, le quota de ma clé gratuite est épuisé. Pour que je puisse continuer le développement, pourrais-tu cocher l'encoche d'autorisation de la clé payante dans l'application ?'."
                    )
                }
            reason = f"Le quota de la clé gratuite pour coder a été atteint. Pour poursuivre cette tâche, il faut mobiliser la clé payante : '{instruction[:80]}'"
            cost_str = "~0.005 $ (< 1 centime)"
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "action": "run_antigravity_task",
                "model": model,
                "reason": reason,
                "estimated_cost": cost_str,
                "instruction_to_jarvis": (
                    f"ATTENTION : Le quota de la clé gratuite a été atteint. "
                    f"Pour coder cette solution avec Antigravity, il faut utiliser la clé payante ({cost_str}). "
                    f"RÈGLE STRICTE ET ABSOLUE : Tu NE DOIS PAS exécuter sans l'accord préalable de Pierre. "
                    f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede que le quota gratuit est atteint, "
                    f"donne l'estimation du coût ({cost_str}), et demande-lui : 'M'autorisez-vous à utiliser la clé payante pour poursuivre le développement ?'. "
                    f"Attends sa réponse. Dès qu'il valide à l'oral ou via l'écran, réinvoque 'run_antigravity_task' avec confirmed_by_user=True."
                )
            }

        print(f"[Reasoning Service] Erreur Antigravity: {e}")
        from services.console_monitor import console_monitor
        console_monitor.record_error(
            source="Reasoning Service",
            message=str(e),
            level="ERROR"
        )
        _, label = resolve_antigravity_model(model)
        return {
            "status": "error",
            "summary": f"Erreur Antigravity: {str(e)}",
            "model_label": label,
            "error_type": "error",
            "engine": "Antigravity IDE",
            "key_used": key_label
        }

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
            "source": "Antigravity DeepThinkingEngine",
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
            "source": "Antigravity DeepThinkingEngine",
            "model_label": chosen_model,
            "status": "error",
            "summary": f"Erreur lors de la réflexion approfondie : {str(e)}",
            "full_text": ""
        }
