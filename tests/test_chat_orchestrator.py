"""Integration tests for the chat orchestrator planner wiring."""

from __future__ import annotations

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.context_requests: list[list[str]] = []
        self.tools = [object()]
        StubAggregator.last_instance = self

    async def apply_configs(self, configs: list[Any]) -> None:
        return

    async def connect(self) -> None:
        return

    async def close(self) -> None:  # pragma: no cover - trivial stub
        return

    def get_openai_tools(self) -> list[dict[str, Any]]:
        self.context_requests.append(["__all__"])
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
        self, contexts: list[str]
    ) -> list[dict[str, Any]]:
        snapshot = [ctx for ctx in contexts]
        self.context_requests.append(snapshot)
        return [
            {
                "type": "function",
                "function": {
                    "name": "calendar_lookup",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

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
    assert aggregator.context_requests
    assert aggregator.context_requests[0] == ["calendar"]

    handler = StubStreamingHandler.last_instance
    assert handler is not None
    assert handler.last_plan is not None
    assert handler.last_plan.contexts_for_attempt(0) == ["calendar"]
