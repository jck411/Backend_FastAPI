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

__all__ = [
    "calculator_server",
    "calendar_server",
    "gdrive_server",
    "gmail_server",
    "housekeeping_server",
    "notion_server",
    "pdf_server",
]

_SUBMODULES: dict[str, str] = {name: f"{__name__}.{name}" for name in __all__}


def __getattr__(name: str) -> ModuleType:
    if name not in _SUBMODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_SUBMODULES[name])
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
