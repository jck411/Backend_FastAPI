"""Service for managing kiosk UI settings."""

import json
import logging
from functools import lru_cache
from pathlib import Path

from backend.schemas.kiosk_ui_settings import KioskUiSettings, KioskUiSettingsUpdate

logger = logging.getLogger(__name__)


class KioskUiSettingsService:
    """Manages kiosk UI settings persistence."""

    def __init__(self, settings_path: Path | None = None):
        if settings_path is None:
            settings_path = Path(__file__).parent.parent / "data" / "kiosk_ui_settings.json"
        self.settings_path = settings_path
        self._settings: KioskUiSettings | None = None

    def get_settings(self) -> KioskUiSettings:
        """Get current UI settings, loading from disk if needed."""
        if self._settings is None:
            self._load_settings()
        return self._settings  # type: ignore

    def _load_settings(self) -> None:
        """Load settings from disk."""
        try:
            if self.settings_path.exists():
                with open(self.settings_path, "r") as f:
                    data = json.load(f)
                self._settings = KioskUiSettings(**data)
            else:
                self._settings = KioskUiSettings()
                self._save_settings()
        except Exception as e:
            logger.error(f"Failed to load kiosk UI settings: {e}")
            self._settings = KioskUiSettings()

    def _save_settings(self) -> None:
        """Save settings to disk."""
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_path, "w") as f:
                json.dump(self._settings.model_dump(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save kiosk UI settings: {e}")

    def update_settings(self, update: KioskUiSettingsUpdate) -> KioskUiSettings:
        """Update settings with partial data."""
        current = self.get_settings()
        update_data = update.model_dump(exclude_unset=True)

        if update_data:
            new_data = current.model_dump()
            new_data.update(update_data)
            self._settings = KioskUiSettings(**new_data)
            self._save_settings()

        return self._settings  # type: ignore


_service_instance: KioskUiSettingsService | None = None


def get_kiosk_ui_settings_service() -> KioskUiSettingsService:
    """Get singleton instance of the UI settings service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = KioskUiSettingsService()
    return _service_instance
