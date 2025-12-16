"""Kiosk TTS settings service for persisting voice synthesis configuration."""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.schemas.kiosk_tts_settings import KioskTtsSettings, KioskTtsSettingsUpdate

logger = logging.getLogger(__name__)

# Default storage path
_DATA_DIR = Path(__file__).parent.parent / "data"
_SETTINGS_FILE = _DATA_DIR / "kiosk_tts_settings.json"


class KioskTtsSettingsService:
    """Service for managing kiosk TTS settings persistence."""

    def __init__(self, settings_path: Optional[Path] = None):
        self._path = settings_path or _SETTINGS_FILE
        self._cached: Optional[KioskTtsSettings] = None

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_settings(self) -> KioskTtsSettings:
        """Load settings from file or return defaults."""
        if self._cached is not None:
            return self._cached

        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._cached = KioskTtsSettings.model_validate(data)
                logger.info(f"Loaded kiosk TTS settings from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load kiosk TTS settings: {e}, using defaults")
                self._cached = KioskTtsSettings()
        else:
            self._cached = KioskTtsSettings()
            logger.info("Using default kiosk TTS settings")

        return self._cached

    def update_settings(self, update: KioskTtsSettingsUpdate) -> KioskTtsSettings:
        """Update settings with partial data and persist to file."""
        current = self.get_settings()

        # Apply non-None updates
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)

        self._save(merged)
        return merged

    def reset_to_defaults(self) -> KioskTtsSettings:
        """Reset settings to defaults."""
        defaults = KioskTtsSettings()
        self._save(defaults)
        return defaults

    def _save(self, settings: KioskTtsSettings) -> None:
        """Persist settings to file."""
        self._ensure_data_dir()
        self._path.write_text(settings.model_dump_json(indent=2))
        self._cached = settings
        logger.info(f"Saved kiosk TTS settings to {self._path}")


# Singleton instance
_instance: Optional[KioskTtsSettingsService] = None


def get_kiosk_tts_settings_service() -> KioskTtsSettingsService:
    """Get the singleton service instance."""
    global _instance
    if _instance is None:
        _instance = KioskTtsSettingsService()
    return _instance
