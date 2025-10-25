"""Tests for backend image reflection heuristics."""

from __future__ import annotations

from src.backend.chat.image_reflection import reflect_assistant_images


def _assistant_message(urls: list[str]) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": [
            {"type": "image_url", "image_url": {"url": url}} for url in urls
        ],
    }


def _user_message(content: object) -> dict[str, object]:
    return {
        "role": "user",
        "content": content,
    }


def test_reflects_single_image_reference() -> None:
    conversation = [
        _assistant_message(["https://example.test/a.png"]),
        _user_message("What color is it?"),
    ]

    reflected = reflect_assistant_images(conversation)
    user_content = reflected[-1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert user_content[0]["text"] == "What color is it?"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"] == "https://example.test/a.png"


def test_reflects_multiple_images_when_plural_reference() -> None:
    conversation = [
        _assistant_message(
            [
                "https://example.test/a.png",
                "https://example.test/b.png",
                "https://example.test/c.png",
            ]
        ),
        _user_message("Can you compare the last two images?"),
    ]

    reflected = reflect_assistant_images(conversation)
    user_content = reflected[-1]["content"]
    assert isinstance(user_content, list)
    urls = [
        fragment["image_url"]["url"]
        for fragment in user_content
        if fragment["type"] == "image_url"
    ]
    assert urls == ["https://example.test/b.png", "https://example.test/c.png"]


def test_no_reflection_without_available_images() -> None:
    conversation = [
        {"role": "assistant", "content": "I did not make an image."},
        _user_message("What color is it?"),
    ]

    reflected = reflect_assistant_images(conversation)
    user_content = reflected[-1]["content"]
    assert isinstance(user_content, str)
    assert user_content == "What color is it?"


def test_tokens_removed_even_when_no_images_attached() -> None:
    conversation = [
        {"role": "assistant", "content": "No images just yet."},
        _user_message("@last Could you resend it?"),
    ]

    reflected = reflect_assistant_images(conversation)
    user_content = reflected[-1]["content"]
    assert isinstance(user_content, str)
    assert user_content == "Could you resend it?"
