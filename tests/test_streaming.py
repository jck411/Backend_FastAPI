"""Tests for streaming handler functionality."""

import json
from typing import Any

import pytest

from src.backend.chat.streaming import (
    StreamingHandler,
    _finalize_tool_calls,
    _merge_tool_calls,
)
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
        assert (
            call["function"]["arguments"]
            == '{"operation": "add", "a": 2, "b": 3}'
        )
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
        assert (
            accumulator[0]["function"]["name"] == "calculator_evaluate"
        )


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
                    "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
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
    ) -> int:
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
        return self._counter


class DummyToolClient:
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:  # pragma: no cover
        raise AssertionError("call_tool should not be invoked in these tests")

    def format_tool_result(self, result: Any) -> str:  # pragma: no cover
        return ""


class DummyModelSettings:
    def __init__(self, model: str, overrides: dict[str, Any]) -> None:
        self._model = model
        self._overrides = overrides

    async def get_openrouter_overrides(self) -> tuple[str, dict[str, Any]]:
        return self._model, self._overrides


@pytest.mark.anyio("asyncio")
async def test_streaming_applies_provider_sort_from_settings() -> None:
    client = DummyOpenRouterClient()
    handler = StreamingHandler(
        client,
        DummyRepository(),
        DummyToolClient(),
        default_model="openrouter/auto",
        model_settings=DummyModelSettings(
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
        client,
        DummyRepository(),
        DummyToolClient(),
        default_model="openrouter/auto",
        model_settings=DummyModelSettings(
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
async def test_streaming_emits_metadata_event() -> None:
    repo = DummyRepository()
    client = DummyOpenRouterClientWithMetadata()
    handler = StreamingHandler(
        client,
        repo,
        DummyToolClient(),
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
async def test_structured_tool_choice_does_not_retry_without_tools() -> None:
    client = ToolUnsupportedClient()
    handler = StreamingHandler(
        client,
        DummyRepository(),
        DummyToolClient(),
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
