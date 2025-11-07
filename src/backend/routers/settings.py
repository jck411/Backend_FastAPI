"""API routes for managing active model settings."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..chat.orchestrator import ChatOrchestrator
from ..schemas.model_settings import (
    ActiveModelSettingsPayload,
    ActiveModelSettingsResponse,
    SystemPromptPayload,
    SystemPromptResponse,
)
from ..services.model_settings import ModelSettingsService
from .chat import _get_models_payload, _model_supports_tools

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
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> ActiveModelSettingsResponse:
    supports_tools = payload.supports_tools

    if supports_tools is None:
        client = orchestrator.get_openrouter_client()
        try:
            models_payload = await _get_models_payload(client)
        except Exception:  # pragma: no cover - fallback to default behaviour
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
    return await service.replace_settings(normalized_payload)


@router.get("/model/active-provider")
async def get_active_provider_info(
    service: ModelSettingsService = Depends(get_model_settings_service),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
) -> Dict[str, Any]:
    """Get information about the active provider for the current model."""
    client = orchestrator.get_openrouter_client()
    return await service.get_active_provider_info(client)


@router.get("/system-prompt", response_model=SystemPromptResponse)
async def read_system_prompt(
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> SystemPromptResponse:
    prompt, planner_enabled = await service.get_orchestrator_settings()
    return SystemPromptResponse(
        system_prompt=prompt,
        llm_planner_enabled=planner_enabled,
    )


@router.put("/system-prompt", response_model=SystemPromptResponse)
async def update_system_prompt(
    payload: SystemPromptPayload,
    service: ModelSettingsService = Depends(get_model_settings_service),
) -> SystemPromptResponse:
    updates: dict[str, Any] = {}
    if "system_prompt" in payload.model_fields_set:
        updates["system_prompt"] = payload.system_prompt
    if "llm_planner_enabled" in payload.model_fields_set:
        updates["llm_planner_enabled"] = payload.llm_planner_enabled

    if updates:
        prompt, planner_enabled = await service.update_orchestrator_settings(**updates)
    else:
        prompt, planner_enabled = await service.get_orchestrator_settings()

    return SystemPromptResponse(
        system_prompt=prompt,
        llm_planner_enabled=planner_enabled,
    )


__all__ = ["router"]
