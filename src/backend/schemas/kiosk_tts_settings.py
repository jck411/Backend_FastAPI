"""Kiosk TTS settings schema for voice synthesis configuration."""

from typing import Optional

from pydantic import BaseModel, Field


# OpenAI TTS voice options
OPENAI_TTS_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

# OpenAI TTS model options
OPENAI_TTS_MODELS = ["tts-1", "tts-1-hd"]

# Response format options and their sample rates
OPENAI_TTS_FORMATS = {
    "pcm": 24000,
    "mp3": 24000,
    "opus": 24000,
    "aac": 24000,
    "flac": 24000,
    "wav": 24000,
}

# Default delimiters for text segmentation
DEFAULT_DELIMITERS = ["\n", ". ", "? ", "! ", "* ", ", ", ": "]

# Available TTS voices (for API endpoint)
TTS_VOICES: list[str] = OPENAI_TTS_VOICES


class KioskTtsSettings(BaseModel):
    """Settings for TTS in kiosk mode."""

    enabled: bool = Field(
        default=True,
        description="Whether TTS is enabled.",
    )

    provider: str = Field(
        default="openai",
        description="TTS provider. Currently only 'openai' is supported.",
    )

    # OpenAI TTS options
    voice: str = Field(
        default="alloy",
        description="OpenAI TTS voice: alloy, echo, fable, onyx, nova, shimmer.",
    )

    model: str = Field(
        default="tts-1",
        description="OpenAI TTS model: tts-1 (faster) or tts-1-hd (higher quality).",
    )

    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=4.0,
        description="Speech speed multiplier (0.25 to 4.0).",
    )

    response_format: str = Field(
        default="pcm",
        description="Audio format: pcm, mp3, opus, aac, flac, wav.",
    )

    # Segmentation pipeline options
    use_segmentation: bool = Field(
        default=True,
        description="Whether to segment text at delimiters for faster initial audio.",
    )

    delimiters: list[str] = Field(
        default_factory=lambda: DEFAULT_DELIMITERS.copy(),
        description="Delimiters to split text at for segmentation.",
    )

    character_maximum: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Max chars before disabling segmentation (remaining text as single chunk).",
    )

    sample_rate: int = Field(
        default=24000,
        description="Audio sample rate in Hz. Derived from response_format.",
    )


class KioskTtsSettingsUpdate(BaseModel):
    """Partial update schema - all fields optional."""

    enabled: bool | None = Field(default=None)
    provider: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    model: str | None = Field(default=None)
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
    response_format: str | None = Field(default=None)
    use_segmentation: bool | None = Field(default=None)
    delimiters: list[str] | None = Field(default=None)
    character_maximum: int | None = Field(default=None, ge=0, le=500)
    sample_rate: int | None = Field(default=None)


def get_default_tts_settings() -> KioskTtsSettings:
    """Return default TTS settings."""
    return KioskTtsSettings()
