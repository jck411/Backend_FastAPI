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
)
from backend.services.time_context import build_context_lines, create_time_snapshot


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
        "Confirm the current date and time using calendar_current_context "
        "before requesting date-based calendar operations."
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

for definition in DEFAULT_CALENDAR_DEFINITIONS:
    cal_id = definition["id"]
    _CALENDAR_ID_TO_LABEL[cal_id] = definition["label"]
    _CALENDAR_ALIAS_TO_ID[cal_id.lower()] = cal_id
    for alias in definition["aliases"]:
        _CALENDAR_ALIAS_TO_ID[alias.lower()] = cal_id

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

    normalized = calendar_id.strip().lower()
    return _CALENDAR_ALIAS_TO_ID.get(normalized, calendar_id)


def _calendar_label(calendar_id: str) -> str:
    """Return a human-friendly label for a calendar ID."""

    canonical = _CALENDAR_ALIAS_TO_ID.get(calendar_id.lower(), calendar_id)
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


def _parse_time_string(time_str: Optional[str]) -> Optional[str]:
    """
    Convert keywords like 'today', 'tomorrow' to RFC3339 timestamps.

    Args:
        time_str: Time string to parse (keyword or ISO format)

    Returns:
        RFC3339 formatted timestamp or None if input is None
    """
    if not time_str:
        return None

    if time_str.lower() == "today":
        date_obj = datetime.date.today()
        return f"{date_obj.isoformat()}T00:00:00Z"
    elif time_str.lower() == "tomorrow":
        date_obj = datetime.date.today() + datetime.timedelta(days=1)
        return f"{date_obj.isoformat()}T00:00:00Z"
    elif time_str.lower() == "yesterday":
        date_obj = datetime.date.today() - datetime.timedelta(days=1)
        return f"{date_obj.isoformat()}T00:00:00Z"
    elif time_str.lower() == "next_week":
        date_obj = datetime.date.today() + datetime.timedelta(days=7)
        return f"{date_obj.isoformat()}T00:00:00Z"  # If it's already in ISO format, ensure it has timezone info
    try:
        parsed_dt = parser.parse(time_str)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=datetime.timezone.utc)

        iso_value = parsed_dt.isoformat()
        if iso_value.endswith("+00:00"):
            iso_value = iso_value[:-6] + "Z"
        return iso_value
    except ValueError:
        # If parsing fails, assume it's already in a valid format
        return time_str


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
    """Report the up-to-date calendar context and record that it was checked."""

    snapshot = create_time_snapshot(timezone)
    _mark_context_checked(snapshot.now_utc)

    lines = list(build_context_lines(snapshot))
    lines.append(
        "Use these values when preparing time ranges, and re-run this tool if "
        "your reasoning depends on the current date."
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
    Retrieve events across the user's Google calendars.

    Always call ``calendar_current_context`` first so the LLM has an accurate
    notion of "today". With no ``calendar_id`` (or when using phrases such as
    "my schedule") the search spans the preconfigured household calendars.
    Provide a specific ID or friendly name (for example "Family Calendar" or
    "Dad Work Schedule") to narrow the query to a single calendar.

    Args:
        user_email: The user's email address (defaults to Jack's primary account).
        calendar_id: Optional calendar ID or friendly name.
        time_min: Start time (ISO format or keywords like "today").
        time_max: End time (optional, ISO format or keywords).
        max_results: Maximum number of events to return after aggregation.
        query: Optional search query.
        detailed: Whether to include full details in results.

    Returns:
        Formatted string with event details.
    """

    try:
        guard_message = _require_recent_context()
        if guard_message:
            return guard_message

        service = get_calendar_service(user_email)

        time_min_rfc = _parse_time_string(time_min)
        time_max_rfc = _parse_time_string(time_max) if time_max else None

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

            if not google_events:
                continue

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
                events_with_keys.append((_event_sort_key(event_info.start), event_info))

        if not events_with_keys:
            if warnings:
                warning_text = "; ".join(warnings)
                return (
                    f"No events found for {user_email}. Encountered issues with: "
                    f"{warning_text}."
                )

            if aggregate:
                return (
                    f"No events found for {user_email} across the configured "
                    f"calendars ({', '.join(calendar_labels)})."
                )

            return (
                f"No events found for {user_email} in calendar '{calendar_labels[0]}'."
            )

        events_with_keys.sort(key=lambda item: item[0])
        ordered_events = [event for _, event in events_with_keys]

        if aggregate:
            ordered_events = _deduplicate_events(ordered_events)

        selected_events = ordered_events[:max_results]

        result_lines = [f"Found {len(selected_events)} events for {user_email}:"]

        if aggregate or len(calendar_labels) > 1:
            result_lines.append("Calendars scanned: " + ", ".join(calendar_labels))
        elif calendar_labels:
            result_lines.append(f"Calendar: {calendar_labels[0]}")

        for event in selected_events:
            if event.is_all_day:
                # Check if it's a multi-day event
                try:
                    start_date = datetime.date.fromisoformat(event.start)
                    end_date = datetime.date.fromisoformat(event.end)
                    # Google Calendar API returns exclusive end dates for all-day events
                    # So we need to subtract 1 day to get the actual last day
                    actual_end_date = end_date - datetime.timedelta(days=1)

                    if start_date == actual_end_date:
                        timing = f"All day on {event.start}"
                    else:
                        timing = f"All day from {event.start} to {actual_end_date.isoformat()}"
                except (ValueError, TypeError):
                    # Fallback if date parsing fails
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
]
