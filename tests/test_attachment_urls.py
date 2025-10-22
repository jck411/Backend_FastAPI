from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services import attachment_urls
from backend.services.attachment_urls import refresh_message_attachments
from src.backend.repository import ChatRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def repository(tmp_path):
    repo = ChatRepository(tmp_path / "chat.db")
    await repo.initialize()
    await repo.ensure_session("session-123")
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.anyio
async def test_refresh_message_attachments_resigns_expired_url(
    repository: ChatRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(timezone.utc)
    await repository.add_attachment(
        attachment_id="att-1",
        session_id="session-123",
        storage_path="session-123/att-1__image.png",
        mime_type="image/png",
        size_bytes=64,
        display_url="https://old.example/att-1",
        delivery_url="https://old.example/att-1",
        gcs_blob="session-123/att-1__image.png",
        signed_url="https://old.example/att-1",
        signed_url_expires_at=now - timedelta(minutes=5),
    )
    await repository.add_message(
        "session-123",
        role="user",
        content=[
            {
                "type": "image_url",
                "image_url": {"url": "https://old.example/att-1"},
                "metadata": {"attachment_id": "att-1"},
            }
        ],
    )

    conversation = await repository.get_messages("session-123")
    assert conversation and isinstance(conversation[0].get("content"), list)

    monkeypatch.setattr(
        attachment_urls,
        "sign_get_url",
        lambda blob_name, expires_delta: "https://new.example/att-1",
    )

    await refresh_message_attachments(
        conversation,
        repository,
        ttl=timedelta(days=7),
    )

    fragment = conversation[0]["content"][0]
    assert fragment["image_url"]["url"] == "https://new.example/att-1"
    assert fragment["metadata"]["display_url"] == "https://new.example/att-1"
    assert fragment["metadata"]["delivery_url"] == "https://new.example/att-1"

    updated_record = await repository.get_attachment("att-1")
    assert updated_record is not None
    assert updated_record["signed_url"] == "https://new.example/att-1"
    expires_at = updated_record["signed_url_expires_at"]
    assert isinstance(expires_at, str)
    assert "T" in expires_at


@pytest.mark.anyio
async def test_refresh_message_attachments_skips_when_valid(
    repository: ChatRepository,
) -> None:
    now = datetime.now(timezone.utc)
    ttl = timedelta(days=7)
    awaited_expiry = now + ttl
    await repository.add_attachment(
        attachment_id="att-2",
        session_id="session-123",
        storage_path="session-123/att-2__image.png",
        mime_type="image/png",
        size_bytes=64,
        display_url="https://valid.example/att-2",
        delivery_url="https://valid.example/att-2",
        gcs_blob="session-123/att-2__image.png",
        signed_url="https://valid.example/att-2",
        signed_url_expires_at=awaited_expiry,
    )
    await repository.add_message(
        "session-123",
        role="assistant",
        content=[
            {
                "type": "image_url",
                "image_url": {"url": "https://valid.example/att-2"},
                "metadata": {"attachment_id": "att-2"},
            }
        ],
    )

    conversation = await repository.get_messages("session-123")
    await refresh_message_attachments(
        conversation,
        repository,
        ttl=ttl,
    )

    fragment = conversation[0]["content"][0]
    assert fragment["image_url"]["url"] == "https://valid.example/att-2"
    assert fragment["metadata"]["display_url"] == "https://valid.example/att-2"
    assert fragment["metadata"]["delivery_url"] == "https://valid.example/att-2"
