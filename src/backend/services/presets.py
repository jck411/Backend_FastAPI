"""Service for persisting configuration presets and capturing/applying snapshots."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from pydantic import ValidationError

from ..chat.mcp_registry import MCPServerConfig
from ..schemas.model_settings import ActiveModelSettingsPayload
from ..schemas.presets import PresetConfig, PresetListItem
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService

if TYPE_CHECKING:
    from ..services.suggestions import SuggestionsService

logger = logging.getLogger(__name__)


class PresetService:
    """Manage named configuration presets."""

    def __init__(
        self,
        path: Path,
        model_settings: ModelSettingsService,
        mcp_settings: MCPServerSettingsService,
        suggestions_service: SuggestionsService | None = None,
    ) -> None:
        self._path = path
        self._model_settings = model_settings
        self._mcp_settings = mcp_settings
        self._suggestions_service = suggestions_service
        self._lock = asyncio.Lock()
        self._presets: Dict[str, PresetConfig] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load presets from disk, tolerating multiple shapes."""
        if not self._path.exists():
            self._presets = {}
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read presets file %s: %s", self._path, exc)
            self._presets = {}
            return

        if isinstance(raw, dict):
            items = raw.get("presets", [])
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        loaded: Dict[str, PresetConfig] = {}
        for item in items:
            try:
                preset = PresetConfig.model_validate(item)
            except ValidationError as exc:
                logger.warning("Skipping invalid preset entry: %s", exc)
                continue
            loaded[preset.name] = preset

        self._presets = loaded

    def _save_to_disk(self) -> None:
        payload = {
            "presets": [
                preset.model_dump(mode="json", exclude_none=True)
                for preset in self._presets.values()
            ]
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        self._path.write_text(serialized + "\n", encoding="utf-8")

    async def list_presets(self) -> List[PresetListItem]:
        async with self._lock:
            items = [
                PresetListItem(
                    name=preset.name,
                    model=preset.model,
                    is_default=preset.is_default,
                    created_at=preset.created_at,
                    updated_at=preset.updated_at,
                )
                for preset in self._presets.values()
            ]
            # Sort alphabetically by name for stable UI
            items.sort(key=lambda item: item.name.lower())
            return items

    async def get_preset(self, name: str) -> PresetConfig:
        async with self._lock:
            preset = self._presets.get(name)
            if preset is None:
                raise KeyError(f"Unknown preset: {name}")
            return preset.model_copy(deep=True)

    async def get_default_preset(self) -> PresetConfig | None:
        """Get the default preset if one is set."""
        async with self._lock:
            for preset in self._presets.values():
                if preset.is_default:
                    return preset.model_copy(deep=True)
            return None

    async def set_default(self, name: str) -> PresetConfig:
        """Mark a preset as the default. Only one preset can be default at a time."""
        async with self._lock:
            preset = self._presets.get(name)
            if preset is None:
                raise KeyError(f"Unknown preset: {name}")

            # Clear any existing default
            for existing_preset in self._presets.values():
                if existing_preset.is_default:
                    existing_preset.is_default = False

            # Set new default
            preset.is_default = True
            preset.updated_at = datetime.now(timezone.utc)
            self._save_to_disk()
            return preset.model_copy(deep=True)

    async def _capture_current_locked(self, name: str) -> PresetConfig:
        """Capture current config while caller holds the lock."""
        settings = await self._model_settings.get_settings()
        system_prompt = await self._model_settings.get_system_prompt()
        mcp_configs = await self._mcp_settings.get_configs()

        # Capture suggestions if service is available
        suggestions = None
        if self._suggestions_service is not None:
            suggestions = await self._suggestions_service.get_suggestions()

        now = datetime.now(timezone.utc)
        snapshot = PresetConfig(
            name=name,
            model=settings.model,
            provider=settings.provider,
            parameters=settings.parameters,
            supports_tools=settings.supports_tools,
            system_prompt=system_prompt,
            mcp_servers=[cfg.model_copy(deep=True) for cfg in mcp_configs],
            suggestions=suggestions if suggestions else None,
            created_at=now,
            updated_at=now,
        )
        return snapshot

    async def create_from_current(self, name: str) -> PresetConfig:
        """Create a new preset from current configuration."""
        async with self._lock:
            if name in self._presets:
                raise ValueError(f"Preset already exists: {name}")
            snapshot = await self._capture_current_locked(name)
            self._presets[name] = snapshot
            self._save_to_disk()
            return snapshot.model_copy(deep=True)

    async def save_snapshot(self, name: str) -> PresetConfig:
        """Overwrite an existing preset with a new snapshot of current configuration."""
        async with self._lock:
            existing = self._presets.get(name)
            if existing is None:
                raise KeyError(f"Unknown preset: {name}")
            snapshot = await self._capture_current_locked(name)
            snapshot.created_at = existing.created_at
            snapshot.updated_at = datetime.now(timezone.utc)
            self._presets[name] = snapshot
            self._save_to_disk()
            return snapshot.model_copy(deep=True)

    async def delete(self, name: str) -> bool:
        async with self._lock:
            preset = self._presets.get(name)
            if preset is None:
                return False
            if preset.is_default:
                raise ValueError(f"Cannot delete default preset: {name}")
            self._presets.pop(name)
            self._save_to_disk()
            return True

    async def apply(self, name: str) -> PresetConfig:
        """Apply a preset to the running system (persisting changes via underlying services)."""
        async with self._lock:
            preset = self._presets.get(name)
            if preset is None:
                raise KeyError(f"Unknown preset: {name}")

        # Apply model/provider/parameters
        payload = ActiveModelSettingsPayload(
            model=preset.model,
            provider=preset.provider,
            parameters=preset.parameters,
            supports_tools=preset.supports_tools,
        )
        await self._model_settings.replace_settings(payload)

        # Apply system prompt
        await self._model_settings.update_system_prompt(preset.system_prompt)

        # Apply MCP server configs if present
        if preset.mcp_servers is not None:
            # Get current configs to preserve servers not in the preset
            current_configs = await self._mcp_settings.get_configs()
            preset_ids = {cfg.id for cfg in preset.mcp_servers}

            # Keep servers from current config that aren't in the preset
            # This preserves fallback servers and any servers added outside presets
            preserved = [cfg for cfg in current_configs if cfg.id not in preset_ids]

            # Combine preserved servers with preset servers
            merged_configs = preserved + [
                MCPServerConfig.model_validate(cfg.model_dump())
                for cfg in preset.mcp_servers
            ]

            # Persist to disk and update service
            await self._mcp_settings.replace_configs(merged_configs)

        # Apply suggestions if service is available
        # If preset has no suggestions, replace with empty list to clear existing ones
        if self._suggestions_service is not None:
            suggestions_to_apply = (
                preset.suggestions if preset.suggestions is not None else []
            )
            await self._suggestions_service.replace_suggestions(suggestions_to_apply)

        # Return a copy of the applied preset
        return await self.get_preset(name)


__all__ = ["PresetService"]
