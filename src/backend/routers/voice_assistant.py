import base64
import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from backend.services.voice_session import VoiceConnectionManager
from backend.services.stt_service import STTService
from backend.services.tts_service import TTSService
from backend.services.kiosk_chat_service import KioskChatService
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service

router = APIRouter(prefix="/api/voice", tags=["Voice Assistant"])
logger = logging.getLogger(__name__)

async def handle_connection(
    websocket: WebSocket,
    client_id: str,
    manager: VoiceConnectionManager,
    stt_service: STTService,
    tts_service: TTSService,
    kiosk_chat_service: KioskChatService
):
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

                # Generate LLM response
                try:
                    response_text = await kiosk_chat_service.generate_response(text, client_id=client_id)
                except Exception as e:
                    logger.error(f"LLM generation failed for {client_id}: {e}", exc_info=True)
                    response_text = "Sorry, I couldn't process that request."

                if response_text:
                    await manager.update_state(client_id, "SPEAKING")
                    # Send response text to frontend for display
                    await manager.broadcast({"type": "assistant_response", "text": response_text})

                    audio_played = False
                    # Use TTS
                    try:
                        audio_data = await tts_service.synthesize(response_text)

                        if audio_data:
                            # 4. Play Audio on Client - broadcast to all (browser + Pi)
                            await manager.broadcast({
                                "type": "tts_audio",
                                "data": base64.b64encode(audio_data).decode('utf-8')
                            })
                            logger.info(f"Sent TTS audio for {client_id}")
                            audio_played = True
                    except Exception as e:
                        logger.error(f"TTS generation failed: {e}")

                    try:
                        # Check conversation mode
                        llm_settings = get_kiosk_llm_settings_service().get_settings()
                        if llm_settings.conversation_mode:
                            logger.info(f"Conversation mode active for {client_id}, listening for reply")
                            await manager.update_state(client_id, "LISTENING")
                        else:
                            await manager.update_state(client_id, "IDLE")
                    except Exception as e:
                        logger.error(f"Error transitioning state after speaking: {e}")
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
                confidence = data.get("confidence", 0.0)
                logger.info(f"Wake word detected for {client_id} (confidence: {confidence})")

                # New conversation starts with wake word -> Clear history
                kiosk_chat_service.clear_history(client_id)

                await manager.update_state(client_id, "LISTENING")

                # Start STT processing
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
                        audio_b64 = payload.get("audio") if isinstance(payload, dict) else payload
                        chunk = base64.b64decode(audio_b64)
                        logger.debug(f"Received audio chunk for {client_id}: {len(chunk)} bytes")
                        await stt_service.stream_audio(client_id, chunk)
                    else:
                        logger.warning(f"Received audio_chunk event without data for {client_id}")
                else:
                    if not session:
                        logger.warning(f"Received audio_chunk but no session for {client_id}")
                    else:
                        # logger.debug(f"Received audio_chunk but state is {session.state}, not LISTENING")
                        pass

            elif event_type == "tts_playback_start":
                logger.info(f"TTS playback started for {client_id} - Muting ALL clients (State -> SPEAKING)")
                await manager.set_all_states("SPEAKING")

            elif event_type == "tts_playback_end":
                logger.info(f"TTS playback ended for {client_id} - Resuming ALL clients (State -> LISTENING)")
                # Only resume listening if we were speaking (avoid race conditions if we already moved on)
                # Or just force it, as end of playback generally means ready to listen.
                # Check if conversation mode is active or if we should go to IDLE?
                # Actually, standard flow: User speaks -> STT -> LLM -> TTS -> Client plays -> Client finishes -> Listen again.
                await manager.set_all_states("LISTENING")

                # Re-initialize STT session if needed, or ensuring it's ready.
                # Our STT service stays open, we just gate the chunks.

            elif event_type == "stream_end":
                logger.info(f"Stream end for {client_id}")
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
    # Note: KioskChatService is optional for startup but required for LLM processing
    if not hasattr(app_state, "voice_manager"):
        logger.error("Voice Manager not initialized")
        await websocket.close(code=1000, reason="Server not ready")
        return

    manager = app_state.voice_manager
    stt_service = app_state.stt_service
    tts_service = app_state.tts_service
    kiosk_chat_service = getattr(app_state, "kiosk_chat_service", None)

    if kiosk_chat_service is None:
        # Fallback if service not initialized properly (e.g. startup error)
        # We allow connection but LLM calls will fail individually
        logger.warning("KioskChatService not found in app state")

    await handle_connection(websocket, client_id, manager, stt_service, tts_service, kiosk_chat_service)
