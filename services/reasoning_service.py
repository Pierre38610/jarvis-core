"""Service de raisonnement approfondi pour J.A.R.V.I.S.
Permet d'arbitrer entre l'API Google GenAI Thinking et l'agent Antigravity IDE
(avec choix parmi Gemini 3.8 Flash Low/Med/High, 3.1 Pro Low/Med/High, Claude 3.7 Sonnet et Claude Opus).
Stratégie de clé : clé GRATUITE en priorité, repli automatique sur clé PAYANTE si quota épuisé.
"""

import os
from typing import Dict, Any
from google import genai
from google.genai import types
from config import GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID, HAS_PAID_API_KEY, WORKSPACE_DIR
from google_antigravity import AntigravityAgent, resolve_antigravity_model

# Clients Gemini : clé GRATUITE prioritaire, clé PAYANTE en repli
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
    if is_heavy_model and not confirmed_by_user:
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
    if not confirmed_by_user:
        # Essai exclusif sur la clé gratuite pour les modèles Flash
        if GEMINI_API_KEY_FREE:
            api_key_to_use = GEMINI_API_KEY_FREE
            key_label = "Clé Gratuite"
            print(f"[Reasoning Service] Antigravity avec clé GRATUITE ({model})...")
        else:
            reason = f"Aucune clé gratuite disponible pour le développement de code : '{instruction[:80]}'"
            cost_str = "~0.005 $"
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "action": "run_antigravity_task",
                "model": model,
                "reason": reason,
                "estimated_cost": cost_str,
                "instruction_to_jarvis": (
                    f"ATTENTION : Le développement nécessite la clé payante ({cost_str}). "
                    f"Explique à Pierre la situation et demande-lui son accord oral pour mobiliser la clé payante."
                )
            }
    else:
        # Pierre a expressément confirmé l'utilisation de la clé payante
        if not GEMINI_API_KEY_PAID:
            return {"status": "error", "summary": "Aucune clé payante configurée.", "model_label": model}
        api_key_to_use = GEMINI_API_KEY_PAID
        key_label = "Clé Payante"
        print(f"[Reasoning Service] Antigravity avec clé PAYANTE confirmée ({model})...")

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
            print(f"[Reasoning Service] Quota clé gratuite atteint pour Antigravity. Demande d'accord payant...")
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

async def run_deep_reasoning(question: str, model_choice: str | None = None, engine: str = "auto", confirmed_by_user: bool = False) -> Dict[str, Any]:
    """Routage intelligent de la réflexion complexe :
    1. Si un grand modèle Antigravity (Pro/Claude) est demandé :
       Nécessite la clé payante. Si confirmed_by_user=False -> 'requires_user_confirmation'.
    2. Si mode auto ou thinking API :
       Tente d'abord sur la clé GRATUITE.
       Si quota atteint et non confirmé -> demande accord oral.
       Si confirmé -> peut utiliser la clé payante.
    """
    use_antigravity = (engine == "antigravity")
    if model_choice and any(k in model_choice.lower() for k in ["pro", "claude", "sonnet", "opus", "antigravity"]):
        use_antigravity = True

    if use_antigravity:
        chosen_model = model_choice or "gemini-3.1-pro-high"
        if not confirmed_by_user:
            reason = f"Réflexion approfondie et analyse complexe avec {chosen_model} pour : '{question[:80]}'"
            cost_str = "~0.03 $"
            return {
                "status": "requires_user_confirmation",
                "requires_paid_consent": True,
                "action": "ask_deep_reasoning",
                "reason": reason,
                "estimated_cost": cost_str,
                "instruction_to_jarvis": (
                    f"Cette réflexion avec grand modèle ({chosen_model}) nécessite la clé payante ({cost_str}). "
                    f"RÈGLE STRICTE ET ABSOLUE : Tu NE DOIS PAS exécuter sans confirmation préalable de Pierre. "
                    f"Explique à Pierre à l'oral avec ta voix Aoede pourquoi tu préconises {chosen_model} ({reason}), "
                    f"donne l'estimation du coût ({cost_str}), et demande-lui explicitement son accord oral : 'M'autorisez-vous à utiliser l'API payante ?'. "
                    f"S'il refuse, tu pourras répondre avec engine='google_api' qui utilise la clé gratuite sans frais."
                )
            }
        print(f"[Reasoning Service] Réflexion déléguée à Antigravity IDE avec {chosen_model} (clé payante confirmée)...")
        ag_res = await run_antigravity_task(f"Réflexion, synthèse et analyse approfondie : {question}", model=chosen_model, confirmed_by_user=True)
        return {
            "source": "Antigravity IDE",
            "model_label": ag_res.get("model_label", "Antigravity"),
            "status": ag_res.get("status", "completed"),
            "summary": ag_res.get("summary", ""),
            "full_text": ag_res.get("summary", "")
        }

    # 2. Exécution via l'API officielle Google GenAI Thinking
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

    # Tentative d'abord avec la clé GRATUITE
    if client_free:
        for m_id, m_label in models_to_try:
            try:
                print(f"[Reasoning Service] Thinking {m_id} avec Clé Gratuite...")
                response = await client_free.aio.models.generate_content(
                    model=m_id,
                    contents=prompt,
                    config=config_thinking
                )
                text_output = (response.text or "").strip()
                if text_output:
                    return {
                        "source": "Google API",
                        "model_label": f"{m_label} (Clé Gratuite)",
                        "key_used": "Clé Gratuite",
                        "status": "completed",
                        "summary": text_output[:1800],
                        "full_text": text_output
                    }
            except Exception as m_err:
                print(f"[Reasoning Service] Modèle gratuit {m_id} indisponible ({m_err})...")

    # Si la clé gratuite a échoué et que Pierre n'a pas confirmé :
    if not confirmed_by_user:
        reason = f"Les modèles de réflexion sur la clé gratuite ont épuisé leurs quotas pour : '{question[:80]}'"
        cost_str = "~0.01 $"
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": True,
            "action": "ask_deep_reasoning",
            "reason": reason,
            "estimated_cost": cost_str,
            "instruction_to_jarvis": (
                f"Les modèles de réflexion sur la clé gratuite ont épuisé leurs quotas. "
                f"Pour répondre avec l'API Thinking, il faut utiliser la clé payante ({cost_str}). "
                f"RÈGLE STRICTE : Il est impossible d'utiliser la clé payante sans accord préalable. "
                f"Explique la situation à Pierre avec ta voix Aoede, donne l'estimation ({cost_str}) et demande son accord oral."
            )
        }

    # Si Pierre a confirmé : tentative sur clé payante
    if client_paid:
        for m_id, m_label in models_to_try:
            try:
                print(f"[Reasoning Service] Thinking {m_id} avec Clé Payante...")
                response = await client_paid.aio.models.generate_content(
                    model=m_id,
                    contents=prompt,
                    config=config_thinking
                )
                text_output = (response.text or "").strip()
                if text_output:
                    return {
                        "source": "Google API",
                        "model_label": f"{m_label} (Clé Payante)",
                        "key_used": "Clé Payante",
                        "status": "completed",
                        "summary": text_output[:1800],
                        "full_text": text_output
                    }
            except Exception as m_err:
                print(f"[Reasoning Service] Modèle payant {m_id} indisponible ({m_err})...")

    return {
        "source": "Google API",
        "model_label": "Gemini Thinking",
        "status": "error",
        "summary": "Impossible d'exécuter la réflexion approfondie sur les clés configurées.",
        "full_text": ""
    }
