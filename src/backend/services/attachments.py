"""Attachment storage and metadata management."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from starlette.datastructures import URL
from starlette.requests import Request
from googleapiclient.http import MediaIoBaseUpload

from ..mcp_servers.gdrive_helpers import (
    check_public_link_permission,
    format_public_sharing_error,
    get_drive_image_url,
)
from .google_auth.auth import get_drive_service
from ..repository import AttachmentRecord, ChatRepository
from ..utils import build_storage_name
from .gcs import GCSUploadError, GCSUploader

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

    @property
    def gdrive_file_id(self) -> str | None:
        value = self.record.get("gdrive_file_id")
        return value if isinstance(value, str) and value else None

    @property
    def gdrive_public_url(self) -> str | None:
        value = self.record.get("gdrive_public_url")
        return value if isinstance(value, str) and value else None

    @property
    def gdrive_uploaded_at(self) -> datetime | None:
        value = self.record.get("gdrive_uploaded_at")
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @property
    def gcs_blob_name(self) -> str | None:
        value = self.record.get("gcs_blob_name")
        return value if isinstance(value, str) and value else None

    @property
    def gcs_public_url(self) -> str | None:
        value = self.record.get("gcs_public_url")
        return value if isinstance(value, str) and value else None

    @property
    def gcs_uploaded_at(self) -> datetime | None:
        value = self.record.get("gcs_uploaded_at")
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None


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
        gdrive_uploads_folder: str = "root",
        gdrive_default_user_email: str | None = None,
        gcs_bucket_name: str | None = None,
        gcs_project_id: str | None = None,
        gcs_credentials_file: Path | None = None,
        gcs_public_url_template: str | None = None,
    ) -> None:
        self._repo = repository
        self._base_dir = base_dir
        self._max_size_bytes = max_size_bytes
        self._retention = timedelta(days=retention_days)
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._gdrive_folder = gdrive_uploads_folder or "root"
        self._gdrive_default_user_email = gdrive_default_user_email
        self._gcs_bucket_name = gcs_bucket_name
        self._gcs_project_id = gcs_project_id
        self._gcs_credentials_file = gcs_credentials_file
        self._gcs_public_url_template = gcs_public_url_template
        self._gcs_uploader: GCSUploader | None = None
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
        stored_name = build_storage_name(attachment_id, extension, upload.filename)
        relative_path = relative_dir / stored_name
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

    def _ensure_gcs_uploader(self) -> GCSUploader:
        if not self._gcs_bucket_name:
            raise AttachmentError("Google Cloud Storage bucket is not configured")

        if self._gcs_uploader is None:
            self._gcs_uploader = GCSUploader(
                self._gcs_bucket_name,
                project_id=self._gcs_project_id,
                credentials_file=self._gcs_credentials_file,
                public_url_template=self._gcs_public_url_template,
            )
        return self._gcs_uploader

    async def get_public_image_url(
        self, attachment_id: str, *, force: bool = False
    ) -> str:
        """Return a public URL for an image attachment using configured storage."""

        if self._gcs_bucket_name:
            return await self.upload_to_gcs(attachment_id, force=force)

        return await self.upload_to_gdrive(attachment_id, force=force)

    async def upload_to_gdrive(
        self,
        attachment_id: str,
        *,
        user_email: str | None = None,
        force: bool = False,
    ) -> str:
        """Upload an attachment to Google Drive and return the public URL."""

        stored = await self.resolve(attachment_id)
        record = stored.record

        mime_type = str(record.get("mime_type") or "")
        if not mime_type.startswith("image/"):
            raise AttachmentError(
                f"Attachment {attachment_id} is not an image (mime={mime_type})"
            )

        resolved_user = user_email or self._gdrive_default_user_email
        if not resolved_user:
            raise AttachmentError(
                "Google Drive user email required; configure gdrive_default_user_email"
            )

        try:
            service = get_drive_service(resolved_user)
        except ValueError as exc:
            raise AttachmentError(str(exc)) from exc
        except Exception as exc:
            raise AttachmentError(
                f"Failed to initialize Google Drive service: {exc}"
            ) from exc

        file_id = record.get("gdrive_file_id")
        public_url = record.get("gdrive_public_url")

        if file_id and not force:
            try:
                await self._ensure_drive_public(service, file_id)
            except AttachmentError as exc:
                logger.info(
                    "Drive metadata for attachment %s is stale: %s. Re-uploading.",
                    attachment_id,
                    exc,
                )
            else:
                if public_url:
                    return public_url
                url = get_drive_image_url(file_id)
                await self._repo.update_attachment_drive_metadata(
                    attachment_id,
                    file_id=file_id,
                    public_url=url,
                )
                return url

        metadata = record.get("metadata")
        attachment_name = None
        if isinstance(metadata, dict):
            filename = metadata.get("filename")
            if isinstance(filename, str) and filename.strip():
                attachment_name = filename.strip()
        if not attachment_name:
            attachment_name = stored.path.name

        try:
            data = await asyncio.to_thread(stored.path.read_bytes)
        except Exception as exc:
            raise AttachmentError(
                f"Failed to read attachment file {stored.path}: {exc}"
            ) from exc

        media = MediaIoBaseUpload(BytesIO(data), mimetype=mime_type, resumable=False)
        file_metadata: dict[str, Any] = {
            "name": attachment_name,
            "mimeType": mime_type,
        }
        if self._gdrive_folder and self._gdrive_folder != "root":
            file_metadata["parents"] = [self._gdrive_folder]

        try:
            created = await asyncio.to_thread(
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name",
                    supportsAllDrives=True,
                )
                .execute
            )
        except Exception as exc:
            raise AttachmentError(
                f"Failed to upload attachment {attachment_id} to Google Drive: {exc}"
            ) from exc

        drive_file_id = created.get("id")
        if not isinstance(drive_file_id, str) or not drive_file_id:
            raise AttachmentError(
                f"Google Drive upload for attachment {attachment_id} returned no file ID"
            )

        metadata = await self._ensure_drive_public(
            service,
            drive_file_id,
            file_name=created.get("name"),
        )

        public_url = get_drive_image_url(drive_file_id)
        uploaded_at = datetime.now(timezone.utc)
        await self._repo.update_attachment_drive_metadata(
            attachment_id,
            file_id=drive_file_id,
            public_url=public_url,
            uploaded_at=uploaded_at,
        )
        logger.info(
            "Uploaded attachment %s to Google Drive as %s",
            attachment_id,
            drive_file_id,
        )
        return public_url

    async def upload_to_gcs(
        self,
        attachment_id: str,
        *,
        force: bool = False,
    ) -> str:
        """Upload an attachment to Google Cloud Storage and return the public URL."""

        if not self._gcs_bucket_name:
            raise AttachmentError("Google Cloud Storage bucket is not configured")

        stored = await self.resolve(attachment_id)
        record = stored.record

        mime_type = str(record.get("mime_type") or "")
        if not mime_type.startswith("image/"):
            raise AttachmentError(
                f"Attachment {attachment_id} is not an image (mime={mime_type})"
            )

        existing_blob = record.get("gcs_blob_name")
        existing_url = record.get("gcs_public_url")
        if existing_blob and existing_url and not force:
            return existing_url

        uploader = self._ensure_gcs_uploader()

        metadata = record.get("metadata")
        attachment_name = None
        if isinstance(metadata, dict):
            filename = metadata.get("filename")
            if isinstance(filename, str) and filename.strip():
                attachment_name = filename.strip()
        if not attachment_name:
            attachment_name = stored.path.name

        blob_name = existing_blob or os.fspath(record.get("storage_path") or attachment_name)
        cache_control = "public, max-age=31536000, immutable"

        try:
            data = await asyncio.to_thread(
                uploader.upload_file,
                file_path=stored.path,
                blob_name=blob_name,
                content_type=mime_type,
                cache_control=cache_control,
            )
        except GCSUploadError as exc:
            raise AttachmentError(str(exc)) from exc

        now = datetime.now(timezone.utc)
        await self._repo.update_attachment_gcs_metadata(
            attachment_id,
            blob_name=data.blob_name,
            public_url=data.public_url,
            uploaded_at=now,
        )

        return data.public_url

    async def _ensure_drive_public(
        self,
        service: Any,
        file_id: str,
        *,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Ensure the Drive file has public access and return metadata."""

        try:
            metadata = await asyncio.to_thread(
                service.files()
                .get(
                    fileId=file_id,
                    fields=(
                        "id, name, permissions, webViewLink, webContentLink, shared, trashed"
                    ),
                    supportsAllDrives=True,
                )
                .execute
            )
        except Exception as exc:  # pragma: no cover - network/Drive errors
            raise AttachmentError(
                f"Failed to retrieve Drive metadata for {file_id}: {exc}"
            ) from exc

        if metadata.get("trashed"):
            name = metadata.get("name", file_name or "(unknown)")
            raise AttachmentError(
                f"Google Drive file '{name}' (ID: {file_id}) is in trash; remove metadata to retry."
            )

        permissions = metadata.get("permissions", [])
        if not check_public_link_permission(permissions):
            try:
                await asyncio.to_thread(
                    service.permissions()
                    .create(
                        fileId=file_id,
                        body={
                            "type": "anyone",
                            "role": "reader",
                            "allowFileDiscovery": False,
                        },
                        fields="id",
                        sendNotificationEmail=False,
                        supportsAllDrives=True,
                    )
                    .execute
                )
            except Exception as exc:  # pragma: no cover - network/Drive errors
                name = metadata.get("name", file_name or "(unknown)")
                raise AttachmentError(
                    f"Unable to enable public access for '{name}' (ID: {file_id}): {exc}"
                ) from exc

            try:
                metadata = await asyncio.to_thread(
                    service.files()
                    .get(
                        fileId=file_id,
                        fields=(
                            "id, name, permissions, webViewLink, webContentLink, shared"
                        ),
                        supportsAllDrives=True,
                    )
                    .execute
                )
            except Exception as exc:  # pragma: no cover - network/Drive errors
                raise AttachmentError(
                    f"Failed to confirm public access for file {file_id}: {exc}"
                ) from exc

            permissions = metadata.get("permissions", [])

        if not check_public_link_permission(permissions):
            name = metadata.get("name", file_name or "(unknown)")
            raise AttachmentError(format_public_sharing_error(name, file_id))

        return metadata

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
