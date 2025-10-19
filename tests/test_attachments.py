"""Attachment service tests covering PDF support."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
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

    stored_relative = Path(call_kwargs["storage_path"])
    assert stored_relative.as_posix().startswith("session1/")
    assert stored_relative.name.endswith("__report.pdf")
    assert (storage_dir / stored_relative).exists()


@pytest.mark.asyncio
async def test_upload_to_gdrive_uploads_and_caches(monkeypatch, tmp_path: Path) -> None:
    data = b"\x89PNG\r\n\x1a\n" + b"0" * 128
    attachments_dir = tmp_path / "attachments"
    file_path = attachments_dir / "session1" / "att-1.png"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(data)

    record = {
        "attachment_id": "att-1",
        "session_id": "session1",
        "storage_path": "session1/att-1.png",
        "mime_type": "image/png",
        "size_bytes": len(data),
        "display_url": "http://example/uploads/att-1",
        "delivery_url": "http://example/uploads/att-1",
        "metadata": {"filename": "att-1.png"},
        "created_at": "2024-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": "2024-01-01T00:00:00",
        "gdrive_file_id": None,
        "gdrive_public_url": None,
        "gdrive_uploaded_at": None,
    }

    repository = MagicMock()
    repository.get_attachment = AsyncMock(return_value=record)
    repository.update_attachment_drive_metadata = AsyncMock()

    service = AttachmentService(
        repository=repository,
        base_dir=attachments_dir,
        max_size_bytes=10 * 1024 * 1024,
        retention_days=7,
    )

    state = {"public": False, "file_id": "drive-file"}

    class DummyService:
        def __init__(self) -> None:
            self.create_calls = 0
            self.permission_calls = 0

        def files(self):
            service = self

            class Files:
                def create(self_inner, body=None, **kwargs):
                    def execute():
                        service.create_calls += 1
                        state["file_id"] = "drive-file"
                        state["public"] = False
                        return {"id": state["file_id"], "name": body.get("name")}

                    return SimpleNamespace(execute=execute)

                def get(self_inner, **kwargs):
                    def execute():
                        permissions = []
                        if state["public"]:
                            permissions = [{"type": "anyone", "role": "reader"}]
                        return {
                            "id": state["file_id"],
                            "name": "image.png",
                            "mimeType": "image/png",
                            "permissions": permissions,
                            "shared": state["public"],
                        }

                    return SimpleNamespace(execute=execute)

            return Files()

        def permissions(self):
            service = self

            class Permissions:
                def create(self_inner, **kwargs):
                    def execute():
                        service.permission_calls += 1
                        state["public"] = True
                        return {"id": "perm-1"}

                    return SimpleNamespace(execute=execute)

            return Permissions()

    dummy_service = DummyService()

    monkeypatch.setattr(
        "backend.services.attachments.get_drive_service", lambda *_: dummy_service
    )

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "backend.services.attachments.asyncio.to_thread", fake_to_thread
    )

    url = await service.upload_to_gdrive("att-1", user_email="user@example.com")

    assert url == "https://drive.google.com/uc?export=view&id=drive-file"
    assert dummy_service.create_calls == 1
    assert dummy_service.permission_calls == 1
    repository.update_attachment_drive_metadata.assert_awaited_once()
