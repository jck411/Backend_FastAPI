"""Tests for the Gmail MCP server."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.mcp_servers.gmail_server as gmail_module
import backend.services.gmail_download_simple as gmail_download_simple
from backend.mcp_servers.gmail_server import (
    search_gmail_messages,
)


@pytest.mark.asyncio
async def test_download_attachment_stores_via_service(monkeypatch):
    service_stub = MagicMock()
    monkeypatch.setattr(
        gmail_module,
        "get_gmail_service",
        lambda user_email: service_stub,
    )

    data = {
        "filename": "sample.txt",
        "mime_type": "text/plain",
        "content_bytes": b"hello",
        "size_bytes": 5,
    }
    monkeypatch.setattr(
        gmail_module,
        "fetch_gmail_attachment_data",
        AsyncMock(return_value=data),
    )

    record = {
        "attachment_id": "att-1",
        "mime_type": "text/plain",
        "size_bytes": 5,
        "signed_url": "https://signed",
        "metadata": {"filename": "sample.txt"},
        "expires_at": "2024-01-01T00:00:00Z",
    }
    attachment_service = MagicMock()
    attachment_service.save_bytes = AsyncMock(return_value=record)
    monkeypatch.setattr(
        gmail_module,
        "_get_attachment_service",
        AsyncMock(return_value=attachment_service),
    )

    result = await gmail_module.download_gmail_attachment(
        message_id="msg-1",
        attachment_id="att-1",
        session_id="session-1",
        user_email="user@example.com",
    )

    attachment_service.save_bytes.assert_awaited_once_with(
        session_id="session-1",
        data=b"hello",
        mime_type="text/plain",
        filename_hint="sample.txt",
    )
    assert "Attachment stored" in result
    assert "Signed URL" in result


@patch("backend.mcp_servers.gmail_server.get_gmail_service")
@pytest.mark.asyncio
async def test_search_gmail_messages_auth_error(mock_get_gmail_service):
    mock_get_gmail_service.side_effect = ValueError("Missing credentials")

    result = await search_gmail_messages("from:someone@example.com")

    assert "Authentication error" in result
    assert "Missing credentials" in result
    assert "Connect Google Services" in result


@pytest.mark.asyncio
async def test_download_attachment_preserves_filename(tmp_path):
    data = b"%PDF-1.4 attachment content"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": [
                {
                    "filename": "Invoice.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-123", "size": len(data)},
                }
            ]
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    info = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-1",
        attachment_id="att-123",
        save_dir=tmp_path,
    )

    stored_path = Path(info["absolute_path"])
    assert stored_path.exists()
    assert stored_path.parent == tmp_path
    assert stored_path.name == "Invoice.pdf"
    assert stored_path.read_bytes() == data
    assert info["filename"] == "Invoice.pdf"


@pytest.mark.asyncio
async def test_download_attachment_generates_unique_name(tmp_path):
    data = b"binary payload"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": [
                {
                    "filename": "",
                    "mimeType": "application/octet-stream",
                    "body": {"attachmentId": "att-123", "size": len(data)},
                },
                {
                    "filename": "",
                    "mimeType": "application/octet-stream",
                    "body": {"attachmentId": "att-456", "size": len(data)},
                },
            ]
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    first = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-1",
        attachment_id="att-123",
        save_dir=tmp_path,
    )
    second = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-1",
        attachment_id="att-456",
        save_dir=tmp_path,
    )

    assert Path(first["absolute_path"]).name == "attachment.bin"
    assert Path(second["absolute_path"]).name == "attachment-1.bin"


@pytest.mark.asyncio
async def test_download_attachment_discards_hashed_name(tmp_path):
    data = b"payload"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": [
                {
                    "filename": "4e31a91b92c24fe3a533ed113c811a0e__file.bin",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-999", "size": len(data)},
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": (
                                "attachment;"
                                " filename*=UTF-8''Pain%20Equianalgesic%20Table.pdf"
                            ),
                        }
                    ],
                }
            ]
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    info = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-4",
        attachment_id="att-999",
        save_dir=tmp_path,
    )

    saved_name = Path(info["absolute_path"]).name
    assert saved_name == "Pain Equianalgesic Table.pdf"


@pytest.mark.asyncio
async def test_download_attachment_uses_header_filename(tmp_path):
    data = b"payload"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": [
                {
                    "filename": "",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-789", "size": len(data)},
                    "headers": [
                        {"name": "Content-Disposition", "value": 'attachment; filename="file.pdf"'}
                    ],
                }
            ]
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    info = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-2",
        attachment_id="att-789",
        save_dir=tmp_path,
    )

    saved_name = Path(info["absolute_path"]).name
    assert saved_name == "file.pdf"


@pytest.mark.asyncio
async def test_download_attachment_parses_combined_headers(tmp_path):
    data = b"payload"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": [
                {
                    "filename": "",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "att-111", "size": len(data)},
                    "headers": [
                        {
                            "name": "Content-Type",
                            "value": (
                                "application/pdf;"
                                " name*0*=UTF-8''5070%20Electrolyte%20"
                                "name*1*=infusions.pdf"
                            ),
                        },
                        {
                            "name": "Content-Disposition",
                            "value": (
                                "attachment;"
                                " filename*0*=UTF-8''5070%20Electrolyte%20"
                                "filename*1*=infusions.pdf"
                            ),
                        },
                    ],
                }
            ]
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    info = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-3",
        attachment_id="att-111",
        save_dir=tmp_path,
    )

    saved_name = Path(info["absolute_path"]).name
    assert saved_name == "5070 Electrolyte infusions.pdf"


@pytest.mark.asyncio
async def test_download_attachment_handles_missing_part(tmp_path):
    data = b"payload"
    encoded = base64.urlsafe_b64encode(data).decode("ascii")

    message_payload = {
        "payload": {
            "parts": []
        }
    }

    service = MagicMock()
    users_api = service.users.return_value
    messages_api = users_api.messages.return_value
    attachments_api = messages_api.attachments.return_value

    messages_api.get.return_value.execute.return_value = message_payload
    attachments_api.get.return_value.execute.return_value = {"data": encoded}

    info = await gmail_download_simple.download_gmail_attachment(
        service,
        message_id="msg-5",
        attachment_id="att-missing",
        save_dir=tmp_path,
    )

    saved_path = Path(info["absolute_path"])
    assert saved_path.exists()
    assert saved_path.name == "attachment.bin"
    assert saved_path.read_bytes() == data
