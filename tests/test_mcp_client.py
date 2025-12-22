"""Tests for MCP client HTTP transport and reconnection logic."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from mcp.types import CallToolResult, TextContent, Tool

from backend.chat.mcp_client import (
    HTTP_MAX_RECONNECT_ATTEMPTS,
    HTTP_RECONNECT_DELAY,
    MCPToolClient,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def mock_tool() -> Tool:
    """Create a mock tool for testing."""
    return Tool(
        name="test_tool",
        description="A test tool",
        inputSchema={"type": "object", "properties": {"arg": {"type": "string"}}},
    )


@pytest.fixture
def mock_session(mock_tool: Tool) -> MagicMock:
    """Create a mock ClientSession."""
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(
        return_value=MagicMock(tools=[mock_tool], nextCursor=None)
    )
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[TextContent(type="text", text="result")], isError=False
        )
    )
    return session


class TestHTTPTransportBasics:
    """Test basic HTTP transport functionality."""

    async def test_http_server_detection(self) -> None:
        """Test that HTTP servers are correctly identified."""
        http_client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="http-server"
        )
        assert http_client.is_http_server is True
        assert http_client.http_url == "http://example.com/mcp"

        module_client = MCPToolClient(
            server_module="backend.mcp_servers.test_server",
            http_port=9000,
            server_id="module-server",
        )
        assert module_client.is_http_server is True
        assert module_client.http_url == "http://127.0.0.1:9000/mcp"

        command_client = MCPToolClient(
            command=["python", "-m", "some.module"],
            http_port=9001,
            server_id="command-server",
        )
        assert command_client.is_http_server is True
        assert command_client.http_url == "http://127.0.0.1:9001/mcp"

    async def test_http_connection_with_timeout(self, mock_session: MagicMock) -> None:
        """Test that HTTP connections establish a session."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch(
                "mcp.client.streamable_http.streamablehttp_client"
            ) as mock_http_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
        ):
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_context.__aexit__ = AsyncMock()
            mock_http_client.return_value = mock_context

            await client.connect()

            mock_http_client.assert_called_once_with("http://example.com/mcp")

        await client.close()


class TestHTTPErrorHandling:
    """Test HTTP-specific error handling."""

    async def test_connection_timeout(self) -> None:
        """Test handling of connection timeout."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with patch(
            "mcp.client.streamable_http.streamablehttp_client"
        ) as mock_http_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(
                side_effect=asyncio.TimeoutError("Connection timed out")
            )
            mock_http_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            assert "timed out" in str(exc_info.value).lower()

    async def test_dns_resolution_failure(self) -> None:
        """Test handling of DNS resolution failures."""
        client = MCPToolClient(
            http_url="http://invalid.domain.local/mcp", server_id="test-server"
        )

        dns_error = httpx.ConnectError("Name or service not known", request=MagicMock())

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=dns_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "dns" in error_msg or "hostname" in error_msg
            assert client._last_connection_error is dns_error

    async def test_connection_refused(self) -> None:
        """Test handling of connection refused errors."""
        client = MCPToolClient(
            http_url="http://localhost:9999/mcp", server_id="test-server"
        )

        refused_error = httpx.ConnectError(
            "[Errno 111] Connection refused", request=MagicMock()
        )

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=refused_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "refused" in error_msg
            assert "running" in error_msg

    async def test_network_error(self) -> None:
        """Test handling of generic network errors."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        network_error = httpx.NetworkError("Network unreachable", request=MagicMock())

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=network_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            assert "network error" in str(exc_info.value).lower()

    async def test_http_401_authentication_required(self) -> None:
        """Test handling of 401 Unauthorized responses."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.reason_phrase = "Unauthorized"
        auth_error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=auth_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "authentication" in error_msg or "401" in error_msg

    async def test_http_403_forbidden(self) -> None:
        """Test handling of 403 Forbidden responses."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.reason_phrase = "Forbidden"
        forbidden_error = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=forbidden_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "forbidden" in error_msg or "403" in error_msg

    async def test_http_404_not_found(self) -> None:
        """Test handling of 404 Not Found responses."""
        client = MCPToolClient(
            http_url="http://example.com/wrong-endpoint", server_id="test-server"
        )

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        not_found_error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=not_found_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "not found" in error_msg or "404" in error_msg

    async def test_http_500_server_error(self) -> None:
        """Test handling of 500 Internal Server Error responses."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"
        server_error = httpx.HTTPStatusError(
            "Internal Server Error", request=MagicMock(), response=mock_response
        )

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=server_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "500" in error_msg or "internal error" in error_msg

    async def test_invalid_sse_stream_format(self) -> None:
        """Test handling of invalid SSE stream format."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        value_error = ValueError("Invalid SSE stream format: missing event type")

        with patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=value_error)
            mock_sse_client.return_value = mock_context

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            error_msg = str(exc_info.value).lower()
            assert "invalid" in error_msg and "sse" in error_msg


class TestHTTPReconnectionLogic:
    """Test reconnection logic for HTTP servers."""

    async def test_reconnect_succeeds(self, mock_session: MagicMock) -> None:
        """Test successful reconnection to HTTP server."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_context.__aexit__ = AsyncMock()
            mock_sse_client.return_value = mock_context

            # Simulate a connection failure
            client._last_connection_error = Exception("Previous failure")
            client._reconnect_attempts = 1

            success = await client.reconnect()

            assert success is True
            assert client._reconnect_attempts == 0  # Reset after successful connection
            assert client._last_connection_error is None
            mock_sleep.assert_called_once_with(HTTP_RECONNECT_DELAY)

        await client.close()

    async def test_reconnect_fails_max_attempts(self) -> None:
        """Test reconnection failure after max attempts."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )
        client._reconnect_attempts = HTTP_MAX_RECONNECT_ATTEMPTS

        success = await client.reconnect()

        assert success is False
        assert client._reconnect_attempts == HTTP_MAX_RECONNECT_ATTEMPTS

    async def test_reconnect_fails_connection_error(
        self, mock_session: MagicMock
    ) -> None:
        """Test reconnection failure due to connection error."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(
                side_effect=httpx.ConnectError("Still down", request=MagicMock())
            )
            mock_sse_client.return_value = mock_context

            initial_attempts = client._reconnect_attempts
            success = await client.reconnect()

            assert success is False
            assert client._reconnect_attempts == initial_attempts + 1

    async def test_reconnect_resets_counter_on_success(
        self, mock_session: MagicMock
    ) -> None:
        """Test that successful reconnection resets the counter."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_context.__aexit__ = AsyncMock()
            mock_sse_client.return_value = mock_context

            # Simulate previous failed attempts
            client._reconnect_attempts = 2

            # First connection should reset counter
            await client.connect()
            assert client._reconnect_attempts == 0

            # Now close and reconnect
            await client.close()
            success = await client.reconnect()

            assert success is True
            assert client._reconnect_attempts == 0

        await client.close()

    async def test_multiple_reconnect_attempts(self, mock_session: MagicMock) -> None:
        """Test multiple reconnection attempts with eventual success."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        attempt_count = 0

        def mock_connect_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise httpx.ConnectError("Connection failed", request=MagicMock())
            return (MagicMock(), MagicMock(), MagicMock())

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=mock_connect_side_effect)
            mock_context.__aexit__ = AsyncMock()
            mock_sse_client.return_value = mock_context

            # First two attempts should fail
            success1 = await client.reconnect()
            assert success1 is False
            assert client._reconnect_attempts == 1

            success2 = await client.reconnect()
            assert success2 is False
            assert client._reconnect_attempts == 2

            # Third attempt should succeed
            success3 = await client.reconnect()
            assert success3 is True
            assert client._reconnect_attempts == 0  # Reset on success

        await client.close()


class TestHTTPToolExecution:
    """Test tool execution over HTTP transport."""

    async def test_call_tool_over_http(self, mock_session: MagicMock) -> None:
        """Test that tools can be called successfully over HTTP."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
        ):
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_context.__aexit__ = AsyncMock()
            mock_sse_client.return_value = mock_context

            await client.connect()

            result = await client.call_tool("test_tool", {"arg": "value"})

            assert result is not None
            mock_session.call_tool.assert_called_once_with(
                "test_tool", {"arg": "value"}
            )

        await client.close()

    async def test_get_openai_tools_over_http(self, mock_session: MagicMock) -> None:
        """Test that tools can be retrieved in OpenAI format over HTTP."""
        client = MCPToolClient(
            http_url="http://example.com/mcp", server_id="test-server"
        )

        with (
            patch("mcp.client.streamable_http.streamablehttp_client") as mock_sse_client,
            patch("backend.chat.mcp_client.ClientSession", return_value=mock_session),
        ):
            mock_streams = (MagicMock(), MagicMock(), MagicMock())
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_streams)
            mock_context.__aexit__ = AsyncMock()
            mock_sse_client.return_value = mock_context

            await client.connect()

            tools = client.get_openai_tools()

            assert len(tools) == 1
            assert tools[0]["function"]["name"] == "test_tool"
            assert tools[0]["function"]["description"] == "A test tool"

        await client.close()
