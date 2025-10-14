"""Helper utilities shared by the Google Drive MCP server."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

__all__ = [
    "DRIVE_QUERY_PATTERNS",
    "build_drive_list_params",
    "check_public_link_permission",
    "format_public_sharing_error",
    "get_drive_image_url",
    "escape_query_term",
]

DRIVE_QUERY_PATTERNS = [
    re.compile(r"\b\w+\s*(=|!=|>|<)\s*['\"].*?['\"]", re.IGNORECASE),
    re.compile(r"\b\w+\s*(=|!=|>|<)\s*\d+", re.IGNORECASE),
    re.compile(r"\bcontains\b", re.IGNORECASE),
    re.compile(r"\bin\s+parents\b", re.IGNORECASE),
    re.compile(r"\bhas\s*\{", re.IGNORECASE),
    re.compile(r"\btrashed\s*=\s*(true|false)\b", re.IGNORECASE),
    re.compile(r"\bstarred\s*=\s*(true|false)\b", re.IGNORECASE),
    re.compile(r"['\"][^'\"]+['\"]\s+in\s+parents", re.IGNORECASE),
    re.compile(r"\bfullText\s+contains\b", re.IGNORECASE),
    re.compile(r"\bname\s*(=|contains)\b", re.IGNORECASE),
    re.compile(r"\bmimeType\s*(=|!=)\b", re.IGNORECASE),
]


def check_public_link_permission(permissions: List[Dict[str, Any]]) -> bool:
    """Return True if the file is shared with “Anyone with the link”."""
    return any(
        permission.get("type") == "anyone"
        and permission.get("role") in {"reader", "writer", "commenter"}
        for permission in permissions or []
    )


def format_public_sharing_error(file_name: str, file_id: str) -> str:
    """Return a standard error message for files lacking public access."""
    return (
        f"❌ Permission Error: '{file_name}' not shared publicly. "
        "Set 'Anyone with the link' → 'Viewer' in Google Drive sharing. "
        f"File: https://drive.google.com/file/d/{file_id}/view"
    )


def get_drive_image_url(file_id: str) -> str:
    """Return the embeddable Drive URL used for publicly shared images."""
    return f"https://drive.google.com/uc?export=view&id={file_id}"


def build_drive_list_params(
    query: str,
    page_size: int,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> Dict[str, Any]:
    """Return parameters suitable for Drive `files().list` calls."""
    params: Dict[str, Any] = {
        "q": query,
        "pageSize": max(page_size, 1),
        "fields": (
            "nextPageToken, files(id, name, mimeType, webViewLink, iconLink, "
            "modifiedTime, size)"
        ),
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": include_items_from_all_drives,
    }

    if drive_id:
        params["driveId"] = drive_id
        params["corpora"] = corpora or "drive"
    elif corpora:
        params["corpora"] = corpora

    return params


def escape_query_term(value: str) -> str:
    """Escape apostrophes in literals for Drive query syntax."""
    return value.replace("'", "\\'")
