"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp: FastMCP = FastMCP("shell-control")  # type: ignore


OUTPUT_TRUNCATE_BYTES = 50 * 1024
LOG_RETENTION_HOURS = 48
DELTAS_RETENTION_DAYS = 30
DELTAS_MAX_ENTRIES = 100
HOST_PROFILE_ENV = "HOST_PROFILE_ID"
HOST_ROOT_ENV = "HOST_ROOT_PATH"

# Track background jobs: job_id -> {process, command, start_time, log_id, ...}
_background_jobs: dict[str, dict[str, Any]] = {}

# Validation pattern for host_id to prevent path traversal attacks
_VALID_HOST_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


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
    """Return the root directory containing host profiles and state.

    Override with HOST_ROOT_PATH env var to use a custom location (e.g., GDrive sync folder).
    """

    custom_root = os.environ.get(HOST_ROOT_ENV, "").strip()
    if custom_root:
        host_root = Path(custom_root).expanduser()
    else:
        host_root = _get_repo_root() / "host"

    host_root.mkdir(parents=True, exist_ok=True)
    return host_root


def _get_host_id() -> str:
    """Return the active host identifier from the environment."""

    env_value = os.environ.get(HOST_PROFILE_ENV, "").strip()
    return env_value or "local"


def _get_host_dir(host_id: str | None = None) -> Path:
    """Return (and create) the directory for the given or active host.

    Raises:
        ValueError: If host_id contains invalid characters (path traversal prevention).
    """
    resolved_id = host_id or _get_host_id()

    # Validate host_id to prevent path traversal attacks
    if not _VALID_HOST_ID.match(resolved_id):
        raise ValueError(
            f"Invalid host_id: {resolved_id!r}. Must be alphanumeric with - or _"
        )

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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        host_id = _get_host_id()
        raise FileNotFoundError(
            f"Host profile not found for id '{host_id}'. Expected at: {path}"
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Host profile at {path} is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Host profile at {path} must contain a JSON object")

    return payload


def _load_state() -> dict:
    """Load the current host state; return an empty object if missing."""

    path = _get_state_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
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
    """Recursively merge updates into base dict (returns new dict).

    Special handling:
    - None values DELETE the key from base
    - Nested dicts are merged recursively
    - All other values replace the existing value
    """

    result = base.copy()
    for key, value in updates.items():
        if value is None:
            # None means "delete this key"
            result.pop(key, None)
        elif (
            key in result and isinstance(result[key], dict) and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _cleanup_old_deltas(path: Path) -> None:
    """Remove delta entries older than DELTAS_RETENTION_DAYS or exceeding DELTAS_MAX_ENTRIES."""

    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return

    if not lines:
        return

    cutoff = time.time() - (DELTAS_RETENTION_DAYS * 24 * 3600)
    kept: list[str] = []

    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get("ts", 0) >= cutoff:
                kept.append(line)
        except json.JSONDecodeError:
            pass  # Skip corrupted entries

    # Also enforce max entries (keep most recent)
    if len(kept) > DELTAS_MAX_ENTRIES:
        kept = kept[-DELTAS_MAX_ENTRIES:]

    # Rewrite file atomically
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text("\n".join(kept) + "\n" if kept else "", encoding="utf-8")
    tmp_path.replace(path)


def _append_delta(delta_type: str, changes: dict, reason: str | None = None) -> None:
    """Append a change record to the deltas log for audit purposes."""

    path = _get_deltas_path()

    # Periodic cleanup (run before appending)
    _cleanup_old_deltas(path)

    entry = {
        "ts": time.time(),
        "type": delta_type,
        "changes": changes,
        "reason": reason,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# Patterns that trigger state snapshots
_SNAPSHOT_TRIGGERS: list[tuple[str, str]] = [
    # Package managers (all distros)
    (r"(pacman|yay|paru)\s+-S\s", "packages"),
    (r"(pacman|yay|paru)\s+-R", "packages"),
    (r"pacman\s+-Syu", "packages"),
    (r"apt(-get)?\s+(install|remove|purge|upgrade)", "packages"),
    (r"dnf\s+(install|remove|upgrade)", "packages"),
    (r"flatpak\s+(install|uninstall)", "packages"),
    (r"snap\s+(install|remove)", "packages"),
    (r"pipx\s+(install|uninstall)", "packages"),
    # Services
    (r"systemctl\s+(enable|disable)\s", "services"),
    # Default apps
    (r"xdg-settings\s+set\s", "defaults"),
    (r"xdg-mime\s+default\s", "defaults"),
    (r"update-alternatives\s+--set\s", "defaults"),
]

# Categories of packages to track (grep patterns for pacman -Qe)
_TRACKED_CATEGORIES: dict[str, list[str]] = {
    "browsers": [
        "brave",
        "firefox",
        "chromium",
        "google-chrome",
        "vivaldi",
        "microsoft-edge",
        "librewolf",
        "floorp",
        "zen-browser",
    ],
    "editors": [
        "code",
        "visual-studio-code",
        "neovim",
        "vim",
        "emacs",
        "sublime-text",
        "atom",
        "gedit",
        "kate",
        "helix",
    ],
    "terminals": [
        "alacritty",
        "kitty",
        "wezterm",
        "foot",
        "konsole",
        "gnome-terminal",
        "tilix",
        "terminator",
    ],
    "system_tools": [
        "earlyoom",
        "timeshift",
        "tlp",
        "auto-cpufreq",
        "zram-generator",
        "preload",
        "thermald",
        "power-profiles-daemon",
    ],
    "media": [
        "spotify",
        "vlc",
        "mpv",
        "obs-studio",
        "kdenlive",
        "audacity",
        "gimp",
        "inkscape",
        "krita",
    ],
    "dev_tools": [
        "docker",
        "podman",
        "nodejs",
        "npm",
        "yarn",
        "python",
        "go",
        "rust",
        "cargo",
        "git",
        "github-cli",
    ],
}


async def _snapshot_tracked_packages() -> dict[str, list[str]]:
    """Snapshot only the tracked package categories (fast, ~100 tokens)."""

    # Build a single grep pattern for all tracked packages
    all_patterns = []
    for packages in _TRACKED_CATEGORIES.values():
        all_patterns.extend(packages)

    # Escape special chars and join with |
    pattern = "|".join(f"^{p}" for p in all_patterns)

    # Run pacman -Qe and grep for our tracked packages
    try:
        process = await asyncio.create_subprocess_shell(
            f"pacman -Qe 2>/dev/null | grep -E '{pattern}' || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        output = stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception):
        return {}

    if not output:
        return {}

    # Parse output and categorize
    result: dict[str, list[str]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        # Line format: "package-name version"
        parts = line.split()
        if not parts:
            continue
        pkg_name = parts[0]
        pkg_with_ver = line.strip()

        # Find which category this belongs to
        for category, patterns in _TRACKED_CATEGORIES.items():
            for pattern in patterns:
                if pkg_name.startswith(pattern) or pkg_name == pattern:
                    if category not in result:
                        result[category] = []
                    result[category].append(pkg_with_ver)
                    break

    return result


async def _snapshot_enabled_services() -> list[str]:
    """Snapshot user-enabled systemd services (fast, ~20 tokens)."""

    # Only get user-enabled services, not all system services
    tracked_services = [
        "earlyoom",
        "tlp",
        "thermald",
        "auto-cpufreq",
        "docker",
        "podman",
        "libvirtd",
        "bluetooth",
        "cups",
        "sshd",
        "power-profiles-daemon",
        "timeshift-autosnap",
    ]
    pattern = "|".join(tracked_services)

    try:
        process = await asyncio.create_subprocess_shell(
            f"systemctl list-unit-files --state=enabled --type=service 2>/dev/null "
            f"| grep -E '{pattern}' | awk '{{print $1}}' || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        output = stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception):
        return []

    return [s.strip() for s in output.splitlines() if s.strip()]


async def _snapshot_defaults() -> dict[str, str]:
    """Snapshot XDG default applications (browser, file manager, etc.)."""

    defaults: dict[str, str] = {}

    # Key XDG settings the LLM needs for natural language commands
    xdg_queries = [
        ("default-web-browser", "browser"),
        ("default-url-scheme-handler https", "browser_https"),
    ]

    for query, key in xdg_queries:
        try:
            process = await asyncio.create_subprocess_shell(
                f"xdg-settings get {query} 2>/dev/null || true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
            value = stdout.decode("utf-8", errors="replace").strip()
            if value:
                # Strip .desktop suffix for cleaner output
                defaults[key] = value.replace(".desktop", "")
        except (asyncio.TimeoutError, Exception):
            pass

    # Also get xdg-mime defaults for common types
    mime_queries = [
        ("inode/directory", "file_manager"),
        ("application/pdf", "pdf_viewer"),
        ("image/png", "image_viewer"),
        ("video/mp4", "video_player"),
        ("audio/mpeg", "audio_player"),
        ("text/plain", "text_editor"),
    ]

    for mime_type, key in mime_queries:
        try:
            process = await asyncio.create_subprocess_shell(
                f"xdg-mime query default {mime_type} 2>/dev/null || true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
            value = stdout.decode("utf-8", errors="replace").strip()
            if value:
                defaults[key] = value.replace(".desktop", "")
        except (asyncio.TimeoutError, Exception):
            pass

    return defaults


async def _auto_snapshot_state(triggers: set[str]) -> dict[str, object]:
    """Run targeted snapshots based on what triggered, update state automatically.

    Triggers:
        - "packages": Snapshot installed apps in tracked categories
        - "services": Snapshot enabled systemd services
        - "defaults": Snapshot XDG default applications
    """

    snapshot: dict[str, object] = {}

    # Package changes -> snapshot tracked packages + defaults (install may change defaults)
    if "packages" in triggers:
        snapshot["packages"] = await _snapshot_tracked_packages()
        snapshot["defaults"] = await _snapshot_defaults()  # May have changed

    # Service changes -> snapshot enabled services
    if "services" in triggers:
        snapshot["enabled_services"] = await _snapshot_enabled_services()

    # Default app changes -> just snapshot defaults
    if "defaults" in triggers and "packages" not in triggers:
        snapshot["defaults"] = await _snapshot_defaults()

    if not snapshot:
        return {}

    # Update state with snapshot
    try:
        current = _load_state()
    except ValueError:
        current = {}

    snapshot["snapshot_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    merged = _deep_merge(current, snapshot)
    _save_state(merged)

    return snapshot


def _detect_snapshot_triggers(command: str) -> set[str]:
    """Check if a command should trigger a state snapshot.

    Returns a set of trigger categories: "packages", "services", "defaults"
    """

    import re

    triggers: set[str] = set()
    for pattern, trigger in _SNAPSHOT_TRIGGERS:
        if re.search(pattern, command, re.IGNORECASE):
            triggers.add(trigger)
    return triggers


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
    use_askpass = False

    stripped = command.lstrip()

    # Check if command starts with an AUR helper that calls sudo internally
    aur_helpers = ("yay", "paru", "pikaur", "trizen", "aurman")
    aur_match = None
    for helper in aur_helpers:
        if stripped.startswith(helper + " ") or stripped == helper:
            aur_match = helper
            break

    if aur_match and sudo_password:
        # AUR helpers call sudo multiple times - use SUDO_ASKPASS approach
        # This is more reliable than --sudoflags for multi-sudo scenarios
        use_askpass = True
    elif stripped.startswith("sudo") and sudo_password:
        # Direct sudo command - use stdin
        send_password = True
        rest = stripped[len("sudo") :].lstrip()

        # Auto-add --noconfirm for pacman commands if missing
        if re.search(r"pacman\s+-S", rest) and "--noconfirm" not in rest:
            # Insert --noconfirm after pacman -S... flags
            rest = re.sub(r"(pacman\s+-\S+)", r"\1 --noconfirm", rest, count=1)

        if " -S " not in stripped and not stripped.startswith("sudo -S"):
            stripped = f"sudo -S {rest}".strip()
        else:
            stripped = f"sudo {rest}".strip()
        prepared_command = (
            f"{command[: len(command) - len(command.lstrip())]}{stripped}"
        )

    shell_env = _build_shell_env()

    # For AUR helpers, set up SUDO_ASKPASS with an inline script
    # This handles multiple sudo calls during package builds
    if use_askpass and sudo_password and aur_match:
        # AUR helpers call sudo multiple times during builds
        # Strategy: pre-authenticate sudo with -v, then use --sudoloop to keep it alive
        rest_of_command = stripped[len(aur_match) :].lstrip()

        # Escape password for shell (handle special chars like $, `, ", ', etc.)
        escaped_password = sudo_password.replace("'", "'\"'\"'")

        # Auto-add --noconfirm if not present (non-interactive requirement)
        if "--noconfirm" not in rest_of_command:
            rest_of_command = f"--noconfirm {rest_of_command}"

        prepared_command = (
            f"echo '{escaped_password}' | sudo -S -v && "  # Validate/refresh sudo
            f"{aur_match} --sudoloop {rest_of_command}"
        )
        send_password = False  # Password already in command

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

    result: dict[str, object] = {
        "stdout": truncated_stdout,
        "stderr": truncated_stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "truncated": truncated,
        "log_id": log_id,
        "command": command,
        "working_directory": working_directory,
    }

    # Auto-snapshot if command succeeded and triggers snapshot
    if exit_code == 0:
        triggers = _detect_snapshot_triggers(command)
        if triggers:
            snapshot = await _auto_snapshot_state(triggers)
            if snapshot:
                result["state_updated"] = True
                result["snapshot"] = snapshot

    return result


@mcp.tool("shell_execute")  # type: ignore
async def shell_execute(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: int = 30,
    confirm: bool = False,
    background: bool = False,
) -> str:
    """Execute a shell command on the host system.

    Full PATH is configured automatically (includes ~/.local/bin, snap, flatpak, cargo, etc.).
    GUI applications can be launched. Sudo is supported if SUDO_PASSWORD is configured.

    Sudo handling:
    - Direct 'sudo ...' commands: Password auto-injected via stdin (-S flag added automatically)
    - AUR helpers (yay, paru, etc.): Pre-authenticated with --sudoloop for long builds

    IMPORTANT - Non-interactive execution:
    - Commands run without TTY. Always use flags to skip prompts.
    - --noconfirm is auto-added for pacman/yay/paru commands.

    IMPORTANT - Package installation best practices:
    - For installing/updating a SINGLE package: Use 'yay -S package' (NOT -Syu)
    - For full system upgrade: Use 'yay -Syu' (can take 30+ minutes for AUR rebuilds)
    - The -u flag upgrades ALL packages, which rebuilds all outdated AUR packages
    - Example: 'yay -S visual-studio-code-insiders-bin' (fast, just installs/updates one package)

    IMPORTANT - Long-running commands:
    - For commands expected to take >30 seconds, set background=True
    - This returns immediately with a job_id
    - Use shell_job_status(job_id) to check progress and get results
    - Example: Package updates, large builds, system upgrades

    Returns: stdout, stderr, exit_code, duration_ms, and log_id.
    - If background=True: Returns immediately with job_id and status="running"
    - If output exceeds 50KB, 'truncated' will be true; use shell_get_full_output(log_id) for complete output.
    - If command times out, increase timeout_seconds.
    - If exit_code is 0 and command modified packages/services/defaults, state is auto-snapshotted.

    Limitation: D-Bus commands (gsettings, qdbus, notify-send) won't affect the live desktop
    session—suggest user run those manually if needed.

    Tip: Call host_get_profile first to learn OS, desktop, package manager, and installed apps.
    """

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

    # Background execution for long-running commands
    if background:
        job_id = uuid.uuid4().hex[:12]
        _background_jobs[job_id] = {
            "command": command,
            "working_directory": working_directory,
            "timeout_seconds": timeout_seconds,
            "start_time": time.time(),
            "status": "running",
            "result": None,
            "error": None,
            "end_time": 0,
        }

        # Start the background task
        asyncio.create_task(
            _run_background_job(job_id, command, working_directory, timeout_seconds)
        )

        return json.dumps(
            {
                "status": "running",
                "job_id": job_id,
                "command": command,
                "message": "Command started in background. Use shell_job_status(job_id) to check progress.",
                "tip": "Poll shell_job_status every 10-30 seconds for long operations.",
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
    """Retrieve full command output when shell_execute returned truncated=true.

    Args:
        log_id: The log_id returned by shell_execute
        offset: Byte offset to start reading from (for chunked retrieval)
        limit: Maximum bytes to return (default 100KB)

    Logs are retained for 48 hours.
    """

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


async def _run_background_job(
    job_id: str,
    command: str,
    working_directory: str | None,
    timeout_seconds: int,
) -> None:
    """Background task that runs a command and updates job status when done."""
    job = _background_jobs.get(job_id)
    if not job:
        return

    try:
        result = await _execute_and_log(
            command,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )
        job["status"] = "completed"
        job["result"] = result
        job["end_time"] = time.time()
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(exc)
        job["end_time"] = time.time()


@mcp.tool("shell_job_status")  # type: ignore
async def shell_job_status(job_id: str | None = None) -> str:
    """Check status of background shell jobs.

    Args:
        job_id: Specific job to check. If None, returns all active jobs.

    Returns job status:
    - "running": Command still executing (shows elapsed time)
    - "completed": Finished successfully (includes full result)
    - "failed": Finished with error

    Use this to monitor long-running commands started with background=True.
    """
    # Clean up old completed jobs (keep for 1 hour)
    cutoff = time.time() - 3600
    to_remove = [
        jid
        for jid, job in _background_jobs.items()
        if job.get("end_time", 0) > 0 and job["end_time"] < cutoff
    ]
    for jid in to_remove:
        del _background_jobs[jid]

    if job_id:
        job = _background_jobs.get(job_id)
        if not job:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Job {job_id} not found (may have expired)",
                    "job_id": job_id,
                }
            )

        elapsed = time.time() - job["start_time"]
        response: dict[str, Any] = {
            "job_id": job_id,
            "command": job["command"],
            "status": job["status"],
            "elapsed_seconds": round(elapsed, 1),
            "started_at": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(job["start_time"])
            ),
        }

        if job["status"] == "completed":
            response["result"] = job.get("result", {})
        elif job["status"] == "failed":
            response["error"] = job.get("error", "Unknown error")

        return json.dumps(response)

    # Return all jobs
    jobs_summary = []
    for jid, job in _background_jobs.items():
        elapsed = time.time() - job["start_time"]
        summary: dict[str, Any] = {
            "job_id": jid,
            "command": job["command"][:80]
            + ("..." if len(job["command"]) > 80 else ""),
            "status": job["status"],
            "elapsed_seconds": round(elapsed, 1),
        }
        if job["status"] == "completed":
            summary["exit_code"] = job.get("result", {}).get("exit_code")
        jobs_summary.append(summary)

    return json.dumps(
        {
            "status": "ok",
            "active_jobs": len(
                [j for j in _background_jobs.values() if j["status"] == "running"]
            ),
            "total_jobs": len(_background_jobs),
            "jobs": jobs_summary,
        }
    )


@mcp.tool("host_get_profile")  # type: ignore
async def host_get_profile() -> str:
    """Get static host configuration (OS, desktop, hardware, capabilities, limitations).

    Call this FIRST before running commands to understand:
    - OS and package manager (e.g., Arch/pacman vs Ubuntu/apt)
    - Desktop environment (KDE, GNOME, etc.)
    - Known binary names (e.g., 'brave' not 'brave-browser')
    - System limitations (e.g., D-Bus restrictions)
    - Hardware model for device-specific commands

    Profile is manually curated and rarely changes.
    """

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
    """Get dynamic host state (installed packages, enabled services, default apps).

    State is auto-updated when shell_execute runs commands that modify:
    - Packages (pacman/apt/dnf install/remove)
    - Services (systemctl enable/disable)
    - Default apps (xdg-settings/xdg-mime)

    Returns tracked categories: browsers, editors, terminals, system_tools, media, dev_tools.
    Use this to check what's already installed before suggesting installations.
    """

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
    """Update static host profile (use sparingly for permanent config changes).

    Use for:
    - Adding notes about discovered binary names
    - Documenting new capabilities or limitations
    - Recording user preferences

    Do NOT use for: installed packages, services, defaults (those go in state).

    Args:
        updates: Dict to deep-merge (set value to null to delete a key)
        reason: Explanation logged to deltas.log for audit
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
    merged["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
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
    """Manually update host state for changes not auto-detected.

    Auto-snapshot handles: package installs, service enable/disable, xdg defaults.
    Use this for other runtime state like:
    - CPU governor settings
    - Display configuration
    - Network profiles
    - Custom environment changes

    Args:
        updates: Dict to deep-merge (set value to null to delete a key)
        reason: Explanation logged to deltas.log for audit
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


@mcp.tool("host_list")  # type: ignore
async def host_list() -> str:
    """List all configured hosts (for multi-machine setups).

    Shows which host is currently active and what config files exist.
    Useful when HOST_PROFILE_ID env var switches between machines.
    """

    host_root = _get_host_root()
    hosts: list[dict[str, object]] = []

    try:
        for entry in host_root.iterdir():
            if entry.is_dir():
                profile_exists = (entry / "profile.json").exists()
                state_exists = (entry / "state.json").exists()
                deltas_exists = (entry / "deltas.log").exists()

                # Only include if it has at least a profile or state
                if profile_exists or state_exists:
                    hosts.append(
                        {
                            "id": entry.name,
                            "has_profile": profile_exists,
                            "has_state": state_exists,
                            "has_deltas": deltas_exists,
                        }
                    )
    except OSError as exc:
        return json.dumps(
            {
                "status": "error",
                "message": f"Failed to list hosts: {exc}",
            }
        )

    return json.dumps(
        {
            "status": "ok",
            "active_host": _get_host_id(),
            "host_root": str(host_root),
            "hosts": hosts,
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
    "shell_job_status",
    "host_get_profile",
    "host_get_state",
    "host_update_profile",
    "host_update_state",
    "host_list",
    "run",
]
