"""routers/voice.py
WebSocket full-duplex Gemini Live — Canal vocal principal de J.A.R.V.I.S.
Gère la boucle PCM, le barge-in, la gestion du quota et le dispatch des outils.
"""

from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from google.genai import types

import config
import auth
from services.supervision_service import supervision_service
from services.console_monitor import console_monitor
from core.shared_state import (
    active_task_controller,
    client_free, client_paid,
    broadcast_supervision, broadcast_jarvis_state,
    QuotaExhaustedError, ModelSwitchRequested,
    is_quota_or_limit_error, merge_user_speech,
    get_tool_metadata,
)
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool

router = APIRouter()


async def _build_system_instruction() -> str:
    """Construit dynamiquement le system_instruction de la session Live en injectant le contexte mémoire."""
    from services.unified_memory import unified_memory_manager

    # Injection dynamique du contexte de mémoire unifiée
    memory_context = await unified_memory_manager.build_live_context_prompt()

    paid_key_status = "CLÉ PAYANTE ACTIVE" if config.HAS_PAID_API_KEY else "CLÉ PAYANTE NON CONFIGURÉE (mode économie forcée)"

    # Le texte complet de l'instruction système est dans config.JARVIS_SYSTEM_INSTRUCTION_TEMPLATE
    # avec des placeholders {memory_context}, {paid_key_status}, {live_model}
    # Si la config n'a pas le template, on utilise le texte brut comme fallback.
    template = getattr(config, "JARVIS_SYSTEM_INSTRUCTION_TEMPLATE", None)
    if template:
        return template.format(
            memory_context=memory_context,
            paid_key_status=paid_key_status,
            live_model=config.GEMINI_LIVE_MODEL
        )
    # Fallback : JARVIS_SYSTEM_INSTRUCTION statique + injection mémoire en tête
    static = getattr(config, "JARVIS_SYSTEM_INSTRUCTION", "")
    if memory_context:
        return f"{memory_context}\n\n{static}"
    return static


async def _establish_live_session(model: str, client):
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

    session_ctx = client.aio.live.connect(model=model, config=live_config)
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

    # S'assurer qu'une seule instance WebSocket et session Live existe à la fois
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

    # Sélection du modèle et de la clé
    active_live_model = config.GEMINI_LIVE_MODEL

    # Clé gratuite = prioritaire pour gemini-3.8-live standard
    # Clé payante = obligatoire pour extended-thinking et repli quota
    if "extended-thinking" in active_live_model:
        current_live_client = client_paid or client_free
        is_paid_live = (current_live_client is client_paid)
    else:
        current_live_client = client_free or client_paid
        is_paid_live = (current_live_client is client_paid)

    tier_badge = "Clé Payante" if is_paid_live else "Clé Gratuite"

    try:
        # ─── client_to_gemini : Réception des frames PCM depuis le frontend ──────
        async def client_to_gemini():
            """Reçoit l'audio PCM 16kHz 16-bit mono depuis le frontend et le stream vers Gemini Live."""
            current_speech_text = ""
            try:
                while True:
                    data = await websocket.receive()
                    if "bytes" in data:
                        # Frame audio brute PCM → Gemini Live
                        audio_chunk = data["bytes"]
                        await session.send_realtime_input(
                            audio=types.Blob(data=audio_chunk, mime_type="audio/pcm;rate=16000")
                        )
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        msg_type = msg.get("type", "")

                        if msg_type == "text":
                            text_input = msg.get("text", "").strip()
                            if text_input:
                                await session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part.from_text(text=text_input)]),
                                    turn_complete=True
                                )

                        elif msg_type == "image":
                            image_b64 = msg.get("data", "")
                            mime = msg.get("mime", "image/jpeg")
                            caption = msg.get("caption", "")
                            if image_b64:
                                image_bytes = base64.b64decode(image_b64)
                                parts = [types.Part.from_bytes(data=image_bytes, mime_type=mime)]
                                if caption:
                                    parts.append(types.Part.from_text(text=caption))
                                await session.send_client_content(
                                    turns=types.Content(role="user", parts=parts),
                                    turn_complete=True
                                )

                        elif msg_type == "inject_instruction":
                            instruction_text = msg.get("text", "").strip()
                            if instruction_text:
                                try:
                                    await session.send_client_content(
                                        turns=types.Content(role="user", parts=[types.Part.from_text(text=instruction_text)]),
                                        turn_complete=True
                                    )
                                except Exception as inj_err:
                                    print(f"[Voice WS] inject_instruction error: {inj_err}")

                        elif msg_type == "switch_model":
                            new_model = msg.get("model", "")
                            if new_model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
                                raise ModelSwitchRequested(new_model)

                        elif msg_type == "speech_delta":
                            current_speech_text = merge_user_speech(current_speech_text, msg.get("text", ""))
                            await websocket.send_text(json.dumps({
                                "type": "transcript",
                                "role": "user",
                                "text": current_speech_text
                            }))

                        elif msg_type == "speech_end":
                            current_speech_text = ""

                        elif msg_type == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))

            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError, ModelSwitchRequested, QuotaExhaustedError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                err_str = str(e).lower()
                is_normal = any(k in err_str for k in ["cannot call", "close message", "connection closed", "disconnect", "closed", "1000", "1001", "(1000, none)", "1000 none", "connectionclosedok"])
                if is_normal or getattr(e, "code", None) in (1000, 1001):
                    raise WebSocketDisconnect(code=1000)
                print(f"[client_to_gemini] Erreur: {e}")
                raise
            finally:
                pass

        # ─── gemini_to_client : Réception des réponses Gemini → Frontend ─────────
        async def gemini_to_client():
            """Reçoit les réponses audio et texte de Gemini Live et les relaie au client."""
            live_display_label = "Gemini 3.8 Live (Thinking)" if "extended-thinking" in active_live_model else "Gemini 3.8 Live"

            try:
                async for response in session.receive():
                    # ── Audio chunk (réponse vocale d'Aoede) ──────────────────────
                    if response.data:
                        audio_b64 = base64.b64encode(response.data).decode("utf-8")
                        await websocket.send_text(json.dumps({
                            "type": "audio",
                            "data": audio_b64,
                            "encoding": "pcm",
                            "sampleRate": 24000
                        }))

                    # ── Transcript partiel de la voix d'Aoede (texte en cours) ────
                    if response.text:
                        await websocket.send_text(json.dumps({
                            "type": "transcript",
                            "role": "jarvis",
                            "text": response.text
                        }))

                    # ── Réponse serveur (fin de tour, metadata, etc.) ─────────────
                    if response.server_content:
                        sc = response.server_content

                        if sc.turn_complete:
                            await websocket.send_text(json.dumps({"type": "turn_complete"}))
                            supervision_service.update_voice_state("idle", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
                            await broadcast_supervision()

                        if sc.interrupted:
                            await websocket.send_text(json.dumps({"type": "barge_in"}))
                            supervision_service.update_voice_state("listening", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
                            await broadcast_supervision()

                        # Transcriptions partielles / complètes côté utilisateur
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if hasattr(part, "text") and part.text:
                                    await websocket.send_text(json.dumps({
                                        "type": "transcript",
                                        "role": "jarvis",
                                        "text": part.text
                                    }))

                        if sc.input_transcription and sc.input_transcription.text:
                            await websocket.send_text(json.dumps({
                                "type": "transcript",
                                "role": "user",
                                "text": sc.input_transcription.text
                            }))

                        if sc.output_transcription and sc.output_transcription.text:
                            await websocket.send_text(json.dumps({
                                "type": "transcript",
                                "role": "jarvis",
                                "text": sc.output_transcription.text
                            }))

                    # ── Appels d'outils (Tool Calls) ─────────────────────────────
                    if response.tool_call:
                        supervision_service.update_voice_state("active", model=active_live_model, is_paid=is_paid_live, api_label=tier_badge)
                        await broadcast_supervision()

                        for call in response.tool_call.function_calls:
                            name = call.name
                            args = dict(call.args) if call.args else {}

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

                            # Dispatch vers le module métier
                            tool_resp = await dispatch_tool(
                                name=name,
                                args=args,
                                websocket=websocket,
                                session=session,
                                is_paid_live=is_paid_live,
                                live_display_label=live_display_label,
                            )

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

                            # Signal de fin d'outil au frontend
                            await websocket.send_text(json.dumps({
                                "type": "tool_end",
                                "tool_name": name,
                                "state": t_meta.get("state", "listening")
                            }))

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

            try:
                print(f"[Voice Channel] Connexion Live ({active_live_model}) avec {tier_badge}...")
                session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
            except Exception as initial_conn_err:
                if not is_paid_live and client_paid and config.is_paid_key_authorized():
                    print(f"[Voice Channel] Clé gratuite en échec ({initial_conn_err}). Bascule immédiate de repli sur la clé payante...")
                    supervision_service.set_free_quota_exhausted(True)
                    console_monitor.record_error(source="Voice Channel", message=f"Bascule de repli sur clé payante : {initial_conn_err}", level="WARNING")
                    current_live_client = client_paid
                    is_paid_live = True
                    tier_badge = "Clé Payante (Repli Quota)"
                    await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Limite de la clé gratuite atteinte. Bascule automatique sur la clé payante.", "voice": False}))
                    session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
                else:
                    if not is_paid_live and client_paid and not config.is_paid_key_authorized():
                        await websocket.send_text(json.dumps({"type": "jarvis_announcement", "text": "Limite de la clé gratuite atteinte. La clé payante est verrouillée dans l'application. Cochez l'encoche pour l'autoriser.", "voice": False}))
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
            setup_done_event.set()

            if not greeting_sent:
                greeting_sent = True
                greeting_instruction = (
                    "[INSTRUCTION SYSTÈME INVISIBLE] La session vocale vient de démarrer. "
                    "Salue Pierre naturellement et d'égal à égal avec ta voix Aoede en une courte phrase sympa, directe et décontractée pour lui dire que tu es prête."
                )
                try:
                    await session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part.from_text(text=greeting_instruction)]),
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
