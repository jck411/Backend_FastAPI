"""Calendar CRUD API router for the main calendar UI."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.services.google_auth.auth import DEFAULT_USER_EMAIL, get_calendar_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calendar", tags=["Calendar"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class EventIn(BaseModel):
    summary: str
    start: str  # ISO date or datetime
    end: str
    all_day: bool = False
    description: Optional[str] = None
    location: Optional[str] = None
    calendar_id: str = "primary"


class EventOut(BaseModel):
    id: str
    summary: str
    start: str
    end: str
    all_day: bool
    calendar_id: str
    calendar_name: str
    color: Optional[str] = None
    html_link: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


class CalendarInfo(BaseModel):
    id: str
    summary: str
    color: str
    primary: bool = False
    access_role: str = "reader"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_event(event: dict, cal_id: str, cal_name: str, color: str | None = None) -> EventOut:
    start = event.get("start", {})
    end = event.get("end", {})
    is_all_day = "date" in start
    return EventOut(
        id=event.get("id", ""),
        summary=event.get("summary", "(No title)"),
        start=start.get("date") or start.get("dateTime", ""),
        end=end.get("date") or end.get("dateTime", ""),
        all_day=is_all_day,
        calendar_id=cal_id,
        calendar_name=cal_name,
        color=color,
        html_link=event.get("htmlLink"),
        description=event.get("description"),
        location=event.get("location"),
    )


def _svc():
    """Shortcut to get the calendar service."""
    return get_calendar_service(DEFAULT_USER_EMAIL)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/calendars", response_model=list[CalendarInfo])
async def list_calendars():
    """Return all calendars the user has access to."""
    svc = _svc()
    result = await asyncio.to_thread(svc.calendarList().list().execute)
    items = result.get("items", [])
    return [
        CalendarInfo(
            id=c["id"],
            summary=c.get("summary", c["id"]),
            color=c.get("backgroundColor", "#4285f4"),
            primary=c.get("primary", False),
            access_role=c.get("accessRole", "reader"),
        )
        for c in items
    ]


@router.get("/events", response_model=list[EventOut])
async def list_events(
    start: str = Query(..., description="Start date ISO (YYYY-MM-DD)"),
    end: str = Query(..., description="End date ISO (YYYY-MM-DD)"),
):
    """Fetch events across all calendars for the given date range."""
    svc = _svc()

    # Build time bounds with timezone
    time_min = f"{start}T00:00:00Z"
    time_max = f"{end}T23:59:59Z"

    # Get all calendars first
    cal_list = await asyncio.to_thread(svc.calendarList().list().execute)
    calendars = cal_list.get("items", [])

    all_events: list[EventOut] = []

    for cal in calendars:
        cal_id = cal["id"]
        cal_name = cal.get("summary", cal_id)
        color = cal.get("backgroundColor", "#4285f4")

        try:
            result = await asyncio.to_thread(
                svc.events()
                .list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=500,
                )
                .execute
            )
            for ev in result.get("items", []):
                all_events.append(_parse_event(ev, cal_id, cal_name, color))
        except Exception as e:
            logger.warning(f"Failed to fetch calendar {cal_id}: {e}")

    # Sort by start time
    all_events.sort(key=lambda e: e.start)
    return all_events


@router.post("/events", response_model=EventOut)
async def create_event(event: EventIn):
    """Create a new calendar event."""
    svc = _svc()

    if event.all_day:
        body: dict[str, Any] = {
            "summary": event.summary,
            "start": {"date": event.start},
            "end": {"date": event.end},
        }
    else:
        body = {
            "summary": event.summary,
            "start": {"dateTime": event.start, "timeZone": "America/New_York"},
            "end": {"dateTime": event.end, "timeZone": "America/New_York"},
        }

    if event.description:
        body["description"] = event.description
    if event.location:
        body["location"] = event.location

    try:
        created = await asyncio.to_thread(
            svc.events()
            .insert(calendarId=event.calendar_id, body=body)
            .execute
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cal_list = await asyncio.to_thread(svc.calendarList().list().execute)
    cal_map = {c["id"]: c for c in cal_list.get("items", [])}
    cal = cal_map.get(event.calendar_id, {})

    return _parse_event(
        created,
        event.calendar_id,
        cal.get("summary", event.calendar_id),
        cal.get("backgroundColor"),
    )


@router.put("/events/{event_id}", response_model=EventOut)
async def update_event(event_id: str, event: EventIn):
    """Update an existing calendar event."""
    svc = _svc()

    if event.all_day:
        body: dict[str, Any] = {
            "summary": event.summary,
            "start": {"date": event.start},
            "end": {"date": event.end},
        }
    else:
        body = {
            "summary": event.summary,
            "start": {"dateTime": event.start, "timeZone": "America/New_York"},
            "end": {"dateTime": event.end, "timeZone": "America/New_York"},
        }

    if event.description:
        body["description"] = event.description
    if event.location:
        body["location"] = event.location

    try:
        updated = await asyncio.to_thread(
            svc.events()
            .update(calendarId=event.calendar_id, eventId=event_id, body=body)
            .execute
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    cal_list = await asyncio.to_thread(svc.calendarList().list().execute)
    cal_map = {c["id"]: c for c in cal_list.get("items", [])}
    cal = cal_map.get(event.calendar_id, {})

    return _parse_event(
        updated,
        event.calendar_id,
        cal.get("summary", event.calendar_id),
        cal.get("backgroundColor"),
    )


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    calendar_id: str = Query("primary", description="Calendar the event belongs to"),
):
    """Delete a calendar event."""
    svc = _svc()
    try:
        await asyncio.to_thread(
            svc.events()
            .delete(calendarId=calendar_id, eventId=event_id)
            .execute
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}
