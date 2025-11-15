"""Helpers for preparing chat messages for model consumption."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, MutableMapping, Sequence


def parse_attachment_references(text: str) -> tuple[str, list[str]]:
    """Extract attachment IDs from plain text markers or JSON payloads."""

    if not isinstance(text, str):
        return text, []

    original_text = text
    attachment_ids: list[str] = []

    if "attachment_id:" in text:
        lines: list[str] = []
        for line in text.split("\n"):
            if line.strip().startswith("attachment_id:"):
                attachment_id = line.strip().split(":", 1)[1].strip()
                if attachment_id:
                    attachment_ids.append(attachment_id)
            else:
                lines.append(line)
        text = "\n".join(lines).strip()

    if not attachment_ids:
        attachment_ids = _extract_attachment_ids_from_json(original_text)

    return text, attachment_ids


def _extract_attachment_ids_from_json(text: str) -> list[str]:
    """Parse JSON text to locate attachment_id fields."""

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return []

    found: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            attachment_id = value.get("attachment_id")
            if isinstance(attachment_id, str) and attachment_id.strip():
                found.append(attachment_id.strip())
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return found


def prepare_messages_for_model(
    messages: Sequence[MutableMapping[str, Any]] | Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return a message list formatted for model consumption."""

    prepared: list[dict[str, Any]] = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        content = message.get("content")

        if role != "tool" or not isinstance(content, list):
            prepared.append(deep_copy_jsonable(message))
            continue

        text_fragments: list[str] = []
        image_fragments: list[dict[str, Any]] = []
        other_fragments: list[dict[str, Any]] = []

        for fragment in content:
            if not isinstance(fragment, dict):
                continue
            fragment_type = fragment.get("type")
            if fragment_type == "text":
                text_value = fragment.get("text")
                if isinstance(text_value, str):
                    text_fragments.append(text_value)
            elif fragment_type == "image_url":
                image_data = fragment.get("image_url")
                if isinstance(image_data, dict):
                    url_value = image_data.get("url")
                    if isinstance(url_value, str) and url_value.strip():
                        image_fragments.append(deep_copy_jsonable(fragment))
            else:
                other_fragments.append(fragment)

        tool_payload = deep_copy_jsonable(message)

        tool_text_parts: list[str] = []
        if text_fragments:
            joined = "\n".join(text_fragments).strip()
            if joined:
                tool_text_parts.append(joined)
        if other_fragments:
            for fragment in other_fragments:
                try:
                    tool_text_parts.append(json.dumps(fragment))
                except (TypeError, ValueError):
                    tool_text_parts.append(str(fragment))
        if not tool_text_parts and image_fragments:
            tool_text_parts.append("Tool returned image attachment(s).")

        # Include GCS URLs in tool message text so LLM can reference them
        # Images will be injected into assistant response via pending_tool_attachments
        if image_fragments:
            url_lines: list[str] = []
            for fragment in image_fragments:
                image_block = fragment.get("image_url") or {}
                url_value = image_block.get("url")
                metadata_block = fragment.get("metadata", {})
                filename = metadata_block.get("filename", "image") if isinstance(metadata_block, dict) else "image"
                if isinstance(url_value, str) and url_value.strip():
                    url_lines.append(f"Image URL: {url_value}")
            if url_lines:
                tool_text_parts.extend(url_lines)

        tool_payload["content"] = "\n".join(tool_text_parts)
        prepared.append(tool_payload)

    return prepared


def deep_copy_jsonable(value: Any) -> Any:
    """Best-effort deep copy for JSON-serialisable structures."""

    try:
        return deepcopy(value)
    except Exception:  # pragma: no cover - defensive fallback
        if isinstance(value, dict):
            return {deep_copy_jsonable(k): deep_copy_jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [deep_copy_jsonable(item) for item in value]
        return value


__all__ = [
    "deep_copy_jsonable",
    "parse_attachment_references",
    "prepare_messages_for_model",
]

