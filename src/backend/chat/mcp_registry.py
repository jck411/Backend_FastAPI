"""Configuration loader and aggregator for MCP tool servers."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import shlex
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Iterable, Sequence

from anyio import ClosedResourceError
from mcp.types import CallToolResult, Tool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .mcp_client import MCPToolClient

logger = logging.getLogger(__name__)


class MCPServerToolConfig(BaseModel):
    """Per-tool configuration overrides for an MCP server."""

    model_config = ConfigDict(extra="forbid")

    contexts: list[str] | None = Field(
        default=None,
        description="Optional list of contexts/tags that apply to the specific tool",
    )

    @field_validator("contexts", mode="before")
    @classmethod
    def _normalize_contexts(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if isinstance(item, str)]
        raise TypeError("contexts must be a sequence of strings or null")

    @field_validator("contexts")
    @classmethod
    def _dedupe_contexts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unique: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique


class MCPServerConfig(BaseModel):
    """Declarative description of how to launch an MCP server."""

    model_config = ConfigDict(extra="ignore")  # Allow legacy fields during migration

    id: Annotated[
        str,
        Field(..., min_length=1, description="Stable identifier for the server"),
    ]
    enabled: bool = Field(
        default=True, description="Whether the server should be launched"
    )
    module: str | None = Field(
        default=None,
        description="Python module path to launch via `python -m`",
    )
    command: list[str] | None = Field(
        default=None,
        description="Explicit command (argv) to execute for the server",
    )
    http_url: str | None = Field(
        default=None,
        description="HTTP/SSE endpoint URL for remote MCP server (e.g., http://example.com/mcp)",
    )
    http_port: int | None = Field(
        default=None,
        description="Local HTTP port to connect to (implies http://127.0.0.1:{port}/mcp)",
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
    contexts: list[str] = Field(
        default_factory=list,
        description="Logical contexts/tags advertised by all tools from this server",
    )
    tool_overrides: dict[str, MCPServerToolConfig] = Field(
        default_factory=dict,
        description="Optional per-tool override settings keyed by tool name",
    )
    client_enabled: dict[str, bool] = Field(
        default_factory=lambda: {"svelte": True, "kiosk": False, "cli": True},
        description="Per-client enabled state: {client_id: True/False}",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_enabled_flags(cls, data: Any) -> Any:
        """Migrate legacy kiosk_enabled/frontend_enabled to client_enabled dict."""
        if not isinstance(data, dict):
            return data

        # If client_enabled already exists, use it
        if "client_enabled" in data:
            return data

        # Migrate legacy fields
        frontend_enabled = data.pop("frontend_enabled", True)
        kiosk_enabled = data.pop("kiosk_enabled", False)

        data["client_enabled"] = {
            "svelte": frontend_enabled,
            "kiosk": kiosk_enabled,
            "cli": frontend_enabled,  # CLI follows frontend by default
        }
        return data

    def is_enabled_for_client(self, client_id: str) -> bool:
        """Check if this server is enabled for a specific client."""
        return self.client_enabled.get(client_id, False)

    def is_enabled_for_any_client(self) -> bool:
        """Check if this server is enabled for any UI client (svelte, kiosk, cli)."""
        return (
            self.client_enabled.get("svelte", False)
            or self.client_enabled.get("kiosk", False)
            or self.client_enabled.get("cli", False)
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

    @field_validator("contexts", mode="before")
    @classmethod
    def _normalize_contexts(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if isinstance(item, str)]
        raise TypeError("contexts must be a sequence of strings")

    @field_validator("contexts")
    @classmethod
    def _dedupe_contexts(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    @field_validator("tool_overrides", mode="before")
    @classmethod
    def _normalize_tool_overrides(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError(
                "tool_overrides must be a mapping of tool names to overrides"
            )
        normalized: dict[str, Any] = {}
        for key, override in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError("tool_overrides keys must be non-empty strings")
            normalized[key] = override
        return normalized

    @model_validator(mode="after")
    def _validate_launch_method(self) -> "MCPServerConfig":
        if self.http_url and self.http_port is not None:
            raise ValueError(
                f"Define only one of 'http_url' or 'http_port' for MCP server '{self.id}'"
            )

        if self.http_url:
            if self.module or self.command:
                raise ValueError(
                    f"Do not combine 'http_url' with 'module' or 'command' for MCP server '{self.id}'"
                )
            return self

        if self.http_port is not None:
            return self

        message = (
            "Define 'http_url' or 'http_port' for MCP server '%s' "
            "(HTTP transport is required)"
        )
        raise ValueError(message % self.id)

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


def load_server_configs(
    path: Path, *, fallback: Sequence[dict[str, Any]] | None = None
) -> list[MCPServerConfig]:
    """Load MCP server definitions from JSON, optionally merging fallback entries."""

    definitions: list[dict[str, Any]] = []

    if fallback:
        definitions.extend(fallback)

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Invalid JSON in MCP server config {path}: {exc}"
            ) from exc

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
                "Overriding MCP server definition for id '%s' with later entry",
                config.id,
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
    contexts: tuple[str, ...]
    description: str | None
    parameters: dict[str, Any] | None


@dataclass(slots=True)
class _ToolDigestEntry:
    name: str
    description: str | None
    parameters: dict[str, Any] | None
    server: str
    contexts: tuple[str, ...]

    def __post_init__(self) -> None:
        self._name_lower = self.name.lower()
        self._description_lower = (self.description or "").lower()
        if self.parameters is None:
            self._parameters_blob = ""
        else:
            try:
                self._parameters_blob = json.dumps(
                    self.parameters, sort_keys=True
                ).lower()
            except TypeError:
                self._parameters_blob = str(self.parameters).lower()

    _name_lower: str = field(init=False, repr=False)
    _description_lower: str = field(init=False, repr=False)
    _parameters_blob: str = field(init=False, repr=False)

    def score_for_context(self, context: str) -> float:
        if not context or context == "__all__":
            return 1.0 + 0.05 * len(self.contexts)
        term = context.lower()
        score = 0.1
        if term in self.contexts:
            score += 4.0
        if term in self._name_lower:
            score += 3.0
        if term and term in self._description_lower:
            score += 2.0
        if term and term in self._parameters_blob:
            score += 1.0
        return score

    def to_summary(self, score: float) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "server": self.server,
            "contexts": list(self.contexts),
            "score": score,
        }
        if self.parameters is not None:
            payload["parameters"] = copy.deepcopy(self.parameters)
        return payload


# Port range for discovering running MCP servers
MCP_DISCOVERY_PORTS = range(9001, 9012)  # 9001-9011 inclusive


class MCPToolAggregator:
    """Aggregate tools from multiple MCP servers behind a single interface."""

    def __init__(
        self,
        configs: Sequence[MCPServerConfig],
        *,
        base_env: dict[str, str] | None = None,
        default_cwd: Path | None = None,
        lazy_mode: bool = False,
        managed_mode: bool = False,
    ) -> None:
        self._configs = [cfg for cfg in configs]
        self._config_map: dict[str, MCPServerConfig] = {
            cfg.id: cfg for cfg in self._configs
        }
        self._base_env = dict(base_env or {})
        self._default_cwd = default_cwd
        self._lazy_mode = lazy_mode
        self._managed_mode = managed_mode
        self._clients: dict[str, MCPToolClient] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._bindings: dict[str, _ToolBinding] = {}
        self._binding_order: list[_ToolBinding] = []
        self._openai_tools: list[dict[str, Any]] = []
        self._openai_tool_map: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._connected = False
        self._tool_catalog: dict[str, list[str]] = {}
        self._context_digest_index: dict[str, list[_ToolDigestEntry]] = {}
        self._global_digest: list[_ToolDigestEntry] = []

    @property
    def tools(self) -> list[Any]:
        """Return the raw MCP tool descriptors across all servers."""

        return [binding.tool for binding in self._binding_order]

    async def connect(self) -> None:
        """Launch all enabled MCP servers and build the tool registry.

        In lazy_mode, this is a no-op. Use discover_and_connect() instead.
        """

        async with self._lock:
            if self._connected:
                return

            # In lazy mode, skip all MCP connection at startup
            if self._lazy_mode:
                logger.debug("MCP aggregator in lazy mode, skipping startup connection")
                self._connected = True
                return

            logger.info(
                "Starting MCP aggregator with %d configured server(s)",
                len(self._configs),
            )

            for config in self._configs:
                if not config.enabled:
                    continue
                if not config.is_enabled_for_any_client():
                    logger.debug(
                        "MCP server '%s' not enabled for any client, skipping",
                        config.id,
                    )
                    continue
                await self._launch_server(config)

            if not self._clients:
                logger.warning(
                    "No MCP servers were started; tool execution is disabled"
                )

            await self._refresh_locked()
            self._connected = True

    async def discover_and_connect(self) -> dict[str, bool]:
        """Scan MCP_DISCOVERY_PORTS for running servers and connect to enabled ones.

        Returns a dict mapping port -> is_running for discovered servers.
        This is the main entry point for lazy MCP discovery.
        """
        async with self._lock:
            discovered: dict[str, bool] = {}

            # Scan all ports in the discovery range
            for port in MCP_DISCOVERY_PORTS:
                is_running = await self._is_server_running("127.0.0.1", port)
                discovered[str(port)] = is_running

                if not is_running:
                    continue

                # Find config for this port
                config = None
                for cfg in self._configs:
                    if cfg.http_port == port:
                        config = cfg
                        break

                if config is None:
                    logger.info(
                        "Discovered MCP server on port %d but no config found, skipping",
                        port,
                    )
                    continue

                # Check if already connected
                if config.id in self._clients:
                    logger.debug(
                        "MCP server '%s' on port %d already connected",
                        config.id,
                        port,
                    )
                    continue

                # Check if enabled for backend
                if not config.enabled:
                    logger.debug(
                        "MCP server '%s' on port %d disabled, skipping",
                        config.id,
                        port,
                    )
                    continue

                if not config.is_enabled_for_any_client():
                    logger.debug(
                        "MCP server '%s' on port %d not enabled for any client, skipping",
                        config.id,
                        port,
                    )
                    continue

                # Connect to the running server
                logger.info(
                    "Discovered MCP server '%s' running on port %d, connecting...",
                    config.id,
                    port,
                )
                await self._launch_server(config)

            # Refresh tool registry after discovery
            await self._refresh_locked()
            self._connected = True

            logger.info(
                "MCP discovery complete: %d server(s) connected, %d tool(s) available",
                len(self._clients),
                len(self._binding_order),
            )

            return discovered

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
                    # Terminate spawned process if any
                    await self._terminate_process(server_id)
                    continue

                old_cfg = old_map.get(server_id)
                if self._requires_restart(old_cfg, new_cfg):
                    await client.close()
                    self._clients.pop(server_id, None)
                    await self._terminate_process(server_id)

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
        openai_tool_map: dict[str, dict[str, Any]] = {}
        drafts: list[
            tuple[MCPServerConfig, MCPToolClient, Tool, dict[str, Any], tuple[str, ...]]
        ] = []
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

            try:
                await client.refresh_tools()
            except ClosedResourceError:
                logger.warning(
                    "MCP server '%s' closed during tool refresh; removing client",
                    config.id,
                )
                await client.close()
                self._clients.pop(config.id, None)
                tool_catalog[config.id] = []
                continue
            except Exception:
                logger.exception(
                    "Failed to refresh tools for MCP server '%s'", config.id
                )
                tool_catalog[config.id] = []
                continue
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
                override = config.tool_overrides.get(tool.name)
                if override is not None and override.contexts is not None:
                    context_values = override.contexts
                else:
                    context_values = config.contexts
                normalized_contexts: list[str] = []
                seen_contexts: set[str] = set()
                for value in context_values:
                    if not isinstance(value, str):
                        continue
                    normalized = value.strip().lower()
                    if not normalized or normalized in seen_contexts:
                        continue
                    seen_contexts.add(normalized)
                    normalized_contexts.append(normalized)
                contexts_tuple = tuple(normalized_contexts)
                drafts.append((config, client, tool, original, contexts_tuple))
                name_counts[tool.name] += 1

        for config, client, tool, original, contexts in drafts:
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

            function_spec = original.get("function", {})
            description_value = function_spec.get("description")
            if not isinstance(description_value, str):
                description_value = None
            parameters_value = function_spec.get("parameters")
            if isinstance(parameters_value, dict):
                parameters_copy = copy.deepcopy(parameters_value)
            else:
                parameters_copy = None

            binding = _ToolBinding(
                qualified_name=qualified_name,
                original_name=tool.name,
                tool=tool,
                client=client,
                config=config,
                contexts=contexts,
                description=description_value,
                parameters=parameters_copy,
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
            openai_tool_map[qualified_name] = enriched

        self._bindings = binding_map
        self._binding_order = bindings
        self._openai_tools = openai_tools
        self._openai_tool_map = openai_tool_map
        self._rebuild_context_digest(bindings)
        self._tool_catalog = {
            key: value for key, value in tool_catalog.items() if key in self._config_map
        }

    async def close(self) -> None:
        """Terminate all server processes and reset state."""

        async with self._lock:
            # Close all clients with individual timeouts and error handling
            for server_id, client in list(self._clients.items()):
                try:
                    await asyncio.wait_for(client.close(), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("Timeout closing MCP client '%s'", server_id)
                except Exception as exc:
                    logger.warning("Error closing MCP client '%s': %s", server_id, exc)

            # Terminate all spawned processes
            for server_id, process in list(self._processes.items()):
                try:
                    if process.returncode is None:
                        process.terminate()
                        await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                except Exception as exc:
                    logger.warning("Error terminating MCP process '%s': %s", server_id, exc)

            self._clients.clear()
            self._processes.clear()
            self._bindings.clear()
            self._binding_order.clear()
            self._openai_tools.clear()
            self._openai_tool_map.clear()
            self._context_digest_index.clear()
            self._global_digest = []
            self._connected = False

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return tool descriptors formatted for OpenRouter/OpenAI."""

        return [copy.deepcopy(spec) for spec in self._openai_tools]

    def get_openai_tools_by_qualified_names(
        self, names: Iterable[str]
    ) -> list[dict[str, Any]]:
        """Return OpenAI tool specs for the provided qualified names."""

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for name in names:
            if not isinstance(name, str):
                continue
            if not name or name in seen:
                continue
            spec = self._openai_tool_map.get(name)
            if spec is None:
                continue
            results.append(copy.deepcopy(spec))
            seen.add(name)
        return results

    def get_capability_digest(
        self,
        contexts: Iterable[str] | None = None,
        *,
        limit: int = 5,
        include_global: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return ranked tool summaries grouped by context."""

        if contexts is None:
            requested = sorted(
                key
                for key in self._context_digest_index
                if key and key not in {"__all__"}
            )
        else:
            requested = []
            seen: set[str] = set()
            for context in contexts:
                if not isinstance(context, str):
                    continue
                normalized = context.strip().lower()
                if not normalized or normalized == "__all__" or normalized in seen:
                    continue
                seen.add(normalized)
                requested.append(normalized)

        digest: dict[str, list[dict[str, Any]]] = {}
        for context in requested:
            entries = self._context_digest_index.get(context)
            if not entries:
                continue
            ranked = self._rank_digest_entries(context, entries, limit)
            if ranked:
                digest[context] = [entry.to_summary(score) for score, entry in ranked]

        if include_global:
            if self._global_digest:
                ranked_global = self._rank_digest_entries(
                    "__all__", self._global_digest, limit
                )
                digest["__all__"] = [
                    entry.to_summary(score) for score, entry in ranked_global
                ]
            else:
                digest["__all__"] = []

        return digest

    def get_openai_tools_for_contexts(
        self, contexts: Iterable[str]
    ) -> list[dict[str, Any]]:
        """Return tool descriptors filtered by matching contexts."""

        requested = {
            ctx.strip().lower()
            for ctx in contexts
            if isinstance(ctx, str) and ctx.strip()
        }
        if not requested or "__all__" in requested:
            return self.get_openai_tools()

        matched: list[dict[str, Any]] = []
        for binding in self._binding_order:
            if binding.contexts and any(ctx in requested for ctx in binding.contexts):
                spec = self._openai_tool_map.get(binding.qualified_name)
                if spec is not None:
                    matched.append(copy.deepcopy(spec))
        return matched

    def _rank_digest_entries(
        self,
        context: str,
        entries: Sequence[_ToolDigestEntry],
        limit: int,
    ) -> list[tuple[float, _ToolDigestEntry]]:
        if not entries:
            return []
        scored: list[tuple[float, _ToolDigestEntry]] = [
            (entry.score_for_context(context), entry) for entry in entries
        ]
        scored.sort(key=lambda item: (-item[0], item[1].name))
        if limit > 0:
            return scored[:limit]
        return scored

    def _rebuild_context_digest(self, bindings: Sequence[_ToolBinding]) -> None:
        if not bindings:
            self._context_digest_index = {"__all__": []}
            self._global_digest = []
            return

        context_index: dict[str, list[_ToolDigestEntry]] = {}
        global_entries: list[_ToolDigestEntry] = []

        for binding in bindings:
            parameters_copy = (
                copy.deepcopy(binding.parameters)
                if isinstance(binding.parameters, dict)
                else None
            )
            entry = _ToolDigestEntry(
                name=binding.qualified_name,
                description=binding.description,
                parameters=parameters_copy,
                server=binding.config.id,
                contexts=binding.contexts,
            )
            global_entries.append(entry)

            if binding.contexts:
                for context in binding.contexts:
                    context_index.setdefault(context, []).append(entry)
            else:
                context_index.setdefault("__unscoped__", []).append(entry)

        context_index["__all__"] = list(global_entries)
        self._context_digest_index = context_index
        self._global_digest = global_entries

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> CallToolResult:
        """Execute a tool routed to the correct MCP server."""

        binding = self._bindings.get(name)
        if binding is None:
            raise ValueError(f"Unknown tool: {name}")
        logger.info(
            "[MCP-DEBUG] Dispatching tool '%s' (original: '%s') to server '%s'",
            name,
            binding.original_name,
            binding.config.id,
        )
        try:
            result = await binding.client.call_tool(binding.original_name, arguments)
            logger.info(
                "[MCP-DEBUG] Tool '%s' completed from server '%s'",
                name,
                binding.config.id,
            )
            return result
        except Exception as exc:
            logger.error(
                "[MCP-DEBUG] Tool '%s' FAILED with exception: %s",
                name,
                exc,
            )
            raise

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
            active_lookup.setdefault(binding.config.id, {})[binding.original_name] = (
                binding
            )

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
                    "contexts": list(config.contexts),
                    "tool_overrides": {
                        name: override.model_dump(exclude_none=True)
                        for name, override in config.tool_overrides.items()
                    },
                }
            )
        return details

    async def _is_server_running(self, host: str, port: int) -> bool:
        """Check if a server is already accepting connections on the given port."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=0.5,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    async def _spawn_server_process(
        self, config: MCPServerConfig, env: dict[str, str], cwd: Path | None
    ) -> asyncio.subprocess.Process | None:
        """Spawn an MCP server as a subprocess."""
        if not config.module or config.http_port is None:
            logger.warning(
                "Cannot spawn MCP server '%s': missing module or http_port",
                config.id,
            )
            return None

        argv = [
            sys.executable,
            "-m",
            config.module,
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(config.http_port),
        ]

        # Disable FastMCP banner for cleaner output
        spawn_env = {**env, "FASTMCP_SHOW_CLI_BANNER": "false", "PYTHONUNBUFFERED": "1"}

        try:
            logger.info(
                "Spawning MCP server '%s' on port %d...",
                config.id,
                config.http_port,
            )
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd) if cwd else None,
                env=spawn_env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return process
        except Exception:
            logger.exception("Failed to spawn MCP server '%s'", config.id)
            return None

    async def _terminate_process(self, server_id: str) -> None:
        """Terminate a spawned server process if it exists."""
        process = self._processes.pop(server_id, None)
        if process is None:
            return

        try:
            if process.returncode is None:
                logger.info("Terminating MCP server '%s'...", server_id)
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=3.0)
                logger.info("MCP server '%s' terminated", server_id)
        except asyncio.TimeoutError:
            logger.warning("MCP server '%s' did not terminate, killing...", server_id)
            process.kill()
            await process.wait()
        except Exception as exc:
            logger.warning("Error terminating MCP server '%s': %s", server_id, exc)

    async def _launch_server(self, config: MCPServerConfig) -> None:
        env = self._base_env.copy()
        env.update(config.env)
        cwd = config.resolved_cwd(self._default_cwd)

        try:
            if config.http_url is not None:
                # Remote server - always connect_only
                client = MCPToolClient(
                    http_url=config.http_url,
                    server_id=config.id,
                    connect_only=True,
                )
            elif config.http_port is not None:
                already_running = await self._is_server_running(
                    "127.0.0.1", config.http_port
                )

                if already_running:
                    logger.info(
                        "MCP server '%s' already running on port %d, connecting...",
                        config.id,
                        config.http_port,
                    )
                    client = MCPToolClient(
                        http_port=config.http_port,
                        server_id=config.id,
                        connect_only=True,
                    )
                elif self._managed_mode and config.module:
                    # In managed mode, spawn the server process
                    process = await self._spawn_server_process(config, env, cwd)
                    if process is None:
                        return

                    self._processes[config.id] = process

                    # Wait for server to start accepting connections
                    for attempt in range(20):  # 10 second timeout
                        await asyncio.sleep(0.5)
                        if await self._is_server_running("127.0.0.1", config.http_port):
                            break
                    else:
                        logger.error(
                            "MCP server '%s' failed to start on port %d",
                            config.id,
                            config.http_port,
                        )
                        await self._terminate_process(config.id)
                        return

                    logger.info(
                        "MCP server '%s' started on port %d, connecting...",
                        config.id,
                        config.http_port,
                    )
                    client = MCPToolClient(
                        http_port=config.http_port,
                        server_id=config.id,
                        connect_only=True,
                    )
                elif self._lazy_mode:
                    # In lazy mode without managed mode, skip servers that aren't running
                    logger.info(
                        "MCP server '%s' not running on port %d, skipping (start with option 2)",
                        config.id,
                        config.http_port,
                    )
                    return
                else:
                    # In normal mode (tests), spawn the server via MCPToolClient
                    client = MCPToolClient(
                        server_module=config.module,
                        command=config.command,
                        http_port=config.http_port,
                        server_id=config.id,
                        cwd=cwd,
                        env=env,
                    )
            else:
                logger.warning(
                    "MCP server '%s' has no http_url or http_port configured",
                    config.id,
                )
                return

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

        comparable_fields = ("module", "command", "http_url", "http_port", "cwd", "env")
        for attr in comparable_fields:
            if getattr(old_cfg, attr) != getattr(new_cfg, attr):
                return True
        return False


__all__ = [
    "MCPServerToolConfig",
    "MCPServerConfig",
    "MCPToolAggregator",
    "load_server_configs",
]
