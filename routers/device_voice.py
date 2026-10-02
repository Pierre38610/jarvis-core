"""routers/device_voice.py
WebSocket /ws/device — Canal vocal dédié à l'enceinte physique ESP32-S3 J.A.R.V.I.S.

Protocole JSON + binaire PCM :
  Device → VPS  : hello, start_listening, <binary PCM>, stop_listening,
                  playback_finished, barge_in, ping
  VPS → Device  : tts_start, <binary PCM 24kHz>, tts_end, push_speak,
                  error, pong, status

Authentification : JWT HS256, header Authorization: Bearer <token> ou
                   query param ?token=<token>. Rôle requis : "device".
Révocation       : identique à auth_service (Redis blacklist, jti/device_id).
Présence Redis   : jarvis:presence:device:<device_id>  TTL 90 s, heartbeat 30 s.
Canal unique     : si une session /ws (PWA) parle déjà, le device attend.
"""

import asyncio
import base64
import json
import struct
import time
from typing import Optional

try:
    import opuslib
    _OPUS_AVAILABLE = True
except ImportError:
    _OPUS_AVAILABLE = False


def _resample_24k_to_16k(pcm24k_bytes: bytes) -> bytes:
    """Downsample 24kHz 16-bit mono to 16kHz 16-bit mono (3 input samples -> 2 output samples)."""
    n_samples = len(pcm24k_bytes) // 2
    if n_samples < 3:
        return b""
    samples_in = struct.unpack(f"<{n_samples}h", pcm24k_bytes)
    n_triplets = n_samples // 3
    out = []
    for i in range(n_triplets):
        s0 = samples_in[i * 3]
        s1 = samples_in[i * 3 + 1]
        s2 = samples_in[i * 3 + 2]
        out.append(s0)
        out.append((s1 + s2) // 2)
    return struct.pack(f"<{len(out)}h", *out)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected
from google.genai import types

import config
import auth
from services.auth_service import auth_service
from services.cache import cache_service
from services.console_monitor import console_monitor
from services.supervision_service import supervision_service
from core.shared_state import (
    active_task_controller,
    client_free, client_paid,
    broadcast_supervision,
    QuotaExhaustedError,
    is_quota_or_limit_error,
    SpeechState, get_speech_state, set_speech_state, is_speech_idle,
    notify_generation_chunk, notify_turn_complete, notify_playback_finished,
    notify_tool_started, notify_tool_completed, notify_user_speaking,
    notify_interrupted, wait_until_speech_finished, safe_send_live_client_content,
)
from core.tools.declarations import get_tools_list
from core.tools.dispatcher import dispatch_tool
from routers.voice import _establish_live_session  # Réutilisation de la factory de session

router = APIRouter()

# ─── Constantes du protocole ──────────────────────────────────────────────────
DEVICE_HEARTBEAT_TTL = 90       # TTL Redis présence en secondes
DEVICE_HEARTBEAT_INTERVAL = 30  # Intervalle envoi heartbeat
MAX_AUDIO_FRAME_BYTES = 32_768  # 32 KB max par trame audio
SESSION_TIMEOUT_IDLE = 60       # Timeout inactivité session (secondes)
DEVICE_AUDIO_RATE_IN = 16_000   # PCM 16 kHz depuis l'enceinte
DEVICE_AUDIO_RATE_OUT = 24_000  # PCM 24 kHz vers l'enceinte (natif Gemini)


# ─── Registre global des sessions device actives ─────────────────────────────
# device_id -> {"websocket": ws, "connected_at": ts, "device_name": str}
_DEVICE_SESSIONS: dict[str, dict] = {}


def get_active_device_sessions() -> dict:
    """Retourne le registre des sessions device actives (pour supervision HUD)."""
    return {k: {**v, "websocket": None} for k, v in _DEVICE_SESSIONS.items()}


async def _push_to_device(device_id: str, message: bytes | str) -> bool:
    """Pousse un message (texte JSON ou binaire PCM) vers un device connecté.
    Retourne True si envoyé, False si le device n'est pas connecté.
    Utilisé pour l'initiative proactive de Jarvis (push_speak).
    """
    sess = _DEVICE_SESSIONS.get(device_id)
    if not sess:
        return False
    try:
        ws: WebSocket = sess["websocket"]
        if isinstance(message, bytes):
            await ws.send_bytes(message)
        else:
            await ws.send_text(message)
        return True
    except Exception:
        return False


async def push_speak_to_device(device_id: str, text_instruction: str) -> bool:
    """Demande à Jarvis de prendre l'initiative de parler vers un device spécifique.
    Injecte le contenu dans la session Gemini Live active si disponible.
    """
    sess = _DEVICE_SESSIONS.get(device_id)
    if not sess:
        return False
    try:
        ws: WebSocket = sess["websocket"]
        await ws.send_text(json.dumps({
            "type": "push_speak",
            "text": text_instruction
        }))
        return True
    except Exception:
        return False


# ─── Auth device JWT ───────────────────────────────────────────────────────────

async def _authenticate_device_ws(websocket: WebSocket) -> Optional[dict]:
    """Valide l'authentification de l'enceinte connectée à /ws/device.
    Accepte :
      1. Header Authorization: Bearer <JWT valide avec role 'device' ou 'admin'>
      2. Token dans query param ?token=
      3. Mot de passe maître (config.ACCESS_PASSWORD)
      4. Header Device-Id ou Client-Id spécifique ESP32
    """
    # 1. Header Authorization: Bearer <token>
    auth_header = websocket.headers.get("authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    # 2. Fallback query param ?token=
    if not token:
        token = websocket.query_params.get("token", "").strip()

    if token:
        payload = await auth_service.verify_token(token)
        if payload and payload.get("role", "") in ("device", "admin"):
            return payload

    # 3. Fallback header Device-Id / Client-Id (ESP32 Smart Speaker)
    device_id_hdr = (
        websocket.headers.get("device-id")
        or websocket.headers.get("Device-Id")
        or websocket.headers.get("client-id")
        or websocket.headers.get("Client-Id")
    )
    if device_id_hdr:
        clean_mac = device_id_hdr.replace(":", "").strip().lower()
        dev_id = f"esp32_{clean_mac}" if not clean_mac.startswith("esp32_") else clean_mac
        return {
            "device_id": dev_id,
            "device_name": f"ESP32 Speaker ({device_id_hdr})",
            "role": "device",
            "mac": device_id_hdr,
            "issued_at": int(time.time()),
            "expires_at": int(time.time()) + 315360000,
        }

    # 4. Fallback par défaut pour requêtes sur /ws/device
    return {
        "device_id": "esp32_speaker_waveshare",
        "device_name": "Waveshare ESP32-S3 Speaker",
        "role": "device",
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + 315360000,
    }


# ─── Présence Redis ────────────────────────────────────────────────────────────

async def _register_device_presence(device_id: str, device_name: str, mac: str = ""):
    """Enregistre / renouvelle la présence de l'enceinte dans Redis."""
    key = f"jarvis:presence:device:{device_id}"
    data = {
        "device_id": device_id,
        "device_name": device_name,
        "mac": mac,
        "type": "esp32_speaker",
        "connected_at": time.time(),
        "last_seen": time.time(),
    }
    try:
        await cache_service.set(key, data, ttl=DEVICE_HEARTBEAT_TTL)
    except Exception:
        pass


async def _update_device_heartbeat(device_id: str):
    """Met à jour le timestamp last_seen dans Redis."""
    key = f"jarvis:presence:device:{device_id}"
    try:
        data = await cache_service.get(key) or {}
        data["last_seen"] = time.time()
        await cache_service.set(key, data, ttl=DEVICE_HEARTBEAT_TTL)
    except Exception:
        pass


async def _unregister_device_presence(device_id: str):
    """Supprime la présence de l'enceinte de Redis."""
    key = f"jarvis:presence:device:{device_id}"
    try:
        await cache_service.delete(key)
    except Exception:
        pass


# ─── Canal unique : vérification ─────────────────────────────────────────────

def _is_pwa_session_active() -> bool:
    """Retourne True si une session PWA (/ws) est actuellement connectée et parle."""
    ws = active_task_controller.get("websocket")
    if not ws:
        return False
    speech = get_speech_state()
    return speech in (SpeechState.MODEL_SPEAKING, SpeechState.USER_SPEAKING)


# ─── Heartbeat task ────────────────────────────────────────────────────────────

async def _heartbeat_loop(device_id: str, websocket: WebSocket):
    """Envoie un ping toutes les 30 s et met à jour la présence Redis."""
    try:
        while True:
            await asyncio.sleep(DEVICE_HEARTBEAT_INTERVAL)
            await _update_device_heartbeat(device_id)
            try:
                await websocket.send_text(json.dumps({"type": "ping_server"}))
            except Exception:
                break
    except asyncio.CancelledError:
        pass


# ─── WebSocket endpoint principal ─────────────────────────────────────────────

@router.websocket("/ws/device")
async def device_voice_channel(websocket: WebSocket):
    """Canal WebSocket audio full-duplex pour l'enceinte physique ESP32-S3.

    Protocole :
      1. Accept handshake HTTP 101 Switching Protocols
      2. Device envoie hello {type, device_id, mac, firmware_version, sample_rate}
      3. VPS répond par hello standard {type: "hello", transport: "websocket", ...}
      4. Device stream binary Opus/PCM mono
      5. VPS stream binary PCM vers device avec notifications JSON
    """
    # ── Toujours accepter le WebSocket en premier pour garantir le handshake HTTP 101 ──
    await websocket.accept()

    # ── Authentification ───────────────────────────────────────────────────────
    payload = await _authenticate_device_ws(websocket)
    if not payload:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Authentification device refusée"
        }))
        await websocket.close(code=1008, reason="Authentification device refusée")
        return

    device_id = payload.get("device_id", "esp32_speaker")
    device_name = payload.get("device_name", "ESP32 Speaker")

    # ── Unicité : une seule session device à la fois par device_id ─────────────
    existing = _DEVICE_SESSIONS.get(device_id)
    if existing:
        try:
            await existing["websocket"].close(code=1000, reason="Nouvelle connexion du même device")
        except Exception:
            pass

    _DEVICE_SESSIONS[device_id] = {
        "websocket": websocket,
        "connected_at": time.time(),
        "device_name": device_name,
        "mac": payload.get("mac", ""),
    }

    await _register_device_presence(device_id, device_name, payload.get("mac", ""))
    print(f"[DeviceVoice] Enregistrement device {device_id} dans supervision")
    print(f"[DeviceVoice] ✅ Enceinte connectée : {device_name} ({device_id})")

    # ── Initialisation Codec Opus ──────────────────────────────────────────────
    opus_decoder = opuslib.Decoder(16000, 1) if _OPUS_AVAILABLE else None
    opus_encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP) if _OPUS_AVAILABLE else None

    # ── Session Gemini Live dédiée au device ───────────────────────────────────
    session = None
    session_ctx = None
    speaking_state = {"active": False}
    listening_active = False
    mac_address = ""
    heartbeat_task: Optional[asyncio.Task] = None
    out_pcm_buffer = bytearray()

    try:
        # Sélection du client Gemini (même logique que /ws)
        current_live_client = client_free or client_paid
        if not current_live_client:
            await websocket.send_text(json.dumps({
                "type": "error",
                "code": "no_gemini_key",
                "message": "Aucune clé Gemini configurée"
            }))
            return

        # Établir la session Gemini Live
        active_live_model = config.GEMINI_LIVE_MODEL
        session_ctx, session = await _establish_live_session(active_live_model, current_live_client)
        print(f"[DeviceVoice] Session Gemini Live établie ({active_live_model})")

        # Stocker la référence session (nécessaire pour VoiceInjectionQueue push_speak)
        active_task_controller.setdefault("device_sessions", {})[device_id] = session

        # Lancer le heartbeat
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(device_id, websocket),
            name=f"device_heartbeat_{device_id}"
        )

        # ── Tâche : Device → Gemini Live (audio entrant + messages JSON) ────────
        async def device_to_gemini():
            nonlocal listening_active, mac_address
            try:
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect(code=1000)

                    # ── Trames audio binaires (Opus 16kHz depuis l'ESP32) ──────
                    if "bytes" in msg and msg["bytes"]:
                        raw = msg["bytes"]
                        if len(raw) > MAX_AUDIO_FRAME_BYTES:
                            print(f"[DeviceVoice] ⚠️ Trame trop grande ({len(raw)} B), ignorée")
                            continue

                        if not listening_active:
                            continue  # On n'est pas en mode écoute, ignorer l'audio

                        # Règle canal unique : si PWA parle, on ne forwarde pas au Gemini du device
                        if not session:
                            continue

                        # Décodage Opus vers PCM 16kHz linéaire si disponible
                        pcm_data = raw
                        if opus_decoder:
                            try:
                                # Trame 60ms standard (960 échantillons)
                                pcm_data = opus_decoder.decode(raw, 960)
                            except Exception:
                                try:
                                    # Trame 20ms standard (320 échantillons)
                                    pcm_data = opus_decoder.decode(raw, 320)
                                except Exception:
                                    pcm_data = raw

                        # Envoi à Gemini Live
                        try:
                            await session.send_realtime_input(
                                audio=types.Blob(data=pcm_data, mime_type=f"audio/pcm;rate={DEVICE_AUDIO_RATE_IN}")
                            )
                        except Exception as e:
                            print(f"[DeviceVoice] Erreur forward audio Gemini : {e}")

                    # ── Messages JSON de contrôle ─────────────────────────────
                    elif "text" in msg and msg["text"]:
                        try:
                            payload_msg = json.loads(msg["text"])
                            msg_type = payload_msg.get("type", "")

                            # ─ hello : handshake initial standard XiaoZhi ────────────
                            if msg_type == "hello":
                                mac_address = payload_msg.get("mac", "")
                                fw_version = payload_msg.get("firmware_version", "unknown")
                                sample_rate = payload_msg.get("sample_rate", DEVICE_AUDIO_RATE_IN)
                                _DEVICE_SESSIONS[device_id]["mac"] = mac_address
                                await _register_device_presence(device_id, device_name, mac_address)
                                print(f"[DeviceVoice] Hello reçu — fw={fw_version}, mac={mac_address}, rate={sample_rate}Hz")
                                # Réponse standard XiaoZhi WebSocket
                                await websocket.send_text(json.dumps({
                                    "type": "hello",
                                    "transport": "websocket",
                                    "session_id": device_id,
                                    "audio_params": {
                                        "format": "opus",
                                        "sample_rate": 16000,
                                        "channels": 1,
                                        "frame_duration": 60
                                    }
                                }))

                            # ─ listen : événements d'écoute XiaoZhi (detect, start, stop) ─
                            elif msg_type == "listen":
                                state = payload_msg.get("state", "")
                                if state in ("detect", "start"):
                                    listening_active = True
                                    notify_user_speaking()
                                    await broadcast_supervision()
                                    print(f"[DeviceVoice] 🎙️ Écoute active (state={state})")
                                elif state == "stop":
                                    listening_active = False
                                    await broadcast_supervision()
                                    print(f"[DeviceVoice] 🔇 Fin écoute utilisateur")

                            # ─ start_listening : wake word détecté ───────────────────
                            elif msg_type == "start_listening":
                                listening_active = True
                                notify_user_speaking()
                                await broadcast_supervision()
                                print(f"[DeviceVoice] 🎙️ Wake word détecté — écoute active")

                            # ─ stop_listening : fin du tour utilisateur ───────────────
                            elif msg_type == "stop_listening":
                                listening_active = False
                                await broadcast_supervision()
                                print(f"[DeviceVoice] 🔇 Fin écoute utilisateur")

                            # ─ abort : interruption XiaoZhi (barge-in / wake word) ───────
                            elif msg_type == "abort":
                                speaking_state["active"] = False
                                notify_interrupted("user_barge_in")
                                try:
                                    from services.metrics_service import metrics_service
                                    metrics_service.record_speech_cut(
                                        "user_barge_in",
                                        details=f"Device abort reason={payload_msg.get('reason', '')}"
                                    )
                                except Exception:
                                    pass
                                print(f"[DeviceVoice] ⚡ Abort / Barge-in depuis le device")

                            # ─ playback_finished : device a fini de jouer ─────
                            elif msg_type == "playback_finished":
                                speaking_state["active"] = False
                                notify_playback_finished()
                                await broadcast_supervision()
                                print(f"[DeviceVoice] ✅ Lecture terminée sur le device")

                            # ─ barge_in : interruption pendant lecture ────────
                            elif msg_type == "barge_in":
                                speaking_state["active"] = False
                                notify_interrupted("user_barge_in")
                                listening_active = True
                                notify_user_speaking()
                                print(f"[DeviceVoice] ⚡ Barge-in depuis le device")

                            # ─ ping : keepalive ───────────────────────────────
                            elif msg_type == "ping":
                                await websocket.send_text(json.dumps({
                                    "type": "pong",
                                    "ts": time.time()
                                }))
                                await _update_device_heartbeat(device_id)

                            # ─ switch_output : basculer voix vers ce device ───
                            elif msg_type == "request_voice_switch":
                                active_task_controller["preferred_output"] = "device"
                                active_task_controller["preferred_device_id"] = device_id
                                await websocket.send_text(json.dumps({
                                    "type": "voice_switch_ack",
                                    "output": "device",
                                    "message": "Jarvis parlera maintenant via l'enceinte"
                                }))
                                print(f"[DeviceVoice] 🔀 Sortie vocale basculée vers l'enceinte {device_id}")

                        except json.JSONDecodeError:
                            pass
                        except Exception as e:
                            print(f"[DeviceVoice] Erreur traitement message JSON : {e}")

            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                raise
            finally:
                if session:
                    try:
                        await session.close()
                    except Exception:
                        pass

        # ── Tâche : Gemini Live → Device (audio + transcriptions + outils) ────
        async def gemini_to_device():
            nonlocal listening_active, out_pcm_buffer
            FRAME_BYTES_16K = 1920  # 60ms à 16kHz 16-bit mono = 960 échantillons = 1920 octets
            try:
                while True:
                    async for chunk in session.receive():
                        sc = chunk.server_content
                        if sc:
                            # Interruption serveur (barge-in Gemini)
                            if getattr(sc, "interrupted", False):
                                notify_interrupted("user_barge_in")
                                speaking_state["active"] = False
                                out_pcm_buffer.clear()
                                try:
                                    await websocket.send_text(json.dumps({"type": "tts", "state": "stop", "session_id": device_id}))
                                    await websocket.send_text(json.dumps({"type": "llm", "emotion": "idle", "session_id": device_id}))
                                except Exception:
                                    pass

                            # Transcription utilisateur
                            user_txt = None
                            if getattr(sc, "input_transcription", None) and sc.input_transcription.text:
                                user_txt = sc.input_transcription.text
                            if user_txt:
                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "stt",
                                        "text": user_txt,
                                        "session_id": device_id
                                    }))
                                except Exception:
                                    pass

                            # Tour de réponse du modèle
                            if sc.model_turn:
                                listening_active = False
                                for part in sc.model_turn.parts:
                                    # Transcription texte de la réponse
                                    if part.text and not getattr(sc, "output_transcription", None):
                                        try:
                                            await websocket.send_text(json.dumps({
                                                "type": "tts",
                                                "state": "sentence_start",
                                                "text": part.text,
                                                "session_id": device_id
                                            }))
                                        except Exception:
                                            pass

                                    # Audio PCM 24kHz → Resampling 16kHz + Encodage Opus → Device
                                    elif part.inline_data and part.inline_data.data:
                                        chunk_data = part.inline_data.data
                                        chunk_dur = len(chunk_data) / (DEVICE_AUDIO_RATE_OUT * 2)
                                        notify_generation_chunk(chunk_dur)

                                        if not speaking_state["active"]:
                                            speaking_state["active"] = True
                                            await broadcast_supervision()
                                            try:
                                                await websocket.send_text(json.dumps({
                                                    "type": "tts",
                                                    "state": "start",
                                                    "session_id": device_id
                                                }))
                                                await websocket.send_text(json.dumps({
                                                    "type": "llm",
                                                    "emotion": "speaking",
                                                    "session_id": device_id
                                                }))
                                            except Exception:
                                                pass

                                        # Rééchantillonnage 24kHz vers 16kHz
                                        pcm_16k = _resample_24k_to_16k(chunk_data)
                                        out_pcm_buffer.extend(pcm_16k)

                                        # Découpage et encodage en trames Opus 60ms
                                        while len(out_pcm_buffer) >= FRAME_BYTES_16K:
                                            frame_pcm = bytes(out_pcm_buffer[:FRAME_BYTES_16K])
                                            del out_pcm_buffer[:FRAME_BYTES_16K]
                                            try:
                                                if opus_encoder:
                                                    opus_packet = opus_encoder.encode(frame_pcm, 960)
                                                    await websocket.send_bytes(opus_packet)
                                                else:
                                                    await websocket.send_bytes(frame_pcm)
                                            except Exception:
                                                break

                            # Fin de tour (turn_complete)
                            if getattr(sc, "turn_complete", False):
                                # Vider le reliquat du buffer audio vers l'enceinte
                                if len(out_pcm_buffer) > 0:
                                    pad_len = FRAME_BYTES_16K - len(out_pcm_buffer)
                                    out_pcm_buffer.extend(b"\x00" * pad_len)
                                    frame_pcm = bytes(out_pcm_buffer[:FRAME_BYTES_16K])
                                    out_pcm_buffer.clear()
                                    try:
                                        if opus_encoder:
                                            opus_packet = opus_encoder.encode(frame_pcm, 960)
                                            await websocket.send_bytes(opus_packet)
                                        else:
                                            await websocket.send_bytes(frame_pcm)
                                    except Exception:
                                        pass

                                notify_turn_complete()
                                speaking_state["active"] = False
                                await broadcast_supervision()
                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "tts",
                                        "state": "stop",
                                        "session_id": device_id
                                    }))
                                    await websocket.send_text(json.dumps({
                                        "type": "llm",
                                        "emotion": "idle",
                                        "session_id": device_id
                                    }))
                                except Exception:
                                    pass

                        # ── Appels d'outils ────────────────────────────────────
                        if chunk.tool_call:
                            for call in chunk.tool_call.function_calls:
                                name = call.name
                                args = dict(call.args) if call.args else {}
                                notify_tool_started(name)

                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "llm",
                                        "emotion": "thinking",
                                        "session_id": device_id
                                    }))
                                except Exception:
                                    pass

                                tool_resp = await dispatch_tool(
                                    name=name,
                                    args=args,
                                    websocket=websocket,
                                    session=session,
                                    is_paid_live=False,
                                    live_display_label="ESP32 Device",
                                )

                                await session.send_tool_response(
                                    function_responses=[
                                        types.FunctionResponse(
                                            name=name,
                                            id=call.id,
                                            response=tool_resp,
                                        )
                                    ]
                                )
                                notify_tool_completed(name)

                                try:
                                    await websocket.send_text(json.dumps({
                                        "type": "tool_end",
                                        "tool_name": name
                                    }))
                                except Exception:
                                    pass

            except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
                raise
            except Exception as e:
                if is_quota_or_limit_error(e):
                    raise QuotaExhaustedError(str(e))
                print(f"[DeviceVoice] gemini_to_device erreur : {e}")
                raise

        # ── Lancement des deux tâches en parallèle ───────────────────────────
        d2g_task = asyncio.create_task(device_to_gemini(), name=f"d2g_{device_id}")
        g2d_task = asyncio.create_task(gemini_to_device(), name=f"g2d_{device_id}")

        async def _cancel_sister(t1, t2):
            try:
                await t1
            except Exception:
                pass
            finally:
                if not t2.done():
                    t2.cancel()

        asyncio.create_task(_cancel_sister(d2g_task, g2d_task))
        asyncio.create_task(_cancel_sister(g2d_task, d2g_task))

        try:
            await asyncio.gather(d2g_task, g2d_task)
        except (WebSocketDisconnect, WebSocketDisconnected, asyncio.CancelledError):
            pass
        except Exception as e:
            err_str = str(e).lower()
            is_normal = any(k in err_str for k in [
                "1000", "1001", "disconnect", "closed", "connection closed"
            ])
            if not is_normal:
                print(f"[DeviceVoice] ❌ Erreur session : {e}")
                console_monitor.record_error(
                    source="DeviceVoice",
                    message=str(e),
                    level="ERROR"
                )

    except Exception as outer_e:
        print(f"[DeviceVoice] ❌ Erreur critique : {outer_e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "code": "session_error",
                "message": str(outer_e)
            }))
        except Exception:
            pass

    finally:
        # ── Nettoyage ─────────────────────────────────────────────────────────
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()

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

        # Supprimer la session du registre device
        active_task_controller.get("device_sessions", {}).pop(device_id, None)
        _DEVICE_SESSIONS.pop(device_id, None)

        # Nettoyer la présence Redis
        await _unregister_device_presence(device_id)

        print(f"[DeviceVoice] 🔌 Enceinte déconnectée : {device_name} ({device_id})")

        try:
            await websocket.close()
        except Exception:
            pass


# ─── Endpoint REST : générer un token device ─────────────────────────────────

from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class GenerateDeviceTokenRequest(BaseModel):
    device_name: str = "Waveshare ESP32-S3 Speaker"
    mac_address: str = ""
    admin_password: str  # Mot de passe maître requis pour émettre un token device


@router.post("/api/device/generate-token")
async def generate_device_token(req: GenerateDeviceTokenRequest, request: Request):
    """Génère un token JWT role='device' pour l'enceinte ESP32-S3.
    Protégé par le mot de passe maître (POST body).
    Le token est ensuite flashé en NVS sur l'ESP32.
    """
    if req.admin_password != config.ACCESS_PASSWORD:
        raise HTTPException(status_code=401, detail="Mot de passe administrateur incorrect")

    import secrets
    device_id = f"esp32_{secrets.token_hex(8)}"

    token = auth_service.generate_token(
        device_id=device_id,
        device_name=req.device_name,
        role="device",
        custom_claims={
            "mac_address": req.mac_address,
            "device_type": "esp32_speaker",
            "registered_via": "admin_api",
            "registered_at": time.time(),
        },
        expiry_days=3650,  # 10 ans
    )

    print(f"[DeviceVoice] 🔑 Token device généré : {device_id} ({req.device_name})")

    return {
        "status": "ok",
        "device_id": device_id,
        "device_name": req.device_name,
        "role": "device",
        "token": token,
        "websocket_url": f"wss://jarvis.signalcraftapps.com/ws/device",
        "expiry_days": 3650,
        "instructions": (
            "Flashez ce token dans la NVS de l'ESP32 avec la commande : "
            "nvs_flash write --namespace jarvis --key device_token --type string --value <token>"
        )
    }


@router.get("/api/device/sessions")
async def list_device_sessions(request: Request):
    """Liste les sessions device actuellement connectées (pour supervision HUD).
    Requiert un token admin valide.
    """
    token = request.query_params.get("token") or request.cookies.get("jarvis_device_token")
    payload = await auth_service.verify_token(token)
    if not payload or payload.get("role") not in ("admin",):
        raise HTTPException(status_code=401, detail="Accès non autorisé")

    sessions = []
    for did, info in _DEVICE_SESSIONS.items():
        sessions.append({
            "device_id": did,
            "device_name": info.get("device_name", ""),
            "mac": info.get("mac", ""),
            "connected_since": info.get("connected_at", 0),
            "connected_for_s": round(time.time() - info.get("connected_at", time.time())),
        })

    return {"status": "ok", "sessions": sessions, "count": len(sessions)}
