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


# ─── Resampler continu 24kHz -> 16kHz sans perte d'échantillons ───────────────

class Continuous24kTo16kResampler:
    """Rééchantillonne le flux PCM 24kHz 16-bit mono vers 16kHz 16-bit mono en continu.
    Conserve les reliquats d'octets / d'échantillons entre chaque paquet pour garantir
    une continuité de phase parfaite et supprimer les artefacts ou cliquetis.
    Ratio : 3 échantillons 24kHz (6 octets) -> 2 échantillons 16kHz (4 octets).
    """
    def __init__(self):
        self._buffer = bytearray()

    def process(self, pcm24k_bytes: bytes) -> bytes:
        if not pcm24k_bytes:
            return b""
        self._buffer.extend(pcm24k_bytes)

        # Nous traitons par triplets d'échantillons 16 bits (6 octets)
        n_triplets = len(self._buffer) // 6
        if n_triplets == 0:
            return b""

        process_len = n_triplets * 6
        raw_triplets = self._buffer[:process_len]
        del self._buffer[:process_len]

        samples_in = struct.unpack(f"<{n_triplets * 3}h", raw_triplets)
        out_samples = [0] * (n_triplets * 2)
        for i in range(n_triplets):
            s0 = samples_in[i * 3]
            s1 = samples_in[i * 3 + 1]
            s2 = samples_in[i * 3 + 2]
            # Interpolation linéaire exacte :
            # y0 = s0 (t = 0)
            # y1 = (s1 + s2) / 2 (t = 1.5 en horloge 24k -> 1.0 en horloge 16k)
            out_samples[i * 2] = s0
            out_samples[i * 2 + 1] = (s1 + s2) // 2

        return struct.pack(f"<{len(out_samples)}h", *out_samples)

    def flush(self) -> bytes:
        """Complète les derniers échantillons orphelins avec du padding zéro."""
        if not self._buffer:
            return b""
        if len(self._buffer) % 2 != 0:
            self._buffer.append(0)
        rem_bytes = len(self._buffer) % 6
        if rem_bytes > 0:
            self._buffer.extend(b"\x00" * (6 - rem_bytes))
        return self.process(b"")

    def clear(self):
        self._buffer.clear()


# ─── Régulateur de flux audio (Pacer) vers l'ESP32 ────────────────────────────

class DeviceAudioPacer:
    """Régule l'envoi des trames Opus 60ms vers l'ESP32 au rythme temps-réel (55ms par trame de 60ms).
    Évite l'engorgement de la file de décodage matérielle de l'ESP32 (limite 20 paquets / 1.2s),
    ce qui empêche tout rejet de paquet et toute dégradation sonore (voix hachée / gargouillis).
    """
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=300)
        self.task: Optional[asyncio.Task] = None
        self.running = False
        self.frames_sent = 0

    def start(self):
        if not self.task or self.task.done():
            self.running = True
            self.frames_sent = 0
            self.task = asyncio.create_task(self._pacer_loop(), name=f"pacer_{self.device_id}")

    async def put_frame(self, opus_bytes: bytes):
        """Ajoute une trame audio 60ms à la file d'émission régulée."""
        if not self.running:
            self.start()
        await self.queue.put(opus_bytes)

    async def _pacer_loop(self):
        TARGET_INTERVAL_S = 0.055  # 55ms par trame de 60ms
        BURST_LIMIT = 3  # Les 3 premières trames (180ms) partent immédiatement pour amorcer le buffer sans latence
        try:
            while self.running:
                frame = await self.queue.get()
                if frame is None:
                    self.queue.task_done()
                    break

                try:
                    await self.websocket.send_bytes(frame)
                    self.frames_sent += 1
                except Exception as e:
                    print(f"[DeviceVoice] Erreur envoi trame audio pacer : {e}")
                    self.queue.task_done()
                    break

                self.queue.task_done()

                # Régulation temporelle
                if self.frames_sent > BURST_LIMIT:
                    await asyncio.sleep(TARGET_INTERVAL_S)
                else:
                    await asyncio.sleep(0.005)

        except asyncio.CancelledError:
            pass
        finally:
            self.running = False

    async def wait_drained(self):
        """Attend que toutes les trames en attente soient transmises à l'ESP32."""
        if self.running and not self.queue.empty():
            await self.queue.join()

    def abort(self):
        """Interrompt immédiatement la diffusion en cours (ex: interruption / barge-in)."""
        self.running = False
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except Exception:
                break
        if self.task and not self.task.done():
            self.task.cancel()


# ─── WebSocket endpoint principal ─────────────────────────────────────────────

@router.websocket("/ws/device")
async def device_voice_channel(websocket: WebSocket):
    """Canal WebSocket audio full-duplex pour l'enceinte physique ESP32-S3.

    Protocole :
      1. Accept handshake HTTP 101 Switching Protocols
      2. Device envoie hello {type, device_id, mac, firmware_version, sample_rate}
      3. VPS répond par hello standard {type: "hello", transport: "websocket", ...}
      4. Device stream binary Opus/PCM mono 16kHz
      5. VPS stream binary Opus 16kHz régulé à 55ms/trame vers device avec notifications JSON
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

    # ── Initialisation Codec Opus & Composants Audio ────────────────────────────
    opus_decoder = opuslib.Decoder(16000, 1) if _OPUS_AVAILABLE else None
    opus_encoder = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP) if _OPUS_AVAILABLE else None
    resampler = Continuous24kTo16kResampler()
    pacer = DeviceAudioPacer(websocket, device_id)
    pacer.start()

    # ── Session Gemini Live dédiée au device ───────────────────────────────────
    session = None
    session_ctx = None
    speaking_state = {"active": False}
    listening_active = False
    mac_address = ""
    heartbeat_task: Optional[asyncio.Task] = None
    out_pcm_16k_buffer = bytearray()
    FRAME_BYTES_16K = 1920  # 60ms à 16kHz 16-bit mono = 960 échantillons = 1920 octets

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

                        if not session:
                            continue

                        # Décodage Opus vers PCM 16kHz linéaire
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
                                    # Si Jarvis était en train de parler, interruption immédiate
                                    if speaking_state["active"]:
                                        pacer.abort()
                                        resampler.clear()
                                        out_pcm_16k_buffer.clear()
                                        speaking_state["active"] = False
                                        notify_interrupted("user_barge_in")
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
                                if speaking_state["active"]:
                                    pacer.abort()
                                    resampler.clear()
                                    out_pcm_16k_buffer.clear()
                                    speaking_state["active"] = False
                                    notify_interrupted("user_barge_in")
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
                                pacer.abort()
                                resampler.clear()
                                out_pcm_16k_buffer.clear()
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
                                pacer.abort()
                                resampler.clear()
                                out_pcm_16k_buffer.clear()
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
                print(f"[DeviceVoice] device_to_gemini exception : {e}")
                raise
            finally:
                if session:
                    try:
                        await session.close()
                    except Exception:
                        pass

        # ── Tâche : Gemini Live → Device (audio + transcriptions + outils) ────
        async def gemini_to_device():
            nonlocal listening_active, out_pcm_16k_buffer
            try:
                while True:
                    async for chunk in session.receive():
                        sc = chunk.server_content
                        if sc:
                            # Interruption serveur (barge-in Gemini)
                            if getattr(sc, "interrupted", False):
                                notify_interrupted("user_barge_in")
                                pacer.abort()
                                resampler.clear()
                                out_pcm_16k_buffer.clear()
                                speaking_state["active"] = False
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

                                    # Audio PCM 24kHz → Resampling 16kHz + Encodage Opus → Pacer Queue
                                    elif part.inline_data and part.inline_data.data:
                                        chunk_data = part.inline_data.data
                                        chunk_dur = len(chunk_data) / (DEVICE_AUDIO_RATE_OUT * 2)
                                        notify_generation_chunk(chunk_dur)

                                        if not speaking_state["active"]:
                                            speaking_state["active"] = True
                                            pacer.start()
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

                                        # Rééchantillonnage 24kHz vers 16kHz continu sans perte
                                        pcm_16k = resampler.process(chunk_data)
                                        out_pcm_16k_buffer.extend(pcm_16k)

                                        # Découpage et encodage en trames Opus 60ms
                                        while len(out_pcm_16k_buffer) >= FRAME_BYTES_16K:
                                            frame_pcm = bytes(out_pcm_16k_buffer[:FRAME_BYTES_16K])
                                            del out_pcm_16k_buffer[:FRAME_BYTES_16K]
                                            try:
                                                if opus_encoder:
                                                    opus_packet = opus_encoder.encode(frame_pcm, 960)
                                                    await pacer.put_frame(opus_packet)
                                                else:
                                                    await pacer.put_frame(frame_pcm)
                                            except Exception as enc_err:
                                                print(f"[DeviceVoice] Erreur encodage Opus : {enc_err}")
                                                break

                            # Fin de tour (turn_complete)
                            if getattr(sc, "turn_complete", False):
                                # Vider le reliquat du resampleur vers le buffer 16kHz
                                flushed_16k = resampler.flush()
                                if flushed_16k:
                                    out_pcm_16k_buffer.extend(flushed_16k)

                                # Vider le reliquat du buffer 16kHz avec padding zéro
                                if len(out_pcm_16k_buffer) > 0:
                                    pad_len = FRAME_BYTES_16K - len(out_pcm_16k_buffer)
                                    out_pcm_16k_buffer.extend(b"\x00" * pad_len)
                                    frame_pcm = bytes(out_pcm_16k_buffer[:FRAME_BYTES_16K])
                                    out_pcm_16k_buffer.clear()
                                    try:
                                        if opus_encoder:
                                            opus_packet = opus_encoder.encode(frame_pcm, 960)
                                            await pacer.put_frame(opus_packet)
                                        else:
                                            await pacer.put_frame(frame_pcm)
                                    except Exception:
                                        pass

                                # Attendre que toutes les trames soient transmises à l'ESP32 au rythme régulé
                                await pacer.wait_drained()

                                # Période de grâce (500ms) pour que l'enceinte matérielle finisse la restitution de son buffer DAC
                                await asyncio.sleep(0.5)

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
        pacer.abort()
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
