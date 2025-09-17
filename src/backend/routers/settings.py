"""API routes for managing active model settings."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..chat.orchestrator import ChatOrchestrator
from ..schemas.model_settings import (
    ActiveModelSettingsPayload,
    ActiveModelSettingsResponse,
)
from ..services.model_settings import ModelSettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_model_settings_service(request: Request) -> ModelSettingsService:
    service = getattr(request.app.state, "model_settings_service", None)
    if service is None:  # pragma: no cover - defensive
        raise RuntimeError("Model settings service is not configured")
    return service


def get_chat_orchestrator(request: Request) -> ChatOrchestrator:
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if orchestrator is None:  # pragma: no cover - defensive
        raise RuntimeError("Chat orchestrator is not configured")
    return orchestrator


@router.get("/model", response_model=ActiveModelSettingsResponse)
async def read_model_settings(
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> ActiveModelSettingsResponse:
    return await service.get_settings()


@router.put("/model", response_model=ActiveModelSettingsResponse)
async def update_model_settings(
    payload: ActiveModelSettingsPayload,
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> ActiveModelSettingsResponse:
    return await service.replace_settings(payload)


@router.get("/model/active-provider")
async def get_active_provider_info(
    service: ModelSettingsService = Depends(get_model_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> Dict[str, Any]:
    """Get information about the active provider for the current model."""
    return await service.get_active_provider_info(orchestrator._client)


__all__ = ["router"]
