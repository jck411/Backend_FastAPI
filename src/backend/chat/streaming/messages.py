"""Helpers for preparing chat messages for model consumption."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, MutableMapping, Sequence


def parse_attachment_references(text: str) -> tuple[str, list[str]]:
    """Extract inline attachment references from tool output text."""

    if "attachment_id:" not in text:
        return text, []

    attachment_ids: list[str] = []
    lines: list[str] = []

    for line in text.split("\n"):
        if line.strip().startswith("attachment_id:"):
            attachment_id = line.strip().split(":", 1)[1].strip()
            if attachment_id:
                attachment_ids.append(attachment_id)
        else:
            lines.append(line)

    cleaned_text = "\n".join(lines).strip()
    return cleaned_text, attachment_ids


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

        tool_payload["content"] = "\n".join(tool_text_parts)
        prepared.append(tool_payload)

        if not image_fragments:
            continue

        synthetic_content: list[dict[str, Any]] = []
        description = (
            "Image retrieved from tool result for analysis."
            if len(image_fragments) == 1
            else "Images retrieved from tool result for analysis."
        )
        synthetic_content.append({"type": "text", "text": description})

        for fragment in image_fragments:
            image_block = fragment.get("image_url") or {}
            url_value = image_block.get("url")
            if not isinstance(url_value, str) or not url_value:
                continue
            synthetic_fragment: dict[str, Any] = {
                "type": "image_url",
                "image_url": {"url": url_value},
            }
            metadata_block = fragment.get("metadata")
            if isinstance(metadata_block, dict):
                synthetic_fragment["metadata"] = metadata_block
            synthetic_content.append(synthetic_fragment)

        if len(synthetic_content) <= 1:
            continue

        synthetic_message: dict[str, Any] = {
            "role": "user",
            "content": synthetic_content,
        }

        metadata: dict[str, Any] = {"source": "tool_attachment_proxy"}
        tool_call_id = message.get("tool_call_id")
        tool_name = message.get("tool_name")
        if isinstance(tool_call_id, str) and tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        if isinstance(tool_name, str) and tool_name:
            metadata["tool_name"] = tool_name
        if metadata:
            synthetic_message["metadata"] = metadata

        prepared.append(synthetic_message)

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

