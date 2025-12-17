import logging

import httpx

from backend.config import get_settings
from backend.services.kiosk_tts_settings import get_kiosk_tts_settings_service

logger = logging.getLogger(__name__)


class TTSService:
    """Service for Text-to-Speech generation using Deepgram Aura, ElevenLabs, OpenAI, or Unreal Speech."""

    def __init__(self):
        settings = get_settings()

        # Load Deepgram API key
        self.deepgram_api_key = (
            settings.deepgram_api_key.get_secret_value()
            if settings.deepgram_api_key else None
        )
        self.deepgram_base_url = "https://api.deepgram.com/v1/speak"

        # Load ElevenLabs API key
        self.elevenlabs_api_key = (
            settings.elevenlabs_api_key.get_secret_value()
            if settings.elevenlabs_api_key else None
        )
        self.elevenlabs_base_url = "https://api.elevenlabs.io/v1/text-to-speech"

        # Load OpenAI API key
        self.openai_api_key = (
            settings.openai_api_key.get_secret_value()
            if settings.openai_api_key else None
        )
        self.openai_base_url = "https://api.openai.com/v1/audio/speech"

        # Load Unreal Speech API key
        self.unrealspeech_api_key = (
            settings.unrealspeech_api_key.get_secret_value()
            if settings.unrealspeech_api_key else None
        )
        self.unrealspeech_base_url = "https://api.v8.unrealspeech.com/stream"

        # Log available providers
        providers = []
        if self.deepgram_api_key:
            providers.append("deepgram")
        if self.elevenlabs_api_key:
            providers.append("elevenlabs")
        if self.openai_api_key:
            providers.append("openai")
        if self.unrealspeech_api_key:
            providers.append("unrealspeech")

        if not providers:
            logger.warning("No TTS API keys configured. TTS will not be available.")
        else:
            logger.info(f"TTS providers available: {', '.join(providers)}")

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to audio using the configured provider.
        Returns raw PCM audio bytes, or empty bytes if TTS is disabled.
        """
        # Get current TTS settings
        tts_settings = get_kiosk_tts_settings_service().get_settings()

        # Check if TTS is enabled
        if not tts_settings.enabled:
            logger.info("TTS is disabled, skipping synthesis")
            return b""

        provider = tts_settings.provider

        if provider == "elevenlabs":
            return await self._synthesize_elevenlabs(text, tts_settings)
        elif provider == "openai":
            return await self._synthesize_openai(text, tts_settings)
        elif provider == "unrealspeech":
            return await self._synthesize_unrealspeech(text, tts_settings)
        else:
            # Default to Deepgram
            return await self._synthesize_deepgram(text, tts_settings)

    async def _synthesize_deepgram(self, text: str, tts_settings) -> bytes:
        """Synthesize using Deepgram Aura."""
        if not self.deepgram_api_key:
            logger.error("Deepgram API key not configured")
            return b""

        try:
            params = {
                "model": tts_settings.model,
                "encoding": "linear16",
                "sample_rate": str(tts_settings.sample_rate),
                "container": "none",
            }

            headers = {
                "Authorization": f"Token {self.deepgram_api_key}",
                "Content-Type": "application/json",
            }

            payload = {"text": text}

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.deepgram_base_url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                audio_data = response.content
                logger.info(f"Deepgram TTS synthesized {len(audio_data)} bytes for text: {text[:50]}...")
                return audio_data

        except Exception as e:
            logger.error(f"Deepgram TTS Error: {e}")
            return b""

    async def _synthesize_elevenlabs(self, text: str, tts_settings) -> bytes:
        """Synthesize using ElevenLabs."""
        if not self.elevenlabs_api_key:
            logger.error("ElevenLabs API key not configured")
            return b""

        try:
            voice_id = tts_settings.model  # For ElevenLabs, model stores the voice_id
            url = f"{self.elevenlabs_base_url}/{voice_id}"

            # Map sample rate to ElevenLabs output format
            # ElevenLabs supports: pcm_16000, pcm_22050, pcm_24000, pcm_44100
            sample_rate = tts_settings.sample_rate
            if sample_rate <= 16000:
                output_format = "pcm_16000"
            elif sample_rate <= 22050:
                output_format = "pcm_22050"
            elif sample_rate <= 24000:
                output_format = "pcm_24000"
            else:
                output_format = "pcm_44100"

            headers = {
                "xi-api-key": self.elevenlabs_api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",  # Higher quality model
                "voice_settings": {
                    "stability": 0.5,             # Lower = more expressive with natural pauses
                    "similarity_boost": 0.75,     # Default recommendation
                    "style": 0.0,                 # Style exaggeration off
                    "use_speaker_boost": True,    # Speaker boost for clarity
                },
                "speed": 0.9,                     # Slightly slower for natural pacing (0.7-1.2)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    params={"output_format": output_format},
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                audio_data = response.content
                logger.info(f"ElevenLabs TTS synthesized {len(audio_data)} bytes for text: {text[:50]}...")
                return audio_data

        except Exception as e:
            logger.error(f"ElevenLabs TTS Error: {e}")
            return b""

    async def _synthesize_openai(self, text: str, tts_settings) -> bytes:
        """Synthesize using OpenAI TTS."""
        if not self.openai_api_key:
            logger.error("OpenAI API key not configured")
            return b""

        try:
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": "tts-1",       # Use tts-1 for speed, tts-1-hd for quality
                "input": text,
                "voice": tts_settings.model,  # Voice name like "alloy", "nova", etc.
                "response_format": "pcm",     # Raw PCM for direct playback
                "speed": 1.0,                 # Normal speed (0.25 to 4.0)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.openai_base_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                audio_data = response.content
                logger.info(f"OpenAI TTS synthesized {len(audio_data)} bytes for text: {text[:50]}...")
                return audio_data

        except Exception as e:
            logger.error(f"OpenAI TTS Error: {e}")
            return b""

    async def _synthesize_unrealspeech(self, text: str, tts_settings) -> bytes:
        """Synthesize using Unreal Speech."""
        if not self.unrealspeech_api_key:
            logger.error("Unreal Speech API key not configured")
            return b""

        try:
            headers = {
                "Authorization": f"Bearer {self.unrealspeech_api_key}",
                "Content-Type": "application/json",
            }

            # v8 API payload (no Codec param for /stream)
            payload = {
                "Text": text,
                "VoiceId": tts_settings.model,  # v8 voices: Autumn, Sierra, Noah, etc.
                "Bitrate": "192k",
                "Speed": 0,
                "Pitch": 1.0,
            }

            logger.info(f"Unreal Speech request: VoiceId={tts_settings.model}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.unrealspeech_base_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                audio_data = response.content
                logger.info(f"Unreal Speech TTS synthesized {len(audio_data)} bytes for text: {text[:50]}...")
                return audio_data

        except httpx.HTTPStatusError as e:
            logger.error(f"Unreal Speech TTS HTTP Error: {e.response.status_code} - {e.response.text}")
            return b""
        except Exception as e:
            logger.error(f"Unreal Speech TTS Error: {e}")
            return b""
