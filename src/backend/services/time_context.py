"""Shared utilities for producing consistent time context across MCP servers."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

try:  # pragma: no cover - zoneinfo is standard from Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback when zoneinfo is unavailable
    ZoneInfo = None  # type: ignore

_LOCAL_DEFAULT = _dt.datetime.now().astimezone().tzinfo or _dt.timezone.utc
EASTERN_TIMEZONE_NAME = "America/New_York"


def resolve_timezone(
    timezone_name: Optional[str],
    fallback: Optional[_dt.tzinfo] = None,
) -> _dt.tzinfo:
    """Resolve ``timezone_name`` to a tzinfo, falling back to sensible defaults."""

    if timezone_name and ZoneInfo is not None:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            pass

    if fallback is not None:
        return fallback

    return _LOCAL_DEFAULT


@dataclass(slots=True)
class TimeSnapshot:
    """Snapshot of the current moment in UTC and a target timezone."""

    tzinfo: _dt.tzinfo
    now_utc: _dt.datetime
    now_local: _dt.datetime

    @property
    def eastern(self) -> _dt.datetime:
        """Return the time converted to US Eastern, when available."""

        timezone = resolve_timezone(EASTERN_TIMEZONE_NAME, _dt.timezone.utc)
        return self.now_utc.astimezone(timezone)

    @property
    def date(self) -> _dt.date:
        return self.now_local.date()

    @property
    def iso_local(self) -> str:
        return self.now_local.isoformat()

    @property
    def iso_utc(self) -> str:
        return self.now_utc.isoformat()

    @property
    def unix_seconds(self) -> int:
        return int(self.now_utc.timestamp())

    @property
    def unix_precise(self) -> str:
        return f"{self.now_utc.timestamp():.6f}"

    def format_time(self) -> str:
        return self.now_local.strftime("%H:%M:%S %Z")

    def timezone_display(self) -> str:
        """Return a human friendly representation of the timezone."""

        tz = self.tzinfo
        key = getattr(tz, "key", None)
        if key:
            return key
        name = tz.tzname(self.now_local)
        return name or str(tz)


def create_time_snapshot(
    timezone_name: Optional[str] = None,
    *,
    fallback: Optional[_dt.tzinfo] = None,
) -> TimeSnapshot:
    """Return a TimeSnapshot for ``timezone_name``."""

    tzinfo = resolve_timezone(timezone_name, fallback)
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    now_local = now_utc.astimezone(tzinfo)
    return TimeSnapshot(tzinfo=tzinfo, now_utc=now_utc, now_local=now_local)


def format_timezone_offset(offset: Optional[_dt.timedelta]) -> str:
    """Return an ISO-8601 style UTC offset string."""

    if offset is None:
        return "UTC+00:00"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def build_context_lines(
    snapshot: TimeSnapshot,
    *,
    include_week: bool = True,
    upcoming_anchors: Sequence[tuple[str, _dt.timedelta]] = (
        ("Tomorrow", _dt.timedelta(days=1)),
        ("Day after tomorrow", _dt.timedelta(days=2)),
        ("In 3 days", _dt.timedelta(days=3)),
        ("This weekend", _dt.timedelta(days=5)),
        ("Next week (7 days)", _dt.timedelta(weeks=1)),
        ("In 2 weeks", _dt.timedelta(weeks=2)),
    ),
) -> Iterable[str]:
    """Yield human-readable context lines for ``snapshot``."""

    today_local = snapshot.date
    yesterday = today_local - _dt.timedelta(days=1)

    yield "=" * 60
    yield "CURRENT DATE AND TIME CONTEXT"
    yield "=" * 60
    yield ""
    yield f"Today: {today_local.isoformat()} ({snapshot.now_local.strftime('%A')})"
    yield f"Yesterday: {yesterday.isoformat()} ({yesterday.strftime('%A')})"
    yield f"Current time: {snapshot.format_time()}"
    yield f"Timezone: {snapshot.timezone_display()}"
    yield f"ISO timestamp (local): {snapshot.iso_local}"
    yield f"ISO timestamp (UTC): {snapshot.iso_utc}"
    yield ""

    if include_week:
        start_of_week = today_local - _dt.timedelta(days=today_local.weekday())
        end_of_week = start_of_week + _dt.timedelta(days=6)
        yield f"Current week: {start_of_week.isoformat()} → {end_of_week.isoformat()}"
        yield f"  (Monday to Sunday)"
        yield ""

    if upcoming_anchors:
        yield "Upcoming date anchors (for calendar queries):"
        for label, delta in upcoming_anchors:
            anchor = today_local + delta
            yield f"  • {label}: {anchor.isoformat()} ({anchor.strftime('%A')})"
        yield ""
    
    yield "=" * 60
