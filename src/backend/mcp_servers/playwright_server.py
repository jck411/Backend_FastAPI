"""MCP server exposing Playwright-based browser automation tools.

Connects to an existing browser via Chrome DevTools Protocol (CDP),
enabling browser control without screenshots in the LLM loop.
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

# Default port for HTTP transport
DEFAULT_HTTP_PORT = 9011
DEFAULT_CDP_ENDPOINT = "http://localhost:9222"
DEFAULT_CDP_PORT = 9222

# URLs that should never be auto-selected as the working page
# These are typically chat interfaces or important apps
_PROTECTED_URL_PATTERNS = [
    "localhost:5173",       # Dev server (Svelte frontend)
    "127.0.0.1:5173",
    "chat.openai.com",      # ChatGPT
    "gemini.google.com",    # Gemini
    "claude.ai",            # Claude
    "mail.google.com",      # Gmail
    "calendar.google.com",  # Calendar
]

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
# Global Browser State
# =============================================================================

# Lazy import playwright to avoid startup cost when not using browser tools
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
        raise RuntimeError("Not connected to browser. Call browser_connect first.")
    return _page


def _is_protected_url(url: str) -> bool:
    """Check if a URL is protected (should not be auto-selected for automation).

    Protected URLs are typically chat interfaces or important apps that
    should not be hijacked when connecting to the browser.
    """
    if not url:
        return False
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in _PROTECTED_URL_PATTERNS)


# =============================================================================
# Browser Tools
# =============================================================================


async def _browser_connect_impl(
    endpoint: str = DEFAULT_CDP_ENDPOINT,
    timeout_ms: int = 30000,
) -> str:
    """Internal implementation of browser_connect that can be called directly."""
    global _browser, _context, _page, _connected

    try:
        pw = await _ensure_playwright()

        # Connect to existing browser via CDP
        _browser = await pw.chromium.connect_over_cdp(
            endpoint,
            timeout=timeout_ms,
        )

        # Gather all pages across all contexts
        all_pages: list[Any] = []
        for ctx in _browser.contexts:
            all_pages.extend(ctx.pages)

        # Find the first non-protected page to use
        selected_page = None
        protected_skipped = []
        for p in all_pages:
            if _is_protected_url(p.url):
                protected_skipped.append(p.url)
            elif selected_page is None:
                selected_page = p

        # If all pages are protected, create a new tab
        if selected_page is None:
            if _browser.contexts:
                _context = _browser.contexts[0]
            else:
                _context = await _browser.new_context()
            _page = await _context.new_page()
            created_new_tab = True
        else:
            _page = selected_page
            _context = _page.context
            created_new_tab = False

        _connected = True

        # Gather info about open tabs
        tabs = []
        for ctx in _browser.contexts:
            for p in ctx.pages:
                page_title = await p.title()
                tabs.append({
                    "title": page_title[:50] if page_title else "(untitled)",
                    "url": p.url,
                    "protected": _is_protected_url(p.url),
                    "active": p == _page,
                })

        return json.dumps({
            "status": "ok",
            "endpoint": endpoint,
            "tabs_count": len(tabs),
            "tabs": tabs[:10],  # Limit to first 10 for token efficiency
            "current_url": _page.url if _page else None,
            "created_new_tab": created_new_tab,
            "protected_skipped": protected_skipped[:5] if protected_skipped else None,
        })

    except Exception as exc:
        _connected = False
        return json.dumps({
            "status": "error",
            "message": str(exc),
            "hint": "Ensure browser is running with: brave --remote-debugging-port=9222",
        })


@mcp.tool("browser_connect")  # type: ignore[misc]
async def browser_connect(
    endpoint: str = DEFAULT_CDP_ENDPOINT,
    timeout_ms: int = 30000,
) -> str:
    """Connect to a running browser via Chrome DevTools Protocol.

    The browser must be started with remote debugging enabled, e.g.:
        brave --remote-debugging-port=9222

    IMPORTANT: This will NOT hijack protected pages like localhost:5173,
    chat.openai.com, or other chat interfaces. If all open pages are
    protected, a new blank tab will be created for automation work.

    Args:
        endpoint: CDP endpoint URL (default: http://localhost:9222)
        timeout_ms: Connection timeout in milliseconds (default: 30000)

    Returns:
        JSON with status, browser info, and available pages.
    """
    return await _browser_connect_impl(endpoint, timeout_ms)


@mcp.tool("browser_open")  # type: ignore[misc]
async def browser_open(
    url: str | None = None,
    preset: str | None = None,
    wait_for_ready: bool = True,
    timeout_ms: int = 10000,
) -> str:
    """Launch a new minimal browser window (Brave 'app mode') with CDP enabled.

    Opens a clean, chromeless window like the waybar bookmarks.
    Automatically connects via CDP when ready.

    Use this when:
    - No browser is running with CDP enabled
    - You want a fresh window that won't interfere with existing tabs
    - You want to use a waybar bookmark preset

    Args:
        url: URL to open (ignored if preset is provided)
        preset: Waybar bookmark preset name. Options:
            - "chatgpt", "gemini", "google", "dev", "calendar", "gmail", "github"
        wait_for_ready: Wait for CDP connection after launch (default: True)
        timeout_ms: CDP connection timeout (default: 10000)

    Returns:
        JSON with status and connection info.
    """
    global _browser, _context, _page, _connected

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
        # First, check if CDP is already available (browser already running)
        # This prevents launching orphaned windows when a browser exists
        try:
            import httpx
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(f"http://localhost:{DEFAULT_CDP_PORT}/json/version")
                if resp.status_code == 200:
                    # Browser already running! Just connect, don't navigate
                    result = await _browser_connect_impl(timeout_ms=5000)
                    result_data = json.loads(result)

                    if result_data.get("status") == "ok":
                        # Return connection info; LLM can use browser_navigate if needed
                        return json.dumps({
                            "status": "ok",
                            "reused_existing": True,
                            "intended_url": target_url,
                            "preset": preset,
                            "current_url": result_data.get("current_url"),
                            "tabs_count": result_data.get("tabs_count"),
                            "hint": f"Browser already running. Use browser_navigate to go to {target_url}",
                        })
        except Exception:
            # CDP not available, proceed with launching new browser
            pass

        # No existing browser, launch Brave in app mode with CDP enabled
        cdp_flags = f"--remote-debugging-port={DEFAULT_CDP_PORT} --force-dark-mode --disable-session-restore"
        cmd = f'brave --app="{target_url}" {cdp_flags}'

        # Launch in background
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        if not wait_for_ready:
            return json.dumps({
                "status": "launched",
                "url": target_url,
                "preset": preset,
                "message": "Browser launched. Call browser_connect to connect.",
            })

        # Wait for CDP to become available
        start_time = time.time()
        last_error = None

        while (time.time() - start_time) * 1000 < timeout_ms:
            await asyncio.sleep(0.5)  # Check every 500ms

            try:
                result = await _browser_connect_impl(timeout_ms=2000)
                result_data = json.loads(result)

                if result_data.get("status") == "ok":
                    # Successfully connected
                    return json.dumps({
                        "status": "ok",
                        "launched_url": target_url,
                        "preset": preset,
                        "current_url": result_data.get("current_url"),
                        "tabs_count": result_data.get("tabs_count"),
                    })
                else:
                    last_error = result_data.get("message")
            except Exception as e:
                last_error = str(e)

        return json.dumps({
            "status": "error",
            "message": f"Browser launched but CDP connection timed out: {last_error}",
            "hint": "The browser may still be starting. Try browser_connect in a few seconds.",
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": str(exc),
        })


@mcp.tool("browser_new_tab")  # type: ignore[misc]
async def browser_new_tab(
    url: str = "about:blank",
    switch_to: bool = True,
) -> str:
    """Create a new tab for automation work.

    Use this when you're connected to a browser but want to work in a
    fresh tab without disturbing existing pages.

    Args:
        url: URL to open in the new tab (default: about:blank)
        switch_to: Make this the active page for automation (default: True)

    Returns:
        JSON with status and new tab info.
    """
    global _page

    try:
        if not _connected or _context is None:
            return json.dumps({
                "status": "error",
                "message": "Not connected to browser. Call browser_connect or browser_open first.",
            })

        # Create new page in current context
        new_page = await _context.new_page()

        # Navigate if URL provided
        if url and url != "about:blank":
            await new_page.goto(url, wait_until="domcontentloaded")

        # Switch to new page if requested
        if switch_to:
            _page = new_page
            await new_page.bring_to_front()

        page_title = await new_page.title()
        return json.dumps({
            "status": "ok",
            "url": new_page.url,
            "title": page_title[:50] if page_title else None,
            "active": switch_to,
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
    """Navigate to a URL in the current tab.

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
        JSON with status and clicked element info.
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
            "clicked": True,
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
        selector: CSS selector for the input element
        text: Text to type
        clear_first: Clear existing content before typing (default: True)
        delay_ms: Delay between keystrokes in milliseconds
        timeout_ms: Timeout waiting for element

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
            # Full page text
            if content_type == "text":
                content = await page.inner_text("body")
            elif content_type == "html":
                content = await page.content()
            else:
                content = await page.inner_text("body")

        # Truncate if needed
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


@mcp.tool("browser_tabs")  # type: ignore[misc]
async def browser_tabs(
    switch_to: int | None = None,
) -> str:
    """List browser tabs or switch to a specific tab.

    Args:
        switch_to: Tab index to switch to (0-based). If None, just list tabs.

    Returns:
        JSON with tabs list and current tab info.
    """
    global _page

    try:
        if not _connected or _browser is None:
            raise RuntimeError("Not connected to browser")

        # Gather all tabs
        tabs = []
        all_pages = []
        for ctx in _browser.contexts:
            for p in ctx.pages:
                all_pages.append(p)
                page_title = await p.title()
                tabs.append({
                    "index": len(tabs),
                    "title": page_title[:50] if page_title else "(untitled)",
                    "url": p.url,
                    "active": p == _page,
                })

        # Switch if requested
        if switch_to is not None:
            if 0 <= switch_to < len(all_pages):
                _page = all_pages[switch_to]
                await _page.bring_to_front()
                # Update active flag
                for i, tab in enumerate(tabs):
                    tab["active"] = (i == switch_to)
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"Invalid tab index: {switch_to}. Valid: 0-{len(all_pages)-1}",
                })

        return json.dumps({
            "status": "ok",
            "tabs_count": len(tabs),
            "tabs": tabs,
            "current_index": next(
                (i for i, t in enumerate(tabs) if t["active"]), 0
            ),
        })

    except Exception as exc:
        return json.dumps({
            "status": "error",
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

        # Determine save path
        if path:
            save_path = Path(path)
        else:
            save_path = Path(tempfile.gettempdir()) / f"screenshot_{int(time.time())}.png"

        # Take screenshot
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
    """Close the Playwright connection (does NOT close the browser itself).

    Use this to cleanly disconnect when done with automation.
    The browser window remains open for manual use.

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
            "message": "Disconnected from browser",
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
    "browser_connect",
    "browser_open",
    "browser_new_tab",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_extract",
    "browser_wait",
    "browser_tabs",
    "browser_screenshot",
    "browser_close",
]
