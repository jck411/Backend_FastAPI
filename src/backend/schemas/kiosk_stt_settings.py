"""Pydantic models for kiosk STT settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KioskSttSettingsPayload(BaseModel):
    """Wire payload for updating kiosk STT settings."""

    eot_timeout_ms: Optional[int] = Field(
        default=None,
        ge=500,
        le=10000,
        description="Max silence duration in ms before EndOfTurn (500-10000)"
    )
    eot_threshold: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=0.9,
        description="Confidence threshold for EndOfTurn detection (0.5-0.9)"
    )

    model_config = ConfigDict(extra="forbid")


class KioskSttSettingsResponse(BaseModel):
    """Response payload for kiosk STT settings."""

    eot_timeout_ms: int = Field(
        default=5000,
        ge=500,
        le=10000,
        description="Max silence duration in ms before EndOfTurn"
    )
    eot_threshold: float = Field(
        default=0.7,
        ge=0.5,
        le=0.9,
        description="Confidence threshold for EndOfTurn detection"
    )
    updated_at: Optional[datetime] = Field(default=None)

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "KioskSttSettingsPayload",
    "KioskSttSettingsResponse",
]
