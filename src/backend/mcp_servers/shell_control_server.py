"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp: FastMCP = FastMCP("shell-control")  # type: ignore


OUTPUT_TRUNCATE_BYTES = 20 * 1024
LOG_RETENTION_HOURS = 48
DELTAS_RETENTION_DAYS = 30
DELTAS_MAX_ENTRIES = 100
HOST_PROFILE_ENV = "HOST_PROFILE_ID"
HOST_ROOT_ENV = "HOST_ROOT_PATH"

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
    # Package managers (Arch)
    (r"(pacman|yay|paru)\s+-S\s", "packages"),
    (r"(pacman|yay|paru)\s+-R", "packages"),
    (r"pacman\s+-Syu", "packages"),
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


async def _detect_system_info() -> dict[str, object]:
    """Detect static system information (OS, desktop, display server, kernel)."""

    info: dict[str, object] = {}

    # OS info from /etc/os-release
    try:
        process = await asyncio.create_subprocess_shell(
            "cat /etc/os-release 2>/dev/null || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
        output = stdout.decode("utf-8", errors="replace")

        for line in output.splitlines():
            if line.startswith("NAME="):
                info["os"] = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("ID_LIKE="):
                info["os_base"] = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("ID=") and "os_base" not in info:
                # Fallback if ID_LIKE not present
                info["os_base"] = line.split("=", 1)[1].strip().strip('"')
    except (asyncio.TimeoutError, Exception):
        pass

    # Kernel version
    try:
        process = await asyncio.create_subprocess_shell(
            "uname -r 2>/dev/null || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
        value = stdout.decode("utf-8", errors="replace").strip()
        if value:
            info["kernel"] = value
    except (asyncio.TimeoutError, Exception):
        pass

    # Desktop environment from XDG_CURRENT_DESKTOP
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    if desktop:
        info["desktop"] = desktop

    # Session type (wayland/x11)
    session_type = os.environ.get("XDG_SESSION_TYPE", "").strip()
    if session_type:
        info["display_server"] = session_type

    # Detect package manager and AUR helper
    pkg_managers = [
        ("pacman", "pacman"),
        ("apt", "apt"),
        ("dnf", "dnf"),
        ("zypper", "zypper"),
        ("emerge", "portage"),
    ]
    for cmd, name in pkg_managers:
        try:
            process = await asyncio.create_subprocess_shell(
                f"command -v {cmd} >/dev/null 2>&1 && echo found || true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
            if b"found" in stdout:
                info["package_manager"] = name
                break
        except (asyncio.TimeoutError, Exception):
            pass

    # Detect AUR helper (Arch-based only)
    if info.get("package_manager") == "pacman":
        aur_helpers = ["yay", "paru", "pikaur", "trizen", "aurman"]
        for helper in aur_helpers:
            try:
                process = await asyncio.create_subprocess_shell(
                    f"command -v {helper} >/dev/null 2>&1 && echo found || true",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2.0)
                if b"found" in stdout:
                    info["aur_helper"] = helper
                    break
            except (asyncio.TimeoutError, Exception):
                pass

    return info


async def _auto_snapshot_software(triggers: set[str]) -> dict[str, object]:
    """Run targeted snapshots based on what triggered, update profile.software automatically.

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

    # Update profile.software section with snapshot
    try:
        current = _load_profile()
    except (FileNotFoundError, ValueError):
        current = {}

    # Ensure software section exists
    if "software" not in current:
        current["software"] = {}

    # Merge snapshot into software section
    snapshot["snapshot_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    current["software"] = _deep_merge(current.get("software", {}), snapshot)
    current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_profile(current)
    _append_delta("software_snapshot", snapshot, "Auto-snapshot after command")

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

    # Ensure D-Bus session bus for desktop settings (gsettings, qdbus, etc.)
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        uid = os.getuid()
        dbus_socket = f"/run/user/{uid}/bus"
        if os.path.exists(dbus_socket):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={dbus_socket}"

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
            snapshot = await _auto_snapshot_software(triggers)
            if snapshot:
                result["profile_updated"] = True
                result["software_snapshot"] = snapshot

    return result


@mcp.tool("shell_execute")  # type: ignore
async def shell_execute(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: int = 30,
    confirm: bool = False,
) -> str:
    """Execute a shell command on the host system.

    Call host_get_profile first if unsure about OS/package manager.

    Sudo supported if SUDO_PASSWORD is set. GUI apps can be launched.

    Non-interactive (no TTY); --noconfirm auto-added for pacman/yay.

    Packages: Use 'yay -S <pkg>' for installs (NOT -Syu).
    'yay -Syu' upgrades ALL packages — only if user explicitly asks.

    Returns: stdout, stderr, exit_code, duration_ms, log_id.
    If truncated=true, use shell_get_full_output(log_id).
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


@mcp.tool("host_get_profile")  # type: ignore
async def host_get_profile() -> str:
    """Get host profile with hardware, software, and notes.

    Profile structure:
    - hardware: CPU, GPU, RAM, model, has_discrete_gpu
    - software: OS, desktop, package_manager, aur_helper, plus:
      - packages: Auto-tracked installed apps by category (browsers, editors, etc.)
      - enabled_services: Auto-tracked systemd services
      - defaults: Auto-tracked XDG default apps (browser, file_manager, etc.)
    - notes: Binary quirks, limitations, user preferences

    The software section is auto-updated after shell_execute runs
    package/service/xdg commands. Check profile.software.packages
    before suggesting installations.
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


@mcp.tool("host_update_profile")  # type: ignore
async def host_update_profile(updates: dict, reason: str | None = None) -> str:
    """Update host profile (hardware, software, notes).

    Profile sections:
    - hardware: CPU, GPU, RAM, model (rarely changes)
    - software: OS, desktop, package manager, plus auto-tracked packages/services/defaults
    - notes: Binary quirks, limitations, user preferences

    The software.packages, software.enabled_services, and software.defaults
    are auto-updated by shell_execute after install/service/xdg commands.
    Use this tool for manual corrections or non-auto-detected changes.

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


@mcp.tool("host_detect_system")  # type: ignore
async def host_detect_system() -> str:
    """Detect and update profile with current system information.

    Auto-detects: OS, kernel, desktop environment, display server (wayland/x11),
    package manager, AUR helper, installed packages, enabled services, default apps.

    Run this to initialize a new profile or audit an existing one.
    Safe to run anytime — merges detected info into profile without overwriting
    manual notes or hardware info.
    """

    # Detect static system info
    system_info = await _detect_system_info()

    # Also snapshot dynamic software state
    packages = await _snapshot_tracked_packages()
    services = await _snapshot_enabled_services()
    defaults = await _snapshot_defaults()

    # Build software section
    software_update: dict[str, object] = {**system_info}
    if packages:
        software_update["packages"] = packages
    if services:
        software_update["enabled_services"] = services
    if defaults:
        software_update["defaults"] = defaults
    software_update["snapshot_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Load current profile and merge
    try:
        current = _load_profile()
    except (FileNotFoundError, ValueError):
        current = {}

    # Merge into software section
    if "software" not in current:
        current["software"] = {}
    current["software"] = _deep_merge(current.get("software", {}), software_update)
    current["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    _save_profile(current)
    _append_delta(
        "system_detect", {"software": software_update}, "Auto-detected system info"
    )

    return json.dumps(
        {
            "status": "ok",
            "host_id": _get_host_id(),
            "message": "System info detected and profile updated",
            "detected": software_update,
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
    "host_update_profile",
    "host_detect_system",
    "run",
]
