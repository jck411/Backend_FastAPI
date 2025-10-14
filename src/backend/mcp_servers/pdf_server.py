"""MCP server exposing Kreuzberg document intelligence utilities.

This module piggybacks on the official Kreuzberg MCP server implementation so
that we can manage PDF and other document formats alongside our existing tool
suite. The Kreuzberg project already provides a comprehensive set of tools,
resources, and prompts – we simply re-export its FastMCP instance so the
backend can launch it like any other built-in server.
"""

from __future__ import annotations

from kreuzberg._mcp import server as kreuzberg_server

mcp = kreuzberg_server.mcp


def run() -> None:  # pragma: no cover - integration entrypoint
    """Execute the Kreuzberg MCP server when launched as a script."""

    kreuzberg_server.main()


# Re-export the highest-level helpers so downstream imports remain stable.
extract_document = kreuzberg_server.extract_document
extract_bytes = kreuzberg_server.extract_bytes
batch_extract_bytes = kreuzberg_server.batch_extract_bytes
batch_extract_document = kreuzberg_server.batch_extract_document
extract_simple = kreuzberg_server.extract_simple


__all__ = [
    "mcp",
    "run",
    "extract_document",
    "extract_bytes",
    "batch_extract_bytes",
    "batch_extract_document",
    "extract_simple",
]


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()
