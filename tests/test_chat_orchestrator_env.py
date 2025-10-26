"""Tests for environment handling within the chat orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.chat import orchestrator


def test_build_mcp_base_env_reads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("NOTION_TOKEN=from_file\nNOTION_API_KEY=fallback\n", encoding="utf-8")

    env = orchestrator._build_mcp_base_env(tmp_path)

    assert env["NOTION_TOKEN"] == "from_file"
    assert env["NOTION_API_KEY"] == "fallback"


def test_build_mcp_base_env_prefers_process_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "process-value")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("NOTION_TOKEN=from_file\n", encoding="utf-8")

    env = orchestrator._build_mcp_base_env(tmp_path)

    assert env["NOTION_TOKEN"] == "process-value"
