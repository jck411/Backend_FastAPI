"""Pydantic models for configuration presets (model + settings + system prompt + MCP servers)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..chat.mcp_registry import MCPServerConfig
from ..schemas.model_settings import ModelHyperparameters, ProviderPreferences


class PresetConfig(BaseModel):
    """A full snapshot of chat configuration saved under a name."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Unique preset name")
    model: str = Field(..., description="Selected model id")
    provider: Optional[ProviderPreferences] = Field(
        default=None, description="Provider routing preferences"
    )
    parameters: Optional[ModelHyperparameters] = Field(
        default=None, description="Model hyperparameter overrides"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Active system prompt",
    )
    mcp_servers: Optional[List[MCPServerConfig]] = Field(
        default=None,
        description="MCP server configurations (enabled state, disabled tools, env overrides, etc.)",
    )
    is_default: bool = Field(
        default=False,
        description="Whether this preset is the default preset to load on startup",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp",
    )


class PresetListItem(BaseModel):
    """Lightweight listing item for presets."""

    model_config = ConfigDict(extra="forbid")

    name: str
    model: str
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class PresetCreatePayload(BaseModel):
    """Payload to create a new preset from the current configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)


class PresetSaveSnapshotPayload(BaseModel):
    """Payload to save a new snapshot over an existing preset (optional note)."""

    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None)


__all__ = [
    "PresetConfig",
    "PresetListItem",
    "PresetCreatePayload",
    "PresetSaveSnapshotPayload",
]
