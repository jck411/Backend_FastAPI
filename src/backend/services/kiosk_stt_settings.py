"""Service for managing kiosk STT settings."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ..schemas.kiosk_stt_settings import KioskSttSettingsPayload, KioskSttSettingsResponse

logger = logging.getLogger(__name__)

# Default values
DEFAULT_EOT_TIMEOUT_MS = 5000
DEFAULT_EOT_THRESHOLD = 0.7


class KioskSttSettingsService:
    """Manages kiosk STT settings persistence."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._cache: Dict[str, Any] | None = None

    def _load(self) -> Dict[str, Any]:
        """Load settings from disk."""
        if self._cache is not None:
            return self._cache

        if self._path.exists():
            try:
                with open(self._path, "r") as f:
                    self._cache = json.load(f)
                    return self._cache
            except Exception as e:
                logger.warning(f"Failed to load kiosk STT settings: {e}")

        # Return defaults
        self._cache = {
            "eot_timeout_ms": DEFAULT_EOT_TIMEOUT_MS,
            "eot_threshold": DEFAULT_EOT_THRESHOLD,
            "updated_at": None,
        }
        return self._cache

    def _save(self, data: Dict[str, Any]) -> None:
        """Save settings to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        self._cache = data

    async def get_settings(self) -> KioskSttSettingsResponse:
        """Get current STT settings."""
        data = self._load()
        return KioskSttSettingsResponse(
            eot_timeout_ms=data.get("eot_timeout_ms", DEFAULT_EOT_TIMEOUT_MS),
            eot_threshold=data.get("eot_threshold", DEFAULT_EOT_THRESHOLD),
            updated_at=data.get("updated_at"),
        )

    async def update_settings(
        self, payload: KioskSttSettingsPayload
    ) -> KioskSttSettingsResponse:
        """Update STT settings."""
        data = self._load()

        if payload.eot_timeout_ms is not None:
            data["eot_timeout_ms"] = payload.eot_timeout_ms
        if payload.eot_threshold is not None:
            data["eot_threshold"] = payload.eot_threshold

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(data)

        return KioskSttSettingsResponse(
            eot_timeout_ms=data.get("eot_timeout_ms", DEFAULT_EOT_TIMEOUT_MS),
            eot_threshold=data.get("eot_threshold", DEFAULT_EOT_THRESHOLD),
            updated_at=data.get("updated_at"),
        )

    def get_eot_timeout_ms(self) -> int:
        """Get current EOT timeout in milliseconds."""
        data = self._load()
        return data.get("eot_timeout_ms", DEFAULT_EOT_TIMEOUT_MS)

    def get_eot_threshold(self) -> float:
        """Get current EOT confidence threshold."""
        data = self._load()
        return data.get("eot_threshold", DEFAULT_EOT_THRESHOLD)


__all__ = ["KioskSttSettingsService"]
