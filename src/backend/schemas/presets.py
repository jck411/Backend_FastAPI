"""Pydantic models for configuration presets (model + settings + system prompt + MCP servers)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..chat.mcp_registry import MCPServerConfig
from ..schemas.model_settings import ModelHyperparameters, ProviderPreferences


class Suggestion(BaseModel):
    """A quick prompt suggestion button."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, description="Button label")
    text: str = Field(..., min_length=1, description="Prompt text to use")


class MultiSelectFilter(BaseModel):
    """Multi-select filter with include/exclude lists."""

    model_config = ConfigDict(extra="forbid")

    include: List[str] = Field(default_factory=list)
    exclude: List[str] = Field(default_factory=list)


class PresetModelFilters(BaseModel):
    """Model explorer filters to save in presets (excludes search)."""

    model_config = ConfigDict(extra="forbid")

    input_modalities: Optional[MultiSelectFilter] = Field(
        default=None, alias="inputModalities"
    )
    output_modalities: Optional[MultiSelectFilter] = Field(
        default=None, alias="outputModalities"
    )
    min_context: Optional[int] = Field(default=None, alias="minContext")
    min_prompt_price: Optional[float] = Field(default=None, alias="minPromptPrice")
    max_prompt_price: Optional[float] = Field(default=None, alias="maxPromptPrice")
    sort: Optional[Literal["newness", "price", "context"]] = None
    series: Optional[MultiSelectFilter] = None
    providers: Optional[MultiSelectFilter] = None
    supported_parameters: Optional[MultiSelectFilter] = Field(
        default=None, alias="supportedParameters"
    )
    moderation: Optional[MultiSelectFilter] = None


class PresetConfig(BaseModel):
    """A full snapshot of chat configuration saved under a name."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., min_length=1, description="Unique preset name")
    model: str = Field(..., description="Selected model id")
    provider: Optional[ProviderPreferences] = Field(
        default=None, description="Provider routing preferences"
    )
    parameters: Optional[ModelHyperparameters] = Field(
        default=None, description="Model hyperparameter overrides"
    )
    supports_tools: Optional[bool] = Field(
        default=None,
        description="Whether the selected model supports tool use",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Active system prompt",
    )
    mcp_servers: Optional[List[MCPServerConfig]] = Field(
        default=None,
        description="MCP server configurations (enabled state, disabled tools, env overrides, etc.)",
    )
    suggestions: Optional[List[Suggestion]] = Field(
        default=None,
        description="Quick prompt suggestions shown at the top of the screen",
    )
    model_filters: Optional[PresetModelFilters] = Field(
        default=None,
        alias="model_filters",
        description="Model explorer filter state (excludes search field)",
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
    has_filters: bool = False
    created_at: datetime
    updated_at: datetime


class PresetCreatePayload(BaseModel):
    """Payload to create a new preset from the current configuration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., min_length=1)
    model_filters: Optional[PresetModelFilters] = Field(
        default=None, alias="model_filters"
    )


class PresetSaveSnapshotPayload(BaseModel):
    """Payload to save a new snapshot over an existing preset (optional note)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    note: Optional[str] = Field(default=None)
    model_filters: Optional[PresetModelFilters] = Field(
        default=None, alias="model_filters"
    )


__all__ = [
    "Suggestion",
    "MultiSelectFilter",
    "PresetModelFilters",
    "PresetConfig",
    "PresetListItem",
    "PresetCreatePayload",
    "PresetSaveSnapshotPayload",
]
