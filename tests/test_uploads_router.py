from __future__ import annotations

import io
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.backend.app import create_app
from src.backend.config import get_settings


@pytest.fixture
def upload_client(monkeypatch, tmp_path) -> Generator[TestClient, None, None]:
    """Fixture providing a test client for upload endpoints."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_DATABASE_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MODEL_SETTINGS_PATH", str(tmp_path / "model_settings.json"))
    monkeypatch.setenv("MCP_SERVERS_PATH", str(tmp_path / "mcp_servers.json"))
    monkeypatch.setenv("ATTACHMENTS_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()

    # Disable default MCP servers to prevent them from starting
    mcp_file = tmp_path / "mcp_servers.json"
    mcp_file.write_text("""{
        "servers": [
            {"id": "local-calculator", "module": "backend.mcp_servers.calculator_server", "enabled": false},
            {"id": "housekeeping", "module": "backend.mcp_servers.housekeeping_server", "enabled": false}
        ]
    }""")

    app = create_app()

    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


def _tiny_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_upload_and_download_image(upload_client: TestClient, tmp_path: Path) -> None:
    response = upload_client.post(
        "/api/uploads",
        data={"session_id": "session-test"},
        files={"file": ("pixel.png", _tiny_png(), "image/png")},
    )

    assert response.status_code == 201
    payload = response.json()
    attachment = payload["attachment"]

    assert attachment["mimeType"] == "image/png"
    assert attachment["sessionId"] == "session-test"
    assert attachment["displayUrl"].startswith("http://testserver/api/uploads/")

    download = upload_client.get(f"/api/uploads/{attachment['id']}/content")
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert download.content == _tiny_png()

    # Ensure file was persisted to the configured uploads directory
    uploads_dir = tmp_path / "uploads" / "session-test"
    stored_files = list(uploads_dir.glob("*"))
    assert stored_files, "expected uploaded file on disk"


def test_upload_rejects_unsupported_type(upload_client: TestClient) -> None:
    response = upload_client.post(
        "/api/uploads",
        data={"session_id": "session-test"},
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 415
    body = response.json()
    assert "Unsupported attachment type" in body["detail"]
