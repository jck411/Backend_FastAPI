from __future__ import annotations

from src.backend.schemas.chat import ChatCompletionRequest, ChatMessage


def test_chat_message_string_content():
    message = ChatMessage(role="user", content="hello world")
    assert message.content == "hello world"


def test_chat_message_multimodal_content():
    content = [
        {"type": "text", "text": "Describe this scene"},
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/image.png"},
        },
    ]
    message = ChatMessage(role="user", content=content)
    assert isinstance(message.content, list)
    assert message.content == content


def test_chat_completion_request_multimodal_payload():
    message = ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "What's in this image?"},
            {
                "type": "image_url",
                "image_url": {"url": "https://example.com/pic.jpg"},
            },
        ],
    )
    request = ChatCompletionRequest(messages=[message])

    payload = request.to_openrouter_payload("default-model")

    assert payload["model"] == "default-model"
    assert isinstance(payload["messages"][0]["content"], list)
