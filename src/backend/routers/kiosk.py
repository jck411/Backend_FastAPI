"""Kiosk API router for STT, TTS, LLM, presets, and MCP settings and related configuration."""

import logging
from typing import Any

from fastapi import APIRouter, Request

from backend.schemas.kiosk_stt_settings import KioskSttSettings, KioskSttSettingsUpdate
from backend.schemas.kiosk_tts_settings import KioskTtsSettings, KioskTtsSettingsUpdate, DEEPGRAM_VOICES
from backend.schemas.kiosk_llm_settings import KioskLlmSettings, KioskLlmSettingsUpdate
from backend.schemas.kiosk_presets import KioskPresets, KioskPreset, KioskPresetUpdate, KioskPresetActivate
from backend.services.kiosk_stt_settings import get_kiosk_stt_settings_service
from backend.services.kiosk_tts_settings import get_kiosk_tts_settings_service
from backend.services.kiosk_llm_settings import get_kiosk_llm_settings_service
from backend.services.kiosk_presets import get_kiosk_presets_service

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


# ============== LLM Settings ==============

@router.get("/llm-settings", response_model=KioskLlmSettings)
async def get_llm_settings() -> KioskLlmSettings:
    """Get current kiosk LLM settings."""
    service = get_kiosk_llm_settings_service()
    settings = service.get_settings()
    logger.debug(f"Returning kiosk LLM settings: {settings}")
    return settings


@router.put("/llm-settings", response_model=KioskLlmSettings)
async def update_llm_settings(update: KioskLlmSettingsUpdate) -> KioskLlmSettings:
    """Update kiosk LLM settings."""
    service = get_kiosk_llm_settings_service()
    settings = service.update_settings(update)
    logger.info(f"Updated kiosk LLM settings: {settings}")
    return settings


@router.post("/llm-settings/reset", response_model=KioskLlmSettings)
async def reset_llm_settings() -> KioskLlmSettings:
    """Reset kiosk LLM settings to defaults."""
    service = get_kiosk_llm_settings_service()
    settings = service.reset_to_defaults()
    logger.info("Reset kiosk LLM settings to defaults")
    return settings


# ============== Presets ==============

@router.get("/presets", response_model=KioskPresets)
async def get_presets() -> KioskPresets:
    """Get all kiosk presets."""
    service = get_kiosk_presets_service()
    presets = service.get_presets()
    logger.debug(f"Returning kiosk presets: {presets}")
    return presets


@router.put("/presets", response_model=KioskPresets)
async def update_preset(update: KioskPresetUpdate) -> KioskPresets:
    """Update a single preset by index."""
    service = get_kiosk_presets_service()
    presets = service.update_preset(update)
    logger.info(f"Updated kiosk preset {update.index}: {update.preset.name}")
    return presets


@router.post("/presets/activate", response_model=KioskPresets)
async def activate_preset(activate: KioskPresetActivate) -> KioskPresets:
    """Activate a preset by index and apply all its settings (LLM, STT, TTS)."""
    presets_service = get_kiosk_presets_service()
    llm_service = get_kiosk_llm_settings_service()
    stt_service = get_kiosk_stt_settings_service()
    tts_service = get_kiosk_tts_settings_service()

    # Activate the preset
    presets = presets_service.activate_preset(activate.index)
    active_preset = presets.presets[presets.active_index]

    # Apply LLM settings
    from backend.schemas.kiosk_llm_settings import KioskLlmSettingsUpdate
    llm_service.update_settings(KioskLlmSettingsUpdate(
        model=active_preset.model,
        system_prompt=active_preset.system_prompt,
        temperature=active_preset.temperature,
        max_tokens=active_preset.max_tokens,
    ))

    # Apply STT settings
    from backend.schemas.kiosk_stt_settings import KioskSttSettingsUpdate
    stt_service.update_settings(KioskSttSettingsUpdate(
        eot_threshold=active_preset.eot_threshold,
        eot_timeout_ms=active_preset.eot_timeout_ms,
        keyterms=active_preset.keyterms,
    ))

    # Apply TTS settings
    from backend.schemas.kiosk_tts_settings import KioskTtsSettingsUpdate
    tts_service.update_settings(KioskTtsSettingsUpdate(
        enabled=active_preset.tts_enabled,
        model=active_preset.tts_model,
        sample_rate=active_preset.tts_sample_rate,
    ))

    logger.info(f"Activated kiosk preset: {active_preset.name}")
    return presets


@router.post("/presets/reset", response_model=KioskPresets)
async def reset_presets() -> KioskPresets:
    """Reset all presets to defaults."""
    service = get_kiosk_presets_service()
    presets = service.reset_to_defaults()
    logger.info("Reset kiosk presets to defaults")
    return presets


# ============== MCP Server Settings ==============
# Note: kiosk_enabled is stored in the main MCP server config.
# Use PATCH /api/mcp/servers/{server_id} with {"kiosk_enabled": true/false} to update.

@router.get("/mcp-servers")
async def get_mcp_servers(request: Request) -> list[dict[str, Any]]:
    """Get all available MCP servers with their kiosk enabled status.

    Returns a list of servers with id, tool_count, and kiosk_enabled flag.
    To update kiosk_enabled, use PATCH /api/mcp/servers/{server_id}.
    """
    mcp_settings = getattr(request.app.state, "mcp_server_settings_service", None)
    orchestrator = getattr(request.app.state, "chat_orchestrator", None)

    if mcp_settings is None or orchestrator is None:
        logger.warning("MCP settings or orchestrator not configured")
        return []

    # Get configs to read kiosk_enabled
    configs = await mcp_settings.get_configs()
    kiosk_map = {cfg.id: cfg.kiosk_enabled for cfg in configs}

    # Get runtime info from orchestrator
    servers_info = orchestrator.describe_mcp_servers()

    result = []
    for server in servers_info:
        server_id = server.get("id", "")
        result.append({
            "id": server_id,
            "enabled": server.get("enabled", False),
            "tool_count": server.get("tool_count", 0),
            "kiosk_enabled": kiosk_map.get(server_id, False),
        })

    return result

