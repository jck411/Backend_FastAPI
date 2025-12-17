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

# Available ElevenLabs voices (voice_id: display_name)
# These are some popular pre-made voices; users can also use custom voice IDs
ELEVENLABS_VOICES = [
    "21m00Tcm4TlvDq8ikWAM",  # Rachel - warm, calm female
    "EXAVITQu4vr4xnSDxMaL",  # Bella - soft female
    "ErXwobaYiN019PkySvjV",  # Antoni - calm male
    "VR6AewLTigWG4xSOukaG",  # Arnold - strong male
    "pNInz6obpgDQGcFmaJgB",  # Adam - deep male
    "yoZ06aMxZJJ28mfd3POQ",  # Sam - versatile male
    "MF3mGyEYCl7XYWbV9V6O",  # Elli - young female
    "TxGEqnHWrfWFTfGW9XjX",  # Josh - deep male
    "XB0fDUnXU5powFXDhCwa",  # Charlotte - natural female
    "onwK4e9ZLuTAKqWW03F9",  # Daniel - British male
]

# Friendly display names for ElevenLabs voices
ELEVENLABS_VOICE_NAMES = {
    "21m00Tcm4TlvDq8ikWAM": "Rachel",
    "EXAVITQu4vr4xnSDxMaL": "Bella",
    "ErXwobaYiN019PkySvjV": "Antoni",
    "VR6AewLTigWG4xSOukaG": "Arnold",
    "pNInz6obpgDQGcFmaJgB": "Adam",
    "yoZ06aMxZJJ28mfd3POQ": "Sam",
    "MF3mGyEYCl7XYWbV9V6O": "Elli",
    "TxGEqnHWrfWFTfGW9XjX": "Josh",
    "XB0fDUnXU5powFXDhCwa": "Charlotte",
    "onwK4e9ZLuTAKqWW03F9": "Daniel",
}

# Available OpenAI TTS voices
OPENAI_VOICES = [
    "alloy",    # Neutral, balanced
    "ash",      # Warm
    "ballad",   # Soft
    "coral",    # Warm, friendly
    "echo",     # Neutral
    "fable",    # Expressive, British
    "nova",     # Warm, female
    "onyx",     # Deep, authoritative
    "sage",     # Calm
    "shimmer",  # Expressive, female
]

# Available Unreal Speech v8 voices
UNREALSPEECH_VOICES = [
    # American Female
    "Autumn",
    "Melody",
    "Hannah",
    "Emily",
    "Ivy",
    "Kaitlyn",
    "Luna",
    "Willow",
    "Lauren",
    "Sierra",
    # American Male
    "Noah",
    "Jasper",
    "Caleb",
    "Ronan",
    "Ethan",
    "Daniel",
    "Zane",
]

SAMPLE_RATES = [8000, 16000, 24000, 48000]


class KioskTtsSettings(BaseModel):
    """Settings for TTS in kiosk mode."""

    enabled: bool = Field(
        default=True,
        description="Whether TTS is enabled. If False, no audio will be generated.",
    )

    provider: Literal["deepgram", "elevenlabs", "openai", "unrealspeech"] = Field(
        default="deepgram",
        description="TTS provider. Options: 'deepgram', 'elevenlabs', 'openai', or 'unrealspeech'.",
    )

    model: str = Field(
        default="aura-asteria-en",
        description="Voice model/ID to use for synthesis.",
    )

    sample_rate: int = Field(
        default=16000,
        description="Audio sample rate in Hz (8000, 16000, 24000, or 48000).",
    )


class KioskTtsSettingsUpdate(BaseModel):
    """Partial update schema - all fields optional."""

    enabled: bool | None = Field(default=None)
    provider: Literal["deepgram", "elevenlabs", "openai", "unrealspeech"] | None = Field(default=None)
    model: str | None = Field(default=None)
    sample_rate: int | None = Field(default=None, ge=8000, le=48000)


def get_default_tts_settings() -> KioskTtsSettings:
    """Return default TTS settings."""
    return KioskTtsSettings()


