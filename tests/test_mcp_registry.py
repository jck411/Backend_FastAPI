"""Tests for MCP server configuration loading and aggregation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult, Tool

from backend.chat.mcp_registry import (
    MCPServerConfig,
    MCPToolAggregator,
    load_server_configs,
)
from backend.repository import ChatRepository

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def build_tool_definition(name: str, description: str) -> tuple[Tool, dict[str, Any]]:
    tool = Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": {}},
    )
    spec = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }
    return tool, spec


def make_fake_client_factory(
    tool_map: dict[str, list[tuple[Tool, dict[str, Any]]]],
    created: dict[str, Any],
):
    class FakeClient:
        def __init__(
            self,
            server_module: str | None,
            *,
            command: list[str] | None = None,
            server_id: str | None = None,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
        ) -> None:
            if server_id is None:
                raise AssertionError("server_id must be provided")
            definitions = tool_map.get(server_id, [])
            self._tools = [tool for tool, _ in definitions]
            self._specs = [spec for _, spec in definitions]
            self._calls: list[tuple[str, dict[str, Any]]] = []
            self._closed = False
            self.server_id = server_id
            created[server_id] = self

        async def connect(self) -> None:  # pragma: no cover - trivial stub
            return None

        async def refresh_tools(self) -> None:  # pragma: no cover - trivial stub
            return None

        def get_openai_tools(self) -> list[dict[str, Any]]:
            return [json.loads(json.dumps(spec)) for spec in self._specs]

        @property
        def tools(self) -> list[Tool]:
            return list(self._tools)

        async def call_tool(
            self,
            name: str,
            arguments: dict[str, Any] | None = None,
        ) -> CallToolResult:
            record = (name, arguments or {})
            self._calls.append(record)
            return CallToolResult(
                content=[],
                structuredContent={
                    "server": self.server_id,
                    "tool": name,
                    "arguments": arguments or {},
                },
                isError=False,
            )

        async def close(self) -> None:
            self._closed = True

        @property
        def calls(self) -> list[tuple[str, dict[str, Any]]]:
            return list(self._calls)

        @property
        def closed(self) -> bool:
            return self._closed

    return FakeClient


def build_notion_export(**overrides: Any) -> dict[str, Any]:
    server = {
        "id": "custom-notion",
        "command": [
            "uv",
            "run",
            "backend.mcp_servers.notion_server",
        ],
        "env": {"NOTION_TOKEN": "${NOTION_TOKEN}"},
        "tool_prefix": "custom-notion",
        "enabled": True,
    }
    server.update(overrides)
    return {"servers": [server]}


def test_load_server_configs_uses_fallback(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    fallback = [{"id": "local", "module": "backend.mcp_servers.calculator_server"}]

    configs = load_server_configs(path, fallback=fallback)

    assert len(configs) == 1
    assert configs[0].id == "local"
    assert configs[0].module == "backend.mcp_servers.calculator_server"


def test_load_server_configs_overrides_fallback(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "id": "local",
                        "module": "custom.server",
                        "enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    fallback = [{"id": "local", "module": "backend.mcp_servers.calculator_server"}]
    configs = load_server_configs(path, fallback=fallback)

    assert len(configs) == 1
    assert configs[0].module == "custom.server"
    assert configs[0].enabled is False


def test_load_server_configs_prefers_notion_export(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    path.write_text(json.dumps(build_notion_export()), encoding="utf-8")

    fallback = [
        {
            "id": "custom-notion",
            "module": "backend.mcp_servers.notion_server",
        }
    ]

    configs = load_server_configs(path, fallback=fallback)

    assert len(configs) == 1
    config = configs[0]
    assert config.id == "custom-notion"
    assert config.command == [
        "uv",
        "run",
        "backend.mcp_servers.notion_server",
    ]
    assert config.module is None
    assert config.tool_prefix == "custom-notion"
    assert config.env == {"NOTION_TOKEN": "${NOTION_TOKEN}"}


async def test_aggregator_preserves_unique_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_map = {
        "server_a": [build_tool_definition("alpha", "Alpha tool")],
        "server_b": [build_tool_definition("beta", "Beta tool")],
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        MCPServerConfig(id="server_a", module="pkg.alpha"),
        MCPServerConfig(id="server_b", module="pkg.beta"),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    tool_names = {entry["function"]["name"] for entry in aggregator.get_openai_tools()}
    assert tool_names == {"alpha", "beta"}

    result = await aggregator.call_tool("alpha", {"value": 1})
    assert result.structuredContent is not None
    assert result.structuredContent["server"] == "server_a"
    assert created["server_a"].calls == [("alpha", {"value": 1})]

    await aggregator.close()
    assert created["server_a"].closed is True
    assert created["server_b"].closed is True


async def test_aggregator_prefixes_duplicate_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_map = {
        "server_a": [build_tool_definition("shared", "Primary shared tool")],
        "server_b": [build_tool_definition("shared", "Secondary shared tool")],
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        MCPServerConfig(id="server_a", module="pkg.alpha"),
        MCPServerConfig(id="server_b", module="pkg.beta"),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    tool_names = {entry["function"]["name"] for entry in aggregator.get_openai_tools()}
    assert tool_names == {"server_a__shared", "server_b__shared"}

    await aggregator.call_tool("server_b__shared", {"value": 42})
    assert created["server_b"].calls == [("shared", {"value": 42})]

    await aggregator.close()


async def test_builtin_housekeeping_server_runs_via_aggregator(tmp_path: Path) -> None:
    import asyncio

    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "src"

    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH", "")
    new_pythonpath = os.pathsep.join(filter(None, [existing_path, str(src_dir)]))
    env["PYTHONPATH"] = new_pythonpath
    env.setdefault("OPENROUTER_API_KEY", "test-key")

    db_path = tmp_path / "chat.db"
    env["CHAT_DATABASE_PATH"] = str(db_path)

    repository = ChatRepository(db_path)
    await repository.initialize()
    await repository.ensure_session("session-test")
    await repository.add_message("session-test", role="user", content="hello world")
    await repository.add_message(
        "session-test", role="assistant", content="Hello back!"
    )
    await repository.close()

    config = MCPServerConfig(
        id="housekeeping",
        module="backend.mcp_servers.housekeeping_server",
        env={
            "PYTHONPATH": new_pythonpath,
            "OPENROUTER_API_KEY": env["OPENROUTER_API_KEY"],
            "CHAT_DATABASE_PATH": str(db_path),
        },
    )

    aggregator = MCPToolAggregator(
        [config],
        base_env=env,
        default_cwd=project_root,
    )

    try:
        # Add timeout for the entire test to prevent hanging
        async def run_test():
            await aggregator.connect()
            tool_names = {
                entry["function"]["name"] for entry in aggregator.get_openai_tools()
            }
            assert {"test_echo", "current_time", "chat_history"}.issubset(tool_names)

            result = await aggregator.call_tool(
                "test_echo",
                {"message": "ping", "uppercase": True},
            )
            formatted = aggregator.format_tool_result(result)
            assert "PING" in formatted

            clock = await aggregator.call_tool("current_time", {"format": "unix"})
            clock_payload = (
                clock.structuredContent if clock.structuredContent is not None else {}
            )
            value = clock_payload.get("value")
            assert clock_payload.get("format") == "unix"
            assert isinstance(value, str) and value.isdigit()
            assert clock_payload.get("utc_unix") == value
            assert clock_payload.get("utc_unix_precise")
            assert clock_payload.get("eastern_iso")
            assert clock_payload.get("eastern_abbreviation")
            assert clock_payload.get("timezone") == "America/New_York"

            history = await aggregator.call_tool(
                "chat_history",
                {"session_id": "session-test", "limit": 5, "newest_first": False},
            )
            history_payload = (
                history.structuredContent
                if history.structuredContent is not None
                else {}
            )
            assert history_payload.get("session_id") == "session-test"
            messages = history_payload.get("messages") or []
            assert messages, "expected chat_history to return at least one message"
            assert any(
                "hello world" in (item.get("content") or "") for item in messages
            )
            summary = history_payload.get("summary") or ""
            assert "hello world" in summary

        # Run with a 10-second timeout
        await asyncio.wait_for(run_test(), timeout=10.0)
    finally:
        # Ensure cleanup happens with timeout
        try:
            await asyncio.wait_for(aggregator.close(), timeout=5.0)
        except asyncio.TimeoutError:
            pass  # Log already issued in close() method


async def test_notion_export_tools_are_prefixed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export_path = tmp_path / "servers.json"
    export_path.write_text(json.dumps(build_notion_export()), encoding="utf-8")

    fallback = [
        {
            "id": "custom-notion",
            "module": "backend.mcp_servers.notion_server",
        }
    ]

    configs = load_server_configs(export_path, fallback=fallback)

    tool_map = {
        "custom-notion": [
            build_tool_definition("notion_search", "Search Notion"),
            build_tool_definition("notion_create_page", "Create Notion page"),
        ]
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        tool_names = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert tool_names == {
            "custom-notion__notion_search",
            "custom-notion__notion_create_page",
        }

        await aggregator.call_tool(
            "custom-notion__notion_search", {"query": "meeting notes"}
        )
        assert created["custom-notion"].calls == [
            ("notion_search", {"query": "meeting notes"})
        ]
    finally:
        await aggregator.close()
