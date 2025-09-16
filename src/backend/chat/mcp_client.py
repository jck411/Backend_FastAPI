"""Async MCP client wrapper for tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, ListToolsResult, Tool

logger = logging.getLogger(__name__)


class MCPToolClient:
    """Maintain a long-lived MCP session and expose tool execution helpers."""

    def __init__(
        self,
        server_module: str,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self._server_module = server_module
        self._cwd = cwd
        self._env = env
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[Tool] = []
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Spawn the MCP server and initialize the client session."""

        async with self._lock:
            if self._session is not None:
                return

            exit_stack = AsyncExitStack()
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", self._server_module],
                cwd=str(self._cwd) if self._cwd is not None else None,
                env=self._env,
            )

            logger.info("Starting MCP server for module '%s'", self._server_module)
            read_stream, write_stream = await exit_stack.enter_async_context(stdio_client(params))

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
                logger.info("Closing MCP session")
                await self._exit_stack.aclose()
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

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
        """Execute a tool by name with optional JSON arguments."""

        if self._session is None:
            raise RuntimeError("MCP session has not been initialized")

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
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
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
