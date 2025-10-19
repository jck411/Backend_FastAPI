"""Utilities for uploading files to Google Cloud Storage."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google.cloud import storage
from google.oauth2 import service_account


logger = logging.getLogger(__name__)


class GCSUploadError(RuntimeError):
    """Raised when a Google Cloud Storage operation fails."""


@dataclass(slots=True)
class GCSUploadResult:
    """Metadata returned after uploading a blob to GCS."""

    blob_name: str
    public_url: str


class GCSUploader:
    """Upload helper that manages a Google Cloud Storage client."""

    def __init__(
        self,
        bucket_name: str,
        *,
        project_id: Optional[str] = None,
        credentials_file: Optional[Path] = None,
        public_url_template: str | None = None,
    ) -> None:
        if not bucket_name:
            raise ValueError("bucket_name is required for GCSUploader")

        self._bucket_name = bucket_name
        self._project_id = project_id
        self._credentials_file = credentials_file
        self._public_url_template = public_url_template
        self._client: storage.Client | None = None

    def _get_client(self) -> storage.Client:
        if self._client is not None:
            return self._client

        credentials = None
        if self._credentials_file is not None:
            logger.info(
                "Initializing Google Cloud Storage client with service account file %s",
                self._credentials_file,
            )
            credentials = service_account.Credentials.from_service_account_file(
                str(self._credentials_file)
            )

        try:
            client = storage.Client(project=self._project_id, credentials=credentials)
        except Exception as exc:  # pragma: no cover - google client init errors
            raise GCSUploadError(f"Failed to create GCS client: {exc}") from exc

        self._client = client
        return client

    def upload_file(
        self,
        *,
        file_path: Path,
        blob_name: str,
        content_type: str,
        cache_control: str | None = None,
    ) -> GCSUploadResult:
        """Upload a file to the configured bucket and return its public URL."""

        client = self._get_client()

        try:
            bucket = client.bucket(self._bucket_name)
        except Exception as exc:  # pragma: no cover - google client errors
            raise GCSUploadError(f"Failed to access GCS bucket {self._bucket_name}: {exc}") from exc

        blob = bucket.blob(blob_name)
        try:
            blob.upload_from_filename(
                filename=str(file_path), content_type=content_type
            )
            if cache_control:
                blob.cache_control = cache_control
                blob.patch()
            blob.make_public()
        except Exception as exc:
            raise GCSUploadError(
                f"Failed to upload {file_path} to GCS bucket {self._bucket_name}: {exc}"
            ) from exc

        if self._public_url_template:
            public_url = self._public_url_template.format(
                bucket=self._bucket_name,
                blob=blob.name,
            )
        else:
            public_url = blob.public_url

        return GCSUploadResult(blob_name=blob.name, public_url=public_url)


__all__ = ["GCSUploader", "GCSUploadError", "GCSUploadResult"]

