"""Generic client settings service.

This service is parameterized by client_id and handles all settings
operations for any client (kiosk, svelte, cli, etc.).
"""

import json
import logging
from pathlib import Path
from typing import Optional

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

logger = logging.getLogger(__name__)

# Default data directory
_DATA_DIR = Path(__file__).parent.parent / "data" / "clients"


class ClientSettingsService:
    """Service for managing settings for a specific client."""

    def __init__(self, client_id: str, data_dir: Optional[Path] = None):
        self.client_id = client_id
        self.base_path = (data_dir or _DATA_DIR) / client_id
        self._cache: dict[str, object] = {}

    def _ensure_dir(self) -> None:
        """Ensure the client data directory exists."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, name: str) -> Path:
        """Get path to a settings file."""
        return self.base_path / f"{name}.json"

    def _load_json(self, name: str) -> Optional[dict]:
        """Load JSON from a settings file."""
        path = self._file_path(name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return None

    def _save_json(self, name: str, data: dict) -> None:
        """Save JSON to a settings file."""
        self._ensure_dir()
        path = self._file_path(name)
        path.write_text(json.dumps(data, indent=2))
        logger.debug(f"Saved {path}")

    # =========================================================================
    # LLM Settings
    # =========================================================================

    def get_llm(self) -> LlmSettings:
        """Get LLM settings for this client."""
        if "llm" in self._cache:
            return self._cache["llm"]  # type: ignore

        data = self._load_json("llm")
        if data:
            try:
                settings = LlmSettings.model_validate(data)
            except Exception as e:
                logger.warning(f"Invalid LLM settings for {self.client_id}: {e}")
                settings = LlmSettings()
        else:
            settings = LlmSettings()

        self._cache["llm"] = settings
        return settings

    def update_llm(self, update: LlmSettingsUpdate) -> LlmSettings:
        """Update LLM settings with partial data."""
        current = self.get_llm()
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)
        self._save_json("llm", merged.model_dump())
        self._cache["llm"] = merged
        return merged

    def replace_llm(self, settings: LlmSettings) -> LlmSettings:
        """Replace LLM settings entirely."""
        self._save_json("llm", settings.model_dump())
        self._cache["llm"] = settings
        return settings

    # =========================================================================
    # STT Settings
    # =========================================================================

    def get_stt(self) -> SttSettings:
        """Get STT settings for this client."""
        if "stt" in self._cache:
            return self._cache["stt"]  # type: ignore

        data = self._load_json("stt")
        if data:
            try:
                settings = SttSettings.model_validate(data)
            except Exception as e:
                logger.warning(f"Invalid STT settings for {self.client_id}: {e}")
                settings = SttSettings()
        else:
            settings = SttSettings()

        self._cache["stt"] = settings
        return settings

    def update_stt(self, update: SttSettingsUpdate) -> SttSettings:
        """Update STT settings with partial data."""
        current = self.get_stt()
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)
        self._save_json("stt", merged.model_dump())
        self._cache["stt"] = merged
        return merged

    # =========================================================================
    # TTS Settings
    # =========================================================================

    def get_tts(self) -> TtsSettings:
        """Get TTS settings for this client."""
        if "tts" in self._cache:
            return self._cache["tts"]  # type: ignore

        data = self._load_json("tts")
        if data:
            try:
                settings = TtsSettings.model_validate(data)
            except Exception as e:
                logger.warning(f"Invalid TTS settings for {self.client_id}: {e}")
                settings = TtsSettings()
        else:
            settings = TtsSettings()

        self._cache["tts"] = settings
        return settings

    def update_tts(self, update: TtsSettingsUpdate) -> TtsSettings:
        """Update TTS settings with partial data."""
        current = self.get_tts()
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)
        self._save_json("tts", merged.model_dump())
        self._cache["tts"] = merged
        return merged

    # =========================================================================
    # MCP Servers
    # =========================================================================

    def get_mcp_servers(self) -> list[McpServerRef]:
        """Get MCP server references for this client."""
        if "mcp_servers" in self._cache:
            return self._cache["mcp_servers"]  # type: ignore

        data = self._load_json("mcp_servers")
        if data and isinstance(data, dict) and "servers" in data:
            try:
                servers = [McpServerRef.model_validate(s) for s in data["servers"]]
            except Exception as e:
                logger.warning(f"Invalid MCP servers for {self.client_id}: {e}")
                servers = []
        else:
            servers = []

        self._cache["mcp_servers"] = servers
        return servers

    def update_mcp_servers(self, update: McpServersUpdate) -> list[McpServerRef]:
        """Replace MCP server references."""
        servers = update.servers
        self._save_json("mcp_servers", {"servers": [s.model_dump() for s in servers]})
        self._cache["mcp_servers"] = servers
        return servers

    def set_mcp_server_enabled(self, server_id: str, enabled: bool) -> list[McpServerRef]:
        """Enable or disable a specific MCP server."""
        current = self.get_mcp_servers()
        found = False
        for server in current:
            if server.server_id == server_id:
                server.enabled = enabled
                found = True
                break
        if not found:
            current.append(McpServerRef(server_id=server_id, enabled=enabled))
        self._save_json("mcp_servers", {"servers": [s.model_dump() for s in current]})
        self._cache["mcp_servers"] = current
        return current

    # =========================================================================
    # UI Settings
    # =========================================================================

    def get_ui(self) -> UiSettings:
        """Get UI settings for this client."""
        if "ui" in self._cache:
            return self._cache["ui"]  # type: ignore

        data = self._load_json("ui")
        if data:
            try:
                settings = UiSettings.model_validate(data)
            except Exception as e:
                logger.warning(f"Invalid UI settings for {self.client_id}: {e}")
                settings = UiSettings()
        else:
            settings = UiSettings()

        self._cache["ui"] = settings
        return settings

    def update_ui(self, update: UiSettingsUpdate) -> UiSettings:
        """Update UI settings with partial data."""
        current = self.get_ui()
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)
        self._save_json("ui", merged.model_dump())
        self._cache["ui"] = merged
        return merged

    # =========================================================================
    # Presets
    # =========================================================================

    def get_presets(self) -> ClientPresets:
        """Get all presets for this client."""
        if "presets" in self._cache:
            return self._cache["presets"]  # type: ignore

        data = self._load_json("presets")
        if data:
            try:
                presets = ClientPresets.model_validate(data)
            except Exception as e:
                logger.warning(f"Invalid presets for {self.client_id}: {e}")
                presets = ClientPresets()
        else:
            presets = ClientPresets()

        self._cache["presets"] = presets
        return presets

    def update_preset(self, index: int, update: ClientPresetUpdate) -> ClientPresets:
        """Update a preset at the given index."""
        presets = self.get_presets()
        if index < 0 or index >= len(presets.presets):
            raise ValueError(f"Preset index {index} out of range")

        preset = presets.presets[index]
        update_data = update.model_dump(exclude_none=True)

        # Handle nested LLM update
        if "llm" in update_data and update_data["llm"]:
            llm_update = update_data.pop("llm")
            preset.llm = preset.llm.model_copy(update=llm_update)
        # Handle nested STT update
        if "stt" in update_data and update_data["stt"]:
            stt_update = update_data.pop("stt")
            if preset.stt:
                preset.stt = preset.stt.model_copy(update=stt_update)
            else:
                preset.stt = SttSettings.model_validate(stt_update)
        # Handle nested TTS update
        if "tts" in update_data and update_data["tts"]:
            tts_update = update_data.pop("tts")
            if preset.tts:
                preset.tts = preset.tts.model_copy(update=tts_update)
            else:
                preset.tts = TtsSettings.model_validate(tts_update)
        # Handle remaining fields
        for key, value in update_data.items():
            setattr(preset, key, value)

        self._save_presets(presets)
        return presets

    def activate_preset(self, index: int) -> ClientSettings:
        """Activate a preset and apply its settings."""
        presets = self.get_presets()
        if index < 0 or index >= len(presets.presets):
            raise ValueError(f"Preset index {index} out of range")

        preset = presets.presets[index]
        presets.active_index = index
        self._save_presets(presets)

        # Apply preset settings
        self.replace_llm(preset.llm)
        if preset.stt:
            self._save_json("stt", preset.stt.model_dump())
            self._cache["stt"] = preset.stt
        if preset.tts:
            self._save_json("tts", preset.tts.model_dump())
            self._cache["tts"] = preset.tts
        if preset.mcp_servers:
            # Ensure all items are McpServerRef models, then serialize
            validated_servers = [
                s if isinstance(s, McpServerRef) else McpServerRef.model_validate(s)
                for s in preset.mcp_servers
            ]
            self._save_json("mcp_servers", {"servers": [s.model_dump() for s in validated_servers]})
            self._cache["mcp_servers"] = validated_servers




        return ClientSettings(
            llm=preset.llm,
            stt=preset.stt,
            tts=preset.tts,
            mcp_servers=preset.mcp_servers,
        )

    def add_preset(self, preset: ClientPreset) -> ClientPresets:
        """Add a new preset."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        # Set timestamps if not provided
        if preset.created_at is None:
            preset = ClientPreset(
                name=preset.name,
                llm=preset.llm,
                stt=preset.stt,
                tts=preset.tts,
                mcp_servers=preset.mcp_servers,
                created_at=now,
                updated_at=now,
            )
        presets = self.get_presets()
        presets.presets.append(preset)
        self._save_presets(presets)
        return presets


    def delete_preset(self, index: int) -> ClientPresets:
        """Delete a preset at the given index."""
        presets = self.get_presets()
        if index < 0 or index >= len(presets.presets):
            raise ValueError(f"Preset index {index} out of range")
        presets.presets.pop(index)
        # Adjust active index if needed
        if presets.active_index is not None:
            if presets.active_index == index:
                presets.active_index = None
            elif presets.active_index > index:
                presets.active_index -= 1
        self._save_presets(presets)
        return presets

    def _save_presets(self, presets: ClientPresets) -> None:
        """Save presets to file."""
        self._save_json("presets", presets.model_dump())
        self._cache["presets"] = presets

    # =========================================================================
    # Full Settings Bundle
    # =========================================================================

    def get_all(self) -> ClientSettings:
        """Get complete settings bundle."""
        return ClientSettings(
            llm=self.get_llm(),
            stt=self.get_stt(),
            tts=self.get_tts(),
            ui=self.get_ui(),
            mcp_servers=self.get_mcp_servers(),
        )

    def reset_all(self) -> ClientSettings:
        """Reset all settings to defaults."""
        self._cache.clear()
        for name in ["llm", "stt", "tts", "ui", "mcp_servers", "presets"]:
            path = self._file_path(name)
            if path.exists():
                path.unlink()
        return self.get_all()


# =============================================================================
# Service Registry
# =============================================================================

_services: dict[str, ClientSettingsService] = {}


def get_client_settings_service(client_id: str) -> ClientSettingsService:
    """Get or create a settings service for the given client."""
    if client_id not in _services:
        _services[client_id] = ClientSettingsService(client_id)
    return _services[client_id]


def clear_service_cache() -> None:
    """Clear the service registry (for testing)."""
    _services.clear()


__all__ = [
    "ClientSettingsService",
    "get_client_settings_service",
    "clear_service_cache",
]
