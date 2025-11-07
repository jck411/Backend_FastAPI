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
from src.backend.chat.tool_context_planner import ToolCandidate, ToolContextPlan
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
        self.events: list[dict[str, Any]] = []

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

    async def add_event(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> None:
        self.events.append(
            {
                "session_id": session_id,
                "kind": kind,
                "payload": dict(payload),
                "request_id": request_id,
            }
        )


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
        self.last_rationale: str | None = None

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        if self.call_index == 0:
            self.call_index += 1
            rationale = (
                "Rationale 1: I'll inspect your calendar to find the details you're"
                " asking about."
            )
            self.last_rationale = rationale
            initial_chunk = {
                "id": "gen-tool-1",
                "choices": [
                    {
                        "delta": {
                            "content": rationale,
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
    def __init__(
        self,
        tool_calls: list[dict[str, Any]],
        final_message: str,
        *,
        include_rationale: bool = True,
    ) -> None:
        super().__init__()
        self.tool_calls = tool_calls
        self.final_message = final_message
        self.call_index = 0
        self.include_rationale = include_rationale
        self.rationales: list[str] = []

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        if self.call_index < len(self.tool_calls):
            call = self.tool_calls[self.call_index]
            self.call_index += 1
            rationale_index = self.call_index
            arguments = call.get("arguments", {})
            if isinstance(arguments, dict):
                arguments_payload = json.dumps(arguments)
            else:
                arguments_payload = str(arguments)
            rationale_text: str | None = None
            if self.include_rationale:
                raw_rationale = call.get("rationale")
                if isinstance(raw_rationale, str) and raw_rationale.strip():
                    rationale_text = raw_rationale.strip()
                    if not rationale_text.lower().startswith("rationale"):
                        rationale_text = (
                            f"Rationale {rationale_index}: {rationale_text}"
                        )
                else:
                    tool_name = call.get("name", "calendar_lookup")
                    rationale_text = (
                        f"Rationale {rationale_index}: I'll run {tool_name} to gather"
                        " information for your request."
                    )
                self.rationales.append(rationale_text)
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
            if rationale_text:
                chunk["choices"][0]["delta"]["content"] = rationale_text
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


class EmbeddedRationaleOpenRouterClient(DummyOpenRouterClient):
    def __init__(self) -> None:
        super().__init__()
        self.phase = 0

    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        if self.phase == 0:
            self.phase += 1
            chunk = {
                "id": "gen-embedded-1",
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "rationale": (
                                        "Checking today's calendar for events. "
                                        "If there's anything interesting I'll report back."
                                    ),
                                    "function": {
                                        "name": "calendar_lookup",
                                        "arguments": json.dumps({"query": "today"}),
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

        self.phase += 1
        final_chunk = {
            "id": "gen-embedded-final",
            "choices": [
                {
                    "delta": {"content": "Your calendar is all set."},
                    "finish_reason": "stop",
                }
            ],
        }
        yield {"data": json.dumps(final_chunk)}
        yield {"data": "[DONE]"}


class MissingSecondRationaleClient(DummyOpenRouterClient):
    async def stream_chat_raw(self, payload: dict[str, Any]):
        self.payloads.append(payload)
        chunk = {
            "id": "gen-missing-rationale",
            "choices": [
                {
                    "delta": {
                        "content": "Rationale 1: Checking the calendar availability.",
                        "tool_calls": [
                            {
                                "id": "call_0",
                                "type": "function",
                                "function": {
                                    "name": "calendar_lookup",
                                    "arguments": json.dumps(
                                        {"query": "team standup schedule"}
                                    ),
                                },
                            },
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "tasks_lookup",
                                    "arguments": json.dumps(
                                        {"query": "team standup follow-ups"}
                                    ),
                                },
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        yield {"data": json.dumps(chunk)}
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
async def test_streaming_injects_tool_digest_once_per_turn() -> None:
    client = ToolCallOpenRouterClient()
    repo = DummyRepository()
    tool_client = ExpandingToolClient()
    tool_client.results = ["Meeting scheduled."]
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    plan = ToolContextPlan(
        stages=[["calendar"]],
        broad_search=False,
        ranked_contexts=["calendar"],
        candidate_tools={
            "calendar": [
                ToolCandidate(
                    name="context_calendar_tool",
                    description="Check calendar availability",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "window": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                    server="calendar",
                )
            ]
        },
    )
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's next on my agenda?")],
    )
    conversation = [{"role": "user", "content": "What's next on my agenda?"}]

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-digest",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    assert client.payloads, "Expected at least one payload"
    for payload in client.payloads:
        tool_names = [
            function.get("name")
            for spec in payload.get("tools", [])
            if isinstance(spec, dict)
            and isinstance(function := spec.get("function"), dict)
            and isinstance(function.get("name"), str)
        ]
        assert tool_names, "Expected filtered tools in payload"
        digest_messages = [
            message
            for message in payload.get("messages", [])
            if isinstance(message, dict)
            and message.get("role") == "system"
            and isinstance(message.get("content"), str)
            and message["content"].startswith("Tool digest")
        ]
        assert len(digest_messages) == 1, "Digest should be emitted exactly once"
        digest_text = digest_messages[0]["content"]
        parsed_names: list[str] = []
        for line in digest_text.splitlines():
            if not line.startswith("- "):
                continue
            remainder = line[2:]
            name = remainder.split(" — ", 1)[0].split(" (", 1)[0].strip()
            if name:
                parsed_names.append(name)
        assert parsed_names == tool_names
        assert "Check calendar availability" in digest_text
        assert "query*" in digest_text

    persisted_system = [msg for msg in repo.messages if msg["role"] == "system"]
    assert not persisted_system, "Digest messages should remain transient"
    assert events[-1]["data"] == "[DONE]"


@pytest.mark.anyio("asyncio")
async def test_streaming_emits_context_plan_notice() -> None:
    client = DummyOpenRouterClient()
    repo = DummyRepository()
    tool_client = DummyToolClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    plan = ToolContextPlan(
        stages=[["calendar"], ["tasks"]],
        broad_search=False,
        ranked_contexts=["calendar", "tasks"],
        intent="Review upcoming events",
    )
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my calendar?")],
    )
    conversation = [{"role": "user", "content": "What's on my calendar?"}]

    plan_notices: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-plan-notice",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        if event.get("event") != "notice" or not event.get("data"):
            continue
        payload = json.loads(event["data"])
        if payload.get("type") == "tool_plan_status":
            plan_notices.append(payload)

    assert plan_notices, "Expected plan status notice"
    notice = plan_notices[0]
    assert notice["used_fallback"] is False
    assert notice["contexts"] == ["calendar", "tasks"]
    assert notice["display_contexts"][0] == "Calendar"
    assert notice["message"].startswith("*") and notice["message"].endswith("*")


@pytest.mark.anyio("asyncio")
async def test_streaming_emits_fallback_plan_notice() -> None:
    client = DummyOpenRouterClient()
    repo = DummyRepository()
    tool_client = DummyToolClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    plan = ToolContextPlan(
        stages=[],
        broad_search=True,
        intent="General assistance",
        used_fallback=True,
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Hello")],
    )
    conversation = [{"role": "user", "content": "Hello"}]

    plan_notices: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-fallback-notice",
        request,
        conversation,
        [],
        None,
        plan,
    ):
        if event.get("event") != "notice" or not event.get("data"):
            continue
        payload = json.loads(event["data"])
        if payload.get("type") == "tool_plan_status":
            plan_notices.append(payload)

    assert plan_notices, "Expected fallback plan notice"
    notice = plan_notices[0]
    assert notice["used_fallback"] is True
    assert notice["contexts"] == []
    assert "Fallback tool plan active" in notice["message"]
    assert notice["message"].startswith("*") and notice["message"].endswith("*")


@pytest.mark.anyio("asyncio")
async def test_streaming_blocks_tools_without_privacy_consent() -> None:
    client = ToolCallOpenRouterClient()
    repo = DummyRepository()
    tool_client = ExpandingToolClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    plan = ToolContextPlan(
        stages=[["calendar"]],
        ranked_contexts=["calendar"],
        candidate_tools={
            "calendar": [
                ToolCandidate(
                    name="context_calendar_tool",
                    description="Check calendar availability",
                    parameters={"type": "object", "properties": {}},
                    server="calendar",
                )
            ]
        },
        privacy_note="Running calendar tools may read your private events.",
    )
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Find my next meeting.")],
    )
    conversation = [{"role": "user", "content": "Find my next meeting."}]

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-privacy-required",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    assert events[-1]["data"] == "[DONE]"
    assert client.payloads, "Expected request payloads to be sent"
    for payload in client.payloads:
        assert "tools" not in payload

    notice_types = [
        json.loads(event["data"]).get("type")
        for event in events
        if event.get("event") == "notice"
    ]
    assert "privacy_consent_required" in notice_types
    assert "privacy_consent_blocked" in notice_types
    assert tool_client.calls == 0

    consent_events = [
        entry for entry in repo.events if entry["kind"] == "privacy_consent"
    ]
    statuses = {entry["payload"].get("status") for entry in consent_events}
    assert "required" in statuses
    assert "blocked" in statuses


@pytest.mark.anyio("asyncio")
async def test_streaming_resumes_after_privacy_consent_granted() -> None:
    client = ToolCallOpenRouterClient()
    repo = DummyRepository()
    tool_client = ExpandingToolClient()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    plan = ToolContextPlan(
        stages=[["calendar"]],
        ranked_contexts=["calendar"],
        privacy_note="Running calendar tools may read your private events.",
    )
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    request = ChatCompletionRequest(
        messages=[
            ChatMessage(role="user", content="Find my next meeting."),
        ],
        metadata={"privacy_consent": {"status": "granted"}},
    )
    conversation = [{"role": "user", "content": "Find my next meeting."}]

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-privacy-granted",
        request,
        conversation,
        initial_tools,
        None,
        plan,
    ):
        events.append(event)

    assert client.payloads, "Expected request payloads to be sent"
    assert any(payload.get("tools") for payload in client.payloads)
    assert tool_client.calls > 0

    notice_types = [
        json.loads(event["data"]).get("type")
        for event in events
        if event.get("event") == "notice"
    ]
    assert "privacy_consent_granted" in notice_types
    assert "privacy_consent_blocked" not in notice_types

    consent_events = [
        entry for entry in repo.events if entry["kind"] == "privacy_consent"
    ]
    statuses = {entry["payload"].get("status") for entry in consent_events}
    assert "granted" in statuses


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
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
        tool_hop_limit=1,
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

    print("tool_client.calls", tool_client.calls)
    print("tool_client.context_history", tool_client.context_history)
    print("client payload count", len(client.payloads))
    print("final event", events[-1] if events else None)
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
    rationale_events = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    followup_events = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_followup_required"
    ]
    assert rationale_events, "Expected rationale notice before tool execution"
    assert followup_events, "Expected follow-up notice after tool execution"
    rationale_message = rationale_events[0]["message"]
    assert rationale_message == client.last_rationale
    notice = followup_events[0]
    assert notice["reason"] == "no_results"
    assert notice["tool"] == "calendar_lookup"
    assert notice["next_contexts"] == ["tasks"]
    assert notice["confirmation_required"] is True
    assert notice["rationale"] == rationale_message

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    assert tool_events[0]["rationale"] == rationale_message

    metadata_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "metadata"
    ]
    tool_rationales = metadata_events[0].get("tool_rationales")
    assert tool_rationales and tool_rationales[0]["text"] == rationale_message
    assert tool_rationales[0]["index"] == 1

    assistant_messages = [
        message for message in repo.messages if message["role"] == "assistant"
    ]
    assert assistant_messages
    assistant_rationales = assistant_messages[0]["metadata"].get("tool_rationales")
    assert assistant_rationales and assistant_rationales[0]["text"] == rationale_message
    assert assistant_rationales[0]["index"] == 1
    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    assert tool_messages
    assert tool_messages[0]["metadata"]["tool_rationale"] == rationale_message
    assert tool_messages[0]["metadata"]["tool_rationale_index"] == 1


@pytest.mark.anyio("asyncio")
async def test_streaming_requests_rationale_when_missing() -> None:
    client = MultiToolOpenRouterClient(
        [{"name": "calendar_lookup", "arguments": {"query": "habit review"}}],
        final_message="We'll continue once there's a plan.",
        include_rationale=False,
    )
    tool_client = ExpandingToolClient()
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Help me review habits")],
    )
    conversation = [{"role": "user", "content": "Help me review habits"}]
    plan = ToolContextPlan(stages=[["calendar"]], broad_search=False)
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-missing-rationale",
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
    rationale_notices = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    assert rationale_notices
    generated_notice = rationale_notices[0]
    assert generated_notice["tool"] == "calendar_lookup"
    assert generated_notice["auto_generated"] is True
    missing_rationale = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_rationale_missing"
    ]
    assert not missing_rationale

    followup_events = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_followup_required"
    ]
    assert followup_events
    assert followup_events[0]["reason"] == "empty_result"
    assert followup_events[0]["rationale_auto_generated"] is True

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    finished_events = [
        event
        for event in tool_events
        if event.get("status") == "finished" and event.get("name") == "calendar_lookup"
    ]
    assert finished_events
    assert finished_events[0]["rationale_auto_generated"] is True
    assert tool_client.calls == 1

    metadata_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "metadata"
    ]
    assert metadata_events
    missing_entries = metadata_events[0].get("tool_rationales")
    assert missing_entries and missing_entries[0]["auto_generated"] is True
    assert missing_entries[0]["text"].startswith("Rationale 1:")
    assert missing_entries[0]["index"] == 1

    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    assert tool_messages
    assert tool_messages[0]["metadata"]["tool_rationale_auto_generated"] is True
    assert tool_messages[0]["metadata"]["tool_rationale"].startswith("Rationale 1:")
    assert tool_messages[0]["metadata"]["tool_rationale_index"] == 1
    assert events[-1]["data"] == "[DONE]"


@pytest.mark.anyio("asyncio")
async def test_streaming_blocks_tool_when_followup_rationale_missing() -> None:
    client = MissingSecondRationaleClient()
    tool_client = ExpandingToolClient()
    tool_client.results = ["Calendar summary ready."]
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[
            ChatMessage(role="user", content="Summarize the standup decisions"),
        ]
    )
    conversation = [
        {"role": "user", "content": "Summarize the standup decisions"},
    ]
    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": "calendar_lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tasks_lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-missing-second-rationale",
        request,
        conversation,
        tools_payload,
        None,
    ):
        events.append(event)

    notice_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "notice"
    ]
    rationale_notices = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    missing_notices = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_rationale_missing"
    ]
    assert rationale_notices
    assert any(notice.get("index") == 1 for notice in rationale_notices)
    assert missing_notices == []
    assert any(
        notice.get("auto_generated") is True and notice.get("index") == 2
        for notice in rationale_notices
    )

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    finished_tool = next(
        event
        for event in tool_events
        if event.get("call_id") == "call_0" and event.get("status") == "finished"
    )
    second_tool = next(
        event
        for event in tool_events
        if event.get("call_id") == "call_1" and event.get("status") == "finished"
    )
    assert finished_tool["rationale_index"] == 1
    assert finished_tool["rationale_auto_generated"] is False
    assert second_tool["rationale_index"] == 2
    assert second_tool["rationale_auto_generated"] is True
    assert tool_client.calls >= 2

    metadata_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "metadata"
    ]
    assert metadata_events
    tool_rationales = metadata_events[0].get("tool_rationales")
    assert tool_rationales and len(tool_rationales) == 2
    assert tool_rationales[0]["index"] == 1
    assert tool_rationales[0]["text"].startswith("Rationale 1:")
    assert tool_rationales[0]["auto_generated"] is False
    assert tool_rationales[1]["index"] == 2
    assert tool_rationales[1]["auto_generated"] is True
    assert tool_rationales[1]["text"].startswith("Rationale 2:")

    assistant_messages = [
        message for message in repo.messages if message["role"] == "assistant"
    ]
    assert assistant_messages
    assistant_rationales = assistant_messages[0]["metadata"].get("tool_rationales")
    assert assistant_rationales and len(assistant_rationales) == 2
    assert assistant_rationales[0]["index"] == 1
    assert assistant_rationales[0]["text"].startswith("Rationale 1:")
    assert assistant_rationales[1]["index"] == 2
    assert assistant_rationales[1]["auto_generated"] is True
    assert assistant_rationales[1]["text"].startswith("Rationale 2:")

    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    tool_message_map: dict[str, dict[str, Any]] = {}
    for message in tool_messages:
        call_id = message.get("tool_call_id")
        if isinstance(call_id, str) and call_id not in tool_message_map:
            tool_message_map[call_id] = message
    assert {"call_0", "call_1"}.issubset(tool_message_map)
    first_message = tool_message_map["call_0"]
    second_message = tool_message_map["call_1"]
    assert first_message["metadata"]["tool_rationale_index"] == 1
    assert first_message["metadata"]["tool_rationale"].startswith("Rationale 1:")
    assert first_message["metadata"]["tool_rationale_auto_generated"] is False
    assert second_message["metadata"]["tool_rationale_index"] == 2
    assert second_message["metadata"]["tool_rationale"].startswith("Rationale 2:")
    assert second_message["metadata"]["tool_rationale_auto_generated"] is True

@pytest.mark.anyio("asyncio")
async def test_streaming_uses_embedded_tool_rationale() -> None:
    client = EmbeddedRationaleOpenRouterClient()
    tool_client = ExpandingToolClient()
    tool_client.results = ["Calendar summary ready."]
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my calendar?")],
    )
    conversation = [{"role": "user", "content": "What's on my calendar?"}]
    plan = ToolContextPlan(stages=[["calendar"]], broad_search=False)
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-embedded-rationale",
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
    assert not any(
        notice.get("type") == "tool_rationale_missing" for notice in notice_events
    )

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    assert tool_events, "Expected tool event"
    first_tool = tool_events[0]
    assert first_tool["rationale_index"] == 1
    assert (
        first_tool["rationale"]
        == "Rationale 1: Checking today's calendar for events."
    )

    metadata_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "metadata"
    ]
    assert metadata_events, "Expected metadata event"
    stored_rationales = metadata_events[0].get("tool_rationales")
    assert stored_rationales and stored_rationales[0]["text"].startswith(
        "Rationale 1:"
    )

    assistant_messages = [
        message for message in repo.messages if message["role"] == "assistant"
    ]
    assert assistant_messages
    assistant_metadata = assistant_messages[0]["metadata"] or {}
    stored_assistant_rationales = assistant_metadata.get("tool_rationales")
    assert stored_assistant_rationales and stored_assistant_rationales[0]["text"].startswith(
        "Rationale 1:"
    )

    tool_messages = [
        message for message in repo.messages if message["role"] == "tool"
    ]
    assert tool_messages
    assert (
        tool_messages[0]["metadata"]["tool_rationale"]
        == "Rationale 1: Checking today's calendar for events."
    )
    assert events[-1]["data"] == "[DONE]"


@pytest.mark.anyio("asyncio")
async def test_streaming_generates_fallback_rationale_when_missing() -> None:
    client = MultiToolOpenRouterClient(
        [
            {
                "name": "list_calendars",
                "arguments": {"user_google_email": "jack@example.com"},
            }
        ],
        final_message="Calendar review complete.",
        include_rationale=False,
    )
    tool_client = ExpandingToolClient()
    tool_client.results = ["Calendar summary ready."]
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
        tool_client,  # type: ignore[arg-type]
        default_model="openrouter/auto",
    )

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my calendar today?")],
    )
    conversation = [{"role": "user", "content": "What's on my calendar today?"}]
    plan = ToolContextPlan(stages=[["calendar"]], broad_search=False)
    initial_tools = tool_client.get_openai_tools_for_contexts(
        plan.contexts_for_attempt(0)
    )

    events: list[dict[str, Any]] = []
    async for event in handler.stream_conversation(
        "session-fallback-rationale",
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
    tool_rationale_notices = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    assert tool_rationale_notices, "Expected auto-generated rationale notice"
    generated_notice = tool_rationale_notices[0]
    assert generated_notice["auto_generated"] is True
    assert generated_notice["message"].startswith("Rationale 1:")
    assert generated_notice["tool"] == "list_calendars"

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    assert tool_events, "Expected tool events"
    finished_tool = next(
        event for event in tool_events if event.get("status") == "finished"
    )
    assert finished_tool["rationale"].startswith("Rationale 1:")
    assert finished_tool["rationale_auto_generated"] is True
    started_tool = next(
        event for event in tool_events if event.get("status") == "started"
    )
    assert started_tool["rationale_auto_generated"] is True
    assert tool_client.calls == 1

    metadata_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "metadata"
    ]
    assert metadata_events
    tool_rationales = metadata_events[0]["tool_rationales"]
    assert tool_rationales and tool_rationales[0]["auto_generated"] is True
    assert tool_rationales[0]["text"].startswith("Rationale 1:")

    assistant_messages = [
        message for message in repo.messages if message["role"] == "assistant"
    ]
    assert assistant_messages
    assistant_rationales = assistant_messages[0]["metadata"]["tool_rationales"]
    assert assistant_rationales[0]["auto_generated"] is True
    assert assistant_rationales[0]["text"].startswith("Rationale 1:")

    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    assert tool_messages
    tool_metadata = tool_messages[0]["metadata"]
    assert tool_metadata["tool_rationale_auto_generated"] is True
    assert tool_metadata["tool_rationale"].startswith("Rationale 1:")

    assert events[-1]["data"] == "[DONE]"


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
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
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

    rationale_events = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    followup_events = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_followup_required"
    ]

    assert rationale_events, "Expected rationale notice before tool execution"
    assert followup_events, "Expected follow-up notice when tool arguments are missing"
    rationale_message = rationale_events[0]["message"]
    assert rationale_events[0]["index"] == 1
    notice = followup_events[0]
    assert notice["reason"] == "missing_arguments"
    assert notice["tool"] == "calendar_lookup"
    assert notice["next_contexts"] == []
    assert notice["confirmation_required"] is True
    assert notice["rationale"] == rationale_message
    assert tool_client.calls == 0
    assert len(client.payloads) == 2
    assert events[-1]["data"] == "[DONE]"

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    assert tool_events[0]["rationale"] == rationale_message
    assert tool_events[0]["rationale_index"] == 1

    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    assert tool_messages[0]["metadata"]["tool_rationale"] == rationale_message
    assert tool_messages[0]["metadata"]["tool_rationale_index"] == 1


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
    repo = DummyRepository()
    handler = StreamingHandler(
        client,  # type: ignore[arg-type]
        repo,  # type: ignore[arg-type]
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

    rationale_events = [
        notice for notice in notice_events if notice.get("type") == "tool_rationale"
    ]
    followup_events = [
        notice
        for notice in notice_events
        if notice.get("type") == "tool_followup_required"
    ]

    assert len(rationale_events) == 2
    assert len(followup_events) == 2
    first_notice, second_notice = followup_events
    assert first_notice["reason"] == "no_results"
    assert first_notice["next_contexts"] == ["tasks"]
    assert second_notice["reason"] == "no_results"
    assert second_notice["next_contexts"] == ["notes"]
    assert first_notice["rationale"] == rationale_events[0]["message"]
    assert second_notice["rationale"] == rationale_events[1]["message"]
    assert rationale_events[0]["index"] == 1
    assert rationale_events[1]["index"] == 2
    assert tool_client.context_history[0] == ["calendar"]
    assert ["calendar", "tasks"] in tool_client.context_history
    assert ["calendar", "tasks", "notes"] in tool_client.context_history
    assert tool_client.calls == 2
    assert len(client.payloads) == 3
    assert events[-1]["data"] == "[DONE]"

    tool_events = [
        json.loads(event["data"])
        for event in events
        if event.get("event") == "tool"
    ]
    tool_rationale_map = {
        event.get("call_id"): (
            event.get("rationale"),
            event.get("rationale_index"),
        )
        for event in tool_events
        if event.get("call_id")
    }
    expected_rationales = [
        (event["message"], event["index"]) for event in rationale_events
    ]
    for index, (expected_text, expected_index) in enumerate(
        expected_rationales, start=1
    ):
        stored = tool_rationale_map.get(f"call_{index}")
        assert stored is not None
        assert stored[0] == expected_text
        assert stored[1] == expected_index

    tool_messages = [message for message in repo.messages if message["role"] == "tool"]
    stored_rationales = {
        message["tool_call_id"]: (
            message["metadata"].get("tool_rationale"),
            message["metadata"].get("tool_rationale_index"),
        )
        for message in tool_messages
    }
    for index, (expected_text, expected_index) in enumerate(
        expected_rationales, start=1
    ):
        stored = stored_rationales.get(f"call_{index}")
        assert stored is not None
        assert stored[0] == expected_text
        assert stored[1] == expected_index
