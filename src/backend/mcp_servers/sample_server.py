"""Built-in MCP server exposing simple test tools for aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-toolkit")


@dataclass
class EchoResult:
    message: str
    uppercase: bool


@mcp.tool("test_echo")
async def test_echo(message: str, uppercase: bool = False) -> dict[str, Any]:
    """Return the message, optionally uppercased, for integration testing."""

    payload = message.upper() if uppercase else message
    return asdict(EchoResult(message=payload, uppercase=uppercase))


@mcp.tool("current_time")
async def current_time(format: Literal["iso", "unix"] = "iso") -> dict[str, Any]:
    """Return the current UTC time in ISO 8601 or Unix timestamp form."""

    now = datetime.now(timezone.utc)
    if format == "iso":
        rendered = now.isoformat()
    elif format == "unix":
        rendered = f"{now.timestamp():.6f}"
    else:  # pragma: no cover - guarded by Literal
        raise ValueError(f"Unsupported format: {format}")

    return {
        "format": format,
        "value": rendered,
    }


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = ["mcp", "run", "test_echo", "current_time"]
