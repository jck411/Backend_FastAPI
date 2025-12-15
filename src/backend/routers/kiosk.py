"""API routes for managing Kiosk settings (Model & MCP)."""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException

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
from ..schemas.model_settings import (
    ActiveModelSettingsPayload,
    ActiveModelSettingsResponse,
    SystemPromptPayload,
    SystemPromptResponse,
)
from ..schemas.kiosk_stt_settings import (
    KioskSttSettingsPayload,
    KioskSttSettingsResponse,
)
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService
from ..services.kiosk_stt_settings import KioskSttSettingsService

def get_kiosk_service(request: Request):
    service = getattr(request.app.state, "kiosk_chat_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Kiosk Chat Service is not configured")
    return service

def get_model_settings_service(
    kiosk_service=Depends(get_kiosk_service)
) -> ModelSettingsService:
    return kiosk_service.model_settings_service

def get_mcp_settings_service(
    kiosk_service=Depends(get_kiosk_service)
) -> MCPServerSettingsService:
    return kiosk_service.mcp_settings_service

def get_stt_settings_service(request: Request) -> KioskSttSettingsService:
    service = getattr(request.app.state, "kiosk_stt_settings_service", None)
    if service is None:
        raise HTTPException(status_code=500, detail="Kiosk STT Settings Service is not configured")
    return service

async def get_chat_orchestrator(
    kiosk_service=Depends(get_kiosk_service)
) -> ChatOrchestrator:
    await kiosk_service.ensure_initialized()
    return kiosk_service.orchestrator

from .chat import _get_models_payload, _model_supports_tools

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])

# --- Dependencies ---

@router.get("/settings/model", response_model=ActiveModelSettingsResponse)
async def read_model_settings(
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> ActiveModelSettingsResponse:
    return await service.get_settings()


@router.put("/settings/model", response_model=ActiveModelSettingsResponse)
async def update_model_settings(
    payload: ActiveModelSettingsPayload,
    service: ModelSettingsService = Depends(get_model_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> ActiveModelSettingsResponse:
    supports_tools = payload.supports_tools

    if supports_tools is None:
        client = orchestrator.get_openrouter_client()
        try:
            models_payload = await _get_models_payload(client)
        except Exception:
            models_payload = {}
        data = models_payload.get("data") if isinstance(models_payload, dict) else None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("id") == payload.model:
                    supports_tools = _model_supports_tools(item)
                    break

    payload_data = payload.model_dump(exclude_none=False)
    payload_data["supports_tools"] = supports_tools
    normalized_payload = ActiveModelSettingsPayload.model_validate(payload_data)
    # This saves to kiosk_model_settings.json
    return await service.replace_settings(normalized_payload)


@router.get("/settings/model/active-provider")
async def get_active_provider_info(
    service: ModelSettingsService = Depends(get_model_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> Dict[str, Any]:
    client = orchestrator.get_openrouter_client()
    return await service.get_active_provider_info(client)


@router.get("/settings/system-prompt", response_model=SystemPromptResponse)
async def read_system_prompt(
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> SystemPromptResponse:
    prompt = await service.get_system_prompt()
    return SystemPromptResponse(system_prompt=prompt)


@router.put("/settings/system-prompt", response_model=SystemPromptResponse)
async def update_system_prompt(
    payload: SystemPromptPayload,
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> SystemPromptResponse:
    if "system_prompt" in payload.model_fields_set:
        prompt = await service.update_system_prompt(payload.system_prompt)
    else:
        prompt = await service.get_system_prompt()
    return SystemPromptResponse(system_prompt=prompt)


# --- STT Settings Routes ---

@router.get("/settings/stt", response_model=KioskSttSettingsResponse)
async def read_stt_settings(
    service: KioskSttSettingsService = Depends(get_stt_settings_service),
) -> KioskSttSettingsResponse:
    """Get current STT settings for end-of-turn detection."""
    return await service.get_settings()


@router.put("/settings/stt", response_model=KioskSttSettingsResponse)
async def update_stt_settings(
    payload: KioskSttSettingsPayload,
    service: KioskSttSettingsService = Depends(get_stt_settings_service),
) -> KioskSttSettingsResponse:
    """Update STT settings for end-of-turn detection.

    Args:
        eot_timeout_ms: Max silence duration in ms before EndOfTurn (500-10000)
        eot_threshold: Confidence threshold for EndOfTurn detection (0.5-0.9)
    """
    return await service.update_settings(payload)


# --- MCP Server Routes ---

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
        )
        servers.append(status)

    updated_at = await service.updated_at()
    return MCPServerStatusResponse(servers=servers, updated_at=updated_at)


@router.get("/mcp/servers", response_model=MCPServerStatusResponse)
async def read_mcp_servers(
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    return await _build_status_response(service, orchestrator)


@router.put("/mcp/servers", response_model=MCPServerStatusResponse)
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


@router.patch("/mcp/servers/{server_id}", response_model=MCPServerStatusResponse)
async def update_mcp_server(
    server_id: str,
    payload: MCPServerUpdatePayload,
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    updates = payload.model_dump(exclude_none=True)
    disabled_tools = updates.pop("disabled_tools", None)
    enabled = updates.pop("enabled", None)

    try:
        await service.patch_server(
            server_id,
            enabled=enabled,
            disabled_tools=disabled_tools,
            overrides=updates,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' not found")

    configs = await service.get_configs()
    await orchestrator.apply_mcp_configs(configs)
    return await _build_status_response(service, orchestrator)


@router.post("/mcp/servers/refresh", response_model=MCPServerStatusResponse)
async def refresh_mcp_servers(
    service: MCPServerSettingsService = Depends(get_mcp_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> MCPServerStatusResponse:
    await orchestrator.refresh_mcp_tools()
    return await _build_status_response(service, orchestrator)


__all__ = ["router"]
