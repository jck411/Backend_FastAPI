"""Helpers for parsing the simple logging settings file."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

_LEVEL_MAP: dict[str, int | None] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "off": None,
}

_DEFAULT_KEYS = ("terminal", "sessions", "conversations")
_DEFAULT_LEVEL = "info"


@dataclass(frozen=True)
class LoggingSettings:
    terminal_level: int | None
    sessions_level: int | None
    conversations_level: int | None


def _normalize_level(value: str) -> str:
    return value.strip().lower()


def _resolve_level(value: str) -> int | None:
    return _LEVEL_MAP.get(_normalize_level(value), _LEVEL_MAP[_DEFAULT_LEVEL])


def parse_logging_settings(path: Path) -> LoggingSettings:
    """Parse the human-readable logging settings file."""

    levels: dict[str, int | None] = {
        key: _LEVEL_MAP[_DEFAULT_LEVEL] for key in _DEFAULT_KEYS
    }

    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = (part.strip() for part in line.split("=", 1))
            normalized_key = key.lower()
            if normalized_key not in _DEFAULT_KEYS:
                continue
            levels[normalized_key] = _resolve_level(value)

    return LoggingSettings(
        terminal_level=levels["terminal"],
        sessions_level=levels["sessions"],
        conversations_level=levels["conversations"],
    )


__all__ = ["LoggingSettings", "parse_logging_settings"]
