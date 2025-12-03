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
    monkeypatch.setenv("REQUIRE_APPROVAL", "false")
    monkeypatch.delenv("SUDO_PASSWORD", raising=False)
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
    command = "python -c \"import sys; sys.exit(42)\""
    result = json.loads(await shell_control_server.shell_execute(command))

    assert result["exit_code"] == 42


async def test_shell_execute_timeout() -> None:
    command = "python -c \"import time; time.sleep(10)\""
    result = json.loads(
        await shell_control_server.shell_execute(command, timeout_seconds=1)
    )

    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"]


async def test_shell_execute_approval_gate(log_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_APPROVAL", "true")

    result = json.loads(await shell_control_server.shell_execute("echo test"))

    assert result["status"] == "awaiting_confirmation"
    assert "log_id" not in result
    assert list(log_dir.iterdir()) == []


async def test_shell_execute_approval_confirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_APPROVAL", "true")

    result = json.loads(await shell_control_server.shell_execute("echo ok", confirm=True))

    assert result["stdout"].strip() == "ok"
    assert result["exit_code"] == 0


async def test_shell_execute_yolo_mode() -> None:
    result = json.loads(await shell_control_server.shell_execute("echo free", confirm=False))

    assert result["stdout"].strip() == "free"
    assert result["exit_code"] == 0


async def test_shell_execute_truncation() -> None:
    payload = "A" * 60000
    command = f"python -c \"print('{payload}')\""

    result = json.loads(await shell_control_server.shell_execute(command))

    assert result["truncated"] is True
    assert len(result["stdout"].encode("utf-8")) <= shell_control_server.OUTPUT_TRUNCATE_BYTES
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


async def test_shell_execute_sudo_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUDO_PASSWORD", "sekret")
    calls: dict[str, object] = {}

    class DummyProcess:
        def __init__(self) -> None:
            self.returncode = 0
            self.inputs: list[bytes | None] = []

        async def communicate(self, input: bytes | None = None):
            self.inputs.append(input)
            return b"done", b""

        def kill(self) -> None:
            calls["killed"] = True

    async def fake_subprocess(command: str, *args, **kwargs):
        calls["command"] = command
        proc = DummyProcess()
        calls["process"] = proc
        return proc

    monkeypatch.setattr(shell_control_server.asyncio, "create_subprocess_shell", fake_subprocess)

    result = json.loads(await shell_control_server.shell_execute("sudo echo ok"))

    assert result["exit_code"] == 0
    assert "sudo -S echo ok" in str(calls["command"])
    proc = calls["process"]
    assert isinstance(proc, DummyProcess)
    assert proc.inputs and proc.inputs[0] == b"sekret\n"


async def test_shell_execute_working_directory(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()

    result = json.loads(
        await shell_control_server.shell_execute("pwd", working_directory=str(workdir))
    )

    assert result["stdout"].strip() == str(workdir)
    assert result["exit_code"] == 0


def test_get_host_id_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOST_PROFILE_ID", raising=False)

    assert shell_control_server._get_host_id() == "local"


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


def test_state_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST_PROFILE_ID", "demo")
    payload = {"ts": "now", "ok": True}

    shell_control_server._save_state(payload)

    assert shell_control_server._load_state() == payload


def test_load_state_missing_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST_PROFILE_ID", "demo")

    assert shell_control_server._load_state() == {}
