"""Tests for LLM-based context planning."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.chat.llm_planner import LLMContextPlanner
from src.backend.schemas.chat import ChatCompletionRequest, ChatMessage


def _make_request(text: str, **kwargs) -> ChatCompletionRequest:
    """Helper to create a test request."""
    message = ChatMessage(role="user", content=text)
    return ChatCompletionRequest(messages=[message], **kwargs)


@pytest.mark.asyncio
async def test_llm_planner_uses_llm_response() -> None:
    """Test that LLM planner uses the LLM response when available."""
    mock_client = MagicMock()
    mock_client.request_tool_plan = AsyncMock(
        return_value={
            "plan": {
                "stages": [["calendar"], ["tasks"]],
                "intent": "Schedule management",
                "broad_search": False,
            }
        }
    )
    
    planner = LLMContextPlanner(mock_client)
    request = _make_request("What's on my schedule?")
    conversation = [{"role": "user", "content": "What's on my schedule?"}]
    
    plan = await planner.plan(request, conversation)

    assert plan.stages == [["calendar"], ["tasks"]]
    assert plan.intent == "Schedule management"
    assert plan.broad_search is False
    assert plan.used_fallback is False
    mock_client.request_tool_plan.assert_called_once()


@pytest.mark.asyncio
async def test_llm_planner_fallback_on_error() -> None:
    """Test that LLM planner falls back when LLM request fails."""
    mock_client = MagicMock()
    mock_client.request_tool_plan = AsyncMock(
        side_effect=Exception("LLM planner unavailable")
    )
    
    planner = LLMContextPlanner(mock_client)
    request = _make_request("What's on my schedule?")
    conversation = [{"role": "user", "content": "What's on my schedule?"}]
    
    plan = await planner.plan(request, conversation)

    # Should get fallback plan with broad search
    assert plan.broad_search is True
    assert plan.stages == []
    assert plan.intent == "General assistance with all available tools"
    assert plan.used_fallback is True


@pytest.mark.asyncio
async def test_llm_planner_explicit_tool_request() -> None:
    """Test fallback plan for explicit tool requests."""
    mock_client = MagicMock()
    mock_client.request_tool_plan = AsyncMock(
        side_effect=Exception("LLM planner unavailable")
    )
    
    planner = LLMContextPlanner(mock_client)
    request = _make_request(
        "call calendar__list",
        tool_choice={"type": "function", "function": {"name": "calendar__list"}},
    )
    conversation = [{"role": "user", "content": "call calendar__list"}]
    
    plan = await planner.plan(request, conversation)

    # Should recognize explicit tool request
    assert plan.broad_search is True
    assert plan.intent == "Use specified tools"
    assert plan.used_fallback is True


@pytest.mark.asyncio
async def test_llm_planner_compacts_tool_digest() -> None:
    """Test that tool digest is properly compacted for LLM."""
    mock_client = MagicMock()
    mock_client.request_tool_plan = AsyncMock(
        return_value={"plan": {"broad_search": True}}
    )
    
    planner = LLMContextPlanner(mock_client)
    request = _make_request("Help me")
    conversation = [{"role": "user", "content": "Help me"}]
    
    capability_digest = {
        "calendar": [
            {
                "name": "calendar__list",
                "description": "List calendar events",
                "parameters": {"type": "object"},
                "server": "calendar-server",
                "score": 0.9,
            }
        ],
        "tasks": [
            {
                "name": "tasks__list",
                "description": "List tasks",
            }
        ],
    }
    
    await planner.plan(request, conversation, capability_digest)
    
    # Verify request_tool_plan was called with compacted digest
    call_args = mock_client.request_tool_plan.call_args
    tool_digest = call_args.kwargs["tool_digest"]
    
    assert "calendar" in tool_digest
    assert tool_digest["calendar"][0]["name"] == "calendar__list"
    assert tool_digest["calendar"][0]["description"] == "List calendar events"
    assert tool_digest["calendar"][0]["score"] == 0.9
    
    assert "tasks" in tool_digest
    assert tool_digest["tasks"][0]["name"] == "tasks__list"


@pytest.mark.asyncio
async def test_llm_planner_handles_invalid_digest() -> None:
    """Test that planner handles invalid capability digest gracefully."""
    mock_client = MagicMock()
    mock_client.request_tool_plan = AsyncMock(
        return_value={"plan": {"broad_search": True}}
    )
    
    planner = LLMContextPlanner(mock_client)
    request = _make_request("Help me")
    conversation = [{"role": "user", "content": "Help me"}]
    
    # Invalid digest with non-dict entries
    capability_digest = {
        "calendar": ["not a dict", {"invalid": "no name"}],
        "tasks": None,  # Invalid entry
    }
    
    plan = await planner.plan(request, conversation, capability_digest)

    # Should still generate a plan from the LLM response
    assert plan is not None
    assert plan.used_fallback is False
    mock_client.request_tool_plan.assert_called_once()
