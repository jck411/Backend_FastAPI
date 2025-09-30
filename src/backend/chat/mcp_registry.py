"""Configuration loader and aggregator for MCP tool servers."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from collections import Counter
from typing import Any, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from mcp.types import CallToolResult, Tool

from .mcp_client import MCPToolClient

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Declarative description of how to launch an MCP server."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Stable identifier for the server")
    enabled: bool = Field(default=True, description="Whether the server should be launched")
    module: str | None = Field(
        default=None,
        description="Python module path to launch via `python -m`",
    )
    command: list[str] | None = Field(
        default=None,
        description="Explicit command (argv) to execute for the server",
    )
    cwd: Path | None = Field(
        default=None,
        description="Working directory for the launched process",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variable overrides for the server",
    )
    tool_prefix: str | None = Field(
        default=None,
        description="Optional prefix applied to exposed tool names to keep them unique",
    )
    disabled_tools: set[str] | None = Field(
        default=None,
        description="Optional set of tool names to hide without disabling the server",
    )

    @field_validator("command", mode="before")
    @classmethod
    def _normalize_command(cls, value: Any) -> Any:
        if isinstance(value, str):
            return shlex.split(value)
        return value

    @field_validator("disabled_tools", mode="before")
    @classmethod
    def _normalize_disabled_tools(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (list, tuple, set)):
            return {str(item) for item in value if isinstance(item, str)}
        if isinstance(value, str):
            return {value}
        raise TypeError("disabled_tools must be a sequence of strings or null")

    @model_validator(mode="after")
    def _require_launch_target(self) -> "MCPServerConfig":
        if (self.module is None) == (self.command is None):
            message = "Define exactly one of 'module' or 'command' for MCP server '%s'"
            raise ValueError(message % self.id)
        return self

    def resolved_cwd(self, base: Path | None) -> Path | None:
        """Return an absolute working directory for the server."""

        if self.cwd is None:
            return base
        if self.cwd.is_absolute() or base is None:
            return self.cwd
        return (base / self.cwd).resolve()

    def qualify_tool_name(self, name: str) -> str:
        """Return a unique tool name using the configured prefix or id."""

        prefix = self.tool_prefix or self.id
        if not prefix:
            return name
        return f"{prefix}__{name}"


def load_server_configs(path: Path, *, fallback: Sequence[dict[str, Any]] | None = None) -> list[MCPServerConfig]:
    """Load MCP server definitions from JSON, optionally merging fallback entries."""

    definitions: list[dict[str, Any]] = []

    if fallback:
        definitions.extend(fallback)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid JSON in MCP server config {path}: {exc}") from exc

        if isinstance(payload, dict):
            items = payload.get("servers")
            if items is None:
                raise ValueError(
                    f"Expected 'servers' key in MCP server config file {path}"
                )
        elif isinstance(payload, list):
            items = payload
        else:  # pragma: no cover - defensive
            raise ValueError(
                f"Unsupported MCP server config format in {path}: expected list or object"
            )

        if not isinstance(items, list):
            raise ValueError(
                f"Invalid MCP server config in {path}: 'servers' must be a list"
            )

        definitions.extend(items)

    errors: list[str] = []
    configs_by_id: dict[str, MCPServerConfig] = {}
    order: list[str] = []

    for raw in definitions:
        try:
            config = MCPServerConfig.model_validate(raw)
        except (ValidationError, ValueError) as exc:
            errors.append(str(exc))
            continue

        if config.id in configs_by_id:
            logger.info(
                "Overriding MCP server definition for id '%s' with later entry", config.id
            )
            order = [existing for existing in order if existing != config.id]

        configs_by_id[config.id] = config
        order.append(config.id)

    if errors:
        message = "\n".join(errors)
        raise ValueError(f"Failed to load MCP server configuration:\n{message}")

    return [configs_by_id[item_id] for item_id in order]


@dataclass
class _ToolBinding:
    qualified_name: str
    original_name: str
    tool: Tool
    client: MCPToolClient
    config: MCPServerConfig


class MCPToolAggregator:
    """Aggregate tools from multiple MCP servers behind a single interface."""

    def __init__(
        self,
        configs: Sequence[MCPServerConfig],
        *,
        base_env: dict[str, str] | None = None,
        default_cwd: Path | None = None,
    ) -> None:
        self._configs = [cfg for cfg in configs]
        self._config_map: dict[str, MCPServerConfig] = {
            cfg.id: cfg for cfg in self._configs
        }
        self._base_env = dict(base_env or {})
        self._default_cwd = default_cwd
        self._clients: dict[str, MCPToolClient] = {}
        self._bindings: dict[str, _ToolBinding] = {}
        self._binding_order: list[_ToolBinding] = []
        self._openai_tools: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._connected = False
        self._tool_catalog: dict[str, list[str]] = {}

    @property
    def tools(self) -> list[Any]:
        """Return the raw MCP tool descriptors across all servers."""

        return [binding.tool for binding in self._binding_order]

    async def connect(self) -> None:
        """Launch all enabled MCP servers and build the tool registry."""

        async with self._lock:
            if self._connected:
                return

            logger.info(
                "Starting MCP aggregator with %d configured server(s)", len(self._configs)
            )

            for config in self._configs:
                if not config.enabled:
                    continue
                await self._launch_server(config)

            if not self._clients:
                logger.warning("No MCP servers were started; tool execution is disabled")

            await self._refresh_locked()
            self._connected = True

    async def apply_configs(self, configs: Sequence[MCPServerConfig]) -> None:
        """Apply a new configuration set, restarting servers as needed."""

        async with self._lock:
            new_configs = [cfg for cfg in configs]
            new_map: dict[str, MCPServerConfig] = {cfg.id: cfg for cfg in new_configs}
            old_map = self._config_map

            self._configs = new_configs
            self._config_map = new_map

            if not self._connected:
                return

            # Stop servers that are no longer enabled or removed, or require restart.
            for server_id, client in list(self._clients.items()):
                new_cfg = new_map.get(server_id)
                if new_cfg is None or not new_cfg.enabled:
                    await client.close()
                    self._clients.pop(server_id, None)
                    continue

                old_cfg = old_map.get(server_id)
                if self._requires_restart(old_cfg, new_cfg):
                    await client.close()
                    self._clients.pop(server_id, None)

            # Launch new or re-enabled servers.
            for config in new_configs:
                if not config.enabled or config.id in self._clients:
                    continue
                await self._launch_server(config)

            await self._refresh_locked()

    async def refresh(self) -> None:
        """Refresh tool catalogs for all running servers."""

        async with self._lock:
            await self._refresh_locked()

    async def _refresh_locked(self) -> None:
        bindings: list[_ToolBinding] = []
        binding_map: dict[str, _ToolBinding] = {}
        openai_tools: list[dict[str, Any]] = []
        drafts: list[tuple[MCPServerConfig, MCPToolClient, Tool, dict[str, Any]]] = []
        name_counts: Counter[str] = Counter()
        tool_catalog: dict[str, list[str]] = {}

        for config in self._configs:
            previous = self._tool_catalog.get(config.id, [])
            tool_catalog[config.id] = list(previous)

            if not config.enabled:
                continue
            client = self._clients.get(config.id)
            if client is None:
                continue

            await client.refresh_tools()
            all_tools = list(client.tools)
            tool_catalog[config.id] = [tool.name for tool in all_tools]

            specs_by_name: dict[str, dict[str, Any]] = {}
            for spec in client.get_openai_tools():
                function = spec.get("function")
                if not isinstance(function, dict):
                    continue
                tool_name = function.get("name")
                if not isinstance(tool_name, str):
                    continue
                specs_by_name[tool_name] = copy.deepcopy(spec)

            disabled = config.disabled_tools or set()

            for tool in all_tools:
                if tool.name in disabled:
                    continue
                original = specs_by_name.get(tool.name)
                if not original:
                    continue
                drafts.append((config, client, tool, original))
                name_counts[tool.name] += 1

        for config, client, tool, original in drafts:
            if name_counts[tool.name] == 1 and not config.tool_prefix:
                qualified_name = tool.name
            else:
                qualified_name = config.qualify_tool_name(tool.name)

            if qualified_name in binding_map:
                logger.warning(
                    "Skipping duplicate tool mapping for '%s' from server '%s'",
                    qualified_name,
                    config.id,
                )
                continue

            binding = _ToolBinding(
                qualified_name=qualified_name,
                original_name=tool.name,
                tool=tool,
                client=client,
                config=config,
            )
            bindings.append(binding)
            binding_map[qualified_name] = binding

            enriched = copy.deepcopy(original)
            enriched_function = enriched.get("function", {})
            enriched_function["name"] = qualified_name
            desc = enriched_function.get("description") or ""
            if not desc:
                enriched_function["description"] = f"[{config.id}]"
            elif f"[{config.id}]" not in desc:
                enriched_function["description"] = f"[{config.id}] {desc}"
            enriched["function"] = enriched_function
            openai_tools.append(enriched)

        self._bindings = binding_map
        self._binding_order = bindings
        self._openai_tools = openai_tools
        self._tool_catalog = {
            key: value for key, value in tool_catalog.items() if key in self._config_map
        }

    async def close(self) -> None:
        """Terminate all server processes and reset state."""

        async with self._lock:
            for client in self._clients.values():
                await client.close()
            self._clients.clear()
            self._bindings.clear()
            self._binding_order.clear()
            self._openai_tools.clear()
            self._connected = False

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return tool descriptors formatted for OpenRouter/OpenAI."""

        return copy.deepcopy(self._openai_tools)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> CallToolResult:
        """Execute a tool routed to the correct MCP server."""

        binding = self._bindings.get(name)
        if binding is None:
            raise ValueError(f"Unknown tool: {name}")
        return await binding.client.call_tool(binding.original_name, arguments)

    def format_tool_result(self, result: Any) -> str:
        return MCPToolClient.format_tool_result(result)

    def active_servers(self) -> list[str]:
        """Return identifiers for servers that successfully started."""

        return list(self._clients.keys())

    def get_configs(self) -> list[MCPServerConfig]:
        """Return a deep copy of the current configuration list."""

        return [cfg.model_copy(deep=True) for cfg in self._configs]

    def describe_servers(self) -> list[dict[str, Any]]:
        """Return runtime metadata for each configured server."""

        tool_counts: Counter[str] = Counter(
            binding.config.id for binding in self._binding_order
        )
        active_lookup: dict[str, dict[str, _ToolBinding]] = {}
        for binding in self._binding_order:
            active_lookup.setdefault(binding.config.id, {})[
                binding.original_name
            ] = binding

        details: list[dict[str, Any]] = []
        for config in self._configs:
            known_tools = self._tool_catalog.get(config.id, [])
            active_map = active_lookup.get(config.id, {})
            tool_entries: list[dict[str, Any]] = []
            if known_tools:
                for name in sorted(known_tools):
                    binding = active_map.get(name)
                    if binding is not None:
                        qualified = binding.qualified_name
                        enabled = True
                    else:
                        qualified = config.qualify_tool_name(name)
                        enabled = False
                    tool_entries.append(
                        {
                            "qualified_name": qualified,
                            "name": name,
                            "enabled": enabled,
                        }
                    )
            else:
                for binding in sorted(
                    active_map.values(), key=lambda item: item.original_name
                ):
                    tool_entries.append(
                        {
                            "qualified_name": binding.qualified_name,
                            "name": binding.original_name,
                            "enabled": True,
                        }
                    )
            details.append(
                {
                    "id": config.id,
                    "enabled": config.enabled,
                    "connected": config.id in self._clients,
                    "tool_count": tool_counts.get(config.id, 0),
                    "tools": tool_entries,
                    "disabled_tools": sorted(config.disabled_tools)
                    if config.disabled_tools
                    else [],
                }
            )
        return details

    async def _launch_server(self, config: MCPServerConfig) -> None:
        env = self._base_env.copy()
        env.update(config.env)
        cwd = config.resolved_cwd(self._default_cwd)

        try:
            client = MCPToolClient(
                config.module,
                command=config.command,
                server_id=config.id,
                cwd=cwd,
                env=env,
            )
            await client.connect()
        except Exception:
            logger.exception("Failed to start MCP server '%s'", config.id)
            return

        self._clients[config.id] = client

    @staticmethod
    def _requires_restart(
        old_cfg: MCPServerConfig | None, new_cfg: MCPServerConfig
    ) -> bool:
        if old_cfg is None:
            return True

        comparable_fields = ("module", "command", "cwd", "env")
        for field in comparable_fields:
            if getattr(old_cfg, field) != getattr(new_cfg, field):
                return True
        return False


__all__ = [
    "MCPServerConfig",
    "MCPToolAggregator",
    "load_server_configs",
]
