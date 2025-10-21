"""Shared utilities for task scheduling and time normalization."""

from __future__ import annotations

import datetime
from typing import Optional


class _FallbackParser:
    @staticmethod
    def parse(timestr: str) -> datetime.datetime:
        return datetime.datetime.fromisoformat(timestr.replace("Z", "+00:00"))


try:  # Prefer python-dateutil when available for robust parsing.
    from dateutil import parser as _dateutil_parser  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    _dateutil_parser = None


def _parse(timestr: str) -> datetime.datetime:
    if _dateutil_parser is not None:
        return _dateutil_parser.parse(timestr)  # type: ignore[no-any-return]
    return _FallbackParser.parse(timestr)


def parse_rfc3339_datetime(value: Optional[str]) -> Optional[datetime.datetime]:
    """Best-effort conversion of an RFC3339 string to an aware datetime."""

    if not value:
        return None

    try:
        parsed = _parse(value)
    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    else:
        parsed = parsed.astimezone(datetime.timezone.utc)

    return parsed


def normalize_rfc3339(dt_value: datetime.datetime) -> str:
    """Return an RFC3339 string in canonical UTC form."""

    normalized = dt_value.astimezone(datetime.timezone.utc).isoformat()
    if normalized.endswith("+00:00"):
        normalized = normalized[:-6] + "Z"
    return normalized


def compute_task_window(
    time_min_rfc: Optional[str], time_max_rfc: Optional[str]
) -> tuple[Optional[datetime.datetime], datetime.datetime, Optional[datetime.datetime]]:
    """Determine the primary task window and overdue cutoff.

    Previous behavior limited overdue tasks to the last ~14 days, which caused
    older overdue items to be omitted from aggregated schedule views. To ensure
    overdue tasks are represented more completely while maintaining performance,
    widen the lookback window to a sensible default and bias further based on
    the provided start date when available.
    """

    now = datetime.datetime.now(datetime.timezone.utc)
    start_dt = parse_rfc3339_datetime(time_min_rfc)
    end_dt = parse_rfc3339_datetime(time_max_rfc)

    if end_dt is None:
        base = start_dt if start_dt and start_dt > now else now
        end_dt = base + datetime.timedelta(days=7)

    if end_dt < now:
        end_dt = now

    # Remove past-due lookback boundaries: include all historical overdue tasks.
    # Returning None signals callers to avoid setting a dueMin filter.
    past_due_cutoff: Optional[datetime.datetime] = None

    return start_dt, end_dt, past_due_cutoff


def parse_time_string(time_str: Optional[str]) -> Optional[str]:
    """Convert keywords like 'today' or 'tomorrow' to RFC3339 timestamps.

    Keywords are rendered using the local timezone offset (e.g., T00:00:00-04:00)
    rather than UTC Z to reflect the user's local day boundaries.
    """

    if not time_str:
        return None

    lowered = time_str.lower()
    today = datetime.date.today()

    if lowered == "today":
        date_obj = today
    elif lowered == "tomorrow":
        date_obj = today + datetime.timedelta(days=1)
    elif lowered == "yesterday":
        date_obj = today - datetime.timedelta(days=1)
    elif lowered == "next_week":
        date_obj = today + datetime.timedelta(days=7)
    elif lowered == "next_month":
        next_month = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        date_obj = next_month
    elif lowered == "next_year":
        date_obj = today.replace(year=today.year + 1)
    else:
        try:
            date_obj = datetime.date.fromisoformat(time_str)
        except ValueError:
            try:
                dt = datetime.datetime.fromisoformat(time_str)
            except ValueError:
                return time_str
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")

    # Build a midnight datetime with the local timezone offset
    local_tz = datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc
    local_midnight = datetime.datetime(
        date_obj.year, date_obj.month, date_obj.day, 0, 0, 0, tzinfo=local_tz
    )
    return local_midnight.astimezone(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
