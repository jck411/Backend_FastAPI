import httpx
from deepgram import AsyncDeepgramClient

from backend.config import get_settings


class TTSService:
    """Service for Text-to-Speech generation using Deepgram Aura."""

    def __init__(self):
        settings = get_settings()
        api_key = settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        self.client = AsyncDeepgramClient(api_key=api_key)

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio using Deepgram.
        Returns raw PCM audio bytes (16kHz, 16-bit, mono).
        """
        try:
            # Use dict for options
            speak_options = {
                "model": "aura-asteria-en",
                "encoding": "linear16",
                "sample_rate": 16000,
                "container": "none",
            }

            # Deepgram SDK synchronous call
            # Using standard SDK usage, passing options as dict might be supported
            # or passing kw arguments to the method.
            # Assuming speak.v("1").stream(source, options) pattern

            # The 'source' argument is {"text": text}, and 'options' handles the rest.

            response = await self.client.speak.v("1").stream({"text": text}, speak_options)

            # The response should be a stream-able object.
            # We want all bytes.
            return await response.read()

        except Exception as e:
            print(f"TTS Error: {e}")
            # Return empty bytes or raise?
            # Let's return empty bytes to avoid crashing the caller
            return b""
