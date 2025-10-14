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

__all__ = [
    "calculator_server",
    "calendar_server",
    "gdrive_server",
    "gmail_server",
    "housekeeping_server",
    "pdf_server",
]
