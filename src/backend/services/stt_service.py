import asyncio
import logging
import threading
import queue
from typing import Callable, Optional

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from backend.config import get_settings

logger = logging.getLogger(__name__)


class STTService:
    """
    Manages Deepgram streaming STT sessions using the v2 API.

    Uses the synchronous DeepgramClient.listen.v2.connect() pattern
    running in background threads, with thread-safe queues to bridge
    transcript callbacks back to async code.
    """

    def __init__(self):
        settings = get_settings()
        api_key = settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        self.api_key = api_key
        self.client = DeepgramClient(api_key=api_key)

        # Session management
        self.sessions = {}  # session_id -> DeepgramSession

    async def create_session(
        self,
        session_id: str,
        on_transcript: Callable[[str, bool], None],
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Start a new live transcription session.
        """
        try:
            # Create and start the session
            session = DeepgramSession(
                api_key=self.api_key,
                session_id=session_id,
                on_transcript=on_transcript,
                on_error=on_error,
            )
            session.connect()

            self.sessions[session_id] = session

            # Start background task to poll transcripts from the session
            asyncio.create_task(self._poll_transcripts(session_id))

            logger.info(f"Started STT session for {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create STT session: {e}")
            if on_error:
                if asyncio.iscoroutinefunction(on_error):
                    await on_error(str(e))
                else:
                    on_error(str(e))
            return False

    async def _poll_transcripts(self, session_id: str):
        """Poll transcript queue and invoke callbacks."""
        session = self.sessions.get(session_id)
        if not session:
            return

        while session_id in self.sessions and session.is_running:
            try:
                # Check for transcripts with timeout
                transcript, is_final = session.get_transcript(timeout=0.1)
                if transcript:
                    if asyncio.iscoroutinefunction(session.on_transcript):
                        await session.on_transcript(transcript, is_final)
                    else:
                        session.on_transcript(transcript, is_final)
            except queue.Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error polling transcripts: {e}")
                await asyncio.sleep(0.1)

    async def stream_audio(self, session_id: str, audio_bytes: bytes):
        """Send audio data to the live connection."""
        session = self.sessions.get(session_id)
        if session and session.is_running:
            session.send_audio(audio_bytes)
        else:
            logger.warning(f"Cannot stream audio for {session_id}: session={session is not None}, running={session.is_running if session else False}")

    async def close_session(self, session_id: str):
        """Close the live connection."""
        session = self.sessions.pop(session_id, None)
        if session:
            session.close()
            logger.info(f"Closed STT session for {session_id}")


class DeepgramSession:
    """
    A single Deepgram transcription session running in a background thread.

    Uses the working pattern from deepgram-voice-transcriber:
    - DeepgramClient.listen.v2.connect() context manager
    - Background thread for start_listening()
    - Thread-safe queue for transcripts
    """

    def __init__(
        self,
        api_key: str,
        session_id: str,
        on_transcript: Callable[[str, bool], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.session_id = session_id
        self.on_transcript = on_transcript
        self.on_error = on_error

        self._client = DeepgramClient(api_key=api_key)
        self._context_manager = None
        self._socket = None
        self._ready = threading.Event()
        self._running = False
        self._listening_thread = None

        # Thread-safe queue for transcripts (thread -> async)
        self._transcript_queue = queue.Queue()

    @property
    def is_running(self) -> bool:
        return self._running and self._ready.is_set()

    def _handle_message(self, result) -> None:
        """Handle transcript messages from Deepgram (v2 Flux API format)."""
        try:
            # v2 Flux API returns result.transcript directly (NOT result.channel.alternatives)
            transcript = getattr(result, "transcript", "")
            if transcript:
                event = getattr(result, "event", None)
                is_final = event == "EndOfTurn"
                self._transcript_queue.put((transcript, is_final))
                logger.debug(f"Transcript ({self.session_id}): {transcript} (Final: {is_final})")
        except Exception as e:
            logger.error(f"Error processing transcript: {e}")

    def _handle_error(self, error) -> None:
        """Handle connection errors."""
        logger.error(f"Deepgram error for {self.session_id}: {error}")
        if self.on_error:
            # Can't easily call async from thread, so just log
            logger.error(f"STT Error: {error}")

    def _on_open(self, _) -> None:
        """Handle connection open."""
        logger.info(f"Deepgram connected for {self.session_id}")
        self._ready.set()

    def _on_close(self, _) -> None:
        """Handle connection close."""
        logger.info(f"Deepgram disconnected for {self.session_id}")
        self._ready.clear()

    def connect(self) -> None:
        """Connect to Deepgram in a background thread."""
        # EXACT params from working deepgram-voice-transcriber
        params = {
            "model": "flux-general-en",
            "encoding": "linear16",
            "sample_rate": "16000",
            "eot_threshold": "0.7",
            "eot_timeout_ms": "5000",
        }

        logger.info(f"Connecting to Deepgram for {self.session_id} with params: {params}")

        # Use v2 API - this returns a context manager
        self._context_manager = self._client.listen.v2.connect(**params)
        # Enter the context manager to get the actual socket client
        self._socket = self._context_manager.__enter__()

        # Register event handlers on the socket client
        self._socket.on(EventType.OPEN, self._on_open)
        self._socket.on(EventType.MESSAGE, self._handle_message)
        self._socket.on(EventType.ERROR, self._handle_error)
        self._socket.on(EventType.CLOSE, self._on_close)

        # Start listening in background thread
        def listen_loop():
            try:
                self._socket.start_listening()
            except Exception as e:
                if self._running:
                    self._handle_error(e)

        self._running = True
        self._listening_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listening_thread.start()

        # Wait for connection to be ready
        if not self._ready.wait(timeout=10.0):
            logger.error(f"Timeout waiting for Deepgram connection for {self.session_id}")

    def send_audio(self, data: bytes) -> None:
        """Send audio data to Deepgram."""
        if self._socket and self._ready.is_set():
            try:
                self._socket.send_media(data)
            except Exception as e:
                logger.error(f"Error sending audio for {self.session_id}: {e}")
        else:
            logger.warning(f"Cannot send audio: socket={self._socket is not None}, ready={self._ready.is_set()}")

    def get_transcript(self, timeout: float = 0.1) -> tuple[str, bool]:
        """Get next transcript from queue (thread-safe)."""
        return self._transcript_queue.get(timeout=timeout)

    def close(self) -> None:
        """Close the connection."""
        self._running = False
        if self._context_manager:
            try:
                self._context_manager.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing connection for {self.session_id}: {e}")
            self._context_manager = None
            self._socket = None
