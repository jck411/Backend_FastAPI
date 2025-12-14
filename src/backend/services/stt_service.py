import asyncio
import json
import logging
from typing import Callable, Optional

from deepgram import DeepgramClient, AsyncDeepgramClient
from deepgram.core.events import EventType

from backend.config import get_settings

logger = logging.getLogger(__name__)


class STTService:
    """
    Manages Deepgram streaming STT sessions.
    """

    def __init__(self):
        settings = get_settings()
        api_key = settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        self.client = AsyncDeepgramClient(api_key=api_key)
        self.live_connections = {}  # session_id -> socket_client_instance
        self.session_tasks = {}      # session_id -> asyncio.Task (manager)
        self.stop_events = {}        # session_id -> asyncio.Event

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
            # Create a stop event for this session
            stop_event = asyncio.Event()
            self.stop_events[session_id] = stop_event

            # Start background task to manage connection
            task = asyncio.create_task(
                self._manage_deepgram_connection(session_id, stop_event, on_transcript, on_error)
            )
            self.session_tasks[session_id] = task

            logger.info(f"Started STT initialization task for {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to create STT session: {e}")
            if on_error:
                if asyncio.iscoroutinefunction(on_error):
                    await on_error(str(e))
                else:
                    on_error(str(e))
            return False

    async def _manage_deepgram_connection(
        self,
        session_id: str,
        stop_event: asyncio.Event,
        on_transcript: Callable[[str, bool], None],
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Background task to hold the Deepgram WebSocket connection open.
        """
        try:
            # Flattened options as required by this SDK version
            # Note: passing strings for boolean-like params as per type hints seen in inspection
            options = {
                "model": "nova-2",
                "language": "en-US",
                "smart_format": "true",
                "interim_results": "true",
                "vad_events": "true",
                "endpointing": "1000",
            }

            async with self.client.listen.v1.connect(**options) as dg_connection:
                self.live_connections[session_id] = dg_connection
                logger.info(f"Deepgram connected for {session_id}")

                # Register handlers
                async def handle_message(self, result, **kwargs):
                    # result is an object (V1SocketClientResponse)
                    # We need to parse it.
                    # Based on SDK, it emits parsed objects directly.
                    # result might be ListenV1ResultsEvent etc.

                    try:
                        # Check if it has 'channel' attribute (Transcript event)
                        if hasattr(result, 'channel'):
                            alternatives = result.channel.alternatives
                            if alternatives and len(alternatives) > 0:
                                transcript = alternatives[0].transcript
                                is_final = result.is_final

                                if transcript:
                                    if asyncio.iscoroutinefunction(on_transcript):
                                        await on_transcript(transcript, is_final)
                                    else:
                                        on_transcript(transcript, is_final)

                        # Handle errors if result is error type?
                        # The SDK uses EventType.ERROR for errors, passing exc.
                    except Exception as e:
                        logger.error(f"Error processing transcript: {e}")

                async def handle_error(self, error, **kwargs):
                    logger.error(f"Deepgram error for {session_id}: {error}")
                    if on_error:
                        if asyncio.iscoroutinefunction(on_error):
                            await on_error(str(error))
                        else:
                            on_error(str(error))

                # Register event listeners
                # Since dg_connection is AsyncV1SocketClient which is EventEmitterMixin
                # We typically use .on(EventType.MESSAGE, handler)
                # But handler signature in EventEmitterMixin?
                # SDK source says: await handler(self, event_data, **kwargs)
                dg_connection.on(EventType.MESSAGE, handle_message)
                dg_connection.on(EventType.ERROR, handle_error)

                # Start the listening loop in a separate task so we can also check stop_event
                listen_task = asyncio.create_task(dg_connection.start_listening())

                # Wait for stop signal
                await stop_event.wait()

                # Cleanup
                # Cancelling listen task (or it stops when connection closes, but we are closing connection by exiting context)
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"Deepgram connection loop failed for {session_id}: {e}")
            if on_error:
                if asyncio.iscoroutinefunction(on_error):
                    await on_error(str(e))
                else:
                    on_error(str(e))
        finally:
            # Cleanup global state
            self.live_connections.pop(session_id, None)
            self.stop_events.pop(session_id, None)
            self.session_tasks.pop(session_id, None)
            logger.info(f"Deepgram session ended for {session_id}")

    async def stream_audio(self, session_id: str, audio_bytes: bytes):
        """Send audio data to the live connection."""
        connection = self.live_connections.get(session_id)
        if connection:
            try:
                # Use send_media for binary data
                await connection.send_media(audio_bytes)
            except Exception as e:
                logger.error(f"Error streaming audio for {session_id}: {e}")

    async def close_session(self, session_id: str):
        """Close the live connection."""
        # Signal the background task to exit
        event = self.stop_events.get(session_id)
        if event:
            event.set()

        # Wait for task to finish?
        # Optional, but good for cleanup.
        task = self.session_tasks.get(session_id)
        if task:
            try:
                # wait briefly
                await asyncio.wait([task], timeout=2.0)
            except Exception:
                pass
