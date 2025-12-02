"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("shell-control")


OUTPUT_TRUNCATE_BYTES = 50 * 1024


def _get_log_dir() -> Path:
    """Return the directory used to store shell execution logs."""

    log_dir = Path(__file__).parents[3] / "logs" / "shell"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _truncate_output(text: str) -> tuple[str, bool]:
    """Truncate stdout/stderr to the configured limit."""

    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= OUTPUT_TRUNCATE_BYTES:
        return text, False

    slice_bytes = encoded[:OUTPUT_TRUNCATE_BYTES]
    return slice_bytes.decode("utf-8", errors="replace"), True


def _build_shell_env() -> dict[str, str]:
    """Build environment for shell commands with complete system PATH."""

    env = os.environ.copy()

    # Start with comprehensive system paths - no limitations
    system_paths = [
        # User paths
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
        # Standard system paths
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/usr/bin",
        "/sbin",
        "/bin",
        # Package manager paths
        "/snap/bin",
        "/var/lib/snapd/snap/bin",
        "/var/lib/flatpak/exports/bin",
        os.path.expanduser("~/.local/share/flatpak/exports/bin"),
        # Optional/third-party paths
        "/opt/bin",
        "/opt/local/bin",
        # Common application-specific paths
        "/opt/brave.com/brave",
        "/opt/google/chrome",
        "/opt/microsoft/msedge",
        "/opt/vivaldi",
        # Games/Steam
        os.path.expanduser("~/.steam/debian-installation/ubuntu12_32"),
        # Language-specific (often have CLI tools)
        os.path.expanduser("~/.cargo/bin"),
        os.path.expanduser("~/.go/bin"),
        os.path.expanduser("~/go/bin"),
        os.path.expanduser("~/.npm-global/bin"),
        os.path.expanduser("~/.yarn/bin"),
        os.path.expanduser("~/.deno/bin"),
        os.path.expanduser("~/.bun/bin"),
        # Ruby
        os.path.expanduser("~/.gem/ruby/*/bin"),
        os.path.expanduser("~/.rbenv/bin"),
        os.path.expanduser("~/.rvm/bin"),
    ]

    current_path = env.get("PATH", "")
    path_parts = current_path.split(":") if current_path else []

    # Add all paths, prioritizing system paths at the end (user paths come first in current)
    for sys_path in system_paths:
        # Handle glob patterns
        if "*" in sys_path:
            import glob

            matched = glob.glob(sys_path)
            for match in matched:
                if match not in path_parts and os.path.isdir(match):
                    path_parts.append(match)
        elif sys_path not in path_parts and os.path.isdir(sys_path):
            path_parts.append(sys_path)

    env["PATH"] = ":".join(path_parts)

    # Ensure DISPLAY is set for GUI apps
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    # Ensure XDG runtime dir for Wayland/desktop integration
    if "XDG_RUNTIME_DIR" not in env:
        uid = os.getuid()
        xdg_runtime = f"/run/user/{uid}"
        if os.path.isdir(xdg_runtime):
            env["XDG_RUNTIME_DIR"] = xdg_runtime

    return env


async def _run_command(
    command: str,
    *,
    working_directory: str | None,
    timeout_seconds: int,
) -> tuple[str, str, int, float]:
    """Execute the shell command and capture results."""

    sudo_password = os.environ.get("SUDO_PASSWORD")
    prepared_command = command
    send_password = False

    stripped = command.lstrip()
    if stripped.startswith("sudo") and sudo_password:
        send_password = True
        rest = stripped[len("sudo") :].lstrip()
        if " -S " not in stripped and not stripped.startswith("sudo -S"):
            stripped = f"sudo -S {rest}".strip()
        prepared_command = (
            f"{command[: len(command) - len(command.lstrip())]}{stripped}"
        )

    shell_env = _build_shell_env()

    start = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_shell(
            prepared_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_directory or None,
            env=shell_env,
        )

        stdin_data = None
        if send_password and sudo_password:
            stdin_data = f"{sudo_password}\n".encode()

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin_data),
                timeout=float(timeout_seconds),
            )
            exit_code = process.returncode if process.returncode is not None else -1
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            exit_code = -1
            if not stderr_bytes:
                stderr_bytes = (
                    f"Process timed out after {timeout_seconds} seconds".encode()
                )

    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - start) * 1000
        message = f"Error executing command: {exc}"
        return "", message, -1, duration_ms

    duration_ms = (time.perf_counter() - start) * 1000

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    return stdout, stderr, exit_code, duration_ms


async def _execute_and_log(
    command: str,
    *,
    working_directory: str | None,
    timeout_seconds: int,
) -> dict[str, object]:
    """Execute a shell command and persist the full output to a log file."""

    stdout, stderr, exit_code, duration_ms = await _run_command(
        command,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
    )

    truncated_stdout, truncated_stdout_flag = _truncate_output(stdout)
    truncated_stderr, truncated_stderr_flag = _truncate_output(stderr)
    truncated = truncated_stdout_flag or truncated_stderr_flag

    # Persist the full (pre-truncated) output for retrieval
    log_id = uuid.uuid4().hex
    log_payload = {
        "log_id": log_id,
        "command": command,
        "working_directory": working_directory,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "timestamp": time.time(),
        "truncated": truncated,
    }

    log_path = _get_log_dir() / f"{log_id}.json"
    log_path.write_text(
        json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "stdout": truncated_stdout,
        "stderr": truncated_stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "truncated": truncated,
        "log_id": log_id,
        "command": command,
        "working_directory": working_directory,
    }


@mcp.tool("shell_execute")  # type: ignore
async def shell_execute(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: int = 30,
    confirm: bool = False,
) -> str:
    """Execute a shell command with optional approval and logging."""

    require_approval = os.environ.get("REQUIRE_APPROVAL", "false").lower() == "true"

    if require_approval and not confirm:
        return json.dumps(
            {
                "status": "awaiting_confirmation",
                "command": command,
                "working_directory": working_directory,
                "message": "Set confirm=True to execute this command",
            }
        )

    result = await _execute_and_log(
        command,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
    )
    return json.dumps(result)


@mcp.tool("shell_get_full_output")  # type: ignore
async def shell_get_full_output(
    log_id: str,
    offset: int = 0,
    limit: int = 100000,
) -> str:
    """Retrieve stored command output by log id with optional chunking."""

    log_path = _get_log_dir() / f"{log_id}.json"
    if not log_path.exists():
        return json.dumps(
            {
                "status": "error",
                "message": f"Log not found for id {log_id}",
                "log_id": log_id,
            }
        )

    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.dumps(
            {
                "status": "error",
                "message": "Stored log is corrupted",
                "log_id": log_id,
            }
        )

    start = max(offset, 0)
    end = start + limit if limit is not None else None
    stdout = payload.get("stdout", "")
    stderr = payload.get("stderr", "")

    response = {
        **payload,
        "stdout": stdout[start:end] if isinstance(stdout, str) else "",
        "stderr": stderr[start:end] if isinstance(stderr, str) else "",
        "offset": start,
        "limit": limit,
    }
    return json.dumps(response)


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "shell_execute",
    "shell_get_full_output",
    "run",
]
