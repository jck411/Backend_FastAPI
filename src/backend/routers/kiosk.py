"""Kiosk API router for STT and TTS settings and related configuration."""

import logging

from fastapi import APIRouter

from backend.schemas.kiosk_stt_settings import KioskSttSettings, KioskSttSettingsUpdate
from backend.schemas.kiosk_tts_settings import KioskTtsSettings, KioskTtsSettingsUpdate, DEEPGRAM_VOICES
from backend.services.kiosk_stt_settings import get_kiosk_stt_settings_service
from backend.services.kiosk_tts_settings import get_kiosk_tts_settings_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kiosk", tags=["Kiosk"])


# ============== STT Settings ==============

@router.get("/stt-settings", response_model=KioskSttSettings)
async def get_stt_settings() -> KioskSttSettings:
    """Get current kiosk STT settings."""
    service = get_kiosk_stt_settings_service()
    settings = service.get_settings()
    logger.debug(f"Returning kiosk STT settings: {settings}")
    return settings


@router.put("/stt-settings", response_model=KioskSttSettings)
async def update_stt_settings(update: KioskSttSettingsUpdate) -> KioskSttSettings:
    """Update kiosk STT settings."""
    service = get_kiosk_stt_settings_service()
    settings = service.update_settings(update)
    logger.info(f"Updated kiosk STT settings: {settings}")
    return settings


@router.post("/stt-settings/reset", response_model=KioskSttSettings)
async def reset_stt_settings() -> KioskSttSettings:
    """Reset kiosk STT settings to defaults."""
    service = get_kiosk_stt_settings_service()
    settings = service.reset_to_defaults()
    logger.info("Reset kiosk STT settings to defaults")
    return settings


# ============== TTS Settings ==============

@router.get("/tts-settings", response_model=KioskTtsSettings)
async def get_tts_settings() -> KioskTtsSettings:
    """Get current kiosk TTS settings."""
    service = get_kiosk_tts_settings_service()
    settings = service.get_settings()
    logger.debug(f"Returning kiosk TTS settings: {settings}")
    return settings


@router.put("/tts-settings", response_model=KioskTtsSettings)
async def update_tts_settings(update: KioskTtsSettingsUpdate) -> KioskTtsSettings:
    """Update kiosk TTS settings."""
    service = get_kiosk_tts_settings_service()
    settings = service.update_settings(update)
    logger.info(f"Updated kiosk TTS settings: {settings}")
    return settings


@router.post("/tts-settings/reset", response_model=KioskTtsSettings)
async def reset_tts_settings() -> KioskTtsSettings:
    """Reset kiosk TTS settings to defaults."""
    service = get_kiosk_tts_settings_service()
    settings = service.reset_to_defaults()
    logger.info("Reset kiosk TTS settings to defaults")
    return settings


@router.get("/tts-voices")
async def get_tts_voices() -> list[str]:
    """Get available TTS voice models."""
    return DEEPGRAM_VOICES
