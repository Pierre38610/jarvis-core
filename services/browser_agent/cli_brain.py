"""Cerveau décisionnel et vérificateur du Browser Agent Jarvis via Antigravity CLI (agy)."""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

import config
from google_antigravity import AntigravityAgent

logger = logging.getLogger("jarvis.browser_agent.cli_brain")

S4_FORMAT_SPEC = (
    '{"thought":"une phrase","actions":[{"type":"click","id":12}],'
    '"need_screenshot":false,"done":false,"result":"","handoff":null} '
    'Types d\'action : click{id} | type{id,text,enter?:bool} | select{id,value} | '
    'scroll{direction:"down"|"up"} | goto{url} (uniquement pour start_url ou une URL lue dans la page) | '
    'wait{seconds<=120} | back{} | extract{} (renvoie le texte principal complet de la page). '
    'handoff : null ou {"reason":"captcha|login|2fa|choix_utilisateur","message":"phrase pour l\'utilisateur"}.'
)

S5_RULES_SUMMARY = (
    "1. Clic strictement interdit sur les boutons d'achat/paiement final (payer, commander, buy now, valider commande...) : arrêter la tâche quand tout est prêt.\n"
    "2. Ne jamais saisir de mot de passe, numéro de carte bancaire ou CVV : déclencher un handoff (captcha|login|2fa|choix_utilisateur).\n"
    "3. Exécuter 1 à 3 actions maximum par étape parmi les types autorisés (click, type, select, scroll, goto, wait, back, extract)."
)


def extract_first_json(text: str) -> Optional[Dict[str, Any]]:
    """Extrait le premier objet JSON valide du texte en ignorant tout texte parasite."""
    if not text or not text.strip():
        return None

    decoder = json.JSONDecoder()
    start_pos = 0
    text_len = len(text)

    while start_pos < text_len:
        idx = text.find("{", start_pos)
        if idx == -1:
            break
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        except Exception:
            pass
        start_pos = idx + 1

    return None


def _validate_decide_keys(payload: Any) -> Optional[Dict[str, Any]]:
    """Valide la présence et le type des clés minimales requises pour une décision S4."""
    if not isinstance(payload, dict):
        return None

    if "actions" not in payload or not isinstance(payload["actions"], list):
        return None

    if "done" not in payload:
        return None

    return {
        "thought": str(payload.get("thought", "")),
        "actions": payload["actions"],
        "need_screenshot": bool(payload.get("need_screenshot", False)),
        "done": bool(payload.get("done", False)),
        "result": str(payload.get("result", "")),
        "handoff": payload.get("handoff", None),
    }


def _validate_verify_keys(payload: Any) -> Optional[Dict[str, Any]]:
    """Valide la présence et le type des clés requises pour une vérification."""
    if not isinstance(payload, dict):
        return None

    if "ok" not in payload:
        return None

    return {
        "ok": bool(payload.get("ok", False)),
        "reason": str(payload.get("reason", "")),
    }


async def _call_agy(prompt: str, model: str, timeout: float) -> str:
    """Exécute un prompt via AntigravityAgent (agy CLI) et renvoie le texte brut sans le flag --thinking."""
    agent = AntigravityAgent(model=model)
    task_result = await asyncio.wait_for(agent.run_cli_task_stream(prompt), timeout=timeout)
    return getattr(task_result, "summary", "") or ""


def _format_history(history: Optional[List[Any]]) -> str:
    """Formate les 6 dernières entrées de l'historique sur une ligne chacune."""
    if not history:
        return "Aucun historique."

    recent = history[-6:]
    lines = []
    for item in recent:
        if isinstance(item, (dict, list)):
            lines.append(json.dumps(item, ensure_ascii=False))
        else:
            lines.append(str(item).replace("\n", " ").strip())
    return "\n".join(f"- {line}" for line in lines)


def _format_snapshot_elements(elements: Any) -> str:
    """Formate les éléments du snapshot pour le prompt."""
    if isinstance(elements, list):
        return "\n".join(str(el) for el in elements[:150])
    return str(elements or "")


async def decide(
    goal: str,
    recipe_text: Optional[str],
    memory_hint: Optional[str],
    snapshot: Dict[str, Any],
    history: List[Any],
    screenshot_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Demande au CLI agy la prochaine action de navigation.

    Construit un prompt court en français selon les spécifications S2, S4 et S5.
    Effectue un seul essai de rattrapage si la réponse n'est pas un JSON valide.
    """
    model = (
        getattr(config, "BROWSER_VISION_MODEL", "gemini-3.8-flash")
        if screenshot_path
        else getattr(config, "BROWSER_BRAIN_MODEL", "gemini-3.8-flash")
    )
    timeout = getattr(config, "BROWSER_CLI_TIMEOUT", 90)

    url = snapshot.get("url", "")
    title = snapshot.get("title", "")
    elements_str = _format_snapshot_elements(snapshot.get("elements", []))
    text_content = str(snapshot.get("text", ""))[:1500]
    history_str = _format_history(history)

    prompt_parts = [
        "Tu pilotes un navigateur. Réponds UNIQUEMENT avec un objet JSON valide.",
        f"Format JSON attendu :\n{S4_FORMAT_SPEC}",
        f"Règles strictes :\n{S5_RULES_SUMMARY}",
        f"Objectif : {goal}",
        f"Recette : {recipe_text or 'Aucune'}",
        f"Indice mémoire : {memory_hint or 'Aucun'}",
        f"Page actuelle :\n- URL : {url}\n- Titre : {title}\n- Éléments :\n{elements_str}\n- Texte visible :\n{text_content}",
        f"Historique récent (dernières actions et résultats) :\n{history_str}",
    ]

    if screenshot_path:
        abs_img_path = os.path.abspath(screenshot_path)
        prompt_parts.append(f"Ouvre et analyse l'image {abs_img_path} avant de répondre.")

    full_prompt = "\n\n".join(prompt_parts)

    # 1ère tentative
    try:
        raw_output = await _call_agy(full_prompt, model=model, timeout=timeout)
        parsed = extract_first_json(raw_output)
        validated = _validate_decide_keys(parsed)
        if validated is not None:
            return validated
    except Exception as exc:
        logger.warning("Échec ou timeout lors du premier appel agy decide : %s", exc)

    # UN seul nouvel essai en cas de JSON invalide
    logger.info("Réponse agy invalide pour decide, tentative de réessai...")
    retry_prompt = (
        f"{full_prompt}\n\n"
        "Ta réponse précédente n'était pas du JSON valide. "
        "Réponds UNIQUEMENT avec un objet JSON valide correspondant au format demandé."
    )

    try:
        raw_output_retry = await _call_agy(retry_prompt, model=model, timeout=timeout)
        parsed_retry = extract_first_json(raw_output_retry)
        validated_retry = _validate_decide_keys(parsed_retry)
        if validated_retry is not None:
            return validated_retry
    except Exception as exc:
        logger.warning("Échec ou timeout lors du réessai agy decide : %s", exc)

    return {"actions": [], "done": False, "error": "invalid_json"}


async def verify(
    goal: str,
    success_criteria: str,
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Vérifie si l'objectif de navigation est atteint selon le critère de réussite."""
    model = getattr(config, "BROWSER_VERIFIER_MODEL", "gemini-3.8-flash")
    timeout = getattr(config, "BROWSER_CLI_TIMEOUT", 90)

    url = snapshot.get("url", "")
    title = snapshot.get("title", "")
    elements_str = _format_snapshot_elements(snapshot.get("elements", []))
    text_content = str(snapshot.get("text", ""))[:1500]

    prompt = (
        "Tu es un vérificateur de navigation web. Réponds UNIQUEMENT avec un objet JSON valide : "
        '{"ok": true|false, "reason": "explication concise"}.\n\n'
        f"Objectif : {goal}\n"
        f"Critère de réussite : {success_criteria}\n\n"
        f"Page actuelle :\n- URL : {url}\n- Titre : {title}\n- Éléments :\n{elements_str}\n- Texte visible :\n{text_content}\n\n"
        "L'objectif est-il atteint conformément au critère de réussite ?"
    )

    # 1ère tentative
    try:
        raw_output = await _call_agy(prompt, model=model, timeout=timeout)
        parsed = extract_first_json(raw_output)
        validated = _validate_verify_keys(parsed)
        if validated is not None:
            return validated
    except Exception as exc:
        logger.warning("Échec ou timeout lors du premier appel agy verify : %s", exc)

    # UN seul nouvel essai
    logger.info("Réponse agy invalide pour verify, tentative de réessai...")
    retry_prompt = (
        f"{prompt}\n\n"
        "Ta réponse précédente n'était pas du JSON valide. "
        "Réponds UNIQUEMENT avec un objet JSON valide au format : {\"ok\": bool, \"reason\": \"...\"}."
    )

    try:
        raw_output_retry = await _call_agy(retry_prompt, model=model, timeout=timeout)
        parsed_retry = extract_first_json(raw_output_retry)
        validated_retry = _validate_verify_keys(parsed_retry)
        if validated_retry is not None:
            return validated_retry
    except Exception as exc:
        logger.warning("Échec ou timeout lors du réessai agy verify : %s", exc)

    return {"ok": False, "reason": "invalid_json"}


async def selftest_vision(test_image_dir: Optional[str] = None) -> Dict[str, Any]:
    """Crée une image PNG 200x80 avec le texte 'JARVIS42' et demande à agy le texte écrit dessus.

    Fonction de diagnostic manuel : ne pas exécuter automatiquement.
    """
    import tempfile
    from PIL import Image, ImageDraw

    out_dir = test_image_dir or tempfile.gettempdir()
    img_path = os.path.join(out_dir, "jarvis_selftest_vision.png")

    # Image 200x80 blanche avec texte noir
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 30), "JARVIS42", fill=(0, 0, 0))
    img.save(img_path)

    prompt = (
        f"Ouvre et analyse l'image {os.path.abspath(img_path)} avant de répondre. "
        "Quel est le texte exact écrit sur cette image ? "
        "Réponds UNIQUEMENT avec un objet JSON valide au format : {\"text\": \"...\"}"
    )

    model = getattr(config, "BROWSER_VISION_MODEL", "gemini-3.8-flash")
    timeout = getattr(config, "BROWSER_CLI_TIMEOUT", 90)

    raw = await _call_agy(prompt, model=model, timeout=timeout)
    parsed = extract_first_json(raw)
    return {
        "image_path": img_path,
        "raw_response": raw,
        "parsed": parsed,
    }
