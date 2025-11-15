"""Tests for the Google Drive MCP server."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.mcp_servers.gdrive_server import (
    copy_drive_file,
    create_drive_folder,
    get_drive_file_content,
    download_drive_file,
    delete_drive_file,
    list_drive_items,
    move_drive_file,
    rename_drive_file,
    search_drive_files,
    _detect_file_type_query,
)


@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_search_drive_files_auth_error(mock_get_drive_service):
    mock_get_drive_service.side_effect = ValueError("Missing credentials")

    result = await search_drive_files("important doc")
    payload = json.loads(result)

    assert payload["ok"] is False
    assert "Authentication error" in payload["error"]["message"]
    assert "Missing credentials" in payload["error"]["message"]
    assert "Connect Google Services" in payload["error"]["message"]


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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["folder"]["display_label"] == "bps"
    assert payload["data"]["count"] == 1
    assert payload["data"]["items"][0]["name"] == "notes.txt"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["action"] == "trashed"
    assert payload["data"]["file_id"] == "file123"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["action"] == "permanently_deleted"
    assert payload["data"]["file_id"] == "file123"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["destination_folder_id"] == "newParent"
    assert payload["data"]["file_id"] == "file123"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["file"]["name"] == "Report Copy"
    assert payload["data"]["source_file_id"] == "file123"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["file_name"] == "New Name"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["file"]["name"] == "Report.pdf"
    assert "Hello world from PDF" in payload["data"]["content"]
    assert payload["data"]["extraction"]["method"] == "pdf_extractor"
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

    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["folder"]["name"] == "Project"
    assert payload["data"]["folder"]["parents"] == ["rootFolder"]
    files_api.create.assert_called_once()
    kwargs = files_api.create.call_args.kwargs
    assert kwargs["body"]["name"] == "Project"
    assert kwargs["body"]["parents"] == ["rootFolder"]


def test_detect_file_type_images():
    """Test detection of image file type queries."""
    assert _detect_file_type_query("image") == "mimeType contains 'image/'"
    assert _detect_file_type_query("images") == "mimeType contains 'image/'"
    assert _detect_file_type_query("photo") == "mimeType contains 'image/'"
    assert _detect_file_type_query("latest image") == "mimeType contains 'image/'"
    assert _detect_file_type_query("my photos") == "mimeType contains 'image/'"
    assert _detect_file_type_query("picture") == "mimeType contains 'image/'"
    assert _detect_file_type_query("jpg") == "mimeType contains 'image/'"
    assert _detect_file_type_query("png") == "mimeType contains 'image/'"


def test_detect_file_type_pdfs():
    """Test detection of PDF file type queries."""
    assert _detect_file_type_query("pdf") == "mimeType = 'application/pdf'"
    assert _detect_file_type_query("pdfs") == "mimeType = 'application/pdf'"
    assert _detect_file_type_query("latest pdf") == "mimeType = 'application/pdf'"


def test_detect_file_type_documents():
    """Test detection of document file type queries."""
    assert _detect_file_type_query("document") == "mimeType = 'application/vnd.google-apps.document'"
    assert _detect_file_type_query("google doc") == "mimeType = 'application/vnd.google-apps.document'"


def test_detect_file_type_spreadsheets():
    """Test detection of spreadsheet file type queries."""
    assert _detect_file_type_query("spreadsheet") == "mimeType = 'application/vnd.google-apps.spreadsheet'"
    assert _detect_file_type_query("sheet") == "mimeType = 'application/vnd.google-apps.spreadsheet'"


def test_detect_file_type_no_match():
    """Test that non-file-type queries return None."""
    assert _detect_file_type_query("budget report") is None
    assert _detect_file_type_query("meeting notes") is None
    assert _detect_file_type_query("project plan") is None


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_search_images_filters_by_mime_type(mock_get_drive_service, mock_to_thread):
    """Test that searching for 'image' filters by image MIME type, not text search."""
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "img123",
                "name": "vacation.jpg",
                "mimeType": "image/jpeg",
                "size": "2048000",
                "modifiedTime": "2025-11-13T12:00:00.000Z",
                "webViewLink": "https://drive.google.com/file/d/img123/view",
            }
        ]
    }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    result = await search_drive_files(query="image", user_email="user@example.com", page_size=10)

    # Verify the Drive API was called with correct MIME type filter
    files_api.list.assert_called_once()
    call_kwargs = files_api.list.call_args.kwargs
    query_param = call_kwargs.get("q")
    
    # The query should filter by image MIME type
    assert "mimeType contains 'image/'" in query_param
    # The query should NOT do a text search for "image"
    assert "name contains 'image'" not in query_param
    
    payload = json.loads(result)
    assert payload["ok"] is True
    assert payload["data"]["files"][0]["name"] == "vacation.jpg"
    assert payload["data"]["files"][0]["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_search_budget_spreadsheet_combines_filters(mock_get_drive_service, mock_to_thread):
    """Test that 'budget spreadsheet' filters by spreadsheet type AND searches for 'budget'."""
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.list.return_value.execute.return_value = {"files": []}

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    await search_drive_files(query="budget spreadsheet", user_email="user@example.com", page_size=10)

    # Verify the query combines MIME type filter with name search
    call_kwargs = files_api.list.call_args.kwargs
    query_param = call_kwargs.get("q")
    
    assert "mimeType = 'application/vnd.google-apps.spreadsheet'" in query_param
    assert "name contains 'budget'" in query_param
    assert " and " in query_param


@pytest.mark.asyncio
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
@patch("backend.mcp_servers.gdrive_server.get_drive_service")
async def test_search_text_file_strips_keywords(mock_get_drive_service, mock_to_thread):
    mock_service = MagicMock()
    mock_get_drive_service.return_value = mock_service

    files_api = mock_service.files.return_value
    files_api.list.return_value.execute.return_value = {"files": []}

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    mock_to_thread.side_effect = fake_to_thread

    await search_drive_files(
        query="latest text file project plan",
        user_email="user@example.com",
        page_size=5,
    )

    call_kwargs = files_api.list.call_args.kwargs
    query_param = call_kwargs.get("q")

    assert "mimeType = 'text/plain'" in query_param
    assert "name contains 'project plan'" in query_param
    assert "text file" not in query_param
