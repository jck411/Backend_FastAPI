"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp: FastMCP = FastMCP("shell-control")  # type: ignore


OUTPUT_TRUNCATE_BYTES = 50 * 1024
LOG_RETENTION_HOURS = 48
HOST_PROFILE_ENV = "HOST_PROFILE_ID"


def _get_repo_root() -> Path:
    """Return the project root (same logic as logging helpers)."""

    return Path(__file__).resolve().parents[3]


def _get_log_dir() -> Path:
    """Return the directory used to store shell execution logs."""

    log_dir = _get_repo_root() / "logs" / "shell"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _cleanup_old_logs() -> None:
    """Remove shell logs older than LOG_RETENTION_HOURS."""

    log_dir = _get_log_dir()
    cutoff = time.time() - (LOG_RETENTION_HOURS * 3600)

    for log_file in log_dir.glob("*.json"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass  # File may have been deleted concurrently


def _get_host_root() -> Path:
    """Return the root directory containing host profiles and state."""

    host_root = _get_repo_root() / "host"
    host_root.mkdir(parents=True, exist_ok=True)
    return host_root


def _get_host_id() -> str:
    """Return the active host identifier from the environment."""

    env_value = os.environ.get(HOST_PROFILE_ENV, "").strip()
    return env_value or "local"


def _get_host_dir(host_id: str | None = None) -> Path:
    """Return (and create) the directory for the given or active host."""

    resolved_id = host_id or _get_host_id()
    host_dir = _get_host_root() / resolved_id
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir


def _get_profile_path(host_id: str | None = None) -> Path:
    """Return the profile.json path for the given or active host."""

    return _get_host_dir(host_id) / "profile.json"


def _get_state_path(host_id: str | None = None) -> Path:
    """Return the state.json path for the given or active host."""

    return _get_host_dir(host_id) / "state.json"


def _get_deltas_path(host_id: str | None = None) -> Path:
    """Return the deltas.log path for the given or active host."""

    return _get_host_dir(host_id) / "deltas.log"


def _load_profile() -> dict:
    """Load the current host profile; raise if it is missing or invalid."""

    path = _get_profile_path()
    if not path.exists():
        host_id = _get_host_id()
        raise FileNotFoundError(
            f"Host profile not found for id '{host_id}'. Expected at: {path}"
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Host profile at {path} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Host profile at {path} must contain a JSON object")

    return payload


def _load_state() -> dict:
    """Load the current host state; return an empty object if missing."""

    path = _get_state_path()
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Host state at {path} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Host state at {path} must contain a JSON object")

    return payload


def _save_state(state: dict) -> None:
    """Persist host state to disk atomically."""

    path = _get_state_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


def _save_profile(profile: dict) -> None:
    """Persist host profile to disk atomically."""

    path = _get_profile_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge updates into base dict (returns new dict)."""

    result = base.copy()
    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _append_delta(delta_type: str, changes: dict, reason: str | None = None) -> None:
    """Append a change record to the deltas log for audit purposes."""

    path = _get_deltas_path()
    entry = {
        "ts": time.time(),
        "type": delta_type,
        "changes": changes,
        "reason": reason,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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

    # Clean up old logs before writing new one
    _cleanup_old_logs()

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


@mcp.tool("host_get_profile")  # type: ignore
async def host_get_profile() -> str:
    """Return the active host profile JSON."""

    try:
        profile = _load_profile()
    except FileNotFoundError as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id(),
                "message": str(exc),
            }
        )
    except ValueError as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id(),
                "message": str(exc),
            }
        )

    return json.dumps({"status": "ok", "host_id": _get_host_id(), "profile": profile})


@mcp.tool("host_get_state")  # type: ignore
async def host_get_state() -> str:
    """Return the active host state JSON (empty if missing)."""

    try:
        state = _load_state()
    except ValueError as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id(),
                "message": str(exc),
            }
        )

    return json.dumps({"status": "ok", "host_id": _get_host_id(), "state": state})


@mcp.tool("host_update_profile")  # type: ignore
async def host_update_profile(updates: dict, reason: str | None = None) -> str:
    """Merge updates into the host profile for significant system changes.

    Use this after installing/removing software, changing defaults, or modifying
    system capabilities. Updates are deep-merged into the existing profile.

    Args:
        updates: Dict of changes to merge (e.g., {"apps": {"browser": "firefox"}})
        reason: Optional explanation for the change (logged to deltas)
    """

    try:
        current = _load_profile()
    except FileNotFoundError:
        # Allow creating profile if it doesn't exist
        current = {}
    except ValueError as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id(),
                "message": str(exc),
            }
        )

    merged = _deep_merge(current, updates)
    _save_profile(merged)
    _append_delta("profile", updates, reason)

    return json.dumps(
        {
            "status": "ok",
            "host_id": _get_host_id(),
            "message": "Profile updated",
            "applied": updates,
        }
    )


@mcp.tool("host_update_state")  # type: ignore
async def host_update_state(updates: dict, reason: str | None = None) -> str:
    """Merge updates into the host state for runtime changes.

    Use this to record current system state after commands that change
    runtime configuration (CPU governor, memory settings, service status, etc.).

    Args:
        updates: Dict of changes to merge (e.g., {"cpu_policy": {"governor": "powersave"}})
        reason: Optional explanation for the change (logged to deltas)
    """

    try:
        current = _load_state()
    except ValueError as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id(),
                "message": str(exc),
            }
        )

    # Auto-update timestamp
    updates_with_ts = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    updates_with_ts.update(updates)

    merged = _deep_merge(current, updates_with_ts)
    _save_state(merged)
    _append_delta("state", updates, reason)

    return json.dumps(
        {
            "status": "ok",
            "host_id": _get_host_id(),
            "message": "State updated",
            "applied": updates,
        }
    )


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "shell_execute",
    "shell_get_full_output",
    "host_get_profile",
    "host_get_state",
    "host_update_profile",
    "host_update_state",
    "run",
]
