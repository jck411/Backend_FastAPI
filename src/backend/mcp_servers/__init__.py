"""Built-in MCP server modules.

Avoid importing submodules at package import time to prevent side effects.
Each MCP server module is executable via ``python -m`` and registers tools
at import-time using decorators. Importing them here would cause the module
code to run twice when launched with ``-m``, triggering warnings like:

    RuntimeWarning: 'backend.mcp_servers.<module>' found in sys.modules after
    import of package 'backend.mcp_servers', but prior to execution of
    'backend.mcp_servers.<module>'

and duplicate tool registrations ("Tool already exists").

Consumers should import submodules directly, e.g.::

    from backend.mcp_servers import gmail_server  # loads submodule on demand

This works because Python automatically loads submodules for ``from pkg import name``.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any, Final

__all__ = [
    "calculator_server",
    "calendar_server",
    "gdrive_server",
    "gmail_server",
    "housekeeping_server",
    "monarch_server",
    "notes_server",
    "pdf_server",
    "shell_control_server",
    "spotify_server",
]

# Canonical list of bundled MCP servers used to seed configuration defaults.
BUILTIN_MCP_SERVER_DEFINITIONS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "local-calculator",
        "module": "backend.mcp_servers.calculator_server",
        "http_port": 9003,
    },
    {
        "id": "housekeeping",
        "module": "backend.mcp_servers.housekeeping_server",
        "http_port": 9002,
    },
    {
        "id": "custom-calendar",
        "module": "backend.mcp_servers.calendar_server",
        "http_port": 9004,
    },
    {
        "id": "custom-gmail",
        "module": "backend.mcp_servers.gmail_server",
        "http_port": 9005,
    },
    {
        "id": "custom-gdrive",
        "module": "backend.mcp_servers.gdrive_server",
        "http_port": 9006,
    },
    {"id": "custom-pdf", "module": "backend.mcp_servers.pdf_server", "http_port": 9007},
    {
        "id": "monarch-money",
        "module": "backend.mcp_servers.monarch_server",
        "http_port": 9008,
    },
    {"id": "notes", "module": "backend.mcp_servers.notes_server", "http_port": 9009},
    {
        "id": "shell-control",
        "module": "backend.mcp_servers.shell_control_server",
        "http_port": 9001,
    },
    {
        "id": "spotify",
        "module": "backend.mcp_servers.spotify_server",
        "http_port": 9010,
    },
)

_SUBMODULES: dict[str, str] = {name: f"{__name__}.{name}" for name in __all__}


def __getattr__(name: str) -> ModuleType:
    if name not in _SUBMODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_SUBMODULES[name])
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
