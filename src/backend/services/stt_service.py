"""
Deepgram STT service using the synchronous SDK pattern with threading.
Based on working implementation from deepgram-voice-transcriber.
"""
import asyncio
import logging
import threading
from typing import Callable, Optional

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from backend.config import get_settings
from backend.services.kiosk_stt_settings import get_kiosk_stt_settings_service

logger = logging.getLogger(__name__)

# Audio settings (must match Pi sender)
SAMPLE_RATE = 16000


class DeepgramSession:
    """Manages a single Deepgram connection using the SDK v5 sync pattern."""

    def __init__(
        self,
        api_key: str,
        session_id: str,
        on_transcript: Callable[[str, bool], None],
        on_error: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,  # Called when Deepgram detects speech start
        eot_threshold: float = 0.7,
        eot_timeout_ms: int = 5000,
        eager_eot_threshold: Optional[float] = None,
        keyterms: Optional[list[str]] = None,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.api_key = api_key
        self.session_id = session_id
        self.on_transcript = on_transcript
        self.on_error = on_error
        self.on_speech_start = on_speech_start  # VAD callback

        # Configurable STT settings
        self.eot_threshold = eot_threshold
        self.eot_timeout_ms = eot_timeout_ms
        self.eager_eot_threshold = eager_eot_threshold
        self.keyterms = keyterms or []

        # Store the main event loop reference for scheduling callbacks from worker thread
        self._event_loop = event_loop

        self._client = DeepgramClient(api_key=api_key)
        self._context_manager = None
        self._socket = None
        self._ready = threading.Event()
        self._running = False
        self._ready = threading.Event()
        self._running = False
        self._listening_thread = None
        self._paused = False  # Track pause state

    def _handle_message(self, result):
        """Handle transcript messages from Deepgram."""
        try:
            # For v2 (Flux): transcript is at top level with event type
            event = getattr(result, "event", None)

            if event == "StartOfTurn":
                logger.info(f"--- StartOfTurn for {self.session_id} ---")
                # Notify that speech has started (used for VAD gating after barge-in)
                if self.on_speech_start:
                    if asyncio.iscoroutinefunction(self.on_speech_start):
                        if self._event_loop is not None:
                            asyncio.run_coroutine_threadsafe(
                                self.on_speech_start(),
                                self._event_loop
                            )
                    else:
                        self.on_speech_start()
                return

            transcript = getattr(result, "transcript", None)
            if transcript:
                is_end_of_turn = event == "EndOfTurn"
                logger.info(f"Transcript for {self.session_id}: '{transcript}' (eot={is_end_of_turn})")

                # Call callback - need to schedule in asyncio loop if it's async
                if asyncio.iscoroutinefunction(self.on_transcript):
                    if self._event_loop is not None:
                        # Use the stored event loop reference (main loop)
                        asyncio.run_coroutine_threadsafe(
                            self.on_transcript(transcript, is_end_of_turn),
                            self._event_loop
                        )
                    else:
                        logger.error(f"No event loop available for transcript callback")
                else:
                    self.on_transcript(transcript, is_end_of_turn)
            else:
                # v1 style: check for channel.alternatives
                if hasattr(result, 'channel'):
                    alternatives = result.channel.alternatives
                    if alternatives and len(alternatives) > 0:
                        transcript_text = alternatives[0].transcript
                        is_final = getattr(result, 'is_final', False)

                        if transcript_text:
                            logger.info(f"Transcript for {self.session_id}: '{transcript_text}' (final={is_final})")
                            if asyncio.iscoroutinefunction(self.on_transcript):
                                if self._event_loop is not None:
                                    asyncio.run_coroutine_threadsafe(
                                        self.on_transcript(transcript_text, is_final),
                                        self._event_loop
                                    )
                                else:
                                    logger.error(f"No event loop available for transcript callback")
                            else:
                                self.on_transcript(transcript_text, is_final)
        except Exception as e:
            logger.error(f"Error processing transcript for {self.session_id}: {e}", exc_info=True)

    def _on_open(self, _):
        logger.info(f"✅ Deepgram connected for {self.session_id}")
        self._ready.set()

    def _on_close(self, _):
        logger.info(f"Deepgram disconnected for {self.session_id}")
        self._ready.clear()

    def _on_error(self, error):
        logger.error(f"Deepgram error for {self.session_id}: {error}")
        if self.on_error:
            if asyncio.iscoroutinefunction(self.on_error):
                if self._event_loop is not None:
                    asyncio.run_coroutine_threadsafe(self.on_error(str(error)), self._event_loop)
                else:
                    logger.error(f"No event loop available for error callback")
            else:
                self.on_error(str(error))

    def connect(self) -> bool:
        """Connect to Deepgram."""
        # Use Flux model with v2 API for fast turn-taking detection
        params = {
            "model": "flux-general-en",
            "encoding": "linear16",
            "sample_rate": str(SAMPLE_RATE),
            "eot_threshold": str(self.eot_threshold),
            "eot_timeout_ms": str(self.eot_timeout_ms),
        }

        # Add optional eager EOT threshold
        if self.eager_eot_threshold is not None:
            params["eager_eot_threshold"] = str(self.eager_eot_threshold)

        # Add keyterms (Deepgram supports multiple keyterm params)
        # Note: The SDK may handle this differently; we pass as list
        if self.keyterms:
            params["keyterm"] = self.keyterms

        logger.info(f"Connecting to Deepgram Flux for {self.session_id} with settings: "
                    f"eot_threshold={self.eot_threshold}, eot_timeout_ms={self.eot_timeout_ms}, "
                    f"eager_eot={self.eager_eot_threshold}, keyterms={len(self.keyterms)}")

        try:
            # Use v2 for Flux turn-taking
            self._context_manager = self._client.listen.v2.connect(**params)
            self._socket = self._context_manager.__enter__()

            # Register handlers
            self._socket.on(EventType.OPEN, self._on_open)
            self._socket.on(EventType.MESSAGE, self._handle_message)
            self._socket.on(EventType.ERROR, self._on_error)
            self._socket.on(EventType.CLOSE, self._on_close)

            # Start listening in background thread
            def listen_loop():
                try:
                    self._socket.start_listening()
                except Exception as e:
                    if self._running:
                        logger.error(f"Listen error for {self.session_id}: {e}")

            self._running = True
            self._listening_thread = threading.Thread(target=listen_loop, daemon=True)
            self._listening_thread.start()

            # Wait for connection
            if not self._ready.wait(timeout=10.0):
                raise RuntimeError(f"Failed to connect to Deepgram for {self.session_id}")

            logger.info(f"Deepgram session ready for {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Deepgram for {self.session_id}: {e}", exc_info=True)
            return False

    def send_audio(self, data: bytes):
        """Send audio to Deepgram."""
        if self._socket and self._ready.is_set():
            if self._paused:
                return  # Drop audio when paused

            try:
                self._socket.send_media(data)
            except Exception as e:
                logger.error(f"Error sending audio for {self.session_id}: {e}")

    def pause(self):
        """Pause audio streaming (mute)."""
        self._paused = True
        logger.debug(f"Deepgram session {self.session_id} PAUSED")

    def resume(self):
        """Resume audio streaming (unmute)."""
        self._paused = False
        logger.debug(f"Deepgram session {self.session_id} RESUMED")

    def close(self):
        """Close connection."""
        self._running = False
        self._ready.clear()
        self._paused = False
        if self._context_manager:
            try:
                self._context_manager.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing Deepgram for {self.session_id}: {e}")
            self._context_manager = None
            self._socket = None
        logger.info(f"Deepgram session closed for {self.session_id}")


class STTService:
    """
    Manages Deepgram streaming STT sessions.
    Uses synchronous SDK pattern with threading for reliable connection management.
    """

    def __init__(self):
        settings = get_settings()
        api_key = settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        self.api_key = api_key
        self.sessions: dict[str, DeepgramSession] = {}

    async def create_session(
        self,
        session_id: str,
        on_transcript: Callable[[str, bool], None],
        on_error: Optional[Callable[[str], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
    ):
        """
        Start a new live transcription session.
        """
        try:
            # Close existing session if any
            if session_id in self.sessions:
                await self.close_session(session_id)

            # Get current kiosk STT settings
            kiosk_settings = get_kiosk_stt_settings_service().get_settings()

            # IMPORTANT: The Deepgram listener runs in a background thread,
            # which has no asyncio event loop. We must capture the main loop
            # here (in async context) and pass it to DeepgramSession for
            # thread-safe callback scheduling via run_coroutine_threadsafe().
            loop = asyncio.get_running_loop()

            # Create new session with configurable settings
            session = DeepgramSession(
                api_key=self.api_key,
                session_id=session_id,
                on_transcript=on_transcript,
                on_error=on_error,
                on_speech_start=on_speech_start,
                eot_threshold=kiosk_settings.eot_threshold,
                eot_timeout_ms=kiosk_settings.eot_timeout_ms,
                eager_eot_threshold=kiosk_settings.eager_eot_threshold,
                keyterms=kiosk_settings.keyterms,
                event_loop=loop,  # Pass event loop for thread-safe callback scheduling
            )

            # Connect in thread pool to not block asyncio
            success = await loop.run_in_executor(None, session.connect)

            if success:
                self.sessions[session_id] = session
                logger.info(f"STT session created for {session_id}")
                return True
            else:
                logger.error(f"Failed to create STT session for {session_id}")
                return False

        except Exception as e:
            logger.error(f"Failed to create STT session: {e}", exc_info=True)
            if on_error:
                if asyncio.iscoroutinefunction(on_error):
                    await on_error(str(e))
                else:
                    on_error(str(e))
            return False

    async def stream_audio(self, session_id: str, audio_bytes: bytes):
        """Send audio data to the live connection."""
        session = self.sessions.get(session_id)
        if session:
            # Run in executor to not block asyncio
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, session.send_audio, audio_bytes)
        else:
            logger.warning(f"No session found for {session_id} when streaming audio")

    async def close_session(self, session_id: str):
        """Close the live connection."""
        session = self.sessions.pop(session_id, None)
        if session:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, session.close)
            logger.info(f"STT session closed for {session_id}")

    def pause_session(self, session_id: str):
        """Pause a specific STT session."""
        session = self.sessions.get(session_id)
        if session:
            session.pause()

    def resume_session(self, session_id: str):
        """Resume a specific STT session."""
        session = self.sessions.get(session_id)
        if session:
            session.resume()
