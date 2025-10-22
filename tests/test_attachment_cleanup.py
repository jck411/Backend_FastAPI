from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.attachments_cleanup import cleanup_expired_attachments
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
async def test_cleanup_expired_attachments(repository: ChatRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)

    stale = await repository.add_attachment(
        attachment_id="expired-1",
        session_id="session-1",
        storage_path="session-1/expired-1__file.png",
        mime_type="image/png",
        size_bytes=10,
        display_url="https://example.com/expired",
        delivery_url="https://example.com/expired",
        gcs_blob="session-1/expired-1__file.png",
        signed_url="https://example.com/expired",
        signed_url_expires_at=now - timedelta(days=1),
        expires_at=now - timedelta(days=1),
    )

    await repository.add_attachment(
        attachment_id="active-1",
        session_id="session-1",
        storage_path="session-1/active-1__file.png",
        mime_type="image/png",
        size_bytes=10,
        display_url="https://example.com/active",
        delivery_url="https://example.com/active",
        gcs_blob="session-1/active-1__file.png",
        signed_url="https://example.com/active",
        signed_url_expires_at=now + timedelta(days=1),
        expires_at=now + timedelta(days=1),
    )

    deleted_blobs: list[str] = []

    def fake_delete(blob_name: str) -> None:
        deleted_blobs.append(blob_name)

    monkeypatch.setattr(
        "backend.services.attachments_cleanup.delete_blob",
        fake_delete,
    )

    removed = await cleanup_expired_attachments(
        repository,
        now=now,
    )

    assert removed == 1
    assert stale["gcs_blob"] in deleted_blobs
    assert await repository.get_attachment("expired-1") is None
    assert await repository.get_attachment("active-1") is not None
