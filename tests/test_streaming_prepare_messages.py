from __future__ import annotations

import copy

from src.backend.chat.streaming import _prepare_messages_for_model


def test_prepare_messages_for_model_injects_image_proxy_message() -> None:
    conversation = [
        {"role": "user", "content": "Please analyze my file."},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "gdrive_analyze_image", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "tool_name": "gdrive_analyze_image",
            "content": [
                {"type": "text", "text": "[Image from Google Drive: sample.jpg]"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/signed-url.png"},
                    "metadata": {"attachment_id": "att-123"},
                },
            ],
        },
    ]

    snapshot = copy.deepcopy(conversation)

    prepared = _prepare_messages_for_model(conversation)

    assert conversation == snapshot  # Original conversation is untouched.
    assert len(prepared) == 4  # Synthetic user message appended.

    tool_payload = prepared[2]
    assert tool_payload["role"] == "tool"
    assert isinstance(tool_payload["content"], str)
    assert "sample.jpg" in tool_payload["content"]

    proxy_message = prepared[3]
    assert proxy_message["role"] == "user"
    assert isinstance(proxy_message.get("content"), list)
    assert proxy_message["content"][0]["type"] == "text"
    assert proxy_message["content"][1]["type"] == "image_url"
    assert (
        proxy_message["content"][1]["image_url"]["url"]
        == "https://example.com/signed-url.png"
    )
    assert proxy_message["metadata"]["tool_call_id"] == "call_123"
    assert proxy_message["metadata"]["source"] == "tool_attachment_proxy"


def test_prepare_messages_for_model_passes_plain_tool_message() -> None:
    conversation = [
        {
            "role": "tool",
            "tool_call_id": "call_plain",
            "content": "Plain text result",
        }
    ]

    prepared = _prepare_messages_for_model(conversation)

    assert len(prepared) == 1
    assert prepared[0]["role"] == "tool"
    assert prepared[0]["content"] == "Plain text result"
