"""Service for persisting and exposing active model settings."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from pydantic import ValidationError

from ..schemas.model_settings import (
    ActiveModelSettingsPayload,
    ActiveModelSettingsResponse,
)

logger = logging.getLogger(__name__)


class ModelSettingsService:
    """Manage the active model, provider routing, and hyperparameters."""

    def __init__(self, path: Path, default_model: str) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._settings = ActiveModelSettingsResponse(model=default_model)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read model settings file %s: %s", self._path, exc)
            return

        try:
            loaded = ActiveModelSettingsResponse.model_validate(data)
        except ValidationError:
            try:
                payload = ActiveModelSettingsPayload.model_validate(data)
            except ValidationError as exc:  # pragma: no cover - corrupted persisted state
                logger.warning(
                    "Invalid model settings payload in %s: %s", self._path, exc
                )
                return
            loaded = ActiveModelSettingsResponse(
                **payload.model_dump(exclude_none=False),
                updated_at=datetime.now(timezone.utc),
            )

        self._settings = loaded

    def _save_to_disk(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = self._settings.model_dump(exclude_none=True)
        data["updated_at"] = self._settings.updated_at.isoformat()
        serialized = json.dumps(data, indent=2, sort_keys=True)
        self._path.write_text(serialized + "\n", encoding="utf-8")

    async def get_settings(self) -> ActiveModelSettingsResponse:
        async with self._lock:
            return self._settings.model_copy(deep=True)

    async def replace_settings(
        self, payload: ActiveModelSettingsPayload
    ) -> ActiveModelSettingsResponse:
        async with self._lock:
            self._settings = ActiveModelSettingsResponse(
                **payload.model_dump(exclude_none=False),
                updated_at=datetime.now(timezone.utc),
            )
            self._save_to_disk()
            return self._settings.model_copy(deep=True)

    async def get_openrouter_overrides(self) -> Tuple[str, Dict[str, Any]]:
        """Return the active model id and OpenRouter payload overrides."""

        settings = await self.get_settings()
        overrides = settings.as_openrouter_overrides()
        return settings.model, overrides


__all__ = ["ModelSettingsService"]
