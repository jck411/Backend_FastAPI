"""Service for managing kiosk presets persistence."""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.schemas.kiosk_presets import (
    KioskPreset,
    KioskPresets,
    KioskPresetUpdate,
)

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent.parent / "data" / "kiosk_presets.json"


class KioskPresetsService:
    """Service for managing kiosk presets persistence."""

    def __init__(self, settings_path: Optional[Path] = None):
        self._path = settings_path or _SETTINGS_FILE
        self._cached: Optional[KioskPresets] = None

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_presets(self) -> KioskPresets:
        """Load presets from file or return defaults."""
        if self._cached is not None:
            return self._cached

        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._cached = KioskPresets.model_validate(data)
                logger.info(f"Loaded kiosk presets from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load kiosk presets: {e}, using defaults")
                self._cached = KioskPresets()
        else:
            self._cached = KioskPresets()
            logger.info("Using default kiosk presets")

        return self._cached

    def update_preset(self, update: KioskPresetUpdate) -> KioskPresets:
        """Update a single preset by index."""
        current = self.get_presets()

        # Ensure we have enough presets
        while len(current.presets) <= update.index:
            current.presets.append(
                KioskPreset(
                    name=f"Preset {len(current.presets) + 1}",
                    model="openai/gpt-4o-mini",
                    system_prompt="You are a helpful assistant.",
                    temperature=0.7,
                    max_tokens=500,
                )
            )

        current.presets[update.index] = update.preset
        self._save(current)
        return current

    def activate_preset(self, index: int) -> KioskPresets:
        """Set the active preset index."""
        current = self.get_presets()
        current.active_index = max(0, min(index, len(current.presets) - 1))
        self._save(current)
        return current

    def get_active_preset(self) -> KioskPreset:
        """Get the currently active preset."""
        presets = self.get_presets()
        return presets.presets[presets.active_index]

    def reset_to_defaults(self) -> KioskPresets:
        """Reset presets to defaults."""
        defaults = KioskPresets()
        self._save(defaults)
        return defaults

    def _save(self, presets: KioskPresets) -> None:
        """Persist presets to file."""
        self._ensure_data_dir()
        self._path.write_text(presets.model_dump_json(indent=2))
        self._cached = presets
        logger.info(f"Saved kiosk presets to {self._path}")


# Singleton instance
_service: Optional[KioskPresetsService] = None


def get_kiosk_presets_service() -> KioskPresetsService:
    """Get the singleton kiosk presets service instance."""
    global _service
    if _service is None:
        _service = KioskPresetsService()
    return _service
