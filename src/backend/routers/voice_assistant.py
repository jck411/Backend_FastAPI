import base64
import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from backend.services.voice_session import VoiceConnectionManager
from backend.services.stt_service import STTService
from backend.services.tts_service import TTSService

router = APIRouter(prefix="/api/voice", tags=["Voice Assistant"])
logger = logging.getLogger(__name__)

async def handle_connection(websocket: WebSocket, client_id: str, manager: VoiceConnectionManager, stt_service: STTService, tts_service: TTSService):
    """
    Main loop for handling a single client's WebSocket connection.
    """
    await manager.connect(websocket, client_id)

    # Session state for this specific connection
    # (In addition to the global session object, we might need local vars)

    async def start_stt_session():
        """Helper to start the STT session with callbacks."""

        async def on_transcript_received(text: str, is_final: bool):
            logger.debug(f"Transcript ({client_id}): {text} (Final: {is_final})")

            # Broadcast transcript to frontend
            await manager.broadcast({"type": "transcript", "text": text, "is_final": is_final})

            if is_final:
                # Transition to PROCESSING
                await manager.update_state(client_id, "PROCESSING")

                # Phase 1 Logic: Echo back
                response_text = f"I heard you say: {text}"

                if response_text:
                    await manager.update_state(client_id, "SPEAKING")
                    # Use TTS
                    try:
                        audio_data = await tts_service.synthesize(response_text)

                        if audio_data:
                            # 4. Play Audio on Client
                            await websocket.send_json({
                                "type": "tts_audio",
                                "data": base64.b64encode(audio_data).decode('utf-8')
                            })
                            logger.info(f"Sent TTS audio for {client_id}")
                    except Exception as e:
                        logger.error(f"TTS generation failed: {e}")
                    finally:
                        await manager.update_state(client_id, "IDLE")

        async def on_stt_error(error: str):
            logger.error(f"STT Error for {client_id}: {error}")
            await manager.update_state(client_id, "IDLE")

        await stt_service.create_session(client_id, on_transcript_received, on_stt_error)

    try:
        while True:
            # Receive message from Pi
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "heartbeat":
                # Respond with heartbeat or just ignore/log
                # The Pi expects we just stay alive
                pass

            elif event_type == "connection_ready":
                logger.info(f"Client {client_id} ready.")

            elif event_type == "wakeword_detected":
                logger.info(f"Wake word detected for {client_id}")
                await manager.update_state(client_id, "LISTENING")
                # Start STT session
                await start_stt_session()

            elif event_type == "wakeword_barge_in":
                logger.info(f"Barge-in for {client_id}")
                # Interrupt TTS
                await manager.send_message(client_id, {"type": "interrupt_tts"})
                await manager.update_state(client_id, "LISTENING")

                # Reset STT
                await stt_service.close_session(client_id)
                await start_stt_session()

            elif event_type == "audio_chunk":
                session = manager.get_session(client_id)
                # Only process audio if we are in listening mode
                if session and session.state == "LISTENING":
                    payload = data.get("data")
                    if payload:
                        chunk = base64.b64decode(payload)
                        await stt_service.stream_audio(client_id, chunk)

            elif event_type == "stream_end":
                logger.info(f"Stream end for {client_id}")
                # We might want to keep the session open for the response,
                # but Deepgram connection might be finished.
                # Actually, stream_end often means "user stopped speaking" (VAD)
                # But Deepgram has its own VAD.
                # If the Pi sends stream_end, we should tell Deepgram we are done sending audio?
                # But Deepgram keeps connection open for transcripts.
                # Let's just ensure we don't stream more.
                pass

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
        manager.disconnect(client_id)
        await stt_service.close_session(client_id)
    except Exception as e:
        logger.error(f"Unexpected error for {client_id}: {e}")
        manager.disconnect(client_id)
        await stt_service.close_session(client_id)


@router.websocket("/connect")
async def voice_connect(websocket: WebSocket):
    # Depending on how the Pi connects, it might send client_id in query param or header?
    # Or we generate one.
    # Plan doesn't specify auth yet, so let's generate or use a header.
    # Let's assume a query param ?client_id=... or default to "pi_1"
    client_id = websocket.query_params.get("client_id", "default_pi")

    app_state = websocket.app.state

    # Ensure services are initialized
    if not hasattr(app_state, "voice_manager"):
        logger.error("Voice Manager not initialized")
        await websocket.close(code=1000, reason="Server not ready")
        return

    manager = app_state.voice_manager
    stt_service = app_state.stt_service
    tts_service = app_state.tts_service

    await handle_connection(websocket, client_id, manager, stt_service, tts_service)
