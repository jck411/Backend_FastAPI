"""API routes for managing MCP server settings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from ..chat.mcp_registry import MCPServerConfig
from ..chat.orchestrator import ChatOrchestrator
from ..schemas.mcp_servers import (
    MCPServerCollectionPayload,
    MCPServerStatus,
    MCPServerStatusResponse,
    MCPServerToolDefinition,
    MCPServerToolStatus,
    MCPServerUpdatePayload,
)
from ..services.mcp_server_settings import MCPServerSettingsService

router = APIRouter(prefix="/api/mcp/servers", tags=["mcp"])


def get_mcp_settings_service(request: Request) -> MCPServerSettingsService:
    service = getattr(request.app.state, "mcp_server_settings_service", None)
    if service is None:  # pragma: no cover - defensive
        raise RuntimeError("MCP server settings service is not configured")
    return service


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if orchestrator is None:  # pragma: no cover - defensive
        raise RuntimeError("Chat orchestrator is not configured")
    return orchestrator


async def _build_status_response(
    service: MCPServerSettingsService,
    orchestrator: ChatOrchestrator,
) -> MCPServerStatusResponse:
    configs = await service.get_configs()
    runtime = orchestrator.describe_mcp_servers()
    runtime_map: dict[str, dict[str, Any]] = {entry["id"]: entry for entry in runtime}

    servers: list[MCPServerStatus] = []
    for config in configs:
        runtime_entry = runtime_map.get(config.id, {})
        tools = [
            MCPServerToolStatus.model_validate(tool)
            for tool in runtime_entry.get("tools", [])
        ]
        status = MCPServerStatus(
            id=config.id,
            enabled=config.enabled,
            connected=bool(runtime_entry.get("connected", False)),
            module=config.module,
            command=config.command,
            cwd=config.cwd,
            env=config.env,
            tool_prefix=config.tool_prefix,
            disabled_tools=sorted(config.disabled_tools)
            if config.disabled_tools
            else [],
            tool_count=int(runtime_entry.get("tool_count", 0)),
            tools=tools,
            contexts=list(config.contexts),
            tool_overrides={
                name: MCPServerToolDefinition(contexts=override.contexts)
                for name, override in config.tool_overrides.items()
            },
            client_enabled=dict(config.client_enabled),
        )
        servers.append(status)

    updated_at = await service.updated_at()
    return MCPServerStatusResponse(servers=servers, updated_at=updated_at)


@router.get("/", response_model=MCPServerStatusResponse)
async def read_mcp_servers(
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    return await _build_status_response(service, orchestrator)


@router.put("/", response_model=MCPServerStatusResponse)
async def replace_mcp_servers(
    payload: MCPServerCollectionPayload,
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    configs = [
        MCPServerConfig.model_validate(defn.model_dump()) for defn in payload.servers
    ]
    persisted = await service.replace_configs(configs)
    await orchestrator.apply_mcp_configs(persisted)
    return await _build_status_response(service, orchestrator)


@router.patch("/{server_id}", response_model=MCPServerStatusResponse)
async def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdatePayload,
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    updates = payload.model_dump(exclude_none=True)
    disabled_tools = updates.pop("disabled_tools", None)
    enabled = updates.pop("enabled", None)

    await service.patch_server(
        server_id,
        enabled=enabled,
        disabled_tools=disabled_tools,
        overrides=updates,
    )
    configs = await service.get_configs()
    await orchestrator.apply_mcp_configs(configs)
    return await _build_status_response(service, orchestrator)


@router.post("/refresh", response_model=MCPServerStatusResponse)
async def refresh_mcp_servers(
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    await orchestrator.refresh_mcp_tools()
    return await _build_status_response(service, orchestrator)


@router.patch("/{server_id}/clients/{client_id}", response_model=MCPServerStatusResponse)
async def set_server_client_enabled(
    server_id: str,
    client_id: str,
    enabled: bool,
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    """Enable or disable a server for a specific client."""
    # Get current config
    configs = await service.get_configs()
    config = next((c for c in configs if c.id == server_id), None)
    if config is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Server not found: {server_id}")

    # Update client_enabled map
    new_client_enabled = dict(config.client_enabled)
    new_client_enabled[client_id] = enabled

    await service.patch_server(
        server_id,
        overrides={"client_enabled": new_client_enabled}
    )
    updated_configs = await service.get_configs()
    await orchestrator.apply_mcp_configs(updated_configs)
    return await _build_status_response(service, orchestrator)


__all__ = ["router"]
