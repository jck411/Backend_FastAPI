"""Utilities for persisting per-session conversation transcripts."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Return a timezone-aware datetime for an ISO string."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class ConversationLogWriter:
    """Persist conversation snapshots to timestamped log files."""

    def __init__(self, base_dir: Path, *, min_level: int | None) -> None:
        self._base_dir = base_dir.resolve()
        self._min_level = min_level

    async def write(
        self,
        *,
        session_id: str,
        session_created_at: str | None,
        request_snapshot: dict[str, Any],
        conversation: list[dict[str, Any]],
    ) -> Path | None:
        """Append a structured snapshot for a session if enabled."""

        # Treat the snapshot as an INFO-level event.
        if self._min_level is None or logging.INFO < self._min_level:
            return None

        timestamp = datetime.now(timezone.utc)
        created_at = _parse_iso_datetime(session_created_at) or timestamp
        created_at_utc = created_at.astimezone(timezone.utc)
        safe_session_id = session_id.replace("/", "_")

        entry = {
            "type": "conversation_snapshot",
            "logged_at": timestamp.astimezone(timezone.utc).isoformat(),
            "session_id": session_id,
            "session_created_at": session_created_at,
            "message_count": len(conversation),
            "request": request_snapshot,
            "conversation": conversation,
        }
        rendered_entry = json.dumps(entry, ensure_ascii=False, indent=2)
        local_time = created_at_utc.astimezone(EASTERN)
        local_date = local_time.strftime("%Y-%m-%d")
        tz_abbr = local_time.tzname() or "ET"
        human_time = local_time.strftime("%Y-%m-%d_%H-%M-%S")

        log_path = (
            self._base_dir
            / local_date
            / f"session_{human_time}_{tz_abbr}_{safe_session_id}.log"
        )

        delimiter = "=" * 80
        header = timestamp.astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        payload = f"{header}\n{delimiter}\n{rendered_entry}\n{delimiter}\n"

        await asyncio.to_thread(self._append_entry, log_path, payload)
        return log_path

    def _append_entry(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)


__all__ = ["ConversationLogWriter"]
