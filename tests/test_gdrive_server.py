"""Tests for the Google Drive MCP server."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.mcp_servers.gdrive_server import (
    auth_status,
    copy_drive_file,
    create_drive_folder,
    get_drive_file_content,
    download_drive_file,
    delete_drive_file,
    generate_auth_url,
    list_drive_items,
    move_drive_file,
    rename_drive_file,
    search_drive_files,
)


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.get_credentials")
async def test_auth_status_authorized(mock_get_credentials):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials

    result = await auth_status("user@example.com")

    assert "already authorized" in result
    mock_get_credentials.assert_called_once_with("user@example.com")


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.get_credentials")
async def test_auth_status_missing(mock_get_credentials):
    mock_get_credentials.return_value = None

    result = await auth_status("user@example.com")

    assert "No stored Google Drive credentials" in result
    mock_get_credentials.assert_called_once_with("user@example.com")


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.authorize_user")
@patch("backend.mcp_servers.gdrive_server.get_credentials")
async def test_generate_auth_url_existing_credentials(
    mock_get_credentials, mock_authorize_user
):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials

    result = await generate_auth_url("user@example.com")

    assert "already has stored credentials" in result
    mock_authorize_user.assert_not_called()


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.authorize_user")
@patch("backend.mcp_servers.gdrive_server.get_credentials")
async def test_generate_auth_url_force_flow(mock_get_credentials, mock_authorize_user):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials
    mock_authorize_user.return_value = "https://auth.example.com"

    result = await generate_auth_url(
        "user@example.com", redirect_uri="https://app.example.com/callback", force=True
    )

    assert "https://auth.example.com" in result
    mock_authorize_user.assert_called_once()


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_search_drive_files_auth_error(mock_get_drive_service):
    mock_get_drive_service.side_effect = ValueError("Missing credentials")

    result = await search_drive_files("important doc")

    assert "Authentication error" in result
    assert "Missing credentials" in result


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_list_drive_items_resolves_folder_name(
    mock_get_drive_service, mock_to_thread
):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    folder_list_call = MagicMock()
    folder_list_call.execute.return_value = {
        "files": [
            {
                "id": "FOLDER123",
                "name": "bps",
                "mimeType": "application/vnd.google-apps.folder",
            }
        ]
    }
    content_list_call = MagicMock()
    content_list_call.execute.return_value = {
        "files": [
            {
                "id": "file1",
                "name": "notes.txt",
                "mimeType": "text/plain",
                "modifiedTime": "2024-05-01T00:00:00.000Z",
                "webViewLink": "https://drive.example/doc",
            }
        ]
    }
    files_api.list.side_effect = [folder_list_call, content_list_call]

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await list_drive_items(
        folder_id="",
        folder_name="bps",
        user_email="user@example.com",
    )

    assert "Found 1 items in folder 'bps'" in result
    assert "notes.txt" in result
    assert files_api.list.call_count == 2


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server._download_request_bytes", new_callable=AsyncMock)
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_download_drive_file_returns_base64(
    mock_get_service, mock_to_thread, mock_download_bytes
):
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.get.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report.pdf",
        "mimeType": "application/pdf",
        "size": "2048",
        "webViewLink": "https://drive.example/report",
        "modifiedTime": "2024-05-01T00:00:00.000Z",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread
    mock_download_bytes.return_value = b"%PDF-1.4"

    result = await download_drive_file("file123", user_email="user@example.com")

    assert result["file_id"] == "file123"
    assert result["download_mime_type"] == "application/pdf"
    assert result["exported"] is False
    assert result["size_bytes"] == len(b"%PDF-1.4")
    assert result["content_base64"] == base64.b64encode(b"%PDF-1.4").decode("ascii")
    mock_download_bytes.assert_awaited_once()


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_delete_drive_file_moves_to_trash(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.get.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report",
    }
    files_api.update.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report",
        "trashed": True,
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await delete_drive_file("file123", user_email="user@example.com")

    assert "moved to trash" in result
    files_api.update.assert_called_once()
    kwargs = files_api.update.call_args.kwargs
    assert kwargs["fileId"] == "file123"
    assert kwargs["body"] == {"trashed": True}


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_delete_drive_file_permanent(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.get.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await delete_drive_file(
        "file123", user_email="user@example.com", permanent=True
    )

    assert "permanently deleted" in result
    files_api.delete.assert_called_once_with(fileId="file123", supportsAllDrives=True)
    files_api.update.assert_not_called()


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_move_drive_file(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.get.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report",
        "parents": ["oldParent"],
    }
    files_api.update.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report",
        "parents": ["newParent"],
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await move_drive_file(
        "file123", destination_folder_id="newParent", user_email="user@example.com"
    )

    assert "moved to folder 'newParent'" in result
    kwargs = mock_service.files.return_value.update.call_args.kwargs
    assert kwargs["addParents"] == "newParent"
    assert kwargs["removeParents"] == "oldParent"


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_copy_drive_file(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.copy.return_value.execute.return_value = {
        "id": "copy456",
        "name": "Report Copy",
        "webViewLink": "https://drive.example/link",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await copy_drive_file(
        "file123",
        user_email="user@example.com",
        new_name="Report Copy",
        destination_folder_id="destFolder",
    )

    assert "Created copy 'Report Copy'" in result
    files_api.copy.assert_called_once()
    kwargs = files_api.copy.call_args.kwargs
    assert kwargs["fileId"] == "file123"
    assert kwargs["body"] == {"name": "Report Copy", "parents": ["destFolder"]}


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_rename_drive_file(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.update.return_value.execute.return_value = {
        "id": "file123",
        "name": "New Name",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await rename_drive_file(
        "file123", new_name="New Name", user_email="user@example.com"
    )

    assert "renamed to 'New Name'" in result
    files_api.update.assert_called_once()
    kwargs = files_api.update.call_args.kwargs
    assert kwargs["body"] == {"name": "New Name"}


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.kb_extract_bytes")
@patch("backend.mcp_servers.gdrive_server._download_request_bytes", new_callable=AsyncMock)
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_get_file_content_pdf_uses_extractor(
    mock_get_service, mock_to_thread, mock_download_bytes, mock_extract
):
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.get.return_value.execute.return_value = {
        "id": "file123",
        "name": "Report.pdf",
        "mimeType": "application/pdf",
        "webViewLink": "https://drive.example/report",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread
    mock_download_bytes.return_value = b"%PDF-1.4...mockpdfbytes"
    mock_extract.return_value = {"content": "Hello world from PDF"}

    result = await get_drive_file_content("file123", user_email="user@example.com")

    assert "Report.pdf" in result
    assert "Hello world from PDF" in result
    mock_extract.assert_called_once()


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_create_drive_folder(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.create.return_value.execute.return_value = {
        "id": "folder789",
        "name": "Project",
        "webViewLink": "https://drive.example/folder",
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await create_drive_folder(
        "Project", parent_folder_id="rootFolder", user_email="user@example.com"
    )

    assert "Created folder 'Project'" in result
    files_api.create.assert_called_once()
    kwargs = files_api.create.call_args.kwargs
    assert kwargs["body"]["name"] == "Project"
    assert kwargs["body"]["parents"] == ["rootFolder"]
