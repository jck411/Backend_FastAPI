"""Kiosk TTS settings schema for voice synthesis configuration."""

from typing import Literal

from pydantic import BaseModel, Field


# Available Deepgram Aura voice models
DEEPGRAM_VOICES = [
    "aura-asteria-en",  # Female, warm (default)
    "aura-luna-en",     # Female
    "aura-stella-en",   # Female
    "aura-athena-en",   # Female
    "aura-hera-en",     # Female
    "aura-orion-en",    # Male
    "aura-arcas-en",    # Male
    "aura-perseus-en",  # Male
    "aura-angus-en",    # Male
    "aura-orpheus-en",  # Male
    "aura-helios-en",   # Male
    "aura-zeus-en",     # Male
]

SAMPLE_RATES = [8000, 16000, 24000, 48000]


class KioskTtsSettings(BaseModel):
    """Settings for TTS in kiosk mode."""

    enabled: bool = Field(
        default=True,
        description="Whether TTS is enabled. If False, no audio will be generated.",
    )

    provider: Literal["deepgram"] = Field(
        default="deepgram",
        description="TTS provider. Currently only 'deepgram' is supported.",
    )

    model: str = Field(
        default="aura-asteria-en",
        description="Voice model to use for synthesis.",
    )

    sample_rate: int = Field(
        default=16000,
        description="Audio sample rate in Hz (8000, 16000, 24000, or 48000).",
    )


class KioskTtsSettingsUpdate(BaseModel):
    """Partial update schema - all fields optional."""

    enabled: bool | None = Field(default=None)
    provider: Literal["deepgram"] | None = Field(default=None)
    model: str | None = Field(default=None)
    sample_rate: int | None = Field(default=None, ge=8000, le=48000)


def get_default_tts_settings() -> KioskTtsSettings:
    """Return default TTS settings."""
    return KioskTtsSettings()
