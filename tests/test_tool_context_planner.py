from src.backend.chat.tool_context_planner import ToolContextPlanner
from src.backend.schemas.chat import ChatCompletionRequest, ChatMessage


def _make_request(text: str, **kwargs) -> ChatCompletionRequest:
    message = ChatMessage(role="user", content=text)
    return ChatCompletionRequest(messages=[message], **kwargs)


def test_planner_picks_calendar_context() -> None:
    planner = ToolContextPlanner()
    request = _make_request("What's on my schedule tomorrow?")

    plan = planner.plan(request, [])

    assert plan.broad_search is True
    assert plan.contexts_for_attempt(0) == ["calendar"]
    assert plan.use_all_tools_for_attempt(0) is False


def test_planner_expands_habit_contexts() -> None:
    planner = ToolContextPlanner()
    request = _make_request("Help me build better habits this month")

    plan = planner.plan(request, [])

    assert plan.contexts_for_attempt(0) == ["calendar"]
    assert plan.contexts_for_attempt(1) == ["calendar", "tasks"]
    assert plan.contexts_for_attempt(2) == ["calendar", "tasks", "notes"]


def test_planner_routes_documents_to_gdrive() -> None:
    planner = ToolContextPlanner()
    request = _make_request("search docs for last year's budget")

    plan = planner.plan(request, None)

    assert plan.contexts_for_attempt(0) == ["gdrive"]


def test_planner_detects_explicit_tool_requests() -> None:
    planner = ToolContextPlanner()
    request = _make_request(
        "call tool calendar__list for everything today",
        tool_choice={"type": "function", "function": {"name": "calendar__list"}},
    )

    plan = planner.plan(request, None)

    assert plan.contexts_for_attempt(0) == []
    assert plan.use_all_tools_for_attempt(0) is True


def test_planner_defaults_to_broad_search_when_no_match() -> None:
    planner = ToolContextPlanner()
    request = _make_request("Just chatting about the weather")

    plan = planner.plan(request, None)

    assert plan.contexts_for_attempt(0) == []
    assert plan.use_all_tools_for_attempt(0) is True
