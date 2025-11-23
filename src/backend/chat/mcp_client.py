"""Async MCP client wrapper for tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, AsyncContextManager, Sequence, cast

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, ListToolsResult, Tool

logger = logging.getLogger(__name__)

# Connection timeout for HTTP/SSE MCP servers (seconds)
HTTP_CONNECTION_TIMEOUT = 30.0
# Maximum number of reconnection attempts for HTTP servers
HTTP_MAX_RECONNECT_ATTEMPTS = 3
# Delay between reconnection attempts (seconds)
HTTP_RECONNECT_DELAY = 2.0


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
        launch_methods = [
            server_module is not None,
            command is not None,
            http_url is not None,
        ]
        if sum(launch_methods) != 1:  # pragma: no cover - defensive
            raise ValueError(
                "Provide exactly one of 'server_module', 'command', or 'http_url'"
            )

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
        self._reconnect_attempts = 0
        self._last_connection_error: Exception | None = None
        self._lifecycle_task: asyncio.Task | None = None
        self._close_event: asyncio.Event | None = None
        self._ready_event: asyncio.Event | None = None

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def is_http_server(self) -> bool:
        """Check if this client connects to an HTTP/SSE server."""
        return self._http_url is not None

    @property
    def http_url(self) -> str | None:
        """Return the HTTP URL if this is an HTTP server, None otherwise."""
        return self._http_url

    async def _run_lifecycle(self) -> None:
        """Own the MCP session lifetime in a single task to avoid cross-task closures."""

        exit_stack = AsyncExitStack()
        try:
            if self._http_url is not None:
                from mcp.client.sse import sse_client

                logger.info(
                    "Connecting to HTTP MCP server at %s (id=%s)",
                    self._http_url,
                    self._server_id,
                )
                async with asyncio.timeout(HTTP_CONNECTION_TIMEOUT):
                    sse_manager = sse_client(
                        self._http_url, timeout=HTTP_CONNECTION_TIMEOUT
                    )
                    (read_stream, write_stream) = await exit_stack.enter_async_context(
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
                logger.info(
                    "Starting MCP server %s (id=%s)", log_target, self._server_id
                )
                stdio_manager = cast(AsyncContextManager[Any], stdio_client(params))
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_manager
                )
            else:
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
                logger.info(
                    "Starting MCP server %s (id=%s)", log_target, self._server_id
                )
                stdio_manager = cast(AsyncContextManager[Any], stdio_client(params))
                read_stream, write_stream = await exit_stack.enter_async_context(
                    stdio_manager
                )

            session = ClientSession(read_stream, write_stream)
            await exit_stack.enter_async_context(session)
            await session.initialize()

            async with self._lock:
                self._exit_stack = exit_stack
                self._session = session
                self._reconnect_attempts = 0
                self._last_connection_error = None

            await self.refresh_tools()

            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()

            if self._close_event is not None:
                await self._close_event.wait()
        except asyncio.TimeoutError as exc:
            async with self._lock:
                self._last_connection_error = exc
            if self._http_url is not None:
                logger.error(
                    "Timeout connecting to HTTP MCP server '%s' after %ss",
                    self._http_url,
                    HTTP_CONNECTION_TIMEOUT,
                )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        except httpx.ConnectError as exc:
            async with self._lock:
                self._last_connection_error = exc
            error_msg = str(exc).lower()
            if self._http_url is not None:
                if (
                    "name or service not known" in error_msg
                    or "nodename nor servname provided" in error_msg
                    or "getaddrinfo failed" in error_msg
                ):
                    logger.error(
                        "DNS resolution failed for HTTP MCP server '%s': %s",
                        self._http_url,
                        exc,
                    )
                elif "connection refused" in error_msg:
                    logger.error(
                        "Connection refused to HTTP MCP server '%s': %s",
                        self._http_url,
                        exc,
                    )
                else:
                    logger.error(
                        "Network error connecting to HTTP MCP server '%s': %s",
                        self._http_url,
                        exc,
                    )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        except httpx.NetworkError as exc:
            async with self._lock:
                self._last_connection_error = exc
            if self._http_url is not None:
                logger.error(
                    "Network error connecting to HTTP MCP server '%s': %s",
                    self._http_url,
                    exc,
                )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        except httpx.HTTPStatusError as exc:
            async with self._lock:
                self._last_connection_error = exc
            status_code = exc.response.status_code
            if self._http_url is not None:
                if status_code == 401:
                    logger.error(
                        "Authentication required for HTTP MCP server '%s'",
                        self._http_url,
                    )
                elif status_code == 403:
                    logger.error(
                        "Access forbidden to HTTP MCP server '%s'",
                        self._http_url,
                    )
                elif status_code == 404:
                    logger.error(
                        "HTTP MCP server endpoint not found '%s'",
                        self._http_url,
                    )
                elif status_code >= 500:
                    logger.error(
                        "HTTP MCP server error '%s': %s %s",
                        self._http_url,
                        status_code,
                        exc.response.reason_phrase,
                    )
                else:
                    logger.error(
                        "HTTP error from MCP server '%s': %s %s",
                        self._http_url,
                        status_code,
                        exc.response.reason_phrase,
                    )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        except ValueError as exc:
            async with self._lock:
                self._last_connection_error = exc
            if self._http_url is not None:
                logger.error(
                    "Invalid SSE stream format from HTTP MCP server '%s': %s",
                    self._http_url,
                    exc,
                )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        except Exception as exc:  # noqa: BLE001
            async with self._lock:
                self._last_connection_error = exc
            logger.error(
                "Unexpected error connecting to MCP server '%s': %s",
                self._http_url or self._server_id,
                exc,
            )
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
        finally:
            if self._ready_event is not None and not self._ready_event.is_set():
                self._ready_event.set()
            try:
                await asyncio.wait_for(exit_stack.aclose(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "MCP session close timed out after 2s for server '%s'",
                    self._server_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error closing MCP session for server '%s': %s",
                    self._server_id,
                    exc,
                )
            async with self._lock:
                self._exit_stack = None
                self._session = None
                self._tools = []
                self._close_event = None
                self._ready_event = None
                self._lifecycle_task = None

    async def connect(self) -> None:
        """Spawn the MCP server and initialize the client session."""

        async with self._lock:
            if self._session is not None:
                return
            lifecycle = self._lifecycle_task
            ready_event = self._ready_event

            if lifecycle is None or lifecycle.done() or ready_event is None:
                self._close_event = asyncio.Event()
                self._ready_event = asyncio.Event()
                self._lifecycle_task = asyncio.create_task(self._run_lifecycle())
                lifecycle = self._lifecycle_task
                ready_event = self._ready_event

        if ready_event is None or lifecycle is None:
            raise RuntimeError("Failed to initialize MCP client lifecycle task")

        await ready_event.wait()

        async with self._lock:
            if self._session is not None:
                return
            error = self._last_connection_error

        if lifecycle.done() and error is None:
            try:
                lifecycle.result()
            except Exception as exc:  # noqa: BLE001
                error = exc

        if error:
            raise ConnectionError(
                f"Failed to connect to MCP server '{self._server_id}': {error}"
            ) from error
        raise ConnectionError(f"Failed to connect to MCP server '{self._server_id}'")

    async def reconnect(self) -> bool:
        """Attempt to reconnect to an HTTP MCP server.

        Returns True if reconnection was successful, False otherwise.
        Only applicable for HTTP servers.
        """
        if not self.is_http_server:
            logger.warning(
                "Reconnect called on non-HTTP server '%s', ignoring",
                self._server_id,
            )
            return False

        if self._reconnect_attempts >= HTTP_MAX_RECONNECT_ATTEMPTS:
            logger.error(
                "Maximum reconnection attempts (%d) reached for HTTP MCP server '%s'",
                HTTP_MAX_RECONNECT_ATTEMPTS,
                self._server_id,
            )
            return False

        self._reconnect_attempts += 1
        logger.info(
            "Attempting to reconnect to HTTP MCP server '%s' (attempt %d/%d)",
            self._server_id,
            self._reconnect_attempts,
            HTTP_MAX_RECONNECT_ATTEMPTS,
        )

        # Close existing connection if any
        await self.close()

        # Wait before reconnecting
        await asyncio.sleep(HTTP_RECONNECT_DELAY)

        try:
            await self.connect()
            logger.info(
                "Successfully reconnected to HTTP MCP server '%s'",
                self._server_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to reconnect to HTTP MCP server '%s': %s",
                self._server_id,
                exc,
            )
            return False

    async def close(self) -> None:
        """Tear down the MCP session and the underlying process."""

        async with self._lock:
            lifecycle = self._lifecycle_task
            close_event = self._close_event

        if lifecycle is None:
            async with self._lock:
                self._exit_stack = None
                self._session = None
                self._tools = []
            return

        logger.info("Closing MCP session for server '%s'", self._server_id)

        if close_event is not None and not close_event.is_set():
            close_event.set()

        try:
            await asyncio.wait_for(lifecycle, timeout=2.5)
        except asyncio.TimeoutError:
            logger.warning(
                "MCP session close timed out after 2.5s for server '%s'",
                self._server_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error closing MCP session for server '%s': %s",
                self._server_id,
                exc,
            )

        async with self._lock:
            self._exit_stack = None
            self._session = None
            self._tools = []
            self._close_event = None
            self._ready_event = None
            self._lifecycle_task = None

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
