#!/usr/bin/env python3
"""Shell Chat CLI - Terminal client for Backend_FastAPI.

A rich TUI that connects to the FastAPI backend via HTTP/SSE,
providing the same capabilities as the Svelte frontend.
"""

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Optional

import httpx
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.style import Style
from rich.text import Text

# Cache directory for session persistence
CACHE_DIR = Path.home() / ".cache" / "shell-chat"
SESSION_FILE = CACHE_DIR / "session_id"

# Styles
USER_STYLE = Style(color="bright_blue", bold=True)
ASSISTANT_STYLE = Style(color="bright_green")
TOOL_STYLE = Style(color="yellow")
ERROR_STYLE = Style(color="red", bold=True)
INFO_STYLE = Style(color="cyan")


class ShellChat:
    """Terminal chat client for Backend_FastAPI."""

    CLIENT_ID = "cli"  # Client identifier for settings isolation

    def __init__(self, server_url: str, preset: Optional[str] = None, profile: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.client_api = f"{self.server_url}/api/clients/{self.CLIENT_ID}"
        self.preset = preset
        self.profile = profile or os.environ.get("SHELL_CHAT_PROFILE", "cli-default")
        self.session_id: Optional[str] = None
        self.console = Console()
        self.running = True
        self._load_session()

    def _load_session(self) -> None:
        """Load session ID from cache file."""
        try:
            if SESSION_FILE.exists():
                self.session_id = SESSION_FILE.read_text().strip()
                if self.session_id:
                    self.console.print(
                        f"[dim]Resuming session: {self.session_id[:8]}...[/dim]"
                    )
        except Exception:
            pass

    def _save_session(self) -> None:
        """Save session ID to cache file."""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if self.session_id:
                SESSION_FILE.write_text(self.session_id)
        except Exception:
            pass

    def _clear_session(self) -> None:
        """Clear the current session."""
        self.session_id = None
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
        except Exception:
            pass
        self.console.print(
            "[info]Session cleared. Starting fresh.[/info]", style=INFO_STYLE
        )

    async def _check_health(self) -> bool:
        """Check if backend is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.server_url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    model = data.get("active_model", "unknown")
                    try:
                        llm_resp = await client.get(f"{self.client_api}/llm")
                        if llm_resp.status_code == 200:
                            model = llm_resp.json().get("model", model)
                    except Exception:
                        pass
                    self.console.print(
                        f"[dim]Connected to backend. CLI model: {model}[/dim]"
                    )
                    return True
        except Exception as e:
            self.console.print(
                f"[error]Cannot connect to backend: {e}[/error]", style=ERROR_STYLE
            )
        return False

    async def _apply_preset(self, index_or_name: str) -> bool:
        """Apply a preset configuration by index."""
        try:
            # Try to parse as index first
            try:
                index = int(index_or_name)
            except ValueError:
                # If not an index, search by name
                presets = await self._get_presets()
                if presets is None:
                    return False
                index = next(
                    (i for i, p in enumerate(presets) if p.get("name", "").lower() == index_or_name.lower()),
                    -1,
                )
                if index < 0:
                    self.console.print(
                        f"[error]Preset '{index_or_name}' not found[/error]", style=ERROR_STYLE
                    )
                    return False

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.client_api}/presets/{index}/activate")
                if resp.status_code == 200:
                    self.console.print(
                        f"[info]Applied preset: {index_or_name}[/info]", style=INFO_STYLE
                    )
                    return True
                elif resp.status_code == 404:
                    self.console.print(
                        f"[error]Preset '{index_or_name}' not found[/error]", style=ERROR_STYLE
                    )
                else:
                    self.console.print(
                        f"[error]Failed to apply preset: {resp.status_code}[/error]",
                        style=ERROR_STYLE,
                    )
        except Exception as e:
            self.console.print(
                f"[error]Failed to apply preset: {e}[/error]", style=ERROR_STYLE
            )
        return False

    async def _get_presets(self) -> Optional[list]:
        """Get list of presets."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.client_api}/presets")
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("presets", [])
        except Exception:
            pass
        return None

    async def _list_presets(self) -> None:
        """List available presets."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.client_api}/presets")
                if resp.status_code == 200:
                    data = resp.json()
                    presets = data.get("presets", [])
                    active_index = data.get("active_index")
                    if not presets:
                        self.console.print("[dim]No presets configured[/dim]")
                        return
                    self.console.print("\n[bold]Available Presets:[/bold]")
                    for i, p in enumerate(presets):
                        name = p.get("name", "?")
                        llm = p.get("llm", {})
                        model = llm.get("model", "?")
                        marker = " [active]" if i == active_index else ""
                        self.console.print(f"  {i}. {name}{marker} - {model}")
                    self.console.print()
        except Exception as e:
            self.console.print(
                f"[error]Failed to list presets: {e}[/error]", style=ERROR_STYLE
            )

    async def _show_model(self) -> None:
        """Show current model."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.client_api}/llm")
                if resp.status_code == 200:
                    data = resp.json()
                    model = data.get("model", "unknown")
                    self.console.print(
                        f"[info]Current model: {model}[/info]", style=INFO_STYLE
                    )
        except Exception as e:
            self.console.print(
                f"[error]Failed to get model: {e}[/error]", style=ERROR_STYLE
            )

    async def _set_model(self, model_id: str) -> None:
        """Set the active model."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(
                    f"{self.client_api}/llm",
                    json={"model": model_id},
                )
                if resp.status_code == 200:
                    self.console.print(
                        f"[info]Model set to: {model_id}[/info]", style=INFO_STYLE
                    )
                else:
                    self.console.print(
                        "[error]Failed to set model[/error]", style=ERROR_STYLE
                    )
        except Exception as e:
            self.console.print(
                f"[error]Failed to set model: {e}[/error]", style=ERROR_STYLE
            )

    async def _list_tools(self) -> None:
        """List MCP servers and their status."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.server_url}/api/mcp/servers/")
                if resp.status_code == 200:
                    data = resp.json()
                    servers = data.get("servers", [])
                    self.console.print("\n[bold]MCP Servers:[/bold]")
                    for server in servers:
                        name = server.get("id", "?")
                        enabled = server.get("enabled", False)
                        status = server.get("status", "unknown")
                        icon = "✓" if enabled else "✗"
                        color = (
                            "green"
                            if enabled and status == "connected"
                            else "red"
                            if enabled
                            else "dim"
                        )
                        self.console.print(
                            f"  [{color}]{icon} {name}[/{color}] ({status})"
                        )
                    self.console.print()
        except Exception as e:
            self.console.print(
                f"[error]Failed to list tools: {e}[/error]", style=ERROR_STYLE
            )

    async def _toggle_tool(self, name: str, enabled: bool) -> None:
        """Enable or disable an MCP server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(
                    f"{self.server_url}/api/mcp/servers/{name}",
                    json={"enabled": enabled},
                )
                if resp.status_code == 200:
                    action = "enabled" if enabled else "disabled"
                    self.console.print(
                        f"[info]Server '{name}' {action}[/info]", style=INFO_STYLE
                    )
                elif resp.status_code == 404:
                    self.console.print(
                        f"[error]Server '{name}' not found[/error]", style=ERROR_STYLE
                    )
                else:
                    self.console.print(
                        f"[error]Failed to toggle server: {resp.status_code}[/error]",
                        style=ERROR_STYLE,
                    )
        except Exception as e:
            self.console.print(
                f"[error]Failed to toggle server: {e}[/error]", style=ERROR_STYLE
            )

    async def _show_system_prompt(self) -> None:
        """Show current system prompt."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.client_api}/llm")
                if resp.status_code == 200:
                    data = resp.json()
                    prompt = data.get("system_prompt", "")
                    self.console.print(
                        Panel(prompt or "(no system prompt set)", title="System Prompt", border_style="dim")
                    )
        except Exception as e:
            self.console.print(
                f"[error]Failed to get system prompt: {e}[/error]", style=ERROR_STYLE
            )


    def _show_help(self) -> None:
        """Show available commands."""
        help_text = """
[bold]Commands:[/bold]
  /help              Show this help message
  /clear             Clear session (new conversation)
  /model             Show current model
  /model <id>        Set model (e.g., /model anthropic/claude-3-opus)
  /presets           List available presets
  /preset <name>     Apply a preset
  /tools             List MCP servers and status
  /tools <name> on   Enable an MCP server
  /tools <name> off  Disable an MCP server
  /system            Show system prompt
  /quit              Exit shell-chat

[bold]Shortcuts:[/bold]
  Ctrl+C             Cancel current request
  Ctrl+D             Exit shell-chat
"""
        self.console.print(
            Panel(help_text.strip(), title="Shell Chat Help", border_style="blue")
        )

    async def _handle_command(self, cmd: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = cmd.strip().split(maxsplit=2)
        if not parts:
            return False

        command = parts[0].lower()

        if command == "/help":
            self._show_help()
            return True
        elif command == "/clear":
            self._clear_session()
            return True
        elif command == "/quit":
            self.running = False
            return True
        elif command == "/model":
            if len(parts) > 1:
                await self._set_model(parts[1])
            else:
                await self._show_model()
            return True
        elif command == "/presets":
            await self._list_presets()
            return True
        elif command == "/preset":
            if len(parts) > 1:
                await self._apply_preset(parts[1])
            else:
                self.console.print("[dim]Usage: /preset <name>[/dim]")
            return True
        elif command == "/tools":
            if len(parts) == 1:
                await self._list_tools()
            elif len(parts) >= 3:
                name = parts[1]
                action = parts[2].lower()
                if action in ("on", "enable", "true", "1"):
                    await self._toggle_tool(name, True)
                elif action in ("off", "disable", "false", "0"):
                    await self._toggle_tool(name, False)
                else:
                    self.console.print("[dim]Usage: /tools <name> on|off[/dim]")
            else:
                self.console.print("[dim]Usage: /tools or /tools <name> on|off[/dim]")
            return True
        elif command == "/system":
            await self._show_system_prompt()
            return True


        return False

    async def _stream_chat(self, message: str) -> None:
        """Send message and stream response via SSE."""
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": message}],
            "metadata": {
                "client_id": self.CLIENT_ID,
                "profile_id": self.profile,
            },
        }
        if self.session_id:
            payload["session_id"] = self.session_id

        full_response = ""
        tool_panels: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{self.server_url}/api/chat/stream",
                    json=payload,
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    if response.status_code != 200:
                        error = await response.aread()
                        self.console.print(
                            f"[error]Error {response.status_code}: {error.decode()}[/error]",
                            style=ERROR_STYLE,
                        )
                        return

                    event_type = "message"
                    buffer = ""

                    # Use Live display for streaming
                    with Live(console=self.console, refresh_per_second=10) as live:
                        async for chunk in response.aiter_text():
                            buffer += chunk
                            lines = buffer.split("\n")
                            buffer = lines[-1]  # Keep incomplete line

                            for line in lines[:-1]:
                                line = line.strip()
                                if not line:
                                    continue

                                if line.startswith("event:"):
                                    event_type = line[6:].strip()
                                elif line.startswith("data:"):
                                    data = line[5:].strip()

                                    if data == "[DONE]":
                                        continue

                                    try:
                                        parsed = json.loads(data)
                                    except json.JSONDecodeError:
                                        continue

                                    if event_type == "session":
                                        self.session_id = parsed.get("session_id")
                                        self._save_session()

                                    elif event_type == "message":
                                        # Extract content delta
                                        choices = parsed.get("choices", [])
                                        if choices:
                                            delta = choices[0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                full_response += content
                                                # Render markdown live
                                                display = Markdown(full_response)
                                                live.update(display)

                                    elif event_type == "tool":
                                        status = parsed.get("status", "")
                                        name = parsed.get("name", "?")
                                        if status == "started":
                                            tool_panels.append(f"🔧 {name}")
                                            live.update(
                                                Text(
                                                    f"🔧 Calling {name}...",
                                                    style=TOOL_STYLE,
                                                )
                                            )
                                        elif status == "finished":
                                            result = parsed.get("result", "")
                                            # Truncate long results
                                            if len(result) > 500:
                                                result = result[:500] + "..."
                                            tool_panels.append(
                                                f"✓ {name}: {result[:100]}"
                                            )
                                        elif status == "hop_limit":
                                            # Show pause message - LLM hit tool call limit
                                            hop_msg = parsed.get("message", "")
                                            hop_count = parsed.get("hop_count", 0)
                                            limit = parsed.get("limit", 20)
                                            live.update(
                                                Text(
                                                    f"⏸️  {hop_msg}",
                                                    style="bold cyan",
                                                )
                                            )
                                            # Also print it permanently so user sees it
                                            self.console.print(
                                                f"\n[bold cyan]⏸️  Completed {hop_count} tool calls (limit: {limit})[/bold cyan]"
                                            )
                                            self.console.print(
                                                "[cyan]Reply 'continue' or 'yes' to keep going, or ask something else.[/cyan]\n"
                                            )

                                    elif event_type == "metadata":
                                        # Could show usage stats here
                                        pass

                    # Show tool results summary after stream completes
                    for panel in tool_panels:
                        if panel.startswith("✓"):
                            self.console.print(f"[dim]{panel}[/dim]")

        except httpx.ReadTimeout:
            self.console.print("[error]Request timed out[/error]", style=ERROR_STYLE)
        except asyncio.CancelledError:
            self.console.print("\n[dim]Request cancelled[/dim]")
        except Exception as e:
            self.console.print(f"[error]Error: {e}[/error]", style=ERROR_STYLE)

    async def run(self) -> None:
        """Main chat loop."""
        # Check connection
        if not await self._check_health():
            return

        # Apply preset if specified
        if self.preset:
            await self._apply_preset(self.preset)

        self.console.print()
        self.console.print(
            "[bold]Shell Chat[/bold] - Type /help for commands, Ctrl+D to exit",
            style=INFO_STYLE,
        )
        self.console.print()

        while self.running:
            try:
                # Get user input
                user_input = Prompt.ask("[bold blue]You[/bold blue]")
                if not user_input.strip():
                    continue

                # Check for commands
                if user_input.startswith("/"):
                    handled = await self._handle_command(user_input)
                    if handled:
                        continue

                # Regular chat message
                self.console.print()
                await self._stream_chat(user_input)
                self.console.print()

            except EOFError:
                # Ctrl+D
                self.console.print("\n[dim]Goodbye![/dim]")
                break
            except KeyboardInterrupt:
                # Ctrl+C - just cancel current input
                self.console.print()
                continue


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Shell Chat - Terminal client for Backend_FastAPI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  shell-chat                           Connect to localhost:8000
  shell-chat --server http://pi:8000   Connect to remote server
  shell-chat --preset coding           Apply preset on startup

Environment Variables:
  SHELLCHAT_SERVER    Default server URL
""",
    )
    parser.add_argument(
        "--server",
        "-s",
        default=os.environ.get("SHELLCHAT_SERVER", "http://localhost:8000"),
        help="Backend server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--preset",
        "-p",
        default=None,
        help="Apply a preset on startup",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("SHELL_CHAT_PROFILE"),
        help="Client profile for MCP server filtering (default: cli-default or $SHELL_CHAT_PROFILE)",
    )

    args = parser.parse_args()

    # Handle signals
    def signal_handler(sig, frame):
        print("\nExiting...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the chat
    chat = ShellChat(server_url=args.server, preset=args.preset, profile=args.profile)
    try:
        asyncio.run(chat.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
