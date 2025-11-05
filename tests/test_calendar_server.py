"""Tests for the calendar MCP server."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.mcp_servers.calendar_server import (
    DEFAULT_READ_CALENDAR_IDS,
    DEFAULT_USER_EMAIL,
    _parse_time_string,
    auth_status,
    create_event,
    delete_event,
    generate_auth_url,
    get_events,
    list_calendars,
    update_event,
)
from backend.mcp_servers.calendar_server import (
    create_task as calendar_create_task,
)
from backend.mcp_servers.calendar_server import (
    delete_task as calendar_delete_task,
)
from backend.mcp_servers.calendar_server import (
    list_task_lists as calendar_list_task_lists,
)
from backend.mcp_servers.calendar_server import (
    list_tasks as list_tasks_tool,
)
from backend.mcp_servers.calendar_server import (
    update_task as calendar_update_task,
)
from backend.tasks.models import Task, TaskListInfo
from backend.tasks.utils import parse_rfc3339_datetime


def test_parse_time_string_none():
    """Test parsing None."""
    assert _parse_time_string(None) is None


def test_parse_time_string_iso_date():
    """Date-only strings gain midnight UTC."""

    assert _parse_time_string("2025-10-12") == "2025-10-12T00:00:00Z"


def test_parse_time_string_naive_datetime():
    """Naive datetimes are treated as UTC."""

    assert _parse_time_string("2025-10-12T09:30:00") == "2025-10-12T09:30:00Z"


def test_parse_time_string_preserves_timezone():
    """Offset-aware datetimes pass through unchanged."""

    value = "2025-10-12T09:30:00-05:00"
    assert _parse_time_string(value) == value


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_get_events_authentication_error(mock_get_calendar_service):
    """Test get_events with authentication error."""
    # Mock the service to raise ValueError
    mock_get_calendar_service.side_effect = ValueError("Authentication failed")

    # Call the function
    result = await get_events(user_email="test@example.com")

    # Check the result
    assert "Authentication error" in result
    assert "Authentication failed" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_get_events_success(mock_get_calendar_service, mock_get_tasks_service):
    """Test get_events with successful response."""
    mock_service = MagicMock()
    mock_get_calendar_service.return_value = mock_service

    def list_side_effect(calendarId, **kwargs):
        response = MagicMock()
        if calendarId == "primary":
            response.execute.return_value = {
                "items": [
                    {
                        "id": "event123",
                        "summary": "Test Event",
                        "start": {"dateTime": "2023-06-01T10:00:00Z"},
                        "end": {"dateTime": "2023-06-01T11:00:00Z"},
                        "htmlLink": "https://calendar.google.com/event?id=event123",
                    }
                ]
            }
        else:
            response.execute.return_value = {"items": []}
        return response

    mock_service.events().list.side_effect = list_side_effect

    # Mock tasks service to return no tasks
    mock_tasks_service = MagicMock()
    mock_get_tasks_service.return_value = mock_tasks_service

    tasklists_list_request = MagicMock()
    tasklists_list_request.execute.return_value = {"items": []}
    mock_tasks_service.tasklists.return_value.list.return_value = tasklists_list_request

    result = await get_events(time_min="2023-06-01")

    assert (
        f"Schedule for {DEFAULT_USER_EMAIL}: 1 calendar event, 0 due tasks." in result
    )
    assert "Calendars scanned:" in result
    assert "Test Event" in result
    assert "[Calendar: Your Primary Calendar]" in result
    assert mock_service.events().list.call_count == len(DEFAULT_READ_CALENDAR_IDS)


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.TaskService")
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_get_events_defaults_time_min(
    mock_get_calendar_service, mock_task_service
):
    """Default schedules should start at the current moment."""

    before_call = datetime.datetime.now(datetime.timezone.utc)

    mock_service = MagicMock()
    mock_get_calendar_service.return_value = mock_service

    list_request = MagicMock()
    list_request.execute.return_value = {
        "items": [
            {
                "id": "future-event",
                "summary": "Future Planning",
                "start": {"dateTime": "2100-01-01T09:00:00Z"},
                "end": {"dateTime": "2100-01-01T10:00:00Z"},
                "htmlLink": "https://calendar.google.com/event?eid=future",
            }
        ]
    }
    mock_service.events().list.return_value = list_request

    task_collection = SimpleNamespace(tasks=[], remaining=0, warnings=[])
    mock_task_service.return_value.collect_scheduled_tasks = AsyncMock(
        return_value=task_collection
    )

    result = await get_events()

    after_call = datetime.datetime.now(datetime.timezone.utc)

    assert f"Schedule for {DEFAULT_USER_EMAIL}" in result
    assert "Future Planning" in result
    assert mock_service.events().list.call_count == len(DEFAULT_READ_CALENDAR_IDS)

    for call_args in mock_service.events().list.call_args_list:
        time_min_value = call_args.kwargs.get("timeMin")
        assert time_min_value is not None
        parsed = parse_rfc3339_datetime(time_min_value)
        assert parsed is not None
        assert (
            before_call - datetime.timedelta(seconds=5)
            <= parsed
            <= after_call + datetime.timedelta(seconds=5)
        )


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_get_events_specific_calendar_alias(mock_get_calendar_service):
    """The helper resolves friendly calendar names to canonical IDs."""

    mock_service = MagicMock()
    mock_get_calendar_service.return_value = mock_service

    list_mock = MagicMock()
    list_mock.execute.return_value = {
        "items": [
            {
                "id": "event-family",
                "summary": "Family Meeting",
                "start": {"date": "2023-06-02"},
                "end": {"date": "2023-06-03"},
            }
        ]
    }

    mock_service.events().list.return_value = list_mock

    result = await get_events(
        user_email="test@example.com",
        calendar_id="Family Calendar",
        time_min="2023-06-01",
    )

    mock_service.events().list.assert_called_once()
    assert (
        mock_service.events().list.call_args.kwargs["calendarId"]
        == "family08001023161820261147@group.calendar.google.com"
    )
    assert "Found 1 events for test@example.com" in result
    assert "Calendar: Family Calendar" in result
    assert "[Calendar: Family Calendar]" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_get_events_includes_tasks(
    mock_get_calendar_service, mock_get_tasks_service
):
    """Aggregated schedule output includes due tasks."""

    mock_calendar_service = MagicMock()
    mock_get_calendar_service.return_value = mock_calendar_service

    # No calendar events returned
    calendar_list_request = MagicMock()
    calendar_list_request.execute.return_value = {"items": []}
    mock_calendar_service.events.return_value.list.return_value = calendar_list_request

    mock_tasks_service = MagicMock()
    mock_get_tasks_service.return_value = mock_tasks_service

    # Provide a single task list
    tasklists_list_request = MagicMock()
    tasklists_list_request.execute.return_value = {
        "items": [{"id": "list-1", "title": "Personal"}]
    }
    mock_tasks_service.tasklists.return_value.list.return_value = tasklists_list_request

    # Provide a due task
    tasks_list_request = MagicMock()
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    due_str = (now + datetime.timedelta(days=1)).isoformat().replace("+00:00", "Z")
    tasks_list_request.execute.return_value = {
        "items": [
            {
                "id": "task-1",
                "title": "Buy groceries",
                "status": "needsAction",
                "due": due_str,
                "notes": "Remember milk",
                "webViewLink": "https://tasks.google.com/task-1",
            }
        ]
    }
    mock_tasks_service.tasks.return_value.list.return_value = tasks_list_request

    result = await get_events(user_email="test@example.com", max_results=5)

    assert "Tasks due or overdue:" in result
    assert "Buy groceries" in result
    assert "No tasks with due dates in this range." not in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_create_event_success(mock_get_calendar_service):
    """Test create_event with successful response."""
    # Create mock service
    mock_service = MagicMock()
    mock_insert = MagicMock()

    # Configure the mock service
    mock_service.events().insert.return_value.execute = mock_insert
    mock_get_calendar_service.return_value = mock_service

    # Configure mock response (should return value directly, not coroutine)
    mock_insert.return_value = {
        "id": "event123",
        "summary": "Test Event",
        "htmlLink": "https://calendar.google.com/event?id=event123",
    }

    # Call the function
    result = await create_event(
        user_email="test@example.com",
        summary="Test Event",
        start_time="2023-06-01T10:00:00Z",
        end_time="2023-06-01T11:00:00Z",
    )

    # Check the result
    assert "Successfully created event" in result
    assert "Test Event" in result
    assert "Your Primary Calendar" in result
    assert "ID: primary" in result
    assert "https://calendar.google.com/event?id=event123" in result
    insert_kwargs = mock_service.events().insert.call_args.kwargs
    assert insert_kwargs["calendarId"] == "primary"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_update_event_success(mock_get_calendar_service):
    """Test update_event with successful response."""
    # Create mock service
    mock_service = MagicMock()
    mock_get = MagicMock()
    mock_update = MagicMock()

    # Configure the mock service
    mock_service.events().get.return_value.execute = mock_get
    mock_service.events().update.return_value.execute = mock_update
    mock_get_calendar_service.return_value = mock_service

    # Configure mock responses (should return values directly, not coroutines)
    mock_get.return_value = {
        "id": "event123",
        "summary": "Old Title",
        "start": {"dateTime": "2023-06-01T10:00:00Z"},
        "end": {"dateTime": "2023-06-01T11:00:00Z"},
    }
    mock_update.return_value = {
        "id": "event123",
        "summary": "Updated Title",
        "htmlLink": "https://calendar.google.com/event?id=event123",
    }

    # Call the function
    result = await update_event(
        user_email="test@example.com",
        event_id="event123",
        summary="Updated Title",
    )

    # Check the result
    assert "Successfully updated event" in result
    assert "Updated Title" in result
    assert "Your Primary Calendar" in result
    assert "ID: primary" in result
    get_kwargs = mock_service.events().get.call_args.kwargs
    update_kwargs = mock_service.events().update.call_args.kwargs
    assert get_kwargs["calendarId"] == "primary"
    assert update_kwargs["calendarId"] == "primary"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_delete_event_success(mock_get_calendar_service):
    """Test delete_event with successful response."""
    # Create mock service
    mock_service = MagicMock()
    mock_get = MagicMock()
    mock_delete = MagicMock()

    # Configure the mock service
    mock_service.events().get.return_value.execute = mock_get
    mock_service.events().delete.return_value.execute = mock_delete
    mock_get_calendar_service.return_value = mock_service

    # Configure mock response (should return value directly, not coroutine)
    mock_get.return_value = {"id": "event123", "summary": "Test Event"}

    # Call the function
    result = await delete_event(
        user_email="test@example.com",
        event_id="event123",
    )

    # Check the result
    assert "Successfully deleted event" in result
    assert "Test Event" in result
    assert "Your Primary Calendar" in result
    assert "ID: primary" in result
    get_kwargs = mock_service.events().get.call_args.kwargs
    delete_kwargs = mock_service.events().delete.call_args.kwargs
    assert get_kwargs["calendarId"] == "primary"
    assert delete_kwargs["calendarId"] == "primary"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_list_task_lists_success(mock_get_tasks_service):
    """calendar_list_task_lists returns task lists."""

    mock_service = MagicMock()
    mock_get_tasks_service.return_value = mock_service

    list_request = MagicMock()
    list_request.execute.return_value = {
        "items": [
            {"id": "list-1", "title": "Personal", "updated": "2024-05-01T12:00:00Z"}
        ]
    }
    mock_service.tasklists.return_value.list.return_value = list_request

    result = await calendar_list_task_lists(user_email="user@example.com")

    assert "Task lists for user@example.com" in result
    assert "Personal" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_list_task_lists_auth_error(mock_get_tasks_service):
    """calendar_list_task_lists reports auth issues."""

    mock_get_tasks_service.side_effect = ValueError("No credentials")

    result = await calendar_list_task_lists(user_email="user@example.com")

    assert "Authentication error" in result
    assert "Google Tasks" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_list_tasks_authentication_error(mock_get_tasks_service):
    """list_tasks surfaces authentication guidance when credentials are missing."""

    mock_get_tasks_service.side_effect = ValueError("Missing")

    result = await list_tasks_tool(user_email="user@example.com")

    assert "Authentication error" in result
    assert "Google Tasks" in result


@pytest.mark.asyncio
@patch(
    "backend.mcp_servers.calendar_server.TaskService.list_task_lists",
    new_callable=AsyncMock,
)
async def test_list_tasks_requests_list_selection(mock_list_task_lists):
    """list_tasks prompts the caller to pick a list when none is provided."""

    mock_list_task_lists.return_value = (
        [
            TaskListInfo(id="list-1", title="Personal"),
            TaskListInfo(id="list-2", title="Work"),
        ],
        None,
    )

    result = await list_tasks_tool(user_email="user@example.com")

    assert "Task lists" in result
    assert "Personal" in result
    assert "Work" in result


@pytest.mark.asyncio
@patch(
    "backend.mcp_servers.calendar_server.TaskService.list_tasks",
    new_callable=AsyncMock,
)
@patch(
    "backend.mcp_servers.calendar_server.TaskService.get_task_list",
    new_callable=AsyncMock,
)
async def test_list_tasks_combines_scheduled_and_unscheduled(
    mock_get_task_list,
    mock_list_tasks,
):
    """list_tasks returns both scheduled and unscheduled items sorted by due date."""

    mock_get_task_list.return_value = TaskListInfo(id="list-1", title="Personal")

    due_time = datetime.datetime(2025, 10, 13, tzinfo=datetime.timezone.utc)
    tasks = [
        Task(
            title="Water plants",
            status="needsAction",
            list_title="Personal",
            list_id="list-1",
            id="task-1",
            due=due_time,
            notes="Use filtered water",
        ),
        Task(
            title="Buy soil",
            status="needsAction",
            list_title="Personal",
            list_id="list-1",
            id="task-2",
            due=None,
        ),
    ]
    mock_list_tasks.return_value = (tasks, None)

    result = await list_tasks_tool(user_email="user@example.com", task_list_id="list-1")

    assert "Water plants" in result
    assert "Due 2025-10-13" in result
    assert "Buy soil" in result
    assert "Unscheduled" in result
    assert result.index("Water plants") < result.index("Buy soil")


@pytest.mark.asyncio
@patch(
    "backend.mcp_servers.calendar_server.TaskService.list_tasks",
    new_callable=AsyncMock,
)
@patch(
    "backend.mcp_servers.calendar_server.TaskService.get_task_list",
    new_callable=AsyncMock,
)
async def test_list_tasks_unscheduled_filter(mock_get_task_list, mock_list_tasks):
    """list_tasks can limit results to unscheduled items only."""

    mock_get_task_list.return_value = TaskListInfo(id="list-1", title="Personal")

    due_time = datetime.datetime(2025, 11, 1, tzinfo=datetime.timezone.utc)
    tasks = [
        Task(
            title="Draft proposal",
            status="needsAction",
            list_title="Personal",
            list_id="list-1",
            id="task-3",
            due=due_time,
        ),
        Task(
            title="Clean garage",
            status="needsAction",
            list_title="Personal",
            list_id="list-1",
            id="task-4",
            due=None,
        ),
    ]
    mock_list_tasks.return_value = (tasks, None)

    result = await list_tasks_tool(
        user_email="user@example.com",
        task_list_id="list-1",
        task_filter="unscheduled",
    )

    assert "Clean garage" in result
    assert "Draft proposal" not in result


@pytest.mark.asyncio
async def test_list_tasks_invalid_filter() -> None:
    """Invalid task_filter values return a helpful message."""

    result = await list_tasks_tool(
        user_email="user@example.com",
        task_list_id="list-1",
        task_filter="invalid",
    )

    assert "Invalid task_filter" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_create_task_due_conversion(mock_get_tasks_service):
    """calendar_create_task normalizes due date strings."""

    mock_service = MagicMock()
    mock_get_tasks_service.return_value = mock_service

    insert_request = MagicMock()
    insert_request.execute.return_value = {
        "id": "task-1",
        "title": "New Task",
        "status": "needsAction",
        "updated": "2024-05-01T12:00:00Z",
        "due": "2025-01-01T00:00:00Z",
    }
    mock_service.tasks.return_value.insert.return_value = insert_request

    await calendar_create_task(
        user_email="user@example.com",
        title="New Task",
        due="2025-01-01",
    )

    insert_kwargs = mock_service.tasks.return_value.insert.call_args.kwargs
    assert insert_kwargs["body"]["due"] == "2025-01-01T00:00:00Z"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_update_task_preserves_existing_fields(mock_get_tasks_service):
    """calendar_update_task pulls current task data before updating."""

    mock_service = MagicMock()
    mock_get_tasks_service.return_value = mock_service

    get_request = MagicMock()
    get_request.execute.return_value = {
        "id": "task-1",
        "title": "Old Task",
        "status": "needsAction",
        "due": "2024-06-01T00:00:00Z",
        "notes": "Existing notes",
    }
    mock_service.tasks.return_value.get.return_value = get_request

    update_request = MagicMock()
    update_request.execute.return_value = {
        "id": "task-1",
        "title": "Old Task",
        "status": "completed",
        "updated": "2024-06-02T10:00:00Z",
        "due": "2024-06-01T00:00:00Z",
    }
    mock_service.tasks.return_value.update.return_value = update_request

    result = await calendar_update_task(
        user_email="user@example.com",
        task_id="task-1",
        status="completed",
    )

    assert "Updated task 'Old Task'" in result
    update_kwargs = mock_service.tasks.return_value.update.call_args.kwargs
    assert update_kwargs["body"]["status"] == "completed"
    assert update_kwargs["body"]["title"] == "Old Task"
    assert update_kwargs["body"]["due"] == "2024-06-01T00:00:00Z"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_tasks_service")
async def test_delete_task_success(mock_get_tasks_service):
    """calendar_delete_task deletes tasks via the API."""

    mock_service = MagicMock()
    mock_get_tasks_service.return_value = mock_service
    delete_request = MagicMock()
    delete_request.execute.return_value = None
    mock_service.tasks.return_value.delete.return_value = delete_request

    result = await calendar_delete_task(
        user_email="user@example.com",
        task_id="task-1",
    )

    assert "Task task-1 deleted" in result
    delete_kwargs = mock_service.tasks.return_value.delete.call_args.kwargs
    assert delete_kwargs["task"] == "task-1"


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_credentials")
async def test_auth_status_authorized(mock_get_credentials):
    """calendar_auth_status reports when credentials exist."""
    mock_credentials = MagicMock()
    mock_credentials.expiry = datetime.datetime(
        2025, 1, 1, tzinfo=datetime.timezone.utc
    )
    mock_get_credentials.return_value = mock_credentials

    result = await auth_status("user@example.com")

    assert "already authorized" in result
    assert "force=true" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_credentials")
async def test_auth_status_missing(mock_get_credentials):
    """calendar_auth_status instructs user to authorize when missing."""
    mock_get_credentials.return_value = None

    result = await auth_status("user@example.com")

    assert "No stored Google Calendar credentials" in result
    assert "calendar_generate_auth_url" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.authorize_user")
@patch("backend.mcp_servers.calendar_server.get_credentials")
async def test_generate_auth_url_existing_credentials(
    mock_get_credentials, mock_authorize_user
):
    """calendar_generate_auth_url short-circuits unless force is set."""
    mock_credentials = MagicMock()
    mock_credentials.expiry = datetime.datetime(
        2025, 1, 1, tzinfo=datetime.timezone.utc
    )
    mock_get_credentials.return_value = mock_credentials

    result = await generate_auth_url("user@example.com")

    assert "already has stored credentials" in result
    mock_authorize_user.assert_not_called()


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.authorize_user")
@patch("backend.mcp_servers.calendar_server.get_credentials")
async def test_generate_auth_url_force_flow(mock_get_credentials, mock_authorize_user):
    """calendar_generate_auth_url returns instructions when forced."""
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials
    mock_authorize_user.return_value = "https://auth.example.com"

    result = await generate_auth_url(
        "user@example.com", redirect_uri="https://app.example.com/callback", force=True
    )

    assert "https://auth.example.com" in result
    assert "Follow these steps" in result
    assert "Advanced" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_list_calendars_success(mock_get_calendar_service):
    """calendar_list_calendars returns summaries for calendars."""
    mock_service = MagicMock()
    mock_get_calendar_service.return_value = mock_service
    mock_execute = MagicMock()
    mock_execute.return_value = {
        "items": [
            {
                "summary": "Primary",
                "id": "primary",
                "primary": True,
                "accessRole": "owner",
            },
            {
                "summary": "Team Calendar",
                "id": "team@example.com",
                "accessRole": "reader",
            },
        ]
    }
    mock_service.calendarList.return_value.list.return_value.execute = mock_execute

    result = await list_calendars("user@example.com")

    assert "Found 2 calendars" in result
    assert '"Primary" [primary]' in result
    assert "team@example.com" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.calendar_server.get_calendar_service")
async def test_list_calendars_auth_error(mock_get_calendar_service):
    """calendar_list_calendars handles missing credentials."""
    mock_get_calendar_service.side_effect = ValueError("No credentials")

    result = await list_calendars("user@example.com")

    assert "Authentication error" in result
    assert "calendar_generate_auth_url" in result
