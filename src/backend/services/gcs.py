"""Helpers for interacting with Google Cloud Storage."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from google.cloud import storage
from google.oauth2 import service_account

from backend.config import get_settings

_client: storage.Client | None = None
_bucket: storage.Bucket | None = None


def _get_settings():
    return get_settings()


def _load_credentials(settings) -> service_account.Credentials | None:
    credentials_path: Path | None = getattr(
        settings, "google_application_credentials", None
    )
    if credentials_path is None:
        return None

    try:
        resolved_path = Path(credentials_path).expanduser().resolve()
    except FileNotFoundError:
        return None

    if not resolved_path.exists():
        return None

    return service_account.Credentials.from_service_account_file(resolved_path)


def get_client() -> storage.Client:
    """Return a cached Storage client."""

    global _client
    if _client is None:
        settings = _get_settings()
        credentials = _load_credentials(settings)
        _client = storage.Client(
            project=settings.gcp_project_id,
            credentials=credentials,
        )
    return _client


def get_bucket() -> storage.Bucket:
    """Return the configured GCS bucket."""

    global _bucket
    if _bucket is None:
        settings = _get_settings()
        _bucket = get_client().bucket(settings.gcs_bucket_name)
    return _bucket


def upload_bytes(blob_name: str, data: bytes, *, content_type: str) -> None:
    """Upload raw bytes to the configured bucket."""

    blob = get_bucket().blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)


def upload_filelike(blob_name: str, file_like: BinaryIO, *, content_type: str) -> None:
    """Upload a file-like object to the configured bucket."""

    blob = get_bucket().blob(blob_name)
    blob.upload_from_file(file_like, content_type=content_type)


def delete_blob(blob_name: str) -> None:
    """Delete a blob if it exists."""

    blob = get_bucket().blob(blob_name)
    blob.delete(if_generation_match=None)


def sign_get_url(blob_name: str, *, expires_delta: timedelta) -> str:
    """Generate a signed GET URL for the given blob."""

    blob = get_bucket().blob(blob_name)
    return blob.generate_signed_url(
        version="v4",
        expiration=expires_delta,
        method="GET",
    )


__all__ = [
    "delete_blob",
    "get_bucket",
    "get_client",
    "sign_get_url",
    "upload_bytes",
    "upload_filelike",
]
