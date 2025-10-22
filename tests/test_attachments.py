"""Attachment service tests covering PDF support."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import backend.services.attachments as attachments
from backend.services.attachments import AttachmentService


@pytest.mark.asyncio
async def test_attachment_service_uploads_to_gcs(monkeypatch) -> None:
    repository = MagicMock()
    repository.ensure_session = AsyncMock()
    repository.add_attachment = AsyncMock(
        return_value={
            "attachment_id": "abc123",
            "session_id": "session1",
            "mime_type": "application/pdf",
            "size_bytes": 25,
            "display_url": "https://signed",
            "delivery_url": "https://signed",
            "signed_url": "https://signed",
            "signed_url_expires_at": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-08T00:00:00Z",
            "metadata": {"filename": "report.pdf"},
        }
    )
    repository.mark_attachments_used = AsyncMock()

    uploaded: dict[str, object] = {}

    def fake_upload_bytes(blob_name: str, data: bytes, *, content_type: str) -> None:
        uploaded["blob_name"] = blob_name
        uploaded["data"] = data
        uploaded["content_type"] = content_type

    monkeypatch.setattr(attachments, "upload_bytes", fake_upload_bytes)
    monkeypatch.setattr(
        attachments,
        "sign_get_url",
        lambda name, expires_delta: "https://signed",
    )
    monkeypatch.setattr(
        attachments,
        "uuid4",
        lambda: SimpleNamespace(hex="abc123"),
    )

    service = AttachmentService(
        repository=repository,
        max_size_bytes=10 * 1024 * 1024,
        retention_days=7,
    )

    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(b"%PDF-1.4 sample content"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    result = await service.save_user_upload(
        session_id="session1",
        upload=upload,
    )

    assert result is repository.add_attachment.return_value
    repository.ensure_session.assert_awaited_once_with("session1")

    call_kwargs = repository.add_attachment.call_args.kwargs
    assert call_kwargs["mime_type"] == "application/pdf"
    assert call_kwargs["size_bytes"] == len(b"%PDF-1.4 sample content")
    assert call_kwargs["delivery_url"] == call_kwargs["display_url"]
    assert call_kwargs["signed_url"] == "https://signed"
    assert call_kwargs["gcs_blob"] == call_kwargs["storage_path"]
    assert call_kwargs["storage_path"].startswith("session1/")
    assert call_kwargs["storage_path"].endswith("__report.pdf")
    assert call_kwargs["metadata"]["filename"] == "report.pdf"
    assert uploaded["blob_name"] == call_kwargs["storage_path"]
    assert uploaded["data"] == b"%PDF-1.4 sample content"
    assert uploaded["content_type"] == "application/pdf"


@pytest.mark.asyncio
async def test_save_bytes_persists_attachment(monkeypatch) -> None:
    repository = MagicMock()
    repository.ensure_session = AsyncMock()
    repository.add_attachment = AsyncMock(
        return_value={
            "attachment_id": "xyz",
            "session_id": "session1",
            "mime_type": "text/plain",
            "size_bytes": 5,
            "display_url": "https://signed",
            "delivery_url": "https://signed",
            "signed_url": "https://signed",
            "signed_url_expires_at": "2024-01-01T00:00:00Z",
            "metadata": {"filename": "note.txt"},
        }
    )

    monkeypatch.setattr(
        attachments,
        "upload_bytes",
        lambda blob_name, data, content_type: None,
    )
    monkeypatch.setattr(
        attachments,
        "sign_get_url",
        lambda name, expires_delta: "https://signed",
    )
    monkeypatch.setattr(attachments, "uuid4", lambda: SimpleNamespace(hex="xyz"))

    service = AttachmentService(
        repository=repository,
        max_size_bytes=1024,
        retention_days=7,
    )

    result = await service.save_bytes(
        session_id="session1",
        data=b"hello",
        mime_type="text/plain",
        filename_hint="note.txt",
    )

    assert result is repository.add_attachment.return_value
    repository.ensure_session.assert_awaited_once_with("session1")
    call_kwargs = repository.add_attachment.call_args.kwargs
    assert call_kwargs["mime_type"] == "text/plain"
    assert call_kwargs["size_bytes"] == 5
    assert call_kwargs["metadata"]["filename"] == "note.txt"
