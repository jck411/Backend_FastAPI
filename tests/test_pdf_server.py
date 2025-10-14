"""Tests for the Kreuzberg-backed PDF MCP server."""

from __future__ import annotations

import pytest

pytest.importorskip("kreuzberg")

from backend.mcp_servers import pdf_server


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
