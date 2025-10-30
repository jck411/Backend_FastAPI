"""Integration tests for the chat orchestrator planner wiring."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from src.backend.chat.orchestrator import ChatOrchestrator
from src.backend.config import Settings
from src.backend.schemas.chat import ChatCompletionRequest, ChatMessage


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class StubRepository:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.sessions: set[str] = set()
        self.messages: list[dict[str, Any]] = []

    async def initialize(self) -> None:  # pragma: no cover - trivial stub
        return

    async def session_exists(self, session_id: str) -> bool:
        return session_id in self.sessions

    async def ensure_session(self, session_id: str) -> None:
        self.sessions.add(session_id)

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
        record = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_call_id": tool_call_id,
            "metadata": metadata,
            "client_message_id": client_message_id,
            "parent_client_message_id": parent_client_message_id,
        }
        self.messages.append(record)
        return len(self.messages)

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self.messages if entry["session_id"] == session_id]

    async def mark_attachments_used(
        self, session_id: str, attachment_ids: list[str]
    ) -> None:
        return

    async def get_attachments_by_ids(
        self, attachment_ids: list[str]
    ) -> dict[str, Any]:
        return {}

    async def update_attachment_signed_url(self, attachment_id: str, **_: Any) -> None:
        return

    async def clear_session(self, session_id: str) -> None:
        self.messages = [m for m in self.messages if m["session_id"] != session_id]
        self.sessions.discard(session_id)

    async def delete_message(self, session_id: str, client_message_id: str) -> int:
        return 0

    async def close(self) -> None:
        return

    async def get_session_metadata(self, session_id: str) -> dict[str, Any]:
        return {}


class StubAggregator:
    last_instance: ClassVar["StubAggregator | None"] = None
    digest_entries_by_context: ClassVar[dict[str, list[str]]] = {
        "calendar": ["calendar_lookup"],
    }
    tool_spec_order: ClassVar[list[str]] = ["calendar_lookup", "global_tool"]
    tool_spec_map: ClassVar[dict[str, dict[str, Any]]] = {
        "calendar_lookup": {
            "type": "function",
            "function": {
                "name": "calendar_lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "global_tool": {
            "type": "function",
            "function": {
                "name": "global_tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.context_requests: list[list[str]] = []
        self.digest_requests: list[tuple[list[str] | None, int, bool]] = []
        self.ranked_requests: list[list[str]] = []
        self.all_tools_requests = 0
        self.tools = [object() for _ in self.tool_spec_order]
        StubAggregator.last_instance = self

    async def apply_configs(self, configs: list[Any]) -> None:
        return

    async def connect(self) -> None:
        return

    async def close(self) -> None:  # pragma: no cover - trivial stub
        return

    def get_openai_tools(self) -> list[dict[str, Any]]:
        self.context_requests.append(["__all__"])
        self.all_tools_requests += 1
        specs: list[dict[str, Any]] = []
        for name in self.tool_spec_order:
            spec = self.tool_spec_map.get(name)
            if spec is None:
                continue
            specs.append(json.loads(json.dumps(spec)))
        return specs

    def get_openai_tools_for_contexts(
        self, contexts: list[str]
    ) -> list[dict[str, Any]]:
        return self.get_openai_tools_by_qualified_names(contexts)

    def get_openai_tools_by_qualified_names(
        self, names: list[str]
    ) -> list[dict[str, Any]]:
        filtered: list[str] = []
        for name in names:
            if isinstance(name, str) and name:
                filtered.append(name)
        self.ranked_requests.append(filtered)
        specs: list[dict[str, Any]] = []
        for name in filtered:
            spec = self.tool_spec_map.get(name)
            if spec is None:
                continue
            specs.append(json.loads(json.dumps(spec)))
        return specs

    def get_capability_digest(
        self,
        contexts: list[str] | None = None,
        *,
        limit: int = 5,
        include_global: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        snapshot = list(contexts) if contexts is not None else None
        self.digest_requests.append((snapshot, limit, include_global))
        if snapshot is not None:
            self.context_requests.append(snapshot)
            requested = snapshot
        else:
            requested = sorted(self.digest_entries_by_context)
        digest: dict[str, list[dict[str, Any]]] = {}
        for context in requested:
            entries = self.digest_entries_by_context.get(context) or []
            if not entries:
                continue
            subset = entries if limit <= 0 else entries[:limit]
            digest[context] = [
                {
                    "name": name,
                    "description": None,
                    "parameters": {"type": "object", "properties": {}},
                    "server": "stub",
                    "score": 1.0,
                    "contexts": [context],
                }
                for name in subset
            ]
        if include_global:
            digest.setdefault("__all__", [])
        return digest

    async def refresh(self) -> None:
        return

    def describe_servers(self) -> list[dict[str, Any]]:
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        raise AssertionError("Tools should not be executed in this stub")

    def format_tool_result(self, result: Any) -> str:
        return ""


class StubStreamingHandler:
    last_instance: ClassVar["StubStreamingHandler | None"] = None

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        StubStreamingHandler.last_instance = self
        self.last_plan = None
        self.last_tools_payload = None

    def set_attachment_service(self, service: Any) -> None:  # pragma: no cover
        self.attachment_service = service

    async def stream_conversation(
        self,
        session_id: str,
        request: ChatCompletionRequest,
        conversation: list[dict[str, Any]],
        tools_payload: list[dict[str, Any]],
        assistant_parent_message_id: str | None,
        tool_context_plan: Any = None,
    ):
        self.last_plan = tool_context_plan
        self.last_tools_payload = tools_payload
        yield {"event": "message", "data": "[DONE]"}


@dataclass
class StubModelSettings:
    async def get_system_prompt(self) -> str | None:
        return None

    async def get_openrouter_overrides(self) -> tuple[str, dict[str, Any]]:
        return "openrouter/auto", {}

    async def sanitize_payload_for_model(
        self, model: str, payload: dict[str, Any], *, client: Any | None = None
    ) -> None:
        return None

    async def model_supports_tools(self, client: Any | None = None) -> bool:
        return True


class StubMCPSettings:
    async def get_configs(self) -> list[dict[str, Any]]:
        return []


class StubOpenRouterClient:
    def __init__(self, *_: Any, **__: Any) -> None:
        return

    async def aclose(self) -> None:  # pragma: no cover - trivial stub
        return


@pytest.mark.anyio("asyncio")
async def test_orchestrator_invokes_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    StubAggregator.digest_entries_by_context = {"calendar": ["calendar_lookup"]}
    StubAggregator.tool_spec_order = ["calendar_lookup", "global_tool"]
    StubAggregator.tool_spec_map = {
        "calendar_lookup": {
            "type": "function",
            "function": {
                "name": "calendar_lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "global_tool": {
            "type": "function",
            "function": {
                "name": "global_tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }

    monkeypatch.setattr(
        "src.backend.chat.orchestrator.ChatRepository", StubRepository
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.MCPToolAggregator", StubAggregator
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.StreamingHandler", StubStreamingHandler
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.OpenRouterClient", StubOpenRouterClient
    )

    settings = Settings(openrouter_api_key="dummy-key")
    orchestrator = ChatOrchestrator(settings, StubModelSettings(), StubMCPSettings())

    await orchestrator.initialize()

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my schedule today?")]
    )

    events = []
    async for event in orchestrator.process_stream(request):
        events.append(event)

    assert events and events[-1]["data"] == "[DONE]"

    aggregator = StubAggregator.last_instance
    assert aggregator is not None
    assert len(aggregator.digest_requests) >= 2
    assert aggregator.digest_requests[1][0] == ["calendar"]
    assert aggregator.ranked_requests[0] == ["calendar_lookup"]

    handler = StubStreamingHandler.last_instance
    assert handler is not None
    assert handler.last_plan is not None
    assert handler.last_plan.contexts_for_attempt(0) == ["calendar"]
    assert handler.last_tools_payload is not None
    assert [
        entry["function"]["name"] for entry in handler.last_tools_payload
    ] == ["calendar_lookup"]


@pytest.mark.anyio("asyncio")
async def test_orchestrator_limits_ranked_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [f"calendar_tool_{index}" for index in range(1, 8)]
    StubAggregator.digest_entries_by_context = {"calendar": names}
    StubAggregator.tool_spec_order = names + ["global_tool"]
    StubAggregator.tool_spec_map = {
        name: {
            "type": "function",
            "function": {
                "name": name,
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    }
    StubAggregator.tool_spec_map["global_tool"] = {
        "type": "function",
        "function": {
            "name": "global_tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }

    monkeypatch.setattr(
        "src.backend.chat.orchestrator.ChatRepository", StubRepository
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.MCPToolAggregator", StubAggregator
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.StreamingHandler", StubStreamingHandler
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.OpenRouterClient", StubOpenRouterClient
    )

    settings = Settings(openrouter_api_key="dummy-key")
    orchestrator = ChatOrchestrator(settings, StubModelSettings(), StubMCPSettings())

    await orchestrator.initialize()

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my schedule today?")]
    )

    async for _ in orchestrator.process_stream(request):
        pass

    aggregator = StubAggregator.last_instance
    assert aggregator is not None
    assert len(aggregator.digest_requests) >= 2
    _, limit, include_global = aggregator.digest_requests[1]
    assert include_global is False
    expected_names = names[:limit]
    assert aggregator.ranked_requests[0] == expected_names
    assert aggregator.all_tools_requests == 0

    handler = StubStreamingHandler.last_instance
    assert handler is not None
    payload_names = [
        entry["function"]["name"] for entry in (handler.last_tools_payload or [])
    ]
    assert payload_names == expected_names


@pytest.mark.anyio("asyncio")
async def test_orchestrator_falls_back_when_digest_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    StubAggregator.digest_entries_by_context = {"calendar": []}
    StubAggregator.tool_spec_order = ["calendar_lookup", "global_tool"]
    StubAggregator.tool_spec_map = {
        "calendar_lookup": {
            "type": "function",
            "function": {
                "name": "calendar_lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "global_tool": {
            "type": "function",
            "function": {
                "name": "global_tool",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }

    monkeypatch.setattr(
        "src.backend.chat.orchestrator.ChatRepository", StubRepository
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.MCPToolAggregator", StubAggregator
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.StreamingHandler", StubStreamingHandler
    )
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.OpenRouterClient", StubOpenRouterClient
    )

    settings = Settings(openrouter_api_key="dummy-key")
    orchestrator = ChatOrchestrator(settings, StubModelSettings(), StubMCPSettings())

    await orchestrator.initialize()

    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="What's on my schedule today?")]
    )

    async for _ in orchestrator.process_stream(request):
        pass

    aggregator = StubAggregator.last_instance
    assert aggregator is not None
    assert aggregator.all_tools_requests == 1
    handler = StubStreamingHandler.last_instance
    assert handler is not None
    payload_names = [
        entry["function"]["name"] for entry in (handler.last_tools_payload or [])
    ]
    assert payload_names == ["calendar_lookup", "global_tool"]
