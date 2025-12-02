"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("shell-control")


# Add your tools here using the @mcp.tool() decorator


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
]
