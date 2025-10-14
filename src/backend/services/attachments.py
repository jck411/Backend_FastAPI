"""Attachment storage and metadata management."""

from __future__ import annotations

import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from starlette.datastructures import URL
from starlette.requests import Request

from ..repository import AttachmentRecord, ChatRepository

logger = logging.getLogger(__name__)


ALLOWED_ATTACHMENT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "application/pdf",
    }
)


class AttachmentError(RuntimeError):
    """Base error raised for attachment failures."""


class UnsupportedAttachmentType(AttachmentError):
    """Raised when an unsupported file type is uploaded."""


class AttachmentTooLarge(AttachmentError):
    """Raised when an uploaded file exceeds the configured limit."""


class AttachmentNotFound(AttachmentError):
    """Raised when an attachment record or file cannot be located."""


@dataclass(slots=True)
class StoredAttachment:
    """Metadata describing a stored attachment."""

    record: AttachmentRecord
    path: Path


class AttachmentService:
    """Persist attachment binaries and metadata for chat sessions."""

    def __init__(
        self,
        repository: ChatRepository,
        base_dir: Path,
        *,
        max_size_bytes: int,
        retention_days: int,
        public_base_url: str | None = None,
    ) -> None:
        self._repo = repository
        self._base_dir = base_dir
        self._max_size_bytes = max_size_bytes
        self._retention = timedelta(days=retention_days)
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        *,
        session_id: str,
        upload: UploadFile,
        request: Request,
    ) -> AttachmentRecord:
        """Validate, persist, and register an uploaded attachment."""

        if not session_id:
            raise AttachmentError("session_id is required")

        mime_type = (upload.content_type or "").lower()
        if mime_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
            raise UnsupportedAttachmentType(mime_type or "unknown")

        extension = self._pick_extension(upload.filename, mime_type)
        attachment_id = uuid4().hex
        relative_dir = Path(session_id)
        relative_path = relative_dir / f"{attachment_id}{extension}"
        absolute_path = (self._base_dir / relative_path).resolve()

        base_dir_resolved = self._base_dir.resolve()
        if (
            base_dir_resolved not in absolute_path.parents
            and absolute_path != base_dir_resolved
        ):
            raise AttachmentError("Resolved attachment path escaped storage directory")

        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            size_bytes = await self._write_file(upload, absolute_path)
        except AttachmentTooLarge:
            try:
                absolute_path.unlink()
            except FileNotFoundError:
                pass
            raise
        if size_bytes <= 0:
            raise AttachmentError("Uploaded file was empty")

        await self._repo.ensure_session(session_id)

        original_url = str(
            request.url_for("download_attachment", attachment_id=attachment_id)
        )
        delivery_url = self._apply_public_base(original_url)
        now = datetime.now(timezone.utc)
        expires_at = (
            now + self._retention if self._retention.total_seconds() > 0 else None
        )
        metadata: dict[str, Any] = {}
        if upload.filename:
            metadata["filename"] = upload.filename
        metadata["mime_type"] = mime_type
        metadata["size_bytes"] = size_bytes

        record = await self._repo.add_attachment(
            attachment_id=attachment_id,
            session_id=session_id,
            storage_path=os.fspath(relative_path),
            mime_type=mime_type,
            size_bytes=size_bytes,
            display_url=original_url,
            delivery_url=delivery_url,
            metadata=metadata or None,
            expires_at=expires_at,
        )

        logger.info(
            "Stored attachment %s (%s, %d bytes) for session %s",
            attachment_id,
            mime_type,
            size_bytes,
            session_id,
        )
        return record

    def _apply_public_base(self, url: str) -> str:
        if not self._public_base_url:
            return url

        parsed = URL(url)
        external = f"{self._public_base_url}{parsed.path}"
        if parsed.query:
            external = (
                f"{external}?{parsed.query}"  # pragma: no cover - future proofing
            )
        return external

    async def resolve(self, attachment_id: str) -> StoredAttachment:
        """Return metadata and filesystem path for an attachment."""

        record = await self._repo.get_attachment(attachment_id)
        if record is None:
            raise AttachmentNotFound(attachment_id)

        storage_path = record.get("storage_path")
        if not storage_path:
            raise AttachmentError("Attachment missing storage path")
        absolute_path = (self._base_dir / storage_path).resolve()
        base_dir_resolved = self._base_dir.resolve()
        if (
            base_dir_resolved not in absolute_path.parents
            and absolute_path != base_dir_resolved
        ):
            raise AttachmentError("Attachment path escaped storage directory")
        if not absolute_path.exists():
            raise AttachmentNotFound(attachment_id)
        return StoredAttachment(record=record, path=absolute_path)

    async def touch(self, attachment_ids: list[str], *, session_id: str) -> None:
        """Mark attachments as referenced in a conversation turn."""

        if not attachment_ids:
            return
        await self._repo.mark_attachments_used(session_id, attachment_ids)

    async def delete(self, attachment_id: str) -> bool:
        """Remove attachment metadata and file from storage."""

        record = await self._repo.get_attachment(attachment_id)
        deleted = await self._repo.delete_attachment(attachment_id)
        if deleted and record and record.get("storage_path"):
            try:
                (self._base_dir / record["storage_path"]).unlink(missing_ok=True)
            except Exception:  # pragma: no cover - best-effort cleanup
                logger.warning(
                    "Failed to remove attachment file %s", attachment_id, exc_info=True
                )
        return deleted

    async def _write_file(self, upload: UploadFile, destination: Path) -> int:
        chunk_size = 1024 * 1024  # 1 MiB
        size = 0
        try:
            with destination.open("wb") as buffer:
                while True:
                    chunk = await upload.read(chunk_size)
                    if not chunk:
                        break
                    buffer.write(chunk)
                    size += len(chunk)
                    if size > self._max_size_bytes:
                        raise AttachmentTooLarge(
                            f"Attachment exceeded {self._max_size_bytes} bytes limit"
                        )
        finally:
            await upload.close()
        return size

    def _pick_extension(self, filename: str | None, mime_type: str) -> str:
        if filename:
            ext = Path(filename).suffix
            if ext:
                return ext

        # Handle common mime types explicitly for more consistent extensions
        if mime_type == "application/pdf":
            return ".pdf"

        guessed = mimetypes.guess_extension(mime_type)
        return guessed or ""


__all__ = [
    "AttachmentService",
    "AttachmentError",
    "UnsupportedAttachmentType",
    "AttachmentTooLarge",
    "AttachmentNotFound",
    "StoredAttachment",
]
