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
    MCPServerToolConfig,
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


DEFAULT_TEST_HTTP_PORT = 9100


def make_config(**kwargs: Any) -> MCPServerConfig:
    if "http_url" not in kwargs and "http_port" not in kwargs:
        kwargs["http_port"] = DEFAULT_TEST_HTTP_PORT
    return MCPServerConfig(**kwargs)


def make_fake_client_factory(
    tool_map: dict[str, list[tuple[Tool, dict[str, Any]]]],
    created: dict[str, Any],
):
    class FakeClient:
        def __init__(
            self,
            server_module: str | None = None,
            *,
            command: list[str] | None = None,
            http_url: str | None = None,
            http_port: int | None = None,
            server_id: str | None = None,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
            connect_only: bool = False,
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


def build_export(**overrides: Any) -> dict[str, Any]:
    server = {
        "id": "external-server",
        "command": [
            "uv",
            "run",
            "backend.mcp_servers.gmail_server",
        ],
        "http_port": DEFAULT_TEST_HTTP_PORT,
        "env": {"EXPORTED_TOKEN": "${EXPORTED_TOKEN}"},
        "tool_prefix": "external-server",
        "enabled": True,
    }
    server.update(overrides)
    return {"servers": [server]}


def test_load_server_configs_uses_fallback(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    fallback = [
        {
            "id": "local",
            "module": "backend.mcp_servers.calculator_server",
            "http_port": DEFAULT_TEST_HTTP_PORT,
        }
    ]

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
                        "http_port": DEFAULT_TEST_HTTP_PORT,
                        "enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    fallback = [
        {
            "id": "local",
            "module": "backend.mcp_servers.calculator_server",
            "http_port": DEFAULT_TEST_HTTP_PORT,
        }
    ]
    configs = load_server_configs(path, fallback=fallback)

    assert len(configs) == 1
    assert configs[0].module == "custom.server"
    assert configs[0].enabled is False


def test_load_server_configs_prefers_export(tmp_path: Path) -> None:
    path = tmp_path / "servers.json"
    path.write_text(json.dumps(build_export()), encoding="utf-8")

    fallback = [
        {
            "id": "external-server",
            "module": "backend.mcp_servers.gmail_server",
            "http_port": DEFAULT_TEST_HTTP_PORT,
        }
    ]

    configs = load_server_configs(path, fallback=fallback)

    assert len(configs) == 1
    config = configs[0]
    assert config.id == "external-server"
    assert config.command == [
        "uv",
        "run",
        "backend.mcp_servers.gmail_server",
    ]
    assert config.module is None
    assert config.tool_prefix == "external-server"
    assert config.env == {"EXPORTED_TOKEN": "${EXPORTED_TOKEN}"}


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
        make_config(id="server_a", module="pkg.alpha"),
        make_config(id="server_b", module="pkg.beta"),
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
        make_config(id="server_a", module="pkg.alpha"),
        make_config(id="server_b", module="pkg.beta"),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        tool_names = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert tool_names == {"server_a__shared", "server_b__shared"}

        await aggregator.call_tool("server_b__shared", {"value": 42})
        assert created["server_b"].calls == [("shared", {"value": 42})]
    finally:
        await aggregator.close()


async def test_aggregator_filters_tools_by_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_map = {
        "server_a": [build_tool_definition("alpha", "Alpha tool")],
        "server_b": [
            build_tool_definition("shared", "Shared calendar tool"),
            build_tool_definition("secondary", "Tasks tool"),
        ],
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(id="server_a", module="pkg.alpha", contexts=["calendar"]),
        make_config(
            id="server_b",
            module="pkg.beta",
            contexts=["tasks"],
            tool_overrides={"shared": MCPServerToolConfig(contexts=["calendar"])},
        ),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        calendar_tools = {
            entry["function"]["name"]
            for entry in aggregator.get_openai_tools_for_contexts(["calendar"])
        }
        assert calendar_tools == {"alpha", "shared"}

        task_tools = {
            entry["function"]["name"]
            for entry in aggregator.get_openai_tools_for_contexts(["tasks"])
        }
        assert task_tools == {"secondary"}

        assert aggregator.get_openai_tools_for_contexts(["unknown"]) == [], (
            "Unexpected tools returned for unknown context"
        )

        all_tools = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert {
            entry["function"]["name"]
            for entry in aggregator.get_openai_tools_for_contexts([])
        } == all_tools
    finally:
        await aggregator.close()


async def test_aggregator_returns_tools_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_map = {
        "server_a": [
            build_tool_definition("alpha", "Alpha tool"),
            build_tool_definition("beta", "Beta tool"),
            build_tool_definition("gamma", "Gamma tool"),
        ]
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(id="server_a", module="pkg.alpha", contexts=["calendar"]),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        digest = aggregator.get_capability_digest(
            ["calendar"], limit=2, include_global=False
        )
        names = [entry["name"] for entry in digest.get("calendar", [])]
        assert names == ["alpha", "beta"]

        reversed_names = list(reversed(names))
        subset = aggregator.get_openai_tools_by_qualified_names(
            reversed_names + [names[0]]
        )
        assert len(subset) == len(reversed_names)
        assert [spec["function"]["name"] for spec in subset] == reversed_names, (
            "Expected tools in requested order"
        )

        # Ensure specs are deep copied
        subset[0]["function"]["description"] = "mutated"
        refreshed = aggregator.get_openai_tools_by_qualified_names([reversed_names[0]])
        assert refreshed[0]["function"].get("description") != "mutated"
    finally:
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

    config = make_config(
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


async def test_exported_manifest_tools_are_prefixed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    export_path = tmp_path / "servers.json"
    export_path.write_text(json.dumps(build_export()), encoding="utf-8")

    fallback = [
        {
            "id": "external-server",
            "module": "backend.mcp_servers.gmail_server",
            "http_port": DEFAULT_TEST_HTTP_PORT,
        }
    ]

    configs = load_server_configs(export_path, fallback=fallback)

    tool_map = {
        "external-server": [
            build_tool_definition("gmail_create_draft", "Create Gmail draft"),
            build_tool_definition("gmail_send", "Send Gmail"),
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
            "external-server__gmail_create_draft",
            "external-server__gmail_send",
        }

        await aggregator.call_tool(
            "external-server__gmail_create_draft", {"subject": "Status"}
        )
        assert created["external-server"].calls == [
            ("gmail_create_draft", {"subject": "Status"})
        ]
    finally:
        await aggregator.close()


async def test_http_server_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that HTTP servers can be configured and connected."""
    tool_map = {
        "http-server": [
            build_tool_definition("http_tool", "HTTP-based tool"),
        ]
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(
            id="http-server",
            http_url="http://localhost:8080/mcp",
            enabled=True,
        )
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        # Verify server is connected
        assert "http-server" in aggregator.active_servers()

        # Verify tools are available
        tool_names = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert "http_tool" in tool_names

        # Test tool execution
        result = await aggregator.call_tool("http_tool", {"param": "value"})
        assert result.structuredContent is not None
        assert result.structuredContent["server"] == "http-server"
    finally:
        await aggregator.close()


async def test_http_server_with_tool_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that HTTP servers with tool_prefix properly namespace tools."""
    tool_map = {
        "http-api": [
            build_tool_definition("fetch", "Fetch data"),
            build_tool_definition("update", "Update data"),
        ]
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(
            id="http-api",
            http_url="http://api.example.com/mcp",
            tool_prefix="api",
            enabled=True,
        )
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        tool_names = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert tool_names == {"api__fetch", "api__update"}

        # Ensure calling with prefixed name routes correctly
        await aggregator.call_tool("api__fetch", {"id": "123"})
        assert created["http-api"].calls == [("fetch", {"id": "123"})]
    finally:
        await aggregator.close()


async def test_mixed_http_and_module_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test aggregator with both HTTP and module-based servers."""
    tool_map = {
        "http-remote": [
            build_tool_definition("remote_tool", "Remote HTTP tool"),
        ],
        "local-module": [
            build_tool_definition("local_tool", "Local module tool"),
        ],
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(
            id="http-remote",
            http_url="http://remote.example.com/mcp",
            enabled=True,
        ),
        make_config(
            id="local-module",
            module="backend.mcp_servers.local_server",
            enabled=True,
        ),
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        active = aggregator.active_servers()
        assert "http-remote" in active
        assert "local-module" in active

        tool_names = {
            entry["function"]["name"] for entry in aggregator.get_openai_tools()
        }
        assert tool_names == {"remote_tool", "local_tool"}

        # Test both tools can be called
        await aggregator.call_tool("remote_tool", {"data": "test"})
        await aggregator.call_tool("local_tool", {"action": "execute"})

        assert created["http-remote"].calls == [("remote_tool", {"data": "test"})]
        assert created["local-module"].calls == [("local_tool", {"action": "execute"})]
    finally:
        await aggregator.close()


async def test_http_server_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that disabled HTTP servers are not started."""
    tool_map: dict[str, list[tuple[Tool, dict[str, Any]]]] = {}
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(
            id="disabled-http",
            http_url="http://disabled.example.com/mcp",
            enabled=False,
        )
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        assert "disabled-http" not in aggregator.active_servers()
        assert len(aggregator.get_openai_tools()) == 0
    finally:
        await aggregator.close()


async def test_http_server_connection_failure_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that connection failures for HTTP servers are handled gracefully."""

    class FailingFakeClient:
        def __init__(self, http_url: str | None, **kwargs: Any) -> None:
            self.server_id = kwargs.get("server_id", "unknown")
            self._tools: list[Tool] = []

        async def connect(self) -> None:
            raise ConnectionError("Failed to connect to HTTP server")

        async def close(self) -> None:
            pass

        @property
        def tools(self) -> list[Tool]:
            return []

        def get_openai_tools(self) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", FailingFakeClient)

    configs = [
        make_config(
            id="failing-http",
            http_url="http://unreachable.example.com/mcp",
            enabled=True,
        )
    ]

    aggregator = MCPToolAggregator(configs)
    # Connection failure should not raise, just log
    await aggregator.connect()

    try:
        # Server should not be in active list
        assert "failing-http" not in aggregator.active_servers()
        assert len(aggregator.get_openai_tools()) == 0
    finally:
        await aggregator.close()


async def test_http_server_with_contexts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test HTTP servers with context filtering."""
    tool_map = {
        "http-contextual": [
            build_tool_definition("email_send", "Send email"),
            build_tool_definition("storage_upload", "Upload file"),
        ]
    }
    created: dict[str, Any] = {}
    fake_client_cls = make_fake_client_factory(tool_map, created)
    monkeypatch.setattr("backend.chat.mcp_registry.MCPToolClient", fake_client_cls)

    configs = [
        make_config(
            id="http-contextual",
            http_url="http://api.example.com/mcp",
            contexts=["email"],
            tool_overrides={
                "storage_upload": MCPServerToolConfig(contexts=["storage"])
            },
            enabled=True,
        )
    ]

    aggregator = MCPToolAggregator(configs)
    await aggregator.connect()

    try:
        email_tools = {
            entry["function"]["name"]
            for entry in aggregator.get_openai_tools_for_contexts(["email"])
        }
        assert email_tools == {"email_send"}

        storage_tools = {
            entry["function"]["name"]
            for entry in aggregator.get_openai_tools_for_contexts(["storage"])
        }
        assert storage_tools == {"storage_upload"}
    finally:
        await aggregator.close()
