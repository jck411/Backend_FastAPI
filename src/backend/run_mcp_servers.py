#!/usr/bin/env python
"""Launch all enabled MCP servers in HTTP transport mode.

This script reads the mcp_servers.json configuration and starts each
enabled server as an HTTP endpoint on its configured port.

Usage:
    python run_mcp_servers.py [--config PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Default port assignments for HTTP transport
DEFAULT_PORTS = {
    "shell-control": 9001,
    "housekeeping": 9002,
    "local-calculator": 9003,
    "custom-calendar": 9004,
    "custom-gmail": 9005,
    "custom-gdrive": 9006,
    "custom-pdf": 9007,
    "monarch-money": 9008,
    "notes": 9009,
    "spotify": 9010,
}

# Map server IDs to their run functions
SERVER_MODULES = {
    "shell-control": "backend.mcp_servers.shell_control_server",
    "housekeeping": "backend.mcp_servers.housekeeping_server",
    "local-calculator": "backend.mcp_servers.calculator_server",
    "custom-calendar": "backend.mcp_servers.calendar_server",
    "custom-gmail": "backend.mcp_servers.gmail_server",
    "custom-gdrive": "backend.mcp_servers.gdrive_server",
    "custom-pdf": "backend.mcp_servers.pdf_server",
    "monarch-money": "backend.mcp_servers.monarch_server",
    "notes": "backend.mcp_servers.notes_server",
    "spotify": "backend.mcp_servers.spotify_server",
}


def get_default_config_path() -> Path:
    """Get the default path to mcp_servers.json."""
    # Script is in src/backend/, config is in data/
    script_dir = Path(__file__).resolve().parent
    # Navigate from src/backend to project root, then to data/
    return script_dir.parents[1] / "data" / "mcp_servers.json"


def load_config(config_path: Path) -> dict[str, Any]:
    """Load the MCP servers configuration from JSON file."""
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        sys.exit(1)

    with open(config_path) as f:
        return json.load(f)


async def start_server(
    server_id: str,
    module_path: str,
    port: int,
    host: str = "127.0.0.1",
    env: dict[str, str] | None = None,
) -> asyncio.subprocess.Process | None:
    """Start a single MCP server as a subprocess.

    Args:
        server_id: Unique identifier for the server
        module_path: Python module path (e.g., backend.mcp_servers.shell_control_server)
        port: HTTP port to bind to
        host: Host address to bind to
        env: Environment variables for the server

    Returns:
        The subprocess.Process object, or None if failed to start
    """
    import os

    # Build environment
    server_env = os.environ.copy()
    if env:
        server_env.update(env)

    cmd = [
        sys.executable,
        "-m",
        module_path,
        "--transport",
        "streamable-http",
        "--host",
        host,
        "--port",
        str(port),
    ]

    logger.info("Starting %s on http://%s:%d", server_id, host, port)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=server_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Started %s (PID: %d)", server_id, process.pid)
        return process
    except Exception as e:
        logger.error("Failed to start %s: %s", server_id, e)
        return None


async def monitor_process(server_id: str, process: asyncio.subprocess.Process) -> None:
    """Monitor a server process and log its output."""
    if process.stdout:
        async for line in process.stdout:
            logger.info("[%s] %s", server_id, line.decode().strip())


async def run_servers(config_path: Path, host: str = "127.0.0.1") -> None:
    """Start all enabled MCP servers and monitor them."""
    config = load_config(config_path)
    servers = config.get("servers", [])

    if not servers:
        logger.warning("No servers configured in %s", config_path)
        return

    # Filter enabled servers
    enabled_servers = [s for s in servers if s.get("enabled", False)]

    if not enabled_servers:
        logger.warning("No servers are enabled in configuration")
        return

    logger.info("Starting %d enabled MCP servers...", len(enabled_servers))

    processes: dict[str, asyncio.subprocess.Process] = {}
    tasks: list[asyncio.Task] = []

    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Received shutdown signal, stopping servers...")
        shutdown_event.set()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    try:
        for server in enabled_servers:
            server_id = server.get("id")
            if not server_id:
                logger.warning("Server entry missing 'id', skipping")
                continue

            # Get port from config or use default
            port = server.get("http_port") or DEFAULT_PORTS.get(server_id)
            if not port:
                logger.warning("No port configured for %s, skipping", server_id)
                continue

            # Get module path from config or use default mapping
            module_path = server.get("module") or SERVER_MODULES.get(server_id)
            if not module_path:
                logger.warning("No module path for %s, skipping", server_id)
                continue

            # Get environment variables
            env = server.get("env", {})

            # Start the server
            process = await start_server(
                server_id, module_path, port, host, env or None
            )
            if process:
                processes[server_id] = process
                # Create monitoring task
                task = asyncio.create_task(monitor_process(server_id, process))
                tasks.append(task)

        if not processes:
            logger.error("No servers were started successfully")
            return

        logger.info("All %d servers started successfully", len(processes))
        logger.info("Press Ctrl+C to stop all servers")

        # Wait for shutdown signal
        await shutdown_event.wait()

    finally:
        # Cleanup: terminate all processes
        logger.info("Shutting down servers...")
        for server_id, process in processes.items():
            if process.returncode is None:
                logger.info("Stopping %s (PID: %d)", server_id, process.pid)
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Force killing %s", server_id)
                    process.kill()

        # Cancel monitoring tasks
        for task in tasks:
            task.cancel()

        logger.info("All servers stopped")


def main() -> None:
    """Main entry point for the MCP server runner."""
    parser = argparse.ArgumentParser(
        description="Launch all enabled MCP servers in HTTP mode"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=get_default_config_path(),
        help="Path to mcp_servers.json configuration file",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind servers to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    asyncio.run(run_servers(args.config, args.host))


if __name__ == "__main__":
    main()
