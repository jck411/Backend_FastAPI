"""Unified client settings router.

This router handles settings for all clients using the pattern:
  /api/clients/{client_id}/llm
  /api/clients/{client_id}/stt
  /api/clients/{client_id}/tts
  /api/clients/{client_id}/mcp-servers
  /api/clients/{client_id}/presets
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from backend.schemas.client_settings import (
    ClientPreset,
    ClientPresets,
    ClientPresetUpdate,
    ClientSettings,
    LlmSettings,
    LlmSettingsUpdate,
    McpServerRef,
    McpServersUpdate,
    SttSettings,
    SttSettingsUpdate,
    TtsSettings,
    TtsSettingsUpdate,
    UiSettings,
    UiSettingsUpdate,
)
from backend.services.client_settings_service import (
    ClientSettingsService,
    get_client_settings_service,
)
from backend.services.mcp_server_settings import MCPServerSettingsService
from backend.chat.orchestrator import ChatOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["Client Settings"])

# Valid client IDs to prevent arbitrary directory creation
VALID_CLIENTS = {"kiosk", "svelte", "cli"}


def validate_client_id(client_id: str = Path(..., description="Client identifier")) -> str:
    """Validate that the client_id is known."""
    if client_id not in VALID_CLIENTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown client '{client_id}'. Valid clients: {', '.join(sorted(VALID_CLIENTS))}",
        )
    return client_id


def get_service(
    client_id: str = Depends(validate_client_id),
) -> ClientSettingsService:
    """Get the settings service for a client."""
    return get_client_settings_service(client_id)


def get_mcp_settings_service(request: Request) -> Optional[MCPServerSettingsService]:
    """Get MCP server settings service from request state (if available)."""
    return getattr(request.app.state, "mcp_server_settings_service", None)


def get_chat_orchestrator(request: Request) -> Optional[ChatOrchestrator]:
    """Get chat orchestrator from request state (if available)."""
    return getattr(request.app.state, "chat_orchestrator", None)


# =============================================================================
# LLM Settings
# =============================================================================


@router.get("/{client_id}/llm", response_model=LlmSettings)
async def get_llm_settings(
    service: ClientSettingsService = Depends(get_service),
) -> LlmSettings:
    """Get LLM settings for the client."""
    return service.get_llm()


@router.put("/{client_id}/llm", response_model=LlmSettings)
async def update_llm_settings(
    update: LlmSettingsUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> LlmSettings:
    """Update LLM settings for the client."""
    return service.update_llm(update)


@router.post("/{client_id}/llm/reset", response_model=LlmSettings)
async def reset_llm_settings(
    service: ClientSettingsService = Depends(get_service),
) -> LlmSettings:
    """Reset LLM settings to defaults."""
    return service.replace_llm(LlmSettings())


# =============================================================================
# STT Settings
# =============================================================================


@router.get("/{client_id}/stt", response_model=SttSettings)
async def get_stt_settings(
    service: ClientSettingsService = Depends(get_service),
) -> SttSettings:
    """Get STT settings for the client."""
    return service.get_stt()


@router.put("/{client_id}/stt", response_model=SttSettings)
async def update_stt_settings(
    update: SttSettingsUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> SttSettings:
    """Update STT settings for the client."""
    return service.update_stt(update)


@router.post("/{client_id}/stt/reset", response_model=SttSettings)
async def reset_stt_settings(
    service: ClientSettingsService = Depends(get_service),
) -> SttSettings:
    """Reset STT settings to defaults."""
    service._save_json("stt", SttSettings().model_dump())
    service._cache.pop("stt", None)
    return service.get_stt()


# =============================================================================
# TTS Settings
# =============================================================================


@router.get("/{client_id}/tts", response_model=TtsSettings)
async def get_tts_settings(
    service: ClientSettingsService = Depends(get_service),
) -> TtsSettings:
    """Get TTS settings for the client."""
    return service.get_tts()


@router.put("/{client_id}/tts", response_model=TtsSettings)
async def update_tts_settings(
    update: TtsSettingsUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> TtsSettings:
    """Update TTS settings for the client."""
    return service.update_tts(update)


@router.post("/{client_id}/tts/reset", response_model=TtsSettings)
async def reset_tts_settings(
    service: ClientSettingsService = Depends(get_service),
) -> TtsSettings:
    """Reset TTS settings to defaults."""
    service._save_json("tts", TtsSettings().model_dump())
    service._cache.pop("tts", None)
    return service.get_tts()


# TTS voice listing (shared across all clients)
@router.get("/{client_id}/tts/voices")
async def get_tts_voices(
    provider: str = "openai",
) -> list[dict[str, str]]:
    """Get available TTS voice models for the specified provider."""
    # OpenAI TTS voices
    if provider == "openai":
        return [
            {"id": "alloy", "name": "Alloy (Neutral)"},
            {"id": "echo", "name": "Echo (Male)"},
            {"id": "fable", "name": "Fable (British)"},
            {"id": "onyx", "name": "Onyx (Male, Deep)"},
            {"id": "nova", "name": "Nova (Female)"},
            {"id": "shimmer", "name": "Shimmer (Female)"},
        ]
    # Deepgram Aura voices
    elif provider == "deepgram":
        return [
            {"id": "aura-asteria-en", "name": "Asteria (Female)"},
            {"id": "aura-luna-en", "name": "Luna (Female)"},
            {"id": "aura-stella-en", "name": "Stella (Female)"},
            {"id": "aura-athena-en", "name": "Athena (Female)"},
            {"id": "aura-hera-en", "name": "Hera (Female)"},
            {"id": "aura-orion-en", "name": "Orion (Male)"},
            {"id": "aura-arcas-en", "name": "Arcas (Male)"},
            {"id": "aura-perseus-en", "name": "Perseus (Male)"},
            {"id": "aura-angus-en", "name": "Angus (Male, Irish)"},
            {"id": "aura-orpheus-en", "name": "Orpheus (Male)"},
            {"id": "aura-helios-en", "name": "Helios (Male, British)"},
            {"id": "aura-zeus-en", "name": "Zeus (Male)"},
        ]
    elif provider == "elevenlabs":
        return [
            {"id": "Rachel", "name": "Rachel"},
            {"id": "Drew", "name": "Drew"},
            {"id": "Clyde", "name": "Clyde"},
            {"id": "Paul", "name": "Paul"},
            {"id": "Domi", "name": "Domi"},
            {"id": "Dave", "name": "Dave"},
            {"id": "Fin", "name": "Fin"},
            {"id": "Sarah", "name": "Sarah"},
            {"id": "Antoni", "name": "Antoni"},
            {"id": "Thomas", "name": "Thomas"},
            {"id": "Charlie", "name": "Charlie"},
            {"id": "Emily", "name": "Emily"},
        ]
    return []


# =============================================================================
# UI Settings
# =============================================================================


@router.get("/{client_id}/ui", response_model=UiSettings)
async def get_ui_settings(
    service: ClientSettingsService = Depends(get_service),
) -> UiSettings:
    """Get UI settings for the client."""
    return service.get_ui()


@router.put("/{client_id}/ui", response_model=UiSettings)
async def update_ui_settings(
    update: UiSettingsUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> UiSettings:
    """Update UI settings for the client."""
    return service.update_ui(update)


@router.post("/{client_id}/ui/reset", response_model=UiSettings)
async def reset_ui_settings(
    service: ClientSettingsService = Depends(get_service),
) -> UiSettings:
    """Reset UI settings to defaults."""
    service._save_json("ui", UiSettings().model_dump())
    service._cache.pop("ui", None)
    return service.get_ui()


# =============================================================================
# MCP Servers
# =============================================================================


@router.get("/{client_id}/mcp-servers", response_model=list[McpServerRef])
async def get_mcp_servers(
    service: ClientSettingsService = Depends(get_service),
) -> list[McpServerRef]:
    """Get MCP server configuration for the client."""
    return service.get_mcp_servers()


@router.put("/{client_id}/mcp-servers", response_model=list[McpServerRef])
async def update_mcp_servers(
    update: McpServersUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> list[McpServerRef]:
    """Update MCP server configuration for the client."""
    return service.update_mcp_servers(update)


@router.patch("/{client_id}/mcp-servers/{server_id}")
async def toggle_mcp_server(
    server_id: str,
    enabled: bool,
    service: ClientSettingsService = Depends(get_service),
) -> list[McpServerRef]:
    """Enable or disable a specific MCP server for the client."""
    return service.set_mcp_server_enabled(server_id, enabled)


# =============================================================================
# Presets
# =============================================================================


@router.get("/{client_id}/presets", response_model=ClientPresets)
async def get_presets(
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Get all presets for the client."""
    return service.get_presets()


@router.post("/{client_id}/presets", response_model=ClientPresets)
async def create_preset(
    preset: ClientPreset,
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Create a new preset."""
    return service.add_preset(preset)


@router.put("/{client_id}/presets/{index}", response_model=ClientPresets)
async def update_preset(
    index: int,
    update: ClientPresetUpdate,
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Update a preset at the given index."""
    try:
        return service.update_preset(index, update)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{client_id}/presets/{index}", response_model=ClientPresets)
async def delete_preset(
    index: int,
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Delete a preset at the given index."""
    try:
        return service.delete_preset(index)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{client_id}/presets/{index}/activate", response_model=ClientSettings)
async def activate_preset(
    index: int,
    service: ClientSettingsService = Depends(get_service),
) -> ClientSettings:
    """Activate a preset and apply its settings."""
    try:
        return service.activate_preset(index)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# Name-based Preset Endpoints (for frontend compatibility)
# =============================================================================


@router.post("/{client_id}/presets/by-name/{name}/apply", response_model=ClientSettings)
async def apply_preset_by_name(
    name: str,
    request: Request,
    client_id: str = Depends(validate_client_id),
    service: ClientSettingsService = Depends(get_service),
) -> ClientSettings:
    """Apply a preset by name.

    This also syncs the preset's MCP server settings to the global registry
    so the chat orchestrator uses the correct MCP servers for this client.
    """
    presets = service.get_presets()
    preset_index = None
    preset = None
    for i, p in enumerate(presets.presets):
        if p.name == name:
            preset_index = i
            preset = p
            break

    if preset_index is None or preset is None:
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")

    # Activate the preset (saves to client-specific storage)
    result = service.activate_preset(preset_index)

    # Also sync MCP server settings to the global registry
    # This ensures the chat orchestrator uses the correct MCP servers
    mcp_service = get_mcp_settings_service(request)
    orchestrator = get_chat_orchestrator(request)

    if mcp_service is not None and preset.mcp_servers:
        # Build a map of preset MCP server enabled states
        preset_mcp_map = {
            s.server_id if isinstance(s, McpServerRef) else s.get("server_id"):
            s.enabled if isinstance(s, McpServerRef) else s.get("enabled", True)
            for s in preset.mcp_servers
        }

        # Patch each server's client_enabled map in the global registry
        try:
            configs = await mcp_service.get_configs()
            for config in configs:
                if config.id in preset_mcp_map:
                    new_enabled = preset_mcp_map[config.id]
                    current_enabled = config.client_enabled.get(client_id, False)
                    if current_enabled != new_enabled:
                        # Update the client_enabled map for this client
                        updated_client_enabled = dict(config.client_enabled)
                        updated_client_enabled[client_id] = new_enabled
                        await mcp_service.patch_server(
                            config.id,
                            overrides={"client_enabled": updated_client_enabled}
                        )

            # Refresh orchestrator with updated configs
            if orchestrator is not None:
                updated_configs = await mcp_service.get_configs()
                await orchestrator.apply_mcp_configs(updated_configs)

            logger.info(f"Synced MCP server settings for preset '{name}' (client: {client_id})")
        except Exception as e:
            # Log but don't fail - the preset was still applied to client storage
            logger.warning(f"Failed to sync MCP settings to global registry: {e}")

    return result


@router.delete("/{client_id}/presets/by-name/{name}", response_model=ClientPresets)
async def delete_preset_by_name(
    name: str,
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Delete a preset by name."""
    presets = service.get_presets()
    for i, preset in enumerate(presets.presets):
        if preset.name == name:
            return service.delete_preset(i)
    raise HTTPException(status_code=404, detail=f"Preset not found: {name}")


@router.post("/{client_id}/presets/by-name/{name}/set-active", response_model=ClientPresets)
async def set_active_preset_by_name(
    name: str,
    service: ClientSettingsService = Depends(get_service),
) -> ClientPresets:
    """Set a preset as the active one by name."""
    presets = service.get_presets()
    for i, preset in enumerate(presets.presets):
        if preset.name == name:
            service.activate_preset(i)
            return service.get_presets()
    raise HTTPException(status_code=404, detail=f"Preset not found: {name}")


# =============================================================================
# Full Settings Bundle
# =============================================================================


@router.get("/{client_id}", response_model=ClientSettings)
async def get_all_settings(
    service: ClientSettingsService = Depends(get_service),
) -> ClientSettings:
    """Get all settings for the client."""
    return service.get_all()


@router.post("/{client_id}/reset", response_model=ClientSettings)
async def reset_all_settings(
    service: ClientSettingsService = Depends(get_service),
) -> ClientSettings:
    """Reset all settings to defaults."""
    return service.reset_all()


__all__ = ["router"]
