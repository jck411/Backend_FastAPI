"""Custom logging handler utilities."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


_EASTERN = ZoneInfo("America/New_York")


class DateStampedFileHandler(logging.FileHandler):
    """File handler that stores logs under date-stamped directories."""

    def __init__(
        self,
        filename: str | None = None,
        *,
        directory: str | Path | None = None,
        prefix: str | None = None,
        encoding: str | None = "utf-8",
        mode: str = "a",
        delay: bool = False,
        errors: Optional[str] = None,
        current_time: datetime | None = None,
    ) -> None:
        timestamp = (current_time or datetime.now(timezone.utc)).astimezone(
            timezone.utc
        )

        base_dir: Path
        base_prefix: str

        if filename:
            filename_path = Path(filename)
            if filename_path.suffix:
                base_dir = filename_path.parent if filename_path.parent else Path.cwd()
                derived = filename_path.stem or "app"
                base_prefix = prefix or derived
            else:
                base_dir = filename_path
                base_prefix = prefix or "app"
        elif directory:
            base_dir = Path(directory)
            base_prefix = prefix or "app"
        else:
            base_dir = Path("logs/app")
            base_prefix = prefix or "app"

        base_dir = base_dir.resolve()
        local_time = timestamp.astimezone(_EASTERN)
        tz_abbr = local_time.tzname() or "ET"
        date_folder = local_time.strftime("%Y-%m-%d")
        human_time = local_time.strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"{base_prefix}_{human_time}_{tz_abbr}.log"
        log_path = (base_dir / date_folder / file_name).resolve()

        log_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(
            log_path,
            mode=mode,
            encoding=encoding,
            delay=delay,
            errors=errors,
        )


__all__ = ["DateStampedFileHandler"]
