"""Kiosk STT settings schema for Deepgram Flux configuration."""

from pydantic import BaseModel, Field


class KioskSttSettings(BaseModel):
    """Settings for Deepgram Flux STT in kiosk mode."""

    eot_threshold: float = Field(
        default=0.7,
        ge=0.5,
        le=0.9,
        description="End-of-turn confidence threshold (0.5-0.9). Higher = more reliable but slower.",
    )

    eot_timeout_ms: int = Field(
        default=5000,
        ge=500,
        le=10000,
        description="Maximum wait (ms) before forcing end-of-turn regardless of confidence.",
    )

    eager_eot_threshold: float | None = Field(
        default=None,
        ge=0.3,
        le=0.9,
        description="Optional eager end-of-turn threshold for speculative LLM generation.",
    )

    keyterms: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Words/phrases to boost recognition (max 100).",
    )


class KioskSttSettingsUpdate(BaseModel):
    """Partial update schema - all fields optional."""

    eot_threshold: float | None = Field(default=None, ge=0.5, le=0.9)
    eot_timeout_ms: int | None = Field(default=None, ge=500, le=10000)
    eager_eot_threshold: float | None = Field(default=None, ge=0.3, le=0.9)
    keyterms: list[str] | None = Field(default=None, max_length=100)
