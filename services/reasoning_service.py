"""Service de raisonnement approfondi pour J.A.R.V.I.S.
Permet d'arbitrer entre l'API Google GenAI Thinking et l'agent Antigravity IDE
(avec choix parmi Gemini 3.8 Flash Low/Med/High, 3.1 Pro Low/Med/High, Claude 3.7 Sonnet et Claude Opus).
"""

import os
from typing import Dict, Any
from google import genai
from google.genai import types
from config import GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID, HAS_PAID_API_KEY, WORKSPACE_DIR
from google_antigravity import AntigravityAgent, resolve_antigravity_model

# Client payant : utilisé pour les raisonnements approfondis (Gemini 3.8 Flash) et tâches Antigravity
client_paid = genai.Client(api_key=GEMINI_API_KEY_PAID) if GEMINI_API_KEY_PAID else None
client_free = genai.Client(api_key=GEMINI_API_KEY_FREE) if GEMINI_API_KEY_FREE else None
client = client_paid or client_free

async def run_antigravity_task(
    instruction: str,
    model: str = "gemini-3.8-flash-high",
    workspace_path: str = WORKSPACE_DIR,
    on_progress: Any = None,
    directive_queue: Any = None
) -> Dict[str, Any]:
    """Exécute une tâche dans le workspace local avec Antigravity IDE et le modèle spécifié."""
    try:
        agent = AntigravityAgent(workspace=workspace_path, model=model, api_key=GEMINI_API_KEY_PAID)
        result = await agent.run_task_stream(instruction, on_progress=on_progress, directive_queue=directive_queue)
        return {
            "status": result.status,
            "summary": result.summary,
            "model_label": result.model_label,
            "error_type": getattr(result, "error_type", None),
            "engine": "Antigravity IDE"
        }
    except Exception as e:
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
            "engine": "Antigravity IDE"
        }

async def run_deep_reasoning(question: str, model_choice: str | None = None, engine: str = "auto") -> Dict[str, Any]:
    """Routage intelligent de la réflexion complexe :
    1. Si engine=='antigravity' ou si un modèle Pro/Claude est demandé -> Antigravity IDE.
    2. Si engine=='google_api' ou mode auto standard -> Google GenAI Thinking API.
    3. Repli transparent sur Antigravity si l'API rencontre un souci."""
    
    # 1. Vérification si la demande cible spécifiquement un grand modèle Antigravity (Pro ou Claude)
    use_antigravity = (engine == "antigravity")
    if model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus", "antigravity"]):
        use_antigravity = True

    if use_antigravity:
        chosen_model = model_choice or "gemini-3.1-pro-high"
        print(f"[Reasoning Service] Réflexion déléguée à Antigravity IDE avec {chosen_model}...")
        ag_res = await run_antigravity_task(f"Réflexion, synthèse et analyse approfondie : {question}", model=chosen_model)
        return {
            "source": "Antigravity IDE",
            "model_label": ag_res.get("model_label", "Antigravity"),
            "status": ag_res.get("status", "completed"),
            "summary": ag_res.get("summary", ""),
            "full_text": ag_res.get("summary", "")
        }

    # 2. Exécution via l'API officielle Google GenAI Thinking (clé payante toujours utilisée)
    thinking_client = client or client_free
    if thinking_client:
        try:
            print(f"[Reasoning Service] Exécution Google GenAI Thinking : {question[:60]}...")
            prompt = (
                f"Tu es le moteur de réflexion analytique de J.A.R.V.I.S. "
                f"Analyse en profondeur la problématique suivante et fournis une réponse rigoureuse, "
                f"claire, synthétique et percutante destinée à être restituée à l'oral par Jarvis :\n\n"
                f"{question}"
            )
            config_thinking = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_budget=2048,
                    include_thoughts=False
                ),
                temperature=0.6
            )
            
            models_to_try = [
                ("gemini-3.8-flash", "Gemini 3.8 Flash (Thinking)"),
                ("gemini-3.5-flash", "Gemini 3.5 Flash (Thinking)"),
                ("gemini-3.6-flash", "Gemini 3.6 Flash (Thinking)"),
                ("gemini-3.7-flash", "Gemini 3.7 Flash (Thinking)"),
                ("gemini-flash-latest", "Gemini Flash Latest (Thinking)")
            ]
            for m_id, m_label in models_to_try:
                try:
                    response = await thinking_client.aio.models.generate_content(
                        model=m_id,
                        contents=prompt,
                        config=config_thinking
                    )
                    text_output = (response.text or "").strip()
                    if text_output:
                        return {
                            "source": "Google API",
                            "model_label": m_label,
                            "status": "completed",
                            "summary": text_output[:1800],
                            "full_text": text_output
                        }
                except Exception as m_err:
                    print(f"[Reasoning Service] Modèle API {m_id} indisponible ({m_err}), tentative suivante...")
        except Exception as e:
            print(f"[Reasoning Service] Échec API Google GenAI ({e}), repli sur Antigravity...")

    # 3. Repli automatique sur Antigravity Agent Pro High
    print(f"[Reasoning Service] Repli sur Antigravity Agent (Gemini 3.1 Pro High)...")
    ag_res = await run_antigravity_task(f"Réflexion et analyse approfondie : {question}", model="gemini-3.1-pro-high")
    summary = ag_res.get("summary", "")
    return {
        "source": "Antigravity IDE",
        "model_label": ag_res.get("model_label", "Gemini 3.1 Pro (High)"),
        "status": ag_res.get("status", "completed"),
        "summary": summary[:1800],
        "full_text": summary
    }
