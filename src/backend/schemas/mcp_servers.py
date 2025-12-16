"""Schemas for MCP server settings API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class MCPServerToolDefinition(BaseModel):
    """Serializable per-tool override definition."""

    model_config = ConfigDict(extra="forbid")

    contexts: list[str] | None = Field(default=None)


class MCPServerDefinition(BaseModel):
    """Serializable MCP server definition used for persistence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    enabled: bool = Field(default=True)
    module: str | None = None
    command: list[str] | None = None
    cwd: Path | None = None
    env: dict[str, str] = Field(default_factory=dict)
    tool_prefix: str | None = None
    disabled_tools: set[str] | None = Field(default=None)
    contexts: list[str] = Field(default_factory=list)
    tool_overrides: dict[str, MCPServerToolDefinition] = Field(default_factory=dict)
    kiosk_enabled: bool = Field(default=False)
    frontend_enabled: bool = Field(default=True)


class MCPServerCollectionPayload(BaseModel):
    """Payload for replacing the full server list."""

    servers: list[MCPServerDefinition]


class MCPServerUpdatePayload(BaseModel):
    """Partial update for a single server."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    disabled_tools: list[str] | None = None
    module: str | None = None
    command: list[str] | None = None
    cwd: Path | None = None
    env: dict[str, str] | None = None
    tool_prefix: str | None = None
    contexts: list[str] | None = None
    tool_overrides: dict[str, MCPServerToolDefinition] | None = None
    kiosk_enabled: bool | None = None
    frontend_enabled: bool | None = None


class MCPServerToolStatus(BaseModel):
    name: str
    qualified_name: str
    enabled: bool = True


class MCPServerStatus(BaseModel):
    """Combined config + runtime status for an MCP server."""

    id: str
    enabled: bool
    connected: bool
    module: str | None = None
    command: list[str] | None = None
    cwd: Path | None = None
    env: dict[str, str] = Field(default_factory=dict)
    tool_prefix: str | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    tool_count: int = 0
    tools: list[MCPServerToolStatus] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    tool_overrides: dict[str, MCPServerToolDefinition] = Field(default_factory=dict)
    kiosk_enabled: bool = Field(default=False)
    frontend_enabled: bool = Field(default=True)


class MCPServerStatusResponse(BaseModel):
    """Response payload containing current server configurations."""

    servers: list[MCPServerStatus]
    updated_at: datetime | None = None


__all__ = [
    "MCPServerCollectionPayload",
    "MCPServerDefinition",
    "MCPServerStatus",
    "MCPServerStatusResponse",
    "MCPServerToolStatus",
    "MCPServerUpdatePayload",
    "MCPServerToolDefinition",
]
