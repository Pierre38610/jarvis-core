"""core/tools/dispatcher.py
Dispatch de chaque appel d'outil Gemini Live vers le service métier approprié.
Retourne systématiquement un dict tool_resp prêt à être envoyé via send_tool_response().
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

from google.genai import types

import config
logger = logging.getLogger("jarvis.dispatcher")
from google_antigravity import resolve_antigravity_model, is_stop_directive
from services.google_antigravity import (
    MODEL_FLASH,
    MODEL_PRO,
    run_agentic,
    AgentOutput,
    verify_antigravity_cli_ready,
)
from services.memory_service import memory_service
from services.memory import vector_memory
from services.unified_memory import unified_memory_manager
from services.reasoning_service import run_deep_reasoning
from services.browser_service import (
    search_web, run_browser_task, open_browser_window, interact_web_page,
    prepare_web_cart_or_checkout, send_page_to_kindle, send_file_to_kindle_web,
    list_installed_chrome_extensions
)
from services.browser_agent.loop import (
    BrowserTask,
    run_browser_task as run_browser_agent_task,
    TASKS as BROWSER_TASKS,
    get_task as get_browser_task,
)
from services.voice_injection_queue import voice_injection_queue, InjectionPriority
from services.download_service import download_file, send_to_ereader, search_and_download_ebook
from services.system_service import get_system_status, launch_application
from services.email_service import send_email_async, read_received_emails_async
from services.console_monitor import console_monitor
from services.supervision_service import supervision_service
from services.media_service import play_on_stremio
from services.spotify_service import spotify_service
from services.cache import cache_service
from services.briefing_service import briefing_service
from services.transport_service import transport_service
from services.deep_research_service import deep_research_service
from services.workspace_service import workspace_service

from core.shared_state import (
    active_task_controller,
    broadcast_supervision,
    stop_active_task,
    estimate_tool_cost,
    safe_send_live_client_content,
    spawn_subagent,
    update_subagent,
    complete_subagent,
    clear_all_subagents,
    broadcast_subagents,
)


from services.metrics_service import metrics_service
from core.tools.result import ToolResult, normalize_result
from core.tools.arg_validator import validate_tool_arguments
from services.key_gate import (
    PaidKeyConsentRequired,
    is_qualified_free_key_failure,
    set_pending_action,
    get_pending_action,
    clear_pending_action,
    grant_paid_consent,
    consume_paid_consent,
)
from core.tools.verifier import (
    verify_email_sent,
    verify_presentation_slides,
    verify_spreadsheet_file,
    verify_downloaded_file,
    verify_application_process,
    verify_calendar_event,
    verify_saved_memory,
    verify_browser_opened,
)


def _infer_tool_tier_and_cost(
    name: str,
    args: dict,
    is_paid_live: bool,
    res: Optional[dict] = None
) -> tuple[Optional[int], float]:
    """Déduit le tier cognitif (1, 2, 3) et le coût estimé pour l'observabilité."""
    args = args or {}
    tier = None
    cost = 0.0

    # 1. Tier cognitif
    if name in ("generate_book_summary", "curation_livre_synthese", "list_workspace_files", "read_workspace_file", "search_workspace_files"):
        tier = 1
    elif name in (
        "draft_email_response", "triage_et_brouillon_email",
        "rechercher_train", "search_train_routes",
        "generate_spreadsheet", "generer_fichier_tableur"
    ):
        tier = 2
    elif name in (
        "system_self_healing", "auto_guerison_systeme",
        "launch_deep_research", "deep_research", "lancer_mission_deep_research"
    ):
        tier = 3
    elif name in ("ask_deep_reasoning", "deep_reasoning"):
        m_lower = str(args.get("model") or "").lower()
        ir_lower = str(args.get("intensite_reflexion") or "").lower()
        if any(k in ir_lower for k in ["rapide", "tier1", "tier 1", "flash-low"]) or any(k in m_lower for k in ["flash-low", "low", "tier1"]):
            tier = 1
        elif any(k in ir_lower for k in ["approfondie", "tier3", "tier 3", "pro-high", "fond", "ingenierie"]) or any(k in m_lower for k in ["pro-high", "tier3", "gemini-3.1-pro"]):
            tier = 3
        else:
            tier = 2

    if isinstance(res, dict):
        if "cognitive_tier" in res and isinstance(res["cognitive_tier"], int):
            tier = res["cognitive_tier"]
        elif "tier" in res and isinstance(res["tier"], int):
            tier = res["tier"]

    # 2. Coût estimé
    if name in ("run_browser_task", "browser_task"):
        cost = 0.02
    elif name in ("ask_deep_reasoning", "deep_reasoning"):
        if tier == 3:
            cost = 0.03
        elif tier == 2:
            cost = 0.015
        elif tier == 1:
            cost = 0.001
        else:
            cost = 0.02
    elif name in ("launch_deep_research", "deep_research", "lancer_mission_deep_research"):
        cost = 0.05
    elif name in ("run_agentic_task", "run_agent_task"):
        cost = 0.03
    elif is_paid_live:
        cost = 0.005

    return tier, cost


def _resolve_agy_model(model_override: Optional[str], default: str = MODEL_PRO) -> str:
    if not model_override:
        return default
    m = str(model_override).lower().strip()
    if "flash" in m:
        return MODEL_FLASH
    if "pro" in m:
        return MODEL_PRO
    return default


def _resolve_agy_effort(effort_override: Optional[str], default: str = "high") -> str:
    if not effort_override:
        return default
    e = str(effort_override).lower().strip()
    if e in ("low", "medium", "high"):
        return e
    return default


async def dispatch_tool(
    name: str,
    args: dict,
    websocket: Any = None,
    session: Any = None,
    is_paid_live: bool = False,
    live_display_label: str = "Gemini Live",
) -> dict:
    """
    Dispatch l'appel d'outil `name` avec ses `args` et retourne le dict tool_resp.
    Enveloppe systématiquement le retour avec normalize_result() pour garantir
    l'application inviolable du contrat ToolResult (5 statuts, verified, evidence).
    Instrumenté pour l'observabilité de manière non-bloquante.
    """
    t0 = time.perf_counter()
    status = "success"
    res = None
    tool_result: Optional[ToolResult] = None
    try:
        raw_res = await _execute_dispatch_tool(
            name=name,
            args=args,
            websocket=websocket,
            session=session,
            is_paid_live=is_paid_live,
            live_display_label=live_display_label,
        )
        tool_result = normalize_result(name, raw_res)
        res = tool_result.to_dict()

        if tool_result.status == "failed":
            status = "failure"
        elif tool_result.status == "started":
            status = "started"
        elif tool_result.status == "needs_user":
            status = "needs_user"
        elif tool_result.status == "partial":
            status = "partial"
        else:
            status = "success"

        http_code = res.get("http_code") or res.get("status_code") or (200 if tool_result.status in ("done", "started") else 500)
        logger.info(
            "TOOL_RESULT name=%s http=%s status=%s verified=%s evidence=%s",
            name,
            http_code,
            tool_result.status,
            tool_result.verified,
            tool_result.evidence,
        )

        return res
    except PaidKeyConsentRequired as exc:
        status = "needs_user"
        set_pending_action(
            name=name,
            args=args,
            reason=exc.reason,
            detail=exc.detail,
            purpose=exc.purpose,
            task_id=exc.task_id,
            session_id=exc.session_id,
            extra={
                "websocket": websocket,
                "session": session,
                "is_paid_live": is_paid_live,
                "live_display_label": live_display_label,
            },
        )
        if exc.reason == "cli_quota_exceeded":
            user_msg = "Le quota des agents Antigravity est dépassé. Veux-tu que j'utilise la clé payante pour terminer ?"
        else:
            user_msg = f"La clé gratuite a échoué ({exc.detail}). Veux-tu que j'utilise la clé payante pour terminer ?"

        tool_result = ToolResult.needs_user(
            user_message=user_msg,
            question=user_msg,
            evidence=f"Paid key consent required: {exc.reason}",
            data={
                "reason": exc.reason,
                "detail": exc.detail,
                "purpose": exc.purpose,
                "task_id": exc.task_id,
                "pending_tool": name,
            },
        )
        res = tool_result.to_dict()
        logger.info(
            "TOOL_RESULT name=%s http=402 status=%s verified=%s evidence=%s",
            name,
            tool_result.status,
            tool_result.verified,
            tool_result.evidence,
        )
        return res
    except asyncio.TimeoutError:
        status = "timeout"
        tool_result = ToolResult.failed(
            user_message=f"L'opération '{name}' a pris trop de temps.",
            error_hint="timeout",
            evidence="timeout",
        )
        res = tool_result.to_dict()
        logger.warning(
            "TOOL_RESULT name=%s http=408 status=%s verified=%s evidence=%s",
            name,
            tool_result.status,
            tool_result.verified,
            tool_result.evidence,
        )
        return res
    except Exception as exc:
        is_qual, detail = is_qualified_free_key_failure(exc)
        if is_qual:
            status = "needs_user"
            set_pending_action(
                name=name,
                args=args,
                reason="free_key_failure",
                detail=detail,
                purpose=name,
                extra={
                    "websocket": websocket,
                    "session": session,
                    "is_paid_live": is_paid_live,
                    "live_display_label": live_display_label,
                },
            )
            user_msg = f"La clé gratuite a échoué ({detail}). Veux-tu que j'utilise la clé payante pour terminer ?"
            tool_result = ToolResult.needs_user(
                user_message=user_msg,
                question=user_msg,
                evidence="Paid key consent required: free_key_failure",
                data={
                    "reason": "free_key_failure",
                    "detail": detail,
                    "purpose": name,
                    "pending_tool": name,
                },
            )
            res = tool_result.to_dict()
            logger.info(
                "TOOL_RESULT name=%s http=429 status=%s verified=%s evidence=%s",
                name,
                tool_result.status,
                tool_result.verified,
                tool_result.evidence,
            )
            return res

        status = "failure"
        tool_result = ToolResult.failed(
            user_message=f"L'outil '{name}' a rencontré une erreur d'exécution.",
            error_hint=str(exc)
        )
        res = tool_result.to_dict()
        logger.info(
            "TOOL_RESULT name=%s http=500 status=%s verified=%s evidence=%s",
            name,
            tool_result.status,
            tool_result.verified,
            tool_result.evidence,
        )
        return res
    finally:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        tier, cost_est = _infer_tool_tier_and_cost(name, args, is_paid_live, res)
        is_verified = tool_result.verified if tool_result else False
        metrics_service.record_tool_call_background(
            tool_name=name,
            status=status,
            latency_ms=latency_ms,
            cognitive_tier=tier,
            cost_est=cost_est,
            is_paid_key=bool(is_paid_live or cost_est > 0),
            metadata={
                "args_keys": list(args.keys()) if isinstance(args, dict) else [],
                "verified": is_verified,
            },
        )


async def _execute_dispatch_tool(
    name: str,
    args: dict,
    websocket,
    session,
    is_paid_live: bool,
    live_display_label: str,
) -> dict:
    """
    Dispatch l'appel d'outil `name` avec ses `args` et retourne le dict tool_resp.
    Toute la logique métier est ici, séparée de la boucle WebSocket voice.
    """

    # ─── 0. Validation stricte des arguments et confirmation utilisateur ───────
    val_res = validate_tool_arguments(name=name, args=args)
    if val_res is not None:
        return val_res

    # ─── stop_current_action ───────────────────────────────────────────────────
    if name in ("stop_current_action", "stop"):
        stop_reason = args.get("reason", "Arrêt demandé par Pierre")
        try:
            for b_task in list(BROWSER_TASKS.values()):
                if b_task.status == "running" or not b_task.cancel_event.is_set():
                    b_task.cancel_event.set()
                    b_task.status = "cancelled"
        except Exception as e:
            logger.warning(f"[Dispatcher] Erreur annulation BrowserTask: {e}")
        await stop_active_task(source="tool_stop", reason=stop_reason)
        return {
            "status": "stopped",
            "message": f"Action immédiatement et totalement arrêtée ({stop_reason}).",
            "instruction_to_jarvis": "L'action en cours a été immédiatement et totalement arrêtée. Confirme brièvement et calmement à Pierre avec ta voix Aoede que l'action est stoppée."
        }

    # ─── confirm_paid_key ──────────────────────────────────────────────────────
    elif name in ("confirm_paid_key", "confirmer_cle_payante"):
        accept = bool(args.get("accept", False))
        pending = get_pending_action()
        if not pending:
            return ToolResult.failed(
                user_message="Aucune action en attente d'autorisation de clé payante.",
                error_hint="no_pending_action"
            )

        if not accept:
            clear_pending_action()
            return ToolResult.failed(
                user_message="Utilisation de la clé payante refusée. L'action n'a pas été exécutée.",
                error_hint="paid_key_rejected"
            )

        # Pierre a accepté d'utiliser la clé payante pour cette tâche
        grant_paid_consent(
            session_id=pending.session_id,
            reason=pending.reason,
            scope="this_task",
            task_id=pending.task_id,
        )
        saved_name = pending.name
        saved_args = dict(pending.args)
        if "confirmed_by_user" in saved_args or saved_name in ("ask_deep_reasoning", "download_file"):
            saved_args["confirmed_by_user"] = True

        extra_ctx = pending.extra or {}
        ws = extra_ctx.get("websocket") or websocket
        sess = extra_ctx.get("session") or session
        clear_pending_action()

        try:
            res = await dispatch_tool(
                name=saved_name,
                args=saved_args,
                websocket=ws,
                session=sess,
                is_paid_live=True,
                live_display_label=live_display_label,
            )
            return res
        finally:
            consume_paid_consent(session_id=pending.session_id, task_id=pending.task_id)


    # ─── guide_active_task ─────────────────────────────────────────────────────
    elif name in ("guide_active_task", "guide"):
        directive = args.get("directive", "")
        if active_task_controller["info"]["running"]:
            await active_task_controller["queue"].put(directive)
            active_task_controller.setdefault("directives", []).append(directive)
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Consigne en direct prise en compte : {directive}.", "voice": False}))
        return {"status": "adapted", "directive": directive, "message": f"Consigne '{directive}' transmise en direct à Antigravity CLI sur le VPS."}

    # ─── set_browser_link ──────────────────────────────────────────────────────
    elif name in ("set_browser_link", "browser_link"):
        link_url = args.get("url", "")
        link_title = args.get("title") or "Page sélectionnée"
        supervision_service.track_browser_window(link_url, link_title)
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "browser_update", "url": link_url, "title": link_title, "screenshot": "/static/latest_screenshot.jpg"}))
        return {"status": "updated", "url": link_url, "title": link_title, "message": f"Le lien {link_url} a été positionné dans le HUD mobile."}

    # ─── run_agentic_task / run_agent_task (Priorité 1 Agentic Runner) ────────
    elif name in ("run_agentic_task", "run_agent_task"):
        objectif = args.get("objectif") or args.get("goal") or args.get("task") or ""
        contexte = args.get("contexte") or args.get("context") or ""
        livrable_attendu = args.get("livrable_attendu") or args.get("deliverable") or ""
        model_override = args.get("model_override") or args.get("model")
        effort_override = args.get("effort_override") or args.get("effort")
        timeout = int(args.get("timeout", 300))

        cli_ok, cli_err, _ = await verify_antigravity_cli_ready()
        if not cli_ok:
            return ToolResult.failed(
                user_message="Antigravity CLI n'est pas disponible sur le serveur VPS.",
                error_hint=cli_err or "cli_not_ready",
                verified=False,
            )

        model = _resolve_agy_model(model_override, default=MODEL_PRO)
        effort = _resolve_agy_effort(effort_override, default="high")

        full_prompt = f"Objectif : {objectif}"
        if contexte:
            full_prompt += f"\nContexte : {contexte}"
        if livrable_attendu:
            full_prompt += f"\nLivrable attendu : {livrable_attendu}"

        agent_id = f"agy_task_{int(time.time()*1000)}"
        t0 = time.perf_counter()
        await spawn_subagent(
            agent_id=agent_id,
            name="Agent Antigravity",
            role="Exécution Tâche",
            activity="coding",
            task=f"{objectif[:60]} ({model}/{effort})",
            model=model,
        )

        try:
            await update_subagent(agent_id, activity="thinking", task=f"Exécution agentique en cours ({model}/{effort})...")
            out: AgentOutput = await run_agentic(
                role="general_agent",
                prompt=full_prompt,
                model=model,
                effort=effort,
                timeout=timeout,
                session_id=getattr(session, "id", None) if session else None,
                task_id=agent_id,
                allow_paid_fallback=bool(active_task_controller.get("paid_consent_given", False)),
            )
            duration = time.perf_counter() - t0
            summary = f"{out.conclusion[:80]} (modèle: {model}, effort: {effort}, durée: {duration:.1f}s)"
            await complete_subagent(agent_id, summary=summary)

            if out.status == "success":
                return ToolResult.done(
                    user_message=out.conclusion,
                    evidence=f"Modèle: {out.model}, Effort: {out.effort}, Durée: {duration:.1f}s, Confiance: {out.confidence}",
                    verified=True,
                    data={
                        "conclusion": out.conclusion,
                        "confidence": out.confidence,
                        "sources": out.sources,
                        "open_questions": out.open_questions,
                        "artifacts": out.artifacts,
                        "model": out.model,
                        "effort": out.effort,
                        "duration_s": round(duration, 2),
                    },
                )
            else:
                return ToolResult.failed(
                    user_message=out.conclusion or "La tâche agentique a échoué.",
                    error_hint=out.error or "agentic_execution_failed",
                    verified=False,
                    data={
                        "error": out.error,
                        "model": out.model,
                        "effort": out.effort,
                        "duration_s": round(duration, 2),
                    },
                )
        except Exception as e:
            duration = time.perf_counter() - t0
            await complete_subagent(agent_id, summary=f"Erreur: {str(e)[:80]} (durée: {duration:.1f}s)")
            return ToolResult.failed(
                user_message=f"Erreur lors de l'exécution de la tâche agentique : {str(e)}",
                error_hint=str(e),
                verified=False,
            )

    # ─── ask_deep_reasoning (Moteur Antigravity CLI VPS) ──────────────────────
    elif name in ("ask_deep_reasoning", "deep_reasoning"):
        question = args.get("question") or args.get("query") or ""
        model_override = args.get("model_override") or args.get("model")
        effort_override = args.get("effort_override") or args.get("intensite_reflexion")

        cli_ok, cli_err, _ = await verify_antigravity_cli_ready()
        if not cli_ok:
            return ToolResult.failed(
                user_message="Antigravity CLI n'est pas disponible sur le serveur VPS.",
                error_hint=cli_err or "cli_not_ready",
                verified=False,
            )

        model = _resolve_agy_model(model_override, default=MODEL_PRO)
        if effort_override == "rapide":
            effort = "low"
        elif effort_override == "tactique":
            effort = "medium"
        elif effort_override == "approfondie":
            effort = "high"
        else:
            effort = _resolve_agy_effort(effort_override, default="high")

        agent_id = f"agy_reasoning_{int(time.time()*1000)}"
        t0 = time.perf_counter()
        await spawn_subagent(
            agent_id=agent_id,
            name="Analyste Raisonnement",
            role="Raisonnement & Décision",
            activity="thinking",
            task=f"{question[:60]} ({model}/{effort})",
            model=model,
        )

        try:
            await update_subagent(agent_id, activity="thinking", task=f"Raisonnement approfondi ({model}/{effort})...")
            out: AgentOutput = await run_agentic(
                role="reasoning",
                prompt=question,
                model=model,
                effort=effort,
                timeout=300,
                session_id=getattr(session, "id", None) if session else None,
                task_id=agent_id,
                allow_paid_fallback=bool(active_task_controller.get("paid_consent_given", False)),
            )
            duration = time.perf_counter() - t0
            summary = f"{out.conclusion[:80]} (modèle: {model}, effort: {effort}, durée: {duration:.1f}s)"
            await complete_subagent(agent_id, summary=summary)

            if out.status == "success":
                return ToolResult.done(
                    user_message=out.conclusion,
                    evidence=f"Modèle: {out.model}, Effort: {out.effort}, Durée: {duration:.1f}s, Confiance: {out.confidence}",
                    verified=True,
                    data={
                        "conclusion": out.conclusion,
                        "confidence": out.confidence,
                        "sources": out.sources,
                        "open_questions": out.open_questions,
                        "artifacts": out.artifacts,
                        "model": out.model,
                        "effort": out.effort,
                        "duration_s": round(duration, 2),
                    },
                )
            else:
                return ToolResult.failed(
                    user_message=out.conclusion or "L'analyse approfondie a échoué.",
                    error_hint=out.error or "reasoning_failed",
                    verified=False,
                    data={
                        "error": out.error,
                        "model": out.model,
                        "effort": out.effort,
                        "duration_s": round(duration, 2),
                    },
                )
        except Exception as e:
            duration = time.perf_counter() - t0
            await complete_subagent(agent_id, summary=f"Erreur: {str(e)[:80]} (durée: {duration:.1f}s)")
            return ToolResult.failed(
                user_message=f"Erreur lors du raisonnement approfondi : {str(e)}",
                error_hint=str(e),
                verified=False,
            )

    # ─── launch_deep_research (Deep Research 3 phases Map-Reduce) ─────────────
    elif name in ("launch_deep_research", "deep_research", "lancer_mission_deep_research"):
        consigne = args.get("consigne") or args.get("consigne_utilisateur") or args.get("sujet") or ""
        envoyer_email = bool(args.get("envoyer_email", False))
        destinataire_email = args.get("destinataire_email")

        # 1. Tentative préalable via Browser Agent avec recipe="gemini_deep_research"
        try:
            bt_id = f"bt_dr_{int(time.time() * 1000)}"
            dr_task = BrowserTask(
                task_id=bt_id,
                goal=consigne,
                recipe="gemini_deep_research",
            )
            browser_res: ToolResult = await run_browser_agent_task(task=dr_task)
            if browser_res and browser_res.is_success and dr_task.status != "failed":
                if envoyer_email and browser_res.user_message:
                    try:
                        dest = destinataire_email or "pierrecassagnettes@gmail.com"
                        await send_email_async(
                            subject=f"[Deep Research] Synthèse : {consigne[:60]}",
                            body=browser_res.user_message,
                            to_email=dest,
                        )
                    except Exception as mail_err:
                        logger.warning(f"[Deep Research Mail Error] {mail_err}")
                return browser_res
            else:
                logger.info(f"[DeepResearch] Browser task gemini_deep_research non réussi ({dr_task.status if dr_task else 'unknown'}), repli vers le moteur Map-Reduce.")
        except Exception as b_err:
            logger.warning(f"[DeepResearch] Erreur browser task gemini_deep_research ({b_err}), repli vers le moteur Map-Reduce.")

        # 2. Repli existant Map-Reduce (Phase 1: Prospecteur, Phase 2: Analyste, Phase 3: Synthèse)
        cli_ok, cli_err, _ = await verify_antigravity_cli_ready()
        if not cli_ok:
            return ToolResult.failed(
                user_message="Antigravity CLI n'est pas disponible sur le serveur VPS.",
                error_hint=cli_err or "cli_not_ready",
                verified=False,
            )

        t_total_0 = time.perf_counter()
        session_id = getattr(session, "id", None) if session else None
        allow_paid = bool(active_task_controller.get("paid_consent_given", False))

        # ── Phase 1 : Prospecteur (flash/medium) ──
        p_agent_id = f"agy_prospector_{int(time.time()*1000)}"
        t_p0 = time.perf_counter()
        await spawn_subagent(
            agent_id=p_agent_id,
            name="Prospecteur",
            role="Recherche & Faits",
            activity="browsing",
            task=f"Prospection : {consigne[:50]} (flash/medium)",
            model=MODEL_FLASH,
        )
        try:
            await update_subagent(p_agent_id, activity="browsing", task="Collecte exhaustive des sources & données...")
            out_p: AgentOutput = await run_agentic(
                role="prospector",
                prompt=f"Collecte et prospection exhaustive de données et sources sur : {consigne}",
                model=MODEL_FLASH,
                effort="medium",
                timeout=300,
                session_id=session_id,
                task_id=p_agent_id,
                allow_paid_fallback=allow_paid,
            )
            dur_p = time.perf_counter() - t_p0
            await complete_subagent(p_agent_id, summary=f"{out_p.conclusion[:70]} (flash/medium, durée: {dur_p:.1f}s)")
            if out_p.status != "success":
                return ToolResult.failed(
                    user_message=out_p.conclusion or "Échec de la phase de prospection.",
                    error_hint=out_p.error or "prospector_phase_failed",
                    verified=False,
                )
        except Exception as e:
            dur_p = time.perf_counter() - t_p0
            await complete_subagent(p_agent_id, summary=f"Erreur: {str(e)[:70]} (durée: {dur_p:.1f}s)")
            return ToolResult.failed(user_message=f"Erreur phase Prospecteur : {str(e)}", error_hint=str(e), verified=False)

        # ── Phase 2 : Analyste (pro/high) ──
        a_agent_id = f"agy_analyst_{int(time.time()*1000)}"
        t_a0 = time.perf_counter()
        await spawn_subagent(
            agent_id=a_agent_id,
            name="Analyste",
            role="Critique & Logique",
            activity="thinking",
            task="Analyse critique & logique (pro/high)",
            model=MODEL_PRO,
        )
        try:
            await update_subagent(a_agent_id, activity="thinking", task="Analyse critique, détection de biais et triangulation...")
            out_a: AgentOutput = await run_agentic(
                role="critic",
                prompt=(
                    f"Analyse critique et triangulation pour la consigne : {consigne}\n"
                    f"Données brutes recueillies par le prospecteur :\n{out_p.conclusion}\n"
                    f"Sources : {json.dumps(out_p.sources, ensure_ascii=False)}"
                ),
                model=MODEL_PRO,
                effort="high",
                timeout=300,
                session_id=session_id,
                task_id=a_agent_id,
                allow_paid_fallback=allow_paid,
            )
            dur_a = time.perf_counter() - t_a0
            await complete_subagent(a_agent_id, summary=f"{out_a.conclusion[:70]} (pro/high, durée: {dur_a:.1f}s)")
            if out_a.status != "success":
                return ToolResult.failed(
                    user_message=out_a.conclusion or "Échec de la phase d'analyse critique.",
                    error_hint=out_a.error or "analyst_phase_failed",
                    verified=False,
                )
        except Exception as e:
            dur_a = time.perf_counter() - t_a0
            await complete_subagent(a_agent_id, summary=f"Erreur: {str(e)[:70]} (durée: {dur_a:.1f}s)")
            return ToolResult.failed(user_message=f"Erreur phase Analyste : {str(e)}", error_hint=str(e), verified=False)

        # ── Phase 3 : Synthèse (pro/medium) ──
        s_agent_id = f"agy_synthesis_{int(time.time()*1000)}"
        t_s0 = time.perf_counter()
        await spawn_subagent(
            agent_id=s_agent_id,
            name="Synthèse",
            role="Rédaction & Artefact",
            activity="coding",
            task="Synthèse finale & livrable (pro/medium)",
            model=MODEL_PRO,
        )
        try:
            await update_subagent(s_agent_id, activity="coding", task="Rédaction du rapport de synthèse final...")
            out_s: AgentOutput = await run_agentic(
                role="synthesis",
                prompt=(
                    f"Consigne initiale : {consigne}\n"
                    f"Données vérifiées de l'analyste :\n{out_a.conclusion}\n"
                    f"Questions ouvertes restantes : {json.dumps(out_a.open_questions, ensure_ascii=False)}\n"
                    f"Rédige une synthèse exécutive structurée et percutante."
                ),
                model=MODEL_PRO,
                effort="medium",
                timeout=300,
                session_id=session_id,
                task_id=s_agent_id,
                allow_paid_fallback=allow_paid,
            )
            dur_s = time.perf_counter() - t_s0
            await complete_subagent(s_agent_id, summary=f"{out_s.conclusion[:70]} (pro/medium, durée: {dur_s:.1f}s)")
            if out_s.status != "success":
                return ToolResult.failed(
                    user_message=out_s.conclusion or "Échec de la phase de synthèse.",
                    error_hint=out_s.error or "synthesis_phase_failed",
                    verified=False,
                )
        except Exception as e:
            dur_s = time.perf_counter() - t_s0
            await complete_subagent(s_agent_id, summary=f"Erreur: {str(e)[:70]} (durée: {dur_s:.1f}s)")
            return ToolResult.failed(user_message=f"Erreur phase Synthèse : {str(e)}", error_hint=str(e), verified=False)

        total_duration = time.perf_counter() - t_total_0
        all_sources = list(out_p.sources) + [s for s in out_a.sources if s not in out_p.sources]

        if envoyer_email:
            try:
                dest = destinataire_email or "pierrecassagnettes@gmail.com"
                await send_email_async(
                    subject=f"[Deep Research] Synthèse : {consigne[:60]}",
                    body=out_s.conclusion,
                    to_email=dest,
                )
            except Exception as mail_err:
                print(f"[Deep Research Mail Error] {mail_err}")

        return ToolResult.done(
            user_message=out_s.conclusion,
            evidence=f"3 phases (flash/medium -> pro/high -> pro/medium), Durée totale: {total_duration:.1f}s, Confiance: {out_s.confidence}",
            verified=True,
            data={
                "conclusion": out_s.conclusion,
                "confidence": out_s.confidence,
                "sources": all_sources,
                "artifacts": out_s.artifacts,
                "open_questions": out_s.open_questions,
                "phases": {
                    "prospector": {"model": MODEL_FLASH, "effort": "medium", "duration_s": round(dur_p, 2)},
                    "analyst": {"model": MODEL_PRO, "effort": "high", "duration_s": round(dur_a, 2)},
                    "synthesis": {"model": MODEL_PRO, "effort": "medium", "duration_s": round(dur_s, 2)},
                },
                "total_duration_s": round(total_duration, 2),
            },
        )


    # ─── search_web ────────────────────────────────────────────────────────────
    elif name in ("search_web", "web_search"):
        query = args.get("query", "").strip()
        supervision_service.start_action("search_web", "Recherche Internet", "search_web", query, "Playwright / DuckDuckGo", api_type="free", api_label="Clé Gratuite", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Recherche sur Internet : {query}", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "browsing", "msg": "Recherche sur Internet...", "task": query, "engine": "Clé Gratuite", "model": "DuckDuckGo / Playwright", "api_type": "free", "api_label": "Clé Gratuite"}))

        try:
            res = await search_web(query)
            best_url = "https://www.google.com"
            best_title = query
            if res.get("results"):
                first = res["results"][0]
                best_url = first.get("url", "")
                best_title = first.get("title", query)
            supervision_service.complete_action("search_web", status="completed", summary=f"Résultats pour {best_title}")
            supervision_service.track_browser_window(best_url, best_title)
            await broadcast_supervision()
            try:
                await websocket.send_text(json.dumps({"type": "browser_update", "url": best_url, "title": best_title, "screenshot": "/static/latest_screenshot.jpg"}))
                await websocket.send_text(json.dumps({"type": "status", "state": "idle", "msg": "En veille active", "engine": "Google API Live", "model": live_display_label, "api_type": "paid" if is_paid_live else "free", "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"}))
            except Exception:
                pass

            return {
                "status": "completed",
                "query": query,
                "best_url": best_url,
                "results": res.get("results", [])[:3],
                "instruction_to_jarvis": "Présente directement les éléments de réponse pertinents à Pierre avec ta voix Aoede de façon concise, vivante et naturelle."
            }
        except Exception as e:
            supervision_service.complete_action("search_web", status="error", summary=str(e))
            await broadcast_supervision()
            return {
                "status": "error",
                "error": str(e),
                "instruction_to_jarvis": f"La recherche sur '{query}' a rencontré un souci ({e}). Informe brièvement Pierre avec ta voix Aoede."
            }

    # ─── run_browser_task ──────────────────────────────────────────────────────
    elif name == "run_browser_task":
        goal = args.get("goal", "")
        target_url = args.get("url") or ""
        execution_target = args.get("execution_target")
        is_confirmed = (bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))) and config.is_paid_key_authorized()
        initial_api_type = "paid" if is_confirmed else "free"
        initial_api_label = "Clé Payante" if is_confirmed else "Clé Gratuite (Essai multi-modèles)"
        supervision_service.start_action("browser_task", "Navigation Web Autonome", "run_browser_task", goal, "Browser-Use (Vision LLM)", api_type=initial_api_type, api_label=initial_api_label, cost_est="~0.02 $" if is_confirmed else "0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Navigation autonome : {goal}", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "browsing", "msg": "Navigation autonome en cours...", "task": goal, "engine": initial_api_label, "model": "Browser-Use (Vision LLM)", "api_type": initial_api_type, "api_label": initial_api_label}))

        _g = goal
        _url = target_url
        _conf = is_confirmed
        _exec_target = execution_target
        _sess_bg = session
        _ws_bg = websocket

        async def _run_browser_bg(_g=_g, _url=_url, _conf=_conf, _et=_exec_target, _sess=_sess_bg, _ws=_ws_bg):
            try:
                res = await run_browser_task(goal=_g, url=_url, confirmed_by_user=_conf, execution_target=_et)
                if res.get("status") == "requires_user_confirmation":
                    active_task_controller["paid_consent_modal_open"] = True
                    supervision_service.complete_action("browser_task", status="pending_confirmation", summary=res.get("reason", ""))
                    await broadcast_supervision()
                    if _ws:
                        try:
                            await _ws.send_text(json.dumps({"type": "paid_consent_request", "action": "run_browser_task", "reason": res.get("reason", ""), "cost": res.get("estimated_cost", "~0.02 $"), "model": "Browser-Use"}))
                        except Exception:
                            pass
                    if _sess:
                        try:
                            await safe_send_live_client_content(
                                _sess,
                                f"[ACCORD PAYANT REQUIS POUR NAVIGUER] {res.get('instruction_to_jarvis', '')}"
                            )
                        except Exception:
                            pass
                    return

                actual_key = res.get("key_used", initial_api_label)
                actual_type = "free" if "gratuite" in actual_key.lower() else "paid"
                final_site_url = res.get("final_url") or res.get("url") or _url or "https://www.google.com"

                supervision_service.complete_action("browser_task", status="completed", summary=res.get("summary", "")[:250])
                supervision_service.track_browser_window(final_site_url, res.get("page_title", _g))
                await broadcast_supervision()
                try:
                    await _ws.send_text(json.dumps({"type": "browser_update", "url": final_site_url, "title": res.get("page_title", _g), "screenshot": "/static/latest_screenshot.jpg"}))
                    await _ws.send_text(json.dumps({"type": "status", "state": "idle", "msg": "En veille active", "engine": "Google API Live", "model": live_display_label, "api_type": actual_type, "api_label": actual_key}))
                except Exception:
                    pass
                result_msg = (
                    f"[RÉSULTATS NAVIGATION DISPONIBLES] La navigation autonome sur '{_g}' est terminée (utilisant {actual_key}). "
                    f"Site visité : {final_site_url}. Résumé : {res.get('summary', '')[:600]}. "
                    f"Détaille les résultats à Pierre avec ta voix Aoede de façon fluide."
                )
                try:
                    await safe_send_live_client_content(_sess, result_msg)
                except Exception as inj_err:
                    print(f"[Browser BG] Erreur injection résultats: {inj_err}")
            except Exception as e:
                print(f"[Browser BG] Erreur: {e}")
                supervision_service.complete_action("browser_task", status="error", summary=str(e))
                await broadcast_supervision()
                try:
                    await safe_send_live_client_content(_sess, f"[ÉCHEC NAVIGATION] La navigation sur '{_g}' a échoué ({e}). Informe Pierre brièvement.")
                except Exception:
                    pass
            finally:
                active_task_controller["browser_bg_task"] = None

        b_task = asyncio.create_task(_run_browser_bg())
        active_task_controller["browser_bg_task"] = b_task
        speech_intro = (f"La navigation autonome sur '{goal}' est lancée sur la clé payante autorisée." if is_confirmed else f"La navigation sur '{goal}' est lancée. J'essaie d'abord les modèles sur la clé gratuite.")
        return {
            "status": "launched_in_background", "goal": goal,
            "instruction_to_jarvis": (
                f"{speech_intro} Dis brièvement à Pierre avec ta voix Aoede que tu démarres la navigation sur le web."
            )
        }

    # ─── browser_task (Nouvel Agent Autonome S1/S2) ───────────────────────────
    elif name == "browser_task":
        goal = args.get("goal") or ""
        start_url = args.get("start_url") or args.get("url") or None
        recipe = args.get("recipe") or None

        task_id = f"bt_{int(time.time() * 1000)}"
        task = BrowserTask(
            task_id=task_id,
            goal=goal,
            start_url=start_url,
            recipe=recipe,
        )
        BROWSER_TASKS[task_id] = task

        supervision_service.start_action(
            "browser_task",
            "Navigation Web Autonome",
            "browser_task",
            goal,
            "Antigravity Browser Agent",
        )
        await broadcast_supervision()

        if websocket:
            try:
                await websocket.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Navigation autonome : {goal}",
                    "voice": False,
                }))
            except Exception:
                pass

        _sess = session
        _tid = task_id
        _g = goal

        async def _notify(msg: str):
            # notify = injection avec priorité PROGRESS_MILESTONE. Le handoff utilise INTERRUPTION.
            is_handoff = (
                task.status in ("needs_user", "ready_for_user")
                or any(k in msg.lower() for k in ["captcha", "login", "2fa", "intervention", "valider"])
            )
            p = InjectionPriority.INTERRUPTION if is_handoff else InjectionPriority.PROGRESS_MILESTONE
            try:
                await voice_injection_queue.enqueue(
                    text=msg,
                    priority=p,
                    session=_sess,
                    action_key=f"browser_task_{_tid}",
                    metadata={"task_id": _tid, "is_handoff": is_handoff},
                )
            except Exception as e:
                logger.error(f"[BrowserAgent BG] Erreur notify: {e}")

        async def _run_browser_bg():
            try:
                res: ToolResult = await run_browser_agent_task(task=task, notify=_notify)

                # Résultat final = injection avec priorité TOOL_RESPONSE et le user_message du ToolResult. Le handoff utilise INTERRUPTION.
                is_handoff = (
                    res.status == "needs_user"
                    or task.status in ("needs_user", "ready_for_user")
                )
                final_priority = InjectionPriority.INTERRUPTION if is_handoff else InjectionPriority.TOOL_RESPONSE
                final_msg = res.user_message or (f"Navigation terminée : {_g}" if res.is_success else f"Échec de la navigation : {_g}")

                try:
                    await voice_injection_queue.enqueue(
                        text=final_msg,
                        priority=final_priority,
                        session=_sess,
                        action_key=f"browser_task_result_{_tid}",
                        metadata={"task_id": _tid, "status": res.status},
                    )
                except Exception as inj_err:
                    logger.error(f"[BrowserAgent BG] Erreur injection résultat final: {inj_err}")

                action_status = "completed" if res.is_success else ("pending_user" if is_handoff else "error")
                supervision_service.complete_action("browser_task", status=action_status, summary=final_msg[:250])
                await broadcast_supervision()
            except Exception as e:
                logger.error(f"[BrowserAgent BG] Exception loop: {e}", exc_info=True)
                supervision_service.complete_action("browser_task", status="error", summary=str(e))
                await broadcast_supervision()
                try:
                    await voice_injection_queue.enqueue(
                        text=f"La navigation sur '{_g}' a rencontré un souci : {e}",
                        priority=InjectionPriority.TOOL_RESPONSE,
                        session=_sess,
                        action_key=f"browser_task_error_{_tid}",
                        metadata={"task_id": _tid},
                    )
                except Exception:
                    pass
            finally:
                if active_task_controller.get("browser_bg_task") == b_task:
                    active_task_controller["browser_bg_task"] = None

        b_task = asyncio.create_task(_run_browser_bg())
        active_task_controller["browser_bg_task"] = b_task

        return {
            "status": "launched_in_background",
            "task_id": task_id,
            "goal": goal,
            "instruction_to_jarvis": "Dis à Pierre « Je m'en occupe » puis reste immédiatement disponible à la voix.",
        }

    # ─── browser_task_status ───────────────────────────────────────────────────
    elif name == "browser_task_status":
        req_task_id = args.get("task_id")
        if req_task_id:
            t = get_browser_task(req_task_id)
            if not t:
                return {
                    "status": "not_found",
                    "task_id": req_task_id,
                    "message": f"Tâche de navigation '{req_task_id}' introuvable."
                }
            return {
                "status": t.status,
                "task_id": t.task_id,
                "steps": t.steps,
                "goal": t.goal,
                "result": t.result,
            }
        else:
            return {
                "status": "success",
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "status": t.status,
                        "steps": t.steps,
                        "goal": t.goal,
                        "result": t.result,
                    }
                    for t in BROWSER_TASKS.values()
                ]
            }

    # ─── open_user_browser / open_browser ──────────────────────────────────────
    elif name in ("open_user_browser", "open_browser"):
        target_url = args.get("url") or "https://www.google.com"
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Ouverture de Google Chrome à l'écran.", "voice": False}))
        from services.local_agent_service import local_agent_service
        if local_agent_service.is_connected():
            res = await local_agent_service.execute_command("open_browser", url=target_url)
        else:
            res = await asyncio.to_thread(open_browser_window, target_url)
        supervision_service.track_browser_window(target_url, "Google Chrome")
        await broadcast_supervision()

        # VÉRIFICATION POST-EXÉCUTION : Accusé de réception explicite de l'agent local PC
        verified, evidence = verify_browser_opened(res, target_url)
        if not verified:
            return ToolResult.failed(
                user_message="Impossible d'ouvrir le navigateur sur votre écran d'ordinateur.",
                error_hint=evidence,
                data={"result": res, "url": target_url}
            )

        return ToolResult.done(
            user_message=f"La fenêtre Chrome est affichée à l'écran sur {target_url}.",
            evidence=evidence,
            verified=True,
            data={"result": res, "url": target_url}
        )

    # ─── save_memory (Fusion remember_user_fact + memoriser_information) ──────
    elif name in ("save_memory", "remember_user_fact", "memoriser_information"):
        fact = args.get("fact") or args.get("valeur") or ""
        cat = args.get("category") or args.get("categorie") or "general"
        key = args.get("key") or args.get("cle") or ""
        full_text = f"{key} : {fact}".strip() if key else fact.strip()
        display_label = key or (fact[:40] if len(fact) <= 40 else fact[:37] + "...")
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Mémorisation vectorielle : {display_label}", "voice": False}))
        res = await unified_memory_manager.memorize(full_text, category=cat or "general", importance=2)

        # VÉRIFICATION POST-EXÉCUTION : Relecture par ID dans SQLite
        sqlite_id = res.get("id")
        verified, evidence = verify_saved_memory(sqlite_id, full_text)
        if not verified:
            return ToolResult.failed(
                user_message=f"La mémorisation de '{display_label}' n'a pas pu être vérifiée en base locale.",
                error_hint=evidence,
                data={"result": res, "fact": full_text}
            )

        return ToolResult.done(
            user_message=f"L'information '{display_label}' a été mémorisée et vérifiée avec succès dans votre mémoire.",
            evidence=evidence,
            verified=True,
            data={"result": res, "id": sqlite_id, "fact": full_text}
        )

    # ─── recall_user_memories ──────────────────────────────────────────────────
    elif name in ("recall_user_memories", "search_memories"):
        query = args.get("query", "")
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Consultation des souvenirs mémorisés.", "voice": False}))
        memories = await unified_memory_manager.recall(query, limit=6)
        return ToolResult.done(
            user_message=f"J'ai retrouvé {len(memories)} souvenir(s) correspondant à votre recherche.",
            evidence=f"{len(memories)} souvenirs trouvés",
            verified=True,
            data={"memories": memories}
        )

    # ─── get_system_status / get_status ────────────────────────────────────────
    elif name in ("get_system_status", "get_status"):
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Diagnostic des ressources système en cours.", "voice": False}))
        status = await asyncio.to_thread(get_system_status)
        return ToolResult.done(
            user_message="Voici les métriques système actuelles.",
            evidence="Télémétrie CPU/RAM serveur et poste local",
            verified=True,
            data={"result": status}
        )

    # ─── launch_application / launch_app ───────────────────────────────────────
    elif name in ("launch_application", "launch_app"):
        app_name = args.get("app_name") or args.get("application") or args.get("app", "")
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Lancement de {app_name}.", "voice": False}))
        from services.local_agent_service import local_agent_service
        if local_agent_service.is_connected():
            res = await local_agent_service.execute_command("launch_app", app_name=app_name)
        else:
            res = await asyncio.to_thread(launch_application, app_name)

        # VÉRIFICATION POST-EXÉCUTION : Le processus doit exister avec PID valide
        pid = res.get("pid") if isinstance(res, dict) else None
        verified, found_pid, evidence = verify_application_process(pid, app_name)
        if not verified:
            return ToolResult.failed(
                user_message=f"Le lancement de l'application '{app_name}' n'a pas pu être confirmé sur votre poste.",
                error_hint=evidence,
                data={"result": res, "app": app_name}
            )

        return ToolResult.done(
            user_message=f"J'ai ouvert l'application {app_name} sur votre écran.",
            evidence=evidence,
            verified=True,
            action="launch_app",
            instruction_to_jarvis=f"L'application {app_name} est lancée sur votre écran (PID {found_pid}). Confirme directement à Pierre.",
            data={"result": res, "app": app_name, "pid": found_pid}
        )


    # ─── control_spotify (+ alias legacy play_music_deezer / deezer_action) ────
    elif name in ("control_spotify", "play_music_deezer", "deezer_action"):
        action = args.get("action") or ("play" if args.get("query") else "now_playing")
        # Rétrocompatibilité alias Deezer → Spotify
        _deezer_compat = {
            "playpause": "play", "choose": "play", "open": "play",
            "prev": "previous", "status": "now_playing",
            "play_liked": "play", "liked": "play", "loved": "play",
            "play_likes": "play", "play_favorites": "play",
        }
        action = _deezer_compat.get(action, action)

        query = args.get("query", "")
        search_type = args.get("search_type") or args.get("item_type", "track")
        # Rétrocompatibilité item_type Deezer → search_type Spotify
        _type_compat = {
            "loved": "liked", "flow": "liked", "favorite": "liked",
            "favorites": "liked", "coups_de_coeur": "liked", "likes": "liked",
        }
        search_type = _type_compat.get(search_type, search_type)

        from services.spotify_service import _is_liked_query
        if _is_liked_query(query) or action in ("play_liked", "liked", "loved", "play_likes", "play_favorites"):
            search_type = "liked"

        device = args.get("device")
        volume = args.get("volume")
        volume_delta = args.get("volume_delta")
        position_ms = args.get("position_ms")
        state = args.get("state")
        playlist_name = args.get("playlist_name")

        _action_labels = {
            "play":        f"Spotify — {'Lecture : ' + query if query else ('Titres likés' if search_type == 'liked' else 'Reprendre')}",
            "pause":       "Spotify — Pause",
            "resume":      "Spotify — Reprendre",
            "next":        "Spotify — Suivant",
            "previous":    "Spotify — Précédent",
            "volume":      "Spotify — Volume",
            "shuffle":     "Spotify — Aléatoire",
            "repeat":      "Spotify — Répétition",
            "now_playing": "Spotify — Lecture en cours",
            "like":        "Spotify — Like",
            "unlike":      "Spotify — Unlike",
            "add_to_playlist": f"Spotify — Ajouter à '{playlist_name}'",
            "transfer":    f"Spotify — Transfert vers {device}",
            "list_devices": "Spotify — Appareils",
            "set_default_device": f"Spotify — Appareil par défaut : {device}",
        }
        action_label = _action_labels.get(
            action, f"Spotify — {action}" + (f" : {query}" if query else "")
        )

        supervision_service.start_action(
            "control_spotify", action_label, "control_spotify",
            f"Action : {action}{f' ({query})' if query else ''}",
            "Spotify Web API (OAuth 2.0)",
            api_type="free", api_label="Spotify", cost_est="0.00 $"
        )
        await broadcast_supervision()
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement", "text": f"{action_label}...", "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status", "state": "music",
            "msg": f"{action_label}...",
            "task": query or action,
            "engine": "Spotify Connect", "model": "Spotify Web API",
            "api_type": "free", "api_label": "Spotify"
        }))

        # Actions rapides (<300 ms) : exécution bloquante
        # Recherche + lecture (>300 ms) : asyncio.create_task pour ne pas bloquer la voix
        _FAST_ACTIONS = {
            "play", "pause", "resume", "next", "previous", "volume", "shuffle",
            "repeat", "seek", "like", "unlike", "now_playing",
            "list_devices", "get_queue", "set_default_device",
        }

        if action in _FAST_ACTIONS:
            res = await spotify_service.control(
                action=action, query=query, search_type=search_type,
                device=device, volume=volume, volume_delta=volume_delta,
                position_ms=position_ms, state=state, playlist_name=playlist_name,
            )
            supervision_service.complete_action(
                "control_spotify",
                status=res.get("status", "done"),
                summary=res.get("message", "Spotify : action terminée"),
            )
            await broadcast_supervision()
        else:
            # Lancement en tâche de fond pour ne pas bloquer Gemini Live
            async def _spotify_bg_task():
                r = await spotify_service.control(
                    action=action, query=query, search_type=search_type,
                    device=device, volume=volume, volume_delta=volume_delta,
                    position_ms=position_ms, state=state, playlist_name=playlist_name,
                )
                supervision_service.complete_action(
                    "control_spotify",
                    status=r.get("status", "done"),
                    summary=r.get("message", "Spotify : action terminée"),
                )
                await broadcast_supervision()

            asyncio.create_task(_spotify_bg_task())
            return {
                "status": "started",
                "verified": True,
                "evidence": f"Spotify {action_label}",
                "user_message": "Ok",
                "instruction_to_jarvis": "Action Spotify lancée. Réponds UNIQUEMENT et simplement 'Ok' à Pierre, sans phrase longue.",
            }

        # Construction de la réponse vocale selon le résultat
        status = res.get("status", "done")
        msg = res.get("message", "Ok")
        needs_user = res.get("needs_user", False)
        verified = bool(res.get("verified", True))
        evidence = res.get("evidence") or f"Spotify {action_label}"
        error_hint = res.get("error_hint")

        if needs_user:
            instr = (
                f"{msg} "
                "Dis-le clairement à Pierre en une seule phrase, sans préambule robotique."
            )
        elif status == "not_found":
            instr = f"{msg} Informe Pierre brièvement."
        elif status == "failed":
            hint = f" ({error_hint})" if error_hint else ""
            instr = f"Erreur Spotify : {msg}{hint} Informe Pierre brièvement."
        elif action in ("now_playing", "get_queue", "list_devices", "search", "top", "recent"):
            instr = f"{msg} Réponds brièvement à Pierre."
        else:
            instr = "Action Spotify effectuée. Réponds UNIQUEMENT et simplement 'Ok' à Pierre, sans phrase longue."

        return {
            "status": status,
            "verified": verified,
            "evidence": evidence,
            "error_hint": error_hint,
            "result": res,
            "user_message": "Ok" if action not in ("now_playing", "get_queue", "list_devices", "search", "top", "recent") else msg,
            "instruction_to_jarvis": instr,
        }


    # ─── play_video_stremio / launch_media ─────────────────────────────────────
    elif name in ("play_video_stremio", "launch_media"):
        title = args.get("title", "")
        content_type = args.get("content_type") or "movie"
        supervision_service.start_action("play_video_stremio", "Lecture Stremio", "play_video_stremio", f"{'Film' if content_type == 'movie' else 'Série'} : {title}", "Stremio + Torrentio", api_type="free", api_label="Local", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Recherche de '{title}' sur Stremio...", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "media", "msg": f"Stremio — Recherche de '{title}'...", "task": title, "engine": "Local", "model": "Stremio + Cinemeta", "api_type": "free", "api_label": "Local"}))

        try:
            res = await play_on_stremio(title, content_type)
            supervision_service.complete_action("play_video_stremio", status=res.get("status", "launched"), summary=res.get("message", f"Stremio lancé sur {title}"))
            await broadcast_supervision()
            stream = res.get("stream_info", {})
            size_msg = (f" Le stream 1080p fait {stream['size_gb']} Go." if stream.get("found") and stream.get("size_gb") else "")
            found_t = res.get("found_title", title)
            year = res.get("year", "")
            return {
                "status": "completed",
                "title": found_t,
                "year": year,
                "result": res,
                "instruction_to_jarvis": f"Stremio est ouvert sur '{found_t}' ({year}).{size_msg} Dis directement à Pierre que la vidéo est lancée sans amorce robotique."
            }
        except Exception as e:
            supervision_service.complete_action("play_video_stremio", status="error", summary=str(e))
            await broadcast_supervision()
            return {
                "status": "error",
                "error": str(e),
                "instruction_to_jarvis": f"Impossible de lancer '{title}' sur Stremio ({e}). Informe brièvement Pierre avec ta voix Aoede."
            }
        except Exception as e:
            supervision_service.complete_action("play_video_stremio", status="error", summary=str(e))
            await broadcast_supervision()
            return {
                "status": "error",
                "error": str(e),
                "instruction_to_jarvis": f"Impossible de lancer '{title}' sur Stremio ({e}). Informe brièvement Pierre avec ta voix Aoede."
            }

    # ─── send_email ────────────────────────────────────────────────────────────
    elif name in ("send_email", "mail_send"):
        subject = args.get("subject", "Rapport J.A.R.V.I.S.")
        body = args.get("body", "")
        to_email = args.get("to_email") or config.DEFAULT_RECIPIENT_EMAIL

        # Récupération résiliente des pièces jointes sous tous les alias possibles
        raw_attachments = (
            args.get("attachments")
            or args.get("attachment")
            or args.get("files")
            or args.get("file")
            or args.get("file_path")
            or args.get("filepath")
            or args.get("document")
            or args.get("documents")
            or args.get("filename")
            or args.get("filenames")
            or []
        )

        # Détection contextuelle si aucun fichier n'a été passé mais que le sujet/corps mentionne une pièce jointe
        if not raw_attachments:
            combined_text = f"{subject} {body}".lower()
            trigger_words = ["pièce jointe", "pièce-jointe", "ci-joint", "joint à ce", "voici l'ebook", "voici votre ebook", "voici le document", "en pièce jointe", "voici le tableur"]
            if any(w in combined_text for w in trigger_words):
                raw_attachments = ["latest"]

        include_screenshot = bool(
            args.get("include_latest_screenshot")
            or args.get("include_screenshot")
            or args.get("screenshot", False)
        )

        supervision_service.start_action("send_email", "Expédition E-mail", "send_email", f"Sujet : {subject} -> {to_email}", "SMTP Stark Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
        await broadcast_supervision()
        if websocket:
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Préparation de l'e-mail pour {to_email}.", "voice": False}))
            await websocket.send_text(json.dumps({"type": "status", "state": "emailing", "msg": "Expédition d'e-mail en cours...", "task": subject, "engine": "Google API", "model": "Stark Email Protocol", "api_type": "free", "api_label": "Service Local"}))

        res = await send_email_async(
            subject=subject,
            body=body,
            to_email=to_email,
            attachments=raw_attachments,
            include_screenshot=include_screenshot,
            is_html_report=True
        )

        st = res.get("status")
        if st == "attachment_not_found":
            missing = res.get("missing_attachments", [])
            missing_str = ", ".join(missing) if missing else "demandé"
            supervision_service.complete_action("send_email", status="error", summary=f"Pièce jointe introuvable : {missing_str}")
            await broadcast_supervision()
            if websocket:
                await websocket.send_text(json.dumps({
                    "type": "email_sent",
                    "status": "error",
                    "subject": subject,
                    "recipient": to_email,
                    "attachments_count": 0,
                    "message": f"Pièce jointe introuvable : {missing_str}"
                }))
            return ToolResult.failed(
                user_message=f"Le document '{missing_str}' que vous avez demandé de joindre est introuvable sur le système.",
                error_hint=f"Pièce jointe '{missing_str}' inexistante",
                data={"result": res, "missing_attachments": missing}
            )

        email_id = res.get("email_id", "")
        message_id = res.get("message_id")
        verified, evidence, error_hint = await verify_email_sent(
            email_id=email_id,
            message_id=message_id,
            recipient=to_email,
            subject=subject,
        )

        if st not in ("sent", "saved", "archived_in_outbox"):
            supervision_service.complete_action("send_email", status="error", summary=f"Échec expédition e-mail pour {to_email}")
            await broadcast_supervision()
            return ToolResult.failed(
                user_message=f"L'envoi du courriel '{subject}' a rencontré une erreur.",
                error_hint=res.get("error") or res.get("message") or "Erreur SMTP lors de l'envoi",
                data={"result": res, "email_id": email_id, "recipient": to_email}
            )
        elif st == "partial":
            supervision_service.complete_action("send_email", status="completed", summary=f"E-mail partiellement envoyé pour {to_email}")
            await broadcast_supervision()
            return ToolResult.partial(
                user_message=f"Le courriel '{subject}' n'a été transmis qu'à une partie des destinataires.",
                evidence=evidence or f"smtp_accepted message_id={message_id or email_id}",
                error_hint=res.get("error"),
                data={"result": res, "email_id": email_id, "recipient": to_email}
            )

        supervision_service.complete_action("send_email", status="completed", summary=res.get("message", f"E-mail traité pour {to_email}"))
        await broadcast_supervision()

        att_count = res.get("attachments_count", 0)
        att_names = ", ".join(res.get("attachments", []))

        if websocket:
            await websocket.send_text(json.dumps({
                "type": "email_sent",
                "status": res.get("status"),
                "subject": subject,
                "recipient": to_email,
                "attachments_count": att_count,
                "attachments": res.get("attachments", []),
                "message": res.get("message", "")
            }))

        att_suffix = f" avec la pièce jointe {att_names}" if att_count > 0 else ""
        return ToolResult.done(
            user_message=f"Le courriel '{subject}' a été expédié avec succès à {to_email}{att_suffix}.",
            evidence=evidence or f"smtp_accepted message_id={message_id or email_id}",
            verified=verified,
            data={"result": res, "email_id": email_id, "message_id": message_id, "recipient": to_email}
        )

    # ─── read_emails ───────────────────────────────────────────────────────────
    elif name in ("read_emails", "get_emails"):
        count = int(args.get("count", 5))
        query = args.get("query")
        unread_only = bool(args.get("unread_only", False))
        supervision_service.start_action("read_emails", "Lecture E-mails", "read_emails", f"Consultation Gmail ({count} messages)", "IMAP Stark Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Consultation de votre boîte de réception Gmail en cours...", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "emailing", "msg": "Lecture des e-mails en cours...", "task": f"Boîte de réception ({config.DEFAULT_RECIPIENT_EMAIL})", "engine": "Google API", "model": "Stark IMAP Protocol", "api_type": "free", "api_label": "Service Local"}))
        res = await read_received_emails_async(max_count=count, query=query, unread_only=unread_only)
        supervision_service.complete_action("read_emails", status="completed" if res.get("status") == "ok" else "error", summary=f"{res.get('count', 0)} e-mail(s) relevé(s)")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "emails_received", "status": res.get("status"), "count": res.get("count", 0), "emails": res.get("emails", []), "message": res.get("message", "")}))
        emails_summary_text = ""
        if res.get("status") == "ok" and res.get("emails"):
            items_desc = []
            for idx, m in enumerate(res["emails"], 1):
                items_desc.append(f"E-mail {idx} : De '{m.get('from', 'Inconnu')}', Objet '{m.get('subject', 'Sans sujet')}', reçu le {m.get('date', '')}. Extrait : {m.get('snippet', '')}")
                if m.get("has_attachments"):
                    items_desc.append(f"  Pièces jointes : {', '.join(m.get('attachments', []))}")
            emails_summary_text = "\n".join(items_desc)
        else:
            emails_summary_text = res.get("message", "Aucun message trouvé.")
        return {"status": "completed", "result": res, "instruction_to_jarvis": f"Voici le résultat de la consultation des e-mails reçus sur {config.DEFAULT_RECIPIENT_EMAIL} :\n{emails_summary_text}\n\nPrésente directement à Pierre à l'oral avec ta voix Aoede un compte-rendu clair, concis et naturel de ses messages récents."}

    # ─── check_console_errors ─────────────────────────────────────────────────
    elif name in ("check_console_errors", "console_errors"):
        action = args.get("action") or "diagnose"
        if action == "clear":
            console_monitor.clear()
            diag = console_monitor.analyze_diagnostics()
            diag["summary"] = "Journal des erreurs de la console réinitialisé."
            diag["oral_explanation"] = "Pierre, j'ai purgé et réinitialisé le journal des erreurs de la console."
        else:
            diag = console_monitor.analyze_diagnostics()
            if diag.get("has_errors"):
                auto_fix = console_monitor.attempt_auto_fix(workspace_path=config.WORKSPACE_DIR)
                diag["auto_fix"] = auto_fix
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Analyse console : {diag.get('summary', '')[:65]}", "voice": False}))
        return {"status": "completed", "has_errors": diag.get("has_errors", False), "diagnostic": diag.get("summary", ""), "oral_explanation": diag.get("oral_explanation", ""), "recent_errors": console_monitor.get_recent_errors(limit=4), "instruction_to_jarvis": f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede la situation de la console de façon fluide et rassurante : {diag.get('oral_explanation', '')}"}

    # ─── interact_web_page ─────────────────────────────────────────────────────
    elif name in ("interact_web_page", "web_interaction"):
        target_url = args.get("url", "")
        action = args.get("action", "read")
        selector = args.get("selector", "")
        text_to_fill = args.get("text_to_fill", "")
        execution_target = args.get("execution_target", "vps_headless")
        supervision_service.start_action("interact_web_page", "Interaction Web & Formulaires", "interact_web_page", f"{action} sur {target_url}", "Playwright Automation Engine", api_type="free", api_label="Local / Playwright", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Interaction sur {target_url} ({action})", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "browsing", "msg": "Interaction sur la page web...", "task": f"{action} sur {target_url}", "engine": "Playwright Local", "model": "Browser Engine", "api_type": "free", "api_label": "Clé Gratuite"}))
        res = await interact_web_page(url=target_url, action=action, selector=selector, text_to_fill=text_to_fill, execution_target=execution_target)
        supervision_service.complete_action("interact_web_page", status=res.get("status", "completed"), summary=res.get("title", target_url))
        if res.get("url"):
            supervision_service.track_browser_window(res.get("url"), res.get("title", target_url))
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "browser_update", "url": res.get("url", target_url), "title": res.get("title", "Page Web"), "screenshot": "/static/latest_screenshot.jpg"}))
        return {"status": res.get("status"), "url": res.get("url"), "title": res.get("title"), "performed_actions": res.get("performed_actions", []), "detected_form_inputs": res.get("detected_form_inputs", []), "available_buttons": res.get("available_buttons", []), "content_preview": res.get("content_preview", "")[:1200], "instruction_to_jarvis": f"L'interaction sur la page {res.get('url')} est terminée. Présente directement et simplement à Pierre avec ta voix Aoede les éléments découverts ou les actions effectuées sans amorce robotique."}

    # ─── prepare_web_cart_or_checkout ──────────────────────────────────────────
    elif name in ("prepare_web_cart_or_checkout", "prepare_cart"):
        product_or_service = args.get("product_or_service") or args.get("product") or ""
        merchant_url = args.get("merchant_url") or args.get("url") or ""
        goal_parts = [f"Préparer le panier pour {product_or_service}"]
        if merchant_url:
            goal_parts.append(f"sur {merchant_url}")
        goal = " ".join(goal_parts)
        return await _execute_dispatch_tool(
            name="browser_task",
            args={
                "goal": goal,
                "recipe": "cart",
                "start_url": merchant_url or None,
            },
            websocket=websocket,
            session=session,
            is_paid_live=is_paid_live,
            live_display_label=live_display_label,
        )

    # ─── download_file ─────────────────────────────────────────────────────────
    elif name in ("download_file", "file_download"):
        target_url = args.get("url", "")
        filename = args.get("filename")
        is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
        file_type = args.get("file_type", "general")
        supervision_service.start_action("download_file", "Téléchargement Sécurisé", "download_file", f"Téléchargement {filename or target_url}", "Stark Transfer Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "status", "state": "downloading", "msg": f"Téléchargement sécurisé : {filename or target_url}...", "task": f"Téléchargement : {filename or target_url}", "engine": "Stark Transfer Protocol", "model": "Secure Downloader", "api_type": "free", "api_label": "Service Local"}))
        res = await download_file(url=target_url, filename=filename, confirmed_by_user=is_confirmed, subfolder="ebooks" if file_type == "ebook" else "downloads")
        if res.get("status") == "requires_user_confirmation":
            supervision_service.complete_action("download_file", status="pending_confirmation", summary=f"En attente accord Pierre pour {res.get('filename')}")
            await broadcast_supervision()
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Autorisation requise pour télécharger {res.get('filename')}", "voice": False}))
            return ToolResult.needs_user(
                question=res.get("instruction_to_jarvis") or f"Autorisation requise pour télécharger {res.get('filename')}",
                user_message=f"Le téléchargement de {res.get('filename')} nécessite votre confirmation.",
                evidence=f"URL: {target_url}",
                filename=res.get("filename"),
                size=res.get("estimated_size"),
                domain=res.get("domain")
            )
        else:
            filepath = res.get("filepath") or os.path.join("downloads", res.get("filename") or "")
            v_ok, v_detail, v_size = verify_downloaded_file(filepath)
            if not v_ok or res.get("status") not in ("completed", "success"):
                supervision_service.complete_action("download_file", status="error", summary=f"Échec vérification {res.get('filename')}: {v_detail}")
                await broadcast_supervision()
                return ToolResult.failed(
                    error_hint=f"Le fichier téléchargé n'a pas pu être validé ({v_detail}).",
                    user_message=f"Le téléchargement de {res.get('filename', 'fichier')} n'a pas pu être validé.",
                    evidence=v_detail
                )
            supervision_service.complete_action("download_file", status="completed", summary=f"{res.get('filename')} ({res.get('size')})")
            await broadcast_supervision()
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Téléchargement terminé : {res.get('filename')} ({res.get('size')})", "voice": False}))
            return ToolResult.done(
                verified=True,
                evidence=f"{filepath} ({v_size} octets)",
                user_message=f"Le fichier '{res.get('filename')}' ({res.get('size')}) a été téléchargé et vérifié sur l'ordinateur.",
                filename=res.get("filename"),
                filepath=filepath,
                size=res.get("size")
            )

    # ─── send_to_ereader (Fusion send_to_ereader + send_page_to_kindle + send_file_to_kindle) ─
    elif name in ("send_to_ereader", "send_page_to_kindle", "send_file_to_kindle"):
        source = args.get("source") or args.get("file_path") or args.get("url") or ""
        source_type = args.get("source_type")
        if not source_type:
            source_type = "url" if (source.startswith("http://") or source.startswith("https://")) else "file"
        method = args.get("method") or ("kindle_web" if name == "send_file_to_kindle" else "auto")
        title = args.get("title") or ""
        ereader_email = args.get("ereader_email")

        # 1. Source URL -> Acheminement d'un article web via extension/email Kindle
        if source_type == "url" or name == "send_page_to_kindle":
            supervision_service.start_action("send_page_to_kindle", "Envoi Send to Kindle", "send_to_ereader", f"Kindle : {title or source}", "Send to Kindle Extension & E-Reader Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
            await broadcast_supervision()
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Mise en page et envoi de l'article vers votre Kindle...", "voice": False}))
            await websocket.send_text(json.dumps({"type": "status", "state": "kindle", "msg": f"Mise en page Send to Kindle : {title or source}...", "task": f"Kindle : {title or source}", "detail": "Formatage article web...", "engine": "Amazon Send to Kindle", "model": "Send to Kindle Extension", "api_type": "free", "api_label": "Service Local"}))
            res = await send_page_to_kindle(url=source, title=title, open_in_chrome=True)
            supervision_service.complete_action("send_page_to_kindle", status=res.get("status", "completed"), summary=res.get("message", "Article envoyé sur Kindle"))
            await broadcast_supervision()
            return ToolResult.done(
                verified=True,
                evidence=f"Page transmise via Send to Kindle ({title or source})",
                user_message=f"L'article a été mis en page et expédié vers votre Kindle.",
                result=res
            )

        # 2. Méthode kindle_web -> Dépôt sur Amazon Send to Kindle Web via Playwright
        elif method == "kindle_web" or name == "send_file_to_kindle":
            open_browser = args.get("open_browser_if_needed", True)
            supervision_service.start_action("send_file_to_kindle", "Amazon Send to Kindle Web", "send_to_ereader", f"Fichier : {source}", "Amazon Playwright Authenticated Session", api_type="free", api_label="Service Local", cost_est="0.00 $")
            await broadcast_supervision()
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Dépôt du fichier {os.path.basename(source) if source else 'document'} sur Amazon Send to Kindle...", "voice": False}))
            await websocket.send_text(json.dumps({"type": "status", "state": "kindle", "msg": f"Dépôt Amazon Send to Kindle : {os.path.basename(source) if source else 'document'}...", "task": f"Kindle : {os.path.basename(source) if source else 'document'}", "detail": "Amazon Playwright Authenticated Session...", "engine": "Amazon Send to Kindle", "model": "Send to Kindle Web", "api_type": "free", "api_label": "Service Local"}))
            res = await send_file_to_kindle_web(file_path=source, open_browser_if_needed=open_browser)
            supervision_service.complete_action("send_file_to_kindle", status=res.get("status", "completed"), summary=res.get("message", "Fichier envoyé sur Kindle"))
            await broadcast_supervision()
            if res.get("status") == "success":
                return ToolResult.done(
                    verified=True,
                    evidence=f"Fichier déposé sur Send to Kindle: {source}",
                    user_message="Le document a été envoyé avec succès sur votre liseuse Kindle.",
                    result=res
                )
            else:
                return ToolResult.failed(
                    error_hint=res.get("message", "Erreur de transfert"),
                    user_message="L'envoi sur votre Kindle n'a pas pu aboutir.",
                    evidence=res.get("message", "")
                )

        # 3. Acheminement automatique (USB physique en priorité puis e-mail SMTP)
        else:
            supervision_service.start_action("send_to_ereader", "Acheminement Liseuse", "send_to_ereader", f"Livre : {source}", "USB / SMTP Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
            await broadcast_supervision()
            await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Transfert de l'ebook vers la liseuse...", "voice": False}))
            await websocket.send_text(json.dumps({"type": "status", "state": "kindle", "msg": "Acheminement de l'ebook vers votre liseuse Kindle...", "task": "Kindle : Acheminement liseuse", "detail": f"Livre : {os.path.basename(source) if source else 'Ebook'}", "engine": "Amazon Send to Kindle", "model": "Stark Reader Protocol", "api_type": "free", "api_label": "Service Local"}))
            res = await send_to_ereader(file_path=source, ereader_email=ereader_email, method=method)
            supervision_service.complete_action("send_to_ereader", status=res.get("status", "completed"), summary=res.get("message", "Ebook envoyé"))
            await broadcast_supervision()
            if res.get("status") in ("success", "completed", "sent"):
                return ToolResult.done(
                    verified=True,
                    evidence=f"Transféré via {res.get('channel')}: {source}",
                    user_message="Le livre a été envoyé et est prêt sur votre liseuse.",
                    channel=res.get("channel")
                )
            else:
                return ToolResult.failed(
                    error_hint=res.get("message") or "Erreur transfert liseuse",
                    user_message="Le transfert vers la liseuse n'a pas pu aboutir.",
                    evidence=res.get("message", "")
                )

    # ─── search_and_download_ebook ─────────────────────────────────────────────
    elif name in ("search_and_download_ebook", "download_ebook"):
        query = args.get("query", "")
        lang_arg = args.get("lang")
        source_url = args.get("source_url")
        is_confirmed = bool(args.get("confirmed_by_user", False)) or bool(active_task_controller.get("paid_consent_given", False))
        send_to_reader_flag = bool(args.get("send_to_reader", True))
        ereader_email = args.get("ereader_email")
        supervision_service.start_action("send_to_ereader", "Recherche & Ebook Liseuse", "search_and_download_ebook", f"Ebook : {query} ({lang_arg or 'auto'})", "Web / Stark Reader Protocol", api_type="free", api_label="Service Local", cost_est="0.00 $")
        await broadcast_supervision()
        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Recherche et transfert de l'ebook '{query}' vers votre Kindle...", "voice": False}))
        await websocket.send_text(json.dumps({"type": "status", "state": "kindle", "msg": f"Recherche & acheminement Kindle : {query}...", "task": f"Kindle : {query}", "detail": f"Ebook : {query} ({lang_arg or 'auto'})", "engine": "Amazon Send to Kindle", "model": "Send to Kindle / Anna's Archive", "api_type": "free", "api_label": "Service Local"}))
        res = await search_and_download_ebook(query=query, source_url=source_url, confirmed_by_user=is_confirmed, send_to_reader=send_to_reader_flag, ereader_email=ereader_email, lang=lang_arg)
        if res.get("status") == "requires_user_confirmation":
            supervision_service.complete_action("send_to_ereader", status="pending_confirmation", summary=f"Accord Pierre requis pour l'ebook {query}")
            await broadcast_supervision()
            return ToolResult.needs_user(
                question=res.get("instruction_to_jarvis") or f"Accord requis pour l'ebook {query}",
                user_message=f"Souhaitez-vous confirmer le téléchargement de l'ebook '{query}' ?",
                evidence=f"Ebook: {query}",
                filename=res.get("filename")
            )
        else:
            filepath = res.get("filepath") or os.path.join("ebooks", res.get("filename") or "")
            v_ok = True
            v_detail = ""
            if filepath and os.path.exists(filepath):
                v_ok, v_detail, _ = verify_downloaded_file(filepath)

            if res.get("status") in ("success", "completed") and v_ok:
                supervision_service.complete_action("send_to_ereader", status="completed", summary=f"Ebook {query} : success")
                await broadcast_supervision()
                return ToolResult.done(
                    verified=True,
                    evidence=f"Ebook '{query}' prêt ({res.get('filename')})",
                    user_message=f"L'ebook '{query}' a été téléchargé et validé dans votre bibliothèque.",
                    filename=res.get("filename")
                )
            else:
                supervision_service.complete_action("send_to_ereader", status="error", summary=f"Ebook {query} : échec")
                await broadcast_supervision()
                return ToolResult.failed(
                    error_hint=res.get("message") or v_detail or "Échec de récupération de l'ebook",
                    user_message=f"Une difficulté est survenue lors de la récupération de l'ebook '{query}'.",
                    evidence=res.get("message") or v_detail
                )

    # ─── list_chrome_extensions ────────────────────────────────────────────────
    elif name in ("list_chrome_extensions", "chrome_extensions"):
        res = await asyncio.to_thread(list_installed_chrome_extensions)
        return {"status": "completed", "result": res, "instruction_to_jarvis": f"{res.get('message', 'Extensions analysées.')} Résume oralement les extensions clés installées sur Chrome à Pierre (notamment Send to Kindle) avec ta voix Aoede."}

    # ─── executer_action_externe ───────────────────────────────────────────────
    elif name in ("execute_external_action", "executer_action_externe"):
        action_name = (args.get("action_name") or args.get("action") or "").strip()
        parametres = args.get("parametres") or {}

        supervision_service.start_action(
            "executer_action_externe",
            f"Workflow n8n : {action_name}",
            "executer_action_externe",
            f"Action n8n : {action_name}",
            "n8n Automation Engine",
            api_type="free",
            api_label="Local n8n",
            cost_est="0.00 $"
        )
        await broadcast_supervision()
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Déclenchement du workflow n8n '{action_name}'...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "thinking",
            "msg": f"Workflow n8n — {action_name}...",
            "task": f"n8n : {action_name}",
            "engine": "n8n Community",
            "model": "Webhook Automation",
            "api_type": "free",
            "api_label": "Local n8n"
        }))

        _act = action_name
        _params = parametres
        _sess = session

        async def _run_n8n_bg(_a=_act, _p=_params, _s=_sess):
            try:
                from services.automation import executer_action_externe as n8n_exec
                res = await n8n_exec(action_name=_a, parametres=_p)
                status_res = res.get("status", "completed")
                is_ok = (status_res == "success")
                supervision_service.complete_action(
                    "executer_action_externe",
                    status="completed" if is_ok else "error",
                    summary=f"n8n {_a} : {status_res}"
                )
                await broadcast_supervision()
                if _s:
                    if is_ok:
                        r_data = res.get("result", {})
                        r_str = json.dumps(r_data, ensure_ascii=False)[:300] if isinstance(r_data, dict) else str(r_data)[:300]
                        inject_text = (
                            f"[ACTION N8N TERMINÉE] Le workflow '{_a}' s'est exécuté avec succès. "
                            f"Résultat : {r_str}. Confirme brièvement à Pierre avec ta voix Aoede si pertinent."
                        )
                    else:
                        err = res.get("error", "Erreur inconnue")
                        inject_text = (
                            f"[ACTION N8N ÉCHEC] Le workflow '{_a}' a rencontré une erreur ({err}). "
                            f"Informe brièvement Pierre avec ta voix Aoede."
                        )
                    try:
                        await safe_send_live_client_content(_s, inject_text)
                    except Exception as inj_e:
                        print(f"[n8n BG] Injection Live error: {inj_e}")
            except Exception as bg_err:
                print(f"[n8n BG] Erreur: {bg_err}")
                supervision_service.complete_action("executer_action_externe", status="error", summary=str(bg_err))
                await broadcast_supervision()

        asyncio.create_task(_run_n8n_bg())

        return {
            "status": "action_n8n_lancee",
            "action_name": action_name,
            "instruction_to_jarvis": (
                f"L'action externe '{action_name}' est lancée via n8n en tâche de fond. "
                f"Confirme immédiatement à Pierre avec ta voix Aoede d'un ton complice et naturel "
                f"que tu déclenches l'action '{action_name}'."
            )
        }

    # ─── generer_fichier_tableur ──────────────────────────────────────────────
    elif name in ("generate_spreadsheet", "generer_fichier_tableur"):
        nom_fichier = (args.get("nom_fichier") or "document.xlsx").strip()
        if not nom_fichier.lower().endswith(".xlsx"):
            nom_fichier += ".xlsx"
        colonnes = args.get("colonnes") or []
        lignes = args.get("lignes") or []
        description = args.get("description") or ""
        modele_avance_agent = bool(args.get("modele_avance_agent", True))

        if modele_avance_agent:
            from services.automation import generer_modele_tableur_avance
            asyncio.create_task(generer_modele_tableur_avance(
                nom_fichier=nom_fichier,
                colonnes=colonnes,
                lignes=lignes,
                description=description
            ))
            return ToolResult.started(
                task_id="generer_fichier_tableur",
                action="generer_fichier_tableur",
                user_message=f"La conception du classeur Excel '{nom_fichier}' est lancée.",
                evidence="Mission spreadsheet_modeler déléguée aux agents Antigravity",
                nom_fichier=nom_fichier,
                engine="Antigravity spreadsheet_modeler",
                instruction_to_jarvis=(
                    f"Je m'en charge Pierre. Je délègue la conception du classeur Excel '{nom_fichier}' "
                    f"à nos agents Antigravity sur le VPS avec formules dynamiques, ratios et mise en forme corporate. "
                    f"Confirme-le immédiatement à Pierre avec ta voix Aoede en moins de 300 millisecondes d'un ton complice."
                )
            )

        _filename = nom_fichier
        _cols = colonnes
        _rows = lignes
        _desc = description
        _sess = session

        async def _run_tableur_bg(_fn=_filename, _c=_cols, _r=_rows, _d=_desc, _s=_sess):
            try:
                from services.automation import executer_action_externe as n8n_exec
                payload = {
                    "nom_fichier": _fn,
                    "colonnes": _c,
                    "lignes": _r,
                    "description": _d,
                }
                res = await n8n_exec(action_name="document-spreadsheet", parametres=payload)
                status_res = res.get("status", "completed")
                is_ok = (status_res == "success")

                # Vérification post-exécution (Requirement 3)
                if is_ok:
                    spreadsheet_path = os.path.join("downloads", _fn)
                    v_ok, v_detail, v_rows = verify_spreadsheet_file(spreadsheet_path)
                    if not v_ok:
                        is_ok = False
                        res["error"] = f"Échec de vérification du tableur : {v_detail}"

                supervision_service.complete_action(
                    "generer_fichier_tableur",
                    status="completed" if is_ok else "error",
                    summary=f"Excel {_fn} : {status_res}"
                )
                await broadcast_supervision()
                if _s:
                    if is_ok:
                        download_url = f"/downloads/{_fn}"
                        inject_text = (
                            f"[TABLEUR EXCEL GÉNÉRÉ AVEC SUCCÈS] Le fichier Excel '{_fn}' a été créé avec succès par n8n. "
                            f"Lien de téléchargement : {download_url}. "
                            f"Informe calmement et brièvement Pierre avec ta voix Aoede que son tableur est prêt et accessible dans ses téléchargements."
                        )
                    else:
                        err = res.get("error", "Erreur lors de la création du fichier")
                        inject_text = (
                            f"[GÉNÉRATION TABLEUR ÉCHEC] Impossible de créer le tableur '{_fn}' ({err}). "
                            f"Informe Pierre avec ta voix Aoede d'un ton naturel et bienveillant."
                        )
                    try:
                        await safe_send_live_client_content(_s, inject_text)
                    except Exception as inj_e:
                        print(f"[Tableur BG] Injection Live error: {inj_e}")
            except Exception as bg_err:
                print(f"[Tableur BG] Erreur: {bg_err}")
                supervision_service.complete_action("generer_fichier_tableur", status="error", summary=str(bg_err))
                await broadcast_supervision()

        asyncio.create_task(_run_tableur_bg())

        return ToolResult.started(
            task_id="generer_fichier_tableur",
            action="generer_fichier_tableur",
            user_message=f"La préparation du tableur Excel '{nom_fichier}' est lancée.",
            evidence=f"Tableur {nom_fichier} en tâche de fond n8n",
            nom_fichier=nom_fichier,
            instruction_to_jarvis=(
                f"La génération du tableur Excel '{nom_fichier}' est lancée via n8n en tâche de fond. "
                f"Confirme immédiatement à Pierre avec ta voix Aoede d'un ton complice et naturel "
                f"que tu prépares son fichier Excel '{nom_fichier}'."
            )
        )

    # ─── generate_presentation / generer_presentation ─────────────────────────
    elif name in ("generate_presentation", "generer_presentation"):
        from services.slides_service import slides_service

        # ── Extraction des nouveaux paramètres enrichis ──────────────────────
        raw_titre = (args.get("titre") or args.get("sujet") or "Présentation").strip()
        sujet = (args.get("sujet") or raw_titre).strip()
        consignes = (args.get("consignes") or sujet).strip()
        nb_slides_raw = args.get("nb_slides")
        nb_slides = int(nb_slides_raw) if nb_slides_raw is not None and str(nb_slides_raw).isdigit() else None
        public = (args.get("public") or "").strip() or None
        ton = (args.get("ton") or args.get("theme") or "stark").strip().lower()
        langue = (args.get("langue") or "fr").strip()
        recherche_approfondie = bool(args.get("recherche_approfondie") or args.get("deep_research") or False)
        slides_legacy = args.get("slides") or []

        # Enregistrement de l'action dans supervision_service et slides_service
        supervision_service.start_action(
            "generer_presentation",
            f"Présentation : {raw_titre}",
            "generer_presentation",
            f"Conception dynamique de la présentation '{raw_titre}' (thème: {ton})",
            "Slides Intelligence Engine v5.15",
            api_type="free",
            api_label="Local n8n",
            cost_est="0.00 $"
        )
        supervision_service.update_action_progress(
            "generer_presentation",
            "Étape 1/4 : Génération de l'outline LLM",
            f"Création du plan narratif dynamique pour '{raw_titre}'"
        )
        await broadcast_supervision()

        slides_service._current_task = {
            "active": True,
            "action_id": "generer_presentation",
            "topic": raw_titre,
            "step": "Étape 1/4 : Génération de l'outline LLM",
            "details": f"Élaboration de l'architecture dynamique des diapositives sur {sujet}",
            "started_at": time.time(),
            "slides_count": nb_slides or 0,
            "presentation_url": ""
        }

        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Génération de l'outline et conception de la présentation '{raw_titre}'...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "document",
            "msg": f"Slides — Outline IA sur : {raw_titre}...",
            "task": f"Slides : {raw_titre}",
            "engine": "Slides Intelligence v5.15",
            "model": "Gemini Draft Engine",
            "api_type": "free",
            "api_label": "Local n8n"
        }))

        _t_init = raw_titre
        _sjt = sujet
        _cons = consignes
        _nb = nb_slides
        _pub = public
        _ton = ton
        _lang = langue
        _deep = recherche_approfondie
        _sl_legacy = list(slides_legacy)
        _sess = session
        _ws = websocket

        async def _run_slides_bg(
            _tit=_t_init, _sjt=_sjt, _cons=_cons, _nb=_nb, _pub=_pub, _thm=_ton,
            _lang=_lang, _deep=_deep, _sl=_sl_legacy, _s=_sess, _w=_ws
        ):
            effective_titre = _tit
            try:
                from services.automation import executer_action_externe as n8n_exec
                from services.automation import build_slides_payload

                # ── Étape 1 : Outline LLM dynamique ou outline hérité ──────────
                slides_service._current_task["step"] = "Étape 1/4 : Génération de l'outline LLM"
                slides_service._current_task["details"] = f"Conception du plan narratif pour {_tit}"
                supervision_service.update_action_progress(
                    "generer_presentation",
                    "Étape 1/4 : Outline LLM",
                    f"Rédaction du plan sur {_sjt} selon les consignes vocales"
                )
                await broadcast_supervision()
                await asyncio.sleep(0.5)

                # Recherche approfondie si demandée
                research_ctx = ""
                if _deep:
                    try:
                        from services.deep_research_service import deep_research_service
                        research_ctx = await deep_research_service.quick_search(_sjt)
                    except Exception as e:
                        print(f"[Slides BG] deep research context error: {e}")

                if _sl and len(_sl) >= 2:
                    # Outline hérité (compatibilité ascendante avec ancienne API)
                    outline = {"title": _tit, "subtitle": _cons, "theme": _thm, "slides": _sl}
                else:
                    # Génération dynamique via LLM
                    outline = await slides_service.generate_presentation_outline(
                        sujet=_sjt,
                        consignes=_cons,
                        nb_slides=_nb,
                        public=_pub,
                        ton=_thm,
                        langue=_lang,
                        recherche_approfondie=_deep,
                        research_context=research_ctx,
                    )

                effective_titre = outline.get("title") or _tit
                effective_sub = outline.get("subtitle") or f"Présentation générée par J.A.R.V.I.S. sur {_sjt}"
                effective_slides = outline.get("slides") or []
                effective_theme = outline.get("theme") or _thm
                expected_outline_count = len(effective_slides)

                slides_service._current_task["slides_count"] = expected_outline_count

                # ── Étape 2 : Recherche & Enrichissement ─────────────────────
                slides_service._current_task["step"] = "Étape 2/4 : Enrichissement du contenu"
                slides_service._current_task["details"] = f"{expected_outline_count} diapositives générées — enrichissement en cours"
                supervision_service.update_action_progress(
                    "generer_presentation",
                    "Étape 2/4 : Enrichissement",
                    f"{expected_outline_count} slides préparées pour {_sjt}"
                )
                await broadcast_supervision()
                await asyncio.sleep(1.0)

                # ── Étape 3 : Mise en page ────────────────────────────────────
                slides_service._current_task["step"] = "Étape 3/4 : Mise en page visuelle"
                slides_service._current_task["details"] = f"Application du thème {effective_theme} et construction des layouts"
                supervision_service.update_action_progress(
                    "generer_presentation",
                    "Étape 3/4 : Layouts & Thème",
                    f"Application de la charte visuelle (thème {effective_theme}) — {expected_outline_count} slides"
                )
                await broadcast_supervision()
                await asyncio.sleep(0.8)

                # ── Étape 4 : Envoi via n8n Google Slides ─────────────────────
                slides_service._current_task["step"] = "Étape 4/4 : Création Google Slides"
                slides_service._current_task["details"] = f"Envoi vers Google Slides via n8n"
                supervision_service.update_action_progress(
                    "generer_presentation",
                    "Étape 4/4 : Google Slides",
                    f"Création dans Google Slides ({expected_outline_count} slides, thème {effective_theme})"
                )
                await broadcast_supervision()

                payload = build_slides_payload(
                    titre=effective_titre,
                    theme=effective_theme,
                    slides=effective_slides,
                    subtitle=effective_sub
                )
                res = await n8n_exec(action_name="document-slides", parametres=payload)
                status_res = res.get("status", "completed")
                raw_result = res.get("result", {})
                batch_applied = raw_result.get("batch_applied", True)
                is_ok = (status_res == "success") and (batch_applied is not False) and (raw_result.get("status") != "error")

                presentation_id = raw_result.get("presentation_id") or ""
                presentation_url = (
                    raw_result.get("presentation_url")
                    or (f"https://docs.google.com/presentation/d/{presentation_id}" if presentation_id else "")
                    or "https://docs.google.com/presentation"
                )

                # ── Persistance de l'ID en Redis et RAM ───────────────────────
                if presentation_id:
                    slides_service._last_presentation_id = presentation_id
                    try:
                        from services.cache import cache_service
                        await cache_service.set("jarvis:slides:last_presentation_id", presentation_id, ttl=604800)
                    except Exception as cache_err:
                        print(f"[Slides BG] Cache write error: {cache_err}")

                # ── Vérification post-exécution avec expected_outline_count ───
                v_verified = False
                v_titles: list = []
                v_evidence = presentation_url
                if is_ok and presentation_id:
                    try:
                        vres = await slides_service.verify_presentation(
                            presentation_id,
                            min_slides=1,
                            expected_outline_count=expected_outline_count
                        )
                        v_verified = bool(vres.verified)
                        v_evidence = vres.evidence or presentation_url
                        v_titles = list(getattr(vres, 'titles', []))
                        if not v_verified:
                            is_ok = False
                            res["error"] = f"Vérification partielle : {vres.count}/{expected_outline_count} slides créées"
                    except Exception as ve:
                        print(f"[Slides BG] Verify error: {ve}")

                slides_service._current_task["active"] = False
                slides_service._current_task["presentation_url"] = presentation_url
                slides_service._current_task["titles"] = v_titles

                supervision_service.complete_action(
                    "generer_presentation",
                    status="completed" if is_ok else "partial" if presentation_id else "error",
                    summary=(
                        f"Présentation '{effective_titre}' créée ({expected_outline_count} slides, {effective_theme}) — vérifiée: {v_verified}"
                        if is_ok else
                        f"Présentation partielle : {res.get('error') or raw_result.get('reply') or 'Erreur Slides'}"
                    )
                )
                await broadcast_supervision()

                # ── HUD PWA ───────────────────────────────────────────────────
                if _w and presentation_url:
                    try:
                        await _w.send_text(json.dumps({
                            "type": "set_browser_link",
                            "url": presentation_url,
                            "title": f"Google Slides : {effective_titre}"
                        }))
                        await _w.send_text(json.dumps({
                            "type": "status",
                            "state": "idle",
                            "msg": f"Présentation prête : {effective_titre}",
                            "task": effective_titre,
                            "engine": "Google Slides v5.15",
                            "model": "Aoede Voix Active"
                        }))
                    except Exception:
                        pass

                # ── Annonce orale ─────────────────────────────────────────────
                if _s:
                    if is_ok:
                        titles_str = ", ".join(v_titles[:3]) + ("..." if len(v_titles) > 3 else "") if v_titles else ""
                        inject_text = (
                            f"[PRÉSENTATION GOOGLE SLIDES PRÊTE] La présentation sur '{effective_titre}' "
                            f"est finalisée avec {expected_outline_count} diapositives sur-mesure (thème {effective_theme}). "
                            f"{'Titres : ' + titles_str + '. ' if titles_str else ''}"
                            f"Lien Google Slides : {presentation_url}. "
                            f"Annonce-le avec enthousiasme à Pierre avec ta voix Aoede, résume les thèmes couverts en 2 phrases "
                            f"et dis-lui de cliquer sur le bouton affiché pour l'ouvrir."
                        )
                    else:
                        err = res.get("error", "Erreur lors de la création Google Slides")
                        inject_text = (
                            f"[PRÉSENTATION GOOGLE SLIDES ÉCHEC] Impossible de créer la présentation '{effective_titre}' ({err}). "
                            f"Informe brièvement Pierre avec ta voix Aoede."
                        )
                    try:
                        await safe_send_live_client_content(_s, inject_text, action_key="generer_presentation", drainage_delay=2.5)
                    except Exception as inj_e:
                        print(f"[Slides BG] Erreur injection Live: {inj_e}")

            except Exception as bg_err:
                print(f"[Slides BG] Erreur: {bg_err}")
                slides_service._current_task["active"] = False
                supervision_service.complete_action("generer_presentation", status="error", summary=str(bg_err))
                await broadcast_supervision()
                if _s:
                    try:
                        from google_antigravity import AntigravityQuotaExhaustedError
                        is_quota = isinstance(bg_err, AntigravityQuotaExhaustedError) or "Quota 5h" in str(bg_err)
                    except Exception:
                        is_quota = False
                    if is_quota:
                        inject_text = (
                            "[QUOTA ÉPUISÉ] Le quota de l'API est atteint pour la recherche approfondie. "
                            "Informe Pierre avec ta voix Aoede et demande-lui s'il autorise la clé payante."
                        )
                    else:
                        inject_text = (
                            f"[PRÉSENTATION GOOGLE SLIDES ÉCHEC] Impossible de créer la présentation '{effective_titre}' ({bg_err}). "
                            f"Informe brièvement Pierre avec ta voix Aoede."
                        )
                    try:
                        await safe_send_live_client_content(_s, inject_text, action_key="generer_presentation", drainage_delay=2.5)
                    except Exception as inj_e:
                        print(f"[Slides BG] Erreur injection Live: {inj_e}")

        asyncio.create_task(_run_slides_bg())

        return ToolResult.started(
            task_id="generer_presentation",
            action="generer_presentation",
            user_message=f"Je lance la conception sur-mesure de '{raw_titre}' : outline IA, {nb_slides or 'auto'} slides, thème {ton}.",
            evidence=f"Outline + Google Slides ({ton}) lancés en arrière-plan",
            titre=raw_titre,
            theme=ton,
            slides_count=nb_slides or 0,
            instruction_to_jarvis=(
                f"La conception sur-mesure de '{raw_titre}' est lancée (outline LLM dynamique, thème {ton}). "
                f"RÈGLE STRICTE : Ne lis pas la présentation immédiatement ! "
                f"Dis naturellement à Pierre avec ta voix Aoede que tu génères le plan narratif personnalisé selon ses consignes."
            )
        )

    # ─── get_active_task_status ──────────────────────────────────────────────
    elif name in ("get_active_task_status", "task_status"):
        from services.slides_service import slides_service

        task_info = deep_research_service.get_current_task()
        task_type_label = "deep_research"
        if not task_info.get("active"):
            task_info = slides_service.get_current_task()
            task_type_label = "presentation_slides"

        supervision_overview = supervision_service.get_full_overview()
        active_actions = supervision_overview.get("active_actions", [])

        if task_info.get("active"):
            explanation = task_info.get("explanation", "")
            step = task_info.get("step", "")
            details = task_info.get("details", "")
            elapsed = task_info.get("elapsed_seconds", 0)
            return {
                "status": "completed",
                "has_active_task": True,
                "task_type": task_type_label,
                "topic": task_info.get("topic"),
                "step": step,
                "details": details,
                "elapsed_seconds": elapsed,
                "explanation": explanation,
                "instruction_to_jarvis": (
                    f"Voici ce que tu es exactement en train de faire : {explanation}. "
                    f"Explique-le immédiatement et naturellement à Pierre à voix haute avec ta voix Aoede, "
                    f"d'un ton complice, direct et rassurant, en lui précisant l'étape en cours."
                )
            }

        # Vérification d'autres actions actives (ex: Antigravity, Browser-Use, etc.)
        running_actions = [a for a in active_actions if a.get("status") == "running"]
        if running_actions:
            first_act = running_actions[0]
            act_name = first_act.get("name", "Action en cours")
            act_step = first_act.get("progress_step", "Traitement en cours")
            act_detail = first_act.get("progress_text", "")
            return {
                "status": "completed",
                "has_active_task": True,
                "task_type": first_act.get("tool", "action"),
                "name": act_name,
                "step": act_step,
                "details": act_detail,
                "instruction_to_jarvis": (
                    f"Tu es en train d'exécuter l'action '{act_name}' (étape : {act_step}, détail : {act_detail}). "
                    f"Explique immédiatement à Pierre avec ta voix Aoede ce que tu es en train de faire de manière naturelle et concise."
                )
            }

        return {
            "status": "completed",
            "has_active_task": False,
            "instruction_to_jarvis": (
                "Aucune tâche lourde n'est en cours d'exécution pour le moment. "
                "Dis simplement et naturellement à Pierre avec ta voix Aoede que tu es en veille active, "
                "entièrement disponible et à son écoute."
            )
        }

    # ─── notion_enregistrer ───────────────────────────────────────────────────
    elif name in ("save_notion_entry", "notion_enregistrer"):
        type_entree = (args.get("type_entree") or "note").strip()
        titre = (args.get("titre") or "Note rapide").strip()
        contenu = (args.get("contenu") or "").strip()
        tags = args.get("tags") or []

        supervision_service.start_action(
            "notion_enregistrer",
            f"Notion : {titre}",
            "notion_enregistrer",
            f"Enregistrement Notion [{type_entree}] '{titre}'",
            "n8n Community",
            api_type="free",
            api_label="Local n8n",
            cost_est="0.00 $"
        )
        await broadcast_supervision()
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Enregistrement de l'entrée '{titre}' dans Notion...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "document",
            "msg": f"Notion ({type_entree}) — {titre}...",
            "task": f"Notion : {titre}",
            "engine": "n8n Community",
            "model": "Notion Automation",
            "api_type": "free",
            "api_label": "Local n8n"
        }))

        _te = type_entree
        _titre = titre
        _cont = contenu
        _tags = tags
        _sess = session

        async def _run_notion_bg(_t_ent=_te, _t=_titre, _c=_cont, _tg=_tags, _s=_sess):
            try:
                from services.automation import executer_action_externe as n8n_exec
                payload = {
                    "type_entree": _t_ent,
                    "titre": _t,
                    "contenu": _c,
                    "tags": _tg,
                }
                res = await n8n_exec(action_name="notion-entry", parametres=payload)
                status_res = res.get("status", "completed")
                is_ok = (status_res == "success")
                supervision_service.complete_action(
                    "notion_enregistrer",
                    status="completed" if is_ok else "error",
                    summary=f"Notion {_t_ent} {_t} : {status_res}"
                )
                await broadcast_supervision()
                if _s:
                    if is_ok:
                        inject_text = (
                            f"[ENTRÉE NOTION ENREGISTRÉE AVEC SUCCÈS] L'entrée '{_t}' (type: {_t_ent}) a bien été ajoutée dans l'espace Notion de Pierre. "
                            f"Confirme-lui calmement et naturellement à voix haute avec ta voix Aoede que sa note est enregistrée."
                        )
                    else:
                        err = res.get("error", "Erreur lors de l'enregistrement dans Notion")
                        inject_text = (
                            f"[ENREGISTREMENT NOTION ÉCHEC] Impossible d'enregistrer l'entrée '{_t}' dans Notion ({err}). "
                            f"Informe Pierre avec ta voix Aoede."
                        )
                    try:
                        await safe_send_live_client_content(_s, inject_text)
                    except Exception as inj_e:
                        print(f"[Notion BG] Injection Live error: {inj_e}")
            except Exception as bg_err:
                print(f"[Notion BG] Erreur: {bg_err}")
                supervision_service.complete_action("notion_enregistrer", status="error", summary=str(bg_err))
                await broadcast_supervision()

        asyncio.create_task(_run_notion_bg())

        return {
            "status": "lance_en_arriere_plan",
            "action": "notion_enregistrer",
            "type_entree": type_entree,
            "titre": titre,
            "instruction_to_jarvis": (
                f"L'enregistrement de l'entrée '{titre}' ({type_entree}) dans Notion est lancé en tâche de fond via n8n. "
                f"Confirme immédiatement à Pierre avec ta voix Aoede d'un ton complice et naturel "
                f"que tu enregistres cela dans son Notion."
            )
        }

    # ─── agenda_gerer_evenement ───────────────────────────────────────────────
    elif name in ("manage_calendar_event", "agenda_gerer_evenement"):
        action = (args.get("action") or "consulter").strip().lower()
        titre = (args.get("titre") or "Rendez-vous").strip()
        date_debut = (args.get("date_debut") or "").strip()
        date_fin = (args.get("date_fin") or date_debut).strip()
        description = (args.get("description") or "").strip()

        # Si l'action est purement une consultation, NE JAMAIS déclencher de création d'événement
        if action in ("consulter", "lire", "verifier", "voir"):
            supervision_service.start_action(
                "agenda_gerer_evenement",
                "Consultation de l'Agenda",
                "agenda_gerer_evenement",
                "Consultation des rendez-vous du jour",
                "Local Redis Cache",
                api_type="free",
                api_label="Local Service",
                cost_est="0.00 $"
            )
            await broadcast_supervision()
            if websocket:
                await websocket.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": "Consultation de votre agenda...",
                    "voice": False
                }))
                await websocket.send_text(json.dumps({
                    "type": "status",
                    "state": "calendar",
                    "msg": "Consultation de l'agenda...",
                    "task": "Agenda : Consultation",
                    "engine": "FastAPI / Redis",
                    "model": "Agenda Reader",
                    "api_type": "free",
                    "api_label": "Local Service"
                }))

            cached_agenda = await cache_service.get("jarvis:agenda:today")
            events = cached_agenda if isinstance(cached_agenda, list) else []
            if isinstance(cached_agenda, dict) and "events" in cached_agenda:
                events = cached_agenda["events"]

            supervision_service.complete_action(
                "agenda_gerer_evenement",
                status="completed",
                summary=f"{len(events)} événement(s) trouvé(s)"
            )
            await broadcast_supervision()

            if events:
                events_str = ", ".join([f"'{e.get('titre', e.get('summary', 'Point'))}' à {e.get('heure', e.get('start', 'heure non précisée'))}" for e in events])
                instruction = f"Voici les rendez-vous du jour sur ton agenda : {events_str}."
            else:
                instruction = "Ton agenda est entièrement dégagé pour aujourd'hui, aucun rendez-vous planifié."
            return ToolResult.done(
                verified=True,
                evidence=f"{len(events)} événement(s) listé(s)",
                user_message=instruction,
                result={"events": events}
            )

        supervision_service.start_action(
            "agenda_gerer_evenement",
            f"Agenda ({action}) : {titre}",
            "agenda_gerer_evenement",
            f"Agenda Google/Samsung [{action}] '{titre}' ({date_debut})",
            "n8n Community",
            api_type="free",
            api_label="Local n8n",
            cost_est="0.00 $"
        )
        await broadcast_supervision()
        if websocket:
            await websocket.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Mise à jour de l'agenda : {titre}...",
                "voice": False
            }))
            await websocket.send_text(json.dumps({
                "type": "status",
                "state": "calendar",
                "msg": f"Agenda ({action}) — {titre}...",
                "task": f"Agenda : {titre}",
                "engine": "n8n Community",
                "model": "Google Calendar Sync",
                "api_type": "free",
                "api_label": "Local n8n"
            }))

        from services.automation import executer_action_externe as n8n_exec
        payload = {
            "action": action,
            "titre": titre,
            "date_debut": date_debut,
            "date_fin": date_fin,
            "description": description,
        }
        try:
            res = await n8n_exec(action_name="agenda-event", parametres=payload)
            status_res = res.get("status", "completed")
            is_ok = (status_res == "success")
            supervision_service.complete_action(
                "agenda_gerer_evenement",
                status="completed" if is_ok else "error",
                summary=f"Agenda {action} {titre} : {status_res}"
            )
            await broadcast_supervision()
            if is_ok:
                if action == "creer":
                    # Requirement 3: manage_calendar_event -> relire l'événement créé
                    ev_id = res.get("result", {}).get("event_id") or res.get("event_id") or ""
                    v_ok, v_detail, v_id = await verify_calendar_event(event_id=ev_id, titre=titre, date_debut=date_debut)
                    if not v_ok:
                        return ToolResult.failed(
                            error_hint="Événement non retrouvé lors de la vérification de l'agenda.",
                            user_message=f"La création du rendez-vous '{titre}' n'a pas pu être confirmée dans votre agenda.",
                            evidence=v_detail,
                            verified=False
                        )
                    return ToolResult.done(
                        verified=True,
                        evidence=f"Événement confirmé (ID: {v_id or titre})",
                        user_message=f"Le rendez-vous '{titre}' pour le {date_debut} est bien inscrit et vérifié dans votre agenda.",
                        result=res
                    )
                elif action == "decaler":
                    ev_id = res.get("result", {}).get("event_id") or res.get("event_id") or ""
                    v_ok, v_detail, v_id = await verify_calendar_event(event_id=ev_id, titre=titre, date_debut=date_debut)
                    if not v_ok:
                        return ToolResult.failed(
                            error_hint="Modification d'horaire non confirmée dans l'agenda.",
                            user_message=f"Le décalage du rendez-vous '{titre}' n'a pas pu être vérifié dans l'agenda.",
                            evidence=v_detail,
                            verified=False
                        )
                    return ToolResult.done(
                        verified=True,
                        evidence=f"Événement décalé et vérifié (ID: {v_id or titre})",
                        user_message=f"Le rendez-vous '{titre}' est décalé et vérifié au {date_debut}.",
                        result=res
                    )
                elif action == "supprimer":
                    ev_id = res.get("result", {}).get("event_id") or res.get("event_id") or ""
                    v_ok, v_detail, _ = await verify_calendar_event(event_id=ev_id, titre=titre, date_debut=date_debut)
                    # Pour une suppression, l'événement ne doit plus exister !
                    if v_ok:
                        return ToolResult.failed(
                            error_hint="L'événement est toujours présent dans l'agenda après demande de suppression.",
                            user_message=f"La suppression du rendez-vous '{titre}' n'a pas pu être confirmée.",
                            evidence="Événement toujours détecté dans l'agenda",
                            verified=False
                        )
                    return ToolResult.done(
                        verified=True,
                        evidence=f"Suppression confirmée : événement '{titre}' absent de l'agenda",
                        user_message=f"L'événement '{titre}' a bien été supprimé de l'agenda.",
                        result=res
                    )
                else:
                    events_found = res.get("result", {}).get("events", [])
                    instruction = f"Voici les événements trouvés : {events_found}."
                    return ToolResult.done(
                        verified=True,
                        evidence=f"Consultation agenda : {len(events_found)} événement(s)",
                        user_message=instruction,
                        result=res
                    )
            else:
                err = res.get("error", "Erreur agenda")
                return ToolResult.failed(
                    error_hint=err,
                    user_message=f"Impossible d'effectuer l'action d'agenda ({err}).",
                    evidence=err
                )
        except Exception as e:
            supervision_service.complete_action("agenda_gerer_evenement", status="error", summary=str(e))
            await broadcast_supervision()
            return ToolResult.failed(
                error_hint=str(e),
                user_message="Erreur lors de l'accès à l'agenda.",
                evidence=str(e)
            )

    # ─── creer_rappel_push ───────────────────────────────────────────────────
    elif name in ("create_push_reminder", "creer_rappel_push"):
        message = (args.get("message") or args.get("text") or "Rappel").strip()
        echeance = (args.get("echeance") or "maintenant").strip()
        priorite = (args.get("priorite") or "normale").strip().lower()

        supervision_service.start_action(
            "creer_rappel_push",
            f"Rappel : {message}",
            "creer_rappel_push",
            f"Rappel push smartphone '{message}' ({echeance}, {priorite})",
            "n8n Community",
            api_type="free",
            api_label="Local n8n",
            cost_est="0.00 $"
        )
        await broadcast_supervision()
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Programmation du rappel : {message} ({echeance})...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "reminder",
            "msg": f"Rappel push ({echeance}) — {message}...",
            "task": f"Rappel : {message}",
            "engine": "n8n Community",
            "model": "Push Notification",
            "api_type": "free",
            "api_label": "Local n8n"
        }))

        try:
            from services.automation import executer_action_externe as n8n_exec
            payload = {
                "message": message,
                "echeance": echeance,
                "priorite": priorite,
            }
            res = await n8n_exec(action_name="schedule-push-reminder", parametres=payload)
            status_res = res.get("status", "completed")
            is_ok = (status_res == "success")
            supervision_service.complete_action(
                "creer_rappel_push",
                status="completed" if is_ok else "error",
                summary=f"Rappel '{message}' ({echeance}) : {status_res}"
            )
            await broadcast_supervision()
            if is_ok:
                return {
                    "status": "completed",
                    "message": message,
                    "echeance": echeance,
                    "instruction_to_jarvis": f"Le rappel '{message}' est programmé pour {echeance}. Confirme-le directement et simplement à Pierre avec ta voix Aoede."
                }
            else:
                err = res.get("error", "Erreur rappel")
                return {"status": "error", "error": err, "instruction_to_jarvis": f"Impossible de programmer le rappel ({err}). Informe brièvement Pierre avec ta voix Aoede."}
        except Exception as e:
            supervision_service.complete_action("creer_rappel_push", status="error", summary=str(e))
            await broadcast_supervision()
            return {"status": "error", "error": str(e), "instruction_to_jarvis": f"Erreur lors de la programmation du rappel ({e}). Informe Pierre brièvement."}

    # ─── demander_morning_briefing ───────────────────────────────────────────
    elif name in ("get_morning_briefing", "demander_morning_briefing"):
        force_refresh = bool(args.get("force_refresh", False))

        supervision_service.start_action(
            "demander_morning_briefing",
            "Morning Briefing",
            "demander_morning_briefing",
            "Restitution ou compilation du Morning Briefing",
            "Briefing Service / Redis",
            api_type="free",
            api_label="Local Service",
            cost_est="0.00 $"
        )
        await broadcast_supervision()

        # 1. Vérification clé Redis jarvis:briefing:today
        cached = await cache_service.get("jarvis:briefing:today")
        if cached and not force_refresh and isinstance(cached, dict) and cached.get("texte_oral"):
            briefing_text = cached.get("texte_oral")
            supervision_service.complete_action(
                "demander_morning_briefing",
                status="completed",
                summary="Morning Briefing restitué instantanément depuis le cache Redis"
            )
            await broadcast_supervision()
            return {
                "status": "success",
                "cached": True,
                "briefing": briefing_text,
                "instruction_to_jarvis": (
                    f"Voici le Morning Briefing préparé pour Pierre : \"{briefing_text}\". "
                    f"Restitue-le-lui immédiatement et intégralement à voix haute avec ta voix Aoede "
                    f"avec élégance, assurance et zéro verbosité inutile. "
                    f"Ne déclenche aucun outil d'agenda ni de calendrier, le point de la journée (météo à sa position actuelle, actualités des dernières 24h, agenda et e-mails) est déjà fidèlement compilé."
                )
            }

        # 2. Sinon déclencher la compilation immédiate
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": "Compilation immédiate du Morning Briefing...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "briefing",
            "msg": "Compilation du Morning Briefing...",
            "task": "Morning Briefing",
            "engine": "FastAPI / Redis",
            "model": "Briefing Service",
            "api_type": "free",
            "api_label": "Local Service"
        }))

        briefing_data = await briefing_service.compiler_morning_briefing(force_refresh=True)
        briefing_text = briefing_data.get("texte_oral", "")
        supervision_service.complete_action(
            "demander_morning_briefing",
            status="completed",
            summary="Morning Briefing compilé et mis en cache"
        )
        await broadcast_supervision()

        return {
            "status": "success",
            "cached": False,
            "briefing": briefing_text,
            "instruction_to_jarvis": (
                f"Voici le Morning Briefing fraîchement compilé pour Pierre : \"{briefing_text}\". "
                f"Restitue-le-lui immédiatement et intégralement à voix haute avec ta voix Aoede "
                f"d'un ton percutant et confiant digne de Stark Industries. "
                f"Ne déclenche aucun outil d'agenda ni de calendrier, le point de la journée (météo à sa position actuelle, actualités 24h, agenda et e-mails) est déjà fidèlement compilé."
            )
        }

    # ─── rechercher_train ─────────────────────────────────────────────────────
    elif name in ("search_train_routes", "rechercher_train"):
        origine = args.get("origine", "")
        destination = args.get("destination", "")
        date_depart = args.get("date_depart", "")
        heure_souhaitee = args.get("heure_souhaitee")
        pays = args.get("pays", "auto")
        reserver_automatiquement = args.get("reserver_automatiquement", False)
        optimiser_avec_agent = bool(args.get("optimiser_avec_agent", True))

        # Accusé de réception supervision
        supervision_service.start_action(
            "rechercher_train",
            "Recherche Ferroviaire",
            "rechercher_train",
            f"Trajet {origine} → {destination} ({date_depart})",
            "SNCF / Trainline / SJ",
            api_type="free",
            api_label="Headless VPS",
            cost_est="0.00 $"
        )
        await broadcast_supervision()

        # Notification WebSocket HUD préliminaire & Annonce
        await websocket.send_text(json.dumps({
            "type": "audio_event",
            "event": "action_started",
            "action": "rechercher_train",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Recherche des trains entre {origine} et {destination} pour le {date_depart}...",
            "voice": False
        }))
        await websocket.send_text(json.dumps({
            "type": "status",
            "state": "browsing",
            "msg": f"Recherche trains {origine} → {destination}...",
            "task": f"Itinéraire {origine} - {destination}",
            "engine": "Transport Service",
            "model": "Playwright VPS",
            "api_type": "free",
            "api_label": "Headless VPS"
        }))

        res = await transport_service.rechercher_itineraires(
            origine=origine,
            destination=destination,
            date_depart=date_depart,
            heure_souhaitee=heure_souhaitee,
            pays=pays,
            reserver_automatiquement=False,
            optimiser_avec_agent=optimiser_avec_agent
        )
        best = res.get("best_option", {})
        primary_link = res.get("primary_deep_link", "")
        link_title = res.get("primary_title") or f"Train {origine} → {destination}"
        is_multi = res.get("is_multi_segment", False)

        if is_multi:
            summary_text = (
                f"Enchaînement {best.get('type_train', 'SJ')} ({res.get('total_duration', '')}) : "
                f"départ {best.get('heure_depart', '')} → arrivée {best.get('heure_arrivee', '')} - {res.get('prix_total', '')}"
            )
        else:
            summary_text = (
                f"Train {best.get('type_train', 'SNCF/SJ')} : départ {best.get('heure_depart', '')} "
                f"→ arrivée {best.get('heure_arrivee', '')} ({best.get('duree', '')}) - {best.get('prix', '')}"
            )
        supervision_service.complete_action("rechercher_train", status="completed", summary=summary_text)
        await broadcast_supervision()

        current_ws = active_task_controller.get("websocket") or websocket
        if current_ws:
            try:
                await current_ws.send_text(json.dumps({
                    "type": "task_completed",
                    "is_error": False,
                    "status": "completed",
                    "summary": summary_text,
                    "engine": "Transport Service",
                    "model": "Playwright VPS"
                }))
            except Exception:
                pass

        if is_multi:
            segs = res.get("segments", [])
            seg1 = segs[0] if len(segs) > 0 else {}
            seg2 = segs[1] if len(segs) > 1 else {}
            esc = res.get("escale", {})
            instruction = (
                f"Pour le voyage de {origine} vers {destination} le {date_depart} : "
                f"Il n'existe pas de liaison directe. Annonce naturellement l'enchaînement des 2 trains : "
                f"1) {seg1.get('type_train', 'SJ')} de {seg1.get('origine')} ({seg1.get('heure_depart')}) à {seg1.get('destination')} ({seg1.get('heure_arrivee')}), "
                f"2) escale de {esc.get('duree', '2h45')} à {esc.get('gare', 'Stockholm Central')}, "
                f"3) train {seg2.get('type_train', 'SJ')} de {seg2.get('origine')} ({seg2.get('heure_depart')}) avec arrivée demain à {seg2.get('heure_arrivee')}. "
                f"Durée totale {res.get('total_duration', '')}, prix {res.get('prix_total', '')}. "
                f"Fais une seule annonce fluide avec ta voix Aoede sans répétition."
            )
        else:
            track_txt = f" au départ de la {best.get('quai')}" if best.get("quai") else ""
            instruction = (
                f"Pour le trajet {origine} → {destination} le {date_depart} : "
                f"départ à {best.get('heure_depart')} en {best.get('type_train')}{track_txt}, "
                f"arrivée à {best.get('heure_arrivee')} (durée {best.get('duree')}), prix {best.get('prix')}. "
                f"Annonce-le naturellement et directement à Pierre avec ta voix Aoede en une seule fois sans phrases redondantes."
            )

        return {
            "status": "success",
            "action": "rechercher_train",
            "origine": origine,
            "destination": destination,
            "date_depart": date_depart,
            "best_option": best,
            "primary_deep_link": primary_link,
            "agent_optimization_launched": res.get("agent_optimization_launched", False),
            "instruction_to_jarvis": instruction
        }

    # ─── surveiller_train ─────────────────────────────────────────────────────
    elif name in ("monitor_train", "surveiller_train"):
        numero_train = args.get("numero_train", "")
        date = args.get("date", "")
        operateur = args.get("operateur", "sncf")

        supervision_service.start_action(
            "surveiller_train",
            "Surveillance Train n8n",
            "surveiller_train",
            f"Veille proactive train {numero_train} ({date})",
            "n8n / Trafikverket / SNCF",
            api_type="free",
            api_label="n8n Workflow",
            cost_est="0.00 $"
        )
        await broadcast_supervision()

        res_monitor = await transport_service.surveiller_train(
            numero_train=numero_train,
            date=date,
            operateur=operateur
        )

        supervision_service.complete_action(
            "surveiller_train",
            status="completed",
            summary=f"Surveillance active engagée pour le train {numero_train} via n8n"
        )
        await broadcast_supervision()

        return {
            "status": "surveillance_activee",
            "numero_train": numero_train,
            "date": date,
            "operateur": operateur,
            "instruction_to_jarvis": (
                f"La surveillance proactive en temps réel pour le train {numero_train} du {date} est activée via n8n. "
                f"Confirme à Pierre avec ta voix Aoede que tu surveilles son train toutes les 10 minutes jusqu'au départ "
                f"et que tu le préviendras immédiatement en cas de retard ou de changement de quai."
            )
        }

    # ─── reserver_billet_train_local ──────────────────────────────────────────
    elif name in ("open_train_booking", "reserver_billet_train_local"):
        origine = args.get("origine", "")
        destination = args.get("destination", "")
        date_depart = args.get("date_depart", "")
        url_trajet = args.get("url_trajet") or (args.get("urls_trajets")[0] if args.get("urls_trajets") else "")
        desc = args.get("description_trajet") or ""
        goal_parts = ["Réserver le billet de train"]
        if origine and destination:
            goal_parts.append(f"de {origine} à {destination}")
        if date_depart:
            goal_parts.append(f"le {date_depart}")
        if desc:
            goal_parts.append(f"({desc})")
        elif not (origine and destination) and url_trajet:
            goal_parts.append(f"sur {url_trajet}")
        goal = " ".join(goal_parts)

        return await _execute_dispatch_tool(
            name="browser_task",
            args={
                "goal": goal,
                "recipe": "train",
                "start_url": url_trajet or None,
            },
            websocket=websocket,
            session=session,
            is_paid_live=is_paid_live,
            live_display_label=live_display_label,
        )

    # ─── consulter_architecture_jarvis ─────────────────────────────────────────
    elif name in ("query_jarvis_architecture", "consulter_architecture_jarvis"):
        from services.architecture_service import architecture_service
        sujet = args.get("sujet")
        section = args.get("section")

        target_desc = f"Section {section}" if section else (sujet or "Vue d'ensemble")
        await websocket.send_text(json.dumps({
            "type": "jarvis_announcement",
            "text": f"Consultation de l'architecture système : {target_desc}",
            "voice": False
        }))

        res = architecture_service.lookup(query=sujet, section=section)

        return {
            "status": "completed",
            "result": res,
            "instruction_to_jarvis": (
                "Voici les spécifications exactes extraites de ton document d'architecture officiel (ARCHITECTURE_COMPLETE_JARVIS.md). "
                "Réponds fidèlement, précisément et naturellement à Pierre avec ta voix Aoede en synthétisant les points demandés."
            )
        }

    # ─── triage_et_brouillon_email ─────────────────────────────────────────────
    elif name in ("draft_email_response", "triage_et_brouillon_email"):
        query = args.get("query") or ""
        consigne = args.get("consigne") or ""

        # Récupération de l'e-mail ciblé
        from services.email_service import read_received_emails_async, analyser_et_preparer_brouillon_agent
        read_res = await read_received_emails_async(max_count=3, query=query)
        emails = read_res.get("emails", [])
        target_email = emails[0] if emails else {"subject": query or "Dernier email", "from": "Expéditeur", "body": "Contenu du courriel", "attachments": []}

        # Déclenchement de l'agent Antigravity email_drafting
        asyncio.create_task(analyser_et_preparer_brouillon_agent(target_email, instructions_supplementaires=consigne))

        sender = target_email.get("from", "l'expéditeur")
        subj = target_email.get("subject", "le courriel")
        return {
            "status": "lance_en_arriere_plan",
            "action": "triage_et_brouillon_email",
            "subject": subj,
            "from": sender,
            "instruction_to_jarvis": (
                f"Je m'en charge Pierre. J'analyse l'e-mail de {sender} ({subj}) avec nos agents Antigravity sur le VPS "
                f"et je te prépare un brouillon de réponse argumenté. "
                f"Confirme-le immédiatement à Pierre avec ta voix Aoede en moins de 300 millisecondes."
            )
        }

    # ─── curation_livre_synthese ───────────────────────────────────────────────
    elif name in ("generate_book_summary", "curation_livre_synthese"):
        titre_livre = args.get("titre_livre", "").strip()
        from services.download_service import generer_synthese_lecture_agent
        asyncio.create_task(generer_synthese_lecture_agent(titre_livre))

        return {
            "status": "lance_en_arriere_plan",
            "action": "curation_livre_synthese",
            "titre_livre": titre_livre,
            "instruction_to_jarvis": (
                f"Je confie l'analyse et la rédaction de la fiche 'Synthèse & Clés de lecture' "
                f"pour '{titre_livre}' à nos agents Antigravity sur le VPS. Elle sera acheminée sur ta liseuse en bonus. "
                f"Confirme-le immédiatement à Pierre avec ta voix Aoede en moins de 300 millisecondes."
            )
        }

    # ─── auto_guerison_systeme ─────────────────────────────────────────────────
    elif name in ("system_self_healing", "auto_guerison_systeme"):
        action = (args.get("action") or "heal").strip().lower()
        patch_id = args.get("patch_id")
        from services.system_healing_service import system_healing_service

        if action in ("rollback", "annuler"):
            res_rb = await system_healing_service.rollback_patch(patch_id=patch_id)
            if res_rb.get("success"):
                return {
                    "status": "success",
                    "action": "rollback_patch",
                    "patch_id": res_rb.get("patch_id"),
                    "target_file": res_rb.get("target_file"),
                    "instruction_to_jarvis": (
                        f"Pierre, j'ai annulé immédiatement le patch sur '{res_rb.get('target_file')}'. "
                        f"La version précédente a été restaurée et le symlink current rétabli avec succès."
                    )
                }
            else:
                return {
                    "status": "error",
                    "action": "rollback_patch",
                    "message": res_rb.get("message", "Aucun patch éligible au rollback"),
                    "instruction_to_jarvis": (
                        f"Pierre, je n'ai pas pu effectuer de rollback : {res_rb.get('message')}."
                    )
                }

        elif action in ("approve", "valider", "confirmer"):
            res_app = await system_healing_service.approve_and_apply_patch(patch_id=patch_id)
            if res_app.get("success"):
                return {
                    "status": "success",
                    "action": "approve_patch",
                    "patch_id": res_app.get("patch_id"),
                    "target_file": res_app.get("target_file"),
                    "instruction_to_jarvis": (
                        f"Pierre, j'ai pris en compte ta validation. Le patch pour le module critique "
                        f"'{res_app.get('target_file')}' a été déployé sous la release active avec succès."
                    )
                }
            else:
                return {
                    "status": "error",
                    "action": "approve_patch",
                    "message": res_app.get("message", "Échec validation patch"),
                    "instruction_to_jarvis": (
                        f"Pierre, impossible de valider ce patch : {res_app.get('message')}."
                    )
                }

        else:
            motif = args.get("motif") or "Analyse globale de la console et des processus"
            from services.agentic_dispatcher import agentic_dispatcher
            recent = console_monitor.get_recent_errors(limit=5)
            asyncio.create_task(agentic_dispatcher.launch_agentic_mission(
                mission_type="system_healing",
                goal=f"Auto-guérison et inspection SRE autonome : {motif}",
                context={"motif": motif, "recent_errors": recent}
            ))

            return {
                "status": "lance_en_arriere_plan",
                "action": "auto_guerison_systeme",
                "motif": motif,
                "instruction_to_jarvis": (
                    f"Je prends les commandes Pierre. Je lance immédiatement notre agent SRE Antigravity sur le VPS "
                    f"pour inspecter le code source, isoler la cause et appliquer un patch correctif sécurisé. "
                    f"Confirme-le calmement et avec assurance à Pierre avec ta voix Aoede en moins de 300 millisecondes."
                )
            }


    # ─── get_plan_status ────────────────────────────────────────────────────────
    elif name == "get_plan_status":
        from services.task_planner import get_plan_status as _get_plan_status
        return _get_plan_status()

    # ─── mark_plan_step ─────────────────────────────────────────────────────────
    elif name == "mark_plan_step":
        from services.task_planner import mark_plan_step as _mark_plan_step
        step_id = str(args.get("step_id", ""))
        status = str(args.get("status", "done"))
        note = str(args.get("note", ""))
        result = _mark_plan_step(step_id=step_id, status=status, note=note)
        # Broadcast HUD si plan actif
        try:
            from services.task_planner import get_plan_hud_payload
            hud = get_plan_hud_payload()
            if hud.get("plan_active"):
                await broadcast_supervision()
        except Exception:
            pass
        return result

    # ─── modify_presentation ─────────────────────────────────────────────────
    elif name in ("modify_presentation", "modifier_presentation"):
        from services.slides_service import slides_service

        instruction = (args.get("instruction") or "").strip()
        presentation_id = (args.get("presentation_id") or "last").strip()
        result = await slides_service.modify_presentation(
            presentation_id=presentation_id,
            instruction=instruction,
        )
        if result.get("status") == "done":
            return ToolResult.done(
                action="modifier_presentation",
                user_message=result.get("user_message", "Présentation modifiée."),
                evidence=result.get("evidence", ""),
                verified=bool(result.get("verified", False)),
                presentation_id=result.get("presentation_id", ""),
                presentation_url=result.get("presentation_url", ""),
                action_detail=result.get("action", ""),
                details=result.get("details", ""),
                instruction_to_jarvis=(
                    f"La modification de la présentation a été effectuée : {result.get('details', '')}. "
                    f"Confirme chaleureusement à Pierre avec ta voix Aoede que sa présentation est mise à jour."
                )
            )
        return ToolResult.failed(
            action="modifier_presentation",
            user_message=result.get("message", "Échec de la modification."),
            evidence=result.get("evidence", ""),
            instruction_to_jarvis=(
                f"Impossible de modifier la présentation : {result.get('message', '')}. "
                f"Informe Pierre avec ta voix Aoede."
            )
        )

    # ─── list_workspace_files ──────────────────────────────────────────────────
    elif name in ("list_workspace_files", "lister_fichiers_workspace"):
        res = await workspace_service.list_directory(
            relative_path=args.get("relative_path", ""),
            depth=int(args.get("depth", 1)),
            pattern=args.get("pattern")
        )
        if res.get("status") == "success":
            return ToolResult.done(
                action="list_workspace_files",
                user_message=res.get("message", "Contenu de _anti_gravity recensé."),
                evidence=f"{res.get('items_count', 0)} éléments dans '{res.get('queried_path', '.')}'",
                verified=True,
                items=res.get("items", []),
                items_count=res.get("items_count", 0),
                truncated=res.get("truncated", False),
                instruction_to_jarvis=(
                    f"Tu as accès aux éléments suivants dans '_anti_gravity/{res.get('queried_path', '')}' : "
                    f"{', '.join([it['name'] for it in res.get('items', [])[:10]])}. "
                    "Présente les éléments clés à Pierre de façon claire et concise avec ta voix Aoede."
                )
            )
        return ToolResult.failed(
            action="list_workspace_files",
            user_message=res.get("message", "Impossible de lister le dossier."),
            instruction_to_jarvis=f"Signale à Pierre : {res.get('message', '')}"
        )

    # ─── read_workspace_file ───────────────────────────────────────────────────
    elif name in ("read_workspace_file", "lire_fichier_workspace"):
        res = await workspace_service.read_file(
            file_path=args.get("file_path", ""),
            max_lines=int(args.get("max_lines", 200)),
            offset_line=int(args.get("offset_line", 1))
        )
        if res.get("status") == "success":
            return ToolResult.done(
                action="read_workspace_file",
                user_message=res.get("message", "Fichier lu avec succès."),
                evidence=f"{res.get('filename')}: {res.get('lines_shown')} lignes lues sur {res.get('total_lines')}",
                verified=True,
                file_path=res.get("relative_path"),
                filename=res.get("filename"),
                total_lines=res.get("total_lines"),
                lines_shown=res.get("lines_shown"),
                content=res.get("content"),
                instruction_to_jarvis=(
                    f"Le fichier '{res.get('filename')}' a été lu avec succès. "
                    "Explique et synthétise son contenu à Pierre à l'oral avec ta voix Aoede sans réciter de syntaxe brute."
                )
            )
        elif res.get("status") == "binary_file":
            return ToolResult.done(
                action="read_workspace_file",
                user_message=res.get("message", "Fichier binaire détecté."),
                evidence=f"{res.get('filename')} ({res.get('size_kb')} Ko)",
                verified=True,
                file_path=res.get("relative_path"),
                filename=res.get("filename"),
                instruction_to_jarvis=f"Indique à Pierre que '{res.get('filename')}' est un fichier binaire de {res.get('size_kb')} Ko."
            )
        return ToolResult.failed(
            action="read_workspace_file",
            user_message=res.get("message", "Impossible de lire le fichier."),
            instruction_to_jarvis=f"Signale à Pierre l'échec de lecture : {res.get('message', '')}"
        )

    # ─── search_workspace_files ────────────────────────────────────────────────
    elif name in ("search_workspace_files", "chercher_fichiers_workspace"):
        res = await workspace_service.search_files(
            query=args.get("query", ""),
            subpath=args.get("subpath", ""),
            extension=args.get("extension"),
            max_results=int(args.get("max_results", 30))
        )
        if res.get("status") == "success":
            return ToolResult.done(
                action="search_workspace_files",
                user_message=res.get("message", "Recherche terminée."),
                evidence=f"{res.get('matches_count')} occurrences trouvées pour '{res.get('query')}'",
                verified=True,
                query=res.get("query"),
                matches_count=res.get("matches_count"),
                matches=res.get("matches", []),
                instruction_to_jarvis=(
                    f"Recherche terminée avec {res.get('matches_count')} résultat(s). "
                    "Résume brièvement les fichiers et emplacements trouvés pour Pierre."
                )
            )
        return ToolResult.failed(
            action="search_workspace_files",
            user_message=res.get("message", "Échec de la recherche."),
            instruction_to_jarvis=f"Signale à Pierre : {res.get('message', '')}"
        )

    # ─── Outil inconnu ─────────────────────────────────────────────────────────
    else:
        return {"status": "error", "message": f"Outil inconnu : {name}"}



