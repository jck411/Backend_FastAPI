"""Tests for the Kreuzberg-backed PDF MCP server."""

from __future__ import annotations

import pytest

pytest.importorskip("kreuzberg")

from backend.mcp_servers import pdf_server
from pathlib import Path
import base64
import os

import pytest


@pytest.mark.asyncio
async def test_extract_document_uses_uploads_dir_for_local_file(tmp_path, monkeypatch):
    # Arrange uploads directory with a sample PDF-like file
    uploads = tmp_path / "data" / "uploads" / "sub"
    uploads.mkdir(parents=True)
    sample = uploads / "sample.pdf"
    payload = b"%PDF-1.4 minimal"
    sample.write_bytes(payload)

    # Ensure the PDF server resolves attachments to our temp uploads dir
    monkeypatch.setattr(pdf_server, "_resolve_attachments_dir", lambda: uploads.parent)

    called = {"extract_bytes": 0, "extract_document": 0}

    # Patch kreuzberg to ensure we go through extract_bytes (local read path)
    from kreuzberg._mcp import server as kreuzberg_server

    def fake_extract_bytes(content_base64: str, mime_type: str, *args, **kwargs):
        called["extract_bytes"] += 1
        assert mime_type == "application/pdf"
        assert base64.b64decode(content_base64) == payload
        return {"content": "ok"}

    def fail_extract_document(*args, **kwargs):
        called["extract_document"] += 1
        raise AssertionError("Should not delegate to extract_document for uploads")

    monkeypatch.setattr(kreuzberg_server, "extract_bytes", fake_extract_bytes)
    monkeypatch.setattr(kreuzberg_server, "extract_document", fail_extract_document)

    # Act: absolute path inside uploads
    result_abs = await pdf_server.extract_document_urlaware(str(sample))

    # Act: relative path inside uploads should also resolve
    os.chdir(tmp_path)  # guard: ensure CWD changes don't affect our logic
    result_rel = await pdf_server.extract_document_urlaware("sub/sample.pdf")

    # Assert
    assert result_abs == {"content": "ok"}
    assert result_rel == {"content": "ok"}
    assert called["extract_bytes"] == 2


@pytest.mark.asyncio
async def test_list_and_search_upload_paths(tmp_path, monkeypatch):
    uploads = tmp_path / "data" / "uploads"
    (uploads / "a").mkdir(parents=True)
    (uploads / "b").mkdir(parents=True)
    f1 = uploads / "a" / "doc1.pdf"
    f2 = uploads / "a" / "notes.txt"
    f3 = uploads / "b" / "report-final.PDF"
    f1.write_bytes(b"%PDF-1.4 f1")
    f2.write_text("hello")
    f3.write_bytes(b"%PDF-1.4 f3")

    monkeypatch.setattr(pdf_server, "_resolve_attachments_dir", lambda: uploads)

    # List all files
    items = await pdf_server.list_upload_paths()
    names = {item["relative_path"] for item in items if item.get("type") == "file"}
    assert "a/doc1.pdf" in names
    assert "a/notes.txt" in names
    assert "b/report-final.PDF" in names

    # Pattern filter (glob)
    pdfs = await pdf_server.list_upload_paths(pattern="**/*.pdf")
    pdf_names = {item["relative_path"] for item in pdfs}
    # Should include lower-case .pdf and upper-case .PDF due to glob case-sensitivity behavior
    assert "a/doc1.pdf" in pdf_names
    # Depending on OS, glob may be case-sensitive; ensure search finds it
    found_search = await pdf_server.search_upload_paths("report-final", max_results=10)
    assert any("report-final" in item["relative_path"] for item in found_search)

    # Enrichment with DB metadata (original filename)
    # Point the repo DB to a temp file and register one of the files
    monkeypatch.setattr(
        pdf_server, "_resolve_chat_db_path", lambda: tmp_path / "chat.db"
    )
    # Reset repository singleton to ensure it re-initializes
    pdf_server._repository = None  # type: ignore[attr-defined]
    repo = await pdf_server._get_repository()
    # Ensure session and add matching attachment record for a/doc1.pdf
    await repo.ensure_session("a")
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    await repo.add_attachment(
        attachment_id="abc123",
        session_id="a",
        storage_path="a/doc1.pdf",
        mime_type="application/pdf",
        size_bytes=f1.stat().st_size,
        display_url="http://localhost:8000/api/uploads/abc123/content",
        delivery_url="http://localhost:8000/api/uploads/abc123/content",
        metadata={"filename": "Original Name.pdf"},
        expires_at=now,
    )

    enriched = await pdf_server.list_upload_paths()
    match = next((it for it in enriched if it.get("relative_path") == "a/doc1.pdf"), None)
    assert match is not None
    assert match.get("original_filename") == "Original Name.pdf"
    assert match.get("name") == "Original Name.pdf"


def test_pdf_server_reuses_kreuzberg_mcp():
    from kreuzberg._mcp import server as kreuzberg_server

    assert pdf_server.mcp is kreuzberg_server.mcp


def test_pdf_server_run_delegates_to_kreuzberg(monkeypatch):
    from kreuzberg._mcp import server as kreuzberg_server

    invoked = {"count": 0}

    def fake_main() -> None:
        invoked["count"] += 1

    monkeypatch.setattr(kreuzberg_server, "main", fake_main)

    pdf_server.run()

    assert invoked["count"] == 1


def test_pdf_server_re_exports_tool_functions():
    from kreuzberg._mcp import server as kreuzberg_server

    for attr in (
        "extract_document",
        "extract_bytes",
        "batch_extract_bytes",
        "batch_extract_document",
        "extract_simple",
    ):
        assert getattr(pdf_server, attr) is getattr(kreuzberg_server, attr)
