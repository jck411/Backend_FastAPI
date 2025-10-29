"""Tests for streaming handler functionality."""

import json
from types import SimpleNamespace
from typing import Any, Iterable

import pytest

from src.backend.chat.streaming import (
    StreamingHandler,
    _finalize_tool_calls,
    _merge_tool_calls,
)
from src.backend.chat.tool_context_planner import ToolContextPlan
from src.backend.openrouter import OpenRouterError
from src.backend.schemas.chat import ChatCompletionRequest, ChatMessage


class TestFinalizeToolCalls:
    """Ensure finalized tool calls are filtered and normalized."""

    def test_filters_empty_arguments(self):
        """Tool calls with empty arguments should be dropped."""
        calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calculator_evaluate", "arguments": ""},
            }
        ]

        assert _finalize_tool_calls(calls) == []

    def test_filters_whitespace_only_arguments(self):
        """Whitespace arguments should be ignored."""
        calls = [
            {
                "type": "function",
                "function": {"name": "calculator_evaluate", "arguments": "   \n\t  "},
            }
        ]

        assert _finalize_tool_calls(calls) == []

    def test_includes_valid_arguments(self):
        """Valid tool calls should be preserved and include IDs."""
        calls = [
            {
                "type": "function",
                "function": {
                    "name": "calculator_evaluate",
                    "arguments": '{"operation": "add", "a": 2, "b": 3}',
                },
            }
        ]

        result = _finalize_tool_calls(calls)

        assert len(result) == 1
        call = result[0]
        assert call["function"]["name"] == "calculator_evaluate"
        assert call["function"]["arguments"] == '{"operation": "add", "a": 2, "b": 3}'
        assert call["id"] == "call_0"

    def test_preserves_existing_ids(self):
        """Existing call IDs should remain unchanged."""
        calls = [
            {
                "id": "existing",
                "type": "function",
                "function": {
                    "name": "calculator_evaluate",
                    "arguments": '{"operation": "add", "a": 2, "b": 3}',
                },
            }
        ]

        result = _finalize_tool_calls(calls)

        assert len(result) == 1
        assert result[0]["id"] == "existing"


class TestMergeToolCalls:
    """Test the tool call delta merging logic."""

    def test_merge_accumulates_arguments(self):
        """Arguments should be accumulated across multiple deltas."""
        accumulator: list[dict[str, Any]] = []

        # First delta with partial arguments
        _merge_tool_calls(
            accumulator,
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "calculator_evaluate",
                        "arguments": '{"operation":',
                    },
                }
            ],
        )

        # Second delta with more arguments
        _merge_tool_calls(
            accumulator, [{"id": "call_1", "function": {"arguments": '"add","a":2,'}}]
        )

        # Third delta completing arguments
        _merge_tool_calls(
            accumulator, [{"id": "call_1", "function": {"arguments": '"b":3}'}}]
        )

        # Check that arguments were properly accumulated
        call = accumulator[0]
        assert call["function"]["arguments"] == '{"operation":"add","a":2,"b":3}'

    def test_merge_handles_missing_id(self):
        """Tool calls without IDs should be handled gracefully."""
        accumulator: list[dict[str, Any]] = []

        _merge_tool_calls(
            accumulator,
            [
                {
                    "type": "function",
                    "function": {
                        "name": "calculator_evaluate",
                        "arguments": '{"operation":"add"}',
                    },
                }
            ],
        )

        # Should create entry with function details populated
        assert accumulator
        assert accumulator[0]["function"]["name"] == "calculator_evaluate"


@pytest.fixture
def anyio_backend() -> str:
    """Limit AnyIO backend to asyncio for these tests."""
    return "asyncio"


class DummyOpenRouterClient:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        yield {
            "data": json.dumps(
                {
                    "id": "gen-simple",
                    "choices": [
                        {"delta": {"content": "Hello"}, "finish_reason": "stop"}
                    ],
                }
            )
        }
        yield {"data": "[DONE]"}


class DummyOpenRouterClientWithMetadata(DummyOpenRouterClient):
    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        yield {
            "event": "openrouter_headers",
            "data": json.dumps({"OpenRouter-Provider": "test/provider"}),
        }
        yield {
            "data": json.dumps(
                {
                    "id": "gen-abc123",
                    "model": "test/model",
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 7,
                        "total_tokens": 12,
                    },
                    "meta": {
                        "provider": {
                            "id": "meta-test",
                            "name": "Meta Test Provider",
                            "endpoint": "test-endpoint",
                        }
                    },
                    "choices": [
                        {
                            "delta": {"content": "Hello"},
                            "finish_reason": "stop",
                        }
                    ],
                }
            )
        }
        yield {"data": "[DONE]"}


class ToolUnsupportedClient:
    def __init__(self) -> None:
        self.calls = 0

    def stream_chat_raw(self, payload: dict[str, Any]):
        async def _generator():
            self.calls += 1
            raise OpenRouterError(
                404,
                {"error": "Tool use is not supported for this model"},
            )
            yield  # pragma: no cover - required for async generator typing

        return _generator()


class DummyRepository:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._counter = 0

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: Any,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_message_id: str | None = None,
        parent_client_message_id: str | None = None,
    ) -> tuple[int, str | None]:
        self._counter += 1
        record = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_call_id": tool_call_id,
            "metadata": metadata,
            "client_message_id": client_message_id,
            "parent_client_message_id": parent_client_message_id,
            "message_id": self._counter,
        }
        self.messages.append(record)
        return self._counter, None


class DummyToolClient:
    def get_openai_tools(self) -> list[dict[str, Any]]:
        return []

    def get_openai_tools_for_contexts(
        self, contexts: Iterable[str]
    ) -> list[dict[str, Any]]:
        return []

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:  # pragma: no cover
        raise AssertionError("call_tool should not be invoked in these tests")

    def format_tool_result(self, result: Any) -> str:  # pragma: no cover
        return ""


class ToolCallOpenRouterClient(DummyOpenRouterClient):
    def __init__(self) -> None:
        super().__init__()
        self.call_index = 0

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        if self.call_index == 0:
            self.call_index += 1
            initial_chunk = {
                "id": "gen-tool-1",
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calendar_lookup",
                                        "arguments": json.dumps({"query": "team standup"}),
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
            yield {"data": json.dumps(initial_chunk)}
            yield {"data": "[DONE]"}
            return

        self.call_index += 1
        final_chunk = {
            "id": "gen-tool-2",
            "choices": [
                {
                    "delta": {"content": "Here's what I found."},
                    "finish_reason": "stop",
                }
            ],
        }
        yield {"data": json.dumps(final_chunk)}
        yield {"data": "[DONE]"}


class MultiToolOpenRouterClient(DummyOpenRouterClient):
    def __init__(self, tool_calls: list[dict[str, Any]], final_message: str) -> None:
        super().__init__()
        self.tool_calls = tool_calls
        self.final_message = final_message
        self.call_index = 0

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        if self.call_index < len(self.tool_calls):
            call = self.tool_calls[self.call_index]
            self.call_index += 1
            arguments = call.get("arguments", {})
            if isinstance(arguments, dict):
                arguments_payload = json.dumps(arguments)
            else:
                arguments_payload = str(arguments)
            chunk = {
                "id": f"gen-tool-{self.call_index}",
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": f"call_{self.call_index}",
                                    "type": "function",
                                    "function": {
                                        "name": call.get("name", "calendar_lookup"),
                                        "arguments": arguments_payload,
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
            yield {"data": json.dumps(chunk)}
            yield {"data": "[DONE]"}
            return

        self.call_index += 1
        final_chunk = {
            "id": f"gen-final-{self.call_index}",
            "choices": [
                {
                    "delta": {"content": self.final_message},
                    "finish_reason": "stop",
                }
            ],
        }
        yield {"data": json.dumps(final_chunk)}
        yield {"data": "[DONE]"}


class ExpandingToolClient:
    def __init__(self) -> None:
        self.context_history: list[list[str]] = []
        self.results: list[str] = []
        self.calls = 0

    def get_openai_tools(self) -> list[dict[str, Any]]:
        self.context_history.append(["__all__"])
        return [
            {
                "type": "function",
                "function": {
                    "name": "global_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def get_openai_tools_for_contexts(
        self, contexts: Iterable[str]
    ) -> list[dict[str, Any]]:
        snapshot = [ctx for ctx in contexts]
        self.context_history.append(snapshot)
        label = "_".join(snapshot) if snapshot else "none"
        return [
            {
                "type": "function",
                "function": {
                    "name": f"context_{label}_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        self.calls += 1
        return SimpleNamespace(isError=False, content={})

    def format_tool_result(self, result: Any) -> str:
        index = self.calls - 1
        if 0 <= index < len(self.results):
            return self.results[index]
        return ""


class DummyModelSettings:
    def __init__(
        self, model: str, overrides: dict[str, Any], *, supports_tools: bool = True
    ) -> None:
        self._model = model
        self._overrides = overrides
        self._supports_tools = supports_tools

    async def get_openrouter_overrides(self) -> tuple[str, dict[str, Any]]:
        return self._model, self._overrides

    async def model_supports_tools(self) -> bool:
        return self._supports_tools


@pytest.mark.anyio("asyncio")
async def test_streaming_applies_provider_sort_from_settings() -> None:
    client = DummyOpenRouterClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        DummyToolClient(),  # type: ignore[arg-type]
        default_model="openrouter/auto",
        model_settings=DummyModelSettings(  # type: ignore[arg-type]
            "test/model",
            {"provider": {"sort": "price"}},
        ),
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Ping")],
    )
    conversation = [{"role": "user", "content": "Ping"}]

    events = []
    async for event in handler.stream_conversation(
        "session-1",
        request,
        conversation,
        [],
        None,
    ):
        events.append(event)

    assert events[-1]["data"] == "[DONE]"
    assert client.payloads, "Expected payload to be sent to OpenRouter"

    payload = client.payloads[0]
    assert payload["model"] == "test/model"
    assert payload["provider"]["sort"] == "price"


@pytest.mark.anyio("asyncio")
async def test_streaming_merges_request_provider_preferences() -> None:
    client = DummyOpenRouterClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        DummyToolClient(),  # type: ignore[arg-type]
        default_model="openrouter/auto",
        model_settings=DummyModelSettings(  # type: ignore[arg-type]
            "test/model",
            {"provider": {"sort": "latency", "allow_fallbacks": True}},
        ),
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Ping")],
        provider={"allow_fallbacks": False},
    )
    conversation = [{"role": "user", "content": "Ping"}]

    async for _ in handler.stream_conversation(
        "session-2",
        request,
        conversation,
        [],
        None,
    ):
        pass

    payload = client.payloads[0]
    assert payload["provider"]["sort"] == "latency"
    assert payload["provider"]["allow_fallbacks"] is False


@pytest.mark.anyio("asyncio")
async def test_streaming_preserves_user_image_fragments() -> None:
    client = DummyOpenRouterClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        DummyToolClient(),  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    image_url = "https://example.test/generated/a.png"
    request = ChatCompletionRequest(
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "What color is it?"},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            )
        ],
    )
    conversation = [
        {
            "role": "assistant",
            "content": [{"type": "image_url", "image_url": {"url": image_url}}],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is it?"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]

    async for _ in handler.stream_conversation(
        "session-images",
        request,
        conversation,
        [],
        None,
    ):
        pass

    payload = client.payloads[0]
    user_messages = [message for message in payload["messages"] if message.get("role") == "user"]
    assert user_messages, "Expected at least one user message in payload"
    user_message = user_messages[-1]
    assert user_message["content"][-1]["type"] == "image_url"
    assert user_message["content"][-1]["image_url"]["url"] == image_url


@pytest.mark.anyio("asyncio")
async def test_streaming_emits_metadata_event() -> None:
    repo = DummyRepository()
    client = DummyOpenRouterClientWithMetadata()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        DummyToolClient(),  # type: ignore[arg-type]
        default_model="openrouter/auto",
        model_settings=None,
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Ping")],
    )
    conversation = [{"role": "user", "content": "Ping"}]

    events = []
    async for event in handler.stream_conversation(
        "session-meta",
        request,
        conversation,
        [],
        None,
    ):
        events.append(event)

    metadata_events = [event for event in events if event.get("event") == "metadata"]
    assert metadata_events, "Expected metadata event in stream"

    payload = json.loads(metadata_events[0]["data"])
    assert payload["model"] == "test/model"
    assert payload["usage"]["total_tokens"] == 12
    assert payload["routing"]["OpenRouter-Provider"] == "test/provider"
    assert payload["meta"]["provider"]["endpoint"] == "test-endpoint"
    assert payload["generation_id"] == "gen-abc123"
    assert payload["message_id"] == 1

    assert repo.messages, "Expected message persisted"
    record = repo.messages[-1]
    assert record["role"] == "assistant"
    assert record["message_id"] == 1
    metadata = record["metadata"]
    assert metadata is not None
    assert metadata["usage"]["prompt_tokens"] == 5
    assert metadata["routing"]["OpenRouter-Provider"] == "test/provider"
    assert metadata["meta"]["provider"]["name"] == "Meta Test Provider"
    assert metadata["generation_id"] == "gen-abc123"


@pytest.mark.anyio("asyncio")
async def test_streaming_expands_contexts_after_no_result() -> None:
    client = ToolCallOpenRouterClient()
    tool_client = ExpandingToolClient()
    tool_client.results = ["No results found for that query."]
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Can you check my schedule?")],
    )
    conversation = [{"role": "user", "content": "Can you check my schedule?"}]
    plan = ToolContextPlan(stages=[["calendar"], ["tasks"]], broad_search=True)
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events = []
    async for event in handler.stream_conversation(
        "session-expand",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    assert tool_client.calls == 1
    assert tool_client.context_history[0] == ["calendar"]
    assert ["calendar", "tasks"] in tool_client.context_history
    assert len(client.payloads) == 2
    assert events[-1]["data"] == "[DONE]"

    notice_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "notice"
    ]
    assert notice_events, "Expected notice event after empty tool result"
    notice = notice_events[0]
    assert notice["reason"] == "no_results"
    assert notice["tool"] == "calendar_lookup"
    assert notice["next_contexts"] == ["tasks"]
    assert notice["confirmation_required"] is True


@pytest.mark.anyio("asyncio")
async def test_structured_tool_choice_does_not_retry_without_tools() -> None:
    client = ToolUnsupportedClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        DummyToolClient(),  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Require tool")],
        tool_choice={
            "type": "function",
            "function": {"name": "calculator_evaluate"},
        },
    )
    conversation = [{"role": "user", "content": "Require tool"}]
    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": "calculator_evaluate",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    with pytest.raises(OpenRouterError):
        async for _ in handler.stream_conversation(
            "session-tools",
            request,
            conversation,
            tools_payload,
            None,
        ):
            pass

    assert client.calls == 1


@pytest.mark.anyio("asyncio")
async def test_streaming_emits_notice_for_missing_arguments() -> None:
    client = MultiToolOpenRouterClient(
        [{"name": "calendar_lookup", "arguments": ""}],
        final_message="Please share more details.",
    )
    tool_client = ExpandingToolClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Check my calendar today")],
    )
    conversation = [{"role": "user", "content": "Check my calendar today"}]
    plan = ToolContextPlan(stages=[["calendar"], ["tasks"]], broad_search=True)
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-missing-args",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    notice_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "notice"
    ]

    assert notice_events, "Expected notice event when tool arguments are missing"
    notice = notice_events[0]
    assert notice["reason"] == "missing_arguments"
    assert notice["tool"] == "calendar_lookup"
    assert notice["next_contexts"] == []
    assert notice["confirmation_required"] is True
    assert tool_client.calls == 0
    assert len(client.payloads) == 2
    assert events[-1]["data"] == "[DONE]"


@pytest.mark.anyio("asyncio")
async def test_streaming_handles_multi_stage_notices() -> None:
    client = MultiToolOpenRouterClient(
        [
            {"name": "calendar_lookup", "arguments": {"query": "habit review"}},
            {"name": "tasks_lookup", "arguments": {"query": "habit review"}},
        ],
        final_message="Let's confirm the plan.",
    )
    tool_client = ExpandingToolClient()
    tool_client.results = [
        "No events found in that window.",
        "No matching tasks were located.",
    ]
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        DummyRepository(),  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Help me build better habits")],
    )
    conversation = [{"role": "user", "content": "Help me build better habits"}]
    plan = ToolContextPlan(
        stages=[["calendar"], ["tasks"], ["notes"]],
        broad_search=True,
    )
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-multi-stage",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    notice_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "notice"
    ]

    assert len(notice_events) == 2
    first_notice, second_notice = notice_events
    assert first_notice["reason"] == "no_results"
    assert first_notice["next_contexts"] == ["tasks"]
    assert second_notice["reason"] == "no_results"
    assert second_notice["next_contexts"] == ["notes"]
    assert tool_client.context_history[0] == ["calendar"]
    assert ["calendar", "tasks"] in tool_client.context_history
    assert ["calendar", "tasks", "notes"] in tool_client.context_history
    assert tool_client.calls == 2
    assert len(client.payloads) == 3
    assert events[-1]["data"] == "[DONE]"
