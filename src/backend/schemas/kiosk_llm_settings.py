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
        default="You are a helpful assistant who replies succinctly.",
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
    conversation_mode: bool = Field(
        default=False,
        description="Enable continuous conversation mode (mic re-opens after reply)",
    )
    conversation_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Timeout to close session in conversation mode if no speech detected",
    )


class KioskLlmSettingsUpdate(BaseModel):
    """Partial update for kiosk LLM settings."""

    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=4096)
    conversation_mode: Optional[bool] = None
    conversation_timeout_seconds: Optional[float] = Field(default=None, ge=1.0, le=60.0)


__all__ = ["KioskLlmSettings", "KioskLlmSettingsUpdate"]
