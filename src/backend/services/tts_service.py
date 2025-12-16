import logging

import httpx

from backend.config import get_settings
from backend.services.kiosk_tts_settings import get_kiosk_tts_settings_service

logger = logging.getLogger(__name__)


class TTSService:
    """Service for Text-to-Speech generation using Deepgram Aura."""

    def __init__(self):
        settings = get_settings()
        api_key = settings.deepgram_api_key.get_secret_value() if settings.deepgram_api_key else None
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is not set")

        self.api_key = api_key
        self.base_url = "https://api.deepgram.com/v1/speak"

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio using Deepgram.
        Returns raw PCM audio bytes, or empty bytes if TTS is disabled.
        """
        # Get current TTS settings
        tts_settings = get_kiosk_tts_settings_service().get_settings()

        # Check if TTS is enabled
        if not tts_settings.enabled:
            logger.info("TTS is disabled, skipping synthesis")
            return b""

        try:
            params = {
                "model": tts_settings.model,
                "encoding": "linear16",
                "sample_rate": str(tts_settings.sample_rate),
                "container": "none",
            }

            headers = {
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {"text": text}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                audio_data = response.content
                logger.info(f"TTS synthesized {len(audio_data)} bytes for text: {text[:50]}...")
                return audio_data

        except Exception as e:
            logger.error(f"TTS Error: {e}")
            # Return empty bytes to avoid crashing the caller
            return b""
