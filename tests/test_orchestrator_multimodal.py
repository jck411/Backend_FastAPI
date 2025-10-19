from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backend.chat.orchestrator import ChatOrchestrator
from src.backend.config import Settings
from src.backend.services.attachments import AttachmentError


@pytest.fixture
def orchestrator(tmp_path: Path) -> ChatOrchestrator:
    settings = Settings(openrouter_api_key="test-key")
    model_settings = MagicMock()
    mcp_settings = MagicMock()
    return ChatOrchestrator(settings, model_settings, mcp_settings)


@pytest.mark.asyncio
async def test_transform_message_content_uploads(orchestrator: ChatOrchestrator):
    calls: list[str] = []

    class DummyAttachmentService:
        async def get_public_image_url(self, attachment_id: str, **_: object) -> str:
            calls.append(attachment_id)
            return f"https://drive.google.com/uc?export=view&id={attachment_id}"

    orchestrator.set_attachment_service(DummyAttachmentService())

    content = [
        {"type": "text", "text": "Look at this"},
        {
            "type": "image_url",
            "image_url": {"url": "http://local/att-1"},
            "metadata": {"attachment_id": "att-1", "mime_type": "image/png"},
        },
    ]

    transformed = await orchestrator._transform_message_content(content, "session-1")

    assert calls == ["att-1"]
    assert transformed[0]["text"] == "Look at this"
    assert transformed[1]["image_url"]["url"].endswith("att-1")
    assert transformed[1]["metadata"]["attachment_id"] == "att-1"


@pytest.mark.asyncio
async def test_transform_message_content_fallback(orchestrator: ChatOrchestrator):
    service = MagicMock()
    service.get_public_image_url = AsyncMock(side_effect=AttachmentError("failure"))
    orchestrator.set_attachment_service(service)
    orchestrator._inline_base64_image = AsyncMock(  # type: ignore[attr-defined]
        return_value="data:image/png;base64,Zm9v"
    )

    content = [
        {
            "type": "image_url",
            "image_url": {"url": "http://local/att-9"},
            "metadata": {"attachment_id": "att-9", "mime_type": "image/png"},
        }
    ]

    transformed = await orchestrator._transform_message_content(content, "session-2")

    assert transformed[0]["image_url"]["url"].startswith("data:image/png;base64,")
    orchestrator._inline_base64_image.assert_awaited_once_with("att-9")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_inline_base64_image_generates_data_uri(
    orchestrator: ChatOrchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    data = b"\x89PNG\r\n\x1a\n" + b"data"
    file_path = tmp_path / "att.png"
    file_path.write_bytes(data)

    stored = SimpleNamespace(
        record={
            "mime_type": "image/png",
            "size_bytes": len(data),
        },
        path=file_path,
    )

    service = MagicMock()
    service.resolve = AsyncMock(return_value=stored)
    orchestrator.set_attachment_service(service)

    monkeypatch.setattr(
        "src.backend.chat.orchestrator.asyncio.to_thread",
        lambda func, *args, **kwargs: func(*args, **kwargs),
    )

    data_uri = await orchestrator._inline_base64_image("att-inline")

    assert data_uri is not None
    assert data_uri.startswith("data:image/png;base64,")
    payload = data_uri.split(",", 1)[1]
    assert base64.b64decode(payload) == data


@pytest.mark.asyncio
async def test_inline_base64_image_rejects_large_file(
    orchestrator: ChatOrchestrator, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    large_data = b"0" * (2 * 1024 * 1024 + 1)
    file_path = tmp_path / "large.bin"
    file_path.write_bytes(large_data)

    stored = SimpleNamespace(
        record={
            "mime_type": "image/png",
            "size_bytes": len(large_data),
        },
        path=file_path,
    )

    service = MagicMock()
    service.resolve = AsyncMock(return_value=stored)
    orchestrator.set_attachment_service(service)

    monkeypatch.setattr(
        "src.backend.chat.orchestrator.asyncio.to_thread",
        lambda func, *args, **kwargs: func(*args, **kwargs),
    )

    assert await orchestrator._inline_base64_image("too-big") is None
