from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.backend.repository import ChatRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def repository(tmp_path):
    repo = ChatRepository(tmp_path / "chat.db")
    await repo.initialize()
    await repo.ensure_session("session-1")
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.anyio
async def test_structured_content_roundtrip(repository):
    payload = [{"type": "text", "text": "hello"}]
    metadata = {"foo": "bar"}

    await repository.add_message(
        "session-1",
        role="user",
        content=payload,
        metadata=dict(metadata),
    )

    messages = await repository.get_messages("session-1")

    assert len(messages) == 1
    message = messages[0]

    assert message["content"] == payload
    assert message["foo"] == "bar"
    assert metadata == {"foo": "bar"}


@pytest.mark.anyio
async def test_string_content_preserved(repository):
    await repository.add_message(
        "session-1",
        role="assistant",
        content="plain text",
    )

    messages = await repository.get_messages("session-1")

    assert messages[0]["content"] == "plain text"


@pytest.mark.anyio
async def test_attachment_roundtrip(repository):
    record = await repository.add_attachment(
        attachment_id="att-1",
        session_id="session-1",
        storage_path="session-1/image.png",
        mime_type="image/png",
        size_bytes=128,
        display_url="https://example.com/uploads/att-1",
        delivery_url="https://example.com/uploads/att-1",
        metadata={"filename": "image.png"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    fetched = await repository.get_attachment("att-1")

    assert fetched is not None
    assert fetched["attachment_id"] == "att-1"
    assert fetched["session_id"] == "session-1"
    assert fetched["mime_type"] == "image/png"
    assert fetched["size_bytes"] == 128
    assert fetched["metadata"]["filename"] == "image.png"
    assert fetched["gdrive_file_id"] is None
    assert fetched["gdrive_public_url"] is None
    assert fetched["gdrive_uploaded_at"] is None

    uploaded_at = datetime.now(timezone.utc)
    await repository.update_attachment_drive_metadata(
        "att-1",
        file_id="drive-file-123",
        public_url="https://drive.google.com/uc?export=view&id=drive-file-123",
        uploaded_at=uploaded_at,
    )
    updated = await repository.get_attachment("att-1")
    assert updated["gdrive_file_id"] == "drive-file-123"
    assert updated["gdrive_public_url"].endswith("drive-file-123")
    assert updated["gdrive_uploaded_at"].startswith(uploaded_at.isoformat()[:19])

    # Add a small delay to ensure timestamp difference
    import asyncio

    await asyncio.sleep(1.1)  # SQLite CURRENT_TIMESTAMP has 1-second resolution

    await repository.mark_attachments_used("session-1", ["att-1"])
    refreshed = await repository.get_attachment("att-1")
    assert refreshed is not None
    assert refreshed["last_used_at"] != record["last_used_at"]

    removed = await repository.delete_attachment("att-1")
    assert removed is True
    assert await repository.get_attachment("att-1") is None


@pytest.mark.anyio
async def test_message_timestamp_details(repository):
    await repository.add_message("session-1", role="user", content="hello")

    messages = await repository.get_messages("session-1")

    assert messages, "expected at least one message"
    message = messages[0]

    created_at = message.get("created_at")
    created_at_utc = message.get("created_at_utc")
    assert isinstance(created_at, str)
    assert isinstance(created_at_utc, str)
    assert created_at.endswith(("-04:00", "-05:00"))
    assert created_at_utc.endswith("+00:00")
