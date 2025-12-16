"""Kiosk UI settings schema for frontend behavior configuration."""

from pydantic import BaseModel, Field


class KioskUiSettings(BaseModel):
    """Settings for kiosk frontend UI behavior."""

    idle_return_delay_ms: int = Field(
        default=10000,
        ge=1000,
        le=60000,
        description="Delay (ms) before returning to clock screen after going IDLE.",
    )


class KioskUiSettingsUpdate(BaseModel):
    """Partial update schema - all fields optional."""

    idle_return_delay_ms: int | None = Field(default=None, ge=1000, le=60000)
