"""Built-in MCP server exposing housekeeping utilities (time, chat history, etc.)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import timezone
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from backend.config import get_settings
from backend.repository import ChatRepository
from backend.services.attachment_urls import refresh_message_attachments
from backend.services.time_context import (
    EASTERN_TIMEZONE_NAME,
    build_context_lines,
    create_time_snapshot,
    format_timezone_offset,
    resolve_timezone,
)

mcp = FastMCP("housekeeping")

EASTERN_TIMEZONE = resolve_timezone(EASTERN_TIMEZONE_NAME, timezone.utc)
_MESSAGE_PREVIEW_LIMIT = 2000
_MAX_HISTORY_LIMIT = 100

_repository: ChatRepository | None = None
_repository_lock = asyncio.Lock()


@dataclass
class EchoResult:
    message: str
    uppercase: bool


def _resolve_chat_db_path() -> Path:
    """Resolve the absolute path to the chat history database."""

    settings = get_settings()
    db_path = settings.chat_database_path
    if db_path.is_absolute():
        return db_path
    module_path = Path(__file__).resolve()
    project_root = module_path.parents[3]
    return project_root / db_path


async def _get_repository() -> ChatRepository:
    """Return a singleton ChatRepository instance."""

    global _repository
    if _repository is not None:
        return _repository

    async with _repository_lock:
        if _repository is None:
            repository = ChatRepository(_resolve_chat_db_path())
            await repository.initialize()
            _repository = repository
    return _repository


def _render_content(value: Any) -> tuple[str, bool]:
    """Return a readable representation of message content plus truncation flag."""

    if value is None:
        return ("", False)
    if isinstance(value, str):
        text = value.strip()
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    truncated = len(text) > _MESSAGE_PREVIEW_LIMIT
    if truncated:
        text = text[:_MESSAGE_PREVIEW_LIMIT].rstrip() + "…"
    return text, truncated


@mcp.tool("test_echo")
async def test_echo(message: str, uppercase: bool = False) -> dict[str, Any]:
    """Return the message, optionally uppercased, for integration testing."""

    payload = message.upper() if uppercase else message
    return asdict(EchoResult(message=payload, uppercase=uppercase))


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

    snapshot = create_time_snapshot(EASTERN_TIMEZONE_NAME, fallback=timezone.utc)
    eastern = snapshot.eastern

    if format == "iso":
        rendered = snapshot.iso_utc
    elif format == "unix":
        rendered = str(snapshot.unix_seconds)
    else:  # pragma: no cover - guarded by Literal
        raise ValueError(f"Unsupported format: {format}")

    offset = format_timezone_offset(eastern.utcoffset())
    context_lines = list(build_context_lines(snapshot))
    context_summary = "\n".join(context_lines)

    return {
        "format": format,
        "value": rendered,
        "utc_iso": snapshot.iso_utc,
        "utc_unix": str(snapshot.unix_seconds),
        "utc_unix_precise": snapshot.unix_precise,
        "eastern_iso": eastern.isoformat(),
        "eastern_abbreviation": eastern.tzname(),
        "eastern_display": eastern.strftime("%a %b %d %Y %I:%M:%S %p %Z"),
        "eastern_offset": offset,
        "timezone": EASTERN_TIMEZONE_NAME,
        "context_lines": context_lines,
        "context_summary": context_summary,
    }


@mcp.tool(
    "chat_history",
    description=(
        "Return stored chat messages for a session, including ISO timestamps. "
        "Use this tool whenever you need precise timing for earlier turns. "
        "Provide a session_id (automatically supplied by the orchestrator) to retrieve "
        "the most recent messages."
    ),
)
async def chat_history(
    session_id: str | None = None,
    limit: int = 20,
    newest_first: bool = False,
) -> dict[str, Any]:
    """Retrieve recent chat messages plus timestamps for an existing session."""

    if session_id is None or not session_id.strip():
        return {
            "error": "session_id is required to look up conversation history.",
            "hint": "The backend injects this automatically; if calling manually, pass a session_id.",
        }

    if limit <= 0:
        return {"error": "limit must be a positive integer."}

    applied_limit = min(limit, _MAX_HISTORY_LIMIT)

    try:
        repository = await _get_repository()
        messages = await repository.get_messages(session_id)
        settings = get_settings()
        messages = await refresh_message_attachments(
            messages,
            repository,
            ttl=settings.attachment_signed_url_ttl,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "error": f"Failed to load messages for session '{session_id}'.",
            "detail": str(exc),
        }

    if not messages:
        guidance = (
            "No stored messages were found for this session. "
            "If you are certain messages should exist, double-check the session identifier."
        )
        return {
            "session_id": session_id,
            "total_available": 0,
            "applied_limit": 0,
            "newest_first": newest_first,
            "messages": [],
            "summary": guidance,
            "guidance": guidance,
        }

    selected = messages[-applied_limit:]
    if newest_first:
        selected = list(reversed(selected))

    total_messages = len(messages)
    start_index = total_messages - len(selected)

    payload_messages: list[dict[str, Any]] = []
    summary_lines: list[str] = []

    for offset, record in enumerate(selected):
        role = record.get("role", "unknown")
        created_display = (
            record.get("created_at") or record.get("created_at_utc") or "unknown time"
        )
        content_text, truncated = _render_content(record.get("content"))

        payload_messages.append(
            {
                "position": start_index + offset + 1,
                "role": role,
                "created_at": record.get("created_at"),
                "created_at_utc": record.get("created_at_utc"),
                "message_id": record.get("message_id"),
                "client_message_id": record.get("client_message_id"),
                "parent_client_message_id": record.get("parent_client_message_id"),
                "content": content_text,
                "truncated": truncated,
            }
        )

        line = f"{payload_messages[-1]['position']}. [{created_display}] {role}: {content_text}"
        if truncated:
            line += " … (truncated)"
        summary_lines.append(line)

    enumerated_messages = [
        {**message, "index": idx + 1} for idx, message in enumerate(payload_messages)
    ]

    guidance_text = (
        "Use the timestamped entries below when referencing prior conversation turns. "
        "Cite their `created_at` (local ET) or `created_at_utc` values when explaining chronology."
    )

    return {
        "session_id": session_id,
        "total_available": total_messages,
        "applied_limit": len(payload_messages),
        "newest_first": newest_first,
        "messages": enumerated_messages,
        "summary": guidance_text + "\n" + "\n".join(summary_lines),
        "guidance": guidance_text,
    }


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = ["mcp", "run", "test_echo", "current_time", "chat_history"]
