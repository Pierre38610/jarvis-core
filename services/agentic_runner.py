"""Exécuteur d'agents Antigravity CLI avec politique de repli, validation JSON stricte
et bascule sous consentement vers la clé API payante en cas de dépassement de quota.
"""

import asyncio
import json
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from services.antigravity_models import (
    MODEL_FLASH,
    MODEL_PRO,
    validate_model_and_effort,
)
from services.antigravity_prompts import (
    build_agentic_prompt,
    build_json_retry_prompt,
)
from services.key_gate import PaidKeyConsentRequired, get_key, has_paid_consent


@dataclass
class AgentOutput:
    """Structure de résultat standardisée pour une tâche agentique."""
    conclusion: str
    confidence: float
    sources: List[Any] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    artifacts: List[Any] = field(default_factory=list)
    model: str = ""
    effort: str = ""
    status: str = "success"  # "success" | "failed"
    raw_output: str = ""
    error: Optional[str] = None


def _extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    """Tente d'extraire et désérialiser l'objet JSON requis depuis la réponse brute."""
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()
    
    # 1. Tentative directe
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Recherche d'un bloc ```json ... ``` ou ``` ... ```
    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_block:
        try:
            data = json.loads(json_block.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Recherche du premier { au dernier }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def _validate_json_schema(payload: Optional[Dict[str, Any]]) -> bool:
    """Vérifie la présence obligatoire des clés requises dans le JSON."""
    if not isinstance(payload, dict):
        return False
    required_keys = {"conclusion", "confidence", "sources", "open_questions", "artifacts"}
    return required_keys.issubset(payload.keys())


def _build_command(role: str, prompt: str, model: str, effort: str) -> List[str]:
    """Construit la liste des arguments de commande pour agy.
    
    Lève ValueError si '--thinking' est présent dans les arguments.
    """
    binary = shutil.which("agy") or "agy"
    cmd = [binary, role, prompt, "--model", model, "--effort", effort]

    for arg in cmd:
        if "--thinking" in arg:
            raise ValueError("L'utilisation du flag '--thinking' est strictement interdite.")

    return cmd


def _is_quota_error(output: str, exit_code: Optional[int]) -> bool:
    """Détecte si l'erreur correspond à un épuisement de quota CLI agy (429, ResourceExhausted, etc.)."""
    lowered = (output or "").lower()
    quota_terms = ["429", "quota", "resource_exhausted", "quotaexceeded", "rate limit"]
    return any(term in lowered for term in quota_terms)


async def _execute_subprocess(
    cmd: List[str],
    timeout: float,
) -> Tuple[int, str, str]:
    """Exécute la commande via create_subprocess_exec (sans shell)."""
    # Vérification explicite avant exécution
    for arg in cmd:
        if "--thinking" in arg:
            raise ValueError("L'utilisation du flag '--thinking' est strictement interdite.")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        raise

    stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
    return proc.returncode, stdout_str, stderr_str


async def _execute_gemini_paid_fallback(
    prompt: str,
    model: str,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    execute_paid_api_fn: Optional[Callable] = None,
) -> AgentOutput:
    """Exécute la tâche via l'API Gemini Flash/Pro avec la clé PAID (key_gate)."""
    # Récupère la clé payante via key_gate en forçant la raison de quota dépassé
    paid_api_key = get_key(
        purpose="agentic_fallback",
        session_id=session_id,
        task_id=task_id,
        require_paid=True,
        force_reason="cli_quota_exceeded",
        failure_detail="Quota Antigravity CLI dépassé, passage sur l'API Gemini payante autorisée.",
    )

    if execute_paid_api_fn is not None:
        raw_res = await execute_paid_api_fn(prompt=prompt, model=model, api_key=paid_api_key)
    else:
        # Implémentation standard google.genai / fallback
        import config
        gemini_model_name = getattr(config, "GEMINI_PRO_MODEL", "gemini-2.5-pro") if model == MODEL_PRO else getattr(config, "GEMINI_FLASH_MODEL", "gemini-2.5-flash")
        
        try:
            from google import genai
            client = genai.Client(api_key=paid_api_key)
            response = client.models.generate_content(
                model=gemini_model_name,
                contents=prompt,
            )
            raw_res = response.text or ""
        except Exception as e:
            # Fallback google.generativeai si ancien SDK
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=paid_api_key)
                m = legacy_genai.GenerativeModel(gemini_model_name)
                resp = await asyncio.to_thread(m.generate_content, prompt)
                raw_res = resp.text or ""
            except Exception as e2:
                raise RuntimeError(f"Erreur d'appel API Gemini Paid: {e2}") from e2

    parsed = _extract_json_payload(raw_res)
    if parsed and _validate_json_schema(parsed):
        return AgentOutput(
            conclusion=str(parsed.get("conclusion", "")),
            confidence=float(parsed.get("confidence", 1.0)),
            sources=list(parsed.get("sources", [])),
            open_questions=list(parsed.get("open_questions", [])),
            artifacts=list(parsed.get("artifacts", [])),
            model=model,
            effort="paid_api",
            status="success",
            raw_output=raw_res,
        )

    return AgentOutput(
        conclusion="L'API Gemini Paid a répondu mais sans le format JSON requis.",
        confidence=0.0,
        status="failed",
        model=model,
        effort="paid_api",
        raw_output=raw_res,
        error="Invalid JSON response from paid API fallback",
    )


async def run_agentic(
    role: str,
    prompt: str,
    model: str,
    effort: str,
    timeout: int = 300,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    allow_paid_fallback: bool = False,
    execute_paid_api_fn: Optional[Callable] = None,
    custom_exec_fn: Optional[Callable] = None,
) -> AgentOutput:
    """Exécute une tâche agentique via Antigravity CLI.
    
    Spécifications :
    - Validation model/effort avant le subprocess.
    - Exception immédiate si '--thinking' apparaît dans la commande.
    - create_subprocess_exec (aucun shell).
    - 1 seul repli autorisé : pro en timeout -> flash/high.
    - Sortie JSON obligatoire {conclusion, confidence, sources, open_questions, artifacts}, 1 relance si absente, puis failed.
    - Détecter une erreur de quota agy -> lever PaidKeyConsentRequired('cli_quota_exceeded').
      Si consentement accordé -> exécuter la tâche via l'API Gemini Flash/Pro avec la clé PAID, une seule fois.
    """
    # 1. Validation du modèle et de l'effort
    valid_model, valid_effort = validate_model_and_effort(model, effort)

    # Fonction interne d'exécution avec vérification
    exec_func = custom_exec_fn or _execute_subprocess

    # Préparation du prompt enrichi avec contraintes de rôle et format JSON
    full_prompt = build_agentic_prompt(role, prompt)

    current_model = valid_model
    current_effort = valid_effort
    used_timeout_fallback = False

    async def _run_cli_cycle(m: str, eff: str, p: str, tout: float) -> Tuple[int, str, str]:
        cmd = _build_command(role=role, prompt=p, model=m, effort=eff)
        return await exec_func(cmd, tout)

    # Exécution avec gestion du repli unique (pro en timeout -> flash/high)
    try:
        code, stdout, stderr = await _run_cli_cycle(current_model, current_effort, full_prompt, float(timeout))
    except asyncio.TimeoutError:
        if current_model == MODEL_PRO and not used_timeout_fallback:
            # Repli unique autorisé : pro en timeout -> flash/high
            used_timeout_fallback = True
            current_model = MODEL_FLASH
            current_effort = "high"
            try:
                code, stdout, stderr = await _run_cli_cycle(current_model, current_effort, full_prompt, float(timeout))
            except asyncio.TimeoutError:
                return AgentOutput(
                    conclusion="Échec : Timeout de l'agent après repli sur flash/high.",
                    confidence=0.0,
                    model=current_model,
                    effort=current_effort,
                    status="failed",
                    error="TimeoutError après repli unique flash/high",
                )
        else:
            return AgentOutput(
                conclusion=f"Échec : Timeout de l'agent ({current_model}/{current_effort}).",
                confidence=0.0,
                model=current_model,
                effort=current_effort,
                status="failed",
                error="TimeoutError",
            )

    combined_output = f"{stdout}\n{stderr}".strip()

    # Détection de quota agy
    if _is_quota_error(combined_output, code) or code == 429:
        # Vérification si l'utilisateur a déjà accordé son consentement
        user_consented = allow_paid_fallback or has_paid_consent(session_id=session_id, task_id=task_id)
        if user_consented:
            # Exécution unique via API Gemini payante
            return await _execute_gemini_paid_fallback(
                prompt=full_prompt,
                model=current_model,
                session_id=session_id,
                task_id=task_id,
                execute_paid_api_fn=execute_paid_api_fn,
            )
        else:
            raise PaidKeyConsentRequired(
                reason="cli_quota_exceeded",
                detail="Le quota de la commande agy est épuisé (429/quota). Clé payante requise.",
                purpose="agentic_fallback",
                task_id=task_id,
                session_id=session_id,
            )

    # Vérification de la présence du JSON obligatoire
    payload = _extract_json_payload(stdout)
    if not (payload and _validate_json_schema(payload)):
        # 1 seule relance autorisée pour exiger le format JSON
        retry_prompt = build_json_retry_prompt(full_prompt, stdout or combined_output)
        try:
            r_code, r_stdout, r_stderr = await _run_cli_cycle(current_model, current_effort, retry_prompt, float(timeout))
            r_payload = _extract_json_payload(r_stdout)
            if r_payload and _validate_json_schema(r_payload):
                payload = r_payload
                stdout = r_stdout
            else:
                return AgentOutput(
                    conclusion="Échec : Format JSON obligatoire absent après relance.",
                    confidence=0.0,
                    model=current_model,
                    effort=current_effort,
                    status="failed",
                    raw_output=r_stdout or r_stderr,
                    error="Mandatory JSON schema missing after 1 retry",
                )
        except Exception as retry_err:
            return AgentOutput(
                conclusion=f"Échec lors de la relance JSON : {retry_err}",
                confidence=0.0,
                model=current_model,
                effort=current_effort,
                status="failed",
                raw_output=stdout,
                error=str(retry_err),
            )

    if not payload or not _validate_json_schema(payload):
        return AgentOutput(
            conclusion="Échec : Format JSON manquant ou non conforme.",
            confidence=0.0,
            model=current_model,
            effort=current_effort,
            status="failed",
            raw_output=stdout,
            error="Invalid JSON output",
        )

    # Sortie valide avec schéma respecté
    return AgentOutput(
        conclusion=str(payload.get("conclusion", "")),
        confidence=float(payload.get("confidence", 1.0)),
        sources=list(payload.get("sources", [])),
        open_questions=list(payload.get("open_questions", [])),
        artifacts=list(payload.get("artifacts", [])),
        model=current_model,
        effort=current_effort,
        status="success",
        raw_output=stdout,
    )
