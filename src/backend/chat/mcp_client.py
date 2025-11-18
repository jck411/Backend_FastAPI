"""Async MCP client wrapper for tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, AsyncContextManager, Sequence, cast

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, ListToolsResult, Tool

logger = logging.getLogger(__name__)


class MCPToolClient:
    """Maintain a long-lived MCP session and expose tool execution helpers."""

    def __init__(
        self,
        server_module: str | None = None,
        *,
        command: Sequence[str] | None = None,
        http_url: str | None = None,
        server_id: str | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ):
        launch_methods = [server_module is not None, command is not None, http_url is not None]
        if sum(launch_methods) != 1:  # pragma: no cover - defensive
            raise ValueError("Provide exactly one of 'server_module', 'command', or 'http_url'")

        launch_command: list[str] | None = None
        launch_module: str | None = None
        if http_url is not None:
            self._http_url = http_url
        elif command is not None:
            if not command:
                raise ValueError("Command must contain at least one argument")
            launch_command = list(command)
            self._http_url = None
        else:
            launch_module = server_module
            self._http_url = None

        self._server_module = launch_module
        self._launch_command = launch_command
        self._server_id = server_id or (
            launch_module
            or (launch_command[0] if launch_command else self._http_url)
            or "mcp-server"
        )
        self._cwd = cwd
        self._env = env
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._lock = asyncio.Lock()

    @property
    def server_id(self) -> str:
        return self._server_id

    async def connect(self) -> None:
        """Spawn the MCP server and initialize the client session."""

        async with self._lock:
            if self._session is not None:
                return

            exit_stack = AsyncExitStack()
            if self._http_url is not None:
                from mcp.client.sse import sse_client

                logger.info(
                    "Connecting to HTTP MCP server at %s (id=%s)",
                    self._http_url,
                    self._server_id,
                )
                sse_manager = sse_client(self._http_url)
                read_stream, write_stream = await exit_stack.enter_async_context(
                    sse_manager
                )
            elif self._launch_command is not None:
                params = StdioServerParameters(
                    command=self._launch_command[0],
                    args=self._launch_command[1:],
                    cwd=str(self._cwd) if self._cwd is not None else None,
                    env=self._env,
                )
                log_target = "command %s" % " ".join(self._launch_command)
            else:
                # Type guard: _server_module is guaranteed to be str in this branch
                if self._server_module is None:  # pragma: no cover - defensive
                    raise RuntimeError(
                        "Server module must be set when command is not provided"
                    )
                params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", self._server_module],
                    cwd=str(self._cwd) if self._cwd is not None else None,
                    env=self._env,
                )
                log_target = f"module '{self._server_module}'"

            logger.info("Starting MCP server %s (id=%s)", log_target, self._server_id)
            stdio_manager = cast(AsyncContextManager[Any], stdio_client(params))
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_manager
            )

            session = ClientSession(read_stream, write_stream)
            await exit_stack.enter_async_context(session)
            await session.initialize()

            self._exit_stack = exit_stack
            self._session = session

            await self.refresh_tools()

    async def close(self) -> None:
        """Tear down the MCP session and the underlying process."""

        async with self._lock:
            if self._exit_stack is not None:
                logger.info("Closing MCP session for server '%s'", self._server_id)
                try:
                    # Add timeout to prevent hanging on shutdown
                    await asyncio.wait_for(self._exit_stack.aclose(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "MCP session close timed out after 2s for server '%s'",
                        self._server_id,
                    )
                except Exception as exc:
                    # Catch all exceptions including anyio cancel scope errors
                    # These can occur when closing from a different async context
                    logger.warning(
                        "Error closing MCP session for server '%s': %s",
                        self._server_id,
                        exc,
                    )
                finally:
                    # Ensure cleanup happens even if aclose() fails
                    self._exit_stack = None
                    self._session = None
            self._tools = []

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools)

    async def refresh_tools(self) -> None:
        """Fetch and cache the available tools from the MCP server."""

        if self._session is None:
            raise RuntimeError("MCP session has not been initialized")

        tools: list[Tool] = []
        cursor: str | None = None

        while True:
            result: ListToolsResult = await self._session.list_tools(cursor=cursor)
            tools.extend(result.tools)
            cursor = result.nextCursor
            if not cursor:
                break

        self._tools = tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> CallToolResult:
        """Execute a tool by name with optional JSON arguments."""

        if self._session is None:
            raise RuntimeError("MCP session has not been initialized")

        # Validate calendar_create_task calls for common mistakes
        if name == "calendar_create_task" and arguments:
            title = str(arguments.get("title", "")).lower()
            notes = str(arguments.get("notes", "")).lower()
            has_due = arguments.get("due") is not None

            # Check if the title or notes contain scheduling keywords
            scheduling_keywords = [
                "today",
                "tomorrow",
                "schedule",
                "due",
                "deadline",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "next week",
                "this week",
            ]

            has_scheduling_keyword = any(
                keyword in title or keyword in notes for keyword in scheduling_keywords
            )

            if has_scheduling_keyword and not has_due:
                logger.warning(
                    "Creating task with scheduling keywords but missing 'due' parameter. "
                    "Task will be created unscheduled. Title: %s, Notes: %s",
                    arguments.get("title"),
                    arguments.get("notes"),
                )

        logger.debug("Invoking tool '%s' with args=%s", name, arguments)
        return await self._session.call_tool(name, arguments or {})

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """Return tools formatted for OpenAI/OpenRouter tool definitions."""

        formatted: list[dict[str, Any]] = []
        for tool in self._tools:
            description = tool.description or tool.title or ""
            entry: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": description,
                    "parameters": tool.inputSchema
                    or {"type": "object", "properties": {}},
                },
            }
            formatted.append(entry)
        return formatted

    @staticmethod
    def format_tool_result(result: CallToolResult) -> str:
        """Convert an MCP tool result into a plain-text string."""

        texts: list[str] = []
        for item in result.content:
            data = item.model_dump()
            if item.type == "text":
                value = data.get("text")
                if isinstance(value, str):
                    texts.append(value)
            else:
                texts.append(json.dumps(data))
        if not texts:
            if result.structuredContent:
                texts.append(json.dumps(result.structuredContent))
        return "\n".join(texts)


__all__ = ["MCPToolClient"]
