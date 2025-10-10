"""API routes for managing configuration presets (save/apply/delete)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request

from ..chat.orchestrator import ChatOrchestrator
from ..schemas.presets import (
    PresetConfig,
    PresetCreatePayload,
    PresetListItem,
    PresetSaveSnapshotPayload,
)
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.presets import PresetService

router = APIRouter(prefix="/api/presets", tags=["presets"])


def get_preset_service(request: Request) -> PresetService:
    service = getattr(request.app.state, "preset_service", None)
    if service is None:  # pragma: no cover - defensive
        raise RuntimeError("Preset service is not configured")
    return service


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if orchestrator is None:  # pragma: no cover - defensive
        raise RuntimeError("Chat orchestrator is not configured")
    return orchestrator


def get_mcp_settings_service(request: Request) -> MCPServerSettingsService:
    service = getattr(request.app.state, "mcp_server_settings_service", None)
    if service is None:  # pragma: no cover - defensive
        raise RuntimeError("MCP server settings service is not configured")
    return service


@router.get("/", response_model=List[PresetListItem])
async def list_presets(
    service: PresetService = Depends(get_preset_service),
) -> List[PresetListItem]:
    return await service.list_presets()


@router.get("/{name}", response_model=PresetConfig)
async def read_preset(
    name: str,
    service: PresetService = Depends(get_preset_service),
) -> PresetConfig:
    return await service.get_preset(name)


@router.post("/", response_model=PresetConfig)
async def create_preset(
    payload: PresetCreatePayload,
    service: PresetService = Depends(get_preset_service),
) -> PresetConfig:
    return await service.create_from_current(payload.name)


@router.put("/{name}", response_model=PresetConfig)
async def save_snapshot(
    name: str,
    payload: PresetSaveSnapshotPayload
    | None,  # reserved for future metadata like notes
    service: PresetService = Depends(get_preset_service),
) -> PresetConfig:
    return await service.save_snapshot(name)


@router.delete("/{name}", response_model=dict)
async def delete_preset(
    name: str,
    service: PresetService = Depends(get_preset_service),
) -> dict:
    deleted = await service.delete(name)
    return {"deleted": deleted}


@router.post("/{name}/apply", response_model=PresetConfig)
async def apply_preset(
    name: str,
    service: PresetService = Depends(get_preset_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
    mcp_service: MCPServerSettingsService = Depends(get_mcp_settings_service),
) -> PresetConfig:
    preset = await service.apply(name)
    # Ensure the running aggregator applies updated MCP server configs
    configs = await mcp_service.get_configs()
    await orchestrator.apply_mcp_configs(configs)
    return preset


__all__ = ["router"]
