"""MCP server management service.

Extracts MCP server management out of ChatOrchestrator so that the router
can manage connections, discovery, and registry independently.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from ..chat.mcp_registry import MCPServerConfig, MCPToolAggregator
from ..services.mcp_server_settings import MCPServerSettingsService

logger = logging.getLogger(__name__)


class MCPManagementService:
    """Manage MCP server connections and registry."""

    def __init__(
        self,
        aggregator: MCPToolAggregator,
        settings_service: MCPServerSettingsService,
    ) -> None:
        self._aggregator = aggregator
        self._settings = settings_service

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def connect_server(self, url: str) -> dict[str, Any]:
        """Connect to a new MCP server by URL, discover its tools.

        Returns server status dict on success.
        """
        server_id = await self._aggregator.connect_to_url(url)

        # Persist the new server in the registry
        configs = await self._settings.get_configs()
        if not any(c.id == server_id for c in configs):
            new_cfg = MCPServerConfig(id=server_id, url=url)
            await self._settings.add_server(new_cfg)

        # Return the status for the newly connected server
        for entry in self._aggregator.describe_servers():
            if entry["id"] == server_id:
                return entry
        return {"id": server_id, "url": url, "connected": True, "tools": []}

    async def remove_server(self, server_id: str) -> None:
        """Disconnect and remove a server from the registry."""
        # Remove from settings
        await self._settings.remove_server(server_id)
        # Re-apply configs to disconnect
        configs = await self._settings.get_configs()
        await self._aggregator.apply_configs(configs)

    async def discover_servers(
        self, host: str, ports: list[int]
    ) -> list[dict[str, Any]]:
        """Scan for MCP servers on a network host.

        Returns a list of server status dicts for discovered servers.
        """
        results: list[dict[str, Any]] = []
        for port in ports:
            is_running = await self._aggregator._is_server_running(host, port)
            if not is_running:
                continue
            url = f"http://{host}:{port}/mcp"
            try:
                server_id = await self._aggregator.connect_to_url(url)
                # Persist if not already known
                configs = await self._settings.get_configs()
                if not any(c.id == server_id for c in configs):
                    new_cfg = MCPServerConfig(id=server_id, url=url)
                    await self._settings.add_server(new_cfg)

                for entry in self._aggregator.describe_servers():
                    if entry["id"] == server_id:
                        results.append(entry)
                        break
            except Exception:
                logger.exception("Failed to connect to MCP server at %s", url)

        return results

    async def discover_local(self) -> dict[str, bool]:
        """Scan local MCP discovery ports and connect.

        Loads configs on first call (lazy initialisation).
        """
        if not self._aggregator._configs:
            configs = await self._settings.get_configs()
            await self._aggregator.apply_configs(configs)

        return await self._aggregator.discover_and_connect()

    # ------------------------------------------------------------------
    # Status & toggles
    # ------------------------------------------------------------------

    async def get_status(self) -> list[dict[str, Any]]:
        """Return all servers with connection status and tools."""
        return self._aggregator.describe_servers()

    async def toggle_server(self, server_id: str, enabled: bool) -> None:
        """Enable or disable a server."""
        await self._settings.patch_server(server_id, enabled=enabled)
        configs = await self._settings.get_configs()
        await self._aggregator.apply_configs(configs)

    async def toggle_tool(
        self, server_id: str, tool_name: str, enabled: bool
    ) -> None:
        """Enable or disable a specific tool."""
        await self._settings.toggle_tool(server_id, tool_name, enabled=enabled)
        configs = await self._settings.get_configs()
        await self._aggregator.apply_configs(configs)

    async def refresh(self) -> None:
        """Trigger a manual tool catalogue refresh."""
        await self._aggregator.refresh()


__all__ = ["MCPManagementService"]
