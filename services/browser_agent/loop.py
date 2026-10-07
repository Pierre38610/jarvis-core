"""Boucle d'exécution du Browser Agent Jarvis (S2).

Orchestre les étapes de navigation autonome :
open_task -> boucle [snapshot -> decide -> (screenshot + vision si need_screenshot) -> guards -> act -> historique] -> done -> verify.
"""

import asyncio
import base64
from dataclasses import dataclass, field
import logging
import os
import re
import tempfile
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional
import urllib.parse

import config
from core.tools.result import ToolResult
from services.browser_agent import cli_brain, guards, site_memory
from services.local_agent_service import local_agent_service, is_pc_connected_async
from services.l3_error import L3ErrorDetails, set_last_l3_error, get_last_l3_error, sanitize_error_text

logger = logging.getLogger("jarvis.browser_agent.loop")

# Configuration des seuils et temporisations
HANDOFF_INTERVAL = 5.0
HANDOFF_MAX_DURATION = 300.0


@dataclass
class BrowserTask:
    """Représente une tâche de navigation web autonome."""

    task_id: str
    goal: str
    start_url: Optional[str] = None
    recipe: Optional[str] = None
    status: str = "running"  # "running|done|ready_for_user|needs_user|failed|cancelled"
    steps: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    result: str = ""
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    last_error: Optional[Dict[str, Any]] = None


# Registre global des tâches
TASKS: Dict[str, BrowserTask] = {}
TASK_SEMAPHORE = asyncio.Semaphore(getattr(config, "BROWSER_MAX_PARALLEL_TASKS", 2))


def get_task(task_id: str) -> Optional[BrowserTask]:
    """Récupère une tâche active par son identifiant."""
    return TASKS.get(task_id)


def cancel_task(task_id: str) -> bool:
    """Déclenche l'annulation d'une tâche de navigation active."""
    task = TASKS.get(task_id)
    if task:
        task.cancel_event.set()
        task.status = "cancelled"
        logger.info("[BrowserLoop] Annulation demandée pour task=%s", task_id)
        return True
    return False


async def _call_rpc(action: str, timeout: float = 30.0, **params) -> Dict[str, Any]:
    """Transmet une commande RPC à l'agent local sur le PC."""
    return await local_agent_service.execute_command(action, timeout=timeout, **params)


class RecipeDict(dict):
    """Dictionnaire de recette permettant l'accès par clé ou par attribut."""

    def __getattr__(self, item: str) -> Any:
        return self.get(item)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def load_recipe(name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Lit recipes/<name>.md et en extrait start_url, max_steps, max_duration, critere et le texte complet."""
    if not name:
        return None

    recipe_text: Optional[str] = None
    if "\n" in name:
        recipe_text = name
    else:
        recipes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes")
        candidates = [
            name,
            os.path.join(recipes_dir, name),
            os.path.join(recipes_dir, f"{name}.md"),
        ]
        for cand in candidates:
            if os.path.isfile(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        recipe_text = f.read()
                    break
                except Exception as e:
                    logger.warning("[BrowserLoop] Impossible de lire la recette %s: %s", cand, e)

    if recipe_text is None:
        return None

    result = RecipeDict({
        "start_url": "",
        "max_steps": getattr(config, "BROWSER_MAX_STEPS", 40),
        "max_duration": getattr(config, "BROWSER_MAX_DURATION", 1800),
        "critere": "",
        "text": recipe_text,
    })

    for line in recipe_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if ":" in line_clean:
            key, _, val = line_clean.partition(":")
            key_norm = key.strip().lower().replace("è", "e").replace("é", "e").replace("ê", "e")
            val_clean = val.strip()

            if key_norm in ("start_url", "url"):
                result["start_url"] = val_clean
            elif key_norm in ("max_steps", "steps", "max_step"):
                try:
                    result["max_steps"] = int(val_clean)
                except ValueError:
                    pass
            elif key_norm in ("max_duration", "duration", "timeout"):
                try:
                    result["max_duration"] = int(val_clean)
                except ValueError:
                    pass
            elif key_norm in ("critere", "critere_de_reussite", "criteria"):
                result["critere"] = val_clean
                result["critère"] = val_clean

    return result


def _load_recipe_text(recipe: Optional[str]) -> Optional[str]:
    """Charge le contenu textuel d'une recette si un nom ou un chemin est fourni."""
    rec = load_recipe(recipe)
    return rec["text"] if rec else recipe


def _extract_success_criteria(recipe_text: Optional[str], default_goal: str) -> str:
    """Extrait le critère de réussite d'une recette ou utilise l'objectif par défaut."""
    if not recipe_text:
        return default_goal
    match = re.search(
        r"crit[èe]re\s*(?:de\s+r[ée]ussite)?\s*:\s*(.+)$",
        recipe_text,
        re.IGNORECASE | re.MULTILINE,
    )
    if match:
        return match.group(1).strip()
    return default_goal


async def _run_local_browser_loop(
    task: BrowserTask,
    notify: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ToolResult:
    """Exécute la boucle de navigation sur l'agent local PC via RPC."""
    recipe_data = load_recipe(task.recipe) if task.recipe else None
    recipe_text = recipe_data["text"] if recipe_data else _load_recipe_text(task.recipe)

    if recipe_data:
        if not task.start_url and recipe_data.get("start_url"):
            task.start_url = recipe_data["start_url"]
        max_steps = recipe_data.get("max_steps") or getattr(config, "BROWSER_MAX_STEPS", 40)
        max_duration = float(recipe_data.get("max_duration") or getattr(config, "BROWSER_MAX_DURATION", 1800))
        success_criteria = recipe_data.get("critere") or _extract_success_criteria(recipe_text, task.goal)
    else:
        max_steps = getattr(config, "BROWSER_MAX_STEPS", 40)
        max_duration = float(getattr(config, "BROWSER_MAX_DURATION", 1800))
        success_criteria = _extract_success_criteria(recipe_text, task.goal)

    # 1. Ouverture de la tâche sur le navigateur local
    open_res = await _call_rpc(
        "browser_open_task",
        task_id=task.task_id,
        start_url=task.start_url or "",
    )
    if open_res.get("ok") is False or open_res.get("status") in {"error", "pc_offline", "timeout"}:
        task.status = "failed"
        raw_err = open_res.get("error") or open_res.get("message") or "Échec browser_open_task"
        err_msg = sanitize_error_text(str(raw_err))
        l3_err = L3ErrorDetails(
            etape="browser_open_task",
            exception=err_msg,
            traceback_court="",
            capture_ecran=None,
            cause_courte=f"Impossible de démarrer la navigation : {err_msg}",
        )
        task.last_error = l3_err.to_dict()
        set_last_l3_error(task.last_error)
        logger.error("[BrowserLoop] [DeepResearch] task=%s échec ouverture: %s", task.task_id, err_msg)
        return ToolResult.failed(
            user_message=f"Impossible de démarrer la navigation : {err_msg}",
            task_id=task.task_id,
            error_hint=err_msg,
            data={"l3_error": l3_err.to_dict()},
        )

    consecutive_errors = 0
    need_screenshot = False
    step_thoughts: List[str] = []
    current_url = task.start_url or ""
    screenshot_path = None
    start_time = time.time()

    # 2. Boucle principale de navigation (S2)
    for step_n in range(1, max_steps + 1):
        task.steps = step_n

        if time.time() - start_time > max_duration:
            task.status = "failed"
            await _call_rpc("browser_close_task", task_id=task.task_id)
            logger.warning("[BrowserLoop] [DeepResearch] task=%s timeout max_duration=%ss", task.task_id, max_duration)
            l3_err = L3ErrorDetails(
                etape="max_duration",
                exception="max_duration_exceeded",
                traceback_court="",
                capture_ecran=screenshot_path,
                cause_courte=f"Durée maximale dépassée ({int(max_duration)}s)",
            )
            task.last_error = l3_err.to_dict()
            set_last_l3_error(task.last_error)
            return ToolResult.failed(
                user_message=f"La tâche de navigation a dépassé la durée maximale de {int(max_duration)}s.",
                task_id=task.task_id,
                error_hint="max_duration_exceeded",
                evidence=current_url,
                data={"l3_error": l3_err.to_dict()},
            )

        if task.cancel_event.is_set():
            task.status = "cancelled"
            await _call_rpc("browser_close_task", task_id=task.task_id)
            logger.info("[BrowserLoop] task=%s step=%s actions=[] ok=False (cancelled)", task.task_id, step_n)
            return ToolResult.failed(
                user_message="La tâche de navigation a été annulée.",
                task_id=task.task_id,
                error_hint="cancelled",
            )

        # OBSERVER
        snap_res = await _call_rpc("browser_snapshot", task_id=task.task_id)
        if not isinstance(snap_res, dict) or snap_res.get("ok") is False:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                need_screenshot = True
            logger.warning(
                "[BrowserLoop] task=%s step=%s actions=['snapshot'] ok=False",
                task.task_id,
                step_n,
            )
            await asyncio.sleep(1.0)
            continue

        snapshot = snap_res
        if snapshot.get("url"):
            current_url = str(snapshot.get("url"))

        # Mémoire par site
        domain = urllib.parse.urlparse(current_url).netloc
        memory_hint = site_memory.load_hint(domain, task.goal) if domain else ""

        # Capture d'écran préalable si forcée par 3 erreurs consécutives
        screenshot_path = None
        if need_screenshot:
            shot_res = await _call_rpc("browser_screenshot", task_id=task.task_id)
            if shot_res.get("ok") and (shot_res.get("image") or shot_res.get("screenshot")):
                b64_data = shot_res.get("image") or shot_res.get("screenshot")
                tmp_base = "/tmp" if os.name != "nt" else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".cache")
                tmp_dir = os.path.join(tmp_base, "jarvis_browser", task.task_id)
                os.makedirs(tmp_dir, exist_ok=True)
                screenshot_path = os.path.join(tmp_dir, f"step_{step_n}.jpg")
                try:
                    with open(screenshot_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                except Exception as e:
                    logger.warning("[BrowserLoop] Échec sauvegarde screenshot: %s", e)
                    screenshot_path = None

        # DÉCIDER
        decision = await cli_brain.decide(
            goal=task.goal,
            recipe_text=recipe_text,
            memory_hint=memory_hint,
            snapshot=snapshot,
            history=task.history[-6:],
            screenshot_path=screenshot_path,
        )

        # Si le brain réclame une capture d'écran (need_screenshot=True) et qu'on ne l'a pas déjà faite
        if decision.get("need_screenshot") and not screenshot_path:
            shot_res = await _call_rpc("browser_screenshot", task_id=task.task_id)
            if shot_res.get("ok") and (shot_res.get("image") or shot_res.get("screenshot")):
                b64_data = shot_res.get("image") or shot_res.get("screenshot")
                tmp_base = "/tmp" if os.name != "nt" else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".cache")
                tmp_dir = os.path.join(tmp_base, "jarvis_browser", task.task_id)
                os.makedirs(tmp_dir, exist_ok=True)
                screenshot_path = os.path.join(tmp_dir, f"step_{step_n}.jpg")
                try:
                    with open(screenshot_path, "wb") as f:
                        f.write(base64.b64decode(b64_data))
                    # Appel CLI vision dont la réponse remplace celle du brain
                    decision = await cli_brain.decide(
                        goal=task.goal,
                        recipe_text=recipe_text,
                        memory_hint=memory_hint,
                        snapshot=snapshot,
                        history=task.history[-6:],
                        screenshot_path=screenshot_path,
                    )
                except Exception as e:
                    logger.warning("[BrowserLoop] Échec analyse vision: %s", e)

        # Réinitialisation du besoin de capture pour l'étape suivante
        need_screenshot = False

        thought = decision.get("thought", "")
        if thought:
            step_thoughts.append(str(thought))

        # GESTION HANDOFF
        handoff = decision.get("handoff")
        if handoff and isinstance(handoff, dict):
            await _call_rpc("browser_focus", task_id=task.task_id)
            handoff_msg = (
                handoff.get("message")
                or "Une intervention de votre part est requise sur le navigateur."
            )
            if notify:
                try:
                    await notify(handoff_msg)
                except Exception as exc:
                    logger.warning("[BrowserLoop] Erreur appel notify: %s", exc)

            # Surveillance toutes les 5 s pendant 5 min max
            start_handoff = time.time()
            handoff_resolved = False

            while time.time() - start_handoff < HANDOFF_MAX_DURATION:
                try:
                    await asyncio.wait_for(task.cancel_event.wait(), timeout=HANDOFF_INTERVAL)
                    task.status = "cancelled"
                    await _call_rpc("browser_close_task", task_id=task.task_id)
                    return ToolResult.failed(
                        user_message="La tâche a été annulée pendant l'attente utilisateur.",
                        task_id=task.task_id,
                        error_hint="cancelled",
                    )
                except asyncio.TimeoutError:
                    pass

                ho_snap = await _call_rpc("browser_snapshot", task_id=task.task_id)
                if isinstance(ho_snap, dict) and ho_snap.get("ok"):
                    ho_decision = await cli_brain.decide(
                        goal=task.goal,
                        recipe_text=recipe_text,
                        memory_hint=memory_hint,
                        snapshot=ho_snap,
                        history=task.history[-6:],
                    )
                    if not ho_decision.get("handoff"):
                        handoff_resolved = True
                        decision = ho_decision
                        snapshot = ho_snap
                        break

            if not handoff_resolved:
                task.status = "needs_user"
                logger.info(
                    "[BrowserLoop] task=%s step=%s actions=['handoff_timeout'] ok=False",
                    task.task_id,
                    step_n,
                )
                return ToolResult.needs_user(
                    user_message=handoff_msg,
                    task_id=task.task_id,
                    evidence=current_url,
                    data={"reason": handoff.get("reason"), "url": current_url},
                )

        # VÉRIFICATION DE FIN (done=True)
        if decision.get("done"):
            verif_snap = await _call_rpc("browser_snapshot", task_id=task.task_id)
            active_snap = verif_snap if isinstance(verif_snap, dict) and verif_snap.get("ok") else snapshot
            final_url = str(active_snap.get("url") or current_url)

            verif_res = await cli_brain.verify(task.goal, success_criteria, active_snap)
            if verif_res.get("ok"):
                task.status = "done"
                if domain:
                    site_memory.save_success(domain, task.goal, step_thoughts)
                await _call_rpc("browser_focus", task_id=task.task_id)

                reason = verif_res.get("reason", "Objectif vérifié avec succès")
                logger.info(
                    "[BrowserLoop] task=%s step=%s actions=['done'] ok=True",
                    task.task_id,
                    step_n,
                )
                evidence_str = f"{final_url} - {reason}"
                return ToolResult.done(
                    user_message=task.result or f"Objectif atteint : {reason}",
                    evidence=evidence_str,
                    verified=True,
                    task_id=task.task_id,
                    data={"url": final_url, "reason": reason, "steps": task.steps},
                )
            else:
                fail_reason = verif_res.get("reason", "Vérification non concluante")
                task.history.append({
                    "action": {"type": "verify"},
                    "ok": False,
                    "error": f"Échec vérification : {fail_reason}",
                })
                logger.info(
                    "[BrowserLoop] task=%s step=%s actions=['verify_failed'] ok=False",
                    task.task_id,
                    step_n,
                )
                continue

        # GARDE-FOUS (guards)
        actions = decision.get("actions", [])
        allowed_actions = []
        payment_blocked = False

        elements = snapshot.get("elements", [])
        for act in actions:
            allowed, reason = guards.check_action(act, elements)
            if not allowed:
                if "payment" in reason.lower():
                    payment_blocked = True
                    break
                else:
                    task.history.append({
                        "action": act,
                        "ok": False,
                        "error": f"Bloqué par garde-fou : {reason}",
                    })
            else:
                allowed_actions.append(act)

        # Si guards refuse un clic de paiement : status ready_for_user, browser_focus, et arrêt immédiat
        if payment_blocked:
            task.status = "ready_for_user"
            await _call_rpc("browser_focus", task_id=task.task_id)
            logger.info(
                "[BrowserLoop] task=%s step=%s actions=%s ok=True (ready_for_user)",
                task.task_id,
                step_n,
                [a.get("type") for a in actions],
            )
            return ToolResult.needs_user(
                user_message="C'est prêt, il ne te reste qu'à valider.",
                evidence=f"{current_url} (ready_for_user)",
                task_id=task.task_id,
                data={"status": "ready_for_user", "url": current_url},
            )

        # AGIR (browser_act)
        step_ok = True
        action_types = [a.get("type") for a in allowed_actions]

        if allowed_actions:
            act_results = await _call_rpc(
                "browser_act",
                task_id=task.task_id,
                actions=allowed_actions,
            )
            if isinstance(act_results, list):
                has_error = False
                for ar in act_results:
                    act_item = ar.get("action", {})
                    if ar.get("ok"):
                        if act_item.get("type") == "extract":
                            text_extracted = ar.get("text", "")
                            task.result = text_extracted
                            task.history.append({
                                "action": act_item,
                                "ok": True,
                                "result": f"extract OK, {len(text_extracted)} caractères",
                            })
                        else:
                            task.history.append({"action": act_item, "ok": True})
                    else:
                        has_error = True
                        task.history.append({
                            "action": act_item,
                            "ok": False,
                            "error": ar.get("error", "action failed"),
                        })

                if has_error:
                    step_ok = False
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
            else:
                step_ok = False
                consecutive_errors += 1
                task.history.append({
                    "action": allowed_actions,
                    "ok": False,
                    "error": str(act_results),
                })
        else:
            step_ok = False
            consecutive_errors += 1

        if consecutive_errors >= 3:
            need_screenshot = True

        # Logs : une ligne par étape (task_id, n, actions, ok)
        logger.info(
            "[BrowserLoop] task=%s step=%s actions=%s ok=%s",
            task.task_id,
            step_n,
            action_types,
            step_ok,
        )

    # Fin des étapes maximales sans complétion
    task.status = "failed"
    l3_err = L3ErrorDetails(
        etape="max_steps",
        exception="max_steps_exceeded",
        traceback_court="",
        capture_ecran=screenshot_path if 'screenshot_path' in locals() else None,
        cause_courte=f"Limite de {max_steps} étapes atteinte sans validation",
    )
    task.last_error = l3_err.to_dict()
    set_last_l3_error(task.last_error)
    logger.warning("[BrowserLoop] [DeepResearch] task=%s max_steps_exceeded (%s steps)", task.task_id, max_steps)
    return ToolResult.failed(
        user_message=f"La tâche de navigation n'a pas abouti après {max_steps} étapes.",
        task_id=task.task_id,
        error_hint="max_steps_exceeded",
        evidence=current_url,
        data={"l3_error": l3_err.to_dict()},
    )


async def _run_gemini_deep_research_task(
    task: BrowserTask,
    notify: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ToolResult:
    """Exécute une tâche L3 avec l'ordre strict des replis :
      1. Chrome VPS autonome via GeminiWebAutomator (connecté au port CDP VPS 9222).
      2. Agent local PC si disponible (via _run_local_browser_loop).
      3. Échec structuré retourné pour déclencher le repli Map-Reduce Antigravity dans le dispatcher.
    """
    logger.info("[BrowserLoop] [DeepResearch] Lancement tâche L3 gemini_deep_research (task_id=%s, goal=%s)", task.task_id, task.goal)

    # ── 1. Tentative Chrome VPS via GeminiWebAutomator ──
    vps_err_data = None
    try:
        from services.gemini_web_automator import GeminiWebAutomator
        automator = GeminiWebAutomator()
        dr_res = await automator.run_deep_research(
            topic=task.goal,
            task_id=task.task_id,
        )

        if dr_res and dr_res.get("status") == "completed":
            task.status = "done"
            md_path = dr_res.get("markdown_path")
            html_path = dr_res.get("html_path")
            md_content = dr_res.get("markdown_content") or ""
            if not md_content and md_path and os.path.exists(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        md_content = f.read()
                except Exception:
                    pass

            task.result = md_content or html_path or md_path or "Recherche approfondie Gemini Web terminée."
            evidence = f"gemini_deep_research (VPS Chrome CDP: {dr_res.get('page_url') or html_path or md_path})"
            user_msg = (
                f"Recherche approfondie sur « {task.goal} » terminée avec succès. "
                f"La page web interactive a été générée et envoyée par e-mail à Pierre."
            )
            if md_content:
                user_msg = f"{user_msg}\n\n{md_content}"
            logger.info("[BrowserLoop] [DeepResearch] ✔ Succès recherche L3 autonome via Chrome VPS (task_id=%s)", task.task_id)
            return ToolResult.done(
                user_message=user_msg,
                evidence=evidence,
                verified=True,
                task_id=task.task_id,
                data={
                    "engine": "vps_chrome",
                    "status": "completed",
                    "markdown_path": md_path,
                    "html_path": html_path,
                    "page_url": dr_res.get("page_url"),
                    "delivery": dr_res.get("delivery"),
                    "duration_seconds": dr_res.get("duration_seconds"),
                },
            )

        vps_err_data = dr_res.get("l3_error") if isinstance(dr_res, dict) else None
        vps_err_msg = (dr_res.get("error") if isinstance(dr_res, dict) else None) or "Échec de l'automateur Chrome VPS"
        logger.warning(
            "[BrowserLoop] [DeepResearch] ⚠️ Chrome VPS non concluant (%s), tentative de repli vers agent local PC.",
            vps_err_msg,
        )
    except Exception as e:
        import traceback
        tb_short = sanitize_error_text(traceback.format_exc(limit=3))[-500:]
        e_str = sanitize_error_text(str(e))
        l3_err = L3ErrorDetails(
            etape="vps_chrome_automator",
            exception=f"{e.__class__.__name__}: {e_str}",
            traceback_court=tb_short,
            cause_courte=f"Erreur automateur Chrome VPS ({e.__class__.__name__})",
            fallback_initiated=True,
        )
        set_last_l3_error(l3_err)
        vps_err_data = l3_err.to_dict()
        logger.warning(
            "[BrowserLoop] [DeepResearch] [EXCEPTION RECHERCHE L3] Exception Chrome VPS (%s), passage au repli local PC.\n%s",
            e_str,
            tb_short,
        )

    # ── 2. Tentative Agent local PC si disponible ──
    from services.local_agent_service import is_pc_connected_async, local_agent_service

    pc_online = False
    try:
        pc_online = await is_pc_connected_async()
    except Exception:
        pc_online = local_agent_service.is_connected()

    if not pc_online:
        logger.info("[BrowserLoop] [DeepResearch] PC local hors ligne. Déclenchement du repli Map-Reduce.")
        pc_err = L3ErrorDetails(
            etape="local_agent_pc",
            exception="PC local déconnecté",
            traceback_court="",
            cause_courte="Agent local PC hors ligne",
            fallback_initiated=True,
        )
        task.last_error = pc_err.to_dict()
        set_last_l3_error(pc_err)
        task.status = "failed"
        return ToolResult.failed(
            user_message=f"Chrome VPS et agent local PC indisponibles : {pc_err.cause_courte}",
            error_hint="pc_offline",
            task_id=task.task_id,
            data={"l3_error": pc_err.to_dict(), "vps_error": vps_err_data},
        )

    # PC en ligne : tentative d'exécution de la boucle locale PC
    logger.info("[BrowserLoop] [DeepResearch] PC local en ligne, tentative d'exécution via l'agent local PC...")
    local_res = await _run_local_browser_loop(task, notify=notify)
    if local_res and local_res.is_success and task.status != "failed":
        return local_res

    # En cas d'échec de la boucle locale, s'assurer que last_error est bien propagé
    if not task.last_error and local_res and isinstance(local_res.data, dict) and "l3_error" in local_res.data:
        task.last_error = local_res.data["l3_error"]

    return local_res


async def run_browser_task(
    task: BrowserTask,
    notify: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ToolResult:
    """Exécute la boucle complète de navigation autonome pour une tâche donnée."""
    TASKS[task.task_id] = task

    async with TASK_SEMAPHORE:
        if task.cancel_event.is_set():
            task.status = "cancelled"
            return ToolResult.failed(
                user_message="La tâche de navigation a été annulée.",
                task_id=task.task_id,
                error_hint="cancelled",
            )

        if task.recipe == "gemini_deep_research":
            return await _run_gemini_deep_research_task(task, notify=notify)

        return await _run_local_browser_loop(task, notify=notify)


# Alias pour compatibilité d'orchestration
run_browser_agent_task = run_browser_task
