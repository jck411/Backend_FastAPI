"""Tests for the playwright MCP server."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.mcp_servers import playwright_server

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global browser state between tests."""
    playwright_server._playwright = None
    playwright_server._browser = None
    playwright_server._context = None
    playwright_server._page = None
    playwright_server._connected = False
    yield
    playwright_server._playwright = None
    playwright_server._browser = None
    playwright_server._context = None
    playwright_server._page = None
    playwright_server._connected = False


# Helper to get the underlying function from FunctionTool wrapper
def _get_fn(tool):
    """Get the underlying async function from a FunctionTool."""
    return tool.fn if hasattr(tool, "fn") else tool


async def test_browser_navigate_not_connected():
    """Test error when trying to navigate without connecting first."""
    fn = _get_fn(playwright_server.browser_navigate)
    result = json.loads(await fn("https://example.com"))

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_click_not_connected():
    """Test error when trying to click without connecting first."""
    fn = _get_fn(playwright_server.browser_click)
    result = json.loads(await fn("button"))

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_type_not_connected():
    """Test error when trying to type without connecting first."""
    fn = _get_fn(playwright_server.browser_type)
    result = json.loads(await fn("input", "hello"))

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_extract_not_connected():
    """Test error when trying to extract without connecting first."""
    fn = _get_fn(playwright_server.browser_extract)
    result = json.loads(await fn())

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_wait_not_connected():
    """Test error when trying to wait without connecting first."""
    fn = _get_fn(playwright_server.browser_wait)
    result = json.loads(await fn("#element"))

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_tabs_not_connected():
    """Test error when trying to list tabs without connecting first."""
    fn = _get_fn(playwright_server.browser_tabs)
    result = json.loads(await fn())

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_screenshot_not_connected():
    """Test error when trying to screenshot without connecting first."""
    fn = _get_fn(playwright_server.browser_screenshot)
    result = json.loads(await fn())

    assert result["status"] == "error"
    assert "connect" in result["message"].lower()


async def test_browser_close_when_not_connected():
    """Test close succeeds even when not connected."""
    fn = _get_fn(playwright_server.browser_close)
    result = json.loads(await fn())

    assert result["status"] == "ok"
    assert "disconnect" in result["message"].lower()


async def test_browser_navigate_success():
    """Test successful navigation with mocked page."""
    mock_response = MagicMock()
    mock_response.status = 200

    mock_page = MagicMock()
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example Domain")

    playwright_server._page = mock_page
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_navigate)
    result = json.loads(await fn("https://example.com"))

    assert result["status"] == "ok"
    assert result["http_status"] == 200
    mock_page.goto.assert_called_once()


async def test_browser_click_success():
    """Test successful click with mocked page."""
    mock_page = MagicMock()
    mock_page.click = AsyncMock()

    playwright_server._page = mock_page
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_click)
    result = json.loads(await fn("button.submit"))

    assert result["status"] == "ok"
    assert result["clicked"] is True
    mock_page.click.assert_called_once()


async def test_browser_type_success():
    """Test successful typing with mocked page."""
    mock_page = MagicMock()
    mock_page.fill = AsyncMock()

    playwright_server._page = mock_page
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_type)
    result = json.loads(await fn("input#email", "test@example.com"))

    assert result["status"] == "ok"
    assert result["typed_length"] == len("test@example.com")
    mock_page.fill.assert_called_once()


async def test_browser_extract_text_success():
    """Test successful text extraction with mocked page."""
    mock_element = MagicMock()
    mock_element.inner_text = AsyncMock(return_value="Hello World")

    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=mock_element)

    playwright_server._page = mock_page
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_extract)
    result = json.loads(await fn(selector="h1"))

    assert result["status"] == "ok"
    assert result["content"] == "Hello World"
    assert result["truncated"] is False


async def test_browser_extract_truncation():
    """Test that long content is truncated."""
    long_content = "A" * 10000

    mock_element = MagicMock()
    mock_element.inner_text = AsyncMock(return_value=long_content)

    mock_page = MagicMock()
    mock_page.query_selector = AsyncMock(return_value=mock_element)

    playwright_server._page = mock_page
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_extract)
    result = json.loads(await fn(selector="body", limit=5000))

    assert result["status"] == "ok"
    assert len(result["content"]) == 5000
    assert result["truncated"] is True


async def test_browser_tabs_list():
    """Test listing tabs with mocked browser."""
    mock_page1 = MagicMock()
    mock_page1.title = AsyncMock(return_value="Page 1")
    mock_page1.url = "https://example1.com"

    mock_page2 = MagicMock()
    mock_page2.title = AsyncMock(return_value="Page 2")
    mock_page2.url = "https://example2.com"

    mock_context = MagicMock()
    mock_context.pages = [mock_page1, mock_page2]

    mock_browser = MagicMock()
    mock_browser.contexts = [mock_context]

    playwright_server._browser = mock_browser
    playwright_server._page = mock_page1
    playwright_server._connected = True

    fn = _get_fn(playwright_server.browser_tabs)
    result = json.loads(await fn())

    assert result["status"] == "ok"
    assert result["tabs_count"] == 2
    assert len(result["tabs"]) == 2


def test_module_exports():
    """Test that all expected functions are exported."""
    expected = [
        "mcp",
        "run",
        "browser_connect",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_extract",
        "browser_wait",
        "browser_tabs",
        "browser_screenshot",
        "browser_close",
    ]
    for name in expected:
        assert hasattr(playwright_server, name), f"Missing export: {name}"
