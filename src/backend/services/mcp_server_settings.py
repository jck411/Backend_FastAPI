"""Service for persisting MCP server settings and exposing runtime updates."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..chat.mcp_registry import MCPServerConfig, load_server_configs

logger = logging.getLogger(__name__)


def _config_to_payload(config: MCPServerConfig) -> dict[str, Any]:
    """Convert an MCP server config into a JSON-serialisable payload."""

    data = config.model_dump(mode="json", exclude_none=True)
    if config.disabled_tools:
        data["disabled_tools"] = sorted(config.disabled_tools)
    if config.tool_overrides:
        data["tool_overrides"] = {
            name: override.model_dump(mode="json", exclude_none=True)
            for name, override in sorted(config.tool_overrides.items())
        }
    if config.contexts:
        data["contexts"] = list(config.contexts)
    return data


class MCPServerSettingsService:
    """Manage persisted MCP server definitions used by the aggregator."""

    def __init__(
        self,
        path: Path,
        *,
        fallback: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        self._path = path
        self._fallback = [dict(item) for item in fallback or []]
        self._lock = asyncio.Lock()
        self._configs: list[MCPServerConfig] = []
        self._updated_at: datetime | None = None
        self._loaded = False  # Lazy load flag

    def _load_from_disk(self) -> None:
        if self._loaded:
            return

        try:
            configs = load_server_configs(self._path, fallback=self._fallback)
        except ValueError as exc:
            logger.warning(
                "Failed to load MCP server configs from %s: %s", self._path, exc
            )
            configs = [
                MCPServerConfig.model_validate(item) for item in self._fallback
            ]

        self._configs = [cfg.model_copy(deep=True) for cfg in configs]
        try:
            stat = self._path.stat()
            self._updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except FileNotFoundError:
            self._updated_at = None

        self._loaded = True

    def _save_to_disk(self) -> None:
        payload = {"servers": [_config_to_payload(cfg) for cfg in self._configs]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        self._path.write_text(serialized + "\n", encoding="utf-8")
        self._updated_at = datetime.now(timezone.utc)

    async def get_configs(self) -> list[MCPServerConfig]:
        async with self._lock:
            self._load_from_disk()  # Lazy load on first access
            return [cfg.model_copy(deep=True) for cfg in self._configs]

    async def replace_configs(
        self, configs: Sequence[MCPServerConfig]
    ) -> list[MCPServerConfig]:
        async with self._lock:
            seen: set[str] = set()
            ordered: list[MCPServerConfig] = []
            for cfg in configs:
                if cfg.id in seen:
                    raise ValueError(f"Duplicate MCP server id: {cfg.id}")
                seen.add(cfg.id)
                ordered.append(cfg)
            self._configs = [cfg.model_copy(deep=True) for cfg in ordered]
            self._save_to_disk()
            return [cfg.model_copy(deep=True) for cfg in self._configs]

    async def patch_server(
        self,
        server_id: str,
        *,
        enabled: bool | None = None,
        disabled_tools: Iterable[str] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> MCPServerConfig:
        """Apply targeted updates to an individual server configuration."""

        overrides = overrides or {}
        patch_data = dict(overrides)
        if enabled is not None:
            patch_data["enabled"] = enabled
        if disabled_tools is not None:
            patch_data["disabled_tools"] = list(disabled_tools)

        if "id" in patch_data and patch_data["id"] != server_id:
            raise ValueError("Server id cannot be changed")

        async with self._lock:
            self._load_from_disk()  # Lazy load on first access
            for index, existing in enumerate(self._configs):
                if existing.id != server_id:
                    continue

                data = existing.model_dump(exclude_none=False)
                data.update(patch_data)
                updated = MCPServerConfig.model_validate(data)
                self._configs[index] = updated
                self._save_to_disk()
                return updated.model_copy(deep=True)

        raise KeyError(f"Unknown MCP server id: {server_id}")

    async def toggle_tool(
        self, server_id: str, tool_name: str, *, enabled: bool
    ) -> MCPServerConfig:
        async with self._lock:
            self._load_from_disk()  # Lazy load on first access
            for index, existing in enumerate(self._configs):
                if existing.id != server_id:
                    continue

                disabled = set(existing.disabled_tools or set())
                if enabled:
                    disabled.discard(tool_name)
                else:
                    disabled.add(tool_name)

                data = existing.model_dump(exclude_none=False)
                data["disabled_tools"] = sorted(disabled) if disabled else None
                updated = MCPServerConfig.model_validate(data)
                self._configs[index] = updated
                self._save_to_disk()
                return updated.model_copy(deep=True)

        raise KeyError(f"Unknown MCP server id: {server_id}")

    async def updated_at(self) -> datetime | None:
        async with self._lock:
            return self._updated_at


__all__ = ["MCPServerSettingsService"]
