"""Unified client settings schemas.

These schemas are shared across all clients (kiosk, svelte, cli).
Each client stores its own data but uses the same structure.
"""

from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# LLM Settings
# =============================================================================


class LlmSettings(BaseModel):
    """LLM configuration for a client."""

    model: str = Field(
        default="openai/gpt-4o-mini",
        description="OpenRouter model identifier",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="System prompt for the assistant",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature",
    )
    max_tokens: int = Field(
        default=500,
        ge=1,
        le=128000,
        description="Maximum tokens in response",
    )
    supports_tools: Optional[bool] = Field(
        default=None,
        description="Whether model supports tool calling",
    )
    # Kiosk-specific conversation mode
    conversation_mode: bool = Field(
        default=False,
        description="Enable continuous conversation mode",
    )
    conversation_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Timeout in conversation mode if no speech detected",
    )


class LlmSettingsUpdate(BaseModel):
    """Partial update for LLM settings."""

    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    supports_tools: Optional[bool] = None
    conversation_mode: Optional[bool] = None
    conversation_timeout_seconds: Optional[float] = Field(
        default=None, ge=1.0, le=60.0
    )


# =============================================================================
# STT Settings (Speech-to-Text)
# =============================================================================


class SttSettings(BaseModel):
    """STT configuration for a client."""

    eot_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="End-of-turn detection threshold",
    )
    eot_timeout_ms: int = Field(
        default=5000,
        ge=100,
        le=30000,
        description="End-of-turn timeout in milliseconds",
    )
    keyterms: list[str] = Field(
        default_factory=list,
        description="Keywords to boost recognition",
    )


class SttSettingsUpdate(BaseModel):
    """Partial update for STT settings."""

    eot_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    eot_timeout_ms: Optional[int] = Field(default=None, ge=100, le=30000)
    keyterms: Optional[list[str]] = None


# =============================================================================
# TTS Settings (Text-to-Speech)
# =============================================================================


class TtsSettings(BaseModel):
    """TTS configuration for a client."""

    enabled: bool = Field(
        default=True,
        description="Whether TTS is enabled",
    )
    provider: str = Field(
        default="openai",
        description="TTS provider: 'openai' is currently supported",
    )
    model: str = Field(
        default="tts-1",
        description="TTS model: 'tts-1' (faster) or 'tts-1-hd' (higher quality)",
    )
    voice: str = Field(
        default="alloy",
        description="OpenAI TTS voice: alloy, echo, fable, onyx, nova, shimmer",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=4.0,
        description="Speech speed multiplier (0.25 to 4.0)",
    )
    response_format: str = Field(
        default="pcm",
        description="Audio format: pcm, mp3, opus, aac, flac, wav",
    )
    sample_rate: int = Field(
        default=24000,
        ge=8000,
        le=48000,
        description="Audio sample rate in Hz (24000 for OpenAI)",
    )
    # Segmentation pipeline options
    use_segmentation: bool = Field(
        default=True,
        description="Whether to segment text at delimiters for faster initial audio",
    )
    delimiters: list[str] = Field(
        default_factory=lambda: ["\n", ". ", "? ", "! ", "* ", ", ", ": "],
        description="Delimiters to split text at for segmentation",
    )
    character_maximum: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Max chars before disabling segmentation",
    )


class TtsSettingsUpdate(BaseModel):
    """Partial update for TTS settings."""

    enabled: Optional[bool] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = Field(default=None, ge=0.25, le=4.0)
    response_format: Optional[str] = None
    sample_rate: Optional[int] = Field(default=None, ge=8000, le=48000)
    use_segmentation: Optional[bool] = None
    delimiters: Optional[list[str]] = None
    character_maximum: Optional[int] = Field(default=None, ge=0, le=500)


# =============================================================================
# MCP Server References
# =============================================================================



# =============================================================================
# Preset Filters
# =============================================================================


class MultiSelectFilter(BaseModel):
    """Filter with include/exclude lists."""

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class PresetModelFilters(BaseModel):
    """Filters saved with a preset."""

    inputModalities: Optional[MultiSelectFilter] = None
    outputModalities: Optional[MultiSelectFilter] = None
    minContext: Optional[int] = None
    minPromptPrice: Optional[float] = None
    maxPromptPrice: Optional[float] = None
    sort: Optional[str] = None
    series: Optional[MultiSelectFilter] = None
    providers: Optional[MultiSelectFilter] = None
    supportedParameters: Optional[MultiSelectFilter] = None
    moderation: Optional[MultiSelectFilter] = None


# =============================================================================
# Client Presets
# =============================================================================


class ClientPreset(BaseModel):
    """A preset configuration bundle (LLM settings only - MCP servers are separate)."""

    name: str = Field(description="Display name for the preset")
    llm: LlmSettings = Field(default_factory=LlmSettings)
    stt: Optional[SttSettings] = None
    tts: Optional[TtsSettings] = None
    model_filters: Optional[PresetModelFilters] = Field(
        default=None, description="Saved model explorer filters"
    )
    created_at: Optional[str] = Field(
        default=None, description="ISO timestamp when preset was created"
    )
    updated_at: Optional[str] = Field(
        default=None, description="ISO timestamp when preset was last modified"
    )


class ClientPresetUpdate(BaseModel):
    """Partial update for a preset."""

    name: Optional[str] = None
    llm: Optional[LlmSettingsUpdate] = None
    stt: Optional[SttSettingsUpdate] = None
    tts: Optional[TtsSettingsUpdate] = None
    model_filters: Optional[PresetModelFilters] = None


class ClientPresets(BaseModel):
    """Collection of presets for a client."""

    presets: list[ClientPreset] = Field(default_factory=list)
    active_index: Optional[int] = Field(
        default=None,
        description="Index of currently active preset",
    )


# =============================================================================
# UI Settings (for kiosk frontend behavior)
# =============================================================================


class UiSettings(BaseModel):
    """UI behavior settings for frontend clients."""

    idle_return_delay_ms: int = Field(
        default=10000,
        ge=1000,
        le=60000,
        description="Delay (ms) before returning to default screen after going IDLE",
    )


class UiSettingsUpdate(BaseModel):
    """Partial update for UI settings."""

    idle_return_delay_ms: Optional[int] = Field(default=None, ge=1000, le=60000)


# =============================================================================
# Complete Client Settings Bundle
# =============================================================================


class ClientSettings(BaseModel):
    """Complete settings bundle for a client (excludes MCP servers - they're global)."""

    llm: LlmSettings = Field(default_factory=LlmSettings)
    stt: Optional[SttSettings] = None
    tts: Optional[TtsSettings] = None
    ui: Optional[UiSettings] = None


__all__ = [
    "LlmSettings",
    "LlmSettingsUpdate",
    "SttSettings",
    "SttSettingsUpdate",
    "TtsSettings",
    "TtsSettingsUpdate",
    "UiSettings",
    "UiSettingsUpdate",
    "ClientPreset",
    "ClientPresetUpdate",
    "ClientPresets",
    "ClientSettings",
    "MultiSelectFilter",
    "PresetModelFilters",
]
