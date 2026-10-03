"""Exécuteur d'agents Antigravity CLI avec politique de repli, validation JSON stricte,
orchestration parallèle L2 (gather, cross-check, synthèse reduce, vérification bornée)
et bascule sous consentement vers la clé API payante en cas de dépassement de quota.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

import config
from services.antigravity_models import (
    MODEL_FLASH,
    MODEL_PRO,
    validate_model_and_effort,
)
from services.antigravity_prompts import (
    build_agentic_prompt,
    build_l2_agentic_prompt,
    build_json_retry_prompt,
    build_l2_synthesis_prompt,
)
from services.key_gate import PaidKeyConsentRequired, get_key, has_paid_consent
from services.model_routing.fallback_handler import cooldown_manager

logger = logging.getLogger("jarvis.agentic_runner")


@dataclass
class AgentOutput:
    """Structure de résultat standardisée pour une tâche agentique."""
    conclusion: str
    confidence: float
    sources: List[Any] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    artifacts: List[Any] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    model: str = ""
    effort: str = ""
    status: str = "success"  # "success" | "failed"
    raw_output: str = ""
    error: Optional[str] = None
    workspace: Optional[str] = None
    worker_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "sources": self.sources,
            "open_questions": self.open_questions,
            "artifacts": self.artifacts,
            "facts": self.facts,
            "hypotheses": self.hypotheses,
            "uncertainties": self.uncertainties,
            "model": self.model,
            "effort": self.effort,
            "status": self.status,
            "raw_output": self.raw_output,
            "error": self.error,
            "workspace": self.workspace,
            "worker_id": self.worker_id,
        }


@dataclass
class L2WorkerMission:
    """Spécification d'une mission spécialisée pour un agent parallèle L2."""
    worker_id: str
    role: str
    mission: str
    model: str = MODEL_FLASH
    effort: str = "medium"
    timeout: float = 120.0
    workspace: Optional[str] = None


@dataclass
class CrossCheckResult:
    """Résultat de la phase d'audit et de contre-vérification croisée entre agents L2."""
    passed: bool
    contradictions: List[str] = field(default_factory=list)
    unsourced_claims: List[str] = field(default_factory=list)
    invalid_outputs: List[str] = field(default_factory=list)
    agreement_score: float = 1.0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "contradictions": self.contradictions,
            "unsourced_claims": self.unsourced_claims,
            "invalid_outputs": self.invalid_outputs,
            "agreement_score": self.agreement_score,
            "summary": self.summary,
        }


@dataclass
class L2ExecutionResult:
    """Résultat complet d'une orchestration multi-agents parallèle L2."""
    status: str  # "completed" | "partial" | "failed" | "timeout"
    quality_gate_passed: bool
    successful_agents: List[AgentOutput] = field(default_factory=list)
    failed_agents: List[Dict[str, Any]] = field(default_factory=list)
    cross_check: CrossCheckResult = field(default_factory=lambda: CrossCheckResult(passed=False))
    synthesis: Optional[AgentOutput] = None
    iterations_run: int = 1
    max_iterations: int = 2
    duration_seconds: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "quality_gate_passed": self.quality_gate_passed,
            "successful_agents": [a.to_dict() for a in self.successful_agents],
            "failed_agents": self.failed_agents,
            "cross_check": self.cross_check.to_dict() if self.cross_check else {},
            "synthesis": self.synthesis.to_dict() if self.synthesis else None,
            "iterations_run": self.iterations_run,
            "max_iterations": self.max_iterations,
            "duration_seconds": round(self.duration_seconds, 2),
            "error": self.error,
            "metadata": self.metadata,
        }


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
    # Schéma 1 : standard classique
    classic_keys = {"conclusion", "confidence", "sources", "open_questions", "artifacts"}
    if classic_keys.issubset(payload.keys()):
        return True

    # Schéma 2 : L2 spécialisé (faits, sources, hypothèses, incertitudes, conclusion)
    has_conclusion = "conclusion" in payload
    has_sources = "sources" in payload
    has_facts = "facts" in payload or "faits" in payload
    has_hypotheses = "hypotheses" in payload or "hypothèses" in payload
    has_uncertainties = "uncertainties" in payload or "incertitudes" in payload or "open_questions" in payload

    if has_conclusion and has_sources and (has_facts or has_hypotheses or has_uncertainties):
        return True

    return False


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
    cwd: Optional[str] = None,
) -> Tuple[int, str, str]:
    """Exécute la commande via create_subprocess_exec (sans shell) dans un workspace isolé."""
    # Vérification explicite avant exécution
    for arg in cmd:
        if "--thinking" in arg:
            raise ValueError("L'utilisation du flag '--thinking' est strictement interdite.")

    work_dir = None
    if cwd:
        work_dir = os.path.abspath(cwd)
        os.makedirs(work_dir, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
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
            open_questions=list(parsed.get("open_questions") or parsed.get("uncertainties") or []),
            artifacts=list(parsed.get("artifacts", [])),
            facts=list(parsed.get("facts") or parsed.get("faits") or []),
            hypotheses=list(parsed.get("hypotheses") or parsed.get("hypothèses") or []),
            uncertainties=list(parsed.get("uncertainties") or parsed.get("incertitudes") or []),
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
    workspace: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> AgentOutput:
    """Exécute une tâche agentique via Antigravity CLI dans un workspace isolé."""
    valid_model, valid_effort = validate_model_and_effort(model, effort)
    exec_func = custom_exec_fn or _execute_subprocess

    # Vérification cooldown modèle
    if cooldown_manager.is_in_cooldown(valid_model) and valid_model == MODEL_PRO:
        valid_model = MODEL_FLASH
        valid_effort = "high"

    full_prompt = build_agentic_prompt(role, prompt)

    current_model = valid_model
    current_effort = valid_effort
    used_timeout_fallback = False

    async def _run_cli_cycle(m: str, eff: str, p: str, tout: float) -> Tuple[int, str, str]:
        cmd = _build_command(role=role, prompt=p, model=m, effort=eff)
        # Prise en compte de custom_exec_fn avec signature (cmd, timeout) ou (cmd, timeout, cwd)
        try:
            return await exec_func(cmd, tout, cwd=workspace)
        except TypeError:
            return await exec_func(cmd, tout)

    try:
        code, stdout, stderr = await _run_cli_cycle(current_model, current_effort, full_prompt, float(timeout))
    except asyncio.TimeoutError:
        if current_model == MODEL_PRO and not used_timeout_fallback:
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
                    workspace=workspace,
                    worker_id=worker_id,
                )
        else:
            return AgentOutput(
                conclusion=f"Échec : Timeout de l'agent ({current_model}/{current_effort}).",
                confidence=0.0,
                model=current_model,
                effort=current_effort,
                status="failed",
                error="TimeoutError",
                workspace=workspace,
                worker_id=worker_id,
            )

    combined_output = f"{stdout}\n{stderr}".strip()

    # Détection de quota agy
    if _is_quota_error(combined_output, code) or code == 429:
        cooldown_manager.mark_exhausted(current_model)
        user_consented = allow_paid_fallback or has_paid_consent(session_id=session_id, task_id=task_id)
        if user_consented:
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

    # Validation du JSON obligatoire
    payload = _extract_json_payload(stdout)
    if not (payload and _validate_json_schema(payload)):
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
                    workspace=workspace,
                    worker_id=worker_id,
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
                workspace=workspace,
                worker_id=worker_id,
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
            workspace=workspace,
            worker_id=worker_id,
        )

    return AgentOutput(
        conclusion=str(payload.get("conclusion", "")),
        confidence=float(payload.get("confidence", 1.0)),
        sources=list(payload.get("sources", [])),
        open_questions=list(payload.get("open_questions") or payload.get("uncertainties") or []),
        artifacts=list(payload.get("artifacts", [])),
        facts=list(payload.get("facts") or payload.get("faits") or []),
        hypotheses=list(payload.get("hypotheses") or payload.get("hypothèses") or []),
        uncertainties=list(payload.get("uncertainties") or payload.get("incertitudes") or []),
        model=current_model,
        effort=current_effort,
        status="success",
        raw_output=stdout,
        workspace=workspace,
        worker_id=worker_id,
    )


def cross_check_l2_results(
    results: List[AgentOutput],
    worker_missions: Optional[List[L2WorkerMission]] = None,
) -> CrossCheckResult:
    """Phase de cross-check : compare les résultats des agents L2, repère les contradictions,
    les affirmations sans source et les sorties invalides."""
    invalid_outputs: List[str] = []
    unsourced_claims: List[str] = []
    contradictions: List[str] = []

    valid_results: List[AgentOutput] = []
    for i, res in enumerate(results):
        worker_label = res.worker_id or f"Worker_{i+1}"
        if res.status != "success" or not res.conclusion:
            invalid_outputs.append(f"{worker_label}: Résultat invalide ou échec ({res.error or 'conclusion vide'}).")
            continue

        valid_results.append(res)
        facts = getattr(res, "facts", [])
        sources = res.sources or []

        # Affirmations sans sources
        if facts and not sources:
            unsourced_claims.append(f"{worker_label}: {len(facts)} faits affirmés sans aucune source citée.")
        elif not sources and not facts and "source" not in res.conclusion.lower() and len(res.conclusion) > 80:
            unsourced_claims.append(f"{worker_label}: Conclusion sans source citée.")

    # Détection de contradictions entre agents
    if len(valid_results) >= 2:
        conflict_pairs = [
            (r"\bcompatible\b", r"\bincompatible\b"),
            (r"\bpossible\b", r"\bimpossible\b"),
            (r"\bpositif\b", r"\bnégatif\b"),
            (r"\bdisponible\b", r"\bindisponible\b"),
            (r"\brecommandé\b", r"\bdéconseillé\b"),
            (r"\bvrai\b", r"\bfaux\b"),
            (r"\bsuccès\b", r"\béchec\b"),
        ]
        for j in range(len(valid_results)):
            for k in range(j + 1, len(valid_results)):
                w1 = valid_results[j]
                w2 = valid_results[k]
                l1 = w1.worker_id or f"Worker_{j+1}"
                l2 = w2.worker_id or f"Worker_{k+1}"

                c1_lower = w1.conclusion.lower()
                c2_lower = w2.conclusion.lower()

                for p_pos, p_neg in conflict_pairs:
                    if (re.search(p_pos, c1_lower) and re.search(p_neg, c2_lower)) or \
                       (re.search(p_neg, c1_lower) and re.search(p_pos, c2_lower)):
                        contradictions.append(f"Contradiction entre {l1} et {l2} ({p_pos}/{p_neg}).")
                        break

    total_workers = len(results)
    valid_count = len(valid_results)
    
    passed = len(invalid_outputs) == 0 and len(contradictions) == 0 and len(unsourced_claims) == 0 and valid_count > 0

    agreement_score = 1.0
    if total_workers > 0:
        penalty = (len(invalid_outputs) * 0.3) + (len(contradictions) * 0.3) + (len(unsourced_claims) * 0.2)
        agreement_score = max(0.0, min(1.0, 1.0 - penalty))

    summary = f"Cross-check L2: {valid_count}/{total_workers} valides, {len(contradictions)} contradictions, {len(unsourced_claims)} sans source."
    return CrossCheckResult(
        passed=passed,
        contradictions=contradictions,
        unsourced_claims=unsourced_claims,
        invalid_outputs=invalid_outputs,
        agreement_score=round(agreement_score, 2),
        summary=summary,
    )


async def run_l2_parallel_agents(
    goal: str,
    worker_missions: Optional[List[L2WorkerMission]] = None,
    max_workers: int = 3,
    max_iterations: int = 2,
    agent_timeout: float = 120.0,
    global_timeout: float = 300.0,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    allow_paid_fallback: bool = False,
    base_workspace: Optional[str] = None,
    custom_exec_fn: Optional[Callable] = None,
    execute_paid_api_fn: Optional[Callable] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
) -> L2ExecutionResult:
    """Orchestre l'exécution parallèle d'agents L2 Flash/Pro bornés (défaut 3) avec asyncio.gather,
    isolation stricte des workspaces, phase de cross-check (contradictions, sources, JSON),
    synthèse REDUCE par agent désigné, et boucle de vérification bornée (max_iterations=2).
    """
    t0 = time.perf_counter()
    eff_max = max(1, min(10, max_workers))
    tid = task_id or f"l2_task_{int(time.time() * 1000)}"
    root_ws = os.path.abspath(base_workspace or getattr(config, "WORKSPACE_DIR", "./workspace"))
    os.makedirs(root_ws, exist_ok=True)

    # 1. Définition des missions spécialisées
    missions: List[L2WorkerMission] = []
    if worker_missions:
        missions = list(worker_missions)[:eff_max]
    else:
        # 3 missions spécialisées par défaut pour L2
        default_roles = [
            ("prospector_1", "prospector", f"Collecte exhaustive des données, faits vérifiés et sources pour : {goal}", MODEL_FLASH, "medium"),
            ("critic_2", "critic", f"Analyse critique, détection des risques et examen logique pour : {goal}", MODEL_FLASH, "high"),
            ("architect_3", "architect", f"Synthèse structurelle, opportunités et recommandations pour : {goal}", MODEL_FLASH, "medium"),
        ]
        for wid, role, m_text, m_model, m_eff in default_roles[:eff_max]:
            missions.append(L2WorkerMission(
                worker_id=wid,
                role=role,
                mission=m_text,
                model=m_model,
                effort=m_eff,
                timeout=agent_timeout,
            ))

    # 2. Isolation des workspaces pour chaque agent
    for m in missions:
        if not m.workspace:
            agent_ws = os.path.join(root_ws, f"{tid}_{m.worker_id}")
            os.makedirs(agent_ws, exist_ok=True)
            m.workspace = agent_ws

    async def _execute_parallel_flow() -> L2ExecutionResult:
        iteration = 0
        current_missions = list(missions)
        successful_agents: List[AgentOutput] = []
        failed_agents: List[Dict[str, Any]] = []
        cross_check = CrossCheckResult(passed=False)
        last_results: List[AgentOutput] = []

        while iteration < max_iterations:
            iteration += 1
            if on_progress:
                await on_progress({
                    "step": "iteration_start",
                    "iteration": iteration,
                    "max_iterations": max_iterations,
                    "workers_count": len(current_missions),
                })

            # Exécution parallèle des agents via asyncio.gather
            async def _run_single_worker(wm: L2WorkerMission) -> AgentOutput:
                p_text = build_l2_agentic_prompt(wm.role, wm.mission, context=f"Mission L2 : {goal}")
                return await run_agentic(
                    role=wm.role,
                    prompt=p_text,
                    model=wm.model,
                    effort=wm.effort,
                    timeout=int(wm.timeout),
                    session_id=session_id,
                    task_id=f"{tid}_{wm.worker_id}",
                    allow_paid_fallback=allow_paid_fallback,
                    execute_paid_api_fn=execute_paid_api_fn,
                    custom_exec_fn=custom_exec_fn,
                    workspace=wm.workspace,
                    worker_id=wm.worker_id,
                )

            worker_tasks = [_run_single_worker(m) for m in current_missions]
            gathered_results = await asyncio.gather(*worker_tasks, return_exceptions=True)

            current_successful: List[AgentOutput] = []
            current_failed: List[Dict[str, Any]] = []

            for i, res in enumerate(gathered_results):
                wm = current_missions[i]
                if isinstance(res, PaidKeyConsentRequired):
                    raise res
                elif isinstance(res, AgentOutput):
                    if res.status == "success":
                        current_successful.append(res)
                    else:
                        current_failed.append({"worker_id": wm.worker_id, "error": res.error or "status_failed", "output": res.raw_output})
                elif isinstance(res, Exception):
                    current_failed.append({"worker_id": wm.worker_id, "error": str(res)})

            last_results = list(current_successful)
            failed_agents = current_failed

            # Phase de cross-check
            cross_check = cross_check_l2_results(current_successful, current_missions)

            if cross_check.passed and len(current_successful) == len(current_missions):
                successful_agents = current_successful
                break

            if iteration < max_iterations and len(current_successful) > 0:
                # Préparation d'une relance ciblée sur les anomalies du cross-check
                successful_agents = current_successful
                issues = cross_check.contradictions + cross_check.unsourced_claims
                refined_missions: List[L2WorkerMission] = []
                for m in current_missions:
                    refined_missions.append(L2WorkerMission(
                        worker_id=m.worker_id,
                        role=m.role,
                        mission=f"{m.mission}\n\nATTENTION : Corrige impérativement ces anomalies constatées :\n" + "\n".join(f"- {iss}" for iss in issues),
                        model=m.model,
                        effort=m.effort,
                        timeout=m.timeout,
                        workspace=m.workspace,
                    ))
                current_missions = refined_missions
            else:
                successful_agents = current_successful
                break

        # Phase REDUCE / Synthèse finale par agent désigné
        synthesis_output: Optional[AgentOutput] = None
        if successful_agents:
            synth_ws = os.path.join(root_ws, f"{tid}_synthesis")
            os.makedirs(synth_ws, exist_ok=True)
            findings_data = [
                {
                    "worker_id": a.worker_id,
                    "conclusion": a.conclusion,
                    "facts": a.facts,
                    "sources": a.sources,
                    "confidence": a.confidence,
                }
                for a in successful_agents
            ]
            synth_prompt = build_l2_synthesis_prompt(
                goal=goal,
                findings=findings_data,
                contradictions=cross_check.contradictions,
            )
            synthesis_output = await run_agentic(
                role="synthesis",
                prompt=synth_prompt,
                model=MODEL_PRO,
                effort="medium",
                timeout=int(agent_timeout),
                session_id=session_id,
                task_id=f"{tid}_synthesis",
                allow_paid_fallback=allow_paid_fallback,
                execute_paid_api_fn=execute_paid_api_fn,
                custom_exec_fn=custom_exec_fn,
                workspace=synth_ws,
                worker_id="synthesis_lead",
            )

        # Quality Gate indépendant
        all_workers_succeeded = len(successful_agents) == len(missions)
        quality_gate_passed = bool(
            all_workers_succeeded
            and cross_check.passed
            and synthesis_output is not None
            and synthesis_output.status == "success"
        )

        if quality_gate_passed:
            status = "completed"
        elif len(successful_agents) > 0:
            status = "partial"
        else:
            status = "failed"

        dur = time.perf_counter() - t0
        meta = {
            "workers_count": len(missions),
            "successful_count": len(successful_agents),
            "failed_count": len(failed_agents),
            "iterations": iteration,
            "duration_s": round(dur, 2),
            "status": status,
        }
        logger.info(
            f"[L2 Parallel Runner] Fin d'orchestration: {len(successful_agents)}/{len(missions)} agents réussis, "
            f"statut={status}, QG={quality_gate_passed}, durée={dur:.2f}s, itérations={iteration}"
        )

        return L2ExecutionResult(
            status=status,
            quality_gate_passed=quality_gate_passed,
            successful_agents=successful_agents,
            failed_agents=failed_agents,
            cross_check=cross_check,
            synthesis=synthesis_output,
            iterations_run=iteration,
            max_iterations=max_iterations,
            duration_seconds=dur,
            metadata=meta,
        )

    try:
        return await asyncio.wait_for(_execute_parallel_flow(), timeout=global_timeout)
    except asyncio.TimeoutError:
        dur = time.perf_counter() - t0
        logger.warning(f"[L2 Parallel Runner] Timeout global ({global_timeout}s) dépassé.")
        return L2ExecutionResult(
            status="timeout",
            quality_gate_passed=False,
            successful_agents=[],
            failed_agents=[{"error": f"Timeout global {global_timeout}s dépassé"}],
            cross_check=CrossCheckResult(passed=False, summary="Timeout global dépassé"),
            synthesis=None,
            iterations_run=1,
            max_iterations=max_iterations,
            duration_seconds=dur,
            error=f"Timeout global ({global_timeout}s) dépassé.",
            metadata={"timeout": global_timeout, "duration_s": round(dur, 2)},
        )

