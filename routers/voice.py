"""routers/voice.py
WebSocket full-duplex Gemini Live — Canal vocal principal de J.A.R.V.I.S.
Gère la boucle PCM, le barge-in, la gestion du quota et le dispatch des outils.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time

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
    notify_interrupted, wait_until_speech_finished, safe_send_live_client_content,
)
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from services import task_planner as _task_planner_mod

router = APIRouter()


async def _build_system_instruction() -> str:
    """Construit dynamiquement le system_instruction de la session Live en injectant le contexte mémoire et la règle d'arbitrage de présence PC."""
    from services.unified_memory import unified_memory_manager
    from services.local_agent_service import is_pc_connected

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

    template = getattr(config, "JARVIS_SYSTEM_INSTRUCTION_TEMPLATE", None)
    if template:
        try:
            base_prompt = template.format(
                memory_context=memory_context,
                paid_key_status=paid_key_status,
                live_model=config.GEMINI_LIVE_MODEL
            )
        except Exception:
            base_prompt = str(template)
        return f"{base_prompt}\n{nav_arbitration_rule}\n{anti_tics_rule}"

    static = getattr(config, "JARVIS_SYSTEM_INSTRUCTION", "")
    full_prompt = f"{memory_context}\n\n{static}" if memory_context else static
    return f"{full_prompt}\n{nav_arbitration_rule}\n{anti_tics_rule}"



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
    token = websocket.query_params.get("token") or websocket.cookies.get("jarvis_device_token")
    if not auth.is_device_authorized(token):
        await websocket.close(code=1008, reason="Terminal non autorisé")
        return

    # S'assurer qu'une seule instance WebSocket et session Live existe à la fois côté serveur
    prev_ws = active_task_controller.get("websocket")
    prev_session_ctx = active_task_controller.get("live_session_ctx")
    prev_session = active_task_controller.get("live_session")

    if prev_ws and prev_ws != websocket:
        try:
            print("[Voice Channel] Fermeture de la précédente connexion WebSocket orpheline...")
            await prev_ws.close(code=1000, reason="Nouvelle connexion active")
        except Exception:
            pass
    if prev_session_ctx:
        try:
            print("[Voice Channel] Fermeture de la session Live Google précédente...")
            await prev_session_ctx.__aexit__(None, None, None)
        except Exception:
            pass
    elif prev_session:
        try:
            await prev_session.close()
        except Exception:
            pass

    await websocket.accept()
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
    setup_done_event = asyncio.Event()
    speaking_state = {"active": False}

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
                                notify_playback_finished()
                                if is_speech_idle():
                                    supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live)
                                    await broadcast_supervision()
                                pending_switch = active_task_controller.pop("pending_model_switch", None)
                                if pending_switch:
                                    raise ModelSwitchRequested(pending_switch)

                            elif p_type == "playback_finished":
                                notify_playback_finished()
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
                                    if "extended-thinking" in new_model and not config.is_paid_key_authorized():
                                        await websocket.send_text(json.dumps({
                                            "type": "jarvis_announcement",
                                            "text": "Le modèle Extended Thinking requiert la clé payante. Veuillez cocher l'encoche d'autorisation dans l'application.",
                                            "voice": False
                                        }))
                                    elif new_model != active_live_model:
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
                                speaking_state["active"] = False
                                notify_interrupted("user_barge_in")
                                metrics_service.record_speech_cut("user_barge_in", details="WebSocket user_interrupt event")
                                inter_txt = payload.get("text", "").strip()
                                print(f"[Voice Channel] SPEECH_CUT reason=user_barge_in : '{inter_txt}'")
                                is_any_task_running = (
                                    active_task_controller["info"]["running"]
                                    or bool(active_task_controller.get("bg_task"))
                                    or bool(active_task_controller.get("browser_bg_task"))
                                )
                                if is_any_task_running and inter_txt and is_stop_directive(inter_txt):
                                    print(f"[Voice Channel] Interception vocale immédiate d'arrêt via barge-in : '{inter_txt}'")
                                    await stop_active_task(source="barge_in_voice", reason=inter_txt)

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
                                    await wait_until_speech_finished(timeout=5.0, buffer_drainage_delay=0.35)
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
            user_speech_buffer = ""
            is_speaking_state = False

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
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "user",
                                    "text": user_speech_buffer,
                                    "mode": "set"
                                }))

                                # 1. Détection prioritaire immédiate d'ordre d'arrêt d'action en cours
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

                                # 2. Détection d'accord oral si demande de clé payante en attente
                                if active_task_controller.get("paid_consent_modal_open"):
                                    affirmative_words = ["oui", "d'accord", "vas-y", "je valide", "autorise", "fais-le", "c'est bon", "accepte", "valide", "je t'autorise"]
                                    t_clean = user_speech_buffer.lower().strip()
                                    if any(w in t_clean for w in affirmative_words):
                                        print(f"[Voice Channel] Accord oral détecté pour clé payante : '{user_speech_buffer}'")
                                        if not config.is_paid_key_authorized():
                                            print(f"[Voice Channel] Clé payante verrouillée dans l'app. Rappel oral pour cocher la case.")
                                            try:
                                                await safe_send_live_client_content(
                                                    session,
                                                    text_content="[RAPPEL ENCOCHE NON COCHÉE] Pierre a donné son accord oral, mais l'encoche d'autorisation de la clé payante est encore décochée dans l'application. Tu es dans l'impossibilité physique de faire des requêtes sur la clé payante tant qu'elle n'est pas cochée. Rappelle immédiatement à Pierre avec ta voix Aoede : 'Merci Pierre, mais pense à cocher l'encoche d'autorisation de la clé payante sur ton écran pour débloquer l'accès technique !'",
                                                    priority=2,
                                                    role="user",
                                                    turn_complete=True
                                                )
                                            except Exception:
                                                pass
                                        else:
                                            active_task_controller["paid_consent_given"] = True
                                            active_task_controller["paid_consent_modal_open"] = False
                                            await websocket.send_text(json.dumps({"type": "hide_paid_consent"}))
                                            if active_task_controller.get("paid_consent_event"):
                                                active_task_controller["paid_consent_event"].set()

                            # Tour de parole du modèle
                            if sc.model_turn:
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
                                await websocket.send_text(json.dumps({
                                    "type": "transcript",
                                    "role": "jarvis",
                                    "text": sc.output_transcription.text
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
                if not is_paid_live and client_paid and (config.is_paid_key_authorized() or has_voice_consent):
                    print(f"[Voice Channel] Clé gratuite en échec ({initial_conn_err}). Bascule autorisée sur la clé payante...")
                    supervision_service.set_free_quota_exhausted(True)
                    console_monitor.record_error(source="Voice Channel", message=f"Bascule de repli sur clé payante : {initial_conn_err}", level="WARNING")
                    grant_paid_consent(session_id="voice", reason="free_key_failure", scope="this_task")
                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Secours)"
                    await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Échec de la clé gratuite. Bascule de secours sur la clé payante.", "voice": False}))
                    session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                else:
                    if not is_paid_live and client_paid:
                        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"La clé gratuite a échoué ({fail_detail or initial_conn_err}). Autorisation de la clé payante requise.", "voice": False}))
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
            except Exception as loop_e:
                err_s = str(loop_e).lower()
                is_loop_normal = (
                    getattr(loop_e, "code", None) in (1000, 1001)
                    or any(k in err_s for k in ["1000", "1001", "connection closed", "connectionclosed", "normal closure", "(1000, none)", "1000 none", "disconnect"])
                )
                if is_loop_normal:
                    break
                raise
            except ModelSwitchRequested as switch_req:
                new_model = switch_req.model
                print(f"[Voice Channel] Bascule dynamique de modèle vocal demandée : {new_model}")
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

                if new_model == "gemini-3.8-live":
                    current_live_client = client_free if (client_free and not supervision_service._free_quota_exhausted) else (client_paid or client_free)
                    is_paid_live = (current_live_client is client_paid)
                else:
                    current_live_client = client_paid or client_free
                    is_paid_live = (current_live_client is client_paid)

                tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"
                await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": f"Bascule vers le modèle {new_model} ({tier_badge})...", "voice": False}))
                continue
            except QuotaExhaustedError as q_err:
                if not is_paid_live and client_paid and config.is_paid_key_authorized():
                    print(f"[Voice Channel] Quota dépassé sur la clé gratuite en direct ({q_err}). Bascule automatique sur la clé payante...")
                    supervision_service.set_free_quota_exhausted(True)
                    console_monitor.record_error(source="Voice Channel", message="Quota clé gratuite dépassé en direct. Bascule automatique sur clé payante.", level="WARNING")
                    if session_ctx:
                        try:
                            await session_ctx.__aexit__(None, None, None)
                        except Exception:
                            pass
                    session = None
                    session_ctx = None
                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Repli Quota)"
                    await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Limite de la clé gratuite atteinte pendant l'échange. Bascule automatique sur la clé payante effectuée.", "voice": False}))
                    continue
                else:
                    if not is_paid_live and client_paid and not config.is_paid_key_authorized():
                        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Quota de la clé gratuite dépassé. La clé payante est verrouillée dans l'application. Cochez l'encoche pour l'autoriser.", "voice": False}))
                    raise q_err

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
        if active_task_controller.get("websocket") == websocket:
            active_task_controller["websocket"] = None
        if active_task_controller.get("live_session") == session:
            active_task_controller["live_session"] = None
        if active_task_controller.get("live_session_ctx") == session_ctx:
            active_task_controller["live_session_ctx"] = None
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
