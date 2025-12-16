"""Kiosk LLM settings service for persisting OpenRouter configuration."""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.schemas.kiosk_llm_settings import KioskLlmSettings, KioskLlmSettingsUpdate

logger = logging.getLogger(__name__)

# Default storage path
_DATA_DIR = Path(__file__).parent.parent / "data"
_SETTINGS_FILE = _DATA_DIR / "kiosk_llm_settings.json"


class KioskLlmSettingsService:
    """Service for managing kiosk LLM settings persistence."""

    def __init__(self, settings_path: Optional[Path] = None):
        self._path = settings_path or _SETTINGS_FILE
        self._cached: Optional[KioskLlmSettings] = None

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_settings(self) -> KioskLlmSettings:
        """Load settings from file or return defaults."""
        if self._cached is not None:
            return self._cached

        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._cached = KioskLlmSettings.model_validate(data)
                logger.info(f"Loaded kiosk LLM settings from {self._path}")
            except Exception as e:
                logger.warning(f"Failed to load kiosk LLM settings: {e}, using defaults")
                self._cached = KioskLlmSettings()
        else:
            self._cached = KioskLlmSettings()
            logger.info("Using default kiosk LLM settings")

        return self._cached

    def update_settings(self, update: KioskLlmSettingsUpdate) -> KioskLlmSettings:
        """Update settings with partial data and persist to file."""
        current = self.get_settings()

        # Apply non-None updates
        update_data = update.model_dump(exclude_none=True)
        merged = current.model_copy(update=update_data)

        self._save(merged)
        return merged

    def reset_to_defaults(self) -> KioskLlmSettings:
        """Reset settings to defaults."""
        defaults = KioskLlmSettings()
        self._save(defaults)
        return defaults

    def _save(self, settings: KioskLlmSettings) -> None:
        """Persist settings to file."""
        self._ensure_data_dir()
        self._path.write_text(settings.model_dump_json(indent=2))
        self._cached = settings
        logger.info(f"Saved kiosk LLM settings to {self._path}")


# Singleton instance
_instance: Optional[KioskLlmSettingsService] = None


def get_kiosk_llm_settings_service() -> KioskLlmSettingsService:
    """Get the singleton service instance."""
    global _instance
    if _instance is None:
        _instance = KioskLlmSettingsService()
    return _instance


__all__ = ["KioskLlmSettingsService", "get_kiosk_llm_settings_service"]
