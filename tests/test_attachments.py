"""Attachment service tests covering PDF support."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import Headers, UploadFile

from backend.services.attachments import AttachmentService


class DummyRequest:
    def url_for(self, name: str, **kwargs: str) -> str:  # pragma: no cover - simple stub
        return f"http://example.test/{name}/{kwargs.get('attachment_id', '')}"


@pytest.mark.asyncio
async def test_attachment_service_accepts_pdf(tmp_path: Path) -> None:
    repository = MagicMock()
    repository.ensure_session = AsyncMock()
    repository.add_attachment = AsyncMock(
        return_value={"storage_path": "session1/fake.pdf"}
    )
    repository.mark_attachments_used = AsyncMock()

    storage_dir = tmp_path / "attachments"

    service = AttachmentService(
        repository=repository,
        base_dir=storage_dir,
        max_size_bytes=10 * 1024 * 1024,
        retention_days=7,
    )

    upload = UploadFile(
        filename="report.pdf",
        file=io.BytesIO(b"%PDF-1.4 sample content"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    result = await service.save_upload(
        session_id="session1",
        upload=upload,
        request=DummyRequest(),
    )

    assert result is repository.add_attachment.return_value
    repository.ensure_session.assert_awaited_once_with("session1")

    call_kwargs = repository.add_attachment.call_args.kwargs
    assert call_kwargs["mime_type"] == "application/pdf"
    assert call_kwargs["size_bytes"] == len(b"%PDF-1.4 sample content")
    assert call_kwargs["delivery_url"] == call_kwargs["display_url"]

    stored_relative = Path(call_kwargs["storage_path"])
    assert stored_relative.as_posix().startswith("session1/")
    assert stored_relative.name.endswith("__report.pdf")
    assert (storage_dir / stored_relative).exists()
