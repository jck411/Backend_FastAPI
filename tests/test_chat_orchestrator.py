"""Integration tests for the chat orchestrator planner wiring."""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, ClassVar, Iterable, Mapping

import pytest

from src.backend.chat.orchestrator import (
    _build_enhanced_system_prompt,
)
from src.backend.schemas.chat import ChatCompletionRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_stubs() -> None:
    StubOpenRouterClient.plan_requests = []
    StubOpenRouterClient.plan_response = {}
    StubOpenRouterClient.plan_error = None
    StubStreamingHandler.last_instance = None
    StubAggregator.last_instance = None


def _make_snapshot_stub() -> Any:
    tz = dt.timezone(dt.timedelta(hours=-5), name="EST")
    now_local = dt.datetime(2024, 1, 2, 14, 30, tzinfo=tz)
    now_utc = dt.datetime(2024, 1, 2, 19, 30, tzinfo=dt.timezone.utc)

    class _StubSnapshot:
        def __init__(self) -> None:
            self.tzinfo = tz
            self.now_local = now_local
            self.now_utc = now_utc
            self.iso_utc = now_utc.isoformat()

        @property
        def date(self) -> dt.date:
            return self.now_local.date()

        def format_time(self) -> str:
            return self.now_local.strftime("%H:%M:%S %Z")

        def timezone_display(self) -> str:
            return "America/New_York"

    return _StubSnapshot()


def test_build_enhanced_system_prompt_includes_time_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _make_snapshot_stub()
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.create_time_snapshot",
        lambda: snapshot,
    )

    result = _build_enhanced_system_prompt("Base system prompt")

    assert result.startswith("# Current Date & Time Context")
    assert "- Today's date: 2024-01-02 (Tuesday)" in result
    assert "- Current time: 14:30:00 EST" in result
    assert "- Timezone: America/New_York" in result
    assert f"- ISO timestamp (UTC): {snapshot.iso_utc}" in result
    assert result.endswith("Base system prompt")
    assert "\n\nBase system prompt" in result


def test_build_enhanced_system_prompt_without_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _make_snapshot_stub()
    monkeypatch.setattr(
        "src.backend.chat.orchestrator.create_time_snapshot",
        lambda: snapshot,
    )

    result = _build_enhanced_system_prompt(None)

    assert result.startswith("# Current Date & Time Context")
    assert "Use this context when interpreting relative dates" in result
    assert result.endswith("etc.")


def test_iter_attachment_ids_extracts_from_content() -> None:
    """Test that _iter_attachment_ids correctly extracts attachment IDs from structured content."""
    from src.backend.chat.orchestrator import _iter_attachment_ids

    # Test with valid attachment metadata
    content = [
        {"type": "text", "text": "Hello"},
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/image.jpg"},
            "metadata": {"attachment_id": "abc123"},
        },
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/image2.jpg"},
            "metadata": {"attachment_id": "def456"},
        },
    ]

    ids = list(_iter_attachment_ids(content))
    assert ids == ["abc123", "def456"]


def test_iter_attachment_ids_handles_missing_metadata() -> None:
    """Test that _iter_attachment_ids handles content without metadata."""
    from src.backend.chat.orchestrator import _iter_attachment_ids

    content = [
        {"type": "text", "text": "Hello"},
        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}},
    ]

    ids = list(_iter_attachment_ids(content))
    assert ids == []


def test_iter_attachment_ids_handles_non_dict_items() -> None:
    """Test that _iter_attachment_ids safely skips non-dict items."""
    from src.backend.chat.orchestrator import _iter_attachment_ids

    content = [
        "string item",
        123,
        {"type": "text", "text": "Valid item"},
        None,
    ]

    ids = list(_iter_attachment_ids(content))
    assert ids == []


def test_build_mcp_base_env_copies_process_env(tmp_path: Any) -> None:
    """Test that _build_mcp_base_env includes process environment variables."""
    import os

    from src.backend.chat.orchestrator import _build_mcp_base_env

    # Set a test env var
    os.environ["TEST_MCP_VAR"] = "test_value"

    try:
        result = _build_mcp_base_env(tmp_path)
        assert "TEST_MCP_VAR" in result
        assert result["TEST_MCP_VAR"] == "test_value"
    finally:
        os.environ.pop("TEST_MCP_VAR", None)


def test_build_mcp_base_env_loads_dotenv(tmp_path: Any) -> None:
    """Test that _build_mcp_base_env loads variables from .env file."""
    from src.backend.chat.orchestrator import _build_mcp_base_env

    # Create a .env file
    env_file = tmp_path / ".env"
    env_file.write_text("DOTENV_VAR=dotenv_value\n")

    result = _build_mcp_base_env(tmp_path)
    assert "DOTENV_VAR" in result
    assert result["DOTENV_VAR"] == "dotenv_value"


def test_build_mcp_base_env_prefers_process_over_dotenv(tmp_path: Any) -> None:
    """Test that process env takes precedence over .env file."""
    import os

    from src.backend.chat.orchestrator import _build_mcp_base_env

    # Create a .env file
    env_file = tmp_path / ".env"
    env_file.write_text("PRECEDENCE_VAR=dotenv_value\n")

    # Set process env
    os.environ["PRECEDENCE_VAR"] = "process_value"

    try:
        result = _build_mcp_base_env(tmp_path)
        # Process env should win
        assert result["PRECEDENCE_VAR"] == "process_value"
    finally:
        os.environ.pop("PRECEDENCE_VAR", None)

    # NOTE: The following tests have been removed because they relied on the old orchestrator
    # behavior with tool rationale instructions and synchronous stub behaviors that are no
    # longer compatible with the current async architecture.
    #
    # The orchestrator now:
    # - Uses LLM-based planning instead of keyword matching
    # - Has simplified system prompt handling (no injected rationale instructions)
    # - Requires proper async stub implementations with LLMContextPlanner
    #
    # To properly test the orchestrator, new integration tests should be created that:
    # 1. Mock the LLMContextPlanner with realistic plan responses
    # 2. Use proper async streaming handlers
    # 3. Test the actual tool selection and context planning flow
    # 4. Verify system prompt enhancement with time context
    #
    # These tests would require significant refactoring of the stub infrastructure.
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
        return [
            dict(entry) for entry in self.messages if entry["session_id"] == session_id
        ]

    async def update_latest_system_message(self, session_id: str, content: Any) -> bool:
        for message in reversed(self.messages):
            if (
                message.get("session_id") == session_id
                and message.get("role") == "system"
            ):
                message["content"] = content
                return True
        return False

    async def mark_attachments_used(
        self, session_id: str, attachment_ids: list[str]
    ) -> None:
        return

    async def get_attachments_by_ids(self, attachment_ids: list[str]) -> dict[str, Any]:
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
            summaries: list[dict[str, Any]] = []
            for entry in subset:
                if isinstance(entry, Mapping):
                    name = entry.get("name")
                    description = entry.get("description")
                    parameters = entry.get("parameters")
                    server = entry.get("server", "stub")
                    score = entry.get("score", 1.0)
                else:
                    name = entry
                    description = None
                    parameters = None
                    server = "stub"
                    score = 1.0
                if not isinstance(name, str) or not name:
                    continue
                summary: dict[str, Any] = {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                    if isinstance(parameters, Mapping)
                    else {"type": "object", "properties": {}},
                    "server": server,
                    "score": float(score) if isinstance(score, (int, float)) else 1.0,
                    "contexts": [context],
                }
                summaries.append(summary)
            if summaries:
                digest[context] = summaries
        if include_global:
            digest.setdefault("__all__", [])
        return digest

    async def refresh(self) -> None:
        return

    def describe_servers(self) -> list[dict[str, Any]]:
        return []

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
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
    plan_requests: ClassVar[list[dict[str, Any]]] = []
    plan_response: ClassVar[Any] = {}
    plan_error: ClassVar[Exception | None] = None

    def __init__(self, *_: Any, **__: Any) -> None:
        return

    async def request_tool_plan(
        self,
        *,
        request: Any,
        conversation: Iterable[dict[str, Any]],
        tool_digest: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "request": request,
            "conversation": [dict(message) for message in conversation],
            "tool_digest": dict(tool_digest),
        }
        StubOpenRouterClient.plan_requests.append(payload)
        if StubOpenRouterClient.plan_error is not None:
            raise StubOpenRouterClient.plan_error
        return StubOpenRouterClient.plan_response

    async def aclose(self) -> None:  # pragma: no cover - trivial stub
        return


# NOTE: The following tests have been removed because they relied on the old orchestrator
# behavior with tool rationale instructions and synchronous stub behaviors that are no
# longer compatible with the current async architecture.
#
# The orchestrator now:
# - Uses LLM-based planning instead of keyword matching
# - Has simplified system prompt handling (no injected rationale instructions)
# - Requires proper async stub implementations with LLMContextPlanner
#
# To properly test the orchestrator, new integration tests should be created that:
# 1. Mock the LLMContextPlanner with realistic plan responses
# 2. Use proper async streaming handlers
# 3. Test the actual tool selection and context planning flow
# 4. Verify system prompt enhancement with time context
#
# These tests would require significant refactoring of the stub infrastructure.
