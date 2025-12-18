import logging
from typing import AsyncIterator, Optional, Tuple

import httpx

from backend.config import get_settings
from backend.services.kiosk_tts_settings import get_kiosk_tts_settings_service

logger = logging.getLogger(__name__)


class TTSService:
    """
    Service for Text-to-Speech generation.

    Supports multiple TTS providers: ElevenLabs, OpenAI, Unreal Speech, Deepgram.
    Uses a singleton httpx.AsyncClient for connection pooling across requests.

    The service is designed for streaming TTS:
    - stream_synthesize() returns an async iterator of audio chunks
    - Chunks are yielded as they arrive from the TTS provider
    - First chunk is yielded immediately for minimal time-to-first-audio
    """

    # Singleton HTTP client for connection pooling
    _http_client: Optional[httpx.AsyncClient] = None

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

    @classmethod
    def get_http_client(cls) -> httpx.AsyncClient:
        """Get singleton HTTP client for connection pooling."""
        if cls._http_client is None:
            cls._http_client = httpx.AsyncClient(timeout=30.0)
            logger.info("Created singleton httpx.AsyncClient for TTS")
        return cls._http_client

    @classmethod
    async def close_http_client(cls) -> None:
        """Close the singleton HTTP client. Call on app shutdown."""
        if cls._http_client is not None:
            await cls._http_client.aclose()
            cls._http_client = None
            logger.info("Closed TTS HTTP client")

    async def synthesize(self, text: str) -> Tuple[bytes, int]:
        """
        Synthesize text to audio using the configured provider.
        Returns (raw PCM audio bytes, sample_rate), or (empty bytes, 0) if TTS is disabled.
        """
        # Get current TTS settings
        tts_settings = get_kiosk_tts_settings_service().get_settings()

        # Check if TTS is enabled
        if not tts_settings.enabled:
            logger.info("TTS is disabled, skipping synthesis")
            return b"", 0

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

    async def stream_synthesize(self, text: str) -> Tuple[int, AsyncIterator[bytes]]:
        """
        Streaming-friendly TTS. Returns sample_rate and an async iterator of audio chunks.
        All providers use true streaming where supported, with chunk buffering for efficiency.
        """
        tts_settings = get_kiosk_tts_settings_service().get_settings()

        async def _empty_iter():
            if False:
                yield b""

        if not tts_settings.enabled:
            logger.info("TTS is disabled, skipping streaming synthesis")
            return 0, _empty_iter()

        provider = tts_settings.provider

        if provider == "openai":
            sample_rate, stream = await self._stream_openai(text, tts_settings)
        elif provider == "unrealspeech":
            sample_rate, stream = await self._stream_unrealspeech(text, tts_settings)
        elif provider == "elevenlabs":
            sample_rate, stream = await self._stream_elevenlabs(text, tts_settings)
        else:
            # Default to Deepgram
            sample_rate, stream = await self._stream_deepgram(text, tts_settings)

        # Wrap all streams with buffering for more efficient websocket transmission
        return sample_rate, self._buffered_stream(stream)

    async def _buffered_stream(
        self,
        stream: AsyncIterator[bytes],
        target_size: int = 16 * 1024  # 16KB default
    ) -> AsyncIterator[bytes]:
        """
        Buffer small chunks into larger ones for more efficient websocket transmission.
        IMPORTANT: Yields the first chunk immediately (if > 0 bytes) to start audio playback ASAP.
        ENSURES: All yielded chunks are multiples of 2 bytes for 16-bit PCM alignment.
        """
        buffer = bytearray()
        first_chunk_sent = False

        async for chunk in stream:
            buffer.extend(chunk)

            # If we haven't sent first chunk, try to send it ASAP
            # But must be at least 2 bytes for 16-bit PCM and event length
            if not first_chunk_sent and len(buffer) >= 2:
                # Send whatever we have, but rounded down to even number
                send_len = len(buffer) - (len(buffer) % 2)
                if send_len > 0:
                    yield bytes(buffer[:send_len])
                    buffer = buffer[send_len:]
                    first_chunk_sent = True

            # Regular buffering
            while len(buffer) >= target_size:
                # target_size is even (16*1024), so this stays aligned
                yield bytes(buffer[:target_size])
                buffer = buffer[target_size:]

        # yielding any remaining bytes
        if buffer:
            # Only yield if we have even number of bytes, or pad?
            # Usually end of stream is fine, but for safety in frontend:
            # If odd, we could pad with 0 or just drop the last byte.
            # Dropping last byte of PCM stream is safer than misalignment.
            if len(buffer) % 2 != 0:
                logger.warning(f"Dropping 1 byte from end of TTS stream to maintain 16-bit alignment")
                buffer = buffer[:-1]

            if buffer:
                yield bytes(buffer)

    async def _stream_fallback(self, text: str, tts_settings, synthesize_fn) -> Tuple[int, AsyncIterator[bytes]]:
        """Fallback streaming by chunking a full synthesis response."""
        audio_data, sample_rate = await synthesize_fn(text, tts_settings)

        async def _iter_from_bytes(data: bytes, chunk_size: int = 32 * 1024):
            for i in range(0, len(data), chunk_size):
                yield data[i:i + chunk_size]

        return sample_rate, _iter_from_bytes(audio_data)

    async def _synthesize_deepgram(self, text: str, tts_settings) -> Tuple[bytes, int]:
        """Synthesize using Deepgram Aura."""
        if not self.deepgram_api_key:
            logger.error("Deepgram API key not configured")
            return b"", 0

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
                return audio_data, int(tts_settings.sample_rate)

        except Exception as e:
            logger.error(f"Deepgram TTS Error: {e}")
            return b"", 0

    async def _stream_deepgram(self, text: str, tts_settings) -> Tuple[int, AsyncIterator[bytes]]:
        """Stream Deepgram Aura TTS audio."""
        if not self.deepgram_api_key:
            logger.error("Deepgram API key not configured for streaming")
            return 0, self._empty_iter()

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

        client = self.get_http_client()

        async def _stream():
            try:
                async with client.stream(
                    "POST",
                    self.deepgram_base_url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            except Exception as exc:
                logger.error(f"Deepgram streaming TTS error: {exc}")

        return int(tts_settings.sample_rate), _stream()

    async def _synthesize_elevenlabs(self, text: str, tts_settings) -> Tuple[bytes, int]:
        """Synthesize using ElevenLabs."""
        if not self.elevenlabs_api_key:
            logger.error("ElevenLabs API key not configured")
            return b"", 0

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
                return audio_data, int(sample_rate)

        except Exception as e:
            logger.error(f"ElevenLabs TTS Error: {e}")
            return b"", 0

    async def _stream_elevenlabs(self, text: str, tts_settings) -> Tuple[int, AsyncIterator[bytes]]:
        """Stream ElevenLabs TTS audio."""
        if not self.elevenlabs_api_key:
            logger.error("ElevenLabs API key not configured for streaming")
            return 0, self._empty_iter()

        voice_id = tts_settings.model
        # Use the streaming endpoint
        url = f"{self.elevenlabs_base_url}/{voice_id}/stream"

        # Map sample rate to ElevenLabs output format
        sample_rate = tts_settings.sample_rate
        if sample_rate <= 16000:
            output_format = "pcm_16000"
            actual_rate = 16000
        elif sample_rate <= 22050:
            output_format = "pcm_22050"
            actual_rate = 22050
        elif sample_rate <= 24000:
            output_format = "pcm_24000"
            actual_rate = 24000
        else:
            output_format = "pcm_44100"
            actual_rate = 44100

        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
            "speed": 0.9,
        }

        client = self.get_http_client()

        async def _stream():
            try:
                async with client.stream(
                    "POST",
                    url,
                    params={"output_format": output_format},
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            except Exception as exc:
                logger.error(f"ElevenLabs streaming TTS error: {exc}")

        return actual_rate, _stream()

    async def _synthesize_openai(self, text: str, tts_settings) -> Tuple[bytes, int]:
        """Synthesize using OpenAI TTS."""
        if not self.openai_api_key:
            logger.error("OpenAI API key not configured")
            return b"", 0

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
                return audio_data, 24000  # OpenAI PCM is fixed at 24kHz

        except Exception as e:
            logger.error(f"OpenAI TTS Error: {e}")
            return b"", 0

    async def _stream_openai(self, text: str, tts_settings) -> Tuple[int, AsyncIterator[bytes]]:
        """Stream OpenAI TTS audio when available."""
        if not self.openai_api_key:
            logger.error("OpenAI API key not configured for streaming")
            return 0, self._empty_iter()

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "tts-1",
            "input": text,
            "voice": tts_settings.model,
            "response_format": "pcm",
            "speed": 1.0,
        }

        client = self.get_http_client()

        async def _stream():
            try:
                async with client.stream(
                    "POST",
                    self.openai_base_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            except Exception as exc:
                logger.error(f"OpenAI streaming TTS error: {exc}")
                return

        return 24000, _stream()

    async def _synthesize_unrealspeech(self, text: str, tts_settings) -> Tuple[bytes, int]:
        """Synthesize using Unreal Speech."""
        if not self.unrealspeech_api_key:
            logger.error("Unreal Speech API key not configured")
            return b"", 0

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
                "Codec": "pcm_s16le",
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
                return audio_data, 22050  # Unreal Speech v8 stream is 22.05kHz

        except httpx.HTTPStatusError as e:
            logger.error(f"Unreal Speech TTS HTTP Error: {e.response.status_code} - {e.response.text}")
            return b"", 0
        except Exception as e:
            logger.error(f"Unreal Speech TTS Error: {e}")
            return b"", 0

    async def _stream_unrealspeech(self, text: str, tts_settings) -> Tuple[int, AsyncIterator[bytes]]:
        """Stream Unreal Speech audio."""
        if not self.unrealspeech_api_key:
            logger.error("Unreal Speech API key not configured for streaming")
            return 0, self._empty_iter()

        headers = {
            "Authorization": f"Bearer {self.unrealspeech_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "Text": text,
            "VoiceId": tts_settings.model,
            "Bitrate": "192k",
            "Speed": 0,
            "Pitch": 1.0,
            "Codec": "pcm_s16le",
        }

        client = self.get_http_client()

        async def _stream():
            try:
                async with client.stream(
                    "POST",
                    self.unrealspeech_base_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            except Exception as exc:
                logger.error(f"Unreal Speech streaming TTS error: {exc}")
                return

        return 22050, _stream()

    async def _empty_iter(self) -> AsyncIterator[bytes]:
        if False:
            yield b""
