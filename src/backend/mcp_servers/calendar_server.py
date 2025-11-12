"""Custom MCP server for Google Calendar integration.

This server provides Google Calendar tools without the overhead of the full
Google Workspace MCP implementation, focused on specific calendar features.
"""

from __future__ import annotations

import asyncio
import datetime

# Standard library imports
import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, List, Optional, TypedDict

# Third party imports
if TYPE_CHECKING:

    class FastMCP:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def run(self) -> None: ...

        def tool(
            self, name: str
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...
else:
    from mcp.server.fastmcp import FastMCP

# Local imports
from backend.services.google_auth.auth import (
    DEFAULT_USER_EMAIL,
    get_calendar_service,
)
from backend.services.google_auth.auth import (
    get_tasks_service as _google_get_tasks_service,
)
from backend.tasks import (
    ScheduledTask,
    Task,
    TaskAuthorizationError,
    TaskSearchResult,
    TaskService,
    TaskServiceError,
)
from backend.tasks.utils import (
    normalize_rfc3339,
    parse_rfc3339_datetime,
)


# Define parser for date/time handling
# We define our own parser first as a fallback
class FallbackParser:
    @staticmethod
    def parse(timestr):
        """Parse datetime string to datetime object."""
        return dt.datetime.fromisoformat(timestr.replace("Z", "+00:00"))


# Set a default parser implementation
parser = FallbackParser()

# Try to import dateutil if available for better date parsing
# This is wrapped with # type: ignore to suppress the import error in static analysis
try:
    from dateutil import parser  # type: ignore
except ImportError:
    # Keep using our fallback implementation
    pass

# Create MCP server instance
mcp: FastMCP = FastMCP("custom-calendar")


def get_tasks_service(user_email: str):
    """Factory wrapper for Google Tasks service access.

    Exposed so tests can patch the task service dependency without reaching into
    lower-level modules.
    """

    return _google_get_tasks_service(user_email)


def _parse_time_string(time_str: Optional[str]) -> Optional[str]:
    """Normalize ISO-like date/time strings to RFC3339 (UTC) strings."""

    if not time_str:
        return None

    # ISO date-only
    try:
        if len(time_str) == 10 and time_str[4] == "-" and time_str[7] == "-":
            # YYYY-MM-DD
            datetime.date.fromisoformat(time_str)
            return f"{time_str}T00:00:00Z"
    except Exception:
        pass

    # Datetime with no timezone → treat as UTC
    if "T" in time_str and (
        "+" not in time_str and "-" not in time_str[10:] and "Z" not in time_str
    ):
        return time_str + "Z"

    return time_str


@dataclass
class EventInfo:
    """Simple data class for event information."""

    title: str
    start: str
    end: str
    is_all_day: bool
    calendar: str
    calendar_id: str
    id: str
    link: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    ical_uid: Optional[str] = None


class CalendarDefinition(TypedDict):
    """Typed mapping describing a known calendar."""

    id: str
    label: str
    access: str
    aliases: tuple[str, ...]


# Canonical calendar configuration for Jack's Google Workspace
DEFAULT_CALENDAR_DEFINITIONS: tuple[CalendarDefinition, ...] = (
    {
        "id": "primary",
        "label": "Your Primary Calendar",
        "access": "owner",
        "aliases": (
            "primary",
            "primary calendar",
            "main calendar",
            "default calendar",
            DEFAULT_USER_EMAIL,
        ),
    },
    {
        "id": "family08001023161820261147@group.calendar.google.com",
        "label": "Family Calendar",
        "access": "owner",
        "aliases": (
            "family",
            "family calendar",
        ),
    },
    {
        "id": "en.usa#holiday@group.v.calendar.google.com",
        "label": "Holidays in United States",
        "access": "reader",
        "aliases": (
            "holidays",
            "holiday calendar",
            "holidays in united states",
            "us holidays",
        ),
    },
    {
        "id": "4b779996b31f84a4dc520b2f0255e437863f0c826f3249c05f5f13f020fe3ba6@group.calendar.google.com",
        "label": "Mom Work Schedule",
        "access": "reader",
        "aliases": (
            "mom",
            "mom schedule",
            "mom work",
            "mom work schedule",
            "Sanja's work scheduleSanja in office",
        ),
    },
    {
        "id": "0d02885a194bb2bfab4573ac6188f079498c768aa22659656b248962d03af863@group.calendar.google.com",
        "label": "Dad Work Schedule",
        "access": "owner",
        "aliases": (
            "dad",
            "dad schedule",
            "dad work",
            "dad work schedule",
        ),
    },
)

DEFAULT_READ_CALENDAR_IDS: tuple[str, ...] = tuple(
    definition["id"] for definition in DEFAULT_CALENDAR_DEFINITIONS
)

_CALENDAR_ALIAS_TO_ID: dict[str, str] = {}
_CALENDAR_ID_TO_LABEL: dict[str, str] = {}


def _alias_key(value: str) -> str:
    """Normalize alias keys for robust matching.

    - Lowercase
    - Normalize common Unicode punctuation to ASCII
    - Collapse possessives (e.g., mom's, mom’s → mom)
    - Collapse whitespace
    """

    import unicodedata

    txt = value.strip().lower()
    # Normalize unicode quotes to ASCII
    txt = txt.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    # Remove simple possessive 's
    for who in ("mom", "dad"):
        txt = txt.replace(f"{who}'s", who)
    # Also handle the common no-apostrophe form (moms → mom, dads → dad)
    for who in ("mom", "dad"):
        txt = txt.replace(f"{who}s ", f"{who} ")
        if txt.endswith(f"{who}s"):
            txt = txt[:-1]

    # Strip most punctuation except characters that can appear in real
    # calendar IDs (e.g., '@', '+', '#', '-', '_', '.')
    allowed = set("@+#-_. ")
    txt = "".join(ch for ch in txt if ch.isalnum() or ch in allowed)
    # Collapse internal whitespace
    txt = " ".join(txt.split())
    # Fold accents
    txt = "".join(
        c for c in unicodedata.normalize("NFKD", txt) if not unicodedata.combining(c)
    )
    return txt


for definition in DEFAULT_CALENDAR_DEFINITIONS:
    cal_id = definition["id"]
    _CALENDAR_ID_TO_LABEL[cal_id] = definition["label"]
    _CALENDAR_ALIAS_TO_ID[_alias_key(cal_id)] = cal_id
    # Seed alias dictionary with provided aliases and common variants
    for alias in definition["aliases"]:
        _CALENDAR_ALIAS_TO_ID[_alias_key(alias)] = cal_id
    # Add common possessive variants for convenience
    label = definition["label"]
    _CALENDAR_ALIAS_TO_ID[_alias_key(label)] = cal_id

# Lower numbers are treated as more authoritative when deduplicating events.
CALENDAR_PRIORITIES: dict[str, int] = {
    "0d02885a194bb2bfab4573ac6188f079498c768aa22659656b248962d03af863@group.calendar.google.com": 0,
    "4b779996b31f84a4dc520b2f0255e437863f0c826f3249c05f5f13f020fe3ba6@group.calendar.google.com": 0,
    "family08001023161820261147@group.calendar.google.com": 5,
    "primary": 10,
    "en.usa#holiday@group.v.calendar.google.com": 20,
}

_DEFAULT_CALENDAR_PRIORITY = 100

AGGREGATE_CALENDAR_ALIASES: set[str] = {
    "my calendar",
    "my calendars",
    "my schedule",
    "schedule",
    "reading schedule",
}


def _normalize_calendar_id(calendar_id: str) -> str:
    """Map friendly calendar names to canonical IDs when possible."""

    normalized = _alias_key(calendar_id)
    return _CALENDAR_ALIAS_TO_ID.get(normalized, calendar_id)


def _calendar_label(calendar_id: str) -> str:
    """Return a human-friendly label for a calendar ID."""

    canonical = _CALENDAR_ALIAS_TO_ID.get(_alias_key(calendar_id), calendar_id)
    return _CALENDAR_ID_TO_LABEL.get(canonical, calendar_id)


def _should_use_aggregate(calendar_id: Optional[str]) -> bool:
    """Determine whether calls should use the default multi-calendar view."""

    if calendar_id is None:
        return True
    return calendar_id.strip().lower() in AGGREGATE_CALENDAR_ALIASES


def _resolve_calendar_id_for_write(calendar_id: Optional[str]) -> str:
    """Resolve calendar identifiers for create/update/delete operations."""

    if not calendar_id:
        return "primary"

    normalized = calendar_id.strip().lower()
    if normalized in AGGREGATE_CALENDAR_ALIASES:
        return "primary"

    return _CALENDAR_ALIAS_TO_ID.get(normalized, calendar_id)


async def _resolve_task_list_identifier(
    task_service: TaskService, identifier: str
) -> tuple[str, str] | None:
    """Resolve a task list identifier to an (id, title) pair.

    Accepts either a canonical list ID or a human-friendly title. Returns
    (id, title) when a match is found; otherwise returns None.
    """

    ident = identifier.strip()
    if not ident:
        return None

    # Fast path: try as an ID
    try:
        info = await task_service.get_task_list(ident)
        return (info.id, info.title)
    except TaskServiceError:
        pass

    # Fallback: scan lists and match by title (case-insensitive). Prefer exact
    # title matches; allow a unique substring match as a convenience.
    partial_candidates: list[tuple[str, str]] = []

    page_token: str | None = None
    while True:
        lists, next_token = await task_service.list_task_lists(
            max_results=100, page_token=page_token
        )
        for lst in lists:
            title_lower = (lst.title or "").strip().lower()
            ident_lower = ident.lower()
            if title_lower == ident_lower:
                return (lst.id, lst.title)
            if ident_lower and ident_lower in title_lower:
                partial_candidates.append((lst.id, lst.title))

        if not next_token:
            break
        page_token = next_token

    if len(partial_candidates) == 1:
        return partial_candidates[0]

    return None


def _event_sort_key(start_value: str) -> datetime.datetime:
    """Convert an event start value to a sortable datetime."""

    try:
        parsed = parser.parse(start_value)
    except Exception:
        return datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)

    return parsed


def _calendar_priority(calendar_id: str) -> int:
    """Return ordering priority for a calendar when deduplicating events."""

    return CALENDAR_PRIORITIES.get(calendar_id, _DEFAULT_CALENDAR_PRIORITY)


def _event_dedup_key(event: EventInfo) -> str:
    """Return a stable key representing the logical event."""

    if event.ical_uid:
        return event.ical_uid

    return f"{event.title}|{event.start}|{event.end}"


def _deduplicate_events(events: List[EventInfo]) -> List[EventInfo]:
    """Collapse duplicate events, preferring authoritative calendars."""

    deduped: dict[str, EventInfo] = {}
    order: List[str] = []

    for event in events:
        key = _event_dedup_key(event)
        existing = deduped.get(key)

        if existing is None:
            deduped[key] = event
            order.append(key)
            continue

        if _calendar_priority(event.calendar_id) < _calendar_priority(
            existing.calendar_id
        ):
            deduped[key] = event

    return [deduped[key] for key in order]


def _format_task_line(task: ScheduledTask) -> List[str]:
    """Produce formatted lines for a task summary."""

    prefix = "overdue" if task.is_overdue else "due"
    line = (
        f'- [Task] "{task.title}" {prefix} {task.due_display} '
        f"[List: {task.list_title}] ID: {task.id}"
    )

    if task.web_link:
        line += f" | Link: {task.web_link}"

    lines = [line]

    if task.notes:
        snippet = task.notes.strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        lines.append(f"  Notes: {snippet}")

    return lines


def _format_task_search_result(task: TaskSearchResult) -> List[str]:
    """Format a search result entry for display."""

    due_text = f" | Due: {task.due}" if task.due else ""
    completed_text = f" | Completed: {task.completed}" if task.completed else ""
    line = (
        f'- "{task.title}" [List: {task.list_title}] '
        f"Status: {task.status}{due_text}{completed_text} ID: {task.id}"
    )

    if task.web_link:
        line += f" | Link: {task.web_link}"

    lines = [line]

    if task.notes:
        snippet = task.notes.strip()
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        if snippet:
            lines.append(f"  Notes: {snippet}")

    if task.updated:
        lines.append(f"  Updated: {task.updated}")

    return lines


@mcp.tool("calendar_get_events")
async def get_events(
    user_email: str = DEFAULT_USER_EMAIL,
    calendar_id: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 25,
    query: Optional[str] = None,
    detailed: bool = False,
) -> str:
    """Retrieve calendar events. Omit calendar_id to search all household calendars,
    or provide a specific ID/friendly name like "Family Calendar" to filter.
    """

    try:
        service = get_calendar_service(user_email)

        time_min_rfc = _parse_time_string(time_min)
        if not time_min_rfc:
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(
                microsecond=0
            )
            time_min_rfc = normalize_rfc3339(now_utc)
        time_max_rfc = _parse_time_string(time_max) if time_max else None

        # Parse time bounds to datetimes for precise local filtering when
        # Google API semantics include cross-boundary events (e.g. overnight).
        range_min_dt = parse_rfc3339_datetime(time_min_rfc) if time_min_rfc else None
        range_max_dt = parse_rfc3339_datetime(time_max_rfc) if time_max_rfc else None

        aggregate = _should_use_aggregate(calendar_id)
        if aggregate:
            calendars_to_query = list(DEFAULT_READ_CALENDAR_IDS)
        else:
            if calendar_id is None:
                calendars_to_query = list(DEFAULT_READ_CALENDAR_IDS)
                aggregate = True
            else:
                resolved_calendar_id = _normalize_calendar_id(calendar_id)
                calendars_to_query = [resolved_calendar_id]

        calendar_labels = [_calendar_label(cal_id) for cal_id in calendars_to_query]

        params: dict[str, Any] = {
            "maxResults": max(max_results, 1),
            "orderBy": "startTime",
            "singleEvents": True,
        }

        if time_min_rfc:
            params["timeMin"] = time_min_rfc

        if time_max_rfc:
            params["timeMax"] = time_max_rfc

        if query:
            params["q"] = query

        events_with_keys: list[tuple[datetime.datetime, EventInfo]] = []
        warnings: list[str] = []

        for cal_id in calendars_to_query:
            try:
                events_result = await asyncio.to_thread(
                    service.events().list(calendarId=cal_id, **params).execute
                )
            except Exception as exc:
                warnings.append(f"{_calendar_label(cal_id)}: {exc}")
                continue

            google_events = events_result.get("items", [])
            calendar_name = _calendar_label(cal_id)

            for event in google_events:
                start = event.get("start", {})
                end = event.get("end", {})

                is_all_day = "date" in start

                event_start = start.get("date", start.get("dateTime", "")) or ""
                event_end = end.get("date", end.get("dateTime", "")) or ""

                event_info = EventInfo(
                    title=event.get("summary", "(No title)"),
                    start=event_start,
                    end=event_end,
                    is_all_day=is_all_day,
                    calendar=calendar_name,
                    calendar_id=cal_id,
                    id=event.get("id", ""),
                    link=event.get("htmlLink", ""),
                    location=event.get("location", None),
                    description=event.get("description", None),
                    ical_uid=event.get("iCalUID"),
                )
                # Explicitly filter timed events to avoid including items that
                # started before the requested window but overlap into it
                # (e.g., overnight shifts).
                if not is_all_day and range_min_dt is not None:
                    start_key = _event_sort_key(event_info.start)
                    if start_key < range_min_dt:
                        continue
                if not is_all_day and range_max_dt is not None:
                    start_key = _event_sort_key(event_info.start)
                    if start_key > range_max_dt:
                        continue

                events_with_keys.append((_event_sort_key(event_info.start), event_info))

        task_entries: List[ScheduledTask] = []
        truncated_tasks = 0

        if aggregate:
            task_service = TaskService(user_email, service_factory=get_tasks_service)
            try:
                task_collection = await task_service.collect_scheduled_tasks(
                    time_min_rfc, time_max_rfc, None
                )
            except TaskAuthorizationError as exc:
                warnings.append(
                    "Tasks unavailable: "
                    + str(exc)
                    + ". Open the system settings modal and click 'Connect Google Services' to refresh permissions."
                )
            except TaskServiceError as exc:
                warnings.append(f"Tasks unavailable: {exc}.")
            else:
                task_entries = task_collection.tasks
                truncated_tasks = task_collection.remaining
                warnings.extend(task_collection.warnings)

        if not events_with_keys and not task_entries:
            if warnings:
                warning_text = "; ".join(warnings)
                if aggregate:
                    return (
                        f"No events or due tasks found for {user_email} across the "
                        f"configured calendars ({', '.join(calendar_labels)}). "
                        f"Issues encountered: {warning_text}."
                    )
                return (
                    f"No events found for {user_email} in calendar "
                    f"'{calendar_labels[0]}'. Issues encountered: {warning_text}."
                )

            if aggregate:
                return (
                    f"No events or due tasks found for {user_email} across the "
                    f"configured calendars ({', '.join(calendar_labels)})."
                )

            return (
                f"No events found for {user_email} in calendar '{calendar_labels[0]}'."
            )

        events_with_keys.sort(key=lambda item: item[0])
        ordered_events = [event for _, event in events_with_keys]

        if aggregate:
            ordered_events = _deduplicate_events(ordered_events)

        selected_events = ordered_events[:max_results]

        if aggregate:
            event_phrase = "event" if len(selected_events) == 1 else "events"
            task_phrase = "task" if len(task_entries) == 1 else "tasks"
            header = (
                f"Schedule for {user_email}: {len(selected_events)} calendar "
                f"{event_phrase}, {len(task_entries)} due {task_phrase}."
            )
            result_lines = [header]
        else:
            result_lines = [f"Found {len(selected_events)} events for {user_email}:"]

        if aggregate or len(calendar_labels) > 1:
            result_lines.append("Calendars scanned: " + ", ".join(calendar_labels))
        elif calendar_labels:
            result_lines.append(f"Calendar: {calendar_labels[0]}")

        if selected_events:
            if aggregate:
                result_lines.append("")
                result_lines.append("Calendar events:")

            for event in selected_events:
                if event.is_all_day:
                    try:
                        start_date = datetime.date.fromisoformat(event.start)
                        end_date = datetime.date.fromisoformat(event.end)
                        actual_end_date = end_date - datetime.timedelta(days=1)

                        if start_date == actual_end_date:
                            timing = f"All day on {event.start}"
                        else:
                            timing = (
                                f"All day from {event.start} "
                                f"to {actual_end_date.isoformat()}"
                            )
                    except (ValueError, TypeError):
                        timing = f"All day on {event.start}"
                else:
                    timing = f"Starts: {event.start}, Ends: {event.end}"

                if detailed:
                    result_lines.append(f'- "{event.title}" ({timing})')
                    result_lines.append(f"  Calendar: {event.calendar}")
                    if event.description:
                        result_lines.append(f"  Description: {event.description}")
                    if event.location:
                        result_lines.append(f"  Location: {event.location}")
                    result_lines.append(f"  ID: {event.id} | Link: {event.link}")
                else:
                    line = (
                        f'- "{event.title}" ({timing}) '
                        f"[Calendar: {event.calendar}] ID: {event.id}"
                    )
                    if event.link:
                        line += f" | Link: {event.link}"
                    result_lines.append(line)
        elif aggregate:
            result_lines.append("")
            result_lines.append("No calendar events matched this range.")

        if aggregate:
            result_lines.append("")
            if task_entries:
                result_lines.append("Tasks due or overdue:")
                for task in task_entries:
                    result_lines.extend(_format_task_line(task))
                if truncated_tasks:
                    result_lines.append(
                        f"(+{truncated_tasks} additional tasks not shown; "
                        "refine the time range or adjust the task filters.)"
                    )
            else:
                result_lines.append("No tasks with due dates in this range.")

        if warnings:
            result_lines.append("Warnings:")
            for warning in warnings:
                result_lines.append(f"- {warning}")

        return "\n".join(result_lines)

    except ValueError as e:
        return (
            f"Authentication error: {str(e)}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as e:
        return f"Error retrieving calendar events: {str(e)}"


@mcp.tool("calendar_create_event")
async def create_event(
    user_email: str = DEFAULT_USER_EMAIL,
    *,
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
) -> str:
    """
    Create a new calendar event.

    Args:
        user_email: The user's email address
        summary: Event title/summary
        start_time: Start time (RFC3339 format or YYYY-MM-DD for all-day)
        end_time: End time (RFC3339 format or YYYY-MM-DD for all-day)
        calendar_id: Calendar ID (default: 'primary')
        description: Optional event description
        location: Optional event location
        attendees: Optional list of attendee email addresses

    Returns:
        Confirmation message with event details and link
    """
    try:
        # Get the calendar service
        service = get_calendar_service(user_email)

        resolved_calendar_id = _resolve_calendar_id_for_write(calendar_id)
        calendar_label = _calendar_label(resolved_calendar_id)

        # Detect if this is an all-day event (no time component)
        is_all_day = "T" not in start_time and ":" not in start_time

        # Format start and end times according to whether it's all-day or not
        event = {
            "summary": summary,
            "description": description,
            "location": location,
        }

        # Format start and end differently for all-day vs timed events
        if is_all_day:
            event["start"] = {"date": start_time}
            event["end"] = {"date": end_time}
        else:
            # Make sure times have timezone info
            start_formatted = _parse_time_string(start_time)
            end_formatted = _parse_time_string(end_time)

            event["start"] = {"dateTime": start_formatted}
            event["end"] = {"dateTime": end_formatted}

        # Add attendees if specified
        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        # Add notification settings (default 10 minutes before)
        event["reminders"] = {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 10},
            ],
        }

        # Execute the API call to create the event
        created_event = await asyncio.to_thread(
            service.events().insert(calendarId=resolved_calendar_id, body=event).execute
        )

        # Format timing string for the response
        timing = (
            f"all day event on {start_time}"
            if is_all_day
            else f"from {start_time} to {end_time}"
        )

        # Get the event link
        event_link = created_event.get("htmlLink", "")

        return (
            f"Successfully created event '{summary}' ({timing}) in calendar "
            f"'{calendar_label}' (ID: {resolved_calendar_id}). Link: {event_link}"
        )

    except ValueError as e:
        return (
            f"Authentication error: {str(e)}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as e:
        # In production, you would want better error handling
        return f"Error creating calendar event: {str(e)}"


@mcp.tool("calendar_update_event")
async def update_event(
    user_email: str = DEFAULT_USER_EMAIL,
    *,
    event_id: str,
    calendar_id: Optional[str] = None,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
) -> str:
    """
    Update an existing calendar event.

    Args:
        user_email: The user's email address
        event_id: ID of the event to update
        calendar_id: Calendar ID (default: 'primary')
        summary: New event title/summary (optional)
        start_time: New start time (optional, RFC3339 format or YYYY-MM-DD for all-day)
        end_time: New end time (optional, RFC3339 format or YYYY-MM-DD for all-day)
        description: New event description (optional)
        location: New event location (optional)
        attendees: New list of attendee email addresses (optional)

    Returns:
        Confirmation message with updated event details
    """
    try:
        # Get the calendar service
        service = get_calendar_service(user_email)

        resolved_calendar_id = _resolve_calendar_id_for_write(calendar_id)
        calendar_label = _calendar_label(resolved_calendar_id)

        # First, get the existing event
        event = await asyncio.to_thread(
            service.events()
            .get(calendarId=resolved_calendar_id, eventId=event_id)
            .execute
        )

        # Update fields if provided
        if summary:
            event["summary"] = summary

        if description is not None:  # Allow empty string to clear description
            event["description"] = description

        if location is not None:  # Allow empty string to clear location
            event["location"] = location

        # Update start/end times if provided
        if start_time and end_time:
            is_all_day = "T" not in start_time and ":" not in start_time

            if is_all_day:
                event["start"] = {"date": start_time}
                event["end"] = {"date": end_time}
            else:
                start_formatted = _parse_time_string(start_time)
                end_formatted = _parse_time_string(end_time)

                event["start"] = {"dateTime": start_formatted}
                event["end"] = {"dateTime": end_formatted}

        # Update attendees if provided
        if attendees is not None:
            event["attendees"] = [{"email": email} for email in attendees]

        # Execute the API call to update the event
        updated_event = await asyncio.to_thread(
            service.events()
            .update(calendarId=resolved_calendar_id, eventId=event_id, body=event)
            .execute
        )

        # Get the event link
        event_link = updated_event.get("htmlLink", "")

        return (
            f"Successfully updated event '{updated_event.get('summary')}' "
            f"in calendar '{calendar_label}' (ID: {resolved_calendar_id}). "
            f"Link: {event_link}"
        )

    except ValueError as e:
        return (
            f"Authentication error: {str(e)}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as e:
        return f"Error updating calendar event: {str(e)}"


@mcp.tool("calendar_delete_event")
async def delete_event(
    user_email: str = DEFAULT_USER_EMAIL,
    *,
    event_id: str,
    calendar_id: Optional[str] = None,
) -> str:
    """
    Delete a calendar event.

    Args:
        user_email: The user's email address
        event_id: ID of the event to delete
        calendar_id: Calendar ID (default: 'primary')

    Returns:
        Confirmation message
    """
    try:
        # Get the calendar service
        service = get_calendar_service(user_email)

        resolved_calendar_id = _resolve_calendar_id_for_write(calendar_id)
        calendar_label = _calendar_label(resolved_calendar_id)

        # First, get the event details to include in the confirmation
        event = await asyncio.to_thread(
            service.events()
            .get(calendarId=resolved_calendar_id, eventId=event_id)
            .execute
        )

        event_summary = event.get("summary", "Unknown event")

        # Execute the API call to delete the event
        await asyncio.to_thread(
            service.events()
            .delete(calendarId=resolved_calendar_id, eventId=event_id)
            .execute
        )

        return (
            f"Successfully deleted event '{event_summary}' from calendar "
            f"'{calendar_label}' (ID: {resolved_calendar_id})."
        )

    except ValueError as e:
        return (
            f"Authentication error: {str(e)}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as e:
        return f"Error deleting calendar event: {str(e)}"


@mcp.tool("calendar_list_task_lists")
async def list_task_lists(
    user_email: str = DEFAULT_USER_EMAIL,
    max_results: int = 100,
    page_token: Optional[str] = None,
) -> str:
    """
    List Google Task lists available to the user.

    Args:
        user_email: The user's email address.
        max_results: Maximum number of task lists to return (capped at 100).
        page_token: Optional pagination token from a previous call.

    Returns:
        Formatted string describing task lists.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        task_lists, next_page = await task_service.list_task_lists(
            max_results=max_results, page_token=page_token
        )
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    if not task_lists:
        return f"No task lists found for {user_email}."

    lines = [f"Task lists for {user_email}:"]
    for task_list in task_lists:
        lines.append(f"- {task_list.title} (ID: {task_list.id})")
        lines.append(f"  Updated: {task_list.updated or 'N/A'}")

    if next_page:
        lines.append(f"Next page token: {next_page}")

    return "\n".join(lines)


@mcp.tool("list_tasks")
async def list_tasks(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: Optional[str] = None,
    max_results: Optional[int] = None,
    page_token: Optional[str] = None,
    show_completed: bool = False,
    show_deleted: bool = False,
    show_hidden: bool = False,
    due_min: Optional[str] = None,
    due_max: Optional[str] = None,
    task_filter: str = "all",
) -> str:
    """
    List tasks from a specific Google Tasks list. Both scheduled and unscheduled
    tasks are returned unless filtered. Requires explicit list selection.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (ID or title). When omitted, returns
            available lists for user selection.
        max_results: Maximum number of tasks to return. None returns all.
        page_token: Optional pagination token from a previous call.
        show_completed: Whether to include completed tasks.
        show_deleted: Whether to include deleted tasks.
        show_hidden: Whether to include hidden tasks.
        due_min: Optional lower bound for due dates (ISO 8601 or RFC3339).
        due_max: Optional upper bound for due dates (ISO 8601 or RFC3339).
        task_filter: Filter tasks by type: 'all' (default), 'scheduled',
            'unscheduled', 'overdue', or 'upcoming'.

    Returns:
        Formatted string describing tasks, sorted by due date.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    normalized_filter = (task_filter or "all").strip().lower()
    allowed_filters = {"all", "scheduled", "unscheduled", "overdue", "upcoming"}
    if normalized_filter not in allowed_filters:
        return (
            "Invalid task_filter. Supported: all, scheduled, unscheduled, "
            "overdue, upcoming."
        )

    if not task_list_id:
        try:
            task_lists, _ = await task_service.list_task_lists(max_results=50)
        except TaskAuthorizationError as exc:
            return (
                f"Authentication error: {exc}. "
                "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
            )
        except TaskServiceError as exc:
            return str(exc)

        if not task_lists:
            return f"No task lists found for {user_email}."

        lines = [
            f"Task lists for {user_email}. Specify one when calling list_tasks:",
        ]
        for tl in task_lists:
            lines.append(f"- {tl.title} (ID: {tl.id})")
        return "\n".join(lines)

    try:
        resolved = await _resolve_task_list_identifier(task_service, task_list_id)
    except TaskServiceError as exc:
        return str(exc)

    if resolved is None:
        effective_list_id, list_label = task_list_id, task_list_id
    else:
        effective_list_id, list_label = resolved

    collected: List[Task] = []
    token = page_token
    next_token: Optional[str] = None

    def apply_filter(tasks: List[Task]) -> List[Task]:
        now = datetime.datetime.now(datetime.timezone.utc)
        if normalized_filter == "scheduled":
            return [t for t in tasks if t.due is not None]
        if normalized_filter == "unscheduled":
            return [t for t in tasks if t.due is None]
        if normalized_filter == "overdue":
            return [t for t in tasks if t.due and t.due < now]
        if normalized_filter == "upcoming":
            return [t for t in tasks if t.due and t.due >= now]
        return list(tasks)

    target_count = max_results if max_results is not None else None

    while True:
        per_page = 100 if target_count is None else max(1, min(target_count, 100))

        try:
            page_tasks, next_token = await task_service.list_tasks(
                effective_list_id,
                max_results=per_page,
                page_token=token,
                show_completed=show_completed,
                show_deleted=show_deleted,
                show_hidden=show_hidden,
                due_min=due_min,
                due_max=due_max,
            )
        except TaskAuthorizationError as exc:
            return (
                f"Authentication error: {exc}. "
                "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
            )
        except TaskServiceError as exc:
            return str(exc)

        collected.extend(page_tasks)
        filtered = apply_filter(collected)

        if target_count is not None and len(filtered) >= target_count:
            break
        if not next_token:
            break
        token = next_token

    if not filtered:
        msg = {
            "all": "No tasks",
            "scheduled": "No scheduled tasks",
            "unscheduled": "No unscheduled tasks",
            "overdue": "No overdue tasks",
            "upcoming": "No upcoming tasks",
        }[normalized_filter]
        return f"{msg} in '{list_label}' for {user_email}."

    filtered.sort(
        key=lambda t: (
            t.due or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc),
            t.title.lower(),
        )
    )

    display = filtered[:target_count] if target_count else filtered
    has_more = (target_count and len(filtered) > len(display)) or next_token

    header = f"Tasks in '{list_label}' for {user_email}: {len(display)} shown"
    if normalized_filter != "all":
        header += f" (filter: {normalized_filter})."
    else:
        header += "."

    lines = [header]

    for task in display:
        due_text = f"Due {normalize_rfc3339(task.due)}" if task.due else "Unscheduled"
        lines.append(f"- {task.title} [{task.status}] ({due_text}) ID: {task.id}")
        if task.notes:
            lines.append(f"  Notes: {task.notes}")
        if task.web_link:
            lines.append(f"  Link: {task.web_link}")

    if has_more and next_token:
        lines.append(f"Next page token: {next_token}")
    elif has_more:
        lines.append("Additional tasks available; adjust max_results.")

    return "\n".join(lines)


@mcp.tool("search_all_tasks")
async def search_all_tasks(
    user_email: str = DEFAULT_USER_EMAIL,
    query: str = "",
    task_list_id: Optional[str] = None,
    max_results: int = 25,
    include_completed: bool = False,
    include_hidden: bool = False,
    include_deleted: bool = False,
    search_notes: bool = True,
    due_min: Optional[str] = None,
    due_max: Optional[str] = None,
) -> str:
    """Search Google Tasks across every list to learn what the user plans, wants, or needs.
    Call this whenever the user asks about what they have to do, want to read/watch/eat/buy,
    or before offering personal suggestions—questions like "what books do I want to read?"
    should trigger this tool. Prefer short keyword queries copied from the user's request
    (for example, "books"). If you do not have a specific keyword, pass an empty string
    and this tool will return a general overview of recent tasks.

    Args:
        user_email: The user's email address.
        query: Search query string to match against task titles and notes.
        task_list_id: Optional task list identifier or friendly name to narrow search.
        max_results: Maximum number of matching tasks to return (default: 25).
        include_completed: Whether to include completed tasks in results.
        include_hidden: Whether to include hidden tasks.
        include_deleted: Whether to include deleted tasks.
        search_notes: Whether to search task notes in addition to titles (default: True).
        due_min: Optional lower bound for due dates (ISO 8601 or RFC3339).
        due_max: Optional upper bound for due dates (ISO 8601 or RFC3339).

    Returns:
        Formatted string with matching tasks and their details.
    """

    trimmed_query = (query or "").strip()
    general_search = not trimmed_query

    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        search_response = await task_service.search_tasks(
            trimmed_query,
            task_list_id=task_list_id,
            max_results=max_results,
            include_completed=include_completed,
            include_hidden=include_hidden,
            include_deleted=include_deleted,
            search_notes=search_notes,
            due_min=due_min,
            due_max=due_max,
        )
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    matches = search_response.matches
    if not matches:
        if search_response.warnings:
            warning_text = "; ".join(search_response.warnings)
            if general_search:
                return (
                    f"No tasks found for {user_email} across available lists. "
                    f"Warnings: {warning_text}."
                )
            return (
                f"No tasks matched query '{trimmed_query}' for {user_email}. "
                f"Warnings: {warning_text}."
            )
        if general_search:
            return f"No tasks found for {user_email} across available lists."
        return f"No tasks matched query '{trimmed_query}' for {user_email}."

    if general_search:
        header = (
            f"Task overview for {user_email}: {len(matches)} item"
            + ("s" if len(matches) != 1 else "")
            + " highlighted."
        )
    else:
        header = (
            f"Task search for {user_email}: {len(matches)} match"
            + ("es" if len(matches) != 1 else "")
            + f" for '{trimmed_query}'."
        )

    header_lines = [header]

    if not task_list_id and search_response.scanned_lists:
        header_lines.append(
            "Task lists scanned: " + ", ".join(search_response.scanned_lists)
        )
    elif task_list_id and search_response.scanned_lists:
        header_lines.append(f"Task list: {search_response.scanned_lists[0]}")

    for task in matches:
        header_lines.extend(_format_task_search_result(task))

    if search_response.truncated:
        header_lines.append(
            f"(+{search_response.truncated} additional matches not shown; increase max_results or refine the query.)"
        )

    if search_response.warnings:
        header_lines.append("Warnings:")
        for warning in search_response.warnings:
            header_lines.append(f"- {warning}")

    return "\n".join(header_lines)


async def _upcoming_calendar_snapshot(
    user_email: str,
    *,
    days_ahead: int = 7,
    max_results: int = 10,
) -> str:
    """Fetch upcoming events within the next ``days_ahead`` days."""

    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    window_end = now + datetime.timedelta(days=days_ahead)

    return await get_events(
        user_email=user_email,
        time_min=now.isoformat(),
        time_max=window_end.isoformat(),
        max_results=max_results,
        detailed=False,
    )


@mcp.tool("user_context_from_tasks")
async def user_context_from_tasks(
    query: str,
    user_email: str = DEFAULT_USER_EMAIL,
    max_results: int = 25,
    include_completed: bool = False,
) -> str:
    """High-priority alias that surfaces personal context from Google Tasks.
    Always call this before making recommendations; when no obvious keyword is present,
    pass an empty string for ``query`` to fetch a general overview plus upcoming events.
    """

    trimmed_query = (query or "").strip()
    if trimmed_query:
        return await search_all_tasks(
            user_email=user_email,
            query=trimmed_query,
            max_results=max_results,
            include_completed=include_completed,
        )

    # Fallback: gather a general task overview plus the upcoming week calendar snapshot.
    task_summary = await search_all_tasks(
        user_email=user_email,
        query="",
        max_results=max_results,
        include_completed=include_completed,
    )

    calendar_summary = await _upcoming_calendar_snapshot(
        user_email,
        days_ahead=7,
        max_results=max(1, min(max_results, 10)),
    )

    sections: list[str] = []
    if task_summary:
        sections.append(task_summary)
    if calendar_summary:
        sections.append(calendar_summary)

    if sections:
        return "\n\n".join(sections)

    return (
        "No tasks or calendar events were found for the upcoming week. "
        "Use calendar_list_tasks or calendar_get_events for more details."
    )


@mcp.tool("calendar_get_task")
async def get_task(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
    task_id: str = "",
) -> str:
    """
    Retrieve a specific task by ID.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').
        task_id: The task identifier to retrieve.

    Returns:
        Detailed description of the task.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        task = await task_service.get_task(task_list_id, task_id)
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    lines = [
        f"Task details for {user_email}:",
        f"- Title: {task.title}",
        f"- ID: {task.id or task_id}",
        f"- Status: {task.status}",
        f"- Updated: {task.updated or 'N/A'}",
    ]

    if task.due:
        lines.append(f"- Due: {normalize_rfc3339(task.due)}")
    if task.completed:
        lines.append(f"- Completed: {task.completed}")
    if task.notes:
        lines.append(f"- Notes: {task.notes}")
    if task.parent:
        lines.append(f"- Parent: {task.parent}")
    if task.position:
        lines.append(f"- Position: {task.position}")
    if task.web_link:
        lines.append(f"- Link: {task.web_link}")

    return "\n".join(lines)


@mcp.tool("calendar_create_task")
async def create_task(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
    *,
    title: str,
    notes: Optional[str] = None,
    due: Optional[str] = None,
    parent: Optional[str] = None,
    previous: Optional[str] = None,
) -> str:
    """
    Create a new Google Task.

    IMPORTANT: When the user asks to "schedule a task for [date/time]", you MUST
    include the 'due' parameter to actually schedule it. Without 'due', the task
    will be created unscheduled. Use 'due="YYYY-MM-DD"' for date-only scheduling
    or 'due="YYYY-MM-DDTHH:MM:SSZ"' for specific times.

    When scheduling EXISTING tasks, use calendar_update_task instead of creating
    duplicates.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').
        title: Title for the new task.
        notes: Optional detailed notes.
        due: Due date/time (ISO 8601 or RFC3339 format). REQUIRED for scheduling.
        parent: Optional parent task ID for subtasks.
        previous: Optional sibling task ID for positioning.

    Returns:
        Confirmation message with task details.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        created = await task_service.create_task(
            task_list_id,
            title=title,
            notes=notes,
            due=due,
            parent=parent,
            previous=previous,
        )
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    lines = [
        f"Created task '{created.title}' in list {task_list_id}:",
        f"- ID: {created.id or '(unknown)'}",
        f"- Status: {created.status}",
        f"- Updated: {created.updated or 'N/A'}",
    ]

    if created.due:
        lines.append(f"- Due: {normalize_rfc3339(created.due)}")
    if created.web_link:
        lines.append(f"- Link: {created.web_link}")

    return "\n".join(lines)


@mcp.tool("calendar_update_task")
async def update_task(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
    task_id: str = "",
    *,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    due: Optional[str] = None,
) -> str:
    """
    Update an existing task.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').
        task_id: Task identifier to update.
        title: Optional new title.
        notes: Optional new notes (pass empty string to clear).
        status: Optional new status ('needsAction' or 'completed').
        due: Optional new due date/time (ISO 8601 or RFC3339).

    Returns:
        Confirmation message with task details.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        updated_task = await task_service.update_task(
            task_list_id,
            task_id,
            title=title,
            notes=notes,
            status=status,
            due=due,
        )
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    lines = [
        f"Updated task '{updated_task.title}' (ID: {updated_task.id or task_id}):",
        f"- Status: {updated_task.status}",
        f"- Updated: {updated_task.updated or 'N/A'}",
    ]

    if updated_task.due:
        lines.append(f"- Due: {normalize_rfc3339(updated_task.due)}")
    if updated_task.completed:
        lines.append(f"- Completed: {updated_task.completed}")
    if updated_task.web_link:
        lines.append(f"- Link: {updated_task.web_link}")

    return "\n".join(lines)


@mcp.tool("calendar_delete_task")
async def delete_task(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
    task_id: str = "",
) -> str:
    """
    Delete a task from a list.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').
        task_id: Task identifier to delete.

    Returns:
        Confirmation message.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        await task_service.delete_task(task_list_id, task_id)
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    return f"Task {task_id} deleted from list {task_list_id}."


@mcp.tool("calendar_move_task")
async def move_task(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
    task_id: str = "",
    parent: Optional[str] = None,
    previous: Optional[str] = None,
    destination_task_list: Optional[str] = None,
) -> str:
    """
    Move a task within or across task lists.

    Args:
        user_email: The user's email address.
        task_list_id: Current task list identifier (default: '@default').
        task_id: Task identifier to move.
        parent: Optional new parent task ID (for subtasks).
        previous: Optional sibling task ID to position after.
        destination_task_list: Optional destination task list ID.

    Returns:
        Confirmation message describing the move.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        moved = await task_service.move_task(
            task_list_id,
            task_id,
            parent=parent,
            previous=previous,
            destination_task_list=destination_task_list,
        )
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    lines = [f"Moved task '{moved.title}' (ID: {moved.id or task_id})."]

    if moved.parent:
        lines.append(f"- Parent: {moved.parent}")
    if moved.position:
        lines.append(f"- Position: {moved.position}")
    if destination_task_list:
        lines.append(f"- Destination list: {destination_task_list}")

    return "\n".join(lines)


@mcp.tool("calendar_clear_completed_tasks")
async def clear_completed_tasks(
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: str = "@default",
) -> str:
    """
    Clear all completed tasks from a task list (marks them hidden).

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').

    Returns:
        Confirmation message.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        await task_service.clear_completed_tasks(task_list_id)
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Open the system settings modal and click 'Connect Google Services' to refresh Google Tasks permissions."
        )
    except TaskServiceError as exc:
        return str(exc)

    return (
        f"Completed tasks cleared from list {task_list_id}. "
        "Hidden tasks may take a moment to disappear from other clients."
    )


@mcp.tool("calendar_list_calendars")
async def list_calendars(
    user_email: str = DEFAULT_USER_EMAIL, max_results: int = 100
) -> str:
    """
    List calendars the user has access to.

    Args:
        user_email: The user's email address.
        max_results: Maximum number of calendars to include.

    Returns:
        Formatted string describing available calendars.
    """
    try:
        service = get_calendar_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating calendar service: {exc}"

    try:
        calendars: list[dict[str, str]] = []
        page_token: Optional[str] = None

        while len(calendars) < max_results:
            remaining = max_results - len(calendars)
            params: dict[str, Any] = {"maxResults": min(250, remaining)}
            if page_token:
                params["pageToken"] = page_token

            response = await asyncio.to_thread(
                service.calendarList().list(**params).execute
            )

            items = response.get("items", [])
            for item in items:
                calendars.append(
                    {
                        "name": item.get("summary", "(Unnamed calendar)"),
                        "id": item.get("id", ""),
                        "primary": "true" if item.get("primary") else "false",
                        "access_role": item.get("accessRole", "unknown"),
                    }
                )
                if len(calendars) >= max_results:
                    break

            page_token = response.get("nextPageToken")
            if not page_token or len(calendars) >= max_results:
                break

        if not calendars:
            return f"No calendars found for {user_email}."

        lines = [
            f"Found {len(calendars)} calendars for {user_email}:",
        ]
        for calendar in calendars:
            primary_marker = " [primary]" if calendar["primary"] == "true" else ""
            lines.append(
                f'- "{calendar["name"]}"{primary_marker} (ID: {calendar["id"]}, access: {calendar["access_role"]})'
            )

        if page_token:
            lines.append(
                "Additional calendars exist; rerun with a higher max_results value to fetch more."
            )

        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover - unexpected API response
        return f"Error listing calendars: {exc}"


def run() -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
    "get_events",
    "create_event",
    "update_event",
    "delete_event",
    "list_calendars",
    "list_task_lists",
    "list_tasks",
    "search_all_tasks",
    "user_context_from_tasks",
    "get_task",
    "create_task",
    "update_task",
    "delete_task",
    "move_task",
    "clear_completed_tasks",
]
