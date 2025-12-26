"""MCP server exposing shell control utilities for executing commands."""

from __future__ import annotations

import asyncio
import atexit
import glob as glob_module
import json
import os
import re
import shlex
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio.subprocess import Process

from fastmcp import FastMCP

# Default port for HTTP transport
DEFAULT_HTTP_PORT = 9001

mcp: FastMCP = FastMCP("shell-control")  # type: ignore


OUTPUT_TAIL_BYTES = 4 * 1024  # For success: last 4KB is usually enough
OUTPUT_HEAD_BYTES = 2 * 1024  # For failure: first 2KB (context)
OUTPUT_FAIL_TAIL_BYTES = 4 * 1024  # For failure: last 4KB (error details)
LOG_RETENTION_HOURS = 48
DELTAS_RETENTION_DAYS = 30
DELTAS_MAX_ENTRIES = 100
HOST_PROFILE_ENV = "HOST_PROFILE_ID"
HOST_ROOT_ENV = "HOST_ROOT_PATH"

# Shell session settings
SESSION_IDLE_TIMEOUT = 300  # 5 minutes idle = cleanup
SESSION_MAX_AGE = 3600  # 1 hour max session lifetime
SESSION_MAX_COUNT = 5  # Max concurrent sessions

# Validation pattern for host_id to prevent path traversal attacks
_VALID_HOST_ID = re.compile(r"^[a-zA-Z0-9_-]+$")

# Cleanup throttling (avoid scanning files on every command)
CLEANUP_THROTTLE_SECONDS = 300  # 5 minutes between cleanups
_last_log_cleanup: float = 0.0
_last_delta_cleanup: float = 0.0

# Cached package manager detection (set lazily on first use)
_cached_package_manager: str | None = None

# Input validation bounds
TIMEOUT_MIN_SECONDS = 1
TIMEOUT_MAX_SECONDS = 600  # 10 minutes max


def _get_package_manager() -> str:
    """Detect and cache the system package manager.

    Returns: 'pacman', 'dnf', 'apt', or 'unknown'
    """
    global _cached_package_manager

    if _cached_package_manager is not None:
        return _cached_package_manager

    # Check in order of preference
    pkg_managers = [
        ("pacman", "/usr/bin/pacman"),
        ("dnf", "/usr/bin/dnf"),
        ("apt", "/usr/bin/apt"),
    ]

    for name, path in pkg_managers:
        if os.path.exists(path):
            _cached_package_manager = name
            return name

    _cached_package_manager = "unknown"
    return "unknown"


# =============================================================================
# Persistent Shell Session Management
# =============================================================================


@dataclass
class ShellSession:
    """A persistent bash shell session."""

    session_id: str
    process: "Process"
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    cwd: str = field(default_factory=lambda: os.path.expanduser("~"))
    command_count: int = 0

    def is_alive(self) -> bool:
        """Check if the shell process is still running."""
        return self.process.returncode is None

    def is_expired(self) -> bool:
        """Check if session should be cleaned up."""
        now = time.time()
        idle_expired = (now - self.last_used) > SESSION_IDLE_TIMEOUT
        age_expired = (now - self.created_at) > SESSION_MAX_AGE
        return idle_expired or age_expired or not self.is_alive()


# Global session store
_sessions: dict[str, ShellSession] = {}
_sessions_lock = asyncio.Lock()


async def _cleanup_expired_sessions() -> None:
    """Remove expired sessions."""
    async with _sessions_lock:
        expired = [sid for sid, sess in _sessions.items() if sess.is_expired()]
        for sid in expired:
            sess = _sessions.pop(sid, None)
            if sess and sess.is_alive():
                sess.process.terminate()
                try:
                    await asyncio.wait_for(sess.process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    sess.process.kill()
                    # Reap the process to avoid zombies
                    try:
                        await asyncio.wait_for(sess.process.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass  # Process truly stuck, nothing more we can do


async def _get_or_create_session(session_id: str | None = None) -> ShellSession:
    """Get existing session or create a new one."""
    await _cleanup_expired_sessions()

    async with _sessions_lock:
        # If session_id provided, try to find it
        if session_id and session_id in _sessions:
            sess = _sessions[session_id]
            if sess.is_alive() and not sess.is_expired():
                sess.last_used = time.time()
                return sess
            # Session dead/expired, remove it
            _sessions.pop(session_id, None)

        # Enforce max sessions
        if len(_sessions) >= SESSION_MAX_COUNT:
            # Remove oldest session
            oldest_id = min(_sessions, key=lambda s: _sessions[s].last_used)
            old_sess = _sessions.pop(oldest_id)
            if old_sess.is_alive():
                old_sess.process.terminate()

        # Create new session
        new_id = session_id or uuid.uuid4().hex[:12]
        shell_env = _build_shell_env()

        # Use non-interactive bash to avoid command echoing
        process = await asyncio.create_subprocess_shell(
            "bash --norc --noprofile",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            env=shell_env,
            start_new_session=True,
        )

        sess = ShellSession(session_id=new_id, process=process)
        _sessions[new_id] = sess

        return sess


async def _run_in_session(
    sess: ShellSession,
    command: str,
    timeout_seconds: int = 30,
) -> tuple[str, int, str]:
    """Run a command in an existing session.

    Returns: (output, exit_code, new_cwd)
    """
    if not sess.is_alive():
        raise RuntimeError("Session is no longer alive")

    if not sess.process.stdin or not sess.process.stdout:
        raise RuntimeError("Session has no stdin/stdout")

    # Use a unique end marker for this command
    end_marker = f"___END_{uuid.uuid4().hex[:8]}___"

    # Build a script that:
    # 1. Runs the user command
    # 2. Captures exit code
    # 3. Prints marker with exit code and cwd on a single line
    wrapped_cmd = f"""{command}
__ec__=$?
echo ""
echo "{end_marker}:$__ec__:$(pwd)"
"""

    sess.process.stdin.write(wrapped_cmd.encode())
    await sess.process.stdin.drain()

    # Read output until we see the end marker
    output_lines: list[str] = []
    exit_code = -1
    new_cwd = sess.cwd
    start = time.time()

    while True:
        if time.time() - start > timeout_seconds:
            # Timeout - try to interrupt
            sess.process.send_signal(2)  # SIGINT
            raise TimeoutError(f"Command timed out after {timeout_seconds}s")

        try:
            line_bytes = await asyncio.wait_for(
                sess.process.stdout.readline(), timeout=0.5
            )
        except asyncio.TimeoutError:
            continue

        if not line_bytes:
            # EOF - process died
            raise RuntimeError("Shell process terminated unexpectedly")

        line = line_bytes.decode("utf-8", errors="replace").rstrip("\n\r")

        # Check for our end marker
        if line.startswith(end_marker):
            # Parse: ___END_xxxx___:<exit_code>:<cwd>
            parts = line.split(":", 2)
            if len(parts) >= 3:
                try:
                    exit_code = int(parts[1])
                except ValueError:
                    exit_code = -1
                new_cwd = parts[2]
            break

        # Skip empty lines at the start (from echo "")
        if output_lines or line:
            output_lines.append(line)

    # Remove trailing empty line if present
    while output_lines and not output_lines[-1]:
        output_lines.pop()

    sess.cwd = new_cwd
    sess.command_count += 1
    sess.last_used = time.time()

    return "\n".join(output_lines), exit_code, new_cwd


async def _close_session(session_id: str) -> bool:
    """Close a session explicitly."""
    async with _sessions_lock:
        sess = _sessions.pop(session_id, None)
        if not sess:
            return False
        if sess.is_alive():
            sess.process.terminate()
            try:
                await asyncio.wait_for(sess.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                sess.process.kill()
        return True


def _get_repo_root() -> Path:
    """Return the project root (same logic as logging helpers)."""

    return Path(__file__).resolve().parents[3]


def _get_log_dir() -> Path:
    """Return the directory used to store shell execution logs."""

    log_dir = _get_repo_root() / "logs" / "shell"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _cleanup_old_logs() -> None:
    """Remove shell logs older than LOG_RETENTION_HOURS.

    Throttled to run at most once every CLEANUP_THROTTLE_SECONDS.
    """
    global _last_log_cleanup

    now = time.time()
    if now - _last_log_cleanup < CLEANUP_THROTTLE_SECONDS:
        return  # Throttled, skip this cleanup
    _last_log_cleanup = now

    log_dir = _get_log_dir()
    cutoff = now - (LOG_RETENTION_HOURS * 3600)

    for log_file in log_dir.glob("*.json"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
        except OSError:
            pass  # File may have been deleted concurrently


def _get_host_root() -> Path:
    """Return the root directory containing host profiles.

    Raises:
        RuntimeError: If HOST_ROOT_PATH is not set.
    """
    host_root = os.environ.get(HOST_ROOT_ENV, "").strip()
    if not host_root:
        raise RuntimeError(
            f"{HOST_ROOT_ENV} environment variable is required. "
            "Set it to the host profiles directory (e.g., '/home/jack/gdrive/host_profiles')."
        )
    path = Path(host_root).expanduser()
    if not path.exists():
        raise RuntimeError(f"Host profiles directory does not exist: {path}")
    return path


def _get_host_id() -> str:
    """Return the active host identifier from the environment.

    Raises:
        RuntimeError: If HOST_PROFILE_ID is not set.
    """
    env_value = os.environ.get(HOST_PROFILE_ENV, "").strip()
    if not env_value:
        raise RuntimeError(
            f"{HOST_PROFILE_ENV} environment variable is required. "
            "Set it in the MCP server config (e.g., 'xps13')."
        )
    return env_value


def _get_host_id_safe() -> str:
    """Return the host identifier or 'unknown' if not set."""
    return os.environ.get(HOST_PROFILE_ENV, "").strip() or "unknown"


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


def _get_inventory_path(host_id: str | None = None) -> Path:
    """Return the inventory.json path for the given or active host."""

    return _get_host_dir(host_id) / "inventory.json"


def _load_inventory() -> dict:
    """Load the system inventory; return empty dict if missing."""

    path = _get_inventory_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def _save_inventory(inventory: dict) -> None:
    """Persist system inventory to disk atomically."""

    path = _get_inventory_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


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
    """Remove delta entries older than DELTAS_RETENTION_DAYS or exceeding DELTAS_MAX_ENTRIES.

    Throttled to run at most once every CLEANUP_THROTTLE_SECONDS.
    """
    global _last_delta_cleanup

    now = time.time()
    if now - _last_delta_cleanup < CLEANUP_THROTTLE_SECONDS:
        return  # Throttled, skip this cleanup
    _last_delta_cleanup = now

    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return

    if not lines:
        return

    cutoff = now - (DELTAS_RETENTION_DAYS * 24 * 3600)
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
    # Package managers (Fedora/RHEL)
    (r"dnf\s+(install|remove|erase)\s", "packages"),
    (r"dnf\s+(upgrade|update)(\s|$)", "packages"),
    (r"dnf\s+group\s+(install|remove)\s", "packages"),
    # Universal package managers
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

# Settings panels to open after certain commands (pattern -> panel)
# Supports: gnome-control-center, systemsettings (KDE), or generic commands
_SETTINGS_PANELS: dict[str, dict[str, str | None]] = {
    # Bluetooth
    r"bluetooth(ctl)?\s+(connect|pair|trust|power|scan)": {
        "gnome": "gnome-control-center bluetooth",
        "kde": "systemsettings kcm_bluetooth",
        "generic": "blueman-manager",
    },
    r"rfkill\s+(un)?block\s+bluetooth": {
        "gnome": "gnome-control-center bluetooth",
        "kde": "systemsettings kcm_bluetooth",
        "generic": "blueman-manager",
    },
    # Audio/Volume
    r"(pactl|pamixer|amixer)\s+.*(volume|mute|sink|source)": {
        "gnome": "gnome-control-center sound",
        "kde": "systemsettings kcm_pulseaudio",
        "generic": "pavucontrol",
    },
    r"wpctl\s+set-(volume|mute)": {
        "gnome": "gnome-control-center sound",
        "kde": "systemsettings kcm_pulseaudio",
        "generic": "pavucontrol",
    },
    # Display/Monitor
    r"(xrandr|wlr-randr|gnome-randr)\s+": {
        "gnome": "gnome-control-center display",
        "kde": "systemsettings kcm_kscreen",
        "generic": "arandr",
    },
    # Network/WiFi
    r"nmcli\s+(dev|device|con|connection)\s+(wifi|connect|up|down|modify)": {
        "gnome": "gnome-control-center wifi",
        "kde": "systemsettings kcm_networkmanagement",
        "generic": "nm-connection-editor",
    },
    r"nmcli\s+radio\s+wifi": {
        "gnome": "gnome-control-center wifi",
        "kde": "systemsettings kcm_networkmanagement",
        "generic": "nm-connection-editor",
    },
    # Power settings
    r"(powerprofilesctl|power-profiles-daemon)": {
        "gnome": "gnome-control-center power",
        "kde": "systemsettings kcm_powerdevilprofilesconfig",
        "generic": None,
    },
    r"(tlp|auto-cpufreq)": {
        "gnome": "gnome-control-center power",
        "kde": "systemsettings kcm_powerdevilprofilesconfig",
        "generic": None,
    },
    # Appearance/Theme
    r"gsettings\s+set\s+org\.gnome\.(desktop\.interface|shell\.extensions)": {
        "gnome": "gnome-control-center appearance",
        "kde": None,
        "generic": None,
    },
    r"plasma-apply-(lookandfeel|colorscheme|desktoptheme)": {
        "gnome": None,
        "kde": "systemsettings kcm_lookandfeel",
        "generic": None,
    },
    # Keyboard
    r"(setxkbmap|localectl\s+set-x11-keymap)": {
        "gnome": "gnome-control-center keyboard",
        "kde": "systemsettings kcm_keyboard",
        "generic": None,
    },
    # Mouse/Touchpad
    r"(xinput|libinput).*set-prop": {
        "gnome": "gnome-control-center mouse",
        "kde": "systemsettings kcm_touchpad",
        "generic": None,
    },
    # Printers
    r"(lpadmin|lpstat|cupsenable|cupsdisable)": {
        "gnome": "gnome-control-center printers",
        "kde": "systemsettings kcm_printer_manager",
        "generic": "system-config-printer",
    },
    # Default applications
    r"xdg-(settings|mime)\s+(set|default)": {
        "gnome": "gnome-control-center default-apps",
        "kde": "systemsettings kcm_componentchooser",
        "generic": None,
    },
    # Night light / color temperature
    r"(gsettings.*night-light|redshift|gammastep)": {
        "gnome": "gnome-control-center display",
        "kde": "systemsettings kcm_nightcolor",
        "generic": None,
    },
}

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
    """Snapshot only the tracked package categories (fast, ~100 tokens).

    Supports: pacman (Arch), dnf (Fedora/RHEL)
    """
    pkg_manager = _get_package_manager()

    # Build a single grep pattern for all tracked packages
    all_patterns = []
    for packages in _TRACKED_CATEGORIES.values():
        all_patterns.extend(packages)

    # Escape special chars and join with |
    grep_pattern = "|".join(f"^{p}" for p in all_patterns)

    # Select command based on package manager
    if pkg_manager == "pacman":
        # Output: "package-name version"
        cmd = f"pacman -Qe 2>/dev/null | grep -E '{grep_pattern}' || true"
    elif pkg_manager == "dnf":
        # Output: "package-name.arch version repo"
        # Use awk to normalize output to "package-name version"
        cmd = (
            f"dnf list installed 2>/dev/null | grep -E '{grep_pattern}' | "
            f"awk '{{split($1,a,\".\"); print a[1], $2}}' || true"
        )
    else:
        return {}

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
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
    # Both pacman and dnf (after awk) output: "package-name version"
    result: dict[str, list[str]] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
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
    except asyncio.CancelledError:
        raise
    except Exception:
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
        except asyncio.CancelledError:
            raise
        except Exception:
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
    except asyncio.CancelledError:
        raise
    except Exception:
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
        except asyncio.CancelledError:
            raise
        except Exception:
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
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    return info


async def _auto_snapshot_software(triggers: set[str]) -> dict[str, object]:
    """Run targeted snapshots based on what triggered, update inventory.json.

    Writes to inventory.json (NOT profile.json) to keep the LLM context lean.

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

    # Update inventory.json (not profile.json) with snapshot
    current = _load_inventory()
    snapshot["snapshot_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    merged = _deep_merge(current, snapshot)
    _save_inventory(merged)
    _append_delta("inventory_snapshot", snapshot, "Auto-snapshot after command")

    return snapshot


def _detect_snapshot_triggers(command: str) -> set[str]:
    """Check if a command should trigger a state snapshot.

    Returns a set of trigger categories: "packages", "services", "defaults"
    """
    triggers: set[str] = set()
    for pattern, trigger in _SNAPSHOT_TRIGGERS:
        if re.search(pattern, command, re.IGNORECASE):
            triggers.add(trigger)
    return triggers


def _detect_desktop_environment() -> str:
    """Detect the current desktop environment type."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()

    if "gnome" in desktop or "gnome" in session or "unity" in desktop:
        return "gnome"
    elif "kde" in desktop or "plasma" in desktop or "kde" in session:
        return "kde"
    else:
        return "generic"


async def _open_settings_panel(command: str) -> str | None:
    """Check if command triggers a settings panel and open it.

    Returns the panel command that was launched, or None.
    """
    desktop = _detect_desktop_environment()

    for pattern, panels in _SETTINGS_PANELS.items():
        if re.search(pattern, command, re.IGNORECASE):
            panel_cmd = panels.get(desktop) or panels.get("generic")
            if not panel_cmd:
                return None

            # Launch the settings panel in background (fire and forget)
            shell_env = _build_shell_env()
            try:
                await asyncio.create_subprocess_shell(
                    f"nohup {panel_cmd} >/dev/null 2>&1 &",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=shell_env,
                )
                return panel_cmd
            except asyncio.CancelledError:
                raise
            except Exception:
                return None

    return None


def _smart_truncate(text: str, *, success: bool) -> tuple[str, bool]:
    """Truncate output smartly based on command result.

    Success: Return only tail (last N bytes) - LLM just needs confirmation.
    Failure: Return head + tail - context at start, error at end.
    """
    encoded = text.encode("utf-8", errors="replace")
    total_len = len(encoded)

    if success:
        # Success: just the tail is enough
        if total_len <= OUTPUT_TAIL_BYTES:
            return text, False
        tail = encoded[-OUTPUT_TAIL_BYTES:]
        return tail.decode("utf-8", errors="replace"), True
    else:
        # Failure: head + tail for context
        max_bytes = OUTPUT_HEAD_BYTES + OUTPUT_FAIL_TAIL_BYTES
        if total_len <= max_bytes:
            return text, False
        head = encoded[:OUTPUT_HEAD_BYTES]
        tail = encoded[-OUTPUT_FAIL_TAIL_BYTES:]
        separator = b"\n...truncated...\n"
        combined = head + separator + tail
        return combined.decode("utf-8", errors="replace"), True


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
            matched = glob_module.glob(sys_path)
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
    """Execute a shell command and capture results."""
    shell_env = _build_shell_env()

    start = time.perf_counter()
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_directory or None,
            env=shell_env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
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

    except asyncio.CancelledError:
        raise
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

    success = exit_code == 0
    truncated_stdout, truncated_stdout_flag = _smart_truncate(stdout, success=success)
    truncated_stderr, truncated_stderr_flag = _smart_truncate(stderr, success=success)
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

        # Auto-open settings panel for configuration commands
        panel_opened = await _open_settings_panel(command)
        if panel_opened:
            result["settings_panel_opened"] = panel_opened

    return result


async def _find_path(name: str) -> str | None:
    """Search for a file/directory by name under home. Returns first match or None."""
    home = os.path.expanduser("~")
    # Escape name to prevent shell injection
    safe_name = shlex.quote(f"*{name}*")
    try:
        proc = await asyncio.create_subprocess_shell(
            f"find {shlex.quote(home)} -maxdepth 4 -iname {safe_name} -type d 2>/dev/null | head -1",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        result = stdout.decode().strip()
        return result if result else None
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


async def _launch_gui_app(
    command: str,
    working_directory: str | None = None,
) -> dict[str, object]:
    """Launch a GUI application in background. Searches for path if not found."""
    shell_env = _build_shell_env()
    parts = command.split()
    base_cmd = parts[0] if parts else command

    # For xdg-open: if path doesn't exist, search for it
    if base_cmd == "xdg-open" and len(parts) >= 2:
        target = parts[1]
        if not target.startswith(("http://", "https://", "file://")):
            expanded = os.path.expanduser(target)
            if not os.path.exists(expanded):
                # Extract the name to search for (last component)
                search_name = os.path.basename(expanded.rstrip("/"))
                found = await _find_path(search_name)
                if found:
                    command = f"xdg-open {shlex.quote(found)}"
                else:
                    return {
                        "status": "error",
                        "command": command,
                        "error": f"Path not found: {expanded}",
                    }

    # Use setsid to create new session, nohup to ignore hangup,
    # redirect all I/O to /dev/null to fully detach
    detached_command = f"setsid nohup {command} >/dev/null 2>&1 &"

    start = time.perf_counter()
    try:
        await asyncio.create_subprocess_shell(
            detached_command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=working_directory or None,
            env=shell_env,
            start_new_session=True,
        )
        # Don't wait for the process - it's fully detached
        # Just give it a moment to spawn
        await asyncio.sleep(0.1)
        duration_ms = (time.perf_counter() - start) * 1000

        return {
            "status": "launched",
            "command": command,
            "app": base_cmd,
            "background": True,
            "duration_ms": duration_ms,
            "message": f"GUI app '{base_cmd}' launched in background",
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "error",
            "command": command,
            "error": str(exc),
            "duration_ms": duration_ms,
        }


def _validate_timeout(timeout_seconds: int) -> int:
    """Validate and clamp timeout to safe bounds."""
    return max(TIMEOUT_MIN_SECONDS, min(timeout_seconds, TIMEOUT_MAX_SECONDS))


def _validate_working_directory(working_directory: str | None) -> str | None:
    """Validate working directory to prevent path traversal.

    Returns the validated path or None. Raises ValueError for invalid paths.
    """
    if working_directory is None:
        return None

    # Expand user home (~)
    expanded = os.path.expanduser(working_directory)

    # Resolve to absolute path to catch traversal attempts
    try:
        resolved = Path(expanded).resolve()
    except (OSError, ValueError) as e:
        raise ValueError(f"Invalid working directory path: {e}") from e

    # Must exist and be a directory
    if not resolved.exists():
        raise ValueError(f"Working directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Working directory is not a directory: {resolved}")

    return str(resolved)


@mcp.tool("shell_session")  # type: ignore
async def shell_session(
    command: str,
    session_id: str | None = None,
    timeout_seconds: int = 30,
) -> str:
    """Run a command in a persistent shell session.

    PREFER THIS over shell_execute for multi-step tasks. The session persists:
    - cd changes carry over to next command
    - Environment variables persist (export FOO=bar)
    - Background jobs continue running
    - Command history within session

    Workflow example (bluetooth connect):
    1. shell_session(command="bluetoothctl devices | grep -i pixel")
       → Returns session_id, use it for subsequent commands
    2. shell_session(command="bluetoothctl connect XX:XX:XX", session_id="abc123")
       → Same session, can reference previous context

    Args:
        command: The command to run
        session_id: Reuse an existing session. Omit to create new session.
        timeout_seconds: Max time to wait for command (default 30s, max 600s)

    Returns: JSON with output, exit_code, cwd, session_id.
    Always returns session_id - use it for follow-up commands.

    Sessions auto-expire after 5 min idle or 1 hour total.
    """
    # Validate inputs
    timeout_seconds = _validate_timeout(timeout_seconds)

    start = time.perf_counter()

    try:
        sess = await _get_or_create_session(session_id)
        output, exit_code, cwd = await _run_in_session(sess, command, timeout_seconds)
        duration_ms = (time.perf_counter() - start) * 1000

        return json.dumps(
            {
                "status": "ok",
                "output": output,
                "exit_code": exit_code,
                "cwd": cwd,
                "session_id": sess.session_id,
                "command_count": sess.command_count,
                "duration_ms": duration_ms,
            }
        )

    except TimeoutError as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return json.dumps(
            {
                "status": "timeout",
                "error": str(e),
                "session_id": session_id,
                "duration_ms": duration_ms,
            }
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "session_id": session_id,
                "duration_ms": duration_ms,
            }
        )


@mcp.tool("shell_session_close")  # type: ignore
async def shell_session_close(session_id: str) -> str:
    """Close a shell session explicitly.

    Use when done with a multi-step task to free resources.
    Sessions also auto-expire after 5 min idle.
    """
    closed = await _close_session(session_id)
    return json.dumps(
        {
            "status": "ok" if closed else "not_found",
            "session_id": session_id,
            "message": "Session closed" if closed else "Session not found",
        }
    )


@mcp.tool("shell_session_list")  # type: ignore
async def shell_session_list() -> str:
    """List all active shell sessions.

    Shows session IDs, age, last command time, and current directory.
    """
    await _cleanup_expired_sessions()

    sessions_info = []
    for sid, sess in _sessions.items():
        sessions_info.append(
            {
                "session_id": sid,
                "cwd": sess.cwd,
                "command_count": sess.command_count,
                "age_seconds": round(time.time() - sess.created_at, 1),
                "idle_seconds": round(time.time() - sess.last_used, 1),
                "alive": sess.is_alive(),
            }
        )

    return json.dumps(
        {
            "status": "ok",
            "sessions": sessions_info,
            "count": len(sessions_info),
        }
    )


@mcp.tool("shell_execute")  # type: ignore
async def shell_execute(
    command: str,
    working_directory: str | None = None,
    timeout_seconds: int = 30,
    background: bool = False,
) -> str:
    """Execute a shell command (one-shot, no session persistence).

    For multi-step tasks, PREFER shell_session instead - it maintains
    state between commands (cd, env vars, etc.).

    Use shell_execute for:
    - Simple one-off commands
    - GUI app launches (with background=true)

    Args:
        background: Set True for GUI apps (wizards, dialogs, editors).
                    Returns immediately without waiting for app to close.
        timeout_seconds: Max time to wait (default 30s, max 600s)

    Returns: stdout, stderr, exit_code, duration_ms, log_id.
    If truncated=true, use shell_get_full_output(log_id).
    """
    # Validate inputs
    timeout_seconds = _validate_timeout(timeout_seconds)
    try:
        working_directory = _validate_working_directory(working_directory)
    except ValueError as e:
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "command": command,
            }
        )

    if background:
        result = await _launch_gui_app(command, working_directory)
        return json.dumps(result)

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
    end = start + limit
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


# =============================================================================
# UI Automation Tools (ydotool + hyprctl)
# =============================================================================

# ydotool key codes for common modifiers and keys
_YDOTOOL_KEYCODES: dict[str, int] = {
    # Modifiers
    "ctrl": 29, "control": 29, "lctrl": 29,
    "shift": 42, "lshift": 42,
    "alt": 56, "lalt": 56,
    "super": 125, "meta": 125, "win": 125,
    "rctrl": 97, "rshift": 54, "ralt": 100,
    # Function keys
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    # Navigation
    "escape": 1, "esc": 1, "tab": 15, "enter": 28, "return": 28,
    "backspace": 14, "delete": 111, "del": 111, "insert": 110,
    "home": 102, "end": 107, "pageup": 104, "pagedown": 109,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "space": 57, "capslock": 58, "numlock": 69, "scrolllock": 70,
    "printscreen": 99, "pause": 119,
    # Letters (a-z)
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
    "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
    "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
    "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
    # Numbers
    "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
    "6": 7, "7": 8, "8": 9, "9": 10,
    # Symbols
    "minus": 12, "-": 12, "equal": 13, "=": 13, "plus": 13,
    "leftbracket": 26, "[": 26, "rightbracket": 27, "]": 27,
    "semicolon": 39, ";": 39, "apostrophe": 40, "'": 40,
    "grave": 41, "`": 41, "backslash": 43, "\\": 43,
    "comma": 51, ",": 51, "dot": 52, ".": 52, "period": 52,
    "slash": 53, "/": 53,
}


def _parse_key_combo(combo: str) -> list[int]:
    """Parse a key combo string like 'ctrl+shift+a' into keycodes."""
    keys = [k.strip().lower() for k in combo.replace("+", " ").split()]
    codes = []
    for key in keys:
        if key in _YDOTOOL_KEYCODES:
            codes.append(_YDOTOOL_KEYCODES[key])
        else:
            raise ValueError(f"Unknown key: {key}")
    return codes


@mcp.tool("ui_type")  # type: ignore
async def ui_type(text: str, delay_ms: int = 0) -> str:
    """Type text into the currently focused window.

    Uses ydotool to simulate keyboard input. Works in any window.

    Args:
        text: The text to type
        delay_ms: Delay between keystrokes in milliseconds (0 = fastest)

    Example: ui_type("Hello world")
    """
    if not text:
        return json.dumps({"status": "error", "message": "No text provided"})

    # Escape single quotes for shell
    escaped = text.replace("'", "'\\''")
    delay_arg = f"--key-delay {delay_ms}" if delay_ms > 0 else ""

    try:
        process = await asyncio.create_subprocess_shell(
            f"ydotool type {delay_arg} '{escaped}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

        if process.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": stderr.decode("utf-8", errors="replace").strip(),
            })

        return json.dumps({"status": "ok", "typed": len(text)})

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout typing text"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_key")  # type: ignore
async def ui_key(combo: str) -> str:
    """Send a key combination to the currently focused window.

    Uses ydotool to simulate key presses. Supports modifiers.

    Args:
        combo: Key combination like "ctrl+c", "alt+f4", "ctrl+shift+s", "enter"

    Examples:
        ui_key("ctrl+l")     - Focus browser address bar
        ui_key("ctrl+v")     - Paste
        ui_key("alt+f4")     - Close window
        ui_key("enter")      - Press Enter
        ui_key("ctrl+shift+t") - Reopen closed tab
    """
    if not combo:
        return json.dumps({"status": "error", "message": "No key combo provided"})

    try:
        codes = _parse_key_combo(combo)
    except ValueError as exc:
        return json.dumps({"status": "error", "message": str(exc)})

    # Build ydotool key command: press all keys down, then release in reverse
    # Format: keycode:1 (press), keycode:0 (release)
    key_args = " ".join(f"{code}:1" for code in codes)
    key_args += " " + " ".join(f"{code}:0" for code in reversed(codes))

    try:
        process = await asyncio.create_subprocess_shell(
            f"ydotool key {key_args}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

        if process.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": stderr.decode("utf-8", errors="replace").strip(),
            })

        return json.dumps({"status": "ok", "combo": combo})

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout sending keys"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_click")  # type: ignore
async def ui_click(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
) -> str:
    """Click at screen coordinates or at current cursor position.

    Uses ydotool for kernel-level mouse input.

    Args:
        x: X coordinate (absolute). If None, click at current position.
        y: Y coordinate (absolute). If None, click at current position.
        button: "left", "right", or "middle"
        clicks: Number of clicks (1 = single, 2 = double)

    Examples:
        ui_click()                    - Left click at current position
        ui_click(x=100, y=200)        - Left click at coordinates
        ui_click(button="right")      - Right click at current position
        ui_click(x=500, y=300, clicks=2) - Double-click at coordinates
    """
    button_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    if button.lower() not in button_map:
        return json.dumps({
            "status": "error",
            "message": f"Unknown button: {button}. Use 'left', 'right', or 'middle'",
        })

    button_code = button_map[button.lower()]
    clicks = max(1, min(clicks, 5))  # Clamp to 1-5

    try:
        # Move to position if coordinates provided
        if x is not None and y is not None:
            move_proc = await asyncio.create_subprocess_shell(
                f"ydotool mousemove --absolute {x} {y}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_build_shell_env(),
            )
            await asyncio.wait_for(move_proc.communicate(), timeout=5.0)

        # Perform click(s)
        click_cmd = f"ydotool click {button_code}"
        for _ in range(clicks):
            process = await asyncio.create_subprocess_shell(
                click_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_build_shell_env(),
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

            if process.returncode != 0:
                return json.dumps({
                    "status": "error",
                    "message": stderr.decode("utf-8", errors="replace").strip(),
                })

        return json.dumps({
            "status": "ok",
            "button": button,
            "clicks": clicks,
            "position": {"x": x, "y": y} if x is not None else "current",
        })

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout clicking"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_scroll")  # type: ignore
async def ui_scroll(amount: int, direction: str = "down") -> str:
    """Scroll in the currently focused window.

    Uses ydotool for kernel-level scroll input.

    Args:
        amount: Scroll amount (positive integer, roughly corresponds to "clicks")
        direction: "up", "down", "left", or "right"

    Examples:
        ui_scroll(3)                  - Scroll down 3 units
        ui_scroll(5, "up")            - Scroll up 5 units
        ui_scroll(2, "right")         - Scroll right 2 units
    """
    amount = max(1, min(abs(amount), 100))  # Clamp to 1-100

    # ydotool scroll uses wheel events
    # Vertical: positive = down, negative = up
    # Horizontal: positive = right, negative = left
    direction = direction.lower()
    if direction == "down":
        scroll_arg = f"-- 0 -{amount}"
    elif direction == "up":
        scroll_arg = f"-- 0 {amount}"
    elif direction == "right":
        scroll_arg = f"-- {amount} 0"
    elif direction == "left":
        scroll_arg = f"-- -{amount} 0"
    else:
        return json.dumps({
            "status": "error",
            "message": f"Unknown direction: {direction}. Use 'up', 'down', 'left', 'right'",
        })

    try:
        # ydotool mousemove with wheel option
        process = await asyncio.create_subprocess_shell(
            f"ydotool mousemove --wheel {scroll_arg}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

        if process.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": stderr.decode("utf-8", errors="replace").strip(),
            })

        return json.dumps({"status": "ok", "direction": direction, "amount": amount})

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout scrolling"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_list_windows")  # type: ignore
async def ui_list_windows() -> str:
    """List all open windows with their properties.

    Returns window class, title, workspace, position, and size.
    Use this to find windows before focusing or closing them.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            "hyprctl clients -j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

        if process.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": stderr.decode("utf-8", errors="replace").strip(),
            })

        clients = json.loads(stdout.decode("utf-8", errors="replace"))

        # Simplify output to reduce tokens
        windows = []
        for client in clients:
            windows.append({
                "class": client.get("class", ""),
                "title": client.get("title", "")[:50],  # Truncate long titles
                "workspace": client.get("workspace", {}).get("name", ""),
                "address": client.get("address", ""),
                "focused": client.get("focusHistoryID", -1) == 0,
            })

        return json.dumps({"status": "ok", "windows": windows})

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout listing windows"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_focus_window")  # type: ignore
async def ui_focus_window(match: str) -> str:
    """Focus a window by class name or title.

    Args:
        match: Window class (e.g., "brave-browser", "foot", "code-insiders")
               or partial title match

    Examples:
        ui_focus_window("brave-browser")
        ui_focus_window("foot")
        ui_focus_window("code-insiders")
    """
    if not match:
        return json.dumps({"status": "error", "message": "No match pattern provided"})

    # Try class match first (most reliable)
    try:
        process = await asyncio.create_subprocess_shell(
            f"hyprctl dispatch focuswindow class:{shlex.quote(match)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        output = stdout.decode("utf-8", errors="replace").strip()

        if "ok" in output.lower() or process.returncode == 0:
            return json.dumps({"status": "ok", "focused": match, "by": "class"})

        # Try title match as fallback
        process = await asyncio.create_subprocess_shell(
            f"hyprctl dispatch focuswindow title:{shlex.quote(match)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        output = stdout.decode("utf-8", errors="replace").strip()

        if "ok" in output.lower() or process.returncode == 0:
            return json.dumps({"status": "ok", "focused": match, "by": "title"})

        return json.dumps({
            "status": "error",
            "message": f"No window matching '{match}' found",
        })

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout focusing window"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_close_window")  # type: ignore
async def ui_close_window(match: str | None = None) -> str:
    """Close a window by class name, or close the currently focused window.

    Args:
        match: Optional window class (e.g., "brave-browser"). If None, closes focused window.

    Examples:
        ui_close_window()               - Close currently focused window
        ui_close_window("brave-browser") - Close Brave browser
    """
    if match:
        cmd = f"hyprctl dispatch closewindow class:{shlex.quote(match)}"
    else:
        cmd = "hyprctl dispatch killactive"

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

        output = stdout.decode("utf-8", errors="replace").strip()
        if "ok" in output.lower() or process.returncode == 0:
            return json.dumps({
                "status": "ok",
                "closed": match if match else "focused",
            })

        return json.dumps({
            "status": "error",
            "message": stderr.decode("utf-8", errors="replace").strip() or output,
        })

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout closing window"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_get_monitors")  # type: ignore
async def ui_get_monitors() -> str:
    """Get information about connected monitors.

    Returns monitor name, resolution, position, scale, and active workspace.
    Useful for coordinate-based operations.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            "hyprctl monitors -j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_shell_env(),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

        if process.returncode != 0:
            return json.dumps({
                "status": "error",
                "message": stderr.decode("utf-8", errors="replace").strip(),
            })

        monitors = json.loads(stdout.decode("utf-8", errors="replace"))

        # Simplify output
        result = []
        for mon in monitors:
            result.append({
                "name": mon.get("name", ""),
                "width": mon.get("width", 0),
                "height": mon.get("height", 0),
                "x": mon.get("x", 0),
                "y": mon.get("y", 0),
                "scale": mon.get("scale", 1.0),
                "focused": mon.get("focused", False),
                "activeWorkspace": mon.get("activeWorkspace", {}).get("name", ""),
            })

        return json.dumps({"status": "ok", "monitors": result})

    except asyncio.TimeoutError:
        return json.dumps({"status": "error", "message": "Timeout getting monitors"})
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool("ui_batch")  # type: ignore
async def ui_batch(actions: list[dict[str, object]]) -> str:
    """Run multiple UI actions in order with a single tool call.

    Each action must include "action" (or "type"). Supported actions:
    - focus: match/window/title/class/app
    - key: combo/keys
    - type: text (optional delay_ms)
    - click: x, y, button, clicks
    - wait: seconds or ms (default 0.2s)
    - paste: optional combo (default ctrl+v)

    Example:
        ui_batch([
            {"action": "focus", "match": "brave-browser"},
            {"action": "key", "combo": "ctrl+l"},
            {"action": "type", "text": "https://example.com"},
            {"action": "key", "combo": "enter"},
        ])
    """
    if not actions:
        return json.dumps({"status": "error", "message": "No actions provided"})

    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            return json.dumps(
                {"status": "error", "index": idx, "message": "Action must be an object"}
            )

        action_type = (
            action.get("action") or action.get("type") or action.get("op") or ""
        )
        action_type = str(action_type).strip().lower().replace(" ", "_").replace("-", "_")

        if action_type in ("focus", "focus_window", "window_focus"):
            match = (
                action.get("match")
                or action.get("window")
                or action.get("title")
                or action.get("class")
                or action.get("app")
            )
            if not match:
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Focus action requires match",
                    }
                )
            result = await ui_focus_window(str(match))

        elif action_type in ("key", "keys", "combo", "key_combo", "keycombo"):
            combo = action.get("combo") or action.get("keys") or action.get("key")
            if not combo:
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Key action requires combo",
                    }
                )
            result = await ui_key(str(combo))

        elif action_type in ("type", "text", "input"):
            text = (
                action.get("text")
                if "text" in action
                else action.get("value") or action.get("input")
            )
            if text is None:
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Type action requires text",
                    }
                )
            delay_ms = action.get("delay_ms") if "delay_ms" in action else None
            if delay_ms is None:
                delay_ms = action.get("delay") if "delay" in action else None
            if delay_ms is None:
                delay_ms = action.get("ms") if "ms" in action else None
            if delay_ms is None:
                delay_ms = 0
            try:
                delay_ms = int(delay_ms)
            except (TypeError, ValueError):
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "delay_ms must be an integer",
                    }
                )
            result = await ui_type(str(text), delay_ms=delay_ms)

        elif action_type in ("click", "mouse", "mouse_click"):
            x = action.get("x")
            y = action.get("y")
            if (x is None or y is None) and isinstance(action.get("position"), dict):
                pos = action.get("position")
                x = pos.get("x", x)
                y = pos.get("y", y)
            if (x is None) != (y is None):
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Click action requires both x and y",
                    }
                )
            button = action.get("button", "left")
            clicks = action.get("clicks", 1)
            try:
                x = int(x) if x is not None else None
                y = int(y) if y is not None else None
                clicks = int(clicks)
            except (TypeError, ValueError):
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Click action has invalid coordinates or clicks",
                    }
                )
            result = await ui_click(x=x, y=y, button=str(button), clicks=clicks)

        elif action_type in ("wait", "sleep", "pause"):
            seconds = action.get("seconds")
            ms = action.get("ms") if "ms" in action else None
            if ms is None:
                ms = action.get("duration_ms") if "duration_ms" in action else None
            if seconds is None and ms is None:
                seconds = 0.2
            try:
                if ms is not None:
                    seconds = float(ms) / 1000.0
                else:
                    seconds = float(seconds)
            except (TypeError, ValueError):
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Wait action requires numeric seconds or ms",
                    }
                )
            if seconds < 0:
                return json.dumps(
                    {
                        "status": "error",
                        "index": idx,
                        "action": action_type,
                        "message": "Wait duration must be non-negative",
                    }
                )
            await asyncio.sleep(seconds)
            result = json.dumps({"status": "ok", "waited_seconds": seconds})

        elif action_type in ("paste", "paste_clipboard", "clipboard_paste"):
            combo = action.get("combo") or action.get("keys") or "ctrl+v"
            result = await ui_key(str(combo))

        else:
            return json.dumps(
                {
                    "status": "error",
                    "index": idx,
                    "action": action_type,
                    "message": f"Unknown action: {action_type}",
                }
            )

        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return json.dumps(
                {
                    "status": "error",
                    "index": idx,
                    "action": action_type,
                    "message": "Invalid action result",
                }
            )

        if parsed.get("status") != "ok":
            message = parsed.get("message") or parsed.get("error") or "Action failed"
            return json.dumps(
                {
                    "status": "error",
                    "index": idx,
                    "action": action_type,
                    "message": message,
                }
            )

    return json.dumps({"status": "ok", "performed": len(actions)})


# =============================================================================
# Host Profile Tools
# =============================================================================


@mcp.tool("host_get_profile")  # type: ignore
async def host_get_profile() -> str:
    """Get lean host profile for shell control context.

    Contains only what the LLM needs to operate the system:
    - host_id, os, desktop, display, sudo
    - tools: screenshot, clipboard, windows, open_url, file_manager
    - quirks: edge cases and workarounds

    Package lists, services, and defaults are in inventory.json (not returned).
    """

    try:
        profile = _load_profile()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        return json.dumps(
            {
                "status": "error",
                "host_id": _get_host_id_safe(),
                "message": str(exc),
            }
        )

    return json.dumps(
        {"status": "ok", "host_id": _get_host_id_safe(), "profile": profile}
    )


async def _refresh_system_inventory() -> dict[str, object]:
    """Internal: Refresh system inventory after updates.

    Called by system_update after successful package updates.
    Updates inventory.json with current packages, services, defaults.
    """
    # Detect static system info
    system_info = await _detect_system_info()

    # Snapshot dynamic software state
    packages = await _snapshot_tracked_packages()
    services = await _snapshot_enabled_services()
    defaults = await _snapshot_defaults()

    # Build full inventory snapshot
    inventory_update: dict[str, object] = {
        "system": system_info,
        "snapshot_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if packages:
        inventory_update["packages"] = packages
    if services:
        inventory_update["enabled_services"] = services
    if defaults:
        inventory_update["defaults"] = defaults

    # Save to inventory.json
    current_inventory = _load_inventory()
    merged_inventory = _deep_merge(current_inventory, inventory_update)
    _save_inventory(merged_inventory)
    _append_delta("system_detect", inventory_update, "Auto-detected system info")

    # Update lean profile with only essential context
    lean_update = {}
    if "os" in system_info:
        lean_update["os"] = system_info["os"]
    if "desktop" in system_info:
        lean_update["desktop"] = system_info["desktop"]
    if "display_server" in system_info:
        lean_update["display"] = system_info["display_server"]

    if lean_update:
        try:
            current_profile = _load_profile()
        except (FileNotFoundError, ValueError, RuntimeError):
            current_profile = {}
        merged_profile = _deep_merge(current_profile, lean_update)
        merged_profile["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _save_profile(merged_profile)

    return inventory_update


# =============================================================================
# System Maintenance Tools
# =============================================================================

# Paths to maintenance scripts (user's ~/.config/scripts/)
_MAINTENANCE_SCRIPTS = {
    "update_system": "~/.config/scripts/update-system.sh",
    "backup_system": "~/.config/scripts/backup-system.sh",
}


async def _run_maintenance_script(script_key: str, timeout_seconds: int = 300) -> dict:
    """Run a maintenance script and return structured results."""
    script_path = os.path.expanduser(_MAINTENANCE_SCRIPTS.get(script_key, ""))

    if not script_path or not os.path.isfile(script_path):
        return {
            "status": "error",
            "script": script_key,
            "message": f"Script not found: {script_path}",
        }

    if not os.access(script_path, os.X_OK):
        return {
            "status": "error",
            "script": script_key,
            "message": f"Script not executable: {script_path}",
        }

    shell_env = _build_shell_env()
    start = time.perf_counter()

    try:
        process = await asyncio.create_subprocess_shell(
            f"bash {shlex.quote(script_path)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=shell_env,
        )

        stdout_bytes, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=float(timeout_seconds),
        )

        exit_code = process.returncode if process.returncode is not None else -1
        duration_ms = (time.perf_counter() - start) * 1000
        output = stdout_bytes.decode("utf-8", errors="replace")

        # Smart truncate for LLM consumption
        truncated_output, was_truncated = _smart_truncate(output, success=(exit_code == 0))

        return {
            "status": "ok" if exit_code == 0 else "error",
            "script": script_key,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "output": truncated_output,
            "truncated": was_truncated,
        }

    except asyncio.TimeoutError:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "timeout",
            "script": script_key,
            "message": f"Script timed out after {timeout_seconds} seconds",
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "error",
            "script": script_key,
            "message": str(exc),
            "duration_ms": duration_ms,
        }


@mcp.tool("system_update")  # type: ignore
async def system_update() -> str:
    """Install and update packages, extensions, and apps.

    Includes:
    - System packages (pacman + AUR via yay)
    - VS Code Insiders extensions
    - Tarball apps (Antigravity, etc. from ~/Downloads)
    - Package cache cleanup + orphan removal

    Does NOT back up configs. For backups, use system_backup.
    Fully automatic with no prompts. Runs ~/.config/scripts/update-system.sh.
    Typical runtime: 1-5 minutes.

    Returns:
        JSON with status, exit_code, and output summary.
    """
    result = await _run_maintenance_script("update_system", timeout_seconds=600)

    # Trigger a software snapshot after successful update
    if result.get("status") == "ok":
        try:
            snapshot = await _auto_snapshot_software({"packages", "services"})
            if snapshot:
                result["profile_updated"] = True
        except Exception:
            pass  # Non-critical, don't fail the update

    return json.dumps(result)


@mcp.tool("system_backup")  # type: ignore
async def system_backup() -> str:
    """Back up everything: Timeshift snapshot + dotfiles git sync.

    Includes:
    - Timeshift snapshot (system-level, excludes /home)
    - Dotfiles sync, commit, and push to git remote

    Run this BEFORE making major system changes or after config tweaks.
    Fully automatic with no prompts. Runs ~/.config/scripts/backup-system.sh.
    Typical runtime: 1-3 minutes.

    Returns:
        JSON with status, exit_code, and backup details.
    """
    result = await _run_maintenance_script("backup_system", timeout_seconds=300)
    return json.dumps(result)


def _shutdown_sessions() -> None:
    """Synchronously terminate all active shell sessions on shutdown.

    Called via atexit to prevent orphaned bash processes.
    """
    for sid, sess in list(_sessions.items()):
        if sess.is_alive():
            try:
                sess.process.terminate()
                # Give it a moment to terminate
                sess.process.wait()
            except Exception:
                # Last resort: force kill
                try:
                    sess.process.kill()
                    sess.process.wait()
                except Exception:
                    pass  # Nothing more we can do
    _sessions.clear()


# Register shutdown handler to cleanup sessions on exit
atexit.register(_shutdown_sessions)


def run(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
) -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server with the specified transport."""
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    import argparse
    parser = argparse.ArgumentParser(description="Shell Control MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port for HTTP server",
    )
    args = parser.parse_args()
    run(args.transport, args.host, args.port)


__all__ = [
    "mcp",
    "shell_session",
    "shell_session_close",
    "shell_session_list",
    "shell_execute",
    "shell_get_full_output",
    "host_get_profile",
    "system_update",
    "system_backup",
    # UI Automation
    "ui_type",
    "ui_key",
    "ui_click",
    "ui_scroll",
    "ui_list_windows",
    "ui_focus_window",
    "ui_close_window",
    "ui_get_monitors",
    "run",
]
