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
from config import GEMINI_API_KEY_FREE, HAS_PAID_API_KEY, WORKSPACE_DIR
from google_antigravity import (
    AntigravityAgent,
    resolve_antigravity_model,
    AntigravityQuotaExhaustedError,
    CognitiveConfig,
    COGNITIVE_TIER_1,
    COGNITIVE_TIER_2,
    COGNITIVE_TIER_3
)
from services.console_monitor import console_monitor

# Client Gemini gratuit par défaut (Tier 1 classification, flash)
client_free = genai.Client(api_key=GEMINI_API_KEY_FREE) if GEMINI_API_KEY_FREE else None
client = client_free

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


async def classify_query_tier_with_llm(query: str, client_override: Optional[Any] = None) -> Dict[str, Any]:
    """Appel de classification léger sur un modèle Tier 1 bon marché (gemini-3.8-flash).
    Renvoie un JSON strict {"tier": 1|2|3, "reason": "..."} à partir du texte de la requête.
    Garantit zéro surcoût sur la clé payante sauf accord préalable.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return {"tier": 2, "reason": "Requête vide, palier tactique Tier 2 appliqué par défaut"}

    system_prompt = (
        "Tu es le classifieur d'arbitrage cognitif de J.A.R.V.I.S. (assistant Stark Industries de Pierre Cassagnettes).\n"
        "Analyse la requête de l'utilisateur (pouvant provenir d'une transcription vocale ASR imparfaite) "
        "et classe-la dans le palier cognitif adapté (tier 1, 2 ou 3) :\n"
        "- Tier 1 : Tâche simple, rapide, factuelle, extraction d'info, commande directe, check d'état, réponse immédiate sans réflexion complexe.\n"
        "- Tier 2 : Analyse tactique, rédaction intermédiaire, synthèse de données, comparatif standard, optimisation ou requête ouverte du quotidien (défaut normal).\n"
        "- Tier 3 : Haute ingénierie logicielle, architecture système pointue, débogage asynchrone critique, refactoring lourd, benchmark exhaustif multi-critères, délibération Système 2.\n\n"
        "RÈGLE STRICTE : Renvoie UNIQUEMENT un objet JSON valide, sans balises Markdown (pas de ```json), avec ce format exact :\n"
        '{"tier": 1, 2 ou 3, "reason": "Courte justification en français"}'
    )

    eff_client = client_override or client_free
    if not eff_client:
        return {"tier": 2, "reason": "Repli Tier 2 (aucun client API Gemini disponible pour la classification)"}

    models_to_try = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-flash-latest"]
    for m in models_to_try:
        try:
            config_gen = types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
            resp = await asyncio.wait_for(
                eff_client.aio.models.generate_content(
                    model=m,
                    contents=f"{system_prompt}\n\nRequête à classifier :\n\"\"\"{clean_q}\"\"\"",
                    config=config_gen
                ),
                timeout=3.5
            )
            raw = (resp.text or "").strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
            t = int(data.get("tier", 2))
            if t not in (1, 2, 3):
                t = 2
            reason = str(data.get("reason", f"Classifié en Tier {t} par {m}"))
            return {"tier": t, "reason": reason}
        except Exception:
            continue

    return {"tier": 2, "reason": "Repli sécurisé Tier 2 suite à l'indisponibilité du classifieur"}


async def resolve_cognitive_tier(
    mission_type: Optional[str] = None,
    query: str = "",
    user_preference: Optional[str] = None,
    intensite_reflexion: Optional[str] = None,
    client_override: Optional[Any] = None
) -> CognitiveConfig:
    """Résout dynamiquement le palier cognitif (Tier 1, 2 ou 3) selon 3 modes ordonnés :
    1. Surcharge explicite prioritaire (vitesse, modèle forcé, intensité)
    2. Table de correspondance statique par mission_type
    3. Classification légère via modèle Tier 1 (gemini-3.8-flash) renvoyant {"tier": 1|2|3, "reason": "..."}
    """
    # ─── MODE 1 : Surcharge explicite (Overriding) PRIORITAIRE ───
    if intensite_reflexion:
        ir = intensite_reflexion.lower().strip()
        if any(k in ir for k in ["rapide", "tier1", "tier 1", "flash-low", "flash_low", "economique"]):
            return COGNITIVE_TIER_1.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)
        elif any(k in ir for k in ["tactique", "tier2", "tier 2", "flash-high", "flash_high"]):
            return COGNITIVE_TIER_2.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)
        elif any(k in ir for k in ["approfondie", "tier3", "tier 3", "pro-high", "pro_high", "fond", "ingenierie"]):
            return COGNITIVE_TIER_3.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)

    if user_preference:
        up = user_preference.lower().strip()
        if any(k in up for k in ["tier1", "tier 1", "flash-low", "flash_low"]):
            return COGNITIVE_TIER_1.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if any(k in up for k in ["tier2", "tier 2", "tactique", "flash-high", "flash_high"]):
            return COGNITIVE_TIER_2.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if any(k in up for k in ["tier3", "tier 3", "approfondie", "pro-high", "pro_high"]):
            return COGNITIVE_TIER_3.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if "flash" in up:
            if any(k in up for k in ["low", "min", "rapide"]):
                return COGNITIVE_TIER_1.with_details(reason=f"Override modèle: {user_preference}", is_override=True)
            return COGNITIVE_TIER_2.with_details(reason=f"Override modèle: {user_preference}", is_override=True)
        if "pro" in up or "3.1" in up:
            if "low" in up:
                return CognitiveConfig(
                    model="gemini-3.1-pro", thinking_level="low", timeout_seconds=300, tier=2,
                    cli_model_arg="gemini-3.1-pro-low", voice_pitch=COGNITIVE_TIER_2.voice_pitch,
                    description="Tier 2 — Raisonnement Tactique (gemini-3.1-pro | réflexion: low)",
                    reason=f"Override modèle pro-low: {user_preference}", is_override=True
                )
            if any(k in up for k in ["med", "medium"]):
                return CognitiveConfig(
                    model="gemini-3.1-pro", thinking_level="medium", timeout_seconds=300, tier=2,
                    cli_model_arg="gemini-3.1-pro-medium", voice_pitch=COGNITIVE_TIER_2.voice_pitch,
                    description="Tier 2 — Raisonnement Tactique (gemini-3.1-pro | réflexion: medium)",
                    reason=f"Override modèle pro-medium: {user_preference}", is_override=True
                )
            return COGNITIVE_TIER_3.with_details(reason=f"Override modèle pro: {user_preference}", is_override=True)

    if query:
        q_lower = query.lower()
        tier1_signals = [
            "passe rapide", "mode rapide", "en rapide", "fais une passe rapide",
            "réponse rapide", "rapide avec flash", "flash rapide", "ultra rapide",
            "sans réfléchir", "juste un résumé court", "brouillon rapide", "check rapide"
        ]
        if any(sig in q_lower for sig in tier1_signals):
            return COGNITIVE_TIER_1.with_details(reason="Override vocal explicite: consigne de passe rapide", is_override=True)

        tier3_signals = [
            "prends tout ton temps", "réfléchis au maximum", "réflexion maximale",
            "analyse approfondie", "réflexion approfondie", "analyse de fond",
            "haute ingénierie", "délibération complète", "mode pro", "avec pro"
        ]
        if any(sig in q_lower for sig in tier3_signals):
            return COGNITIVE_TIER_3.with_details(reason="Override vocal explicite: consigne d'analyse approfondie", is_override=True)

        tier2_signals = [
            "analyse tactique", "passe tactique", "tactique", "intermédiaire",
            "flash high", "réflexion tactique", "analyse équilibrée"
        ]
        if any(sig in q_lower for sig in tier2_signals):
            return COGNITIVE_TIER_2.with_details(reason="Override vocal explicite: consigne d'analyse tactique", is_override=True)

    # ─── MODE 2 : Table de correspondance statique par mission_type ───
    if mission_type:
        mt = mission_type.lower().strip()
        tier1_missions = {"doc_sync", "book_curation", "email_simple", "log_check", "curation_livre_synthese", "documentation"}
        tier2_missions = {"transport_optimizer", "spreadsheet_modeler", "email_analysis", "email_drafting", "memory_consolidation", "morning_briefing"}
        tier3_missions = {"deep_research", "system_healing", "code_refactoring", "software_refactoring", "auto_guerison_systeme", "healing"}

        if mt in tier1_missions:
            return COGNITIVE_TIER_1.with_details(reason=f"Mission statique {mission_type}", is_override=False)
        if mt in tier2_missions:
            return COGNITIVE_TIER_2.with_details(reason=f"Mission statique {mission_type}", is_override=False)
        if mt in tier3_missions:
            return COGNITIVE_TIER_3.with_details(reason=f"Mission statique {mission_type}", is_override=False)

    # ─── MODE 3 : Classification légère par modèle Tier 1 pour requêtes libres ───
    if query and query.strip():
        classification = await classify_query_tier_with_llm(query, client_override=client_override)
        tier_num = classification.get("tier", 2)
        reason = classification.get("reason", "Classification automatique Tier 1")
        if tier_num == 1:
            return COGNITIVE_TIER_1.with_details(reason=reason, is_override=False)
        elif tier_num == 3:
            return COGNITIVE_TIER_3.with_details(reason=reason, is_override=False)
        else:
            return COGNITIVE_TIER_2.with_details(reason=reason, is_override=False)

    return COGNITIVE_TIER_2.with_details(reason="Défaut standard Tier 2", is_override=False)

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

        from services.slides_service import SLIDES_SCHEMA_PROMPT

        artifact_specs = {
            "slides_schema": SLIDES_SCHEMA_PROMPT,
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
        model: str = "gemini-3.1-pro-high",
        allow_quota_fallback: bool = True,
        chosen_tier: int = 3,
        reason: str = "",
        is_override: bool = False
    ) -> Dict[str, Any]:
        """Exécute l'investigation complète en 3 étapes et enregistre l'artefact sur disque."""
        import re
        import time
        from datetime import datetime

        start_time = time.time()
        fallback_occurred = False
        final_tier = chosen_tier

        def _log_tier_telemetry(status_str: str):
            latency_ms = (time.time() - start_time) * 1000
            try:
                from services.memory import log_tier_routing
                asyncio.create_task(log_tier_routing(
                    query_text=goal,
                    chosen_tier=chosen_tier,
                    reason=reason,
                    final_tier=final_tier,
                    latency_ms=latency_ms,
                    override_manuel=is_override,
                    fallback_occurred=fallback_occurred,
                    metadata={
                        "model_initial": model,
                        "model_final": getattr(task_result, "model_label", model) if 'task_result' in locals() and task_result else model,
                        "status": status_str,
                        "artifact_type": required_artifact
                    }
                ))
            except Exception as tr_err:
                print(f"[Reasoning Engine] Note journalisation tier_routing_log : {tr_err}")

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

        # Exécution de l'investigation avec résilience quota et bascule gracieuse automatique
        try:
            task_result = await agent.run_cli_task_stream(prompt, on_progress=_relay_progress, directive_queue=directive_queue)
        except AntigravityQuotaExhaustedError as quota_err:
            is_heavy = any(k in str(model).lower() for k in ["3.1", "pro", "opus", "sonnet"])
            if is_heavy and allow_quota_fallback:
                fallback_occurred = True
                final_tier = 2
                fallback_msg = (
                    "Pierre, le quota 5h sur 3.1 Pro est atteint. "
                    "J'ai automatiquement basculé l'agent sur 3.8 Flash en réflexion renforcée pour finaliser la tâche sans blocage."
                )
                print(f"[Reasoning Engine] {fallback_msg}")
                try:
                    from services.supervision_service import supervision_service
                    supervision_service.record_event(
                        "QUOTA_FALLBACK",
                        f"Quota 5h saturé sur {model}. Bascule automatique vers Tier 2 (Gemini 3.8 Flash High)."
                    )
                except Exception:
                    pass
                console_monitor.record_error(
                    "Antigravity CLI",
                    f"Quota 5h saturé sur {model}. Rétrogradation automatique vers Gemini 3.8 Flash (High).",
                    level="WARNING"
                )
                if on_progress:
                    await on_progress({
                        "step": "quota_fallback",
                        "text": fallback_msg,
                        "fallback_used": True,
                        "new_model": "Gemini 3.8 Flash (High)"
                    })
                try:
                    from services.briefing_service import briefing_service
                    asyncio.create_task(briefing_service.send_telegram_alert(
                        message=f"⚠️ *Alerte Quota Antigravity*\n{fallback_msg}\n*Objectif* : {goal[:60]}",
                        chat_id="6849746502"
                    ))
                except Exception:
                    pass

                # GARDE-FOU INVIOLABLE (Sections 5.2.3 & 5.4 de l'architecture) :
                # Le repli sur Tier 2 (3.8 Flash High) suite à une erreur 429 / Quota ne doit
                # JAMAIS basculer silencieusement vers la clé payante sans accord préalable.
                # On réévalue strictement get_effective_paid_key() : si Pierre n'a pas coché
                # l'encoche dans l'app, fallback_key est obligatoirement GEMINI_API_KEY_FREE.
                fallback_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
                agent_fallback = AntigravityAgent(workspace=self.workspace, model="gemini-3.8-flash-high", api_key=fallback_key)
                task_result = await agent_fallback.run_cli_task_stream(prompt, on_progress=_relay_progress, directive_queue=directive_queue)
            else:
                _log_tier_telemetry("quota_error")
                raise

        if task_result.status == "cancelled":
            _log_tier_telemetry("cancelled")
            return {"status": "cancelled", "summary": "Investigation interrompue par l'utilisateur.", "artifact_path": None}

        if task_result.status == "error":
            _log_tier_telemetry("error")
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
        if required_artifact == "slides_schema":
            sl_list = parsed_content.get("slides", []) if isinstance(parsed_content, dict) else (parsed_content if isinstance(parsed_content, list) else [])
            oral_summary = f"Plan de présentation en {len(sl_list)} diapositives structuré avec succès sur {goal}."
        elif isinstance(parsed_content, dict) and "recommendation" in parsed_content:
            oral_summary = f"Benchmark finalisé. Recommandation clé : {str(parsed_content.get('recommendation', ''))[:160]}."
        else:
            lines = [line.strip() for line in raw_output.split("\n") if line.strip() and not line.strip().startswith("#")]
            oral_summary = " ".join(lines[:2])[:280] if lines else "Investigation approfondie achevée avec succès."

        if on_progress:
            await on_progress({"step": "complete", "text": "Investigation terminée. Artefact enregistré et prêt."})

        _log_tier_telemetry("completed")

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
    directive_queue: Any = None,
    intensite_reflexion: Optional[str] = None,
    mission_type: Optional[str] = None
) -> Dict[str, Any]:
    """Routage intelligent de la réflexion approfondie (Système 2) :
    RÈGLE ABSOLUE D'INITIATIVE ET CONFIRMATION (Pierre Cassagnettes) :
    - Jarvis doit prendre l'initiative de proposer Antigravity CLI pour toute analyse complexe,
      comparatif stratégique, benchmark ou investigation poussée.
    - MAIS Jarvis doit TOUJOURS demander confirmation à Pierre avant de lancer l'exécution !
    - Si confirmed_by_user=False, l'outil renvoie 'requires_user_confirmation' avec instruction claire pour Aoede.
    - Dès que Pierre confirme à l'oral ou via l'écran, la réflexion multi-agents est engagée.
    - Intègre le routage dynamique en 3 tiers et le repli automatique sur quota 429.
    """
    cog_cfg = await resolve_cognitive_tier(
        mission_type=mission_type,
        query=question,
        user_preference=model_choice,
        intensite_reflexion=intensite_reflexion
    )
    chosen_model = model_choice or cog_cfg.cli_model_arg

    # Vérification clé payante si modèle lourd et encoche décochée
    is_heavy_model = any(k in chosen_model.lower() for k in ["pro", "3.1"])
    if is_heavy_model and not config.is_paid_key_authorized():
        cost_str = "~0.03 $"
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
            "cognitive_tier": cog_cfg.tier,
            "reason": f"Le modèle {chosen_model} nécessite la clé payante qui est actuellement verrouillée.",
            "estimated_cost": cost_str,
            "message": prompt_msg,
            "instruction_to_jarvis": prompt_msg
        }

    # Vérification de l'accord utilisateur préalable
    if not confirmed_by_user:
        reason = f"Investigation approfondie multi-agents via Antigravity ({chosen_model}, {cog_cfg.description}) pour : '{question[:80]}'"
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": False,
            "action": "ask_deep_reasoning",
            "model": chosen_model,
            "cognitive_tier": cog_cfg.tier,
            "reason": reason,
            "estimated_cost": "0.00 $ (Session Google AI Pro)",
            "instruction_to_jarvis": (
                f"RÈGLE D'INITIATIVE ET DE CONFIRMATION OBLIGATOIRE : Cette tâche nécessite une réflexion approfondie multi-agents via Antigravity ({cog_cfg.description}). "
                f"Tu as l'initiative de proposer cette analyse experte, mais tu DOIS IMPÉRATIVEMENT demander l'accord oral de Pierre avant de l'exécuter. "
                f"Demande-lui directement et naturellement avec ta voix Aoede : 'Pierre, pour analyser cette question avec nos agents Antigravity sur le VPS ({cog_cfg.description}), m'autorises-tu à lancer cette réflexion ?'. "
                f"Dès que Pierre valide à l'oral ('oui', 'vas-y', 'lance', 'd'accord'), réinvoque immédiatement 'ask_deep_reasoning' avec confirmed_by_user=True."
            )
        }

    # Pierre a confirmé : engagement du moteur multi-agents autonome
    print(f"[Reasoning Service] Accord confirmé. Lancement de AutonomousReasoningEngine ({cog_cfg.description}) avec {chosen_model}...")
    try:
        inv_res = await reasoning_engine.run_autonomous_investigation(
            goal=question,
            context={"mode": "deep_reasoning", "tier": cog_cfg.tier},
            required_artifact="markdown_report",
            timeout_seconds=cog_cfg.timeout_seconds,
            on_progress=on_progress,
            directive_queue=directive_queue,
            model=chosen_model,
            chosen_tier=cog_cfg.tier,
            reason=getattr(cog_cfg, "reason", ""),
            is_override=getattr(cog_cfg, "is_override", False)
        )
        return {
            "source": "Antigravity CLI (VPS)",
            "model_label": inv_res.get("model_used", chosen_model),
            "cognitive_tier": cog_cfg.tier,
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
