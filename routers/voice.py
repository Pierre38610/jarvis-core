"""routers/voice.py
WebSocket full-duplex Gemini Live — Canal vocal principal de J.A.R.V.I.S.
Gère la boucle PCM, le barge-in, la gestion du quota et le dispatch des outils.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from google.genai import types

import config
import auth
from google_antigravity import is_stop_directive
from services.supervision_service import supervision_service
from services.console_monitor import console_monitor
from services.metrics_service import metrics_service
from core.shared_state import (
    active_task_controller,
    client_free, client_paid,
    broadcast_supervision, broadcast_jarvis_state,
    broadcast_paid_key_status, stop_active_task,
    QuotaExhaustedError, ModelSwitchRequested,
    is_quota_or_limit_error, merge_user_speech,
    get_tool_metadata,
    SpeechState, get_speech_state, set_speech_state, is_speech_idle,
    notify_generation_chunk, notify_turn_complete, notify_playback_finished,
    notify_tool_started, notify_tool_completed, notify_user_speaking,
    notify_interrupted, wait_until_speech_finished, wait_until_speech_idle, safe_send_live_client_content,
    handle_user_barge_in,
)
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from services import task_planner as _task_planner_mod
from services.live_mode_policy import (
    decide as live_mode_decide,
    log_tier_routing_decision,
    LIVE_MODEL_STANDARD,
    LIVE_MODEL_THINKING,
    VOICE_MODE_THINKING,
)
from services.llm_router import resolve_live_fallback
from services.key_gate import (
    PaidKeyConsentRequired,
    grant_paid_consent,
    has_paid_consent,
    is_qualified_free_key_failure,
)
from services.async_utils import fire_and_forget

router = APIRouter()


async def _build_switch_context_prompt(
    recent_turns: list[dict[str, str]],
    announcement_phrase: str = "",
) -> str:
    """Construit le prompt de réinjection de contexte complet lors d'une bascule de modèle Live :
    1. build_live_context_prompt (mémoire unifiée)
    2. 10 derniers tours de dialogue
    3. Plan multi-étapes actif
    4. Sous-agents actifs
    """
    from services.unified_memory import unified_memory_manager

    # 1. Mémoire unifiée
    memory_context = await unified_memory_manager.build_live_context_prompt()

    # 2. 10 derniers tours de dialogue
    last_10 = recent_turns[-10:] if recent_turns else []
    if last_10:
        turns_str = "\n".join([f"- {t.get('role', 'user').upper()}: {t.get('text', '')}" for t in last_10])
    else:
        turns_str = "Aucun tour précédent."

    # 3. Plan actif
    active_plan = _task_planner_mod.get_active_plan()
    if active_plan and hasattr(active_plan, "checklist_text"):
        plan_str = active_plan.checklist_text()
    else:
        plan_str = "Aucun plan actif."

    # 4. Sous-agents actifs
    subagents = supervision_service.get_active_subagents()
    if subagents:
        sub_str = "\n".join([
            f"- [{sa.get('role', 'agent')}] {sa.get('name', 'subagent')} : {sa.get('activity', '')} ({sa.get('task', '')})"
            for sa in subagents
        ])
    else:
        sub_str = "Aucun sous-agent actif."

    prompt = (
        f"[CONTINUITÉ DE CONVERSATION APRÈS BASCULE DE MODÈLE]\n"
        f"MÉMOIRE UNIFIÉE :\n{memory_context}\n\n"
        f"10 DERNIERS TOURS DE DIALOGUE :\n{turns_str}\n\n"
        f"PLAN D'ACTION EN COURS :\n{plan_str}\n\n"
        f"SOUS-AGENTS ACTIFS EN ARRIÈRE-PLAN :\n{sub_str}\n\n"
    )
    if announcement_phrase:
        prompt += (
            f"CONSIGNE VOCALE IMMÉDIATE : Dis exactement et brièvement à Pierre avec ta voix Aoede : '{announcement_phrase}' "
            f"puis poursuis naturellement et réponds à sa demande sans répéter tout le contexte."
        )
    else:
        prompt += (
            "CONSIGNE VOCALE : Poursuis naturellement la conversation avec Pierre en tenant compte de tout ce contexte réinjecté, sans répéter l'historique."
        )

    return prompt


def format_jarvis_system_instruction(
    template: Optional[str] = None,
    current_datetime: Optional[str] = None,
    memory_context: Optional[str] = None,
    active_plan_status: Optional[str] = None,
    active_subagents_status: Optional[str] = None,
    **kwargs
) -> str:
    """Formate le template d'instruction système JARVIS avec les variables requises.
    Si une variable est vide, la valeur 'Aucun' est passée."""
    if template is None:
        template = getattr(config, "JARVIS_SYSTEM_INSTRUCTION_TEMPLATE", "") or ""

    def _val(v: Optional[str]) -> str:
        if v is None:
            return "Aucun"
        s = str(v).strip()
        return s if s else "Aucun"

    format_vars = {
        "current_datetime": _val(current_datetime),
        "memory_context": _val(memory_context),
        "active_plan_status": _val(active_plan_status),
        "active_subagents_status": _val(active_subagents_status),
    }
    format_vars.update(kwargs)
    return template.format(**format_vars)


async def _build_system_instruction() -> str:
    """Construit dynamiquement le system_instruction de la session Live en injectant le contexte mémoire et la règle d'arbitrage de présence PC."""
    from datetime import datetime
    from services.unified_memory import unified_memory_manager
    from services.local_agent_service import is_pc_connected
    from services.turn_audit import get_active_plan_status_str, get_active_subagents_status_str, inject_turn_status_into_prompt

    # Injection dynamique du contexte de mémoire unifiée
    memory_context = await unified_memory_manager.build_live_context_prompt()

    paid_key_status = "CLÉ PAYANTE ACTIVE" if config.HAS_PAID_API_KEY else "CLÉ PAYANTE NON CONFIGURÉE (mode économie forcée)"

    pc_online = is_pc_connected()
    pc_presence_str = "EN LIGNE (PC Windows connecté et prêt pour pilotage Chrome CDP)" if pc_online else "HORS-LIGNE (PC Windows éteint ou déconnecté)"

    nav_arbitration_rule = (
        f"\n\nÉTAT DE PRÉSENCE DU PC WINDOWS ET RÈGLE D'ARBITRAGE DE NAVIGATION :\n"
        f"- État actuel du PC de Pierre : {pc_presence_str}.\n"
        f"- RÈGLE D'ARBITRAGE DE NAVIGATION ET PILOTAGE CHROME LOCAL (CDP vs VPS HEADLESS) :\n"
        f"  Lorsque Pierre te demande une action de navigation web, de recherche visuelle ou d'achat (outils 'run_browser_task', 'prepare_web_cart_or_checkout', 'interact_web_page') :\n"
        f"  * Vérifie l'état de connexion de son PC Windows.\n"
        f"  * Si le PC est HORS-LIGNE : utilise immédiatement execution_target='vps_headless' sans lui poser de question inutile.\n"
        f"  * Si le PC est EN LIGNE et que Pierre n'a pas précisé où exécuter l'action : demande-lui naturellement avec ta voix Aoede : 'Ton PC est allumé Pierre. Tu veux que j'agisse directement sur ton Chrome à l'écran ou je gère ça discrètement en arrière-plan ?'\n"
        f"  * En fonction de sa réponse, appelle l'outil avec execution_target='local_chrome_cdp' (s'il choisit l'écran ou Chrome physique) ou execution_target='vps_headless' (s'il préfère en arrière-plan ou discret)."
    )

    anti_tics_rule = (
        f"\n\nCONSIGNE STRICTE D'ÉLOCUTION NATURELLE ET ANTI-TICS VERBAUX :\n"
        f"- Bannis les amorces robotiques et répétitives en début de réponse telles que 'C'est noté', 'C'est bien noté Pierre', 'Très bien', 'Entendu', 'C'est compris', 'Bien reçu'.\n"
        f"- Varie tes réactions : démarre directement par le verbe d'action ('J'ouvre...', 'Je regarde ça', 'Je m'en charge'), réagis comme un pair naturel ou exécute l'action sans préambule si la demande est simple et évidente.\n"
        f"- Conserve le tutoiement, le ton franc, complice et pragmatique sans servilité."
    )

    cognitive_tier_instruction = (
        f"\n\nPALIERS COGNITIFS (L1 / L2 / L3) ET SÉLECTION D'OUTILS :\n"
        f"- L1 (Économie & Vitesse - Palier par Défaut) : Pour questions factuelles, météo, cours, faits récents, diagnostics légers et actions locales simples. Outil de recherche privilégié : 'search_web'. Si une tâche autonome minimale est requise, exécuter 'run_agentic_task' (modèle flash, effort low). Zéro modèle Pro, zéro navigateur Deep Research lourd pour L1.\n"
        f"- L2 (Raisonnement Tactique & Navigation Web) : Pour navigation web, réservations (billets train, réservation), remplissage de panier, comparaison multi-critères et planification. Outils privilégiés : 'browser_task', 'transport_optimizer', 'spreadsheet_modeler', 'draft_email_response'.\n"
        f"- L3 (Délibération Système 2 & Recherche Approfondie) : Pour études de fond exhaustives, rapports de marché multi-sources, cartographies complètes et auto-guérison système critique. Outils privilégiés : 'launch_deep_research', 'system_self_healing', 'ask_deep_reasoning'.\n"
        f"- Règle anti-doublon : Ne lance jamais deux outils de recherche pour une même intention."
    )

    current_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plan_st = get_active_plan_status_str()
    sub_st = get_active_subagents_status_str()

    template = getattr(config, "JARVIS_SYSTEM_INSTRUCTION_TEMPLATE", None)
    if template:
        try:
            base_prompt = format_jarvis_system_instruction(
                template=template,
                current_datetime=current_dt,
                memory_context=memory_context,
                active_plan_status=plan_st,
                active_subagents_status=sub_st,
                paid_key_status=paid_key_status,
                live_model=config.GEMINI_LIVE_MODEL,
            )
        except Exception:
            base_prompt = str(template)
        return f"{base_prompt}\n{nav_arbitration_rule}\n{anti_tics_rule}\n{cognitive_tier_instruction}"

    static = getattr(config, "JARVIS_SYSTEM_INSTRUCTION", "")
    full_prompt = f"{memory_context}\n\n{static}" if memory_context else static
    full_prompt = inject_turn_status_into_prompt(full_prompt)
    return f"{full_prompt}\n{nav_arbitration_rule}\n{anti_tics_rule}\n{cognitive_tier_instruction}"



async def _establish_live_session(model: str, client_to_use):
    """Établit une session Gemini Live avec la config JARVIS complète (voix Aoede, outils, instruction système)."""
    system_instruction_text = await _build_system_instruction()

    thinking_cfg = types.ThinkingConfig(include_thoughts=True) if "extended-thinking" in model else None

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=get_tools_list(),
        temperature=0.65,
        thinking_config=thinking_cfg,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=getattr(config, "JARVIS_VOICE", None) or "Aoede"
                )
            ),
            language_code="fr-FR"
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=types.Content(
            parts=[types.Part.from_text(text=system_instruction_text)]
        ),
    )

    session_ctx = client_to_use.aio.live.connect(model=model, config=live_config)
    session = await session_ctx.__aenter__()
    return session_ctx, session


@router.websocket("/ws")
async def voice_channel(websocket: WebSocket):
    """Canal WebSocket audio full-duplex Gemini Live principal de J.A.R.V.I.S."""

    # Validation du terminal avant acceptation
    auth_header = websocket.headers.get("authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = websocket.query_params.get("token") or websocket.cookies.get("jarvis_device_token")

    masked_token = f"{token[:4]}...{token[-4:]}" if token and len(token) > 8 else ("***" if token else "None")
    if not auth.is_device_authorized(token):
        print(f"[VoiceWS] ❌ Connexion /ws rejetée (token: {masked_token})")
        await websocket.close(code=1008, reason="Terminal non autorisé")
        return

    print(f"[VoiceWS] 🔌 Connexion /ws autorisée (token: {masked_token})")

    conn_id = f"ws_{uuid.uuid4().hex[:8]}"
    await websocket.accept()
    ws_sessions = active_task_controller.setdefault("ws_sessions", {})
    ws_sessions[conn_id] = websocket
    active_task_controller["websocket"] = websocket
    try:
        await websocket.send_text(json.dumps({
            "type": "paid_key_authorized_update",
            "authorized": config.is_paid_key_authorized(),
            "has_paid_key": config.HAS_PAID_API_KEY
        }))
    except Exception:
        pass

    # Vérification qu'au moins une clé GEMINI est configurée
    if not (client_paid or client_free):
        await websocket.send_text(json.dumps({
            "type": "transcript",
            "role": "jarvis",
            "text": "Erreur : Aucune clé GEMINI configurée."
        }))
        await websocket.close()
        return

    session = None
    session_ctx = None
    greeting_sent = False
    is_model_switch_reconnect = False
    recent_conversation_turns: list[dict[str, str]] = []
    setup_done_event = asyncio.Event()
    speaking_state = {"active": False}

    active_task_controller.pop("pending_model_switch", None)
    active_task_controller.pop("pending_model_switch_meta", None)

    active_live_model = config.GEMINI_LIVE_MODEL

    try:
        # ─── client_to_gemini : Réception des frames PCM et messages depuis le frontend ──────
        async def client_to_gemini():
            """Reçoit l'audio PCM 16kHz 16-bit mono et les messages JSON depuis le frontend et les stream vers Gemini Live."""
            try:
                # Respect du protocole : attendre setup_complete avant d'envoyer l'audio du microphone
                try:
                    await asyncio.wait_for(setup_done_event.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    pass

                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect(code=1000)

                    if "bytes" in msg and msg["bytes"]:
                        # Ne pas saturer Gemini Live d'audio entrant pendant qu'il parle ou restitue du son
                        # ni pendant l'exécution ou le retour d'un outil pour éviter tout barge-in/coupure intempestive
                        now = time.time()
                        is_speaking_or_cooldown = (
                            speaking_state["active"]
                            or active_task_controller.get("speaking_active", False)
                            or now < active_task_controller.get("estimated_speech_end", 0.0) + 0.25
                            or active_task_controller.get("client_speaking", False)
                            or active_task_controller.get("awaiting_tool_response", False)
                            or now < active_task_controller.get("tool_response_cooldown", 0.0)
                        )
                        if not is_speaking_or_cooldown:
                            await session.send_realtime_input(
                                audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                            )

                    elif "text" in msg and msg["text"]:
                        try:
                            payload = json.loads(msg["text"])
                            p_type = payload.get("type", "")

                            if p_type == "speech_started":
                                active_task_controller["client_speaking"] = True
                                notify_user_speaking()

                            elif p_type == "speech_ended":
                                active_task_controller["client_speaking"] = False
                                active_task_controller["speaking_active"] = False
                                active_task_controller["estimated_speech_end"] = 0.0
                                speaking_state["active"] = False
                                notify_user_speaking(False)
                                try:
                                    from services.spotify_service import spotify_service
                                    fire_and_forget(spotify_service.restore_volume(), name="spotify_restore")
                                except Exception:
                                    pass
                                if is_speech_idle():
                                    supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live)
                                    await broadcast_supervision()
                                pending_switch = active_task_controller.pop("pending_model_switch", None)
                                if pending_switch:
                                    raise ModelSwitchRequested(pending_switch)

                            elif p_type == "playback_finished":
                                notify_playback_finished()
                                try:
                                    from services.spotify_service import spotify_service
                                    fire_and_forget(spotify_service.restore_volume(), name="spotify_restore")
                                except Exception:
                                    pass
                                if is_speech_idle():
                                    supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live)
                                    await broadcast_supervision()
                                pending_switch = active_task_controller.pop("pending_model_switch", None)
                                if pending_switch:
                                    raise ModelSwitchRequested(pending_switch)

                            elif p_type == "live_directive":
                                dir_text = payload.get("directive", "").strip()
                                if dir_text:
                                    if is_stop_directive(dir_text):
                                        await stop_active_task(source="live_directive_stop", reason=dir_text)
                                    elif active_task_controller["info"]["running"]:
                                        await active_task_controller["queue"].put(dir_text)
                                        active_task_controller.setdefault("directives", []).append(dir_text)
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Consigne en direct reçue : {dir_text}. Adaptation en cours.",
                                            "voice": False
                                        }))

                            elif p_type == "cancel_active_task":
                                await stop_active_task(source="websocket_cancel_button", reason="Arrêt demandé depuis l'interface")

                            elif p_type == "set_live_model":
                                new_model = (payload.get("model") or "").strip()
                                if new_model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
                                    if new_model != active_live_model:
                                        active_task_controller["pending_model_switch_meta"] = {
                                            "target_mode": "thinking" if "extended-thinking" in new_model else "standard",
                                            "switch_source": "user_demand",
                                            "announcement_phrase": "",
                                        }
                                        if is_speech_idle():
                                            raise ModelSwitchRequested(new_model)
                                        else:
                                            active_task_controller["pending_model_switch"] = new_model
                                            await websocket.send_text(json.dumps({
                                                "type": "jarvis_announcement",
                                                "text": f"Bascule vers {new_model} différée jusqu'à la fin de la phrase en cours...",
                                                "voice": False
                                            }))
                                    else:
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": f"Modèle vocal déjà actif sur {new_model}.",
                                            "voice": False
                                        }))

                            elif p_type == "set_paid_key_authorized":
                                authorized = bool(payload.get("authorized", False))
                                config.set_paid_key_authorized(authorized)
                                active_task_controller["paid_consent_given"] = authorized
                                await broadcast_paid_key_status(authorized)
                                status_text = "activée et autorisée" if authorized else "verrouillée (accès physique coupé)"
                                await websocket.send_text(json.dumps({
                                    "type": "jarvis_announcement",
                                    "text": f"Clé payante {status_text}.",
                                    "voice": False
                                }))
                                if active_task_controller.get("live_session"):
                                    try:
                                        await safe_send_live_client_content(
                                            active_task_controller["live_session"],
                                            text_content=(
                                                f"[INFO SYSTÈME EN DIRECT] Pierre vient de {'COCHER' if authorized else 'DÉCOCHER'} "
                                                f"l'encoche d'autorisation de la clé payante dans l'application. "
                                                f"La clé payante est désormais {'AUTORISÉE' if authorized else 'VERROUILLÉE ET INTERDITE PHYSIQUEMENT'}."
                                            ),
                                            priority=3,
                                            role="user",
                                            turn_complete=True
                                        )
                                    except Exception:
                                        pass
                                await broadcast_supervision()

                            elif p_type == "get_supervision_overview":
                                await broadcast_supervision()

                            elif p_type == "paid_consent_response":
                                action = payload.get("action", "")
                                approved = bool(payload.get("approved", False))
                                active_task_controller["paid_consent_given"] = approved
                                active_task_controller["paid_consent_modal_open"] = False
                                if approved:
                                    config.set_paid_key_authorized(True)
                                    await broadcast_paid_key_status(True)
                                    await broadcast_supervision()
                                if action == "live_fallback":
                                    active_task_controller["paid_live_approved"] = approved
                                if active_task_controller.get("paid_consent_event"):
                                    active_task_controller["paid_consent_event"].set()

                                if approved:
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Autorisation d'accès payant accordée.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                    if active_task_controller.get("live_session"):
                                        try:
                                            await safe_send_live_client_content(
                                                active_task_controller["live_session"],
                                                text_content=(
                                                    "[ACCORD ACCORDÉ DANS LE HUD] Pierre a cliqué sur 'ACCORDER L'ACCÈS PAYANT' sur son écran. "
                                                    "Tu as son accord officiel pour lancer l'action sur l'API payante. "
                                                    "Lance immédiatement la tâche avec confirmed_by_user=True !"
                                                ),
                                                priority=2,
                                                role="user",
                                                turn_complete=True
                                            )
                                        except Exception as e:
                                            print(f"[Paid Consent Injection] {e}")
                                else:
                                    await websocket.send_text(json.dumps({
                                        "type": "jarvis_announcement",
                                        "text": "Utilisation de la clé payante refusée par l'utilisateur.",
                                        "voice": False
                                    }))
                                    await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                    if active_task_controller.get("live_session"):
                                        try:
                                            await safe_send_live_client_content(
                                                active_task_controller["live_session"],
                                                text_content=(
                                                    "[ACCORD REFUSÉ DANS LE HUD] Pierre a cliqué sur 'REFUSER' pour l'accès à la clé payante. "
                                                    "Confirme avec ta voix Aoede que tu n'exécutes pas cette tâche payante et reste à sa disposition pour autre chose."
                                                ),
                                                priority=2,
                                                role="user",
                                                turn_complete=True
                                            )
                                        except Exception as e:
                                            print(f"[Paid Rejection Injection] {e}")

                            elif p_type == "user_interrupt":
                                inter_txt = payload.get("text", "").strip()
                                await handle_user_barge_in(
                                    session=session,
                                    source="pwa_voice",
                                    reason="WebSocket user_interrupt event",
                                    speaking_state=speaking_state,
                                    text=inter_txt,
                                    websocket=websocket,
                                )

                                supervision_service.update_voice_state("listening", model=active_live_model, is_paid=is_paid_live)
                                await broadcast_supervision()
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "state": "listening",
                                    "msg": "À l'écoute, je t'écoute...",
                                    "engine": "Google API Live",
                                    "model": live_display_label,
                                    "api_type": "paid" if is_paid_live else "free",
                                    "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                }))

                            elif p_type == "text":
                                text_input = payload.get("text", "").strip()
                                if text_input and session:
                                    await safe_send_live_client_content(
                                        session,
                                        text_content=text_input,
                                        priority=2,
                                        role="user",
                                        turn_complete=True
                                    )

                            elif p_type == "image":
                                image_b64 = payload.get("data", "")
                                mime = payload.get("mime", "image/jpeg")
                                caption = payload.get("caption", "")
                                if image_b64 and session:
                                    image_bytes = base64.b64decode(image_b64)
                                    parts = [types.Part.from_bytes(data=image_bytes, mime_type=mime)]
                                    if caption:
                                        parts.append(types.Part.from_text(text=caption))
                                    await wait_until_speech_idle(timeout=10.0, sas_delay=0.35)
                                    await session.send_client_content(
                                        turns=types.Content(role="user", parts=parts),
                                        turn_complete=True
                                    )

                            elif p_type == "ping":
                                await websocket.send_text(json.dumps({"type": "pong"}))

                        except ModelSwitchRequested:
                            raise
                        except Exception as e:
                            print(f"[Upload Audio] Erreur message texte: {e}")

            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError, ModelSwitchRequested, QuotaExhaustedError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                err_str = str(e).lower()
                is_normal_close = any(k in err_str for k in [
                    "cannot call", "close message has been sent", "connection closed", "disconnect",
                    "closed", "close", "1000", "1001", "(1000, none)", "1000 none", "connectionclosedok"
                ]) or getattr(e, "code", None) in (1000, 1001)
                if is_normal_close:
                    raise WebSocketDisconnect(code=1000)
                else:
                    print(f"[client_to_gemini] Erreur: {e}")
                    console_monitor.record_error(source="client_to_gemini", message=str(e), level="WARNING")
                    raise
            finally:
                # Fermeture du websocket Google pour débloquer immédiatement gemini_to_client
                try:
                    await session.close()
                except Exception:
                    pass

        # ─── gemini_to_client : Réception des réponses Gemini → Frontend ─────────
        async def gemini_to_client():
            """Reçoit les réponses audio et texte de Gemini Live et les relaie au client."""
            nonlocal recent_conversation_turns
            user_speech_buffer = ""
            is_speaking_state = False
            turn_start_time = time.time()
            turn_user_transcript = ""
            turn_tools = []
            turn_jarvis_sentence = ""
            turn_cuts = 0

            try:
                # Boucle permanente : session.receive() yield une interaction / tour de parole puis se termine.
                # Il faut boucler sur session.receive() pour maintenir la réception des tours successifs.
                while True:
                    async for chunk in session.receive():
                        if getattr(chunk, "setup_complete", None):
                            setup_done_event.set()

                        sc = chunk.server_content
                        if sc:
                            # Interruption (barge-in serveur)
                            if getattr(sc, "interrupted", False):
                                notify_interrupted("user_barge_in")
                                try:
                                    from services.spotify_service import spotify_service
                                    fire_and_forget(spotify_service.restore_volume(), name="spotify_restore")
                                except Exception:
                                    pass
                                turn_cuts += 1
                                metrics_service.record_speech_cut("user_barge_in", details="Gemini Live server content interrupted")
                                print("[Voice Channel] SPEECH_CUT reason=user_barge_in from Gemini Live server content")
                                user_speech_buffer = ""
                                is_speaking_state = False
                                speaking_state["active"] = False
                                active_task_controller["speaking_active"] = False
                                active_task_controller["estimated_speech_end"] = 0.0
                                active_task_controller["client_speaking"] = False
                                await websocket.send_text(json.dumps({"type": "interrupted"}))

                            # Transcription voix utilisateur
                            user_txt = None
                            if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                                user_txt = sc.input_transcription.text
                            elif getattr(sc, "interim_input_transcription", None) and sc.interim_input_transcription.text:
                                user_txt = sc.interim_input_transcription.text

                            if user_txt:
                                user_speech_buffer = merge_user_speech(user_speech_buffer, user_txt)
                                turn_user_transcript = user_speech_buffer
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": user_speech_buffer,
                                    "mode": "set"
                                }))

                                # 1. Évaluation dynamique de la politique Live (LiveModePolicy)
                                _plan_curr = _task_planner_mod.get_active_plan()
                                _plan_steps = len(_plan_curr.steps) if _plan_curr else 0
                                _speech_st = get_speech_state()

                                decision = live_mode_decide(
                                    transcript=user_speech_buffer,
                                    plan_active=_plan_steps,
                                    recent_failures=active_task_controller.get("recent_tool_failures", 0),
                                    tier_hint=active_task_controller.get("current_tier_hint", 1),
                                    session_id="voice",
                                    speech_state=_speech_st,
                                )

                                # Propagation du palier cognitif L1/L2/L3 et observabilité
                                active_task_controller["current_cognitive_level"] = decision.get("cognitive_level", 1)
                                active_task_controller["current_level_name"] = decision.get("cognitive_level_name", "L1")
                                active_task_controller["current_level_reason"] = decision.get("cognitive_level_reason", "")
                                active_task_controller["current_tier_hint"] = decision.get("cognitive_level", 1)

                                # 5. Journalisation systématique dans tier_routing_log
                                asyncio.create_task(log_tier_routing_decision(user_speech_buffer, decision))

                                target_model = LIVE_MODEL_THINKING if decision.get("target_mode") == "thinking" else LIVE_MODEL_STANDARD
                                if target_model != active_live_model:
                                    active_task_controller["pending_model_switch_meta"] = decision
                                    if decision.get("switch_deferred") or not is_speech_idle():
                                        active_task_controller["pending_model_switch"] = target_model
                                        print(f"[Voice Channel] Bascule vers {target_model} différée (Jarvis parle, SpeechState={_speech_st})")
                                    else:
                                        print(f"[Voice Channel] Bascule immédiate vers {target_model} (SpeechState IDLE)")
                                        raise ModelSwitchRequested(target_model)

                                # 2. Détection prioritaire immédiate d'ordre d'arrêt d'action en cours
                                is_any_task_running = (
                                    active_task_controller["info"]["running"]
                                    or bool(active_task_controller.get("bg_task"))
                                    or bool(active_task_controller.get("browser_bg_task"))
                                )
                                if is_any_task_running and (is_stop_directive(user_txt) or is_stop_directive(user_speech_buffer)):
                                    print(f"[Voice Channel] INTERCEPTION VOCALE IMMÉDIATE D'ARRÊT : '{user_speech_buffer}'")
                                    await stop_active_task(source="voice_intercept", reason=user_speech_buffer)
                                    user_speech_buffer = ""
                                    if session:
                                        try:
                                            await safe_send_live_client_content(
                                                session,
                                                text_content="[ACTION IMMÉDIATEMENT ARRÊTÉE] Le développement ou la tâche en cours a été coupé immédiatement selon l'ordre de Pierre. Confirme avec ta voix Aoede que l'action est bien arrêtée.",
                                                priority=1,
                                                role="user",
                                                turn_complete=True
                                            )
                                        except Exception:
                                            pass

                                # 3. Détection d'accord oral si demande de clé payante en attente
                                if active_task_controller.get("paid_consent_modal_open"):
                                    affirmative_words = ["oui", "d'accord", "vas-y", "je valide", "autorise", "fais-le", "c'est bon", "accepte", "valide", "je t'autorise"]
                                    t_clean = user_speech_buffer.lower().strip()
                                    if any(w in t_clean for w in affirmative_words):
                                        print(f"[Voice Channel] Accord oral détecté pour clé payante : '{user_speech_buffer}'")
                                        grant_paid_consent(session_id="voice", reason="free_key_failure", scope="this_task")
                                        active_task_controller["paid_consent_given"] = True
                                        active_task_controller["paid_consent_modal_open"] = False
                                        await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                        if active_task_controller.get("paid_consent_event"):
                                            active_task_controller["paid_consent_event"].set()

                            # Tour de parole du modèle
                            if sc.model_turn:
                                if user_speech_buffer:
                                    recent_conversation_turns.append({"role": "user", "text": user_speech_buffer})
                                    if len(recent_conversation_turns) > 20:
                                        recent_conversation_turns = recent_conversation_turns[-20:]
                                user_speech_buffer = ""
                                for part in sc.model_turn.parts:
                                    if getattr(part, 'thought', False) and part.text:
                                        supervision_service.update_voice_state("thinking", model=active_live_model, is_paid=is_paid_live)
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "status",
                                            "state": "thinking",
                                            "msg": "JARVIS analyse votre demande...",
                                            "engine": "Google API",
                                            "model": live_display_label,
                                            "api_type": "paid" if is_paid_live else "free",
                                            "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite"
                                        }))
                                    elif part.text and not getattr(sc, "output_transcription", None):
                                        turn_jarvis_sentence = f"{turn_jarvis_sentence} {part.text}".strip()
                                        recent_conversation_turns.append({"role": "jarvis", "text": part.text})
                                        if len(recent_conversation_turns) > 20:
                                            recent_conversation_turns = recent_conversation_turns[-20:]
                                        await websocket.send_text(json.dumps({
                                            "type": "transcript",
                                            "role": "jarvis",
                                            "text": part.text
                                        }))
                                    elif part.inline_data and part.inline_data.data:
                                        chunk_dur = len(part.inline_data.data) / (24000 * 2)
                                        notify_generation_chunk(chunk_dur)
                                        speaking_state["active"] = True
                                        active_task_controller["speaking_active"] = True
                                        now = time.time()
                                        active_task_controller["last_audio_chunk_time"] = now
                                        active_task_controller["estimated_speech_end"] = max(
                                            active_task_controller.get("estimated_speech_end", 0.0), now
                                        ) + chunk_dur
                                        if not is_speaking_state:
                                            is_speaking_state = True
                                            try:
                                                from services.spotify_service import spotify_service
                                                fire_and_forget(spotify_service.duck_volume(), name="spotify_duck")
                                            except Exception:
                                                pass
                                            supervision_service.update_voice_state("speaking", model=active_live_model, is_paid=is_paid_live)
                                            await broadcast_supervision()
                                            await websocket.send_text(json.dumps({
                                                "type": "status",
                                                "state": "speaking",
                                                "msg": "JARVIS vous répond...",
                                                "engine": "Google API",
                                                "model": live_display_label,
                                                "api_type": "paid" if is_paid_live else "free",
                                                "api_label": "Clé Payante" if is_paid_live else "Clé Gratuite",
                                                "speaking_only": True
                                            }))
                                        # Envoi du chunk PCM linéaire brut en ArrayBuffer au navigateur
                                        await websocket.send_bytes(part.inline_data.data)

                            # Transcription fidèle de ce que JARVIS dit à l'oral
                            if getattr(sc, "output_transcription", None) and sc.output_transcription.text:
                                jarvis_txt = sc.output_transcription.text
                                turn_jarvis_sentence = f"{turn_jarvis_sentence} {jarvis_txt}".strip()
                                recent_conversation_turns.append({"role": "jarvis", "text": jarvis_txt})
                                if len(recent_conversation_turns) > 20:
                                    recent_conversation_turns = recent_conversation_turns[-20:]
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "jarvis",
                                    "text": jarvis_txt
                                }))

                            # Fin de transmission audio par Gemini
                            if getattr(sc, "turn_complete", False):
                                notify_turn_complete()
                                user_speech_buffer = ""
                                is_speaking_state = False
                                speaking_state["active"] = False
                                active_task_controller["speaking_active"] = False
                                active_task_controller["last_turn_complete_time"] = time.time()
                                await websocket.send_text(json.dumps({"type": "turn_complete"}))

                                # Enregistrement de l'audit de ce tour de dialogue
                                try:
                                    from services.turn_audit import record_turn_audit, get_active_plan_status_str
                                    turn_dur = max(0.0, time.time() - turn_start_time)
                                    record_turn_audit(
                                        transcript=turn_user_transcript,
                                        voice_mode="thinking" if ("extended-thinking" in active_live_model or "thinking" in active_live_model) else "standard",
                                        tools=list(turn_tools),
                                        plan=get_active_plan_status_str(),
                                        final_sentence=turn_jarvis_sentence,
                                        cuts=turn_cuts,
                                        duration=turn_dur,
                                        paid_used=is_paid_live,
                                        paid_reason=str(active_task_controller.get("paid_reason", "")),
                                        paid_consent=str(active_task_controller.get("paid_consent_given", False)),
                                        session_id="voice",
                                    )
                                except Exception as _ae:
                                    print(f"[TurnAudit] Erreur enregistrement tour : {_ae}")

                                # Réinitialisation pour le tour suivant
                                turn_start_time = time.time()
                                turn_user_transcript = ""
                                turn_tools = []
                                turn_jarvis_sentence = ""
                                turn_cuts = 0

                                # Application au tour suivant si une bascule était différée et que la parole est idle
                                if is_speech_idle():
                                    pending_switch = active_task_controller.pop("pending_model_switch", None)
                                    if pending_switch:
                                        print(f"[Voice Channel] Application au tour suivant de la bascule différée : {pending_switch}")
                                        raise ModelSwitchRequested(pending_switch)

                        # ── Appels d'outils (Tool Calls) ─────────────────────────────
                        if chunk.tool_call:
                            user_speech_buffer = ""
                            supervision_service.update_voice_state("active", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
                            await broadcast_supervision()

                            for call in chunk.tool_call.function_calls:
                                name = call.name
                                args = dict(call.args) if call.args else {}

                                notify_tool_started(name)
                                # Notification visuelle outil en cours
                                t_meta = get_tool_metadata(name, args)
                                await websocket.send_text(json.dumps({
                                    "type": "tool_start",
                                    "tool_name": name,
                                    "state": t_meta.get("state", "thinking"),
                                    "msg": t_meta.get("msg", f"Exécution : {name}"),
                                    "task": t_meta.get("task", name),
                                    "engine": t_meta.get("engine", "JARVIS"),
                                    "model": t_meta.get("model", "Agent Core"),
                                    "api_type": t_meta.get("api_type", "free"),
                                    "api_label": t_meta.get("api_label", "Service Local"),
                                }))
                                await websocket.send_text(json.dumps({
                                    "type": "status",
                                    "state": t_meta.get("state", "thinking"),
                                    "msg": t_meta.get("msg", f"Exécution : {name}"),
                                    "task": t_meta.get("task", name),
                                    "detail": t_meta.get("task", name),
                                    "engine": t_meta.get("engine", "JARVIS"),
                                    "model": t_meta.get("model", "Agent Core"),
                                    "api_type": t_meta.get("api_type", "free"),
                                    "api_label": t_meta.get("api_label", "Service Local"),
                                }))

                                active_task_controller["awaiting_tool_response"] = True
                                # Dispatch vers le module métier
                                tool_resp = await dispatch_tool(
                                    name=name,
                                    args=args,
                                    websocket=websocket,
                                    session=session,
                                    is_paid_live=is_paid_live,
                                    live_display_label=live_display_label,
                                )

                                # Audit du statut et de la vérification de l'outil pour ce tour
                                turn_tools.append({
                                    "name": name,
                                    "status": tool_resp.get("status", "unknown") if isinstance(tool_resp, dict) else "done",
                                    "verified": bool(tool_resp.get("verified", False)) if isinstance(tool_resp, dict) else False,
                                })

                                # Règle d'or de canal unique : si l'action s'est terminée de manière synchrone, l'enregistrer
                                if tool_resp.get("status") not in ("started", "launched_in_background", "lance_en_arriere_plan"):
                                    from core.shared_state import mark_action_sync_completed
                                    mark_action_sync_completed(name)

                                # Réponse transmise au modèle Gemini Live
                                await session.send_tool_response(
                                    function_responses=[
                                        types.FunctionResponse(
                                            name=name,
                                            id=call.id,
                                            response=tool_resp,
                                        )
                                    ]
                                )
                                active_task_controller["awaiting_tool_response"] = False
                                active_task_controller["tool_response_cooldown"] = time.time() + 2.5
                                notify_tool_completed(name)

                                # Suivi des échecs consécutifs d'outils pour la politique Live (Règle 3)
                                if isinstance(tool_resp, dict) and ("error" in tool_resp or "exception" in tool_resp or tool_resp.get("status") == "error"):
                                    active_task_controller["recent_tool_failures"] = active_task_controller.get("recent_tool_failures", 0) + 1
                                else:
                                    active_task_controller["recent_tool_failures"] = 0

                                # Signal de fin d'outil au frontend
                                await websocket.send_text(json.dumps({
                                    "type": "tool_end",
                                    "tool_name": name,
                                    "state": t_meta.get("state", "listening")
                                }))

                                # ── Boucle de completion plan multi-etapes ──────────
                                # Met a jour le step correspondant si un plan est actif
                                try:
                                    _plan = _task_planner_mod.get_active_plan()
                                    if _plan and name not in ("get_plan_status", "mark_plan_step"):
                                        # Associer ce tool_call au step running le plus recent
                                        _running = _plan.running_steps()
                                        _step_target = _running[0] if _running else None
                                        if _step_target is None:
                                            _pend = _plan.pending_steps()
                                            _step_target = _pend[0] if _pend else None
                                        if _step_target:
                                            _task_planner_mod.update_step_with_tool_result(
                                                _step_target.id, tool_resp
                                            )
                                        # Broadcast HUD
                                        _hud = _task_planner_mod.get_plan_hud_payload(_plan)
                                        await broadcast_supervision()
                                        await websocket.send_text(json.dumps({
                                            "type": "plan_update",
                                            "plan": _hud
                                        }))
                                        # Injection continuation ou rapport final
                                        await asyncio.sleep(0.4)  # buffer drainage
                                        _done_n = _plan.done_count() + _plan.failed_count()
                                        if _plan.is_complete():
                                            _final_msg = _task_planner_mod.build_final_report_prompt(_plan)
                                            if _final_msg and session:
                                                try:
                                                    await safe_send_live_client_content(
                                                        session,
                                                        text_content=_final_msg,
                                                        priority=2,
                                                        role="user",
                                                        turn_complete=True
                                                    )
                                                except Exception as _pe:
                                                    print(f"[Plan] Injection rapport final: {_pe}")
                                            _task_planner_mod.clear_active_plan()
                                        elif _plan.pending_steps():
                                            _cont_msg = _task_planner_mod.build_continuation_prompt(_plan, _done_n)
                                            if _cont_msg and session and _plan._injection_count < 10:
                                                _plan._injection_count += 1
                                                try:
                                                    await safe_send_live_client_content(
                                                        session,
                                                        text_content=_cont_msg,
                                                        priority=2,
                                                        role="user",
                                                        turn_complete=True
                                                    )
                                                except Exception as _ce:
                                                    print(f"[Plan] Injection continuation: {_ce}")
                                except Exception as _plan_exc:
                                    print(f"[Plan] Erreur boucle completion: {_plan_exc}")

            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError, ModelSwitchRequested, QuotaExhaustedError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                err_str = str(e).lower()
                is_normal_close = any(k in err_str for k in [
                    "cannot call", "close message has been sent", "connection closed", "disconnect",
                    "closed", "close", "1000", "1001", "(1000, none)", "1000 none", "connectionclosedok"
                ]) or getattr(e, "code", None) in (1000, 1001)
                if is_normal_close:
                    raise WebSocketDisconnect(code=1000)
                else:
                    print(f"[gemini_to_client] Erreur: {e}")
                    console_monitor.record_error(source="gemini_to_client", message=str(e), level="WARNING")
                    raise
            finally:
                pass

        # ─── Boucle de reconnexion principale ────────────────────────────────────
        while True:
            live_display_label = "Gemini 3.8 Live (Thinking)" if "extended-thinking" in active_live_model else "Gemini 3.8 Live"

            # Sélection de la clé (gratuite par défaut pour gemini-3.8-live et gemini-3.8-live-extended-thinking)
            from services.key_gate import has_paid_consent, is_qualified_free_key_failure, grant_paid_consent
            has_voice_consent = has_paid_consent(session_id="voice")
            if has_voice_consent and client_paid:
                current_live_client = client_paid
                is_paid_live = True
                tier_badge = "Clé Payante"
            else:
                current_live_client = client_free or client_paid
                is_paid_live = False
                tier_badge = "Clé Gratuite"

            try:
                print(f"[Voice Channel] Connexion Live ({active_live_model}) avec {tier_badge}...")
                session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
            except Exception as initial_conn_err:
                is_qual, fail_detail = is_qualified_free_key_failure(initial_conn_err)
                print(f"[Voice Channel] Échec de connexion Live ({active_live_model}, {tier_badge}): {initial_conn_err}")

                # 3. Repli cascade : Si échec de la clé FREE sur modèle thinking -> passer d'abord en Live standard FREE
                if "extended-thinking" in active_live_model and not is_paid_live:
                    print(f"[Voice Channel] Échec FREE sur thinking. Repli cascade sur Live standard FREE...")
                    active_live_model = LIVE_MODEL_STANDARD
                    config.GEMINI_LIVE_MODEL = LIVE_MODEL_STANDARD
                    current_live_client = client_free or client_paid
                    is_paid_live = False
                    tier_badge = "Clé Gratuite (Repli Standard)"
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Échec du modèle réflexion en clé gratuite. Repli sur le modèle Live standard en clé gratuite.",
                        "voice": False
                    }))
                    try:
                        session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                    except Exception as std_free_err:
                        # Le standard FREE a échoué aussi -> exigence de consentement payant
                        print(f"[Voice Channel] Échec également du standard FREE ({std_free_err}). Demande de consentement payant.")
                        active_task_controller["paid_consent_modal_open"] = True
                        active_task_controller["paid_consent_given"] = False
                        await websocket.send_text(json.dumps({
                            "type": "show_paid_consent",
                            "reason": "free_key_failure",
                            "detail": "Les clés gratuites (thinking et standard) ont échoué. Consentement requis pour la clé payante."
                        }))
                        await websocket.send_text(json.dumps({
                            "type": "jarvis_announcement",
                            "text": "La clé gratuite ne répond plus sur aucun modèle vocal. Pierre, m'autorises-tu à passer sur la clé payante ?",
                            "voice": True
                        }))
                        raise PaidKeyConsentRequired(
                            reason="free_key_failure",
                            detail="Échec de la clé gratuite sur thinking et standard",
                            session_id="voice"
                        )
                elif not is_paid_live:
                    # Échec direct sur standard FREE
                    has_voice_consent = has_paid_consent(session_id="voice") or active_task_controller.get("paid_consent_given")
                    if has_voice_consent and client_paid and config.is_paid_key_authorized():
                        grant_paid_consent(session_id="voice", reason="free_key_failure", scope="this_task")
                        current_live_client = client_paid
                        is_paid_live = True
                        tier_badge = "Clé Payante (Secours)"
                        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Échec de la clé gratuite. Bascule de secours sur la clé payante autorisée.", "voice": False}))
                        session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                    else:
                        active_task_controller["paid_consent_modal_open"] = True
                        active_task_controller["paid_consent_given"] = False
                        await websocket.send_text(json.dumps({
                            "type": "show_paid_consent",
                            "reason": "free_key_failure",
                            "detail": f"Échec de la clé gratuite standard : {fail_detail or initial_conn_err}"
                        }))
                        await websocket.send_text(json.dumps({
                            "type": "jarvis_announcement",
                            "text": "La clé gratuite ne répond plus. Pierre, m'autorises-tu à passer sur la clé payante ?",
                            "voice": True
                        }))
                        raise PaidKeyConsentRequired(
                            reason="free_key_failure",
                            detail=fail_detail or str(initial_conn_err),
                            session_id="voice"
                        )
                elif "extended-thinking" in active_live_model and is_paid_live:
                    print(f"[Voice Channel] Échec PAID sur thinking ({initial_conn_err}). Repli cascade sur Live standard PAID...")
                    active_live_model = LIVE_MODEL_STANDARD
                    config.GEMINI_LIVE_MODEL = LIVE_MODEL_STANDARD
                    session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                else:
                    raise initial_conn_err

            active_task_controller["live_session"] = session
            active_task_controller["live_session_ctx"] = session_ctx
            supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
            await broadcast_supervision()
            await websocket.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Canal vocal {live_display_label} opérationnel ({tier_badge}).",
                "voice": False
            }))

            setup_done_event.clear()

            if not greeting_sent:
                greeting_sent = True
                greeting_instruction = (
                    "[INSTRUCTION SYSTÈME INVISIBLE] La session vocale vient de démarrer. "
                    "Salue Pierre naturellement et d'égal à égal avec ta voix Aoede en une courte phrase sympa, directe et décontractée pour lui dire que tu es prête."
                )
                try:
                    await safe_send_live_client_content(
                        session,
                        text_content=greeting_instruction,
                        priority=2,
                        turn_complete=True
                    )
                    print("[Voice Channel] Amorce vocale (greeting) envoyée avec succès.")
                except Exception as greet_err:
                    print(f"[Voice Channel] Avertissement amorce vocale: {greet_err}")
            elif is_model_switch_reconnect:
                is_model_switch_reconnect = False
                # 2. Réinjection de contexte (build_live_context_prompt + 10 derniers tours + plan + sous-agents actifs)
                meta = active_task_controller.pop("pending_model_switch_meta", {})
                announcement = meta.get("announcement_phrase", "")
                reinjected_context = await _build_switch_context_prompt(
                    recent_turns=recent_conversation_turns,
                    announcement_phrase=announcement,
                )
                try:
                    await safe_send_live_client_content(
                        session,
                        text_content=reinjected_context,
                        priority=1,
                        role="user",
                        turn_complete=bool(announcement),
                    )
                    print(f"[Voice Channel] Contexte réinjecté avec succès suite à bascule ({active_live_model}, annonce={bool(announcement)})")
                except Exception as re_err:
                    print(f"[Voice Channel] Erreur réinjection contexte après bascule: {re_err}")

            client_task = asyncio.create_task(client_to_gemini(), name="client_to_gemini")
            gemini_task = asyncio.create_task(gemini_to_client(), name="gemini_to_client")

            async def _auto_cancel_sister(t1, t2):
                try:
                    await t1
                except Exception:
                    pass
                finally:
                    if not t2.done():
                        t2.cancel()

            asyncio.create_task(_auto_cancel_sister(client_task, gemini_task))
            asyncio.create_task(_auto_cancel_sister(gemini_task, client_task))

            try:
                await asyncio.gather(client_task, gemini_task)
                break
            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
                break
            except ModelSwitchRequested as switch_req:
                new_model = switch_req.model
                print(f"[Voice Channel] Bascule dynamique de modèle vocal demandée : {new_model}")
                active_task_controller.pop("pending_model_switch", None)
                if not is_speech_idle():
                    print(f"[Voice Channel] Attente de la fin de l'élocution avant bascule modèle...")
                    await wait_until_speech_finished(timeout=8.0, buffer_drainage_delay=0.35)
                active_live_model = new_model
                config.GEMINI_LIVE_MODEL = new_model

                if session_ctx:
                    try:
                        await session_ctx.__aexit__(None, None, None)
                    except Exception:
                        pass
                session = None
                session_ctx = None

                # Les deux modèles (standard et thinking) tournent sur clé FREE par défaut
                current_live_client = client_free if (client_free and not supervision_service._free_quota_exhausted) else (client_paid or client_free)
                is_paid_live = (current_live_client is client_paid)
                tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"

                is_model_switch_reconnect = True
                await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Bascule vers le modèle {new_model} ({tier_badge})...", "voice": False}))
                continue
            except QuotaExhaustedError as q_err:
                print(f"[Voice Channel] QuotaExhaustedError: {q_err}")
                # 3. Repli cascade si thinking FREE -> passer d'abord en Live standard FREE
                if "extended-thinking" in active_live_model and not is_paid_live:
                    print(f"[Voice Channel] Quota thinking FREE dépassé. Repli automatique sur Live standard FREE...")
                    active_live_model = LIVE_MODEL_STANDARD
                    config.GEMINI_LIVE_MODEL = LIVE_MODEL_STANDARD
                    current_live_client = client_free
                    is_paid_live = False
                    tier_badge = "Clé Gratuite (Repli Standard)"
                    is_model_switch_reconnect = True
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Limite de la clé gratuite atteinte sur le modèle réflexion. Repli automatique sur Live standard en clé gratuite.",
                        "voice": False
                    }))
                    continue

                # Standard FREE a aussi échoué ou dépassé son quota
                has_voice_consent = has_paid_consent(session_id="voice") or active_task_controller.get("paid_consent_given")
                if has_voice_consent and client_paid and config.is_paid_key_authorized():
                    supervision_service.set_free_quota_exhausted(True)
                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Secours)"
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Bascule autorisée sur la clé payante suite à épuisement de la clé gratuite.",
                        "voice": False
                    }))
                    continue
                else:
                    active_task_controller["paid_consent_modal_open"] = True
                    active_task_controller["paid_consent_given"] = False
                    await websocket.send_text(json.dumps({
                        "type": "show_paid_consent",
                        "reason": "free_key_failure",
                        "detail": "Quota de la clé gratuite dépassé sur Live standard."
                    }))
                    await websocket.send_text(json.dumps({
                        "type": "jarvis_announcement",
                        "text": "Le quota de la clé gratuite est épuisé. Pierre, m'autorises-tu à passer sur la clé payante pour continuer ?",
                        "voice": True
                    }))
                    raise PaidKeyConsentRequired(
                        reason="free_key_failure",
                        detail="Quota clé gratuite épuisé sur thinking et standard",
                        session_id="voice"
                    )
            except Exception as loop_e:
                err_s = str(loop_e).lower()
                is_loop_normal = (
                    getattr(loop_e, "code", None) in (1000, 1001)
                    or any(k in err_s for k in ["1000", "1001", "connection closed", "connectionclosed", "normal closure", "(1000, none)", "1000 none", "disconnect"])
                )
                if is_loop_normal:
                    break
                raise

    except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
        pass
    except Exception as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        is_normal = (
            isinstance(e, (WebSocketDisconnect, WebSocketDisconnected))
            or getattr(e, "code", None) in (1000, 1001)
            or any(k in err_msg for k in ["1000", "1001"])
            or any(k in err_lower for k in ["normal closure", "connectionclosed", "disconnect", "closed", "(1000, none)", "1000 none"])
        )
        if is_normal:
            print(f"[Voice Channel] Fermeture normale de session vocale ({active_live_model})")
        else:
            import traceback
            tb = traceback.format_exc()
            print(f"[Voice Channel] ERREUR CRITIQUE Live ({active_live_model}): {err_msg}\n{tb}")
            console_monitor.record_error(source="Voice Channel", message=f"Erreur Live: {err_msg}", level="ERROR")
            try:
                await websocket.send_text(json.dumps({
                    "type": "transcript",
                    "role": "jarvis",
                    "text": f"Erreur de connexion Live : {err_msg}"
                }))
            except Exception:
                pass
            try:
                await websocket.close(code=1011, reason=f"Live error: {err_msg[:100]}")
            except Exception:
                pass
    finally:
        # Fermeture propre de la session Live pour éviter les sessions zombies (409)
        if session_ctx:
            try:
                await session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
        elif session:
            try:
                await session.close()
            except Exception:
                pass

        print("[Voice Channel] FINALLY: Nettoyage session et références terminé.")
        # Nettoyage du plan multi-etapes actif pour eviter les plans zombies
        try:
            _task_planner_mod.clear_active_plan()
        except Exception:
            pass
        ws_sessions = active_task_controller.get("ws_sessions", {})
        ws_sessions.pop(conn_id, None)
        if active_task_controller.get("websocket") == websocket:
            remaining = list(ws_sessions.values())
            active_task_controller["websocket"] = remaining[-1] if remaining else None
        if active_task_controller.get("live_session") == session:
            active_task_controller["live_session"] = None
        if active_task_controller.get("live_session_ctx") == session_ctx:
            active_task_controller["live_session_ctx"] = None
        if not ws_sessions:
            supervision_service.update_voice_state("offline")
        await broadcast_supervision()
        try:
            await websocket.close()
        except Exception:
            pass

        # IMPORTANT : On ne détruit PAS la tâche de code en arrière-plan si le canal vocal se déconnecte !
        # Elle continue de coder dans le workspace de façon autonome et mettra à jour l'interface.
        bg = active_task_controller.get("bg_task")
        if bg and bg.done():
            active_task_controller["info"]["running"] = False
            active_task_controller["bg_task"] = None
