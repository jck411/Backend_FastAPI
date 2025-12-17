"""Kiosk preset schema for quick configuration switching."""

from typing import Optional

from pydantic import BaseModel, Field


class KioskPreset(BaseModel):
    """A single kiosk preset configuration with LLM, STT, and TTS settings."""

    name: str = Field(description="Display name for the preset")

    # LLM Settings
    model: str = Field(description="OpenRouter model ID")
    system_prompt: str = Field(description="System prompt for the assistant")
    temperature: float = Field(ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(ge=50, le=4096, description="Max response tokens")

    # STT Settings
    eot_threshold: float = Field(
        default=0.7, ge=0.5, le=0.9, description="End-of-turn confidence threshold"
    )
    eot_timeout_ms: int = Field(
        default=5000, ge=500, le=10000, description="Max wait (ms) for end-of-turn"
    )
    keyterms: list[str] = Field(
        default_factory=list, description="Words/phrases to boost recognition"
    )

    # TTS Settings
    tts_enabled: bool = Field(default=True, description="Whether TTS is enabled")
    tts_model: str = Field(
        default="aura-asteria-en", description="TTS voice model"
    )
    tts_sample_rate: int = Field(
        default=16000, description="Audio sample rate in Hz"
    )


class KioskPresets(BaseModel):
    """Collection of kiosk presets."""

    presets: list[KioskPreset] = Field(
        default_factory=lambda: [
            KioskPreset(
                name="Concise",
                model="openai/gpt-4o-mini",
                system_prompt="You are a helpful voice assistant. Give brief, direct answers.",
                temperature=0.5,
                max_tokens=200,
            ),
            KioskPreset(
                name="Detailed",
                model="openai/gpt-4o-mini",
                system_prompt="You are a helpful voice assistant. Provide thorough, comprehensive answers.",
                temperature=0.7,
                max_tokens=800,
            ),
            KioskPreset(
                name="Creative",
                model="openai/gpt-4o-mini",
                system_prompt="You are a creative voice assistant. Be imaginative and engaging.",
                temperature=1.2,
                max_tokens=500,
            ),
            KioskPreset(
                name="Technical",
                model="anthropic/claude-3-haiku",
                system_prompt="You are a technical voice assistant. Be precise and accurate.",
                temperature=0.3,
                max_tokens=600,
            ),
        ],
        description="List of available presets (max 4)",
    )
    active_index: int = Field(
        default=0, ge=0, le=3, description="Currently active preset index"
    )


class KioskPresetUpdate(BaseModel):
    """Update a single preset."""

    index: int = Field(ge=0, le=3, description="Preset index to update")
    preset: KioskPreset = Field(description="New preset values")


class KioskPresetActivate(BaseModel):
    """Activate a preset by index."""

    index: int = Field(ge=0, le=3, description="Preset index to activate")
