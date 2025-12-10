"""Tests for the shell_control MCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.mcp_servers import shell_control_server

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "logs" / "shell"
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(shell_control_server, "_get_log_dir", lambda: path)
    return path


@pytest.fixture(autouse=True)
def host_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "host"
    path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(shell_control_server, "_get_host_root", lambda: path)
    return path


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOST_PROFILE_ID", raising=False)


async def test_shell_execute_simple_command(log_dir: Path) -> None:
    result = json.loads(await shell_control_server.shell_execute("echo hello"))

    assert result["stdout"].strip() == "hello"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0
    assert (log_dir / f"{result['log_id']}.json").exists()


async def test_shell_execute_with_stderr() -> None:
    command = "python -c \"import sys; sys.stderr.write('oops\\n')\""
    result = json.loads(await shell_control_server.shell_execute(command))

    assert "oops" in result["stderr"]
    assert result["exit_code"] == 0


async def test_shell_execute_exit_code() -> None:
    command = 'python -c "import sys; sys.exit(42)"'
    result = json.loads(await shell_control_server.shell_execute(command))

    assert result["exit_code"] == 42


async def test_shell_execute_timeout() -> None:
    command = 'python -c "import time; time.sleep(10)"'
    result = json.loads(
        await shell_control_server.shell_execute(command, timeout_seconds=1)
    )

    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"]


async def test_shell_execute_truncation() -> None:
    payload = "A" * 60000
    command = f"python -c \"print('{payload}')\""

    result = json.loads(await shell_control_server.shell_execute(command))

    assert result["truncated"] is True
    assert (
        len(result["stdout"].encode("utf-8")) <= shell_control_server.OUTPUT_TAIL_BYTES
    )
    assert result["log_id"]


async def test_shell_get_full_output(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = "B" * 70000
    command = f"python -c \"print('{payload}')\""

    execute_result = json.loads(await shell_control_server.shell_execute(command))

    full = json.loads(
        await shell_control_server.shell_get_full_output(execute_result["log_id"])
    )

    assert full["log_id"] == execute_result["log_id"]
    assert full["truncated"] is True
    assert len(full["stdout"]) == len(payload) + 1  # account for newline
    assert full["stdout"].startswith("B" * 10)


async def test_shell_execute_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()

    result = json.loads(
        await shell_control_server.shell_execute("pwd", working_directory=str(workdir))
    )

    assert result["stdout"].strip() == str(workdir)
    assert result["exit_code"] == 0


def test_get_host_id_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOST_PROFILE_ID", raising=False)

    with pytest.raises(RuntimeError, match="HOST_PROFILE_ID"):
        shell_control_server._get_host_id()


def test_load_profile_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST_PROFILE_ID", "xps13")

    with pytest.raises(FileNotFoundError):
        shell_control_server._load_profile()


def test_load_profile_success(host_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST_PROFILE_ID", "xps13")
    profile = {"meta": {"host_id": "xps13"}, "intent": {}}

    profile_path = shell_control_server._get_profile_path()
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    loaded = shell_control_server._load_profile()

    assert loaded == profile


async def test_host_id_validation_prevents_path_traversal() -> None:
    """Test that invalid host_id values are rejected to prevent path traversal."""
    invalid_ids = [
        "../../../etc",
        "..%2F..%2Fetc",
        "host/../other",
        "/etc/passwd",
        "host with spaces",
        "host.with.dots",
    ]

    for invalid_id in invalid_ids:
        with pytest.raises(ValueError, match="Invalid host_id"):
            shell_control_server._get_host_dir(invalid_id)


async def test_host_id_validation_allows_valid_ids(host_root: Path) -> None:
    """Test that valid host_id values are accepted."""
    valid_ids = ["xps13", "ryzen-desktop", "my_laptop", "Host123", "a-b_c"]

    for valid_id in valid_ids:
        # Should not raise
        result = shell_control_server._get_host_dir(valid_id)
        assert result.name == valid_id
        assert result.exists()


async def test_host_get_profile_missing_host_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that host_get_profile returns error when HOST_PROFILE_ID is missing."""
    monkeypatch.delenv("HOST_PROFILE_ID", raising=False)

    result = json.loads(await shell_control_server.host_get_profile())

    assert result["status"] == "error"
    assert result["host_id"] == "unknown"
    assert "HOST_PROFILE_ID" in result["message"]


async def test_host_update_profile_adds_timestamp(
    host_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that host_update_profile adds updated_at timestamp."""
    monkeypatch.setenv("HOST_PROFILE_ID", "test-host")

    # Create initial profile
    profile_path = host_root / "test-host" / "profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text('{"hostname": "test"}', encoding="utf-8")

    # Update profile
    result = json.loads(
        await shell_control_server.host_update_profile(
            {"notes": {"test": "value"}}, reason="test update"
        )
    )

    assert result["status"] == "ok"

    # Verify timestamp was added
    updated_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert "updated_at" in updated_profile
    # Verify format is ISO 8601
    assert updated_profile["updated_at"].endswith("Z")
    assert "T" in updated_profile["updated_at"]
