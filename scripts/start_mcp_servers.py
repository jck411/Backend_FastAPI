#!/usr/bin/env python3
"""Standalone MCP server launcher.

Starts all enabled MCP servers from mcp_servers.json as independent HTTP services.
These servers can then be connected to by the backend or other clients.

Usage:
    python scripts/start_mcp_servers.py
    python scripts/start_mcp_servers.py --servers shell-control,notes
    python scripts/start_mcp_servers.py --config data/mcp_servers.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

# Add src to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from dotenv import dotenv_values


def load_server_configs(config_path: Path) -> list[dict[str, Any]]:
    """Load MCP server configurations from JSON file."""
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        data = json.load(f)

    if isinstance(data, dict):
        return data.get("servers", [])
    return data


def build_env() -> dict[str, str]:
    """Build environment variables for MCP servers."""
    env = os.environ.copy()
    dotenv_path = PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        for key, value in dotenv_values(dotenv_path).items():
            if key and value is not None:
                env.setdefault(key, value)

    # Ensure PYTHONPATH includes src
    pythonpath = env.get("PYTHONPATH", "")
    src_str = str(SRC_DIR)
    if src_str not in pythonpath.split(os.pathsep):
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [pythonpath, src_str]))

    # Disable FastMCP banner for cleaner output
    env["FASTMCP_SHOW_CLI_BANNER"] = "false"
    env["PYTHONUNBUFFERED"] = "1"

    return env


async def start_server(
    server_id: str,
    module: str,
    port: int,
    env: dict[str, str],
    server_env: dict[str, str],
) -> asyncio.subprocess.Process | None:
    """Start a single MCP server."""
    merged_env = {**env, **server_env}

    argv = [
        sys.executable,
        "-m",
        module,
        "--transport",
        "streamable-http",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]

    print(f"  Starting {server_id} on :{port}...")

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(PROJECT_ROOT),
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return process
    except Exception as e:
        print(f"  ✗ Failed to start {server_id}: {e}")
        return None


async def drain_output(
    process: asyncio.subprocess.Process,
    server_id: str,
    verbose: bool = False,
) -> None:
    """Drain stdout/stderr from a process."""
    async def drain_stream(stream: asyncio.StreamReader, label: str) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if verbose and text:
                print(f"[{server_id}] {text}")

    tasks = []
    if process.stdout:
        tasks.append(asyncio.create_task(drain_stream(process.stdout, "stdout")))
    if process.stderr:
        tasks.append(asyncio.create_task(drain_stream(process.stderr, "stderr")))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait for a server to accept connections."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return True
        except OSError:
            await asyncio.sleep(0.2)
    return False


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start MCP servers as independent HTTP services"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "data" / "mcp_servers.json",
        help="Path to mcp_servers.json",
    )
    parser.add_argument(
        "--servers",
        type=str,
        default=None,
        help="Comma-separated list of server IDs to start (default: all enabled)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show server output",
    )
    args = parser.parse_args()

    configs = load_server_configs(args.config)
    base_env = build_env()

    # Filter to requested servers
    requested = None
    if args.servers:
        requested = set(s.strip() for s in args.servers.split(","))

    servers_to_start = []
    for cfg in configs:
        server_id = cfg.get("id")
        if not server_id:
            continue
        if not cfg.get("enabled", True):
            continue
        if requested and server_id not in requested:
            continue
        if not cfg.get("module"):
            continue  # Skip non-module servers (remote URLs)

        servers_to_start.append(cfg)

    if not servers_to_start:
        print("No servers to start.")
        return

    print(f"\n{'='*50}")
    print("MCP Server Pool")
    print(f"{'='*50}\n")
    print(f"Starting {len(servers_to_start)} MCP server(s)...\n")

    processes: dict[str, asyncio.subprocess.Process] = {}
    drain_tasks: list[asyncio.Task] = []

    for cfg in servers_to_start:
        server_id = cfg["id"]
        module = cfg["module"]
        port = cfg.get("http_port", 9000)
        server_env = cfg.get("env", {})

        process = await start_server(server_id, module, port, base_env, server_env)
        if process:
            processes[server_id] = process
            if args.verbose:
                task = asyncio.create_task(drain_output(process, server_id, verbose=True))
                drain_tasks.append(task)

    # Wait for servers to be ready
    print("\nWaiting for servers to be ready...")
    for cfg in servers_to_start:
        server_id = cfg["id"]
        port = cfg.get("http_port", 9000)
        if server_id in processes:
            ready = await wait_for_server("127.0.0.1", port, timeout=15.0)
            if ready:
                print(f"  ✓ {server_id} ready on http://127.0.0.1:{port}/mcp")
            else:
                print(f"  ✗ {server_id} failed to start")

    print(f"\n{'='*50}")
    print("All servers running. Press Ctrl+C to stop.")
    print(f"{'='*50}\n")

    # Setup signal handlers
    stop_event = asyncio.Event()

    def signal_handler() -> None:
        print("\nShutting down servers...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Wait for shutdown signal
    await stop_event.wait()

    # Terminate all processes
    for server_id, proc in processes.items():
        if proc.returncode is None:
            print(f"  Stopping {server_id}...")
            proc.terminate()

    # Wait for termination with timeout
    for server_id, proc in processes.items():
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    # Cancel drain tasks
    for task in drain_tasks:
        task.cancel()

    print("All servers stopped.")


if __name__ == "__main__":
    asyncio.run(main())
