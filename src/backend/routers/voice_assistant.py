import asyncio
import base64
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.voice_session import VoiceConnectionManager
from backend.services.stt_service import STTService
from backend.services.tts_service import TTSService
from backend.services.kiosk_chat_service import KioskChatService
from backend.services.client_settings_service import get_client_settings_service
from backend.services.tts import TextSegmenter, TTSProcessor

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

    Uses queue-based TTS pipeline:
    - TextSegmenter splits LLM chunks into phrases at delimiters (min 25 chars)
    - TTSProcessor synthesizes phrases and broadcasts audio chunks via WebSocket
    - Frontend plays audio immediately using Web Audio API
    """
    await manager.connect(websocket, client_id)

    tts_cancel_event = asyncio.Event()
    tts_task: Optional[asyncio.Task] = None

    async def cancel_tts():
        nonlocal tts_task, tts_cancel_event
        tts_cancel_event.set()
        if tts_task and not tts_task.done():
            tts_task.cancel()
            logger.info(f"Cancelled active TTS task for {client_id}")


    async def start_stt_session():
        """Helper to start the STT session with callbacks."""

        async def on_transcript_received(text: str, is_final: bool):
            logger.debug(f"Transcript ({client_id}): {text} (Final: {is_final})")

            # Broadcast transcript to frontend
            await manager.broadcast({"type": "transcript", "text": text, "is_final": is_final})

            # User spoke, so update activity
            session = manager.get_session(client_id)
            if session:
                session.update_activity()

            if is_final:
                # Transition to PROCESSING
                await manager.update_state(client_id, "PROCESSING")

                # Generate LLM response with streaming + queue-based TTS
                nonlocal tts_cancel_event, tts_task
                tts_cancel_event = asyncio.Event()
                full_response = ""

                # Create queues for the pipeline
                phrase_queue: asyncio.Queue[str | None] = asyncio.Queue()

                # Initialize segmenter with min 25 chars before first delimiter
                segmenter = TextSegmenter(min_chars=25)

                # Initialize processor (will broadcast audio chunks to WebSocket)
                processor = TTSProcessor(tts_service, manager)

                # Start TTS processor task BEFORE LLM streaming
                # This ensures it's ready to process phrases immediately
                tts_task = asyncio.create_task(
                    processor.process(phrase_queue, tts_cancel_event, stt_service)
                )

                try:
                    # Signal start of streaming response
                    await manager.broadcast({"type": "assistant_response_start"})

                    async for event in kiosk_chat_service.generate_response_streaming(text, client_id):
                        if event["type"] == "text_chunk":
                            chunk = event["content"]
                            full_response += chunk
                            await manager.broadcast({"type": "assistant_response_chunk", "text": chunk})

                            # Feed chunks to segmenter, emit phrases to queue
                            for phrase in segmenter.consume(chunk):
                                logger.info(f"Emitting phrase ({len(phrase)} chars): {phrase[:40]}...")
                                await phrase_queue.put(phrase)

                        elif event["type"] == "tool_status":
                            await manager.broadcast({
                                "type": "tool_status",
                                "status": event["status"],
                                "name": event["name"],
                            })
                        elif event["type"] == "error":
                            full_response = event.get("message", "Sorry, I encountered an error.")
                            # Put error message as single phrase
                            await phrase_queue.put(full_response)
                            break

                    # Flush any remaining text from segmenter
                    final_phrase = segmenter.flush()
                    if final_phrase:
                        logger.info(f"Flushing final phrase ({len(final_phrase)} chars)")
                        await phrase_queue.put(final_phrase)

                    # Signal end to phrase queue
                    await phrase_queue.put(None)

                    # Signal end of streaming (with full text for backward compatibility)
                    await manager.broadcast({"type": "assistant_response_end", "text": full_response})

                except Exception as e:
                    logger.error(f"LLM generation failed for {client_id}: {e}", exc_info=True)
                    await phrase_queue.put("Sorry, I couldn't process that request.")
                    await phrase_queue.put(None)
                    await manager.broadcast({"type": "assistant_response_end", "text": "Sorry, I couldn't process that request."})

                # Wait for TTS processing to complete
                if tts_task:
                    await manager.update_state(client_id, "SPEAKING")
                    try:
                        await tts_task
                    except asyncio.CancelledError:
                        logger.info("TTS task was cancelled")
                    finally:
                        tts_task = None

                # Transition back based on conversation mode
                try:
                    llm_settings = get_client_settings_service("kiosk").get_llm()
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

                # Interrupt TTS - broadcast to ALL clients (especially the frontend playing audio)
                await manager.broadcast({"type": "interrupt_tts"})
                await cancel_tts()
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

                        # Check for Silence / Idle Timeout
                        try:
                            # If we are listening but haven't heard/done anything for X seconds, go to IDLE
                            ui_settings = get_client_settings_service("kiosk").get_ui()
                            silence_duration_ms = (datetime.utcnow() - session.last_activity).total_seconds() * 1000

                            if silence_duration_ms > ui_settings.idle_return_delay_ms:
                                logger.info(f"Silence timeout reached ({silence_duration_ms:.0f}ms > {ui_settings.idle_return_delay_ms}ms) - Returning to IDLE")
                                await manager.set_all_states("IDLE", extra_data={"reason": "timeout"})
                        except Exception as e:
                            logger.error(f"Error checking silence timeout: {e}")

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
                # Redundant safety: Ensure all ears are closed
                for cid in manager.active_connections:
                    stt_service.pause_session(cid)

            elif event_type == "tts_playback_end":
                logger.info(f"TTS playback ended for {client_id}")
                # Check if conversation mode is active
                try:
                    llm_settings = get_client_settings_service("kiosk").get_llm()
                    if llm_settings.conversation_mode:
                        logger.info(f"Conversation mode ON - resuming listening")
                        # Resume ALL clients
                        for cid in manager.active_connections:
                            stt_service.resume_session(cid)
                        await manager.set_all_states("LISTENING")
                        # Re-initialize STT session for follow-up
                    else:
                        logger.info(f"Conversation mode OFF - going to IDLE")
                        # Resume ALL clients
                        for cid in manager.active_connections:
                            stt_service.resume_session(cid)
                        await manager.set_all_states("IDLE")
                except Exception as e:
                    logger.error(f"Error checking conversation mode: {e}")
                    # Safety: Resume all
                    for cid in manager.active_connections:
                        stt_service.resume_session(cid)
                    await manager.set_all_states("IDLE")

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
