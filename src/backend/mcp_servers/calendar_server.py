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
from backend.config import get_settings
from backend.services.google_auth.auth import (
    authorize_user,
    get_calendar_service,
    get_credentials,
    get_tasks_service as _google_get_tasks_service,
)
from backend.services.time_context import build_context_lines, create_time_snapshot
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

_CONTEXT_TTL = datetime.timedelta(minutes=5)
_last_context_check: Optional[datetime.datetime] = None


def _mark_context_checked(timestamp: Optional[datetime.datetime] = None) -> None:
    """Record that the caller refreshed the current date context."""

    global _last_context_check

    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    else:
        timestamp = timestamp.astimezone(datetime.timezone.utc)

    _last_context_check = timestamp


def _reset_context_check() -> None:  # pragma: no cover - testing hook
    """Clear stored context check state."""

    global _last_context_check
    _last_context_check = None


def _parse_time_string(time_str: Optional[str]) -> Optional[str]:
    """Convert simple date keywords/strings to RFC3339 (UTC) strings.

    Behavior:
    - None → None
    - 'today'/'tomorrow'/'yesterday' → YYYY-MM-DDT00:00:00Z
    - 'YYYY-MM-DD' → YYYY-MM-DDT00:00:00Z
    - Naive datetime 'YYYY-MM-DDTHH:MM[:SS]' → append Z
    - Already offset/Z → returned as-is
    """

    if not time_str:
        return None

    lowered = time_str.lower()
    today = datetime.date.today()

    if lowered in {"today", "tomorrow", "yesterday"}:
        if lowered == "today":
            d = today
        elif lowered == "tomorrow":
            d = today + datetime.timedelta(days=1)
        else:
            d = today - datetime.timedelta(days=1)
        return f"{d.isoformat()}T00:00:00Z"

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


def _has_recent_context(now: Optional[datetime.datetime] = None) -> bool:
    """Return True if the caller recently refreshed the current date context."""

    reference = _last_context_check
    if reference is None:
        return False

    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    else:
        now = now.astimezone(datetime.timezone.utc)

    return now - reference <= _CONTEXT_TTL


def _require_recent_context() -> Optional[str]:
    """Provide a guard message when no recent context check exists."""

    if _has_recent_context():
        return None

    return (
        "⚠️  REQUIRED: Call calendar_current_context first to get the current date and time.\n\n"
        "Why? Without knowing what day it is RIGHT NOW, any calendar operation using "
        "relative dates (today, tomorrow, next week) will use stale information and "
        "produce incorrect results.\n\n"
        "Action: Call calendar_current_context() now, then retry this operation with "
        "the accurate date information it provides."
    )


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


DEFAULT_USER_EMAIL = "jck411@gmail.com"

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


def _resolve_redirect_uri(redirect_uri: Optional[str]) -> str:
    """Return the effective redirect URI, falling back to settings defaults."""
    if redirect_uri:
        return redirect_uri

    try:
        settings = get_settings()
        return settings.google_oauth_redirect_uri
    except Exception:
        # Fallback enables local usage without full settings (e.g. during tests)
        return "http://localhost:8000/api/google-auth/callback"


@mcp.tool("calendar_auth_status")
async def auth_status(user_email: str = DEFAULT_USER_EMAIL) -> str:
    """
    Report whether the user has valid Google Calendar credentials stored.

    Returns:
        Status message with expiry details or next steps.
    """
    try:
        credentials = get_credentials(user_email)
    except FileNotFoundError:
        credentials = None
    except Exception as exc:  # pragma: no cover - unexpected configuration issues
        return f"Error checking authorization status: {exc}"

    if credentials:
        expiry = getattr(credentials, "expiry", None)
        expiry_text = expiry.isoformat() if expiry else "unknown expiry"
        return (
            f"{user_email} is already authorized for Google Calendar. "
            f"Existing token expires at {expiry_text}. "
            "Use calendar_generate_auth_url with force=true to start a fresh consent flow."
        )

    return (
        f"No stored Google Calendar credentials found for {user_email}. "
        "Run calendar_generate_auth_url to generate an authorization link."
    )


@mcp.tool("calendar_generate_auth_url")
async def generate_auth_url(
    user_email: str = DEFAULT_USER_EMAIL,
    redirect_uri: Optional[str] = None,
    force: bool = False,
) -> str:
    """
    Create a Google OAuth consent URL for the given user.

    Args:
        user_email: The user's email address.
        redirect_uri: Optional override for the redirect URI.
        force: If True, generate a fresh URL even when credentials exist.

    Returns:
        Instructions and URL for completing OAuth consent.
    """
    try:
        credentials = get_credentials(user_email)
    except FileNotFoundError:
        credentials = None
    except Exception as exc:  # pragma: no cover - unexpected configuration issues
        return f"Error checking existing credentials: {exc}"

    if credentials and not force:
        expiry = getattr(credentials, "expiry", None)
        expiry_text = expiry.isoformat() if expiry else "unknown expiry"
        return (
            f"{user_email} already has stored credentials (expires {expiry_text}). "
            "Set force=true if you want to start a fresh consent flow."
        )

    effective_redirect = _resolve_redirect_uri(redirect_uri)

    try:
        auth_url = authorize_user(user_email, effective_redirect)
    except FileNotFoundError as exc:
        return (
            "Missing OAuth client configuration. "
            f"{exc}. Ensure client_secret_*.json is placed in the credentials directory."
        )
    except Exception as exc:
        return f"Error generating authorization URL: {exc}"

    return (
        "Follow these steps to finish Google Calendar authorization:\n"
        f"1. Visit: {auth_url}\n"
        "2. Approve access to your calendar.\n"
        f"3. You will be redirected to {effective_redirect}; the backend will store the token automatically.\n"
        "After completing the flow, run calendar_auth_status to confirm success.\n"
        "Note: Google may warn that the app is unverified. Choose Advanced → Continue to proceed for testing accounts added on the OAuth consent screen."
    )


@mcp.tool("calendar_current_context")
async def calendar_current_context(timezone: Optional[str] = None) -> str:
    """Get the current date and time context for calendar operations.
    
    IMPORTANT: Always call this tool FIRST before any calendar operations that involve
    dates or times. This ensures you have accurate information about:
    - What day it is today
    - What day of the week it is
    - What dates correspond to "tomorrow", "next week", etc.
    
    Without this context, you may use outdated date information, leading to incorrect
    calendar queries or event creation. Call this tool:
    - At the start of any conversation involving calendar or dates
    - Before searching for events with relative dates (today, tomorrow, next week)
    - Before creating or updating events
    - When the user asks "what's on my schedule" or similar time-based queries
    
    The context remains valid for 5 minutes, after which you should refresh it.
    """

    snapshot = create_time_snapshot(timezone)
    _mark_context_checked(snapshot.now_utc)

    lines = list(build_context_lines(snapshot))
    lines.append("")
    lines.append("✓ Context refreshed and valid for the next 5 minutes.")
    lines.append("")
    lines.append(
        "IMPORTANT: Use the exact ISO dates shown above (YYYY-MM-DD format) when "
        "constructing calendar queries. For example:"
    )
    lines.append(f"- To find today's events: use time_min='{snapshot.date.isoformat()}'")
    lines.append(
        f"- To find tomorrow's events: use time_min='{(snapshot.date + datetime.timedelta(days=1)).isoformat()}'"
    )
    lines.append(
        "- For date ranges, use the 'Upcoming anchors' shown above as reference points."
    )

    return "\n".join(lines)


@mcp.tool("calendar_get_events")
async def get_events(
    user_email: str = DEFAULT_USER_EMAIL,
    calendar_id: Optional[str] = None,
    time_min: Optional[str] = "today",
    time_max: Optional[str] = None,
    max_results: int = 25,
    query: Optional[str] = None,
    detailed: bool = False,
) -> str:
    """
    Retrieve events from Google Calendar.

    ⚠️  PREREQUISITE: You MUST call calendar_current_context() first, before using
    this tool. This ensures you have accurate date information for keywords like
    "today", "tomorrow", etc.

    This tool searches across the user's calendars (or a specific calendar if specified).
    With no calendar_id (or when using phrases like "my schedule") the search spans
    all preconfigured household calendars. Provide a specific ID or friendly name
    (e.g., "Family Calendar", "Dad Work Schedule") to narrow the query.

    Args:
        user_email: The user's email address (defaults to Jack's primary account).
        calendar_id: Optional calendar ID or friendly name.
        time_min: Start time (ISO format YYYY-MM-DD or keywords like "today").
                  Use exact dates from calendar_current_context output.
        time_max: End time (optional, ISO format or keywords).
        max_results: Maximum number of events to return after aggregation.
        query: Optional search query for event titles/descriptions.
        detailed: Whether to include full event details in results.

    Returns:
        Formatted string with event details, or an error if context is stale.
    """

    try:
        guard_message = _require_recent_context()
        if guard_message:
            return guard_message

        service = get_calendar_service(user_email)

        time_min_rfc = _parse_time_string(time_min)
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
            "timeMin": time_min_rfc,
        }

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
                    + ". Re-run calendar_generate_auth_url with force=true to extend permissions."
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
            "Use calendar_generate_auth_url to authorize this account."
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

    💡 BEST PRACTICE: Call calendar_current_context() first to get accurate dates
    when using relative terms like "today" or "tomorrow".

    Args:
        user_email: The user's email address
        summary: Event title/summary
        start_time: Start time - use ISO format (YYYY-MM-DD for all-day events,
                    YYYY-MM-DDTHH:MM:SS for timed events). Get exact dates from
                    calendar_current_context when using relative dates.
        end_time: End time (same format as start_time)
        calendar_id: Calendar ID or friendly name (default: 'primary')
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
            "Use calendar_generate_auth_url to authorize this account."
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
            "Use calendar_generate_auth_url to authorize this account."
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
            "Use calendar_generate_auth_url to authorize this account."
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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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


@mcp.tool("calendar_list_tasks")
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
) -> str:
    """
    List tasks within a specific task list, or all due tasks when no list is provided.

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier; when omitted, gather due tasks across lists.
        max_results: Maximum number of tasks to return (capped at 100). Provide
            None to return all matching tasks.
        page_token: Optional pagination token from a previous call.
        show_completed: Whether to include completed tasks.
        show_deleted: Whether to include deleted tasks.
        show_hidden: Whether to include hidden tasks.
        due_min: Optional lower bound for due dates (keywords supported).
        due_max: Optional upper bound for due dates (keywords supported).

    Returns:
        Formatted string describing tasks.
    """
    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        effective_list_id: Optional[str] = None
        list_label: Optional[str] = None

        if task_list_id:
            # Support passing a human-friendly list title by resolving to ID
            resolved = await _resolve_task_list_identifier(task_service, task_list_id)
            if resolved is not None:
                effective_list_id, list_label = resolved
            else:
                effective_list_id, list_label = task_list_id, task_list_id

            list_limit = max_results if max_results is not None else 50
            due_collection = None
        else:
            due_collection = await task_service.collect_due_tasks(
                max_results=max_results,
                show_completed=show_completed,
                show_deleted=show_deleted,
                show_hidden=show_hidden,
                due_min=due_min,
                due_max=due_max,
            )
            tasks = due_collection.tasks
            # No page token in aggregated view here.
    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
        )
    except TaskServiceError as exc:
        return str(exc)

    if task_list_id:
        list_limit = max_results if max_results is not None else 50
        collected_due: list[Task] = []
        next_page_token = page_token
        unscheduled_found = False

        while True:
            page_tasks, page_next = await task_service.list_tasks(
                effective_list_id or task_list_id,
                max_results=list_limit,
                page_token=next_page_token,
                show_completed=show_completed,
                show_deleted=show_deleted,
                show_hidden=show_hidden,
                due_min=due_min,
                due_max=due_max,
            )

            if not page_tasks:
                next_page_token = page_next
                break

            for task in page_tasks:
                if task.due:
                    collected_due.append(task)
                    if len(collected_due) >= list_limit:
                        next_page_token = page_next
                        break
                else:
                    unscheduled_found = True

            if len(collected_due) >= list_limit:
                break

            if not page_next:
                next_page_token = None
                break

            next_page_token = page_next

        if not collected_due:
            message = (
                f"No tasks with scheduled due dates found in list {list_label or task_list_id} "
                f"for {user_email}."
            )
            if unscheduled_found:
                message += (
                    " Use tasks_list_unscheduled to view items without due dates."
                )
            return message

        lines = [
            (
                f"Tasks with scheduled due date/time in list {list_label or task_list_id} for "
                f"{user_email}:"
            )
        ]

        def append_task_details(target: list[str], task: Task) -> None:
            target.append(f"- {task.title} (ID: {task.id})")
            target.append(f"  Status: {task.status}")
            target.append(f"  Updated: {task.updated or 'N/A'}")
            if task.due is not None:
                target.append(f"  Due: {normalize_rfc3339(task.due)}")
            if task.completed:
                target.append(f"  Completed: {task.completed}")
            if task.notes:
                notes = task.notes.strip()
                if len(notes) > 200:
                    notes = notes[:197] + "..."
                if notes:
                    target.append(f"  Notes: {notes}")
            if task.web_link:
                target.append(f"  Link: {task.web_link}")

        for task in collected_due:
            append_task_details(lines, task)

        if unscheduled_found:
            lines.append(
                """
Note: Additional tasks without due dates exist; use tasks_list_unscheduled to view them.
""".strip()
            )

        if next_page_token:
            lines.append(f"Next page token: {next_page_token}")

        return "\n".join(lines)

    # Aggregate due tasks view.
    assert due_collection is not None
    due_tasks = tasks

    if not due_tasks:
        base_message = f"No due tasks found across task lists for {user_email}."
        if due_collection.has_additional:
            base_message += (
                " Additional due tasks may exist; increase max_results or "
                "adjust the filters to reveal more."
            )
        if due_collection.warnings:
            base_message += " Warnings: " + "; ".join(due_collection.warnings) + "."
        return base_message

    shown_count = len(due_tasks)
    task_word = "task" if shown_count == 1 else "tasks"
    if due_collection.total_found > shown_count:
        lines = [
            (
                f"Due tasks for {user_email}: showing {shown_count} of "
                f"{due_collection.total_found} {task_word}."
            )
        ]
    else:
        lines = [f"Due tasks for {user_email}: {shown_count} {task_word}."]

    if due_collection.scanned_lists:
        if len(due_collection.scanned_lists) <= 10:
            lines.append(
                "Task lists scanned: " + ", ".join(due_collection.scanned_lists)
            )
        else:
            displayed_lists = ", ".join(due_collection.scanned_lists[:10])
            remaining_lists = len(due_collection.scanned_lists) - 10
            lines.append(
                f"Task lists scanned: {displayed_lists}, +{remaining_lists} more"
            )

    for task in due_tasks:
        lines.append(f"- {task.title} (ID: {task.id})")
        lines.append(f"  Status: {task.status}")
        lines.append(f"  Task list: {task.list_title} (ID: {task.list_id})")
        if task.due:
            lines.append(f"  Due: {normalize_rfc3339(task.due)}")
        lines.append(f"  Updated: {task.updated or 'N/A'}")
        if task.completed:
            lines.append(f"  Completed: {task.completed}")
        if task.notes:
            notes = task.notes.strip()
            if len(notes) > 200:
                notes = notes[:197] + "..."
            if notes:
                lines.append(f"  Notes: {notes}")
        if task.web_link:
            lines.append(f"  Link: {task.web_link}")

    if due_collection.truncated > 0:
        extra = due_collection.truncated
        extra_word = "task" if extra == 1 else "tasks"
        lines.append(
            f"(+{extra} additional due {extra_word} not shown; increase max_results "
            "or refine the filters to view more.)"
        )
    elif due_collection.has_additional:
        lines.append(
            "Additional due tasks may exist; increase max_results or adjust the "
            "filters to view more."
        )

    if due_collection.warnings:
        lines.append("Warnings:")
        for warning in due_collection.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines)


@mcp.tool("tasks_list_unscheduled")
async def list_unscheduled_tasks(
    *,
    user_email: str = DEFAULT_USER_EMAIL,
    task_list_id: Optional[str] = None,
    max_results: Optional[int] = None,
    page_token: Optional[str] = None,
    show_completed: bool = False,
    show_deleted: bool = False,
    show_hidden: bool = False,
) -> str:
    """List tasks that do not have a scheduled due date."""

    if not task_list_id:
        return "task_list_id is required to list unscheduled tasks."

    try:
        task_service = TaskService(user_email, service_factory=get_tasks_service)
        # Resolve friendly titles to canonical IDs when possible
        effective_list_id = task_list_id
        list_label = task_list_id
        resolved = await _resolve_task_list_identifier(task_service, task_list_id)
        if resolved is not None:
            effective_list_id, list_label = resolved

        list_limit = max_results if max_results is not None else 50
        unscheduled_tasks: list[Task] = []
        next_page_token = page_token
        scheduled_found = False

        while True:
            page_tasks, page_next = await task_service.list_tasks(
                effective_list_id,
                max_results=list_limit,
                page_token=next_page_token,
                show_completed=show_completed,
                show_deleted=show_deleted,
                show_hidden=show_hidden,
            )

            if not page_tasks:
                next_page_token = page_next
                break

            for task in page_tasks:
                if task.due:
                    scheduled_found = True
                    continue

                unscheduled_tasks.append(task)
                if len(unscheduled_tasks) >= list_limit:
                    next_page_token = page_next
                    break

            if len(unscheduled_tasks) >= list_limit:
                break

            if not page_next:
                next_page_token = None
                break

            next_page_token = page_next

    except TaskAuthorizationError as exc:
        return (
            f"Authentication error: {exc}. Use calendar_generate_auth_url "
            "with force=true to authorize Google Tasks."
        )
    except TaskServiceError as exc:
        return str(exc)

    if not unscheduled_tasks:
        message = f"No unscheduled tasks found in list {list_label} for {user_email}."
        if scheduled_found:
            message += " Use calendar_list_tasks to view items with due dates."
        return message

    lines = [(f"Tasks without due date/time in list {list_label} for {user_email}:")]

    for task in unscheduled_tasks:
        lines.append(f"- {task.title} (ID: {task.id})")
        lines.append(f"  Status: {task.status}")
        lines.append(f"  Updated: {task.updated or 'N/A'}")
        lines.append("  Due: Not scheduled")
        if task.completed:
            lines.append(f"  Completed: {task.completed}")
        if task.notes:
            notes = task.notes.strip()
            if len(notes) > 200:
                notes = notes[:197] + "..."
            if notes:
                lines.append(f"  Notes: {notes}")
        if task.web_link:
            lines.append(f"  Link: {task.web_link}")

    if scheduled_found:
        lines.append("Use calendar_list_tasks to view items that have due dates.")

    if next_page_token:
        lines.append(f"Next page token: {next_page_token}")

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
        due_min: Optional lower bound for due dates (keywords like "today" supported).
        due_max: Optional upper bound for due dates (keywords supported).

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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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

    # Ensure context cache is refreshed so calendar_get_events will run.
    await calendar_current_context()

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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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

    ⚠️  PREREQUISITE: If setting a due date, call calendar_current_context() first
    to ensure accurate date interpretation (e.g., what "today" or "tomorrow" means).

    Args:
        user_email: The user's email address.
        task_list_id: Task list identifier (default: '@default').
        title: Title for the new task.
        notes: Optional detailed notes.
        due: Optional due date/time. Use ISO format (YYYY-MM-DD) or keywords
             (today, tomorrow). Get exact dates from calendar_current_context.
        parent: Optional parent task ID for subtasks.
        previous: Optional sibling task ID for positioning.

    Returns:
        Confirmation message with task details.
    """
    guard_message = _require_recent_context()
    if guard_message:
        return guard_message

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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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
        due: Optional new due date/time (keywords supported).

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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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
            "Use calendar_generate_auth_url with force=true to authorize Google Tasks."
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
            "Use calendar_generate_auth_url to authorize this account."
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
    "auth_status",
    "generate_auth_url",
    "calendar_current_context",
    "get_events",
    "create_event",
    "update_event",
    "delete_event",
    "list_calendars",
    "list_task_lists",
    "list_tasks",
    "list_unscheduled_tasks",
    "search_all_tasks",
    "user_context_from_tasks",
    "get_task",
    "create_task",
    "update_task",
    "delete_task",
    "move_task",
    "clear_completed_tasks",
]
