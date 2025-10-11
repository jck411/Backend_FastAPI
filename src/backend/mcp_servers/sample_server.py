"""Built-in MCP server exposing simple test tools for aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-toolkit")

EASTERN_TIMEZONE = ZoneInfo("America/New_York")


@dataclass
class EchoResult:
    message: str
    uppercase: bool


@mcp.tool("test_echo")
async def test_echo(message: str, uppercase: bool = False) -> dict[str, Any]:
    """Return the message, optionally uppercased, for integration testing."""

    payload = message.upper() if uppercase else message
    return asdict(EchoResult(message=payload, uppercase=uppercase))


def _format_timezone_offset(offset: timedelta | None) -> str:
    """Return an ISO-8601 style UTC offset string."""

    if offset is None:
        return "UTC+00:00"

    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


@mcp.tool(
    "current_time",
    description=(
        "Retrieve the current moment with precise Unix timestamps plus UTC and Eastern Time "
        "(ET/EDT) ISO formats. Use this whenever the conversation needs an up-to-date clock "
        "reference or time zone comparison."
    ),
)
async def current_time(format: Literal["iso", "unix"] = "iso") -> dict[str, Any]:
    """Return the current time with UTC and Eastern Time representations."""

    now_utc = datetime.now(timezone.utc)
    eastern = now_utc.astimezone(EASTERN_TIMEZONE)
    unix_seconds = int(now_utc.timestamp())
    unix_precise = f"{now_utc.timestamp():.6f}"
    utc_iso = now_utc.isoformat()
    eastern_iso = eastern.isoformat()

    if format == "iso":
        rendered = utc_iso
    elif format == "unix":
        rendered = str(unix_seconds)
    else:  # pragma: no cover - guarded by Literal
        raise ValueError(f"Unsupported format: {format}")

    offset = _format_timezone_offset(eastern.utcoffset())

    return {
        "format": format,
        "value": rendered,
        "utc_iso": utc_iso,
        "utc_unix": str(unix_seconds),
        "utc_unix_precise": unix_precise,
        "eastern_iso": eastern_iso,
        "eastern_abbreviation": eastern.tzname(),
        "eastern_display": eastern.strftime("%a %b %d %Y %I:%M:%S %p %Z"),
        "eastern_offset": offset,
        "timezone": "America/New_York",
    }


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = ["mcp", "run", "test_echo", "current_time"]
