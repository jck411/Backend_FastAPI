"""Tests for MCP server settings service and API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.chat.mcp_registry import MCPServerConfig
from backend.routers.mcp_servers import (
    get_chat_orchestrator,
    get_mcp_settings_service,
    router as mcp_router,
)
from backend.services.mcp_server_settings import MCPServerSettingsService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class StubMCPServerSettingsService:
    def __init__(self, configs: list[MCPServerConfig]) -> None:
        self._configs = [cfg.model_copy(deep=True) for cfg in configs]
        self.patch_calls: list[tuple[str, dict[str, Any]]] = []
        self.replace_calls = 0
        self._updated_at = None

    async def get_configs(self) -> list[MCPServerConfig]:
        return [cfg.model_copy(deep=True) for cfg in self._configs]

    async def replace_configs(
        self, configs: list[MCPServerConfig]
    ) -> list[MCPServerConfig]:
        self.replace_calls += 1
        self._configs = [cfg.model_copy(deep=True) for cfg in configs]
        return await self.get_configs()

    async def patch_server(
        self,
        server_id: str,
        *,
        enabled: bool | None = None,
        disabled_tools: list[str] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> MCPServerConfig:
        overrides = overrides or {}
        self.patch_calls.append((server_id, {"enabled": enabled, "disabled_tools": disabled_tools, **overrides}))
        for index, cfg in enumerate(self._configs):
            if cfg.id != server_id:
                continue
            data = cfg.model_dump(exclude_none=False)
            if enabled is not None:
                data["enabled"] = enabled
            if disabled_tools is not None:
                data["disabled_tools"] = disabled_tools
            data.update(overrides)
            updated = MCPServerConfig.model_validate(data)
            self._configs[index] = updated
            return updated
        raise KeyError(f"Unknown server id {server_id}")

    async def updated_at(self):
        return self._updated_at


class StubChatOrchestrator:
    def __init__(self) -> None:
        self.applied: list[list[str]] = []
        self.refreshed = False
        self._runtime: list[dict[str, Any]] = []

    async def apply_mcp_configs(self, configs: list[MCPServerConfig]) -> None:
        self.applied.append([cfg.id for cfg in configs])
        runtime = []
        for cfg in configs:
            tools = []
            if cfg.enabled:
                tools = [
                    {
                        "name": "ping",
                        "qualified_name": f"{cfg.id}__ping",
                    }
                ]
            runtime.append(
                {
                    "id": cfg.id,
                    "connected": cfg.enabled,
                    "tool_count": len(tools),
                    "tools": tools,
                }
            )
        self._runtime = runtime

    def describe_mcp_servers(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._runtime]

    async def refresh_mcp_tools(self) -> None:
        self.refreshed = True


async def test_service_loads_fallback_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    fallback = [{"id": "alpha", "module": "pkg.alpha"}]

    service = MCPServerSettingsService(path, fallback=fallback)
    configs = await service.get_configs()

    assert len(configs) == 1
    assert configs[0].id == "alpha"

    new_config = MCPServerConfig(id="beta", module="pkg.beta", enabled=False)
    await service.replace_configs([new_config])

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["servers"][0]["id"] == "beta"
    assert raw["servers"][0]["enabled"] is False

    await service.patch_server("beta", enabled=True)
    configs = await service.get_configs()
    assert configs[0].enabled is True

    await service.toggle_tool("beta", "echo", enabled=False)
    configs = await service.get_configs()
    assert configs[0].disabled_tools == {"echo"}


async def test_router_combines_status() -> None:
    service = StubMCPServerSettingsService(
        [
            MCPServerConfig(id="alpha", module="pkg.alpha"),
            MCPServerConfig(id="beta", module="pkg.beta", enabled=False),
        ]
    )
    orchestrator = StubChatOrchestrator()
    await orchestrator.apply_mcp_configs(await service.get_configs())

    app = FastAPI()
    app.include_router(mcp_router)
    app.dependency_overrides[get_mcp_settings_service] = lambda: service
    app.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/mcp/servers/")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["servers"]) == 2
    alpha = payload["servers"][0]
    assert alpha["id"] == "alpha"
    assert alpha["connected"] is True
    assert alpha["tool_count"] == 1
    assert alpha["tools"][0]["qualified_name"] == "alpha__ping"


async def test_router_patch_updates_service_and_runtime() -> None:
    service = StubMCPServerSettingsService(
        [
            MCPServerConfig(id="alpha", module="pkg.alpha"),
        ]
    )
    orchestrator = StubChatOrchestrator()
    await orchestrator.apply_mcp_configs(await service.get_configs())

    app = FastAPI()
    app.include_router(mcp_router)
    app.dependency_overrides[get_mcp_settings_service] = lambda: service
    app.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/api/mcp/servers/alpha",
            json={"enabled": False, "disabled_tools": ["ping"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["servers"][0]["enabled"] is False
    assert payload["servers"][0]["disabled_tools"] == ["ping"]
    assert orchestrator.applied[-1] == ["alpha"]


async def test_router_refresh_calls_orchestrator() -> None:
    service = StubMCPServerSettingsService(
        [MCPServerConfig(id="alpha", module="pkg.alpha")]
    )
    orchestrator = StubChatOrchestrator()
    await orchestrator.apply_mcp_configs(await service.get_configs())

    app = FastAPI()
    app.include_router(mcp_router)
    app.dependency_overrides[get_mcp_settings_service] = lambda: service
    app.dependency_overrides[get_chat_orchestrator] = lambda: orchestrator

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/mcp/servers/refresh")

    assert response.status_code == 200
    assert orchestrator.refreshed is True
