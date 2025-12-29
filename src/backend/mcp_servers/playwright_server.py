"""MCP server exposing Playwright-based browser automation tools.

Always launches fresh app-mode browser windows for each session.
Connects via Chrome DevTools Protocol (CDP) for browser-native automation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

# Default ports
DEFAULT_HTTP_PORT = 9011
DEFAULT_CDP_PORT = 9222

# Waybar bookmark presets (brave --app mode minimal windows)
_WAYBAR_PRESETS: dict[str, str] = {
    "chatgpt": "https://chat.openai.com",
    "gemini": "https://gemini.google.com/app",
    "google": "https://www.google.com/",
    "dev": "http://localhost:5173/",
    "calendar": "https://calendar.google.com/calendar/u/0/r?pli=1",
    "gmail": "https://mail.google.com/mail/u/0/#inbox",
    "github": "https://github.com/jck411?tab=repositories",
}

mcp = FastMCP("playwright")

# =============================================================================
# Global Browser State (single app-mode window per session)
# =============================================================================

_playwright: Any = None
_browser: Any = None
_context: Any = None
_page: Any = None
_connected: bool = False


async def _ensure_playwright() -> Any:
    """Lazy-load playwright module."""
    global _playwright
    if _playwright is None:
        try:
            from playwright.async_api import async_playwright
            _playwright = await async_playwright().start()
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
    return _playwright


async def _get_page() -> Any:
    """Get the current page, raising if not connected."""
    if not _connected or _page is None:
        raise RuntimeError("Not connected. Call browser_open first.")
    return _page


# =============================================================================
# Browser Tools
# =============================================================================


@mcp.tool("browser_open")  # type: ignore[misc]
async def browser_open(
    url: str | None = None,
    preset: str | None = None,
    timeout_ms: int = 10000,
) -> str:
    """Launch a fresh app-mode browser window and connect for automation.

    Always starts a NEW window - no session restoration, no existing tabs.
    This is the only way to start browser automation.

    Args:
        url: URL to open (ignored if preset is provided)
        preset: Waybar bookmark preset name. Options:
            - "chatgpt", "gemini", "google", "dev", "calendar", "gmail", "github"
        timeout_ms: CDP connection timeout (default: 10000)

    Returns:
        JSON with status and connection info.
    """
    global _browser, _context, _page, _connected

    # Close any existing session first
    if _connected:
        await browser_close()

    # Resolve URL from preset or direct URL
    if preset:
        preset_lower = preset.lower()
        if preset_lower not in _WAYBAR_PRESETS:
            return json.dumps({
                "status": "error",
                "message": f"Unknown preset: {preset}",
                "available_presets": list(_WAYBAR_PRESETS.keys()),
            })
        target_url = _WAYBAR_PRESETS[preset_lower]
    elif url:
        target_url = url
    else:
        target_url = "about:blank"

    try:
        # Launch Brave in app mode with CDP enabled
        # --disable-session-restore: No tab restoration
        # --no-first-run: Skip first-run dialogs
        # --force-dark-mode: Dark theme
        cmd = [
            "brave",
            f"--app={target_url}",
            f"--remote-debugging-port={DEFAULT_CDP_PORT}",
            "--disable-session-restore",
            "--no-first-run",
            "--force-dark-mode",
        ]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait for CDP to become available
        pw = await _ensure_playwright()
        start_time = time.time()
        last_error = None

        while (time.time() - start_time) * 1000 < timeout_ms:
            await asyncio.sleep(0.3)

            try:
                _browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{DEFAULT_CDP_PORT}",
                    timeout=2000,
                )

                # Get the page from the browser
                if _browser.contexts and _browser.contexts[0].pages:
                    _context = _browser.contexts[0]
                    _page = _context.pages[0]
                else:
                    _context = await _browser.new_context()
                    _page = await _context.new_page()
                    await _page.goto(target_url)

                _connected = True

                return json.dumps({
                    "status": "ok",
                    "url": target_url,
                    "preset": preset,
                    "current_url": _page.url,
                })

            except Exception as e:
                last_error = str(e)

        return json.dumps({
            "status": "error",
            "message": f"CDP connection timed out: {last_error}",
            "hint": "Browser may still be starting. Try again.",
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@mcp.tool("browser_navigate")  # type: ignore[misc]
async def browser_navigate(
    url: str,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
) -> str:
    """Navigate to a URL in the current page.

    Args:
        url: The URL to navigate to
        wait_until: When to consider navigation complete:
            - "domcontentloaded" (default): DOM is ready
            - "load": Full page load including resources
            - "networkidle": No network activity for 500ms
        timeout_ms: Navigation timeout in milliseconds

    Returns:
        JSON with status, final URL, and page title.
    """
    try:
        page = await _get_page()

        response = await page.goto(
            url,
            wait_until=wait_until,
            timeout=timeout_ms,
        )

        page_title = await page.title()
        return json.dumps({
            "status": "ok",
            "url": page.url,
            "title": page_title[:100] if page_title else None,
            "http_status": response.status if response else None,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@mcp.tool("browser_click")  # type: ignore[misc]
async def browser_click(
    selector: str,
    button: str = "left",
    click_count: int = 1,
    timeout_ms: int = 10000,
) -> str:
    """Click an element on the page.

    Args:
        selector: CSS selector, text selector ("text=Click me"), or XPath
        button: Mouse button - "left", "right", or "middle"
        click_count: Number of clicks (2 for double-click)
        timeout_ms: Timeout waiting for element

    Returns:
        JSON with status.
    """
    try:
        page = await _get_page()

        await page.click(
            selector,
            button=button,
            click_count=click_count,
            timeout=timeout_ms,
        )

        return json.dumps({
            "status": "ok",
            "selector": selector,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "selector": selector,
            "message": str(exc),
        })


@mcp.tool("browser_type")  # type: ignore[misc]
async def browser_type(
    selector: str,
    text: str,
    clear_first: bool = True,
    delay_ms: int = 0,
    timeout_ms: int = 10000,
) -> str:
    """Type text into an input element.

    Args:
        selector: CSS selector for the input element. Common selectors:
            - Google search: textarea[name="q"]
            - YouTube search: input#search
            - Generic search: input[type="search"], input[name="search"]
            - Generic text input: input[type="text"]
        text: Text to type
        clear_first: Clear existing content before typing (default: True)
        delay_ms: Delay between keystrokes in milliseconds
        timeout_ms: Timeout waiting for element

    Tip: If typing fails, use browser_navigate with URL params instead:
        https://www.google.com/search?q=your+search+query

    Returns:
        JSON with status.
    """
    try:
        page = await _get_page()

        if clear_first:
            await page.fill(selector, text, timeout=timeout_ms)
        else:
            await page.type(selector, text, delay=delay_ms, timeout=timeout_ms)

        return json.dumps({
            "status": "ok",
            "selector": selector,
            "typed_length": len(text),
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "selector": selector,
            "message": str(exc),
        })


@mcp.tool("browser_press_key")  # type: ignore[misc]
async def browser_press_key(
    key: str,
    selector: str | None = None,
) -> str:
    """Press a keyboard key on the page.

    Use this to submit forms (Enter), navigate (Tab), close dialogs (Escape), etc.

    Args:
        key: Key to press. Examples:
            - "Enter" - submit form
            - "Tab" - next field
            - "Escape" - close dialog
            - "ArrowDown", "ArrowUp" - navigate lists
            - "Backspace", "Delete" - delete text
            - Modifiers: "Control+a", "Shift+Tab", "Meta+Enter"
        selector: Optional element to focus first before pressing key

    Returns:
        JSON with status.
    """
    try:
        page = await _get_page()

        if selector:
            await page.focus(selector)

        await page.keyboard.press(key)

        return json.dumps({
            "status": "ok",
            "key": key,
            "selector": selector,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "key": key,
            "message": str(exc),
        })


@mcp.tool("browser_extract")  # type: ignore[misc]
async def browser_extract(
    selector: str | None = None,
    content_type: str = "text",
    limit: int = 5000,
) -> str:
    """Extract content from the page.

    Args:
        selector: CSS selector to extract from (None = entire page)
        content_type: What to extract:
            - "text": Visible text content (default)
            - "html": Inner HTML
            - "value": Input value
            - "attribute:name": Specific attribute
        limit: Maximum characters to return (default: 5000)

    Returns:
        JSON with status and extracted content.
    """
    try:
        page = await _get_page()

        if selector:
            element = await page.query_selector(selector)
            if not element:
                return json.dumps({
                    "status": "error",
                    "message": f"Element not found: {selector}",
                })

            if content_type == "text":
                content = await element.inner_text()
            elif content_type == "html":
                content = await element.inner_html()
            elif content_type == "value":
                content = await element.input_value()
            elif content_type.startswith("attribute:"):
                attr_name = content_type.split(":", 1)[1]
                content = await element.get_attribute(attr_name) or ""
            else:
                content = await element.inner_text()
        else:
            if content_type == "text":
                content = await page.inner_text("body")
            elif content_type == "html":
                content = await page.content()
            else:
                content = await page.inner_text("body")

        truncated = len(content) > limit
        content = content[:limit]

        return json.dumps({
            "status": "ok",
            "selector": selector or "body",
            "content_type": content_type,
            "content": content,
            "truncated": truncated,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@mcp.tool("browser_wait")  # type: ignore[misc]
async def browser_wait(
    selector: str | None = None,
    state: str = "visible",
    timeout_ms: int = 10000,
) -> str:
    """Wait for a condition on the page.

    Args:
        selector: CSS selector to wait for (None = just wait timeout_ms)
        state: Element state to wait for:
            - "visible": Element is visible (default)
            - "hidden": Element is hidden or removed
            - "attached": Element exists in DOM
        timeout_ms: Maximum wait time

    Returns:
        JSON with status and elapsed time.
    """
    try:
        page = await _get_page()
        start = time.time()

        if selector:
            await page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout_ms,
            )
        else:
            await asyncio.sleep(timeout_ms / 1000)

        elapsed_ms = int((time.time() - start) * 1000)

        return json.dumps({
            "status": "ok",
            "selector": selector,
            "state": state,
            "elapsed_ms": elapsed_ms,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "selector": selector,
            "message": str(exc),
        })


@mcp.tool("browser_screenshot")  # type: ignore[misc]
async def browser_screenshot(
    selector: str | None = None,
    full_page: bool = False,
    path: str | None = None,
) -> str:
    """Take a screenshot of the page or a specific element.

    Args:
        selector: CSS selector for element to screenshot (None = viewport)
        full_page: Capture entire scrollable page (ignored if selector provided)
        path: Save path. If None, saves to temp file.

    Returns:
        JSON with status and file path.
    """
    try:
        page = await _get_page()

        if path:
            save_path = Path(path)
        else:
            save_path = Path(tempfile.gettempdir()) / f"screenshot_{int(time.time())}.png"

        if selector:
            element = await page.query_selector(selector)
            if not element:
                return json.dumps({
                    "status": "error",
                    "message": f"Element not found: {selector}",
                })
            await element.screenshot(path=str(save_path))
        else:
            await page.screenshot(path=str(save_path), full_page=full_page)

        return json.dumps({
            "status": "ok",
            "path": str(save_path),
            "selector": selector,
            "full_page": full_page if not selector else False,
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@mcp.tool("browser_close")  # type: ignore[misc]
async def browser_close() -> str:
    """Close the browser and disconnect.

    Closes the app-mode window entirely.

    Returns:
        JSON with status.
    """
    global _browser, _context, _page, _connected, _playwright

    try:
        if _browser:
            await _browser.close()
        if _playwright:
            await _playwright.stop()

        _browser = None
        _context = None
        _page = None
        _playwright = None
        _connected = False

        return json.dumps({
            "status": "ok",
            "message": "Browser closed",
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


# =============================================================================
# Server Entry Point
# =============================================================================


def run(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
) -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server with the specified transport."""
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    parser = argparse.ArgumentParser(description="Playwright MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port for HTTP server",
    )
    args = parser.parse_args()
    run(args.transport, args.host, args.port)


__all__ = [
    "mcp",
    "run",
    "browser_open",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_extract",
    "browser_wait",
    "browser_screenshot",
    "browser_close",
]
