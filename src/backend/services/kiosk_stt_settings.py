"""Kiosk STT settings service for persisting Deepgram Flux configuration."""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.schemas.kiosk_stt_settings import KioskSttSettings, KioskSttSettingsUpdate

logger = logging.getLogger(__name__)

# Default storage path
_DATA_DIR = Path(__file__).parent.parent / "data"
_SETTINGS_FILE = _DATA_DIR / "kiosk_stt_settings.json"


class KioskSttSettingsService:
    """Service for managing kiosk STT settings persistence."""

    def __init__(self, settings_path: Optional[Path] = None):
        self._path = settings_path or _SETTINGS_FILE
        self._cached: Optional[KioskSttSettings] = None

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_settings(self) -> KioskSttSettings:
        """Load settings from file or return defaults."""
        if self._cached is not None:
            return self._cached

        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._cached = KioskSttSettings.model_validate(data)
                logger.info(f"Loaded kiosk STT settings from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load kiosk STT settings: {e}, using defaults")
                self._cached = KioskSttSettings()
        else:
            self._cached = KioskSttSettings()
            logger.info("Using default kiosk STT settings")

        return self._cached

    def update_settings(self, update: KioskSttSettingsUpdate) -> KioskSttSettings:
        """Update settings with partial data and persist to file."""
        current = self.get_settings()

        # Apply non-None updates
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)

        self._save(merged)
        return merged

    def reset_to_defaults(self) -> KioskSttSettings:
        """Reset settings to defaults."""
        defaults = KioskSttSettings()
        self._save(defaults)
        return defaults

    def _save(self, settings: KioskSttSettings) -> None:
        """Persist settings to file."""
        self._ensure_data_dir()
        self._path.write_text(settings.model_dump_json(indent=2))
        self._cached = settings
        logger.info(f"Saved kiosk STT settings to {self._path}")


# Singleton instance
_instance: Optional[KioskSttSettingsService] = None


def get_kiosk_stt_settings_service() -> KioskSttSettingsService:
    """Get the singleton service instance."""
    global _instance
    if _instance is None:
        _instance = KioskSttSettingsService()
    return _instance
