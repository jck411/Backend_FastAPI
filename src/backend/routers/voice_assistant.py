import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

from backend.services.voice_session import VoiceConnectionManager
from backend.services.stt_service import STTService
from backend.services.tts_service import TTSService
from backend.services.kiosk_chat_service import KioskChatService
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service
from backend.services.kiosk_ui_settings import get_kiosk_ui_settings_service


class TwoSegmentSplitter:
    """Stateful splitter that emits a head segment within word bounds and returns the remainder as tail."""

    def __init__(self, min_head_words: int = 8, max_head_words: int = 20):
        self.min_head_words = min_head_words
        self.max_head_words = max_head_words
        self._buffer = ""
        self._tail_parts = []
        self._head_text: Optional[str] = None
        self._head_reason: Optional[str] = None
        self._head_word_count: Optional[int] = None

    @staticmethod
    def _count_words_until(text: str, position: int) -> int:
        words = list(re.finditer(r"\S+", text[:position]))
        return len(words)

    def consume(self, chunk: str) -> Optional[Dict[str, Any]]:
        """Consume a chunk and return head info when the split is decided."""
        if not chunk:
            return None

        if self._head_text is not None:
            self._tail_parts.append(chunk)
            return None

        self._buffer += chunk

        head_info = self._maybe_emit_head()
        if head_info:
            head_text, tail_remainder, reason, word_count = head_info
            self._head_text = head_text
            self._head_reason = reason
            self._head_word_count = word_count
            self._buffer = ""
            if tail_remainder:
                self._tail_parts.append(tail_remainder)
            return {
                "text": head_text,
                "reason": reason,
                "word_count": word_count,
            }

        return None

    def _maybe_emit_head(self) -> Optional[tuple[str, str, str, int]]:
        word_spans = list(re.finditer(r"\S+", self._buffer))
        total_words = len(word_spans)

        if total_words < self.min_head_words:
            return None

        # Prefer a delimiter within bounds
        for match in re.finditer(r"[.!?\n]", self._buffer):
            delimiter_end = match.end()
            words_until = self._count_words_until(self._buffer, delimiter_end)
            if self.min_head_words <= words_until <= self.max_head_words:
                head_text = self._buffer[:delimiter_end]
                tail_remainder = self._buffer[delimiter_end:]
                return head_text, tail_remainder, "delimiter", words_until

        # Force split at max words if needed
        if total_words >= self.max_head_words:
            split_at = word_spans[self.max_head_words - 1].end()
            head_text = self._buffer[:split_at]
            tail_remainder = self._buffer[split_at:]
            return head_text, tail_remainder, "max_words", self.max_head_words

        return None

    def finalize(self) -> tuple[str, str, Optional[str], Optional[int]]:
        """Finalize and return head, tail, reason, and word count."""
        if self._head_text is None:
            # No split happened; entire response is the head
            return self._buffer, "", None, self._count_words_until(self._buffer, len(self._buffer))

        tail_text = "".join(self._tail_parts)
        return self._head_text, tail_text, self._head_reason, self._head_word_count

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

    tts_cancel_event = asyncio.Event()
    tts_task: Optional[asyncio.Task] = None

    async def cancel_tts():
        nonlocal tts_task, tts_cancel_event
        tts_cancel_event.set()
        if tts_task and not tts_task.done():
            tts_task.cancel()
            logger.info(f"Cancelled active TTS task for {client_id}")

    async def stream_tts_segment(text: str, segment_label: str):
        nonlocal tts_cancel_event
        try:
            logger.info(f"Starting TTS for segment '{segment_label}' ({len(text.split())} words)")
            sample_rate, audio_iter = await tts_service.stream_synthesize(text)

            if sample_rate == 0:
                logger.warning(f"TTS not available for segment '{segment_label}'")
                return

            chunk_index = 0
            await manager.broadcast({
                "type": "tts_audio_start",
                "total_bytes": None,
                "total_chunks": None,
                "sample_rate": sample_rate
            })

            async for audio_chunk in audio_iter:
                if tts_cancel_event.is_set():
                    logger.info(f"TTS cancelled mid-stream for segment '{segment_label}'")
                    return

                await manager.broadcast({
                    "type": "tts_audio_chunk",
                    "data": base64.b64encode(audio_chunk).decode('utf-8'),
                    "chunk_index": chunk_index,
                    "is_last": False
                })
                chunk_index += 1

            if tts_cancel_event.is_set():
                logger.info(f"TTS cancelled before completion for segment '{segment_label}'")
                return

            await manager.broadcast({"type": "tts_audio_end"})
            logger.info(f"Completed TTS for segment '{segment_label}'")
        except asyncio.CancelledError:
            logger.info(f"TTS task cancelled for segment '{segment_label}'")
        except Exception as exc:
            logger.error(f"TTS streaming failed for segment '{segment_label}': {exc}", exc_info=True)

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

                # Generate LLM response with streaming
                nonlocal tts_cancel_event, tts_task
                tts_cancel_event = asyncio.Event()
                full_response = ""
                splitter = TwoSegmentSplitter()
                head_tts_task: Optional[asyncio.Task] = None
                try:
                    # Signal start of streaming response
                    await manager.broadcast({"type": "assistant_response_start"})

                    async for event in kiosk_chat_service.generate_response_streaming(text, client_id):
                        if event["type"] == "text_chunk":
                            chunk = event["content"]
                            full_response += chunk
                            await manager.broadcast({"type": "assistant_response_chunk", "text": chunk})

                            head_ready = splitter.consume(chunk)
                            if head_ready and head_tts_task is None:
                                logger.info(
                                    f"Emitting head segment at {head_ready['word_count']} words (reason: {head_ready['reason']})"
                                )
                                head_tts_task = asyncio.create_task(stream_tts_segment(head_ready["text"], "head"))
                                tts_task = head_tts_task
                        elif event["type"] == "tool_status":
                            await manager.broadcast({
                                "type": "tool_status",
                                "status": event["status"],
                                "name": event["name"],
                            })
                        elif event["type"] == "error":
                            full_response = event.get("message", "Sorry, I encountered an error.")
                            break

                    # Signal end of streaming (with full text for backward compatibility)
                    await manager.broadcast({"type": "assistant_response_end", "text": full_response})

                except Exception as e:
                    logger.error(f"LLM generation failed for {client_id}: {e}", exc_info=True)
                    full_response = "Sorry, I couldn't process that request."
                    await manager.broadcast({"type": "assistant_response_end", "text": full_response})

                response_text = full_response.strip() if full_response else "Action completed."

                if response_text:
                    await manager.update_state(client_id, "SPEAKING")

                    # Use streaming TTS with two segments
                    try:
                        head_text, tail_text, head_reason, head_word_count = splitter.finalize()

                        if head_tts_task is None and head_text:
                            logger.info(
                                f"Emitting head segment at {head_word_count} words (reason: {head_reason or 'end_of_stream'})"
                            )
                            head_tts_task = asyncio.create_task(stream_tts_segment(head_text, "head"))
                            tts_task = head_tts_task

                        if head_tts_task:
                            try:
                                await head_tts_task
                            finally:
                                tts_task = None

                        if tail_text:
                            logger.info("Starting tail segment TTS")
                            tts_task = asyncio.create_task(stream_tts_segment(tail_text, "tail"))
                            try:
                                await tts_task
                            finally:
                                tts_task = None
                        else:
                            logger.info("No tail segment to play")
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
                            ui_settings = get_kiosk_ui_settings_service().get_settings()
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

            elif event_type == "tts_playback_end":
                logger.info(f"TTS playback ended for {client_id}")
                # Check if conversation mode is active
                try:
                    llm_settings = get_kiosk_llm_settings_service().get_settings()
                    if llm_settings.conversation_mode:
                        logger.info(f"Conversation mode ON - resuming listening")
                        await manager.set_all_states("LISTENING")
                        # Re-initialize STT session for follow-up
                    else:
                        logger.info(f"Conversation mode OFF - going to IDLE")
                        await manager.set_all_states("IDLE")
                except Exception as e:
                    logger.error(f"Error checking conversation mode: {e}")
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
