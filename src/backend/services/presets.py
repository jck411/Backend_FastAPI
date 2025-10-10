"""Service for persisting configuration presets and capturing/applying snapshots."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError

from ..chat.mcp_registry import MCPServerConfig
from ..schemas.model_settings import ActiveModelSettingsPayload
from ..schemas.presets import PresetConfig, PresetListItem
from ..services.mcp_server_settings import MCPServerSettingsService
from ..services.model_settings import ModelSettingsService

logger = logging.getLogger(__name__)


class PresetService:
    """Manage named configuration presets."""

    def __init__(
        self,
        path: Path,
        model_settings: ModelSettingsService,
        mcp_settings: MCPServerSettingsService,
    ) -> None:
        self._path = path
        self._model_settings = model_settings
        self._mcp_settings = mcp_settings
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

    async def _capture_current_locked(self, name: str) -> PresetConfig:
        """Capture current config while caller holds the lock."""
        settings = await self._model_settings.get_settings()
        system_prompt = await self._model_settings.get_system_prompt()
        mcp_configs = await self._mcp_settings.get_configs()

        now = datetime.now(timezone.utc)
        snapshot = PresetConfig(
            name=name,
            model=settings.model,
            provider=settings.provider,
            parameters=settings.parameters,
            system_prompt=system_prompt,
            mcp_servers=[cfg.model_copy(deep=True) for cfg in mcp_configs],
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
            if name in self._presets:
                self._presets.pop(name)
                self._save_to_disk()
                return True
            return False

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
        )
        await self._model_settings.replace_settings(payload)

        # Apply system prompt
        await self._model_settings.update_system_prompt(preset.system_prompt)

        # Apply MCP server configs if present
        if preset.mcp_servers is not None:
            # Persist to disk and update service
            await self._mcp_settings.replace_configs(
                [
                    MCPServerConfig.model_validate(cfg.model_dump())
                    for cfg in preset.mcp_servers
                ]
            )

        # Return a copy of the applied preset
        return await self.get_preset(name)


__all__ = ["PresetService"]
