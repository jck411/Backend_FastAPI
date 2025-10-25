"""Utilities for reflecting assistant-generated images into user messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

RECENT_ASSISTANT_IMAGE_LIMIT = 5

_WORD_NUMBERS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "couple": 2,
    "pair": 2,
    "both": 2,
}


@dataclass(frozen=True, slots=True)
class ImageReflectionIntent:
    """Intent extracted from a user message about prior assistant images."""

    should_attach: bool
    cleaned_text: str
    requested_count: int | None
    plural: bool
    attach_all: bool


def _normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_number_token(token: str) -> int | None:
    if token in _WORD_NUMBERS:
        return _WORD_NUMBERS[token]
    if token.isdigit():
        return int(token)
    return None


def detect_image_reflection_intent(text: str) -> ImageReflectionIntent:
    """Detect whether a user message references recently generated images."""

    if not text:
        return ImageReflectionIntent(False, "", None, False, False)

    cleaned = text
    requested_count: int | None = None
    attach_all = False

    def _replace_lastall(match: re.Match[str]) -> str:
        nonlocal attach_all
        attach_all = True
        return ""

    cleaned = re.sub(r"@lastall", _replace_lastall, cleaned, flags=re.IGNORECASE)

    def _replace_last(match: re.Match[str]) -> str:
        nonlocal requested_count
        digits = match.group(1)
        value = 1
        if digits:
            parsed = _parse_number_token(digits)
            if parsed and parsed > 0:
                value = parsed
        requested_count = max(requested_count or 0, value)
        return ""

    cleaned = re.sub(r"@last(\d+)?", _replace_last, cleaned, flags=re.IGNORECASE)
    cleaned = _normalise_whitespace(cleaned)

    lower = cleaned.lower()

    last_count_match = re.search(
        r"\b(last|previous|past)\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
        lower,
    )
    if last_count_match:
        token = last_count_match.group(2)
        parsed = _parse_number_token(token)
        if parsed:
            requested_count = max(requested_count or 0, parsed)

    explicit_count_match = re.search(
        r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\s+(images|pictures|photos|renders|results)\b",
        lower,
    )
    if explicit_count_match:
        token = explicit_count_match.group(1)
        parsed = _parse_number_token(token)
        if parsed:
            requested_count = max(requested_count or 0, parsed)

    if re.search(r"\b(both|couple|pair)\b", lower):
        requested_count = max(requested_count or 0, 2)

    if re.search(
        r"\b(all|every)\s+(?:of\s+)?(?:the\s+)?(image|images|pictures|photos|results)\b",
        lower,
    ):
        attach_all = True

    pronoun_pattern = re.compile(r"\b(it|its|that|this|one)\b")
    image_term_pattern = re.compile(
        r"\b(image|picture|photo|render|artwork|drawing|result|shot)\b"
    )
    last_one_pattern = re.compile(
        r"\b(last|previous)\s+(one|image|picture|photo|result)\b"
    )
    plural_pronoun_pattern = re.compile(r"\b(them|those|these|they)\b")
    plural_image_pattern = re.compile(
        r"\b(images|pictures|photos|renders|drawings|results)\b"
    )
    comparison_pattern = re.compile(
        r"\b(compare|comparison|difference|diff|versus|vs|side by side)\b"
    )

    plural = (
        bool(plural_pronoun_pattern.search(lower))
        or bool(plural_image_pattern.search(lower))
        or bool(comparison_pattern.search(lower))
        or bool(requested_count and requested_count >= 2)
        or attach_all
    )

    should_attach = any(
        (
            attach_all,
            requested_count is not None,
            bool(image_term_pattern.search(lower)),
            bool(last_one_pattern.search(lower)),
            bool(plural_pronoun_pattern.search(lower)),
            bool(plural_image_pattern.search(lower)),
            bool(comparison_pattern.search(lower)),
            bool(pronoun_pattern.search(lower)),
        )
    )

    return ImageReflectionIntent(
        should_attach=should_attach,
        cleaned_text=cleaned,
        requested_count=requested_count,
        plural=plural,
        attach_all=attach_all,
    )


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for fragment in content:
            if (
                isinstance(fragment, dict)
                and fragment.get("type") == "text"
                and isinstance(fragment.get("text"), str)
            ):
                parts.append(fragment["text"])
        return " ".join(parts)
    return ""


def _content_has_images(content: Any) -> bool:
    if not isinstance(content, list):
        return False
    for fragment in content:
        if isinstance(fragment, dict) and fragment.get("type") == "image_url":
            return True
    return False


def _extract_image_urls(content: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(content, list):
        for fragment in content:
            if not isinstance(fragment, dict):
                continue
            if fragment.get("type") != "image_url":
                continue
            image = fragment.get("image_url")
            if isinstance(image, dict):
                url = image.get("url")
                if isinstance(url, str) and url:
                    urls.append(url)
    return urls


def _collect_recent_assistant_images(
    messages: Sequence[dict[str, Any]],
    limit: int,
) -> list[str]:
    collected: list[str] = []
    seen = set[str]()
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for url in _extract_image_urls(message.get("content")):
            if url and url not in seen:
                seen.add(url)
                collected.append(url)
    if len(collected) > limit:
        return collected[-limit:]
    return collected


def _select_image_urls(
    urls: Sequence[str],
    intent: ImageReflectionIntent,
    limit: int,
) -> list[str]:
    if not intent.should_attach or not urls:
        return []
    available = min(len(urls), limit)
    if available == 0:
        return []

    if intent.attach_all:
        count = available
    elif intent.requested_count is not None:
        count = max(1, min(intent.requested_count, available))
    elif intent.plural:
        count = min(2, available)
    else:
        count = min(1, available)

    if count <= 0:
        return []
    return list(urls)[-count:]


def reflect_assistant_images(
    conversation: Sequence[dict[str, Any]],
    *,
    limit: int = RECENT_ASSISTANT_IMAGE_LIMIT,
) -> list[dict[str, Any]]:
    """Inject recent assistant images into the last user message when referenced."""

    if not conversation:
        return list(conversation)

    user_index: int | None = None
    for index in range(len(conversation) - 1, -1, -1):
        if conversation[index].get("role") == "user":
            user_index = index
            break

    if user_index is None:
        return list(conversation)

    user_message = conversation[user_index]
    user_content = user_message.get("content")

    if _content_has_images(user_content):
        return list(conversation)

    user_text = _extract_text_from_content(user_content)
    intent = detect_image_reflection_intent(user_text)

    recent_urls = _collect_recent_assistant_images(conversation[:user_index], limit)
    selected_urls = _select_image_urls(recent_urls, intent, limit)

    cleaned_text = intent.cleaned_text
    text_changed = cleaned_text != user_text

    if not selected_urls and not text_changed:
        return list(conversation)

    updated_message = dict(user_message)

    if selected_urls:
        fragments: list[dict[str, Any]] = []
        if cleaned_text:
            fragments.append({"type": "text", "text": cleaned_text})
        for url in selected_urls:
            fragments.append({"type": "image_url", "image_url": {"url": url}})
        updated_message["content"] = fragments
    elif text_changed:
        if isinstance(user_content, list):
            updated_message["content"] = [{"type": "text", "text": cleaned_text}]
        else:
            updated_message["content"] = cleaned_text

    reflected = list(conversation)
    reflected[user_index] = updated_message
    return reflected


__all__ = [
    "ImageReflectionIntent",
    "RECENT_ASSISTANT_IMAGE_LIMIT",
    "detect_image_reflection_intent",
    "reflect_assistant_images",
]
