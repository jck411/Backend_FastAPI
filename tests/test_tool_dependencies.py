"""Tests for automatic tool dependency expansion."""

from backend.chat.tool_context_planner import ToolCandidate, ToolContextPlan
from backend.chat.tool_dependencies import expand_tool_plan_with_dependencies


def test_expand_adds_calendar_auth_for_get_events():
    """When calendar_get_events is in the plan, calendar_auth_status should be added."""
    plan = ToolContextPlan(
        stages=[["calendar"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="calendar_get_events", description="Get events"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    tool_names = {t.name for t in expanded.candidate_tools["calendar"]}
    assert "calendar_auth_status" in tool_names
    assert "calendar_get_events" in tool_names
    # Auth should be first
    assert expanded.candidate_tools["calendar"][0].name == "calendar_auth_status"


def test_expand_adds_calendar_auth_for_list_tasks():
    """When list_tasks is in the plan, calendar_auth_status should be added."""
    plan = ToolContextPlan(
        stages=[["calendar"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="list_tasks", description="List tasks"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    tool_names = {t.name for t in expanded.candidate_tools["calendar"]}
    assert "calendar_auth_status" in tool_names
    assert "list_tasks" in tool_names
    assert expanded.candidate_tools["calendar"][0].name == "calendar_auth_status"


def test_expand_doesnt_duplicate_auth_tools():
    """If auth tool is already present, don't add it again."""
    plan = ToolContextPlan(
        stages=[["calendar"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="calendar_auth_status", description="Auth check"),
                ToolCandidate(name="calendar_get_events", description="Get events"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    tool_names = [t.name for t in expanded.candidate_tools["calendar"]]
    # Should have exactly 2 tools, not 3
    assert len(tool_names) == 2
    assert tool_names.count("calendar_auth_status") == 1


def test_expand_handles_multiple_dependent_tools():
    """Multiple data tools sharing same auth should only add auth once."""
    plan = ToolContextPlan(
        stages=[["calendar"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="calendar_get_events", description="Get events"),
                ToolCandidate(name="list_tasks", description="List tasks"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    tool_names = [t.name for t in expanded.candidate_tools["calendar"]]
    assert tool_names.count("calendar_auth_status") == 1
    assert "calendar_get_events" in tool_names
    assert "list_tasks" in tool_names
    # Auth should be first
    assert tool_names[0] == "calendar_auth_status"


def test_expand_handles_multiple_contexts():
    """Expansion should work across multiple contexts."""
    plan = ToolContextPlan(
        stages=[["calendar", "gmail"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="calendar_get_events", description="Get events"),
            ],
            "gmail": [
                ToolCandidate(name="gmail_list_messages", description="List emails"),
            ],
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    calendar_tools = {t.name for t in expanded.candidate_tools["calendar"]}
    gmail_tools = {t.name for t in expanded.candidate_tools["gmail"]}

    assert "calendar_auth_status" in calendar_tools
    assert "gmail_auth_status" in gmail_tools


def test_expand_empty_plan():
    """Empty plan should remain empty."""
    plan = ToolContextPlan(stages=[], candidate_tools={})

    expanded = expand_tool_plan_with_dependencies(plan)

    assert expanded.candidate_tools == {}


def test_expand_tools_without_dependencies():
    """Tools that don't require auth should be left alone."""
    plan = ToolContextPlan(
        stages=[["general"]],
        candidate_tools={
            "general": [
                ToolCandidate(name="some_random_tool", description="Random tool"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    tool_names = [t.name for t in expanded.candidate_tools["general"]]
    assert len(tool_names) == 1
    assert tool_names[0] == "some_random_tool"


def test_expand_preserves_auth_tool_metadata():
    """Added auth tools should have proper metadata."""
    plan = ToolContextPlan(
        stages=[["calendar"]],
        candidate_tools={
            "calendar": [
                ToolCandidate(name="list_tasks", description="List tasks"),
            ]
        },
    )

    expanded = expand_tool_plan_with_dependencies(plan)

    auth_tool = expanded.candidate_tools["calendar"][0]
    assert auth_tool.name == "calendar_auth_status"
    assert auth_tool.description is not None
    assert "auto-added" in auth_tool.description.lower()
    assert auth_tool.score == 1.0
