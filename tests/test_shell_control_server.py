"""Tests for the shell_control MCP server."""

from backend.mcp_servers.shell_control_server import mcp


class TestShellControlServer:
    """Tests for shell_control MCP server."""

    def test_server_exists(self):
        """Test that the MCP server is initialized."""
        assert mcp is not None
        assert mcp.name == "shell-control"
