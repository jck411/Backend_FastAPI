"""API routes for kiosk UI settings."""

import logging

from fastapi import APIRouter, HTTPException

from backend.schemas.kiosk_ui_settings import KioskUiSettings, KioskUiSettingsUpdate
from backend.services.kiosk_ui_settings import get_kiosk_ui_settings_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kiosk/ui", tags=["Kiosk UI Settings"])


@router.get("/settings", response_model=KioskUiSettings)
async def get_ui_settings() -> KioskUiSettings:
    """Get current kiosk UI settings."""
    try:
        service = get_kiosk_ui_settings_service()
        return service.get_settings()
    except Exception as e:
        logger.error(f"Failed to get kiosk UI settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/settings", response_model=KioskUiSettings)
async def update_ui_settings(update: KioskUiSettingsUpdate) -> KioskUiSettings:
    """Update kiosk UI settings."""
    try:
        service = get_kiosk_ui_settings_service()
        return service.update_settings(update)
    except Exception as e:
        logger.error(f"Failed to update kiosk UI settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
