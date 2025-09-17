"""API routes for managing active model settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

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


__all__ = ["router"]
