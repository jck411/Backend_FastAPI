"""
TTS Processor for Queue-Based Audio Streaming.

This module provides a queue-based TTS processor that reads phrases from
a phrase queue, synthesizes audio using the TTS service, and writes audio
chunks to an output queue for immediate streaming.

Architecture:
    phrase_queue → TTSProcessor.process() → audio_queue → WebSocket broadcast

The processor is designed for concurrent operation:
- Runs as an async task alongside LLM streaming
- Processes phrases as they arrive in the queue
- Streams audio chunks as they're received from the TTS provider
- Handles cancellation gracefully for barge-in support

Usage:
    processor = TTSProcessor(tts_service, manager)

    # Start processing task BEFORE LLM streaming begins
    process_task = asyncio.create_task(
        processor.process(phrase_queue, cancel_event)
    )

    # Feed phrases from LLM stream
    for phrase in segmenter.consume(chunk):
        await phrase_queue.put(phrase)

    await phrase_queue.put(None)  # Signal end
    await process_task
"""

import asyncio
import base64
import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.tts_service import TTSService
    from backend.services.voice_session import VoiceConnectionManager

logger = logging.getLogger(__name__)


class TTSProcessor:
    """
    Queue-based TTS processor for streaming audio synthesis.

    Reads phrases from an input queue, synthesizes audio using the TTS service,
    and broadcasts audio chunks via WebSocket as they arrive.

    Attributes:
        tts_service: The TTS service instance for audio synthesis
        manager: WebSocket connection manager for broadcasting
    """

    def __init__(
        self,
        tts_service: "TTSService",
        manager: "VoiceConnectionManager"
    ):
        """
        Initialize the TTS processor.

        Args:
            tts_service: TTS service instance for audio synthesis
            manager: Voice connection manager for WebSocket broadcasts
        """
        self.tts_service = tts_service
        self.manager = manager

    async def process(
        self,
        phrase_queue: asyncio.Queue,
        cancel_event: asyncio.Event,
        stt_service: Optional[object] = None
    ) -> None:
        """
        Process phrases from queue and broadcast audio chunks.

        This method runs until it receives None from the phrase_queue or
        the cancel_event is set. For each phrase, it:
        1. Calls TTS service to get streaming audio
        2. Broadcasts tts_audio_start on first phrase
        3. Broadcasts tts_audio_chunk for each audio chunk
        4. Broadcasts tts_audio_end when all phrases are processed

        Args:
            phrase_queue: Queue of phrases to synthesize
            cancel_event: Event to signal cancellation (for barge-in)
            stt_service: Optional STT service to pause during TTS playback
        """
        start_time = time.monotonic()
        first_phrase = True
        first_audio_chunk = True
        total_chunks = 0
        sample_rate = 0

        try:
            while True:
                # Check for cancellation
                if cancel_event.is_set():
                    logger.info("TTS processor cancelled")
                    await self.manager.broadcast({"type": "tts_audio_cancelled"})
                    return

                # Get next phrase (with timeout to check cancel event)
                try:
                    phrase = await asyncio.wait_for(
                        phrase_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                # None signals end of stream
                if phrase is None:
                    break

                phrase = phrase.strip()
                if not phrase:
                    continue

                logger.info(f"Processing phrase ({len(phrase)} chars): {phrase[:50]}...")

                # Get streaming audio from TTS service
                try:
                    sample_rate, audio_iter = await self.tts_service.stream_synthesize(phrase)

                    if sample_rate == 0:
                        logger.warning("TTS not available, skipping phrase")
                        continue

                    # Send tts_audio_start on first phrase
                    if first_phrase:
                        await self.manager.broadcast({
                            "type": "tts_audio_start",
                            "sample_rate": sample_rate,
                            "total_bytes": None,
                            "total_chunks": None
                        })
                        first_phrase = False

                        # Pause STT for all clients to prevent self-transcription
                        if stt_service:
                            for cid in self.manager.active_connections:
                                stt_service.pause_session(cid)

                    # Stream audio chunks
                    async for audio_chunk in audio_iter:
                        if cancel_event.is_set():
                            logger.info("TTS cancelled mid-stream")
                            await self.manager.broadcast({"type": "tts_audio_cancelled"})
                            return

                        if first_audio_chunk:
                            elapsed = (time.monotonic() - start_time) * 1000
                            logger.info(f"🎵 First audio chunk in {elapsed:.0f}ms")
                            first_audio_chunk = False

                        await self.manager.broadcast({
                            "type": "tts_audio_chunk",
                            "data": base64.b64encode(audio_chunk).decode('utf-8'),
                            "chunk_index": total_chunks,
                            "is_last": False
                        })
                        total_chunks += 1

                except Exception as e:
                    logger.error(f"TTS synthesis error for phrase: {e}")
                    continue

            # All phrases processed - send end signal
            if not first_phrase:  # Only if we sent at least one chunk
                await self.manager.broadcast({"type": "tts_audio_end"})
                elapsed = (time.monotonic() - start_time) * 1000
                logger.info(f"TTS processing complete: {total_chunks} chunks in {elapsed:.0f}ms")

        except asyncio.CancelledError:
            logger.info("TTS processor task cancelled")
            await self.manager.broadcast({"type": "tts_audio_cancelled"})
        except Exception as e:
            logger.error(f"TTS processor error: {e}", exc_info=True)
            await self.manager.broadcast({"type": "tts_audio_cancelled"})
