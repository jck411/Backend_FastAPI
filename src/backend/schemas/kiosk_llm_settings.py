"""Pydantic schemas for kiosk LLM settings."""

from typing import Optional

from pydantic import BaseModel, Field


class KioskLlmSettings(BaseModel):
    """Kiosk LLM configuration settings."""

    model: str = Field(
        default="openai/gpt-4o-mini",
        description="OpenRouter model identifier",
    )
    system_prompt: Optional[str] = Field(
        default=(
            "You are a friendly and helpful voice assistant. "
            "Keep your responses concise and conversational since they will be spoken aloud. "
            "Avoid using markdown, bullet points, or other formatting that doesn't work well in speech."
        ),
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
        le=4096,
        description="Maximum tokens in response (keep low for voice)",
    )


class KioskLlmSettingsUpdate(BaseModel):
    """Partial update for kiosk LLM settings."""

    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=4096)


__all__ = ["KioskLlmSettings", "KioskLlmSettingsUpdate"]
